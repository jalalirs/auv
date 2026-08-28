package identity

import (
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/base64"
	"fmt"
	"strings"

	"golang.org/x/crypto/argon2"
)

// Argon2id parameters. These are the interactive-use figures from the Argon2
// RFC: costly enough that a stolen verifier is impractical to reverse, cheap
// enough that signing in stays responsive.
const (
	hashTime    = 2
	hashMemory  = 64 * 1024 // kibibytes
	hashThreads = 4
	hashLength  = 32
	saltLength  = 16
)

// hashSecret returns verifier material for a secret. The secret itself is
// never written down anywhere.
func hashSecret(secret string) (string, error) {
	salt := make([]byte, saltLength)
	if _, err := rand.Read(salt); err != nil {
		return "", fmt.Errorf("drawing a salt: %w", err)
	}
	digest := argon2.IDKey([]byte(secret), salt, hashTime, hashMemory, hashThreads, hashLength)
	return fmt.Sprintf("$argon2id$v=%d$m=%d,t=%d,p=%d$%s$%s",
		argon2.Version, hashMemory, hashTime, hashThreads,
		base64.RawStdEncoding.EncodeToString(salt),
		base64.RawStdEncoding.EncodeToString(digest)), nil
}

// verifySecret reports whether a secret produces the given verifier. It
// compares in constant time so that a wrong secret takes as long as a right
// one.
func verifySecret(verifier, secret string) (bool, error) {
	parts := strings.Split(verifier, "$")
	if len(parts) != 6 || parts[1] != "argon2id" {
		return false, fmt.Errorf("the stored verifier is not argon2id")
	}

	var version int
	if _, err := fmt.Sscanf(parts[2], "v=%d", &version); err != nil {
		return false, fmt.Errorf("reading the verifier version: %w", err)
	}
	if version != argon2.Version {
		return false, fmt.Errorf("the stored verifier uses argon2 version %d, this build uses %d",
			version, argon2.Version)
	}

	var memory, time uint32
	var threads uint8
	if _, err := fmt.Sscanf(parts[3], "m=%d,t=%d,p=%d", &memory, &time, &threads); err != nil {
		return false, fmt.Errorf("reading the verifier parameters: %w", err)
	}

	salt, err := base64.RawStdEncoding.DecodeString(parts[4])
	if err != nil {
		return false, fmt.Errorf("reading the verifier salt: %w", err)
	}
	expected, err := base64.RawStdEncoding.DecodeString(parts[5])
	if err != nil {
		return false, fmt.Errorf("reading the verifier digest: %w", err)
	}

	actual := argon2.IDKey([]byte(secret), salt, time, memory, threads, uint32(len(expected)))
	return subtle.ConstantTimeCompare(actual, expected) == 1, nil
}

// tokenLength is the byte length of a session token. 256 bits of randomness is
// beyond guessing, and the token is never stored in that form.
const tokenLength = 32

// newToken returns a bearer token and the digest under which it is stored, so
// that a disclosure of the database does not grant access.
func newToken() (token string, digest []byte, err error) {
	raw := make([]byte, tokenLength)
	if _, err := rand.Read(raw); err != nil {
		return "", nil, fmt.Errorf("drawing a session token: %w", err)
	}
	token = base64.RawURLEncoding.EncodeToString(raw)
	return token, tokenDigest(token), nil
}

func tokenDigest(token string) []byte {
	sum := sha256.Sum256([]byte(token))
	return sum[:]
}
