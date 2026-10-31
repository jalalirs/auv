package httpapi

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"html/template"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/exec"
	"github.com/jalalirs/auv/services/control-plane/internal/identity"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// GoogleSignIn is the platform's Google client. Its zero value is a platform
// that has none.
type GoogleSignIn struct {
	ClientID     string
	ClientSecret string
	// PublicURL is this service as a browser reaches it; Google redirects to
	// PublicURL + googleCallbackPath, which must be registered on the client.
	PublicURL string
	// WebReturn is where a browser lands once signed in.
	WebReturn string
}

func (g GoogleSignIn) configured() bool { return g.ClientID != "" && g.ClientSecret != "" }

func (g GoogleSignIn) redirectURI() string { return g.PublicURL + googleCallbackPath }

// PersonalStart is what a person's own organisation is given when they first
// sign in.
type PersonalStart struct {
	DivesMonthly int
	DailyCap     int
	Queue        string
	Vehicles     []string
}

const (
	googleCallbackPath = "/api/v1/auth/google/callback"
	googleCookie       = "iocean_google"
	googleAuthorize    = "https://accounts.google.com/o/oauth2/v2/auth"
	googleToken        = "https://oauth2.googleapis.com/token"
)

// googleStart sends a browser to Google. The state and the PKCE verifier ride
// in a cookie only this path reads, so the callback can check that the answer
// is to a question this browser asked.
func (d *Dependencies) googleStart(w http.ResponseWriter, r *http.Request) {
	if !d.Google.configured() {
		signInPage(w, http.StatusServiceUnavailable, "Google sign-in is not set up",
			"This iOcean platform has no Google client yet.", "")
		return
	}
	client := r.URL.Query().Get("client")
	if client != "desktop" {
		client = "web"
	}
	state, verifier := randomText(), randomText()
	challenge := sha256.Sum256([]byte(verifier))

	http.SetCookie(w, &http.Cookie{
		Name: googleCookie, Value: state + "." + verifier + "." + client,
		Path: "/api/v1/auth/google", MaxAge: 600,
		HttpOnly: true, Secure: d.SecureCookies, SameSite: http.SameSiteLaxMode,
	})
	query := url.Values{
		"client_id":             {d.Google.ClientID},
		"redirect_uri":          {d.Google.redirectURI()},
		"response_type":         {"code"},
		"scope":                 {"openid email profile"},
		"state":                 {state},
		"code_challenge":        {base64.RawURLEncoding.EncodeToString(challenge[:])},
		"code_challenge_method": {"S256"},
		"prompt":                {"select_account"},
	}
	http.Redirect(w, r, googleAuthorize+"?"+query.Encode(), http.StatusFound)
}

// googleCallback is where Google sends the browser back. It trades the code
// for an ID token on this side, finds or makes the person, brings their
// memberships into line with what institutions approve, and signs them in: in
// the browser for the web, or through a one-minute code for the desktop app.
func (d *Dependencies) googleCallback(w http.ResponseWriter, r *http.Request) {
	if !d.Google.configured() {
		signInPage(w, http.StatusServiceUnavailable, "Google sign-in is not set up",
			"This iOcean platform has no Google client yet.", "")
		return
	}
	http.SetCookie(w, &http.Cookie{Name: googleCookie, Value: "", Path: "/api/v1/auth/google",
		MaxAge: -1, HttpOnly: true, Secure: d.SecureCookies, SameSite: http.SameSiteLaxMode})

	cookie, err := r.Cookie(googleCookie)
	parts := []string{}
	if err == nil {
		parts = strings.Split(cookie.Value, ".")
	}
	query := r.URL.Query()
	if len(parts) != 3 || subtle.ConstantTimeCompare([]byte(parts[0]), []byte(query.Get("state"))) != 1 {
		signInPage(w, http.StatusBadRequest, "That sign-in had expired",
			"Start again from the iOcean app or the website.", "")
		return
	}
	verifier, client := parts[1], parts[2]
	if reason := query.Get("error"); reason != "" {
		signInPage(w, http.StatusOK, "Sign-in was cancelled", "Google said: "+reason, "")
		return
	}

	account, err := d.googleAccount(r.Context(), query.Get("code"), verifier)
	if err != nil {
		d.Logger.Warn("google sign-in failed", "error", err)
		signInPage(w, http.StatusBadGateway, "Google did not confirm who you are",
			"Try again in a moment.", "")
		return
	}

	principalID, err := d.signInGoogle(r.Context(), account)
	if err != nil {
		var message string
		switch {
		case errors.Is(err, errPersonalCapReached):
			message = "iOcean has taken all the new accounts it can today. Try again tomorrow."
		case errors.Is(err, identity.ErrUnverifiedEmail):
			message = "Google has not verified this account's email address."
		default:
			d.Logger.Error("google sign-in could not be recorded", "error", err)
			message = "Something went wrong on our side. Try again in a moment."
		}
		signInPage(w, http.StatusForbidden, "You could not be signed in", message, "")
		return
	}

	if client == "desktop" {
		code, err := d.Identity.CreateHandoff(r.Context(), principalID)
		if err != nil {
			d.Logger.Error("hand-off code not made", "error", err)
			signInPage(w, http.StatusInternalServerError, "You could not be signed in",
				"Something went wrong on our side. Try again in a moment.", "")
			return
		}
		signInPage(w, http.StatusOK, "You are signed in",
			"Go back to iOcean. If it did not open, use the button.",
			"iocean://signed-in?code="+url.QueryEscape(code))
		return
	}

	session, token, _, err := d.Identity.IssueSession(r.Context(), principalID)
	if err != nil {
		signInPage(w, http.StatusForbidden, "You could not be signed in", err.Error(), "")
		return
	}
	d.setSessionCookie(w, token, session.ExpiresAt)
	http.Redirect(w, r, d.Google.WebReturn, http.StatusSeeOther)
}

// googleAccount trades an authorisation code for Google's ID token and reads
// it. The token comes straight from Google's token endpoint over TLS, so its
// issuer, audience and expiry are checked and its signature is not (OpenID
// Connect Core 3.1.3.7).
func (d *Dependencies) googleAccount(ctx context.Context, code, verifier string) (identity.GoogleAccount, error) {
	if code == "" {
		return identity.GoogleAccount{}, errors.New("no code in the callback")
	}
	ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
	defer cancel()
	form := url.Values{
		"code":          {code},
		"client_id":     {d.Google.ClientID},
		"client_secret": {d.Google.ClientSecret},
		"redirect_uri":  {d.Google.redirectURI()},
		"grant_type":    {"authorization_code"},
		"code_verifier": {verifier},
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPost, googleToken, strings.NewReader(form.Encode()))
	if err != nil {
		return identity.GoogleAccount{}, err
	}
	request.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		return identity.GoogleAccount{}, fmt.Errorf("asking Google for the token: %w", err)
	}
	defer response.Body.Close()
	var answer struct {
		IDToken string `json:"id_token"`
		Error   string `json:"error"`
	}
	if err := json.NewDecoder(response.Body).Decode(&answer); err != nil {
		return identity.GoogleAccount{}, fmt.Errorf("reading Google's answer: %w", err)
	}
	if response.StatusCode != http.StatusOK || answer.IDToken == "" {
		return identity.GoogleAccount{}, fmt.Errorf("Google refused the code: %d %s", response.StatusCode, answer.Error)
	}
	return readGoogleIDToken(answer.IDToken, d.Google.ClientID, time.Now())
}

// readGoogleIDToken reads the claims of an ID token Google handed this
// process directly, and refuses one that is not for this client, not from
// Google, or expired.
func readGoogleIDToken(token, clientID string, now time.Time) (identity.GoogleAccount, error) {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return identity.GoogleAccount{}, errors.New("an ID token has three parts")
	}
	payload, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return identity.GoogleAccount{}, fmt.Errorf("decoding the ID token: %w", err)
	}
	var claims struct {
		Iss           string `json:"iss"`
		Aud           string `json:"aud"`
		Sub           string `json:"sub"`
		Exp           int64  `json:"exp"`
		Email         string `json:"email"`
		EmailVerified bool   `json:"email_verified"`
		Name          string `json:"name"`
		HD            string `json:"hd"`
	}
	if err := json.Unmarshal(payload, &claims); err != nil {
		return identity.GoogleAccount{}, fmt.Errorf("reading the ID token: %w", err)
	}
	switch {
	case claims.Iss != "https://accounts.google.com" && claims.Iss != "accounts.google.com":
		return identity.GoogleAccount{}, fmt.Errorf("the ID token is from %q, not Google", claims.Iss)
	case claims.Aud != clientID:
		return identity.GoogleAccount{}, errors.New("the ID token is for another client")
	case now.Unix() >= claims.Exp:
		return identity.GoogleAccount{}, errors.New("the ID token has expired")
	case claims.Sub == "" || claims.Email == "":
		return identity.GoogleAccount{}, errors.New("the ID token names no account")
	}
	return identity.GoogleAccount{
		Subject: claims.Sub, Email: claims.Email, EmailVerified: claims.EmailVerified,
		HostedDomain: strings.ToLower(claims.HD), Name: claims.Name,
	}, nil
}

var errPersonalCapReached = errors.New("today's new personal organisations are all made")

// signInGoogle finds or makes the person a Google account is, makes sure they
// have their own organisation, and lines their memberships up with what
// institutions approve, in one transaction.
func (d *Dependencies) signInGoogle(ctx context.Context, account identity.GoogleAccount) (string, error) {
	var principalID string
	err := d.Pool.InTransaction(ctx, func(conn db.Conn) error {
		id, found, err := d.Identity.PersonForGoogle(ctx, conn, account)
		if err != nil {
			return err
		}
		if !found {
			today := time.Now().UTC().Truncate(24 * time.Hour)
			made, err := d.Identity.PersonalOrganisationsSince(ctx, conn, today)
			if err != nil {
				return err
			}
			if made >= d.Personal.DailyCap {
				return errPersonalCapReached
			}
			person, err := d.Identity.CreateGooglePerson(ctx, conn, account)
			if err != nil {
				return err
			}
			id = person.ID
			if err := d.Audit.Record(ctx, conn, audit.Event{
				ActorID: id, Action: "self.sign_up", SubjectKind: "principal", SubjectID: id,
				Outcome: audit.Succeeded, Detail: map[string]any{"provider": "google"},
			}); err != nil {
				return err
			}
		}
		principalID = id
		if err := d.ensurePersonal(ctx, conn, id); err != nil {
			return err
		}
		return d.Identity.SyncApprovals(ctx, conn, "", id)
	})
	return principalID, err
}

// ensurePersonal founds a person's own organisation if they have none: its
// own contributor binding, a quota with this platform's monthly dives, and
// the starter queue and vehicles.
func (d *Dependencies) ensurePersonal(ctx context.Context, conn db.Conn, principalID string) error {
	var exists bool
	if err := conn.QueryRow(ctx,
		`SELECT EXISTS (SELECT 1 FROM identity.organisation WHERE personal_of = $1)`,
		principalID).Scan(&exists); err != nil {
		return fmt.Errorf("looking for a personal organisation: %w", err)
	}
	if exists {
		return nil
	}
	// Read inside the transaction: the person may have been made in it.
	person := identity.Principal{ID: principalID, Kind: identity.Person}
	if err := conn.QueryRow(ctx,
		`SELECT display_name, email FROM identity.principal WHERE id = $1`, principalID).
		Scan(&person.DisplayName, &person.Email); err != nil {
		return fmt.Errorf("reading the person: %w", db.Translate(err))
	}
	org, err := d.Identity.CreatePersonalOrganisation(ctx, conn, person)
	if err != nil {
		return err
	}
	grants := []policy.GrantSpec{{
		SubjectKind: policy.SubjectOrg, SubjectID: org.ID,
		ScopeKind: policy.ScopeOrg, ScopeID: org.ID, Role: policy.RoleContributor,
	}}
	if d.Personal.Queue != "" {
		grants = append(grants, policy.GrantSpec{
			SubjectKind: policy.SubjectOrg, SubjectID: org.ID,
			ScopeKind: policy.ScopeQueue, ScopeID: d.Personal.Queue, Role: policy.RoleContributor,
		})
	}
	for _, vehicle := range d.Personal.Vehicles {
		grants = append(grants, policy.GrantSpec{
			SubjectKind: policy.SubjectOrg, SubjectID: org.ID,
			ScopeKind: policy.ScopeVehicle, ScopeID: vehicle, Role: policy.RoleViewer,
		})
	}
	for _, grant := range grants {
		grant.CreatedBy = principalID
		if _, err := d.Authorizer.Grant(ctx, conn, grant); err != nil {
			return err
		}
	}
	monthly := d.Personal.DivesMonthly
	if _, err := d.Broker.SetQuota(ctx, conn, exec.Quota{
		OrgID: org.ID, MaxConcurrentJobs: 1, MaxCPU: 8, MaxMemoryBytes: 32 << 30, MaxGPU: 1,
		MaxConcurrentDives: 1, MaxGPUHoursDaily: 4, MaxDivesMonthly: &monthly,
	}); err != nil {
		return err
	}
	return d.Audit.Record(ctx, conn, audit.Event{
		ActorID: principalID, Action: "self.sign_up", SubjectKind: "organisation", SubjectID: org.ID,
		Outcome: audit.Succeeded, Detail: map[string]any{"slug": org.Slug, "personal": true},
	})
}

type exchangeRequest struct {
	Code string `json:"code"`
}

// exchangeHandoff trades the code a desktop app was handed back through
// iocean:// for a session, once.
func (d *Dependencies) exchangeHandoff(w http.ResponseWriter, r *http.Request) {
	var request exchangeRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	if request.Code == "" {
		writeError(w, r, fmt.Errorf("%w: a code is needed", domain.ErrInvalid))
		return
	}
	session, token, principal, err := d.Identity.RedeemHandoff(r.Context(), request.Code)
	if err != nil {
		writeError(w, r, err)
		return
	}
	d.setSessionCookie(w, token, session.ExpiresAt)
	writeJSON(w, r, http.StatusCreated, map[string]any{
		"token": token, "expiresAt": session.ExpiresAt, "principal": principal,
	})
}

func (d *Dependencies) setSessionCookie(w http.ResponseWriter, token string, expires time.Time) {
	http.SetCookie(w, &http.Cookie{
		Name: SessionCookie, Value: token, Path: "/", Expires: expires,
		HttpOnly: true, Secure: d.SecureCookies, SameSite: http.SameSiteLaxMode,
	})
}

func randomText() string {
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		panic(fmt.Sprintf("drawing random bytes: %v", err))
	}
	return base64.RawURLEncoding.EncodeToString(raw)
}

var signInTemplate = template.Must(template.New("sign-in").Parse(`<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{.Title}}: iOcean</title>
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#f5f8fa;color:#071220;
font:17px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
main{max-width:30rem;padding:24px;text-align:center}
h1{font-size:28px;letter-spacing:-0.02em;margin:0 0 12px}
p{color:#4f5f70;margin:0 0 24px}
a{display:inline-block;padding:12px 22px;border-radius:11px;background:#071220;color:#fff;text-decoration:none}
</style></head>
<body><main><h1>{{.Title}}</h1><p>{{.Message}}</p>
{{if .Link}}<a href="{{.Link}}">Open iOcean</a>
<script>window.location.href = {{.Link}};</script>{{end}}
</main></body></html>`))

// signInPage answers a browser in the middle of signing in with a page, not
// JSON: whoever is looking at it is a person, not a program.
func signInPage(w http.ResponseWriter, status int, title, message, link string) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.Header().Set("Cache-Control", "no-store")
	w.WriteHeader(status)
	_ = signInTemplate.Execute(w, map[string]any{
		"Title": title, "Message": message, "Link": template.URL(link),
	})
}
