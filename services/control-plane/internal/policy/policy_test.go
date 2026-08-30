package policy

import (
	"errors"
	"testing"

	"github.com/jalalirs/auv/services/control-plane/internal/domain"
)

// Roles are ordered, and a stronger role carries everything a weaker one does.
func TestRolesAreOrdered(t *testing.T) {
	order := []Role{RoleAnyone, RoleViewer, RoleContributor, RoleSteward, RoleAdmin}
	for i, held := range order {
		for j, needed := range order {
			want := i >= j
			if got := held.AtLeast(needed); got != want {
				t.Errorf("%s.AtLeast(%s) = %v, want %v", held, needed, got, want)
			}
		}
	}
	// An unbound subject holds nothing, which is weaker than everything.
	for _, needed := range order {
		if Role("").AtLeast(needed) {
			t.Errorf("an unbound subject was treated as holding %s", needed)
		}
	}
}

// RoleAnyone is conferred by authenticating, not by anyone's decision, so it
// must not be grantable.
func TestTheBaselineRoleCannotBeGranted(t *testing.T) {
	if _, err := ParseRole(string(RoleAnyone)); !errors.Is(err, domain.ErrInvalid) {
		t.Fatalf("ParseRole(anyone) error = %v, want ErrInvalid", err)
	}
	for _, role := range []Role{RoleViewer, RoleContributor, RoleSteward, RoleAdmin} {
		if _, err := ParseRole(string(role)); err != nil {
			t.Errorf("ParseRole(%s) error = %v", role, err)
		}
	}
}

// An action with no stated requirement cannot be authorised at all, so a typo
// closes a route rather than opening one.
func TestAnUndefinedActionCannotBeAuthorised(t *testing.T) {
	if _, _, err := Requires(Action("city.destroy")); err == nil {
		t.Fatal("an action with no stated requirement was authorisable")
	}
	if AppliesTo(Action("city.destroy"), ResourceCity) {
		t.Fatal("an undefined action was reported as applying to a resource")
	}
}

func TestEveryActionStatesWhatItAppliesTo(t *testing.T) {
	for _, action := range Actions() {
		role, kinds, err := Requires(action)
		if err != nil {
			t.Errorf("Requires(%s) error = %v", action, err)
			continue
		}
		if role == "" {
			t.Errorf("action %q states no required role", action)
		}
		if len(kinds) == 0 {
			t.Errorf("action %q applies to no resource kind", action)
		}
	}
}

// Reading is the weakest thing anyone does, and changing the record is among
// the strongest. If these ever invert, the model is wrong.
func TestReadingNeedsLessAuthorityThanChanging(t *testing.T) {
	pairs := []struct{ read, change Action }{
		{CityRead, CityGrant},
		{VehicleRead, VehicleGrant},
		{VehicleRead, VehicleCreate},
		{JobRead, JobSubmit},
		{OrgRead, OrgAdminister},
	}
	for _, pair := range pairs {
		reading, _, err := Requires(pair.read)
		if err != nil {
			t.Fatalf("Requires(%s) error = %v", pair.read, err)
		}
		changing, _, err := Requires(pair.change)
		if err != nil {
			t.Fatalf("Requires(%s) error = %v", pair.change, err)
		}
		if !changing.AtLeast(reading) || changing == reading && pair.read != pair.change {
			if !changing.AtLeast(reading) {
				t.Errorf("%s needs %s but %s needs %s, which is weaker",
					pair.change, changing, pair.read, reading)
			}
		}
	}
}

func TestAGrantMustBeExpressible(t *testing.T) {
	cases := []struct {
		name  string
		spec  GrantSpec
		valid bool
	}{
		{"a city shared with an institution", GrantSpec{
			SubjectKind: SubjectOrg, SubjectID: "org_x",
			ScopeKind: ScopeCity, ScopeID: "city_y", Role: RoleViewer}, true},
		{"a platform administrator", GrantSpec{
			SubjectKind: SubjectPrincipal, SubjectID: "prin_x",
			ScopeKind: ScopePlatform, Role: RoleAdmin}, true},
		{"a worker over the work queue", GrantSpec{
			SubjectKind: SubjectPrincipal, SubjectID: "prin_w",
			ScopeKind: ScopeWork, Role: RoleAdmin}, true},
		{"the platform scope has no identifier", GrantSpec{
			SubjectKind: SubjectPrincipal, SubjectID: "prin_x",
			ScopeKind: ScopePlatform, ScopeID: "something", Role: RoleAdmin}, false},
		{"a city binding names its city", GrantSpec{
			SubjectKind: SubjectOrg, SubjectID: "org_x",
			ScopeKind: ScopeCity, Role: RoleViewer}, false},
		{"a binding names its subject", GrantSpec{
			SubjectKind: SubjectOrg, ScopeKind: ScopeCity, ScopeID: "city_y",
			Role: RoleViewer}, false},
		{"the baseline role is not grantable", GrantSpec{
			SubjectKind: SubjectOrg, SubjectID: "org_x",
			ScopeKind: ScopeCity, ScopeID: "city_y", Role: RoleAnyone}, false},
	}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			err := test.spec.Validate()
			if test.valid != (err == nil) {
				t.Fatalf("Validate() error = %v, valid = %v", err, test.valid)
			}
		})
	}
}

func TestASubjectKnowsItsOrganisations(t *testing.T) {
	subject := Subject{PrincipalID: "prin_a", OrgIDs: []string{"org_a", "org_b"}}
	if !subject.InOrg("org_b") {
		t.Fatal("a member was not recognised as belonging to its organisation")
	}
	if subject.InOrg("org_c") {
		t.Fatal("a non-member was treated as belonging to an organisation")
	}
}
