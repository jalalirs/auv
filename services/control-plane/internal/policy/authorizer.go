package policy

import (
	"context"
	"errors"
	"fmt"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
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
		return a.decideCity(ctx, subject, action, need, resource.ID)
	case ResourceLayer:
		return a.decideLayer(ctx, subject, action, need, resource.ID)
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
func (a *Authorizer) decideCity(ctx context.Context, subject Subject, action Action, need Role, cityID string) (Decision, error) {
	facts, err := a.cityFacts(ctx, cityID)
	if errors.Is(err, db.ErrNotFound) {
		return denyHidden("no city with that identifier is visible to you"), nil
	}
	if err != nil {
		return Decision{}, err
	}

	role, err := a.effectiveRole(ctx, subject, ScopeCity, cityID)
	if err != nil {
		return Decision{}, err
	}
	if role.AtLeast(need) {
		return allow(role, a.cityFilter(subject, role)), nil
	}

	// An open city may be read by anyone signed in, which is what makes the
	// shared record shared.
	if facts.Discoverability == domain.ListedOpen && need == RoleViewer {
		return allow(RoleViewer, a.cityFilter(subject, RoleViewer)), nil
	}

	if role.AtLeast(RoleViewer) || facts.Discoverability != domain.Unlisted {
		return denyVisible(fmt.Sprintf(
			"this action needs %s in %s; you hold %s", need, facts.Slug, describe(role))), nil
	}
	return denyHidden("no city with that identifier is visible to you"), nil
}

// decideLayer answers questions about a layer, first establishing that its
// container is reachable. A layer is never more visible than the place that
// contains it; requiring the container's decision first is what enforces that.
func (a *Authorizer) decideLayer(ctx context.Context, subject Subject, action Action, need Role, layerID string) (Decision, error) {
	facts, err := a.layerFacts(ctx, layerID)
	if errors.Is(err, db.ErrNotFound) {
		return denyHidden("no layer with that identifier is visible to you"), nil
	}
	if err != nil {
		return Decision{}, err
	}

	if facts.ScopeKind == domain.PlatformScope {
		role, err := a.effectiveRole(ctx, subject, ScopePlatform, "")
		if err != nil {
			return Decision{}, err
		}
		// The shared world is readable by anyone signed in. Everything beyond
		// reading needs authority at the platform.
		if need == RoleViewer {
			return allow(stronger(role, RoleViewer), a.platformFilter(subject, role)), nil
		}
		if role.AtLeast(need) {
			return allow(role, a.platformFilter(subject, role)), nil
		}
		return denyVisible(fmt.Sprintf(
			"this action needs %s at the platform; you hold %s", need, describe(role))), nil
	}

	// A city layer is reachable only through its city.
	container, err := a.decideCity(ctx, subject, CityRead, RoleViewer, facts.CityID)
	if err != nil {
		return Decision{}, err
	}
	if !container.Allowed() {
		return container, nil
	}

	role, err := a.effectiveRole(ctx, subject, ScopeCity, facts.CityID)
	if err != nil {
		return Decision{}, err
	}
	role = stronger(role, container.Role)
	if role.AtLeast(need) {
		return allow(role, a.cityFilter(subject, role)), nil
	}
	return denyVisible(fmt.Sprintf(
		"this action needs %s in that city; you hold %s", need, describe(role))), nil
}

// decideJob answers questions about work, which belongs to the organisation
// that submitted it.
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

type cityFact struct {
	Slug            string
	Discoverability domain.Discoverability
}

func (a *Authorizer) cityFacts(ctx context.Context, cityID string) (cityFact, error) {
	var fact cityFact
	err := a.pool.QueryRow(ctx,
		`SELECT slug, discoverability FROM city.city WHERE id = $1`, cityID).
		Scan(&fact.Slug, &fact.Discoverability)
	return fact, db.Translate(err)
}

type layerFact struct {
	ScopeKind domain.ScopeKind
	CityID    string
}

func (a *Authorizer) layerFacts(ctx context.Context, layerID string) (layerFact, error) {
	var fact layerFact
	var cityID *string
	err := a.pool.QueryRow(ctx,
		`SELECT scope_kind, city_id FROM layer.layer WHERE id = $1`, layerID).
		Scan(&fact.ScopeKind, &cityID)
	if err != nil {
		return fact, db.Translate(err)
	}
	if cityID != nil {
		fact.CityID = *cityID
	}
	return fact, nil
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

// CatalogueScope describes which cities a subject may learn of. Like
// VersionFilter, the decision point produces it and the repository applies it,
// so that listing and reading agree about what is visible.
type CatalogueScope struct {
	// AllCities admits every city, which platform authority carries.
	AllCities bool
	// BoundCityIDs admits cities the subject holds a binding on, whatever
	// their discoverability.
	BoundCityIDs []string
	// IncludeListed admits cities that appear in the catalogue for anyone
	// signed in. Unlisted cities are never admitted by this.
	IncludeListed bool
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
// A queue is asked for the same way but answered differently: hardware carries
// no discoverability, because somebody who cannot run on a queue has no reason
// to learn that it exists.
func (a *Authorizer) Assets(ctx context.Context, subject Subject, kind ScopeKind) (AssetScope, error) {
	switch kind {
	case ScopeCity, ScopeVehicle, ScopeWork:
	default:
		return AssetScope{}, fmt.Errorf(
			"%w: %q is not a scope assets are granted at", domain.ErrInvalid, kind)
	}

	platformRole, err := a.effectiveRole(ctx, subject, ScopePlatform, "")
	if err != nil {
		return AssetScope{}, err
	}
	if platformRole.AtLeast(RoleViewer) {
		return AssetScope{All: true, IncludeDiscoverable: kind != ScopeWork}, nil
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

	scope := AssetScope{IncludeDiscoverable: kind != ScopeWork, BoundIDs: []string{}}
	for rows.Next() {
		var id string
		if err := rows.Scan(&id); err != nil {
			return AssetScope{}, err
		}
		scope.BoundIDs = append(scope.BoundIDs, id)
	}
	return scope, rows.Err()
}

// Catalogue reports which cities a subject may learn of. An unlisted city
// appears only to those bound to it; it is otherwise indistinguishable from a
// city that does not exist.
func (a *Authorizer) Catalogue(ctx context.Context, subject Subject) (CatalogueScope, error) {
	platformRole, err := a.effectiveRole(ctx, subject, ScopePlatform, "")
	if err != nil {
		return CatalogueScope{}, err
	}
	if platformRole.AtLeast(RoleViewer) {
		return CatalogueScope{AllCities: true, IncludeListed: true}, nil
	}

	rows, err := a.pool.Query(ctx, `
		SELECT DISTINCT scope_id
		FROM policy.binding
		WHERE revoked_at IS NULL
		  AND scope_kind = 'city'
		  AND scope_id IS NOT NULL
		  AND (
		        (subject_kind = 'principal' AND subject_id = $1)
		     OR (subject_kind = 'org'       AND subject_id = ANY($2))
		      )`,
		subject.PrincipalID, subject.OrgIDs)
	if err != nil {
		return CatalogueScope{}, fmt.Errorf("reading city bindings: %w", err)
	}
	defer rows.Close()

	scope := CatalogueScope{IncludeListed: true, BoundCityIDs: []string{}}
	for rows.Next() {
		var cityID string
		if err := rows.Scan(&cityID); err != nil {
			return CatalogueScope{}, err
		}
		scope.BoundCityIDs = append(scope.BoundCityIDs, cityID)
	}
	return scope, rows.Err()
}
