package httpapi

import (
	"encoding/json"
	"errors"
	"log/slog"
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/exec"
	"github.com/jalalirs/auv/services/control-plane/internal/identity"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
	"github.com/jalalirs/auv/services/control-plane/internal/reqctx"
	"github.com/jalalirs/auv/services/control-plane/internal/storage"
)

// problem is the shape of every failure the API reports. The message is
// written for the person who will read it.
type problem struct {
	Code      string         `json:"code"`
	Message   string         `json:"message"`
	RequestID string         `json:"requestId"`
	Detail    map[string]any `json:"detail,omitempty"`
}

func writeProblem(w http.ResponseWriter, r *http.Request, status int, code, message string, detail map[string]any) {
	writeJSON(w, r, status, map[string]any{"error": problem{
		Code:      code,
		Message:   message,
		RequestID: reqctx.RequestID(r.Context()),
		Detail:    detail,
	}})
}

func writeJSON(w http.ResponseWriter, r *http.Request, status int, body any) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	if r.Method == http.MethodHead || body == nil {
		return
	}
	encoder := json.NewEncoder(w)
	encoder.SetEscapeHTML(false)
	_ = encoder.Encode(body)
}

func writeUnauthenticated(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("WWW-Authenticate", `Bearer realm="coral-city"`)
	writeProblem(w, r, http.StatusUnauthorized, "unauthenticated",
		"sign in to use this", nil)
}

// writeDenied reports a refusal in the terms the decision point chose. A hidden
// denial reports absence, because the existence of some places is itself
// sensitive; a visible denial says the thing exists and access may be
// requested.
func writeDenied(w http.ResponseWriter, r *http.Request, decision policy.Decision) {
	if decision.Effect == policy.EffectDenyHidden {
		writeProblem(w, r, http.StatusNotFound, "not_found", decision.Reason, nil)
		return
	}
	writeProblem(w, r, http.StatusForbidden, "forbidden", decision.Reason,
		map[string]any{"accessMayBeRequested": true})
}

// writeError maps an error from a component onto the response it deserves.
//
// The mapping lives here so that components raise errors in their own terms and
// no component has to know about HTTP.
func writeError(w http.ResponseWriter, r *http.Request, err error) {
	var refusal *exec.Refusal
	var tooLarge *exec.OutputTooLarge

	switch {
	case errors.Is(err, db.ErrNotFound):
		writeProblem(w, r, http.StatusNotFound, "not_found", "that does not exist", nil)

	case errors.Is(err, domain.ErrInvalid):
		writeProblem(w, r, http.StatusBadRequest, "invalid", err.Error(), nil)

	case errors.Is(err, identity.ErrUnauthenticated):
		writeProblem(w, r, http.StatusUnauthorized, "unauthenticated", err.Error(), nil)

	case errors.Is(err, identity.ErrDisabled):
		writeProblem(w, r, http.StatusForbidden, "disabled", err.Error(), nil)

	case errors.Is(err, storage.ErrDigestMismatch):
		writeProblem(w, r, http.StatusUnprocessableEntity, "digest_mismatch", err.Error(), nil)

	case errors.Is(err, storage.ErrGrantSpent):
		writeProblem(w, r, http.StatusConflict, "grant_spent", err.Error(), nil)

	case errors.Is(err, exec.ErrLeaseInvalid):
		writeProblem(w, r, http.StatusConflict, "lease_invalid", err.Error(), nil)

	case errors.As(err, &refusal):
		// Work was refused because there is no room, which is a decision the
		// caller can act on rather than a fault.
		writeProblem(w, r, http.StatusTooManyRequests, string(refusal.Reason),
			refusal.Error(), refusal.Detail)

	case errors.As(err, &tooLarge):
		writeProblem(w, r, http.StatusUnprocessableEntity, "output_limit_exceeded",
			tooLarge.Error(), map[string]any{
				"name": tooLarge.Name, "sizeBytes": tooLarge.SizeBytes,
				"limitBytes": tooLarge.LimitBytes})

	case db.IsUniqueViolation(err):
		writeProblem(w, r, http.StatusConflict, "conflict", "that already exists", nil)

	default:
		if message, raised := db.RaisedMessage(err); raised {
			// A rule the schema enforces, reported in the words the schema used.
			writeProblem(w, r, http.StatusConflict, "refused_by_record", message, nil)
			return
		}
		// A failure nothing anticipated. The caller is told only that something
		// went wrong, because the detail may say more than they should learn —
		// but it is written down here, with the request identifier, or it would
		// be undiagnosable.
		slog.ErrorContext(r.Context(), "request failed unexpectedly",
			"error", err,
			"method", r.Method,
			"path", r.URL.Path,
			"requestId", reqctx.RequestID(r.Context()))
		writeProblem(w, r, http.StatusInternalServerError, "internal_error",
			"something went wrong serving this request", nil)
	}
}

// readJSON decodes a request body, refusing unknown fields so that a
// misspelled property is reported rather than silently ignored.
func readJSON(r *http.Request, into any) error {
	decoder := json.NewDecoder(http.MaxBytesReader(nil, r.Body, 1<<20))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(into); err != nil {
		return errors.Join(domain.ErrInvalid, err)
	}
	return nil
}
