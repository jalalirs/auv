package httpapi

import (
	"encoding/base64"
	"encoding/json"
	"strings"
	"testing"
	"time"
)

func idToken(t *testing.T, claims map[string]any) string {
	t.Helper()
	payload, err := json.Marshal(claims)
	if err != nil {
		t.Fatal(err)
	}
	return "e30." + base64.RawURLEncoding.EncodeToString(payload) + ".sig"
}

func TestAGoogleIDTokenIsReadOnlyWhenItIsForUsFromGoogleAndCurrent(t *testing.T) {
	now := time.Unix(1_800_000_000, 0)
	good := map[string]any{
		"iss": "https://accounts.google.com", "aud": "client-1", "sub": "1234",
		"exp": now.Unix() + 300, "email": "Ali@KAUST.edu.sa", "email_verified": true,
		"name": "Ali", "hd": "KAUST.edu.sa",
	}
	account, err := readGoogleIDToken(idToken(t, good), "client-1", now)
	if err != nil {
		t.Fatalf("a good token was refused: %v", err)
	}
	if account.Subject != "1234" || !account.EmailVerified || account.HostedDomain != "kaust.edu.sa" {
		t.Fatalf("read %+v", account)
	}

	for name, change := range map[string]map[string]any{
		"another client": {"aud": "client-2"},
		"not Google":     {"iss": "https://evil.example"},
		"expired":        {"exp": now.Unix()},
		"no account":     {"sub": ""},
	} {
		claims := map[string]any{}
		for k, v := range good {
			claims[k] = v
		}
		for k, v := range change {
			claims[k] = v
		}
		if _, err := readGoogleIDToken(idToken(t, claims), "client-1", now); err == nil {
			t.Errorf("a token from %s was accepted", name)
		}
	}
	if _, err := readGoogleIDToken("not-a-token", "client-1", now); err == nil ||
		!strings.Contains(err.Error(), "three parts") {
		t.Errorf("a malformed token gave %v", err)
	}
}
