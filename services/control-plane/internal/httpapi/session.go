package httpapi

import (
	"net/http"
	"time"
)

type signInRequest struct {
	Email  string `json:"email"`
	Secret string `json:"secret"`
}

// signIn authenticates a person and issues a session.
//
// The session token is returned in a cookie the browser cannot read from
// script, and also in the body for programmatic clients that hold it
// themselves.
func (d *Dependencies) signIn(w http.ResponseWriter, r *http.Request) {
	var request signInRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}

	session, token, principal, err := d.Identity.SignIn(r.Context(), request.Email, request.Secret)
	if err != nil {
		writeError(w, r, err)
		return
	}

	http.SetCookie(w, &http.Cookie{
		Name:     SessionCookie,
		Value:    token,
		Path:     "/",
		Expires:  session.ExpiresAt,
		HttpOnly: true,
		Secure:   d.SecureCookies,
		SameSite: http.SameSiteLaxMode,
	})
	writeJSON(w, r, http.StatusCreated, map[string]any{
		"token":     token,
		"expiresAt": session.ExpiresAt,
		"principal": principal,
	})
}

// signOut ends the caller's own sign-in.
func (d *Dependencies) signOut(w http.ResponseWriter, r *http.Request) {
	if cookie, err := r.Cookie(SessionCookie); err == nil && cookie.Value != "" {
		if err := d.Identity.RevokeSession(r.Context(), cookie.Value); err != nil {
			writeError(w, r, err)
			return
		}
	}
	http.SetCookie(w, &http.Cookie{
		Name:     SessionCookie,
		Value:    "",
		Path:     "/",
		Expires:  time.Unix(0, 0),
		HttpOnly: true,
		Secure:   d.SecureCookies,
		SameSite: http.SameSiteLaxMode,
	})
	w.WriteHeader(http.StatusNoContent)
}

// me reports who the caller is and which organisations' bindings apply to them.
func (d *Dependencies) me(w http.ResponseWriter, r *http.Request) {
	principal, signedIn := principalOf(r.Context())
	if !signedIn {
		writeUnauthenticated(w, r)
		return
	}
	subject, _ := subjectOf(r.Context())

	organisations := make([]any, 0, len(subject.OrgIDs))
	for _, orgID := range subject.OrgIDs {
		org, err := d.Identity.Organisation(r.Context(), orgID)
		if err != nil {
			writeError(w, r, err)
			return
		}
		organisations = append(organisations, org)
	}

	writeJSON(w, r, http.StatusOK, map[string]any{
		"principal":     principal,
		"organisations": organisations,
	})
}
