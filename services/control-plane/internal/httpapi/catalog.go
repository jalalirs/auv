package httpapi

import (
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/catalog"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// assetScope converts the decision point's answer into the predicate the
// repository applies. The conversion is mechanical on purpose: deciding in one
// place and applying in another is what lets a listing and a read agree about
// what exists, and any cleverness here would break that.
func assetScope(decided policy.AssetScope) catalog.Scope {
	return catalog.Scope{
		All:                 decided.All,
		BoundIDs:            decided.BoundIDs,
		IncludeDiscoverable: decided.IncludeDiscoverable,
	}
}

// listVehicles lists the vehicles the caller may fly.
//
// Answered by the same decision point as cities, and applied by the same
// predicate, because the two are granted identically and giving them one answer
// is what stops them becoming two.
func (d *Dependencies) listVehicles(w http.ResponseWriter, r *http.Request) {
	subject, _ := subjectOf(r.Context())
	decided, err := d.Authorizer.Assets(r.Context(), subject, policy.ScopeVehicle)
	if err != nil {
		writeError(w, r, err)
		return
	}
	craft, err := d.Catalog.Vehicles(r.Context(), assetScope(decided))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"vehicles": craft})
}

type createVehicleRequest struct {
	Slug         string `json:"slug"`
	Name         string `json:"name"`
	Summary      string `json:"summary"`
	Manufacturer string `json:"manufacturer"`
	Discoverable bool   `json:"discoverable"`
}

// createVehicle publishes a vehicle.
func (d *Dependencies) createVehicle(w http.ResponseWriter, r *http.Request) {
	var request createVehicleRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())

	var created catalog.Vehicle
	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		created, err = d.Catalog.CreateVehicle(r.Context(), conn, catalog.VehicleSpec{
			Slug:         request.Slug,
			Name:         request.Name,
			Summary:      request.Summary,
			Manufacturer: request.Manufacturer,
			Discoverable: request.Discoverable,
			CreatedBy:    principal.ID,
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.VehicleCreate),
			SubjectKind: "vehicle", SubjectID: created.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"slug": created.Slug, "discoverable": created.Discoverable},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, created)
}

// readVehicle reads one vehicle.
func (d *Dependencies) readVehicle(w http.ResponseWriter, r *http.Request) {
	craft, err := d.Catalog.Vehicle(r.Context(), r.PathValue("vehicleId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, craft)
}

// listVehicleVersions lists a vehicle's packages, newest first.
func (d *Dependencies) listVehicleVersions(w http.ResponseWriter, r *http.Request) {
	d.listVersionsOf(w, r, catalog.KindVehicle, r.PathValue("vehicleId"))
}

func (d *Dependencies) listVersionsOf(w http.ResponseWriter, r *http.Request,
	kind catalog.AssetKind, assetID string) {
	versions, err := d.Catalog.Versions(r.Context(), kind, assetID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"versions": versions})
}

// grantVehicle grants the use of a vehicle to a person or an institution.
//
// The same shape as granting a city, deliberately: two assets granted two ways
// would be two things to reason about, and the second one would be the one
// somebody got wrong.
func (d *Dependencies) grantVehicle(w http.ResponseWriter, r *http.Request) {
	var request grantRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())
	vehicleID := r.PathValue("vehicleId")

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
			ScopeKind:   policy.ScopeVehicle,
			ScopeID:     vehicleID,
			Role:        role,
			CreatedBy:   principal.ID,
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.VehicleGrant),
			SubjectKind: "vehicle", SubjectID: vehicleID, Outcome: audit.Succeeded,
			Detail: map[string]any{
				"subjectKind": request.SubjectKind, "subjectId": request.SubjectID,
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

// readVehicleGrants lists who may fly a vehicle.
func (d *Dependencies) readVehicleGrants(w http.ResponseWriter, r *http.Request) {
	bindings, err := d.Authorizer.BindingsAtScope(r.Context(),
		policy.ScopeVehicle, r.PathValue("vehicleId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"grants": bindings})
}
