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
const SessionCookie = "iocean_session"

// OldSessionCookie is the name the session was kept under before the rename;
// a browser signed in then is still signed in (docs/plan/iocean-rename.md).
const OldSessionCookie = "coral_session"

// sessionCookie is the caller's session cookie under either name, the new first.
func sessionCookie(r *http.Request) (*http.Cookie, error) {
	if cookie, err := r.Cookie(SessionCookie); err == nil && cookie.Value != "" {
		return cookie, nil
	}
	return r.Cookie(OldSessionCookie)
}

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

// Unwrap hands back the writer underneath, so that a handler which needs the
// connection itself can reach it.
//
// Without this, anything wrapping the response writer hides the connection
// from http.ResponseController, and a handler asking to extend its write
// deadline is told the feature is not supported — which is what happened to
// drafting a plan: the model thought for forty seconds, the server closed the
// connection at thirty, and the console saw an empty reply with no reason
// attached. A recorder that counts bytes should not also decide what a
// handler may do with its own connection.
func (s *statusRecorder) Unwrap() http.ResponseWriter { return s.ResponseWriter }

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
		principal, found, via, err := d.resolvePrincipal(r)
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
			ViaToken: via,
		}
		next.ServeHTTP(w, r.WithContext(withCaller(r.Context(), who)))
	})
}

func (d *Dependencies) resolvePrincipal(r *http.Request) (identity.Principal, bool, bool, error) {
	if header := r.Header.Get("Authorization"); header != "" {
		scheme, credential, found := strings.Cut(header, " ")
		if !found {
			return identity.Principal{}, false, false, nil
		}
		switch {
		// A personal token is a Bearer like a session, told apart by its
		// prefix, because every MCP client and every HTTP library already
		// knows how to send a Bearer and nothing should have to learn a third
		// scheme for the thing a person is most likely to paste.
		case strings.EqualFold(scheme, "Bearer") && strings.HasPrefix(credential, identity.TokenPrefix):
			principal, err := d.Identity.AuthenticateToken(r.Context(), credential)
			p, ok, err := resolved(principal, err)
			return p, ok, ok, err
		case strings.EqualFold(scheme, "Bearer"):
			principal, err := d.Identity.AuthenticateSession(r.Context(), credential)
			p, ok, err := resolved(principal, err)
			return p, ok, false, err
		case strings.EqualFold(scheme, "Service"):
			principal, err := d.Identity.AuthenticateService(r.Context(), credential)
			p, ok, err := resolved(principal, err)
			return p, ok, false, err
		default:
			return identity.Principal{}, false, false, nil
		}
	}

	cookie, err := sessionCookie(r)
	if err != nil || cookie.Value == "" {
		return identity.Principal{}, false, false, nil
	}
	principal, authErr := d.Identity.AuthenticateSession(r.Context(), cookie.Value)
	p, ok, err := resolved(principal, authErr)
	return p, ok, false, err
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
