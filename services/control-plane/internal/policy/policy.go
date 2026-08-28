// Package policy is the platform's single access-decision point.
//
// Every read and every write resolves here, including compute. No other
// package decides whether an action is permitted, and no other package holds a
// handle to the binding tables. A route that does not consult this package is
// a defect the route-table test refuses to let into a build.
//
// The package distinguishes two ways of saying no. A hidden denial reports
// absence, because the existence of some places is itself sensitive. A visible
// denial reports that the object exists and access may be requested. The
// difference is decided here and nowhere else.
package policy

import (
	"fmt"

	"github.com/jalalirs/auv/services/control-plane/internal/domain"
)

// Role is a named degree of authority at a scope. Roles are ordered: a
// stronger role can do everything a weaker one can.
type Role string

const (
	// RoleAnyone is the authority that signing in confers, held by every
	// authenticated principal everywhere. It is not grantable: it is the floor
	// beneath which no authenticated actor falls, and it is what lets a person
	// browse the catalogue without being bound to anything.
	RoleAnyone Role = "anyone"
	// RoleViewer may read.
	RoleViewer Role = "viewer"
	// RoleContributor may add its own work.
	RoleContributor Role = "contributor"
	// RoleSteward curates a scope: promoting, retracting, and granting.
	RoleSteward Role = "steward"
	// RoleAdmin administers a scope entirely.
	RoleAdmin Role = "admin"
)

// roleStrength orders roles. An unbound subject has the zero role, which is
// weaker than everything, including what signing in confers.
var roleStrength = map[Role]int{
	RoleAnyone: 1, RoleViewer: 2, RoleContributor: 3, RoleSteward: 4, RoleAdmin: 5,
}

// grantable lists the roles a binding may confer. RoleAnyone is deliberately
// absent: it is conferred by authenticating, not by anyone's decision.
var grantable = []Role{RoleViewer, RoleContributor, RoleSteward, RoleAdmin}

// ParseRole validates a role a binding may confer.
func ParseRole(value string) (Role, error) {
	for _, role := range grantable {
		if Role(value) == role {
			return role, nil
		}
	}
	return "", fmt.Errorf("%w: role %q is not one of viewer, contributor, steward, admin",
		domain.ErrInvalid, value)
}

// AtLeast reports whether this role carries the authority of the given role.
func (r Role) AtLeast(other Role) bool { return roleStrength[r] >= roleStrength[other] }

// stronger returns whichever of two roles carries more authority.
func stronger(a, b Role) Role {
	if roleStrength[a] >= roleStrength[b] {
		return a
	}
	return b
}

// ScopeKind is what a binding attaches to.
type ScopeKind string

const (
	// ScopePlatform covers the whole installation.
	ScopePlatform ScopeKind = "platform"
	// ScopeOrg covers one organisation's own work.
	ScopeOrg ScopeKind = "org"
	// ScopeCity covers one place.
	ScopeCity ScopeKind = "city"
	// ScopeWork covers the execution queue. It is separate from the platform
	// so that a worker holds authority over work and over nothing else.
	ScopeWork ScopeKind = "work"
)

// SubjectKind is who a binding attaches to. Binding an organisation grants the
// role to every member, which is how a city is shared with an institution.
type SubjectKind string

const (
	SubjectPrincipal SubjectKind = "principal"
	SubjectOrg       SubjectKind = "org"
)

// ResourceKind names the sort of thing an action is attempted upon.
type ResourceKind string

const (
	ResourcePlatform ResourceKind = "platform"
	ResourceOrg      ResourceKind = "org"
	ResourceCity     ResourceKind = "city"
	ResourceLayer    ResourceKind = "layer"
	ResourceJob      ResourceKind = "job"
	ResourceWork     ResourceKind = "work"
)

// Resource is what an action is attempted upon. The decision point loads
// whatever else it needs to decide, so a caller cannot influence the outcome
// by describing a resource inaccurately.
type Resource struct {
	Kind ResourceKind
	ID   string
}

// Platform names the installation itself.
func Platform() Resource { return Resource{Kind: ResourcePlatform} }

// City names one place.
func City(id string) Resource { return Resource{Kind: ResourceCity, ID: id} }

// Layer names one layer.
func Layer(id string) Resource { return Resource{Kind: ResourceLayer, ID: id} }

// Org names one organisation.
func Org(id string) Resource { return Resource{Kind: ResourceOrg, ID: id} }

// Job names one unit of work.
func Job(id string) Resource { return Resource{Kind: ResourceJob, ID: id} }

// Work names the work queue that service principals lease from.
func Work() Resource { return Resource{Kind: ResourceWork} }

// Effect is how a decision is reported to the caller.
type Effect string

const (
	// EffectAllow permits the action.
	EffectAllow Effect = "allow"
	// EffectDenyHidden refuses and reports absence, because the caller is not
	// entitled to learn that the object exists.
	EffectDenyHidden Effect = "deny_hidden"
	// EffectDenyVisible refuses and reports that the object exists and access
	// may be requested.
	EffectDenyVisible Effect = "deny_visible"
)

// Decision is the outcome of consulting the decision point.
type Decision struct {
	Effect Effect
	// Reason is written for the person who will read it in a denial record or
	// an error body, not for a log parser.
	Reason string
	// Role is the authority the subject held at the resource, which callers
	// use to vary what they return rather than to decide access again.
	Role Role
	// Visible describes which layer versions the subject may see. The decision
	// point produces it and repositories apply it unchanged, so that visibility
	// is decided in one place even though it is enforced in queries.
	Visible VersionFilter
}

// Allowed reports whether the action may proceed.
func (d Decision) Allowed() bool { return d.Effect == EffectAllow }

// Subject is an authenticated actor together with the organisations whose
// bindings it inherits. It is assembled once when a request is authenticated.
type Subject struct {
	PrincipalID string
	// OrgIDs are the organisations this principal belongs to. A binding on any
	// of them applies to this principal.
	OrgIDs []string
	// IsService marks workers, edge stations, and vehicles, which may lease
	// work but may not act as people.
	IsService bool
}

// InOrg reports whether the subject belongs to the given organisation.
func (s Subject) InOrg(orgID string) bool {
	for _, id := range s.OrgIDs {
		if id == orgID {
			return true
		}
	}
	return false
}
