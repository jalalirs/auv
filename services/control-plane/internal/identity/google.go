package identity

import (
	"context"
	"crypto/rand"
	"errors"
	"fmt"
	"regexp"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
)

// GoogleAccount is what Google said about the person signing in, read from an
// ID token this process received from Google itself.
type GoogleAccount struct {
	// Subject is Google's stable id for the account. The email can change.
	Subject       string
	Email         string
	EmailVerified bool
	// HostedDomain is the Google Workspace the account belongs to, empty for a
	// personal account. A domain approval needs it.
	HostedDomain string
	Name         string
}

// ErrUnverifiedEmail refuses a Google account whose address Google has not
// verified: approvals are made by address, so an unverified one could claim
// anybody's.
var ErrUnverifiedEmail = fmt.Errorf("%w: Google has not verified that account's email address", domain.ErrInvalid)

// PersonForGoogle finds who a Google account is, linking it to the person
// already registered with the same address, and reports false when nobody is,
// so the caller can decide whether a new person may be made.
func (s *Store) PersonForGoogle(ctx context.Context, conn db.Conn, account GoogleAccount) (string, bool, error) {
	if !account.EmailVerified {
		return "", false, ErrUnverifiedEmail
	}
	var principalID string
	err := conn.QueryRow(ctx, `
		UPDATE identity.login SET email = $2, hosted_domain = nullif($3, ''), last_used_at = now()
		 WHERE provider = 'google' AND subject = $1
		RETURNING principal_id`, account.Subject, account.Email, account.HostedDomain).Scan(&principalID)
	if err == nil {
		return principalID, true, nil
	}
	if !errors.Is(db.Translate(err), db.ErrNotFound) {
		return "", false, fmt.Errorf("reading a login: %w", err)
	}

	err = conn.QueryRow(ctx, `
		SELECT id FROM identity.principal
		 WHERE kind = 'person' AND lower(email) = lower($1)`, account.Email).Scan(&principalID)
	if errors.Is(db.Translate(err), db.ErrNotFound) {
		return "", false, nil
	}
	if err != nil {
		return "", false, fmt.Errorf("reading a person by address: %w", err)
	}
	if err := s.linkGoogle(ctx, conn, principalID, account); err != nil {
		return "", false, err
	}
	return principalID, true, nil
}

// CreateGooglePerson makes a person from a Google account. They have no
// secret: Google is how they sign in.
func (s *Store) CreateGooglePerson(ctx context.Context, conn db.Conn, account GoogleAccount) (Principal, error) {
	if !account.EmailVerified {
		return Principal{}, ErrUnverifiedEmail
	}
	name := strings.TrimSpace(account.Name)
	if name == "" {
		name, _, _ = strings.Cut(account.Email, "@")
	}
	principal := Principal{ID: ids.New(ids.KindPrincipal), Kind: Person, DisplayName: name, Email: account.Email}
	err := conn.QueryRow(ctx, `
		INSERT INTO identity.principal (id, kind, display_name, email)
		VALUES ($1, 'person', $2, $3) RETURNING created_at`,
		principal.ID, principal.DisplayName, principal.Email).Scan(&principal.CreatedAt)
	if err != nil {
		return Principal{}, fmt.Errorf("creating a person: %w", err)
	}
	if err := s.linkGoogle(ctx, conn, principal.ID, account); err != nil {
		return Principal{}, err
	}
	return principal, nil
}

func (s *Store) linkGoogle(ctx context.Context, conn db.Conn, principalID string, account GoogleAccount) error {
	_, err := conn.Exec(ctx, `
		INSERT INTO identity.login (provider, subject, principal_id, email, hosted_domain)
		VALUES ('google', $1, $2, $3, nullif($4, ''))`,
		account.Subject, principalID, account.Email, account.HostedDomain)
	if err != nil {
		return fmt.Errorf("linking a Google account: %w", err)
	}
	return nil
}

// CreatePersonalOrganisation founds the organisation a person works in on
// their own. Its slug is drawn from their address plus a few random letters,
// because two people called ali will both sign in.
func (s *Store) CreatePersonalOrganisation(ctx context.Context, conn db.Conn, person Principal) (Organisation, error) {
	slug, err := personalSlug(person.Email)
	if err != nil {
		return Organisation{}, err
	}
	org, err := s.CreateOrganisation(ctx, conn, slug, person.DisplayName)
	if err != nil {
		return Organisation{}, err
	}
	if _, err := conn.Exec(ctx,
		`UPDATE identity.organisation SET personal_of = $2 WHERE id = $1`, org.ID, person.ID); err != nil {
		return Organisation{}, fmt.Errorf("marking an organisation personal: %w", err)
	}
	org.PersonalOf = person.ID
	if err := s.AddMember(ctx, conn, org.ID, person.ID); err != nil {
		return Organisation{}, err
	}
	return org, nil
}

var notSlug = regexp.MustCompile(`[^a-z0-9]+`)

func personalSlug(email string) (string, error) {
	local, _, _ := strings.Cut(strings.ToLower(email), "@")
	base := strings.Trim(notSlug.ReplaceAllString(local, "-"), "-")
	if base == "" || base[0] < 'a' || base[0] > 'z' {
		base = "p-" + base
	}
	if len(base) > 40 {
		base = strings.TrimRight(base[:40], "-")
	}
	const letters = "abcdefghjkmnpqrstuvwxyz23456789"
	raw := make([]byte, 5)
	if _, err := rand.Read(raw); err != nil {
		return "", fmt.Errorf("drawing a slug: %w", err)
	}
	for i := range raw {
		raw[i] = letters[int(raw[i])%len(letters)]
	}
	return base + "-" + string(raw), nil
}

// PersonalOrganisationsSince counts the personal organisations founded since
// a moment, which is what bounds how fast free accounts can be made.
func (s *Store) PersonalOrganisationsSince(ctx context.Context, conn db.Conn, since time.Time) (int, error) {
	var count int
	err := conn.QueryRow(ctx, `
		SELECT count(*) FROM identity.organisation
		 WHERE personal_of IS NOT NULL AND created_at >= $1`, since).Scan(&count)
	if err != nil {
		return 0, fmt.Errorf("counting new personal organisations: %w", err)
	}
	return count, nil
}

// approvalMatches is when an approval of the institution m.org_id covers the
// person p: their address is on its list, or their Google account belongs to
// a Workspace domain it was given and their address is in that domain.
const approvalMatches = `(
	EXISTS (SELECT 1 FROM identity.approved_email ae
	         WHERE ae.org_id = o.id AND lower(ae.email) = lower(p.email))
	OR EXISTS (SELECT 1 FROM identity.approved_domain ad
	             JOIN identity.login l ON l.principal_id = p.id AND l.hosted_domain = ad.domain
	            WHERE ad.org_id = o.id AND lower(p.email) LIKE '%@' || ad.domain))`

// SyncApprovals makes memberships agree with approvals: a person an approval
// covers is a member, and a member an approval made but no approval covers any
// more is not. Either argument may be empty, meaning every organisation or
// every person. A membership an administrator made by hand is left alone.
func (s *Store) SyncApprovals(ctx context.Context, conn db.Conn, orgID, principalID string) error {
	_, err := conn.Exec(ctx, `
		DELETE FROM identity.membership m
		 USING identity.organisation o, identity.principal p
		 WHERE m.by_approval AND o.id = m.org_id AND p.id = m.principal_id
		   AND ($1 = '' OR m.org_id = $1) AND ($2 = '' OR m.principal_id = $2)
		   AND NOT `+approvalMatches, orgID, principalID)
	if err != nil {
		return fmt.Errorf("withdrawing memberships: %w", err)
	}
	_, err = conn.Exec(ctx, `
		INSERT INTO identity.membership (org_id, principal_id, by_approval)
		SELECT o.id, p.id, true
		  FROM identity.organisation o, identity.principal p
		 WHERE o.personal_of IS NULL AND p.kind = 'person' AND p.disabled_at IS NULL
		   AND ($1 = '' OR o.id = $1) AND ($2 = '' OR p.id = $2)
		   AND `+approvalMatches+`
		ON CONFLICT (org_id, principal_id) DO NOTHING`, orgID, principalID)
	if err != nil {
		return fmt.Errorf("adding approved members: %w", err)
	}
	return nil
}

// ErrPersonalOrganisation refuses approvals on a personal organisation, which
// has one person by definition.
var ErrPersonalOrganisation = fmt.Errorf("%w: a personal organisation has only its owner", domain.ErrInvalid)

func (s *Store) refusePersonal(ctx context.Context, conn db.Conn, orgID string) error {
	var personal *string
	if err := conn.QueryRow(ctx,
		`SELECT personal_of FROM identity.organisation WHERE id = $1`, orgID).Scan(&personal); err != nil {
		return db.Translate(err)
	}
	if personal != nil {
		return ErrPersonalOrganisation
	}
	return nil
}

// Approval is one address or domain an institution approves.
type Approval struct {
	OrgID     string    `json:"orgId"`
	Email     string    `json:"email,omitempty"`
	Domain    string    `json:"domain,omitempty"`
	AddedBy   string    `json:"addedBy"`
	CreatedAt time.Time `json:"createdAt"`
}

// ApproveEmail adds an address to an institution's list.
func (s *Store) ApproveEmail(ctx context.Context, conn db.Conn, orgID, email, by string) (Approval, error) {
	email = strings.TrimSpace(email)
	at := strings.Index(email, "@")
	if at <= 0 || at == len(email)-1 || strings.ContainsAny(email, " \t") || strings.Count(email, "@") != 1 {
		return Approval{}, fmt.Errorf("%w: %q is not an email address", domain.ErrInvalid, email)
	}
	if err := s.refusePersonal(ctx, conn, orgID); err != nil {
		return Approval{}, err
	}
	approval := Approval{OrgID: orgID, Email: email, AddedBy: by}
	err := conn.QueryRow(ctx, `
		INSERT INTO identity.approved_email (org_id, email, added_by) VALUES ($1, $2, $3)
		RETURNING created_at`, orgID, email, by).Scan(&approval.CreatedAt)
	if err != nil {
		if db.IsUniqueViolation(err) {
			return Approval{}, fmt.Errorf("%w: %s is already approved", domain.ErrInvalid, email)
		}
		return Approval{}, fmt.Errorf("approving an address: %w", err)
	}
	return approval, s.SyncApprovals(ctx, conn, orgID, "")
}

// WithdrawEmail takes an address off an institution's list, and with it the
// membership the approval made.
func (s *Store) WithdrawEmail(ctx context.Context, conn db.Conn, orgID, email string) error {
	tag, err := conn.Exec(ctx, `
		DELETE FROM identity.approved_email WHERE org_id = $1 AND lower(email) = lower($2)`, orgID, email)
	if err != nil {
		return fmt.Errorf("withdrawing an address: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return db.ErrNotFound
	}
	return s.SyncApprovals(ctx, conn, orgID, "")
}

// ApproveDomain gives an institution a whole Workspace domain.
func (s *Store) ApproveDomain(ctx context.Context, conn db.Conn, orgID, name, by string) (Approval, error) {
	name = strings.ToLower(strings.TrimSpace(name))
	if err := s.refusePersonal(ctx, conn, orgID); err != nil {
		return Approval{}, err
	}
	approval := Approval{OrgID: orgID, Domain: name, AddedBy: by}
	err := conn.QueryRow(ctx, `
		INSERT INTO identity.approved_domain (domain, org_id, added_by) VALUES ($1, $2, $3)
		RETURNING created_at`, name, orgID, by).Scan(&approval.CreatedAt)
	if err != nil {
		if db.IsUniqueViolation(err) {
			return Approval{}, fmt.Errorf("%w: %s already belongs to an institution", domain.ErrInvalid, name)
		}
		if db.IsCheckViolation(err) {
			return Approval{}, fmt.Errorf("%w: %q is not a domain name", domain.ErrInvalid, name)
		}
		return Approval{}, fmt.Errorf("approving a domain: %w", err)
	}
	return approval, s.SyncApprovals(ctx, conn, orgID, "")
}

// WithdrawDomain takes a domain from an institution.
func (s *Store) WithdrawDomain(ctx context.Context, conn db.Conn, orgID, name string) error {
	tag, err := conn.Exec(ctx, `
		DELETE FROM identity.approved_domain WHERE org_id = $1 AND domain = lower($2)`, orgID, name)
	if err != nil {
		return fmt.Errorf("withdrawing a domain: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return db.ErrNotFound
	}
	return s.SyncApprovals(ctx, conn, orgID, "")
}

// Approvals lists what an institution approves: addresses, then domains.
func (s *Store) Approvals(ctx context.Context, orgID string) ([]Approval, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT org_id, email, '', added_by, created_at FROM identity.approved_email WHERE org_id = $1
		UNION ALL
		SELECT org_id, '', domain, added_by, created_at FROM identity.approved_domain WHERE org_id = $1
		ORDER BY 3, 2`, orgID)
	if err != nil {
		return nil, fmt.Errorf("listing approvals: %w", err)
	}
	defer rows.Close()
	approvals := []Approval{}
	for rows.Next() {
		var a Approval
		if err := rows.Scan(&a.OrgID, &a.Email, &a.Domain, &a.AddedBy, &a.CreatedAt); err != nil {
			return nil, err
		}
		approvals = append(approvals, a)
	}
	return approvals, rows.Err()
}

// IssueSession signs a principal in, for a way of signing in that has already
// established who they are.
func (s *Store) IssueSession(ctx context.Context, principalID string) (Session, string, Principal, error) {
	principal, err := s.Principal(ctx, principalID)
	if err != nil {
		return Session{}, "", Principal{}, err
	}
	if principal.Disabled {
		return Session{}, "", Principal{}, ErrDisabled
	}
	session, token, err := s.issueSession(ctx, principalID)
	if err != nil {
		return Session{}, "", Principal{}, err
	}
	return session, token, principal, nil
}

// handoffLifetime is how long a desktop app has to trade the code it was
// handed back for a session.
const handoffLifetime = time.Minute

// CreateHandoff makes the single-use code a desktop app trades for a session
// after signing in through the system browser. Only its digest is stored.
func (s *Store) CreateHandoff(ctx context.Context, principalID string) (string, error) {
	code, digest, err := newToken()
	if err != nil {
		return "", err
	}
	if _, err := s.pool.Exec(ctx, `
		INSERT INTO identity.handoff (code_hash, principal_id, expires_at) VALUES ($1, $2, $3)`,
		digest, principalID, time.Now().Add(handoffLifetime)); err != nil {
		return "", fmt.Errorf("making a hand-off code: %w", err)
	}
	return code, nil
}

// RedeemHandoff trades a hand-off code for a session, once.
func (s *Store) RedeemHandoff(ctx context.Context, code string) (Session, string, Principal, error) {
	var principalID string
	err := s.pool.QueryRow(ctx, `
		UPDATE identity.handoff SET used_at = now()
		 WHERE code_hash = $1 AND used_at IS NULL AND expires_at > now()
		RETURNING principal_id`, tokenDigest(code)).Scan(&principalID)
	if errors.Is(db.Translate(err), db.ErrNotFound) {
		return Session{}, "", Principal{}, ErrUnauthenticated
	}
	if err != nil {
		return Session{}, "", Principal{}, fmt.Errorf("redeeming a hand-off code: %w", err)
	}
	return s.IssueSession(ctx, principalID)
}
