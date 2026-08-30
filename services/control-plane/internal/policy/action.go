package policy

import "fmt"

// Action names something a principal may attempt. Every route declares the
// action it performs, and the route-table test refuses a route that declares
// an action this file does not define.
type Action string

const (
	// PlatformAdminister covers creating organisations and platform bindings.
	PlatformAdminister Action = "platform.administer"
	// PlatformReadCatalogue covers listing the cities and vehicles a subject
	// may learn of.
	PlatformReadCatalogue Action = "platform.read_catalogue"
	// SelfRead covers reading one's own identity and memberships.
	SelfRead Action = "self.read"
	// SelfEndSession covers ending one's own sign-in.
	SelfEndSession Action = "self.end_session"

	// OrgRead covers reading an organisation and its members.
	OrgRead Action = "org.read"
	// OrgAdminister covers membership, quota, and service principals.
	OrgAdminister Action = "org.administer"

	// CityCreate covers founding a place.
	CityCreate Action = "city.create"
	// CityRead covers entering a place and reading its description.
	CityRead Action = "city.read"
	// CityGrant covers granting or revoking access to a place.
	CityGrant Action = "city.grant"

	// VehicleCreate covers publishing a vehicle. Vehicles are ours, so this
	// sits at the platform: what a person brings is autonomy, not a hull.
	VehicleCreate Action = "vehicle.create"
	// VehicleRead covers reading a vehicle and how it moves.
	VehicleRead Action = "vehicle.read"
	// VehicleGrant covers granting or revoking the use of a vehicle.
	VehicleGrant Action = "vehicle.grant"

	// ObjectUpload covers obtaining a grant to place bytes in storage.
	ObjectUpload Action = "object.upload"

	// JobSubmit covers asking the platform to run work.
	JobSubmit Action = "job.submit"
	// JobSubmitPrivileged covers submitting work that may reach the network.
	// The sandbox exists so that an organisation's container cannot; granting
	// an exception is a platform decision (ADR-0012).
	JobSubmitPrivileged Action = "job.submit_privileged"
	// JobRead covers reading a job, its attempts, and its events.
	JobRead Action = "job.read"
	// JobCancel covers stopping work that is running.
	JobCancel Action = "job.cancel"

	// ScheduleRead covers reading the platform's recurring work.
	ScheduleRead Action = "schedule.read"
	// ScheduleWrite covers creating or changing it.
	ScheduleWrite Action = "schedule.write"

	// WorkLease covers a service principal taking work from the queue.
	WorkLease Action = "work.lease"
)

// requirement states the authority an action needs and the kinds of resource
// it may be attempted upon. The scope at which authority is measured comes
// from the resource itself, not from this table, so one action can govern both
// a platform-scoped and a city-scoped layer.
//
// Actions absent from this table cannot be authorised at all, which is how a
// typo becomes a refusal rather than an opening.
var requirement = map[Action]struct {
	Role Role
	On   []ResourceKind
}{
	PlatformAdminister:    {RoleAdmin, []ResourceKind{ResourcePlatform}},
	PlatformReadCatalogue: {RoleAnyone, []ResourceKind{ResourcePlatform}},
	SelfRead:              {RoleAnyone, []ResourceKind{ResourcePlatform}},
	SelfEndSession:        {RoleAnyone, []ResourceKind{ResourcePlatform}},

	OrgRead:       {RoleViewer, []ResourceKind{ResourceOrg}},
	OrgAdminister: {RoleAdmin, []ResourceKind{ResourceOrg}},

	CityCreate: {RoleAdmin, []ResourceKind{ResourcePlatform}},
	CityRead:   {RoleViewer, []ResourceKind{ResourceCity}},
	CityGrant:  {RoleSteward, []ResourceKind{ResourceCity}},

	VehicleCreate: {RoleAdmin, []ResourceKind{ResourcePlatform}},
	VehicleRead:   {RoleViewer, []ResourceKind{ResourceVehicle, ResourcePlatform}},
	VehicleGrant:  {RoleSteward, []ResourceKind{ResourceVehicle}},

	ObjectUpload: {RoleContributor, []ResourceKind{ResourceOrg}},

	JobSubmit:           {RoleContributor, []ResourceKind{ResourceOrg}},
	JobSubmitPrivileged: {RoleAdmin, []ResourceKind{ResourcePlatform}},
	JobRead:             {RoleViewer, []ResourceKind{ResourceJob, ResourceOrg}},
	JobCancel:           {RoleContributor, []ResourceKind{ResourceJob}},

	ScheduleRead:  {RoleViewer, []ResourceKind{ResourcePlatform}},
	ScheduleWrite: {RoleAdmin, []ResourceKind{ResourcePlatform}},

	WorkLease: {RoleAdmin, []ResourceKind{ResourceWork}},
}

// Requires reports the role an action needs and the resource kinds it applies
// to.
func Requires(action Action) (Role, []ResourceKind, error) {
	need, known := requirement[action]
	if !known {
		return "", nil, fmt.Errorf("action %q has no stated requirement and cannot be authorised", action)
	}
	return need.Role, need.On, nil
}

// AppliesTo reports whether an action may be attempted upon a resource kind.
func AppliesTo(action Action, kind ResourceKind) bool {
	need, known := requirement[action]
	if !known {
		return false
	}
	for _, allowed := range need.On {
		if allowed == kind {
			return true
		}
	}
	return false
}

// Actions returns every action the platform defines, so that tests can assert
// the route table covers them and declares nothing else.
func Actions() []Action {
	all := make([]Action, 0, len(requirement))
	for action := range requirement {
		all = append(all, action)
	}
	return all
}
