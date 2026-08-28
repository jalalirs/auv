package identity

import (
	"strings"
	"testing"
)

// A stored verifier must not reveal the secret, and two people who choose the
// same secret must not have the same verifier.
func TestASecretIsNeverWrittenDown(t *testing.T) {
	secret := "a-perfectly-ordinary-secret"

	first, err := hashSecret(secret)
	if err != nil {
		t.Fatalf("hashSecret() error = %v", err)
	}
	second, err := hashSecret(secret)
	if err != nil {
		t.Fatalf("hashSecret() error = %v", err)
	}

	if strings.Contains(first, secret) {
		t.Fatal("the stored verifier contains the secret itself")
	}
	if first == second {
		t.Fatal("two verifiers for one secret are identical, so they carry no salt")
	}
	if !strings.HasPrefix(first, "$argon2id$") {
		t.Fatalf("the verifier is not argon2id: %s", first)
	}
}

func TestASecretIsRecognisedAndAWrongOneIsNot(t *testing.T) {
	verifier, err := hashSecret("the-right-secret-value")
	if err != nil {
		t.Fatalf("hashSecret() error = %v", err)
	}

	matches, err := verifySecret(verifier, "the-right-secret-value")
	if err != nil {
		t.Fatalf("verifySecret() error = %v", err)
	}
	if !matches {
		t.Fatal("the right secret was not recognised")
	}

	matches, err = verifySecret(verifier, "the-wrong-secret-value")
	if err != nil {
		t.Fatalf("verifySecret() error = %v", err)
	}
	if matches {
		t.Fatal("a wrong secret was accepted")
	}
}

// The decoy exists so that authenticating an address nobody holds costs the
// same as authenticating one that exists. If it stopped being a usable
// verifier, that timing difference would come back silently.
func TestTheDecoyVerifierIsUsable(t *testing.T) {
	matches, err := verifySecret(decoyVerifier, "anything at all")
	if err != nil {
		t.Fatalf("the decoy verifier cannot be used: %v", err)
	}
	if matches {
		t.Fatal("the decoy verifier accepted a secret, so somebody holds it")
	}
}

func TestAMalformedVerifierIsReportedRatherThanAccepted(t *testing.T) {
	for _, verifier := range []string{"", "not-a-verifier", "$argon2i$v=19$m=1,t=1,p=1$aaaa$bbbb"} {
		if _, err := verifySecret(verifier, "secret"); err == nil {
			t.Errorf("verifySecret(%q) accepted a malformed verifier", verifier)
		}
	}
}

// A session token is stored as its digest, so a disclosure of the record does
// not hand anyone a working session.
func TestASessionTokenIsStoredAsItsDigest(t *testing.T) {
	token, digest, err := newToken()
	if err != nil {
		t.Fatalf("newToken() error = %v", err)
	}
	if len(token) < 40 {
		t.Fatalf("a session token of %d characters is too short to be unguessable", len(token))
	}
	if strings.Contains(string(digest), token) {
		t.Fatal("the stored digest contains the token")
	}
	if len(digest) != 32 {
		t.Fatalf("digest is %d bytes, want 32", len(digest))
	}

	same := tokenDigest(token)
	if string(same) != string(digest) {
		t.Fatal("the same token produced two different digests")
	}

	other, _, err := newToken()
	if err != nil {
		t.Fatalf("newToken() error = %v", err)
	}
	if other == token {
		t.Fatal("two session tokens were identical")
	}
}
