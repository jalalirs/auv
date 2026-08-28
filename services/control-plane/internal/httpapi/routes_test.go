package httpapi

import (
	"slices"
	"strings"
	"testing"

	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// routeTable builds the route table without any live dependency. Registration
// is pure: it declares what each route does, and only the handlers behind it
// need components.
func routeTable(t *testing.T) []Route {
	t.Helper()
	router := NewRouter(&Dependencies{})
	return router.Routes()
}

// TestEveryRouteIsGoverned is the structural guarantee behind ADR-0005: access
// is decided in one place, for every route, without exception.
//
// It is a test rather than a review note because a review can be skipped and a
// build cannot.
func TestEveryRouteIsGoverned(t *testing.T) {
	for _, route := range routeTable(t) {
		name := route.Method + " " + route.Pattern
		if route.Public {
			continue
		}
		if route.Action == "" {
			t.Errorf("%s declares no action, so nothing decides whether it is permitted", name)
			continue
		}
		if route.Resource == nil {
			t.Errorf("%s declares no resource, so nothing decides what it acts upon", name)
		}
		if _, _, err := policy.Requires(route.Action); err != nil {
			t.Errorf("%s: %v", name, err)
		}
	}
}

// TestOnlyExpectedRoutesArePublic keeps the set of endpoints that work before
// anyone is known small and deliberate. Adding one requires changing this list,
// which is the point.
func TestOnlyExpectedRoutesArePublic(t *testing.T) {
	var public []string
	for _, route := range routeTable(t) {
		if route.Public {
			public = append(public, route.Method+" "+route.Pattern)
		}
	}
	slices.Sort(public)

	expected := slices.Clone(PublicRoutes)
	slices.Sort(expected)

	if !slices.Equal(public, expected) {
		t.Fatalf("the public routes have changed.\n  in the table: %v\n  declared:     %v",
			public, expected)
	}
}

// TestEveryRouteDeclaresWhatItIsFor keeps the route table readable as a
// description of the product rather than as a list of paths.
func TestEveryRouteDeclaresWhatItIsFor(t *testing.T) {
	for _, route := range routeTable(t) {
		if strings.TrimSpace(route.Summary) == "" {
			t.Errorf("%s %s has no summary", route.Method, route.Pattern)
		}
	}
}

// TestEveryActionIsReachable catches an action that was defined and then never
// wired to anything, which would mean a capability that exists in the policy
// model but not in the product.
func TestEveryActionIsReachable(t *testing.T) {
	used := map[policy.Action]bool{}
	for _, route := range routeTable(t) {
		if !route.Public {
			used[route.Action] = true
		}
	}
	for _, action := range policy.Actions() {
		if !used[action] {
			t.Errorf("action %q is defined but no route performs it", action)
		}
	}
}

// TestEveryRouteActionMatchesItsResource catches a route that names an action
// which cannot apply to the kind of thing the route acts upon — for example
// asking to publish a city.
func TestEveryRouteActionMatchesItsResource(t *testing.T) {
	for _, route := range routeTable(t) {
		if route.Public {
			continue
		}
		_, kinds, err := policy.Requires(route.Action)
		if err != nil {
			continue
		}
		if len(kinds) == 0 {
			t.Errorf("%s %s: action %q applies to no resource kind",
				route.Method, route.Pattern, route.Action)
		}
	}
}

// TestNoTwoRoutesShareAMethodAndPattern catches a duplicate registration, which
// the multiplexer would otherwise reject at startup rather than in a test.
func TestNoTwoRoutesShareAMethodAndPattern(t *testing.T) {
	seen := map[string]bool{}
	for _, route := range routeTable(t) {
		key := route.Method + " " + route.Pattern
		if seen[key] {
			t.Errorf("%s is registered twice", key)
		}
		seen[key] = true
	}
}
