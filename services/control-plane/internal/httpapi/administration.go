package httpapi

import (
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/exec"
	"github.com/jalalirs/auv/services/control-plane/internal/identity"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

type createOrgRequest struct {
	Slug string `json:"slug"`
	Name string `json:"name"`
}

// createOrganisation founds an institution.
//
// It is created holding contributor at its own scope, so that its members can
// do its work without a separate grant each. Membership on its own grants
// nothing; this binding is what turns membership into authority.
func (d *Dependencies) createOrganisation(w http.ResponseWriter, r *http.Request) {
	var request createOrgRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())

	var org identity.Organisation
	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		org, err = d.Identity.CreateOrganisation(r.Context(), conn, request.Slug, request.Name)
		if err != nil {
			return err
		}
		if _, err := d.Authorizer.Grant(r.Context(), conn, policy.GrantSpec{
			SubjectKind: policy.SubjectOrg, SubjectID: org.ID,
			ScopeKind: policy.ScopeOrg, ScopeID: org.ID,
			Role: policy.RoleContributor, CreatedBy: principal.ID,
		}); err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.PlatformAdminister),
			SubjectKind: "organisation", SubjectID: org.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"slug": org.Slug},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, org)
}

// readOrganisation reports an institution and its members.
func (d *Dependencies) readOrganisation(w http.ResponseWriter, r *http.Request) {
	orgID := r.PathValue("orgId")
	org, err := d.Identity.Organisation(r.Context(), orgID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	members, err := d.Identity.Members(r.Context(), orgID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"organisation": org, "members": members})
}

type createPersonRequest struct {
	DisplayName string `json:"displayName"`
	Email       string `json:"email"`
	Secret      string `json:"secret"`
}

// createPerson adds someone who can sign in.
func (d *Dependencies) createPerson(w http.ResponseWriter, r *http.Request) {
	var request createPersonRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	actor, _ := principalOf(r.Context())

	var person identity.Principal
	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		person, err = d.Identity.CreatePerson(r.Context(), conn, identity.PersonSpec{
			DisplayName: request.DisplayName,
			Email:       request.Email,
			Secret:      request.Secret,
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: actor.ID, Action: string(policy.PlatformAdminister),
			SubjectKind: "principal", SubjectID: person.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"kind": "person"},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, person)
}

type addMemberRequest struct {
	PrincipalID string `json:"principalId"`
}

// addMember records that a person belongs to an institution.
func (d *Dependencies) addMember(w http.ResponseWriter, r *http.Request) {
	var request addMemberRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	actor, _ := principalOf(r.Context())
	orgID := r.PathValue("orgId")

	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		if err := d.Identity.AddMember(r.Context(), conn, orgID, request.PrincipalID); err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: actor.ID, Action: string(policy.OrgAdminister),
			SubjectKind: "organisation", SubjectID: orgID, Outcome: audit.Succeeded,
			Detail: map[string]any{"addedPrincipalId": request.PrincipalID},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// removeMember withdraws a person from an institution.
func (d *Dependencies) removeMember(w http.ResponseWriter, r *http.Request) {
	actor, _ := principalOf(r.Context())
	orgID := r.PathValue("orgId")
	principalID := r.PathValue("principalId")

	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		if err := d.Identity.RemoveMember(r.Context(), conn, orgID, principalID); err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: actor.ID, Action: string(policy.OrgAdminister),
			SubjectKind: "organisation", SubjectID: orgID, Outcome: audit.Succeeded,
			Detail: map[string]any{"removedPrincipalId": principalID},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

type createServicePrincipalRequest struct {
	DisplayName string `json:"displayName"`
}

// createServicePrincipal adds a non-human actor and returns the credential it
// will authenticate with. The credential is shown once and never stored, so it
// cannot be recovered — only replaced.
func (d *Dependencies) createServicePrincipal(w http.ResponseWriter, r *http.Request) {
	var request createServicePrincipalRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	actor, _ := principalOf(r.Context())
	orgID := r.PathValue("orgId")

	var (
		principal  identity.Principal
		credential string
	)
	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		principal, credential, err = d.Identity.CreateServicePrincipal(
			r.Context(), conn, request.DisplayName, orgID)
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: actor.ID, Action: string(policy.OrgAdminister),
			SubjectKind: "principal", SubjectID: principal.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"kind": "service", "orgId": orgID},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, map[string]any{
		"principal":  principal,
		"credential": credential,
		"notice":     "this credential is shown once and is not recoverable",
	})
}

type platformGrantRequest struct {
	SubjectKind string `json:"subjectKind"`
	SubjectID   string `json:"subjectId"`
	ScopeKind   string `json:"scopeKind"`
	ScopeID     string `json:"scopeId,omitempty"`
	Role        string `json:"role"`
}

// grant creates a binding at the platform, an organisation, or the work queue.
// Grants on a city are made by that city's stewards instead.
func (d *Dependencies) grant(w http.ResponseWriter, r *http.Request) {
	var request platformGrantRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	actor, _ := principalOf(r.Context())

	role, err := policy.ParseRole(request.Role)
	if err != nil {
		writeError(w, r, err)
		return
	}

	var binding policy.Binding
	err = d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		binding, err = d.Authorizer.Grant(r.Context(), conn, policy.GrantSpec{
			SubjectKind: policy.SubjectKind(request.SubjectKind),
			SubjectID:   request.SubjectID,
			ScopeKind:   policy.ScopeKind(request.ScopeKind),
			ScopeID:     request.ScopeID,
			Role:        role,
			CreatedBy:   actor.ID,
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: actor.ID, Action: string(policy.PlatformAdminister),
			SubjectKind: "binding", SubjectID: binding.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{
				"subjectKind": request.SubjectKind, "subjectId": request.SubjectID,
				"scopeKind": request.ScopeKind, "scopeId": request.ScopeID,
				"role": string(role),
			},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, binding)
}

type quotaRequest struct {
	MaxConcurrentJobs int     `json:"maxConcurrentJobs"`
	MaxCPU            float64 `json:"maxCpu"`
	MaxMemoryBytes    int64   `json:"maxMemoryBytes"`
	MaxGPU            int     `json:"maxGpu"`
}

// setQuota states what one institution may consume at once.
func (d *Dependencies) setQuota(w http.ResponseWriter, r *http.Request) {
	var request quotaRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	actor, _ := principalOf(r.Context())
	orgID := r.PathValue("orgId")

	var stored exec.Quota
	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		stored, err = d.Broker.SetQuota(r.Context(), conn, exec.Quota{
			OrgID:             orgID,
			MaxConcurrentJobs: request.MaxConcurrentJobs,
			MaxCPU:            request.MaxCPU,
			MaxMemoryBytes:    request.MaxMemoryBytes,
			MaxGPU:            request.MaxGPU,
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: actor.ID, Action: string(policy.PlatformAdminister),
			SubjectKind: "quota", SubjectID: orgID, Outcome: audit.Succeeded,
			Detail: map[string]any{
				"maxConcurrentJobs": stored.MaxConcurrentJobs, "maxCpu": stored.MaxCPU,
				"maxMemoryBytes": stored.MaxMemoryBytes, "maxGpu": stored.MaxGPU,
			},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, stored)
}

type registerTargetRequest struct {
	Name                string  `json:"name"`
	Kind                string  `json:"kind"`
	CapacityCPU         float64 `json:"capacityCpu"`
	CapacityMemoryBytes int64   `json:"capacityMemoryBytes"`
	CapacityGPU         int     `json:"capacityGpu"`
}

// registerTarget records a place work can run.
func (d *Dependencies) registerTarget(w http.ResponseWriter, r *http.Request) {
	var request registerTargetRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	actor, _ := principalOf(r.Context())

	var target exec.Target
	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		target, err = d.Broker.RegisterTarget(r.Context(), conn, exec.TargetSpec{
			Name:                request.Name,
			Kind:                exec.TargetKind(request.Kind),
			CapacityCPU:         request.CapacityCPU,
			CapacityMemoryBytes: request.CapacityMemoryBytes,
			CapacityGPU:         request.CapacityGPU,
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: actor.ID, Action: string(policy.PlatformAdminister),
			SubjectKind: "target", SubjectID: target.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"name": target.Name, "kind": string(target.Kind)},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, target)
}

// listTargets reports every place work can run.
func (d *Dependencies) listTargets(w http.ResponseWriter, r *http.Request) {
	targets, err := d.Broker.Targets(r.Context())
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"targets": targets})
}

// readOwnDenials reports the refusals the caller has received, so that "why
// can I not see this" is answerable from the record rather than from a log.
func (d *Dependencies) readOwnDenials(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalOf(r.Context())
	denials, err := d.Authorizer.DenialsForPrincipal(r.Context(), principal.ID, queryLimit(r, 50, 200))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"denials": denials})
}

// listOrganisations lists every institution on this installation.
func (d *Dependencies) listOrganisations(w http.ResponseWriter, r *http.Request) {
	organisations, err := d.Identity.Organisations(r.Context())
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"organisations": organisations})
}

// listPeople lists everyone who can act.
func (d *Dependencies) listPeople(w http.ResponseWriter, r *http.Request) {
	people, err := d.Identity.People(r.Context())
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"people": people})
}

// revokeAssetGrant withdraws a grant on a place, a vehicle, or a queue.
//
// One path for all three, because a grant is one idea and three ways to take
// one back would be three things to get right.
func (d *Dependencies) revokeAssetGrant(w http.ResponseWriter, r *http.Request,
	action policy.Action, subjectKind, assetID string) {
	principal, _ := principalOf(r.Context())
	bindingID := r.PathValue("bindingId")

	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		if err := d.Authorizer.Revoke(r.Context(), conn, bindingID); err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(action),
			SubjectKind: subjectKind, SubjectID: assetID, Outcome: audit.Succeeded,
			Detail: map[string]any{"revoked": bindingID},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func (d *Dependencies) revokeVehicleGrant(w http.ResponseWriter, r *http.Request) {
	d.revokeAssetGrant(w, r, policy.VehicleGrant, "vehicle", r.PathValue("vehicleId"))
}

func (d *Dependencies) revokeQueueGrant(w http.ResponseWriter, r *http.Request) {
	d.revokeAssetGrant(w, r, policy.QueueGrant, "queue", r.PathValue("queueId"))
}
