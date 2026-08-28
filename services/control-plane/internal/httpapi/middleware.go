package httpapi

import (
	"errors"
	"log/slog"
	"net/http"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/identity"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
	"github.com/jalalirs/auv/services/control-plane/internal/reqctx"
)

// SessionCookie is where a browser keeps its session token. It is read by the
// server and never by script, so a cross-site scripting flaw cannot exfiltrate
// a session.
const SessionCookie = "coral_session"

// withRequestID gives every request an identifier that ties together every
// record written while serving it: audit events, denials, admissions, and
// refusals. A client-supplied identifier is not trusted, because it would let a
// caller forge the trail.
func withRequestID(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := ids.New(ids.KindAuditEvent)
		w.Header().Set("X-Request-ID", id)
		next.ServeHTTP(w, r.WithContext(reqctx.WithRequestID(r.Context(), id)))
	})
}

// statusRecorder remembers what was written so a request can be logged with
// its outcome.
type statusRecorder struct {
	http.ResponseWriter
	status int
	bytes  int
}

func (s *statusRecorder) WriteHeader(status int) {
	if s.status == 0 {
		s.status = status
		s.ResponseWriter.WriteHeader(status)
	}
}

func (s *statusRecorder) Write(body []byte) (int, error) {
	if s.status == 0 {
		s.status = http.StatusOK
	}
	written, err := s.ResponseWriter.Write(body)
	s.bytes += written
	return written, err
}

// Flush lets streaming responses reach the client as they are produced.
func (s *statusRecorder) Flush() {
	if flusher, ok := s.ResponseWriter.(http.Flusher); ok {
		flusher.Flush()
	}
}

func logRequests(logger *slog.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		started := time.Now()
		recorder := &statusRecorder{ResponseWriter: w}
		next.ServeHTTP(recorder, r)
		if recorder.status == 0 {
			recorder.status = http.StatusOK
		}
		logger.LogAttrs(r.Context(), slog.LevelInfo, "request served",
			slog.String("method", r.Method),
			slog.String("path", r.URL.Path),
			slog.Int("status", recorder.status),
			slog.Int("bytes", recorder.bytes),
			slog.Duration("took", time.Since(started)),
			slog.String("requestId", reqctx.RequestID(r.Context())))
	})
}

// recoverPanics keeps one failing request from ending the process, and reports
// it as a fault rather than as a hung connection.
func recoverPanics(logger *slog.Logger, next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		defer func() {
			if recovered := recover(); recovered != nil {
				logger.LogAttrs(r.Context(), slog.LevelError, "request panicked",
					slog.Any("panic", recovered),
					slog.String("method", r.Method),
					slog.String("path", r.URL.Path),
					slog.String("requestId", reqctx.RequestID(r.Context())))
				writeProblem(w, r, http.StatusInternalServerError, "internal_error",
					"something went wrong serving this request", nil)
			}
		}()
		next.ServeHTTP(w, r)
	})
}

// authenticate establishes who is calling, if anyone.
//
// It decides nothing about what they may do. A request with no credentials, or
// with credentials that identify nobody, simply carries no subject; the router
// then refuses every route that is not public.
func (d *Dependencies) authenticate(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		principal, found, err := d.resolvePrincipal(r)
		if err != nil {
			writeError(w, r, err)
			return
		}
		if !found {
			next.ServeHTTP(w, r)
			return
		}

		orgs, err := d.Identity.OrganisationsOf(r.Context(), principal.ID)
		if err != nil {
			writeError(w, r, err)
			return
		}
		who := caller{
			Principal: principal,
			Subject: policy.Subject{
				PrincipalID: principal.ID,
				OrgIDs:      orgs,
				IsService:   principal.Kind == identity.Service,
			},
		}
		next.ServeHTTP(w, r.WithContext(withCaller(r.Context(), who)))
	})
}

func (d *Dependencies) resolvePrincipal(r *http.Request) (identity.Principal, bool, error) {
	if header := r.Header.Get("Authorization"); header != "" {
		scheme, credential, found := strings.Cut(header, " ")
		if !found {
			return identity.Principal{}, false, nil
		}
		switch {
		case strings.EqualFold(scheme, "Bearer"):
			principal, err := d.Identity.AuthenticateSession(r.Context(), credential)
			return resolved(principal, err)
		case strings.EqualFold(scheme, "Service"):
			principal, err := d.Identity.AuthenticateService(r.Context(), credential)
			return resolved(principal, err)
		default:
			return identity.Principal{}, false, nil
		}
	}

	cookie, err := r.Cookie(SessionCookie)
	if err != nil || cookie.Value == "" {
		return identity.Principal{}, false, nil
	}
	principal, authErr := d.Identity.AuthenticateSession(r.Context(), cookie.Value)
	return resolved(principal, authErr)
}

// resolved treats credentials that identify nobody as absence rather than as a
// fault, so that an expired session is refused the same way a missing one is.
func resolved(principal identity.Principal, err error) (identity.Principal, bool, error) {
	switch {
	case err == nil:
		return principal, true, nil
	case errors.Is(err, identity.ErrUnauthenticated), errors.Is(err, identity.ErrDisabled):
		return identity.Principal{}, false, nil
	default:
		return identity.Principal{}, false, err
	}
}
