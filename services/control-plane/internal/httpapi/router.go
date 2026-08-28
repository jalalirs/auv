// Package httpapi is transport. It reads requests, calls the components that
// own the work, and writes responses. It holds no domain logic and makes no
// access decisions of its own.
//
// Every route is declared with the action it performs and the resource it acts
// upon. The router — not the handler — authenticates the caller and consults
// the decision point before the handler runs. A handler therefore cannot forget
// to check access, and TestEveryRouteIsGoverned refuses a build in which a
// route was declared without one.
package httpapi

import (
	"fmt"
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// ResourceOf derives the resource a request acts upon, usually from its path.
type ResourceOf func(*http.Request) (policy.Resource, error)

// Route is one declared endpoint.
type Route struct {
	Method  string
	Pattern string
	// Summary says what the route is for, in the words used in the contract.
	Summary string
	// Public marks the few routes that must work before anyone is known:
	// liveness, readiness, build identity, and signing in. Every other route
	// requires an authenticated principal.
	Public bool
	// Action is what the caller is attempting. Required unless Public.
	Action policy.Action
	// Resource derives what is being acted upon. Required unless Public.
	Resource ResourceOf
	Handle   http.HandlerFunc
}

// Router registers routes and enforces the access rules they declare.
type Router struct {
	mux    *http.ServeMux
	routes []Route
	deps   *Dependencies
}

// NewRouter builds the router over the platform's components.
func NewRouter(deps *Dependencies) *Router {
	router := &Router{mux: http.NewServeMux(), deps: deps}
	router.registerAll()
	return router
}

// Routes returns every declared route, which is what lets a test assert that
// the table as a whole obeys the rules.
func (rt *Router) Routes() []Route {
	out := make([]Route, len(rt.routes))
	copy(out, rt.routes)
	return out
}

// register adds one route, wrapping it in the checks its declaration implies.
func (rt *Router) register(route Route) {
	if route.Handle == nil {
		panic(fmt.Sprintf("route %s %s has no handler", route.Method, route.Pattern))
	}
	if !route.Public {
		if route.Action == "" {
			panic(fmt.Sprintf("route %s %s declares no action", route.Method, route.Pattern))
		}
		if route.Resource == nil {
			panic(fmt.Sprintf("route %s %s declares no resource", route.Method, route.Pattern))
		}
		if _, _, err := policy.Requires(route.Action); err != nil {
			panic(fmt.Sprintf("route %s %s: %v", route.Method, route.Pattern, err))
		}
	}
	rt.routes = append(rt.routes, route)
	rt.mux.HandleFunc(route.Method+" "+route.Pattern, rt.guard(route))
}

// guard authenticates the caller and consults the decision point before the
// handler runs. This is the only path to a handler, so no handler can be
// reached without it.
func (rt *Router) guard(route Route) http.HandlerFunc {
	if route.Public {
		return route.Handle
	}
	return func(w http.ResponseWriter, r *http.Request) {
		subject, signedIn := subjectOf(r.Context())
		if !signedIn {
			writeUnauthenticated(w, r)
			return
		}

		resource, err := route.Resource(r)
		if err != nil {
			writeError(w, r, err)
			return
		}

		decision, err := rt.deps.Authorizer.Decide(r.Context(), subject, route.Action, resource)
		if err != nil {
			writeError(w, r, err)
			return
		}
		if !decision.Allowed() {
			writeDenied(w, r, decision)
			return
		}

		route.Handle(w, r.WithContext(withDecision(r.Context(), decision)))
	}
}

// ServeHTTP dispatches a request.
func (rt *Router) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	rt.mux.ServeHTTP(w, r)
}

// Handler returns the router wrapped in the middleware every request passes
// through, outermost first.
func (rt *Router) Handler() http.Handler {
	var handler http.Handler = rt
	handler = rt.deps.authenticate(handler)
	handler = recoverPanics(rt.deps.Logger, handler)
	handler = logRequests(rt.deps.Logger, handler)
	handler = withRequestID(handler)
	return handler
}

// resource helpers ----------------------------------------------------------

// atPlatform names the installation itself.
func atPlatform() ResourceOf {
	return func(*http.Request) (policy.Resource, error) { return policy.Platform(), nil }
}

// atWork names the queue service principals lease from.
func atWork() ResourceOf {
	return func(*http.Request) (policy.Resource, error) { return policy.Work(), nil }
}

// fromPath names a resource identified by a path segment.
func fromPath(kind policy.ResourceKind, segment string) ResourceOf {
	return func(r *http.Request) (policy.Resource, error) {
		value := r.PathValue(segment)
		if value == "" {
			return policy.Resource{}, fmt.Errorf("%s is missing from the path", segment)
		}
		return policy.Resource{Kind: kind, ID: value}, nil
	}
}
