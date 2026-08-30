package policy

import (
	"context"
	"errors"
	"fmt"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
	"github.com/jalalirs/auv/services/control-plane/internal/reqctx"
)

// Authorizer decides every access question the platform asks.
//
// It loads the facts it decides on rather than accepting them from a caller,
// so no component can influence a decision by describing a resource
// inaccurately.
type Authorizer struct {
	pool *db.Pool
}

// NewAuthorizer builds the decision point over the system of record.
func NewAuthorizer(pool *db.Pool) *Authorizer { return &Authorizer{pool: pool} }

// VersionFilter describes which layer versions a subject may see. The decision
// point produces it; repositories apply it unchanged. Deciding visibility here
// and applying it there keeps one answer to who may see what.
type VersionFilter struct {
	// Canonical admits versions that are part of the shared record.
	Canonical bool
	// RestrictedOfOrgs admits restricted contributions attributed to these
	// organisations, which is how a contributor sees its own work.
	RestrictedOfOrgs []string
	// AllRestricted admits every restricted contribution in the scope, which is
	// how a steward reviews what has been offered.
	AllRestricted bool
	// IncludeWithdrawn admits retracted versions, which stewards must be able
	// to inspect and ordinary readers must not see by default.
	IncludeWithdrawn bool
}

// Decide answers an access question and records a refusal when the answer is
// no. Why access was denied is data, not a log line.
func (a *Authorizer) Decide(ctx context.Context, subject Subject, action Action, resource Resource) (Decision, error) {
	decision, err := a.evaluate(ctx, subject, action, resource)
	if err != nil {
		return Decision{}, err
	}
	if !decision.Allowed() {
		if err := a.recordDenial(ctx, subject, action, resource, decision); err != nil {
			return Decision{}, fmt.Errorf("recording a denial: %w", err)
		}
	}
	return decision, nil
}

// evaluate answers the question without recording it, so that a decision which
// consults another decision does not write two refusals for one request.
func (a *Authorizer) evaluate(ctx context.Context, subject Subject, action Action, resource Resource) (Decision, error) {
	need, kinds, err := Requires(action)
	if err != nil {
		return Decision{}, err
	}
	if !AppliesTo(action, resource.Kind) {
		return Decision{}, fmt.Errorf("action %q does not apply to a %s (it applies to %v)",
			action, resource.Kind, kinds)
	}

	switch resource.Kind {
	case ResourcePlatform:
		return a.decideAtScope(ctx, subject, need, ScopePlatform, "the platform")
	case ResourceWork:
		return a.decideAtScope(ctx, subject, need, ScopeWork, "the work queue")
	case ResourceOrg:
		return a.decideOrg(ctx, subject, need, resource.ID)
	case ResourceCity:
		return a.decideCity(ctx, subject, need, resource.ID)
	case ResourceVehicle:
		return a.decideVehicle(ctx, subject, need, resource.ID)
	case ResourceQueue:
		return a.decideQueue(ctx, subject, need, resource.ID)
	case ResourceDive:
		return a.decideDive(ctx, subject, need, resource.ID)
	case ResourceJob:
		return a.decideJob(ctx, subject, need, resource.ID)
	default:
		return Decision{}, fmt.Errorf("resource kind %q has no decision rule", resource.Kind)
	}
}

func allow(role Role, filter VersionFilter) Decision {
	return Decision{Effect: EffectAllow, Reason: "", Role: role, Visible: filter}
}

func denyHidden(reason string) Decision {
	return Decision{Effect: EffectDenyHidden, Reason: reason}
}

func denyVisible(reason string) Decision {
	return Decision{Effect: EffectDenyVisible, Reason: reason}
}

// decideAtScope answers questions about a scope that has no identifier: the
// installation itself, or the work queue. There is no implicit authority at
// either: a principal holds what it has been bound.
func (a *Authorizer) decideAtScope(ctx context.Context, subject Subject, need Role, scope ScopeKind, described string) (Decision, error) {
	role, err := a.effectiveRole(ctx, subject, scope, "")
	if err != nil {
		return Decision{}, err
	}
	if role.AtLeast(need) {
		return allow(role, a.platformFilter(subject, role)), nil
	}
	return denyVisible(fmt.Sprintf(
		"this action needs %s at %s; you hold %s", need, described, describe(role))), nil
}

// decideOrg answers questions about one organisation's own work.
func (a *Authorizer) decideOrg(ctx context.Context, subject Subject, need Role, orgID string) (Decision, error) {
	role, err := a.effectiveRole(ctx, subject, ScopeOrg, orgID)
	if err != nil {
		return Decision{}, err
	}
	if role.AtLeast(need) {
		return allow(role, VersionFilter{Canonical: true, RestrictedOfOrgs: subject.OrgIDs}), nil
	}
	if !role.AtLeast(RoleViewer) && !subject.InOrg(orgID) {
		return denyHidden("no organisation with that identifier is visible to you"), nil
	}
	return denyVisible(fmt.Sprintf(
		"this action needs %s in that organisation; you hold %s", need, describe(role))), nil
}

// decideCity answers questions about a place.
//
// Discoverability decides what a principal with no binding may learn, and it is
// consulted only after bindings prove insufficient, so a binding always wins.
func (a *Authorizer) decideCity(ctx context.Context, subject Subject, need Role, cityID string) (Decision, error) {
	var slug string
	var discoverable bool
	err := a.pool.QueryRow(ctx,
		`SELECT slug, discoverable FROM catalog.city WHERE id = $1 AND retired_at IS NULL`,
		cityID).Scan(&slug, &discoverable)
	if errors.Is(db.Translate(err), db.ErrNotFound) {
		return denyHidden("no city with that identifier is visible to you"), nil
	}
	if err != nil {
		return Decision{}, fmt.Errorf("reading a city: %w", err)
	}

	role, err := a.effectiveRole(ctx, subject, ScopeCity, cityID)
	if err != nil {
		return Decision{}, err
	}
	if role.AtLeast(need) {
		return allow(role, a.platformFilter(subject, role)), nil
	}

	// An undiscoverable city a caller holds nothing on is reported as absent,
	// so that its existence is not itself a disclosure.
	if role.AtLeast(RoleViewer) || discoverable {
		return denyVisible(fmt.Sprintf(
			"this action needs %s in %s; you hold %s", need, slug, describe(role))), nil
	}
	return denyHidden("no city with that identifier is visible to you"), nil
}

// decideJob answers questions about work, which belongs to the organisation
// that submitted it.
// decideVehicle answers questions about a vehicle.
//
// The same shape as a city, because the two are granted the same way: a grant
// decides, and where there is none, a discoverable asset says why it refused
// while an undiscoverable one says only that it is not there.
func (a *Authorizer) decideVehicle(ctx context.Context, subject Subject, need Role, vehicleID string) (Decision, error) {
	var slug string
	var discoverable bool
	err := a.pool.QueryRow(ctx,
		`SELECT slug, discoverable FROM catalog.vehicle WHERE id = $1 AND retired_at IS NULL`,
		vehicleID).Scan(&slug, &discoverable)
	if errors.Is(db.Translate(err), db.ErrNotFound) {
		return denyHidden("no vehicle with that identifier is visible to you"), nil
	}
	if err != nil {
		return Decision{}, fmt.Errorf("reading a vehicle: %w", err)
	}

	role, err := a.effectiveRole(ctx, subject, ScopeVehicle, vehicleID)
	if err != nil {
		return Decision{}, err
	}
	if role.AtLeast(need) {
		return allow(role, a.platformFilter(subject, role)), nil
	}
	if role.AtLeast(RoleViewer) || discoverable {
		return denyVisible(fmt.Sprintf(
			"this action needs %s on %s; you hold %s", need, slug, describe(role))), nil
	}
	return denyHidden("no vehicle with that identifier is visible to you"), nil
}

// decideQueue answers questions about a queue of hardware.
//
// Hardware carries no discoverability. Somebody who cannot run on a queue has
// no reason to learn it exists, so an ungranted queue is absent rather than
// refused — and a queue that does not exist looks exactly the same, which is
// the point.
func (a *Authorizer) decideQueue(ctx context.Context, subject Subject, need Role, queueID string) (Decision, error) {
	var slug string
	err := a.pool.QueryRow(ctx,
		`SELECT slug FROM compute.queue WHERE id = $1`, queueID).Scan(&slug)
	if errors.Is(db.Translate(err), db.ErrNotFound) {
		return denyHidden("no queue with that identifier is visible to you"), nil
	}
	if err != nil {
		return Decision{}, fmt.Errorf("reading a queue: %w", err)
	}

	role, err := a.effectiveRole(ctx, subject, ScopeQueue, queueID)
	if err != nil {
		return Decision{}, err
	}
	if role.AtLeast(need) {
		return allow(role, a.platformFilter(subject, role)), nil
	}
	if role.AtLeast(RoleViewer) {
		return denyVisible(fmt.Sprintf(
			"this action needs %s on %s; you hold %s", need, slug, describe(role))), nil
	}
	return denyHidden("no queue with that identifier is visible to you"), nil
}

// decideDive answers questions about a dive, which belongs to the institution
// that composed it.
//
// A dive is not shared the way a city is: it is somebody's experiment, and the
// authority to read or change it is the authority they hold in their own
// institution. Asking the organisation rather than carrying a second set of
// bindings is what keeps that true without a second thing to maintain.
func (a *Authorizer) decideDive(ctx context.Context, subject Subject, need Role, diveID string) (Decision, error) {
	var orgID string
	err := a.pool.QueryRow(ctx,
		`SELECT org_id FROM dive.dive WHERE id = $1 AND archived_at IS NULL`,
		diveID).Scan(&orgID)
	if errors.Is(db.Translate(err), db.ErrNotFound) {
		return denyHidden("no dive with that identifier is visible to you"), nil
	}
	if err != nil {
		return Decision{}, fmt.Errorf("reading a dive: %w", err)
	}

	decision, err := a.decideOrg(ctx, subject, need, orgID)
	if err != nil {
		return Decision{}, err
	}
	// Somebody outside the institution should not learn that the dive exists,
	// so the organisation's refusal is reported as absence here.
	if decision.Effect == EffectDenyVisible {
		return decision, nil
	}
	if !decision.Allowed() {
		return denyHidden("no dive with that identifier is visible to you"), nil
	}
	return decision, nil
}

func (a *Authorizer) decideJob(ctx context.Context, subject Subject, need Role, jobID string) (Decision, error) {
	orgID, err := a.jobOrg(ctx, jobID)
	if errors.Is(err, db.ErrNotFound) {
		return denyHidden("no job with that identifier is visible to you"), nil
	}
	if err != nil {
		return Decision{}, err
	}
	return a.decideOrg(ctx, subject, need, orgID)
}

// platformFilter states which platform-scoped versions a subject may see.
func (a *Authorizer) platformFilter(subject Subject, role Role) VersionFilter {
	return VersionFilter{
		Canonical:        true,
		RestrictedOfOrgs: subject.OrgIDs,
		AllRestricted:    role.AtLeast(RoleSteward),
		IncludeWithdrawn: role.AtLeast(RoleSteward),
	}
}

// cityFilter states which versions within a city a subject may see. A
// contributor sees the shared record and its own organisation's work; a
// steward additionally sees every contribution offered for review.
func (a *Authorizer) cityFilter(subject Subject, role Role) VersionFilter {
	filter := VersionFilter{Canonical: true}
	if role.AtLeast(RoleContributor) {
		filter.RestrictedOfOrgs = subject.OrgIDs
	}
	if role.AtLeast(RoleSteward) {
		filter.AllRestricted = true
		filter.IncludeWithdrawn = true
	}
	return filter
}

func describe(role Role) string {
	switch role {
	case "", RoleAnyone:
		return "only what signing in confers"
	default:
		return string(role)
	}
}

// effectiveRole is the strongest authority a subject holds at a scope, counting
// bindings on the subject itself and on any organisation it belongs to.
// Platform bindings apply everywhere, which is what makes a platform steward
// able to curate any city.
func (a *Authorizer) effectiveRole(ctx context.Context, subject Subject, scope ScopeKind, scopeID string) (Role, error) {
	rows, err := a.pool.Query(ctx, `
		SELECT role
		FROM policy.binding
		WHERE revoked_at IS NULL
		  AND (
		        (subject_kind = 'principal' AND subject_id = $1)
		     OR (subject_kind = 'org'       AND subject_id = ANY($2))
		      )
		  AND (
		        scope_kind = 'platform'
		     OR (scope_kind = $3::policy.scope_kind AND coalesce(scope_id, '') = $4)
		      )`,
		subject.PrincipalID, subject.OrgIDs, string(scope), scopeID)
	if err != nil {
		return "", fmt.Errorf("reading bindings: %w", err)
	}
	defer rows.Close()

	// Signing in confers RoleAnyone everywhere. It is the floor, not a grant,
	// and it is what lets an authenticated person browse the catalogue.
	//
	// A service principal gets no such floor: a worker, an edge station, or a
	// vehicle holds exactly what it has been bound and nothing besides, so a
	// compromised one cannot even discover what places exist.
	strongest := Role("")
	if subject.PrincipalID != "" && !subject.IsService {
		strongest = RoleAnyone
	}
	for rows.Next() {
		var role Role
		if err := rows.Scan(&role); err != nil {
			return "", err
		}
		strongest = stronger(strongest, role)
	}
	return strongest, rows.Err()
}

func (a *Authorizer) jobOrg(ctx context.Context, jobID string) (string, error) {
	var orgID string
	err := a.pool.QueryRow(ctx, `SELECT org_id FROM exec.job WHERE id = $1`, jobID).Scan(&orgID)
	return orgID, db.Translate(err)
}

func (a *Authorizer) recordDenial(ctx context.Context, subject Subject, action Action, resource Resource, decision Decision) error {
	effect := "hidden"
	if decision.Effect == EffectDenyVisible {
		effect = "visible"
	}
	var resourceID *string
	if resource.ID != "" {
		resourceID = &resource.ID
	}
	var principalID *string
	if subject.PrincipalID != "" {
		principalID = &subject.PrincipalID
	}
	_, err := a.pool.Exec(ctx, `
		INSERT INTO policy.denial
		    (id, principal_id, action, resource_kind, resource_id, effect, reason, request_id)
		VALUES ($1, $2, $3, $4, $5, $6::policy.denial_effect, $7, $8)`,
		ids.New(ids.KindDenial), principalID, string(action), string(resource.Kind),
		resourceID, effect, decision.Reason, reqctx.RequestID(ctx))
	return err
}

// AssetScope describes which assets of one kind a subject may learn of.
//
// The decision point produces it and the repository applies it unchanged, so
// that a listing and a read agree about what exists without either deciding for
// itself. It is deliberately the same shape for cities and vehicles: the two
// are granted identically, and giving them one answer is what stops them
// drifting into two.
type AssetScope struct {
	// All admits every asset, which platform authority carries.
	All bool
	// BoundIDs admits assets the subject holds a binding on, whatever their
	// discoverability.
	BoundIDs []string
	// IncludeDiscoverable admits assets listed to anyone signed in. An
	// undiscoverable asset is never admitted by this, which is what makes it
	// indistinguishable from one that does not exist.
	IncludeDiscoverable bool
}

// Assets reports which cities or vehicles a subject may learn of.
//
// A queue is asked for the same way and answered without discoverability,
// because hardware carries none: somebody who cannot run on a queue has no
// reason to learn that it exists.
func (a *Authorizer) Assets(ctx context.Context, subject Subject, kind ScopeKind) (AssetScope, error) {
	switch kind {
	case ScopeCity, ScopeVehicle, ScopeQueue:
	default:
		return AssetScope{}, fmt.Errorf("%q is not a scope assets are granted at", kind)
	}

	platformRole, err := a.effectiveRole(ctx, subject, ScopePlatform, "")
	if err != nil {
		return AssetScope{}, err
	}
	if platformRole.AtLeast(RoleViewer) {
		return AssetScope{All: true, IncludeDiscoverable: kind != ScopeQueue}, nil
	}

	rows, err := a.pool.Query(ctx, `
		SELECT DISTINCT scope_id
		FROM policy.binding
		WHERE revoked_at IS NULL
		  AND scope_kind = $1::policy.scope_kind
		  AND scope_id IS NOT NULL
		  AND (
		        (subject_kind = 'principal' AND subject_id = $2)
		     OR (subject_kind = 'org'       AND subject_id = ANY($3))
		      )`,
		string(kind), subject.PrincipalID, subject.OrgIDs)
	if err != nil {
		return AssetScope{}, fmt.Errorf("reading %s bindings: %w", kind, err)
	}
	defer rows.Close()

	scope := AssetScope{IncludeDiscoverable: kind != ScopeQueue, BoundIDs: []string{}}
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return AssetScope{}, err
		}
		scope.BoundIDs = append(scope.BoundIDs, id)
	}
	return scope, rows.Err()
}
