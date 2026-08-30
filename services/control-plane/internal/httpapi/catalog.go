package httpapi

import (
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/catalog"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
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

// listCities lists the places the caller may learn of.
//
// A city the caller has not been granted and which is not discoverable does not
// appear, and is not reported as withheld either: the platform does not
// distinguish "does not exist" from "not yours to know about", because the
// difference is itself a disclosure.
func (d *Dependencies) listCities(w http.ResponseWriter, r *http.Request) {
	subject, _ := subjectOf(r.Context())
	decided, err := d.Authorizer.Assets(r.Context(), subject, policy.ScopeCity)
	if err != nil {
		writeError(w, r, err)
		return
	}
	places, err := d.Catalog.Cities(r.Context(), assetScope(decided))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"cities": places})
}

type createCityRequest struct {
	Slug          string         `json:"slug"`
	Name          string         `json:"name"`
	Summary       string         `json:"summary"`
	Extent        *domain.Extent `json:"extent"`
	HorizontalCRS string         `json:"horizontalCrs"`
	VerticalDatum string         `json:"verticalDatum"`
	Discoverable  bool           `json:"discoverable"`
}

// createCity founds a place.
func (d *Dependencies) createCity(w http.ResponseWriter, r *http.Request) {
	var request createCityRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())

	var created catalog.City
	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		created, err = d.Catalog.CreateCity(r.Context(), conn, catalog.CitySpec{
			Slug:          request.Slug,
			Name:          request.Name,
			Summary:       request.Summary,
			Extent:        request.Extent,
			HorizontalCRS: request.HorizontalCRS,
			VerticalDatum: request.VerticalDatum,
			Discoverable:  request.Discoverable,
			CreatedBy:     principal.ID,
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.CityCreate),
			SubjectKind: "city", SubjectID: created.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"slug": created.Slug, "discoverable": created.Discoverable},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, created)
}

// readCity reads one place.
func (d *Dependencies) readCity(w http.ResponseWriter, r *http.Request) {
	place, err := d.Catalog.City(r.Context(), r.PathValue("cityId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, place)
}

// listCityVersions lists a city's packages, newest first.
func (d *Dependencies) listCityVersions(w http.ResponseWriter, r *http.Request) {
	d.listVersionsOf(w, r, catalog.KindCity, r.PathValue("cityId"))
}

// grantCity grants access to a place.
func (d *Dependencies) grantCity(w http.ResponseWriter, r *http.Request) {
	d.grantAsset(w, r, policy.ScopeCity, policy.CityGrant, "city", r.PathValue("cityId"))
}

// readCityGrants lists who has been granted access to a place.
func (d *Dependencies) readCityGrants(w http.ResponseWriter, r *http.Request) {
	bindings, err := d.Authorizer.BindingsAtScope(r.Context(), policy.ScopeCity, r.PathValue("cityId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"grants": bindings})
}

// revokeCityGrant withdraws access to a place.
func (d *Dependencies) revokeCityGrant(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalOf(r.Context())
	bindingID := r.PathValue("bindingId")

	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		if err := d.Authorizer.Revoke(r.Context(), conn, bindingID); err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.CityGrant),
			SubjectKind: "city", SubjectID: r.PathValue("cityId"), Outcome: audit.Succeeded,
			Detail: map[string]any{"revoked": bindingID},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
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

// grantRequest is who is being granted what.
type grantRequest struct {
	SubjectKind string `json:"subjectKind"`
	SubjectID   string `json:"subjectId"`
	Role        string `json:"role"`
}

// grantAsset grants access to a city or a vehicle.
//
// One path for both, deliberately: two assets granted two ways would be two
// things to reason about, and the second one would be the one somebody got
// wrong.
func (d *Dependencies) grantAsset(w http.ResponseWriter, r *http.Request,
	scope policy.ScopeKind, action policy.Action, subjectKind, assetID string) {
	var request grantRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())

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
			ScopeKind:   scope,
			ScopeID:     assetID,
			Role:        role,
			CreatedBy:   principal.ID,
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(action),
			SubjectKind: subjectKind, SubjectID: assetID, Outcome: audit.Succeeded,
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

// grantVehicle grants the use of a vehicle.
func (d *Dependencies) grantVehicle(w http.ResponseWriter, r *http.Request) {
	d.grantAsset(w, r, policy.ScopeVehicle, policy.VehicleGrant, "vehicle",
		r.PathValue("vehicleId"))
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
