// Package identity establishes who is acting.
//
// It distinguishes people, organisations, and service principals — workers,
// edge stations, and vehicles — so that every action in the record is
// attributable. It decides nothing about what an actor may do; that is the
// decision point's work alone.
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

// ErrUnauthenticated reports credentials that do not identify anyone. It never
// distinguishes an unknown actor from a wrong secret, so the error cannot be
// used to discover who exists.
var ErrUnauthenticated = errors.New("those credentials do not identify anyone")

// ErrDisabled reports a principal that exists but may no longer act.
var ErrDisabled = errors.New("that principal is disabled")

// Kind distinguishes an actor a human drives from one a program drives.
type Kind string

const (
	// Person is an actor a human signs in as.
	Person Kind = "person"
	// Service is an actor a program authenticates as: a worker, an edge
	// station, or a vehicle.
	Service Kind = "service"
)

// Organisation is an institution. It holds members, quota, and its own work.
// It never holds a city; it is granted access to one.
type Organisation struct {
	ID        string    `json:"id"`
	Slug      string    `json:"slug"`
	Name      string    `json:"name"`
	CreatedAt time.Time `json:"createdAt"`
}

// Principal is anything that can act.
type Principal struct {
	ID          string    `json:"id"`
	Kind        Kind      `json:"kind"`
	DisplayName string    `json:"displayName"`
	Email       string    `json:"email,omitempty"`
	OrgID       string    `json:"orgId,omitempty"`
	Disabled    bool      `json:"disabled"`
	CreatedAt   time.Time `json:"createdAt"`
}

// Session is a short-lived, revocable bearer of a principal's identity.
type Session struct {
	ID          string    `json:"id"`
	PrincipalID string    `json:"principalId"`
	IssuedAt    time.Time `json:"issuedAt"`
	ExpiresAt   time.Time `json:"expiresAt"`
}

// Store reads and writes the identity record.
type Store struct {
	pool *db.Pool
	// sessionLifetime bounds how long one sign-in remains usable.
	sessionLifetime time.Duration
}

// NewStore builds the identity store.
func NewStore(pool *db.Pool, sessionLifetime time.Duration) *Store {
	return &Store{pool: pool, sessionLifetime: sessionLifetime}
}

// CreateOrganisation founds an institution.
//
// It is created with one binding: the organisation itself holds contributor at
// its own scope, so that every member can do its work without a separate grant
// per person. Membership on its own grants nothing.
func (s *Store) CreateOrganisation(ctx context.Context, conn db.Conn, slug, name string) (Organisation, error) {
	if err := domain.ValidateSlug(slug); err != nil {
		return Organisation{}, err
	}
	if strings.TrimSpace(name) == "" {
		return Organisation{}, fmt.Errorf("%w: an organisation has a name", domain.ErrInvalid)
	}

	org := Organisation{ID: ids.New(ids.KindOrganisation), Slug: slug, Name: name}
	err := conn.QueryRow(ctx,
		`INSERT INTO identity.organisation (id, slug, name) VALUES ($1, $2, $3) RETURNING created_at`,
		org.ID, org.Slug, org.Name).Scan(&org.CreatedAt)
	if err != nil {
		if db.IsUniqueViolation(err) {
			return Organisation{}, fmt.Errorf("%w: an organisation named %q already exists",
				domain.ErrInvalid, slug)
		}
		return Organisation{}, fmt.Errorf("creating an organisation: %w", err)
	}
	return org, nil
}

// Organisation reads one institution.
func (s *Store) Organisation(ctx context.Context, id string) (Organisation, error) {
	var org Organisation
	err := s.pool.QueryRow(ctx,
		`SELECT id, slug, name, created_at FROM identity.organisation WHERE id = $1`, id).
		Scan(&org.ID, &org.Slug, &org.Name, &org.CreatedAt)
	return org, db.Translate(err)
}

// OrganisationBySlug reads one institution by its stable name.
func (s *Store) OrganisationBySlug(ctx context.Context, slug string) (Organisation, error) {
	var org Organisation
	err := s.pool.QueryRow(ctx,
		`SELECT id, slug, name, created_at FROM identity.organisation WHERE slug = $1`, slug).
		Scan(&org.ID, &org.Slug, &org.Name, &org.CreatedAt)
	return org, db.Translate(err)
}

// PersonSpec describes a person to create.
type PersonSpec struct {
	DisplayName string
	Email       string
	Secret      string
}

// Validate reports whether the person can be created.
func (p PersonSpec) Validate() error {
	if strings.TrimSpace(p.DisplayName) == "" {
		return fmt.Errorf("%w: a person has a display name", domain.ErrInvalid)
	}
	at := strings.Index(p.Email, "@")
	if at <= 0 || at == len(p.Email)-1 || strings.Contains(p.Email, " ") {
		return fmt.Errorf("%w: %q is not an email address", domain.ErrInvalid, p.Email)
	}
	if len(p.Secret) < 12 {
		return fmt.Errorf("%w: a sign-in secret is at least 12 characters", domain.ErrInvalid)
	}
	return nil
}

// CreatePerson adds someone who can sign in.
func (s *Store) CreatePerson(ctx context.Context, conn db.Conn, spec PersonSpec) (Principal, error) {
	if err := spec.Validate(); err != nil {
		return Principal{}, err
	}
	verifier, err := hashSecret(spec.Secret)
	if err != nil {
		return Principal{}, err
	}

	principal := Principal{
		ID:          ids.New(ids.KindPrincipal),
		Kind:        Person,
		DisplayName: spec.DisplayName,
		Email:       spec.Email,
	}
	err = conn.QueryRow(ctx, `
		INSERT INTO identity.principal (id, kind, display_name, email)
		VALUES ($1, 'person', $2, $3)
		RETURNING created_at`,
		principal.ID, principal.DisplayName, principal.Email).Scan(&principal.CreatedAt)
	if err != nil {
		if db.IsUniqueViolation(err) {
			return Principal{}, fmt.Errorf("%w: someone is already registered with that email address",
				domain.ErrInvalid)
		}
		return Principal{}, fmt.Errorf("creating a person: %w", err)
	}

	if _, err := conn.Exec(ctx,
		`INSERT INTO identity.credential (id, principal_id, verifier) VALUES ($1, $2, $3)`,
		ids.New(ids.KindCredential), principal.ID, verifier); err != nil {
		return Principal{}, fmt.Errorf("storing a credential: %w", err)
	}
	return principal, nil
}

// CreateServicePrincipal adds a non-human actor and returns the secret it will
// authenticate with. The secret is shown once and never stored, so it cannot
// be recovered later — only replaced.
func (s *Store) CreateServicePrincipal(ctx context.Context, conn db.Conn, displayName, orgID string) (Principal, string, error) {
	if strings.TrimSpace(displayName) == "" {
		return Principal{}, "", fmt.Errorf("%w: a service principal has a display name", domain.ErrInvalid)
	}
	secret, _, err := newToken()
	if err != nil {
		return Principal{}, "", err
	}
	verifier, err := hashSecret(secret)
	if err != nil {
		return Principal{}, "", err
	}

	principal := Principal{
		ID:          ids.New(ids.KindPrincipal),
		Kind:        Service,
		DisplayName: displayName,
		OrgID:       orgID,
	}
	var org *string
	if orgID != "" {
		org = &orgID
	}
	err = conn.QueryRow(ctx, `
		INSERT INTO identity.principal (id, kind, display_name, org_id)
		VALUES ($1, 'service', $2, $3)
		RETURNING created_at`,
		principal.ID, principal.DisplayName, org).Scan(&principal.CreatedAt)
	if err != nil {
		return Principal{}, "", fmt.Errorf("creating a service principal: %w", err)
	}

	if _, err := conn.Exec(ctx,
		`INSERT INTO identity.credential (id, principal_id, verifier) VALUES ($1, $2, $3)`,
		ids.New(ids.KindCredential), principal.ID, verifier); err != nil {
		return Principal{}, "", fmt.Errorf("storing a credential: %w", err)
	}
	// The identifier is part of the credential so that a service presents both
	// halves and the lookup does not have to search every verifier.
	return principal, principal.ID + ":" + secret, nil
}

// Principal reads one actor.
func (s *Store) Principal(ctx context.Context, id string) (Principal, error) {
	var principal Principal
	var email, orgID *string
	var disabledAt *time.Time
	err := s.pool.QueryRow(ctx, `
		SELECT id, kind, display_name, email, org_id, disabled_at, created_at
		FROM identity.principal WHERE id = $1`, id).
		Scan(&principal.ID, &principal.Kind, &principal.DisplayName,
			&email, &orgID, &disabledAt, &principal.CreatedAt)
	if err != nil {
		return Principal{}, db.Translate(err)
	}
	if email != nil {
		principal.Email = *email
	}
	if orgID != nil {
		principal.OrgID = *orgID
	}
	principal.Disabled = disabledAt != nil
	return principal, nil
}

// AddMember records that a person belongs to an organisation. Membership makes
// the organisation's bindings apply to that person; it grants nothing itself.
func (s *Store) AddMember(ctx context.Context, conn db.Conn, orgID, principalID string) error {
	_, err := conn.Exec(ctx, `
		INSERT INTO identity.membership (org_id, principal_id) VALUES ($1, $2)
		ON CONFLICT (org_id, principal_id) DO NOTHING`, orgID, principalID)
	if err != nil {
		return fmt.Errorf("adding a member: %w", err)
	}
	return nil
}

// RemoveMember withdraws a person from an organisation.
func (s *Store) RemoveMember(ctx context.Context, conn db.Conn, orgID, principalID string) error {
	tag, err := conn.Exec(ctx,
		`DELETE FROM identity.membership WHERE org_id = $1 AND principal_id = $2`, orgID, principalID)
	if err != nil {
		return fmt.Errorf("removing a member: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return db.ErrNotFound
	}
	return nil
}

// OrganisationsOf lists the organisations whose bindings apply to a principal.
func (s *Store) OrganisationsOf(ctx context.Context, principalID string) ([]string, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT org_id FROM identity.membership WHERE principal_id = $1 ORDER BY org_id`, principalID)
	if err != nil {
		return nil, fmt.Errorf("reading memberships: %w", err)
	}
	defer rows.Close()

	orgs := []string{}
	for rows.Next() {
		var orgID string
		if err := rows.Scan(&orgID); err != nil {
			return nil, err
		}
		orgs = append(orgs, orgID)
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	// A service principal belongs to the organisation that owns it even without
	// a membership row, because it is that organisation's instrument.
	var owning *string
	if err := s.pool.QueryRow(ctx,
		`SELECT org_id FROM identity.principal WHERE id = $1`, principalID).Scan(&owning); err != nil {
		return nil, db.Translate(err)
	}
	if owning != nil {
		for _, existing := range orgs {
			if existing == *owning {
				return orgs, nil
			}
		}
		orgs = append(orgs, *owning)
	}
	return orgs, nil
}

// Members lists the people in an organisation.
func (s *Store) Members(ctx context.Context, orgID string) ([]Principal, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT p.id, p.kind, p.display_name, p.email, p.org_id, p.disabled_at, p.created_at
		FROM identity.membership m
		JOIN identity.principal p ON p.id = m.principal_id
		WHERE m.org_id = $1
		ORDER BY p.display_name`, orgID)
	if err != nil {
		return nil, fmt.Errorf("reading members: %w", err)
	}
	defer rows.Close()

	members := []Principal{}
	for rows.Next() {
		var principal Principal
		var email, org *string
		var disabledAt *time.Time
		if err := rows.Scan(&principal.ID, &principal.Kind, &principal.DisplayName,
			&email, &org, &disabledAt, &principal.CreatedAt); err != nil {
			return nil, err
		}
		if email != nil {
			principal.Email = *email
		}
		if org != nil {
			principal.OrgID = *org
		}
		principal.Disabled = disabledAt != nil
		members = append(members, principal)
	}
	return members, rows.Err()
}

// Organisations lists every institution on this installation.
//
// There is no scoping here: only platform authority reaches this, and an
// administrator who may found an institution may see the ones that exist.
func (s *Store) Organisations(ctx context.Context) ([]Organisation, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT id, slug, name, created_at FROM identity.organisation ORDER BY name`)
	if err != nil {
		return nil, fmt.Errorf("listing institutions: %w", err)
	}
	defer rows.Close()

	organisations := []Organisation{}
	for rows.Next() {
		var org Organisation
		if err := rows.Scan(&org.ID, &org.Slug, &org.Name, &org.CreatedAt); err != nil {
			return nil, err
		}
		organisations = append(organisations, org)
	}
	return organisations, rows.Err()
}

// People lists everyone who can act on this installation.
//
// Disabled principals are listed too, and say so. They are kept because the
// audit record names who did each thing, so a name that once acted must remain
// a name; hiding them here would make the record harder to read rather than
// tidier.
func (s *Store) People(ctx context.Context) ([]Principal, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, kind, display_name, coalesce(email, ''), coalesce(org_id, ''),
		       disabled_at IS NOT NULL, created_at
		FROM identity.principal
		ORDER BY disabled_at IS NOT NULL, display_name`)
	if err != nil {
		return nil, fmt.Errorf("listing people: %w", err)
	}
	defer rows.Close()

	people := []Principal{}
	for rows.Next() {
		var person Principal
		if err := rows.Scan(&person.ID, &person.Kind, &person.DisplayName, &person.Email,
			&person.OrgID, &person.Disabled, &person.CreatedAt); err != nil {
			return nil, err
		}
		people = append(people, person)
	}
	return people, rows.Err()
}
