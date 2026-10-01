package identity

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
)

// TokenPrefix marks a personal token, so that the middleware knows which
// lookup to make and a secret scanner can recognise one that leaked into a
// commit. Sessions are bare random strings and never start with it.
const TokenPrefix = "cc_"

// APIToken is a token a person made for a program to act as them. The token
// itself is shown once, when it is made, and never stored.
type APIToken struct {
	ID          string     `json:"id"`
	PrincipalID string     `json:"principalId"`
	Name        string     `json:"name"`
	Prefix      string     `json:"prefix"`
	CreatedAt   time.Time  `json:"createdAt"`
	ExpiresAt   *time.Time `json:"expiresAt,omitempty"`
	LastUsedAt  *time.Time `json:"lastUsedAt,omitempty"`
	RevokedAt   *time.Time `json:"revokedAt,omitempty"`
}

// CreateToken makes a token for a person, named after what will hold it.
//
// Only a person: a service principal already is a program, and a token that
// let one mint credentials for itself would be a way round whoever issued it.
func (s *Store) CreateToken(ctx context.Context, principal Principal, name string, lifetime time.Duration) (APIToken, string, error) {
	if principal.Kind != Person {
		return APIToken{}, "", fmt.Errorf("%w: only a person makes tokens", domain.ErrInvalid)
	}
	name = strings.TrimSpace(name)
	if name == "" {
		return APIToken{}, "", fmt.Errorf("%w: name the token after what will hold it", domain.ErrInvalid)
	}
	random, _, err := newToken()
	if err != nil {
		return APIToken{}, "", err
	}
	token := TokenPrefix + random
	made := APIToken{
		ID:          ids.New(ids.KindAPIToken),
		PrincipalID: principal.ID,
		Name:        name,
		Prefix:      token[:len(TokenPrefix)+6],
	}
	if lifetime > 0 {
		at := time.Now().Add(lifetime)
		made.ExpiresAt = &at
	}
	err = s.pool.QueryRow(ctx, `
		INSERT INTO identity.api_token (id, principal_id, name, prefix, token_hash, expires_at)
		VALUES ($1, $2, $3, $4, $5, $6)
		RETURNING created_at`,
		made.ID, made.PrincipalID, made.Name, made.Prefix, tokenDigest(token), made.ExpiresAt,
	).Scan(&made.CreatedAt)
	if err != nil {
		return APIToken{}, "", fmt.Errorf("making a token: %w", err)
	}
	return made, token, nil
}

// TokensOf lists a person's tokens, newest first, revoked ones included so a
// person can see what they turned off and when.
func (s *Store) TokensOf(ctx context.Context, principalID string) ([]APIToken, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, principal_id, name, prefix, created_at, expires_at, last_used_at, revoked_at
		FROM identity.api_token WHERE principal_id = $1
		ORDER BY created_at DESC`, principalID)
	if err != nil {
		return nil, fmt.Errorf("listing tokens: %w", err)
	}
	defer rows.Close()
	out := []APIToken{}
	for rows.Next() {
		var t APIToken
		if err := rows.Scan(&t.ID, &t.PrincipalID, &t.Name, &t.Prefix,
			&t.CreatedAt, &t.ExpiresAt, &t.LastUsedAt, &t.RevokedAt); err != nil {
			return nil, err
		}
		out = append(out, t)
	}
	return out, rows.Err()
}

// RevokeToken turns one of a person's own tokens off, immediately. Revoking
// somebody else's is indistinguishable from revoking one that does not exist.
func (s *Store) RevokeToken(ctx context.Context, principalID, tokenID string) error {
	tag, err := s.pool.Exec(ctx, `
		UPDATE identity.api_token SET revoked_at = now()
		WHERE id = $1 AND principal_id = $2 AND revoked_at IS NULL`, tokenID, principalID)
	if err != nil {
		return fmt.Errorf("revoking a token: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return db.ErrNotFound
	}
	return nil
}

// AuthenticateToken resolves a personal token to the person who made it.
//
// The person, with their own grants as they are now — not a copy of them taken
// when the token was made. A revoked, expired or unknown token are all the same
// refusal.
func (s *Store) AuthenticateToken(ctx context.Context, token string) (Principal, error) {
	if !strings.HasPrefix(token, TokenPrefix) {
		return Principal{}, ErrUnauthenticated
	}
	var tokenID, principalID string
	err := s.pool.QueryRow(ctx, `
		SELECT id, principal_id FROM identity.api_token
		WHERE token_hash = $1 AND revoked_at IS NULL
		  AND (expires_at IS NULL OR expires_at > now())`,
		tokenDigest(token)).Scan(&tokenID, &principalID)
	if errors.Is(db.Translate(err), db.ErrNotFound) {
		return Principal{}, ErrUnauthenticated
	}
	if err != nil {
		return Principal{}, fmt.Errorf("reading a token: %w", err)
	}
	// When it was last used, so the person can tell a token in use from one
	// left lying about. Best effort: a failure here is not a reason to refuse.
	_, _ = s.pool.Exec(ctx,
		`UPDATE identity.api_token SET last_used_at = now() WHERE id = $1`, tokenID)

	principal, err := s.Principal(ctx, principalID)
	if err != nil {
		return Principal{}, err
	}
	if principal.Disabled {
		return Principal{}, ErrDisabled
	}
	return principal, nil
}
