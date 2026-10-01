package httpapi

import (
	"net/http"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// A person's own tokens: made for a program to act as them, listed so they can
// see which are in use, and revoked in one call.
//
// Only by somebody who signed in themselves. A request arriving through a token
// is refused here, because a token that could make another would let a leaked
// one outlive being revoked: revoke it, and it has already made its successor.

type createTokenRequest struct {
	Name string `json:"name"`
	// Days until it stops working. Zero or absent is no expiry, which is what
	// an assistant on somebody's own laptop usually wants; an afternoon's
	// experiment can say one.
	ExpiresInDays int `json:"expiresInDays,omitempty"`
}

func (d *Dependencies) refuseTokenBearers(w http.ResponseWriter, r *http.Request) bool {
	if !viaToken(r.Context()) {
		return false
	}
	writeDenied(w, r, policy.Decision{
		Effect: policy.EffectDenyVisible,
		Reason: "tokens are made and revoked by signing in, not with a token: " +
			"one that could make another would outlive being revoked",
	})
	return true
}

func (d *Dependencies) listTokens(w http.ResponseWriter, r *http.Request) {
	principal, signedIn := principalOf(r.Context())
	if !signedIn {
		writeUnauthenticated(w, r)
		return
	}
	tokens, err := d.Identity.TokensOf(r.Context(), principal.ID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"tokens": tokens})
}

func (d *Dependencies) createToken(w http.ResponseWriter, r *http.Request) {
	if d.refuseTokenBearers(w, r) {
		return
	}
	principal, signedIn := principalOf(r.Context())
	if !signedIn {
		writeUnauthenticated(w, r)
		return
	}
	var request createTokenRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	lifetime := time.Duration(0)
	if request.ExpiresInDays > 0 {
		lifetime = time.Duration(request.ExpiresInDays) * 24 * time.Hour
	}
	made, token, err := d.Identity.CreateToken(r.Context(), principal, request.Name, lifetime)
	if err != nil {
		writeError(w, r, err)
		return
	}
	// The token itself, once. It is not stored, so it cannot be shown again —
	// only replaced.
	writeJSON(w, r, http.StatusCreated, map[string]any{
		"apiToken": made,
		"token":    token,
		"shownOnce": "this is the only time the token is shown; keep it where the " +
			"program that will use it can read it",
	})
}

func (d *Dependencies) revokeToken(w http.ResponseWriter, r *http.Request) {
	if d.refuseTokenBearers(w, r) {
		return
	}
	principal, signedIn := principalOf(r.Context())
	if !signedIn {
		writeUnauthenticated(w, r)
		return
	}
	if err := d.Identity.RevokeToken(r.Context(), principal.ID, r.PathValue("tokenId")); err != nil {
		writeError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
