package identity

import (
	"context"
	"errors"
	"strings"
	"testing"

	"github.com/jalalirs/auv/services/control-plane/internal/domain"
)

// A personal token says what it is, so that the middleware knows which lookup
// to make and a secret scanner can recognise one that leaked into a commit.
func TestAPersonalTokenCarriesItsPrefixAndASessionDoesNot(t *testing.T) {
	session, _, err := newToken()
	if err != nil {
		t.Fatal(err)
	}
	if strings.HasPrefix(session, TokenPrefix) {
		t.Fatalf("a session token %q starts with %q and would be read as a personal one",
			session, TokenPrefix)
	}
	// A session is base64url, whose alphabet has no underscore after a "cc":
	// the only way to start with "cc_" is to have been made one.
	if !strings.Contains(TokenPrefix, "_") {
		t.Fatal("the prefix must contain a character a session token cannot begin with")
	}
}

// Only a person makes tokens. A service principal already is a program, and a
// token that let one mint credentials for itself would be a way round whoever
// issued it. Refused before the record is touched.
func TestOnlyAPersonMakesTokens(t *testing.T) {
	store := &Store{}
	_, _, err := store.CreateToken(context.Background(),
		Principal{ID: "prin_x", Kind: Service}, "a worker", 0)
	if !errors.Is(err, domain.ErrInvalid) {
		t.Fatalf("a service principal was allowed to make a token: %v", err)
	}
}

// A token has to be named after what will hold it, or a list of them cannot be
// read by the person who made them.
func TestATokenHasAName(t *testing.T) {
	store := &Store{}
	for _, name := range []string{"", "   "} {
		_, _, err := store.CreateToken(context.Background(),
			Principal{ID: "prin_x", Kind: Person}, name, 0)
		if !errors.Is(err, domain.ErrInvalid) {
			t.Fatalf("a token named %q was allowed: %v", name, err)
		}
	}
}

// Something that is not a personal token is refused without a lookup, the same
// way an unknown one is.
func TestAStringWithoutThePrefixIsNotAToken(t *testing.T) {
	store := &Store{}
	_, err := store.AuthenticateToken(context.Background(), "not-a-token")
	if !errors.Is(err, ErrUnauthenticated) {
		t.Fatalf("got %v", err)
	}
}
