package identity

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
)

// SignIn authenticates a person and issues a session.
//
// An unknown email and a wrong secret produce the same error, so the response
// cannot be used to discover who is registered.
func (s *Store) SignIn(ctx context.Context, email, secret string) (Session, string, Principal, error) {
	var (
		principalID string
		verifier    string
		disabledAt  *time.Time
	)
	err := s.pool.QueryRow(ctx, `
		SELECT p.id, c.verifier, p.disabled_at
		FROM identity.principal p
		JOIN identity.credential c ON c.principal_id = p.id AND c.revoked_at IS NULL
		WHERE p.kind = 'person' AND lower(p.email) = lower($1)
		ORDER BY c.created_at DESC
		LIMIT 1`, email).Scan(&principalID, &verifier, &disabledAt)
	if errors.Is(db.Translate(err), db.ErrNotFound) {
		// Spend comparable effort on an unknown address so that timing does not
		// reveal whether it is registered.
		_, _ = verifySecret(decoyVerifier, secret)
		return Session{}, "", Principal{}, ErrUnauthenticated
	}
	if err != nil {
		return Session{}, "", Principal{}, fmt.Errorf("reading a credential: %w", err)
	}

	matches, err := verifySecret(verifier, secret)
	if err != nil {
		return Session{}, "", Principal{}, fmt.Errorf("checking a credential: %w", err)
	}
	if !matches {
		return Session{}, "", Principal{}, ErrUnauthenticated
	}
	if disabledAt != nil {
		return Session{}, "", Principal{}, ErrDisabled
	}

	session, token, err := s.issueSession(ctx, principalID)
	if err != nil {
		return Session{}, "", Principal{}, err
	}
	principal, err := s.Principal(ctx, principalID)
	if err != nil {
		return Session{}, "", Principal{}, err
	}
	return session, token, principal, nil
}

// decoyVerifier is a real argon2id verifier for a secret nobody holds. It
// exists so that authenticating an unknown address costs the same as
// authenticating a known one.
const decoyVerifier = "$argon2id$v=19$m=65536,t=2,p=4$AAAAAAAAAAAAAAAAAAAAAA$" +
	"7ZVQK7hjR1DjqZfBmnEQZGD0eE6iLRvOhwEuVfPO0hI"

func (s *Store) issueSession(ctx context.Context, principalID string) (Session, string, error) {
	token, digest, err := newToken()
	if err != nil {
		return Session{}, "", err
	}
	session := Session{
		ID:          ids.New(ids.KindSession),
		PrincipalID: principalID,
		ExpiresAt:   time.Now().Add(s.sessionLifetime),
	}
	err = s.pool.QueryRow(ctx, `
		INSERT INTO identity.session (id, principal_id, token_hash, expires_at)
		VALUES ($1, $2, $3, $4)
		RETURNING issued_at`,
		session.ID, session.PrincipalID, digest, session.ExpiresAt).Scan(&session.IssuedAt)
	if err != nil {
		return Session{}, "", fmt.Errorf("issuing a session: %w", err)
	}
	return session, token, nil
}

// AuthenticateSession resolves a session token to the principal holding it.
// An expired or revoked session is indistinguishable from an unknown one.
func (s *Store) AuthenticateSession(ctx context.Context, token string) (Principal, error) {
	var principalID string
	err := s.pool.QueryRow(ctx, `
		SELECT principal_id FROM identity.session
		WHERE token_hash = $1 AND revoked_at IS NULL AND expires_at > now()`,
		tokenDigest(token)).Scan(&principalID)
	if errors.Is(db.Translate(err), db.ErrNotFound) {
		return Principal{}, ErrUnauthenticated
	}
	if err != nil {
		return Principal{}, fmt.Errorf("reading a session: %w", err)
	}

	principal, err := s.Principal(ctx, principalID)
	if err != nil {
		return Principal{}, err
	}
	if principal.Disabled {
		return Principal{}, ErrDisabled
	}
	return principal, nil
}

// AuthenticateService resolves a service credential of the form
// "<principal id>:<secret>" to the principal holding it. Workers, edge
// stations, and vehicles authenticate this way; they hold no sessions.
func (s *Store) AuthenticateService(ctx context.Context, credential string) (Principal, error) {
	principalID, secret, found := strings.Cut(credential, ":")
	if !found || principalID == "" || secret == "" {
		return Principal{}, ErrUnauthenticated
	}
	if _, err := ids.Parse(ids.KindPrincipal, principalID); err != nil {
		return Principal{}, ErrUnauthenticated
	}

	var verifier string
	err := s.pool.QueryRow(ctx, `
		SELECT c.verifier
		FROM identity.credential c
		JOIN identity.principal p ON p.id = c.principal_id
		WHERE c.principal_id = $1 AND c.revoked_at IS NULL AND p.kind = 'service'
		ORDER BY c.created_at DESC
		LIMIT 1`, principalID).Scan(&verifier)
	if errors.Is(db.Translate(err), db.ErrNotFound) {
		_, _ = verifySecret(decoyVerifier, secret)
		return Principal{}, ErrUnauthenticated
	}
	if err != nil {
		return Principal{}, fmt.Errorf("reading a service credential: %w", err)
	}

	matches, err := verifySecret(verifier, secret)
	if err != nil {
		return Principal{}, fmt.Errorf("checking a service credential: %w", err)
	}
	if !matches {
		return Principal{}, ErrUnauthenticated
	}

	principal, err := s.Principal(ctx, principalID)
	if err != nil {
		return Principal{}, err
	}
	if principal.Disabled {
		return Principal{}, ErrDisabled
	}
	return principal, nil
}

// RevokeSession ends one sign-in immediately.
func (s *Store) RevokeSession(ctx context.Context, token string) error {
	tag, err := s.pool.Exec(ctx,
		`UPDATE identity.session SET revoked_at = now()
		 WHERE token_hash = $1 AND revoked_at IS NULL`, tokenDigest(token))
	if err != nil {
		return fmt.Errorf("revoking a session: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return db.ErrNotFound
	}
	return nil
}

// PurgeExpiredSessions removes sessions that can no longer authenticate
// anyone. It is called by the background reaper, not by a request.
func (s *Store) PurgeExpiredSessions(ctx context.Context, olderThan time.Duration) (int64, error) {
	tag, err := s.pool.Exec(ctx,
		`DELETE FROM identity.session WHERE expires_at < now() - $1::interval`,
		olderThan.String())
	if err != nil {
		return 0, fmt.Errorf("purging expired sessions: %w", err)
	}
	return tag.RowsAffected(), nil
}
