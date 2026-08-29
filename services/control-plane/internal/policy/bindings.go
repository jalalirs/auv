package policy

import (
	"context"
	"fmt"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
)

// Binding is a role held by a subject at a scope. Sharing a city with an
// institution is a binding whose subject is that organisation; nothing is
// copied and nothing changes about the city itself.
type Binding struct {
	ID          string      `json:"id"`
	SubjectKind SubjectKind `json:"subjectKind"`
	SubjectID   string      `json:"subjectId"`
	ScopeKind   ScopeKind   `json:"scopeKind"`
	ScopeID     string      `json:"scopeId,omitempty"`
	Role        Role        `json:"role"`
	CreatedAt   time.Time   `json:"createdAt"`
	CreatedBy   string      `json:"createdBy"`
	RevokedAt   *time.Time  `json:"revokedAt,omitempty"`
}

// GrantSpec describes a binding to create.
type GrantSpec struct {
	SubjectKind SubjectKind
	SubjectID   string
	ScopeKind   ScopeKind
	ScopeID     string
	Role        Role
	CreatedBy   string
}

// Validate reports whether the grant is expressible.
func (g GrantSpec) Validate() error {
	switch g.SubjectKind {
	case SubjectPrincipal, SubjectOrg:
	default:
		return fmt.Errorf("%w: a binding's subject is a principal or an organisation, not %q",
			domain.ErrInvalid, g.SubjectKind)
	}
	if g.SubjectID == "" {
		return fmt.Errorf("%w: a binding names its subject", domain.ErrInvalid)
	}
	switch g.ScopeKind {
	case ScopePlatform, ScopeWork:
		if g.ScopeID != "" {
			return fmt.Errorf("%w: the %s scope has no identifier", domain.ErrInvalid, g.ScopeKind)
		}
	case ScopeOrg, ScopeCity, ScopeVehicle:
		if g.ScopeID == "" {
			return fmt.Errorf("%w: a %s binding names its scope", domain.ErrInvalid, g.ScopeKind)
		}
	default:
		return fmt.Errorf("%w: a binding's scope is the platform, an organisation, a city, a vehicle, or work, not %q",
			domain.ErrInvalid, g.ScopeKind)
	}
	if _, err := ParseRole(string(g.Role)); err != nil {
		return err
	}
	return nil
}

// Grant creates a binding. It is idempotent: granting a role that is already
// held returns the binding that already exists, so repeating a grant is safe.
func (a *Authorizer) Grant(ctx context.Context, conn db.Conn, spec GrantSpec) (Binding, error) {
	if err := spec.Validate(); err != nil {
		return Binding{}, err
	}
	var scopeID *string
	if spec.ScopeID != "" {
		scopeID = &spec.ScopeID
	}

	binding := Binding{
		ID:          ids.New(ids.KindBinding),
		SubjectKind: spec.SubjectKind,
		SubjectID:   spec.SubjectID,
		ScopeKind:   spec.ScopeKind,
		ScopeID:     spec.ScopeID,
		Role:        spec.Role,
		CreatedBy:   spec.CreatedBy,
	}
	err := conn.QueryRow(ctx, `
		INSERT INTO policy.binding
		    (id, subject_kind, subject_id, scope_kind, scope_id, role, created_by)
		VALUES ($1, $2::policy.subject_kind, $3, $4::policy.scope_kind, $5, $6::policy.role, $7)
		ON CONFLICT (subject_kind, subject_id, scope_kind, coalesce(scope_id, ''), role)
		    WHERE revoked_at IS NULL
		DO UPDATE SET role = EXCLUDED.role
		RETURNING id, created_at`,
		binding.ID, string(spec.SubjectKind), spec.SubjectID, string(spec.ScopeKind),
		scopeID, string(spec.Role), spec.CreatedBy,
	).Scan(&binding.ID, &binding.CreatedAt)
	if err != nil {
		return Binding{}, fmt.Errorf("granting %s: %w", spec.Role, err)
	}
	return binding, nil
}

// Revoke withdraws a binding. Revocation takes effect on the next decision,
// which is the next request; nothing is cached.
func (a *Authorizer) Revoke(ctx context.Context, conn db.Conn, bindingID string) error {
	tag, err := conn.Exec(ctx,
		`UPDATE policy.binding SET revoked_at = now() WHERE id = $1 AND revoked_at IS NULL`,
		bindingID)
	if err != nil {
		return fmt.Errorf("revoking a binding: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return db.ErrNotFound
	}
	return nil
}

// RevokeSubjectAtScope withdraws every role a subject holds at a scope, which
// is how access to a city is withdrawn from an institution in one action.
func (a *Authorizer) RevokeSubjectAtScope(ctx context.Context, conn db.Conn, subjectKind SubjectKind, subjectID string, scope ScopeKind, scopeID string) (int64, error) {
	tag, err := conn.Exec(ctx, `
		UPDATE policy.binding SET revoked_at = now()
		WHERE revoked_at IS NULL
		  AND subject_kind = $1::policy.subject_kind AND subject_id = $2
		  AND scope_kind = $3::policy.scope_kind AND coalesce(scope_id, '') = $4`,
		string(subjectKind), subjectID, string(scope), scopeID)
	if err != nil {
		return 0, fmt.Errorf("revoking bindings at %s: %w", scope, err)
	}
	return tag.RowsAffected(), nil
}

// BindingsAtScope lists the live bindings at a scope, which is what a steward
// reads to see who has been granted access to a place.
func (a *Authorizer) BindingsAtScope(ctx context.Context, scope ScopeKind, scopeID string) ([]Binding, error) {
	rows, err := a.pool.Query(ctx, `
		SELECT id, subject_kind, subject_id, scope_kind, coalesce(scope_id, ''), role, created_at, created_by
		FROM policy.binding
		WHERE revoked_at IS NULL
		  AND scope_kind = $1::policy.scope_kind
		  AND coalesce(scope_id, '') = $2
		ORDER BY created_at`,
		string(scope), scopeID)
	if err != nil {
		return nil, fmt.Errorf("reading bindings at %s: %w", scope, err)
	}
	defer rows.Close()

	var bindings []Binding
	for rows.Next() {
		var binding Binding
		if err := rows.Scan(&binding.ID, &binding.SubjectKind, &binding.SubjectID,
			&binding.ScopeKind, &binding.ScopeID, &binding.Role,
			&binding.CreatedAt, &binding.CreatedBy); err != nil {
			return nil, err
		}
		bindings = append(bindings, binding)
	}
	return bindings, rows.Err()
}

// Denial is a recorded refusal, so that "why can I not see this" is answerable
// from data.
type Denial struct {
	ID           string    `json:"id"`
	OccurredAt   time.Time `json:"occurredAt"`
	PrincipalID  string    `json:"principalId,omitempty"`
	Action       string    `json:"action"`
	ResourceKind string    `json:"resourceKind"`
	ResourceID   string    `json:"resourceId,omitempty"`
	Effect       string    `json:"effect"`
	Reason       string    `json:"reason"`
	RequestID    string    `json:"requestId"`
}

// DenialsForPrincipal reads the most recent refusals a principal received.
func (a *Authorizer) DenialsForPrincipal(ctx context.Context, principalID string, limit int) ([]Denial, error) {
	rows, err := a.pool.Query(ctx, `
		SELECT id, occurred_at, coalesce(principal_id, ''), action, resource_kind,
		       coalesce(resource_id, ''), effect, reason, request_id
		FROM policy.denial
		WHERE principal_id = $1
		ORDER BY occurred_at DESC
		LIMIT $2`, principalID, limit)
	if err != nil {
		return nil, fmt.Errorf("reading denials: %w", err)
	}
	defer rows.Close()

	var denials []Denial
	for rows.Next() {
		var denial Denial
		if err := rows.Scan(&denial.ID, &denial.OccurredAt, &denial.PrincipalID,
			&denial.Action, &denial.ResourceKind, &denial.ResourceID,
			&denial.Effect, &denial.Reason, &denial.RequestID); err != nil {
			return nil, err
		}
		denials = append(denials, denial)
	}
	return denials, rows.Err()
}
