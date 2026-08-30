package httpapi

import (
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// PublicRoutes are the only endpoints that work before anyone is known. They
// exist because a process must be able to say it is alive, a deployment must be
// identifiable, and someone must be able to sign in.
//
// TestOnlyExpectedRoutesArePublic asserts that this list and the route table
// agree, so a route cannot become public without the list changing too.
var PublicRoutes = []string{
	"GET /health/live",
	"GET /health/ready",
	"GET /api/v1/platform",
	"POST /api/v1/sessions",
}

// registerAll declares the platform's routes.
//
// Each non-public route names the action it performs and the resource it acts
// upon. The router applies both before the handler runs, which is why no
// handler in this package checks access for itself.
func (rt *Router) registerAll() {
	d := rt.deps

	// Before anyone is known.
	rt.register(Route{Method: "GET", Pattern: "/health/live", Public: true,
		Summary: "the process can serve HTTP", Handle: d.live})
	rt.register(Route{Method: "GET", Pattern: "/health/ready", Public: true,
		Summary: "the record, the schema, and storage are all usable", Handle: d.ready})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/platform", Public: true,
		Summary: "the build serving this request", Handle: d.platformInfo})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/sessions", Public: true,
		Summary: "sign in", Handle: d.signIn})

	// Oneself.
	rt.register(Route{Method: "DELETE", Pattern: "/api/v1/sessions",
		Summary: "sign out", Action: policy.SelfEndSession, Resource: atPlatform(),
		Handle: d.signOut})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/me",
		Summary: "who the caller is", Action: policy.SelfRead, Resource: atPlatform(),
		Handle: d.me})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/me/denials",
		Summary: "refusals the caller has received", Action: policy.SelfRead,
		Resource: atPlatform(), Handle: d.readOwnDenials})

	// Institutions and people.
	rt.register(Route{Method: "POST", Pattern: "/api/v1/organisations",
		Summary: "found an institution", Action: policy.PlatformAdminister,
		Resource: atPlatform(), Handle: d.createOrganisation})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/people",
		Summary: "add someone who can sign in", Action: policy.PlatformAdminister,
		Resource: atPlatform(), Handle: d.createPerson})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/grants",
		Summary: "bind a role at the platform, an institution, or the work queue",
		Action:  policy.PlatformAdminister, Resource: atPlatform(), Handle: d.grant})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/organisations/{orgId}",
		Summary: "an institution and its members", Action: policy.OrgRead,
		Resource: fromPath(policy.ResourceOrg, "orgId"), Handle: d.readOrganisation})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/organisations/{orgId}/members",
		Summary: "add a member", Action: policy.OrgAdminister,
		Resource: fromPath(policy.ResourceOrg, "orgId"), Handle: d.addMember})
	rt.register(Route{Method: "DELETE", Pattern: "/api/v1/organisations/{orgId}/members/{principalId}",
		Summary: "remove a member", Action: policy.OrgAdminister,
		Resource: fromPath(policy.ResourceOrg, "orgId"), Handle: d.removeMember})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/organisations/{orgId}/service-principals",
		Summary: "add a worker, edge station, or vehicle", Action: policy.OrgAdminister,
		Resource: fromPath(policy.ResourceOrg, "orgId"), Handle: d.createServicePrincipal})

	// Vehicles. Ours to publish and to grant; what a person brings is
	// autonomy, not a hull.
	rt.register(Route{Method: "POST", Pattern: "/api/v1/vehicles",
		Summary: "publish a vehicle", Action: policy.VehicleCreate,
		Resource: atPlatform(), Handle: d.createVehicle})
	// Listing is the catalogue question, not a question about any one vehicle:
	// anyone signed in may ask it, and the scope the decision point returns is
	// what decides how much of an answer they get.
	rt.register(Route{Method: "GET", Pattern: "/api/v1/vehicles",
		Summary: "the vehicles the caller may fly", Action: policy.PlatformReadCatalogue,
		Resource: atPlatform(), Handle: d.listVehicles})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/vehicles/{vehicleId}",
		Summary: "a vehicle", Action: policy.VehicleRead,
		Resource: fromPath(policy.ResourceVehicle, "vehicleId"), Handle: d.readVehicle})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/vehicles/{vehicleId}/grants",
		Summary: "grant the use of a vehicle", Action: policy.VehicleGrant,
		Resource: fromPath(policy.ResourceVehicle, "vehicleId"), Handle: d.grantVehicle})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/vehicles/{vehicleId}/grants",
		Summary: "who may fly a vehicle", Action: policy.VehicleGrant,
		Resource: fromPath(policy.ResourceVehicle, "vehicleId"), Handle: d.readVehicleGrants})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/vehicles/{vehicleId}/versions",
		Summary: "a vehicle's published packages", Action: policy.VehicleRead,
		Resource: fromPath(policy.ResourceVehicle, "vehicleId"), Handle: d.listVehicleVersions})

	// Capacity.
	rt.register(Route{Method: "PUT", Pattern: "/api/v1/organisations/{orgId}/quota",
		Summary: "state what an institution may consume", Action: policy.PlatformAdminister,
		Resource: atPlatform(), Handle: d.setQuota})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/organisations/{orgId}/quota",
		Summary: "what an institution may consume and what it does", Action: policy.OrgRead,
		Resource: fromPath(policy.ResourceOrg, "orgId"), Handle: d.readQuota})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/targets",
		Summary: "record a place work can run", Action: policy.PlatformAdminister,
		Resource: atPlatform(), Handle: d.registerTarget})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/targets",
		Summary: "places work can run", Action: policy.PlatformAdminister,
		Resource: atPlatform(), Handle: d.listTargets})

	// Places.
	rt.register(Route{Method: "GET", Pattern: "/api/v1/cities",
		Summary: "the places the caller may learn of", Action: policy.PlatformReadCatalogue,
		Resource: atPlatform(), Handle: d.listCities})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/cities",
		Summary: "found a place", Action: policy.CityCreate,
		Resource: atPlatform(), Handle: d.createCity})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/cities/{cityId}",
		Summary: "enter a place", Action: policy.CityRead,
		Resource: fromPath(policy.ResourceCity, "cityId"), Handle: d.readCity})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/cities/{cityId}/versions",
		Summary: "a city's published packages", Action: policy.CityRead,
		Resource: fromPath(policy.ResourceCity, "cityId"), Handle: d.listCityVersions})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/cities/{cityId}/grants",
		Summary: "who has been granted access to a place", Action: policy.CityGrant,
		Resource: fromPath(policy.ResourceCity, "cityId"), Handle: d.readCityGrants})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/cities/{cityId}/grants",
		Summary: "share a place", Action: policy.CityGrant,
		Resource: fromPath(policy.ResourceCity, "cityId"), Handle: d.grantCity})
	rt.register(Route{Method: "DELETE", Pattern: "/api/v1/cities/{cityId}/grants/{bindingId}",
		Summary: "withdraw access to a place", Action: policy.CityGrant,
		Resource: fromPath(policy.ResourceCity, "cityId"), Handle: d.revokeCityGrant})

	// Layers, in a place and in the shared world.

	// Bytes.
	rt.register(Route{Method: "POST", Pattern: "/api/v1/organisations/{orgId}/uploads",
		Summary: "obtain a grant to place bytes in storage", Action: policy.ObjectUpload,
		Resource: fromPath(policy.ResourceOrg, "orgId"), Handle: d.requestUpload})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/organisations/{orgId}/uploads/{grantId}/confirm",
		Summary: "check what arrived against what was declared", Action: policy.ObjectUpload,
		Resource: fromPath(policy.ResourceOrg, "orgId"), Handle: d.confirmUpload})

	// The platform's own recurring work.
	rt.register(Route{Method: "GET", Pattern: "/api/v1/schedules",
		Summary: "the platform's recurring work and when each next runs",
		Action:  policy.ScheduleRead, Resource: atPlatform(), Handle: d.listSchedules})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/schedules",
		Summary: "record recurring work", Action: policy.ScheduleWrite,
		Resource: atPlatform(),
		Also:     []policy.Action{policy.JobSubmitPrivileged},
		Handle:   d.createSchedule})

	// Work.
	rt.register(Route{Method: "POST", Pattern: "/api/v1/organisations/{orgId}/jobs",
		Summary: "ask the platform to run work", Action: policy.JobSubmit,
		Resource: fromPath(policy.ResourceOrg, "orgId"),
		// Work that may reach the network, or that publishes what it produced,
		// needs the authority a person would need to do the same by hand.
		Also:   []policy.Action{policy.JobSubmitPrivileged},
		Handle: d.submitJob})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/organisations/{orgId}/jobs",
		Summary: "an institution's work", Action: policy.JobRead,
		Resource: fromPath(policy.ResourceOrg, "orgId"), Handle: d.listJobs})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/jobs/{jobId}",
		Summary: "one job, its attempts, and what it produced", Action: policy.JobRead,
		Resource: fromPath(policy.ResourceJob, "jobId"), Handle: d.readJob})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/jobs/{jobId}/events",
		Summary: "a job's durable account of itself", Action: policy.JobRead,
		Resource: fromPath(policy.ResourceJob, "jobId"), Handle: d.readJobEvents})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/jobs/{jobId}/cancel",
		Summary: "stop work that has not finished", Action: policy.JobCancel,
		Resource: fromPath(policy.ResourceJob, "jobId"), Handle: d.cancelJob})

	// The worker's half of the lease protocol.
	rt.register(Route{Method: "POST", Pattern: "/api/v1/work/lease",
		Summary: "take one admitted job", Action: policy.WorkLease,
		Resource: atWork(), Handle: d.takeWork})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/work/{attemptId}/heartbeat",
		Summary: "extend a lease and learn whether to stop", Action: policy.WorkLease,
		Resource: atWork(), Handle: d.beat})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/work/{attemptId}/started",
		Summary: "report that the container is running", Action: policy.WorkLease,
		Resource: atWork(), Handle: d.reportStarted})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/work/{attemptId}/progress",
		Summary: "report progress", Action: policy.WorkLease,
		Resource: atWork(), Handle: d.reportProgress})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/work/{attemptId}/outputs",
		Summary: "record one file the work produced", Action: policy.WorkLease,
		Resource: atWork(), Handle: d.recordOutput})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/work/{attemptId}/finish",
		Summary: "report how an attempt ended", Action: policy.WorkLease,
		Resource: atWork(), Handle: d.finish})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/work/{attemptId}/inputs",
		Summary: "read one input of leased work", Action: policy.WorkLease,
		Resource: atWork(), Handle: d.inputURL})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/work/{attemptId}/uploads",
		Summary: "obtain a grant to place one output in storage", Action: policy.WorkLease,
		Resource: atWork(), Handle: d.requestWorkerUpload})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/work/{attemptId}/uploads/{grantId}/confirm",
		Summary: "check one output against what was declared", Action: policy.WorkLease,
		Resource: atWork(), Handle: d.confirmWorkerUpload})

	// A path no route claims. It is registered on the multiplexer rather than
	// as a Route because it grants nothing and performs no action; it only
	// reports absence in the same shape as every other failure.
	rt.mux.HandleFunc("/", rt.notFound)
}

// notFound answers a path no route claims, in the same shape as every other
// failure.
func (rt *Router) notFound(w http.ResponseWriter, r *http.Request) {
	writeProblem(w, r, http.StatusNotFound, "not_found", "there is nothing at that path", nil)
}
