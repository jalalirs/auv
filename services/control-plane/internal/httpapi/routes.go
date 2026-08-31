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
	rt.register(Route{Method: "GET", Pattern: "/api/v1/organisations",
		Summary: "every institution on this installation", Action: policy.PlatformAdminister,
		Resource: atPlatform(), Handle: d.listOrganisations})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/people",
		Summary: "everyone who can act", Action: policy.PlatformAdminister,
		Resource: atPlatform(), Handle: d.listPeople})
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
	rt.register(Route{Method: "DELETE", Pattern: "/api/v1/vehicles/{vehicleId}/grants/{bindingId}",
		Summary: "withdraw the use of a vehicle", Action: policy.VehicleGrant,
		Resource: fromPath(policy.ResourceVehicle, "vehicleId"), Handle: d.revokeVehicleGrant})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/vehicles/{vehicleId}/grants",
		Summary: "who may fly a vehicle", Action: policy.VehicleGrant,
		Resource: fromPath(policy.ResourceVehicle, "vehicleId"), Handle: d.readVehicleGrants})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/vehicles/{vehicleId}/versions",
		Summary: "a vehicle's packages", Action: policy.VehicleRead,
		Resource: fromPath(policy.ResourceVehicle, "vehicleId"), Handle: d.listVehicleVersions})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/vehicles/{vehicleId}/versions",
		Summary: "record a package for a vehicle", Action: policy.VehicleCreate,
		Resource: atPlatform(), Handle: d.createVehicleVersion})
	// A vehicle must state how it moves before anything may fly it, so this is
	// refused once the version is published rather than discovered by a dive
	// that has already claimed a GPU.
	rt.register(Route{Method: "PUT", Pattern: "/api/v1/versions/{versionId}/dynamics",
		Summary: "state how a vehicle version moves", Action: policy.VehicleCreate,
		Resource: atPlatform(), Handle: d.setDynamics})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/versions/{versionId}/files",
		Summary: "a package's files, each with a short-lived URL to fetch it",
		Action:  policy.PlatformReadCatalogue, Resource: atPlatform(),
		Handle: d.listVersionFiles})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/versions/{versionId}/publish",
		Summary: "make a package pinnable, and from then on unchangeable",
		Action:  policy.CityCreate, Resource: atPlatform(), Handle: d.publishVersion})

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
		Summary: "a city's packages", Action: policy.CityRead,
		Resource: fromPath(policy.ResourceCity, "cityId"), Handle: d.listCityVersions})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/cities/{cityId}/versions",
		Summary: "record a package for a city", Action: policy.CityCreate,
		Resource: atPlatform(), Handle: d.createCityVersion})
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

	// Queues. The governed resource is the queue, not the device: a queue holds
	// however many devices it holds, so adding hardware is an insert rather
	// than a migration.
	rt.register(Route{Method: "POST", Pattern: "/api/v1/queues",
		Summary: "open a queue", Action: policy.QueueOpen,
		Resource: atPlatform(), Handle: d.createQueue})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/queues",
		Summary: "the queues the caller may submit to", Action: policy.PlatformReadCatalogue,
		Resource: atPlatform(), Handle: d.listQueues})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/queues/{queueId}",
		Summary: "a queue and how much of it is free", Action: policy.QueueRead,
		Resource: fromPath(policy.ResourceQueue, "queueId"), Handle: d.readQueue})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/queues/{queueId}/devices",
		Summary: "place a device in a queue", Action: policy.QueueOpen,
		Resource: atPlatform(), Handle: d.addDevice})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/queues/{queueId}/devices",
		Summary: "the devices in a queue", Action: policy.QueueRead,
		Resource: fromPath(policy.ResourceQueue, "queueId"), Handle: d.listDevices})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/queues/{queueId}/grants",
		Summary: "grant the use of a queue", Action: policy.QueueGrant,
		Resource: fromPath(policy.ResourceQueue, "queueId"), Handle: d.grantQueue})
	rt.register(Route{Method: "DELETE", Pattern: "/api/v1/queues/{queueId}/grants/{bindingId}",
		Summary: "withdraw the use of a queue", Action: policy.QueueGrant,
		Resource: fromPath(policy.ResourceQueue, "queueId"), Handle: d.revokeQueueGrant})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/queues/{queueId}/grants",
		Summary: "who may submit to a queue", Action: policy.QueueGrant,
		Resource: fromPath(policy.ResourceQueue, "queueId"), Handle: d.readQueueGrants})

	// What an institution composes for itself: the autonomy it brings, the
	// water it chooses, and the dives it assembles from those and what the
	// platform publishes.
	rt.register(Route{Method: "POST", Pattern: "/api/v1/organisations/{orgId}/autonomy",
		Summary: "register autonomy, pinned by image digest", Action: policy.DiveWrite,
		Resource: fromPath(policy.ResourceOrg, "orgId"), Handle: d.registerStack})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/organisations/{orgId}/autonomy",
		Summary: "an institution's autonomy", Action: policy.DiveRead,
		Resource: fromPath(policy.ResourceOrg, "orgId"), Handle: d.listStacks})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/organisations/{orgId}/conditions",
		Summary: "record water, observed or constructed", Action: policy.DiveWrite,
		Resource: fromPath(policy.ResourceOrg, "orgId"), Handle: d.createConditions})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/organisations/{orgId}/dives",
		Summary: "define a dive", Action: policy.DiveWrite,
		Resource: fromPath(policy.ResourceOrg, "orgId"), Handle: d.createDive})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/organisations/{orgId}/dives",
		Summary: "an institution's dives", Action: policy.DiveRead,
		Resource: fromPath(policy.ResourceOrg, "orgId"), Handle: d.listDives})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/dives/{diveId}",
		Summary: "a dive", Action: policy.DiveRead,
		Resource: fromPath(policy.ResourceDive, "diveId"), Handle: d.readDive})

	// Running one is granted apart from defining one: composing an experiment
	// costs nothing, and executing it holds a GPU. The route asks about the
	// dive; the handler asks the same decision point about the queue.
	rt.register(Route{Method: "POST", Pattern: "/api/v1/dives/{diveId}/runs",
		Summary: "ask for a dive to be executed", Action: policy.RunRequest,
		Resource: fromPath(policy.ResourceDive, "diveId"),
		Also:     []policy.Action{policy.QueueRead},
		Handle:   d.requestRun})
	// Under the dive, because a run's events belong to it: the authority to
	// read them is the authority to read the experiment they came from, and
	// there is no such thing as authority over a run on its own.
	rt.register(Route{Method: "GET", Pattern: "/api/v1/dives/{diveId}/runs/{runId}/events",
		Summary: "what happened during a run, in order", Action: policy.DiveRead,
		Resource: fromPath(policy.ResourceDive, "diveId"), Handle: d.listRunEvents})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/dives/{diveId}/runs",
		Summary: "what a dive's executions did", Action: policy.DiveRead,
		Resource: fromPath(policy.ResourceDive, "diveId"), Handle: d.listRuns})
	// Ending a dive is asking for one, backwards: it is the same authority,
	// because somebody who may take a machine may give it back. Without this
	// there is no way to hand a GPU back at all — a request could be made and
	// never withdrawn, and every one of them held a device until its lease ran
	// out, whether or not anybody was still there.
	rt.register(Route{Method: "POST", Pattern: "/api/v1/dives/{diveId}/runs/{runId}/cancel",
		Summary: "end a dive, or withdraw a request for one", Action: policy.RunRequest,
		Resource: fromPath(policy.ResourceDive, "diveId"), Handle: d.cancelRun})

	// What an agent does. These sit at the work scope rather than the dive's,
	// because an agent holds authority over running work and over nothing else:
	// it may take the next dive and say what happened to it, and it may not
	// read the institution that asked for it.
	rt.register(Route{Method: "POST", Pattern: "/api/v1/runs/claim",
		Summary: "take the next dive this host can run", Action: policy.WorkClaim,
		Resource: atWork(), Handle: d.claimRun})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/runs/{runId}/packages",
		Summary: "the files of the packages this run needs", Action: policy.WorkReport,
		Resource: atWork(), Handle: d.runPackages})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/runs/{runId}/started",
		Summary: "the simulator is up", Action: policy.WorkReport,
		Resource: atWork(), Handle: d.runStarted})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/runs/{runId}/renew",
		Summary: "still working; hold the device a while longer",
		Action:  policy.WorkReport, Resource: atWork(), Handle: d.renewRun})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/runs/{runId}/events",
		Summary: "what happened during a run", Action: policy.WorkReport,
		Resource: atWork(), Handle: d.recordRunEvent})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/runs/{runId}/finished",
		Summary: "how a run ended", Action: policy.WorkReport,
		Resource: atWork(), Handle: d.finishRun})

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
