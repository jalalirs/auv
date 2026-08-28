package httpapi

import (
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/city"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// catalogue lists the places the caller may learn of.
//
// The predicate comes from the decision point, so a city the caller could not
// enter and is not entitled to know about does not appear here either.
func (d *Dependencies) catalogue(w http.ResponseWriter, r *http.Request) {
	subject, _ := subjectOf(r.Context())
	scope, err := d.Authorizer.Catalogue(r.Context(), subject)
	if err != nil {
		writeError(w, r, err)
		return
	}
	places, err := d.Cities.Catalogue(r.Context(), scope)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"cities": places})
}

type createCityRequest struct {
	Slug            string        `json:"slug"`
	Name            string        `json:"name"`
	Summary         string        `json:"summary"`
	Extent          domain.Extent `json:"extent"`
	CRSEpsg         int           `json:"crsEpsg"`
	VerticalDatum   string        `json:"verticalDatum"`
	Discoverability string        `json:"discoverability"`
}

// createCity founds a place.
func (d *Dependencies) createCity(w http.ResponseWriter, r *http.Request) {
	var request createCityRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())

	discoverability, err := domain.ParseDiscoverability(request.Discoverability)
	if err != nil {
		writeError(w, r, err)
		return
	}

	var created city.City
	err = d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		created, err = d.Cities.Create(r.Context(), conn, city.CreateSpec{
			Slug:            request.Slug,
			Name:            request.Name,
			Summary:         request.Summary,
			Extent:          request.Extent,
			CRS:             domain.CoordinateReference(request.CRSEpsg),
			VerticalDatum:   request.VerticalDatum,
			Discoverability: discoverability,
			CreatedBy:       principal.ID,
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.CityCreate),
			SubjectKind: "city", SubjectID: created.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"slug": created.Slug, "discoverability": created.Discoverability},
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
	place, err := d.Cities.City(r.Context(), r.PathValue("cityId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	decision := decisionOf(r.Context())
	writeJSON(w, r, http.StatusOK, map[string]any{
		"city": place,
		"you":  map[string]any{"role": decision.Role},
	})
}

type updateCityRequest struct {
	Name            *string `json:"name,omitempty"`
	Summary         *string `json:"summary,omitempty"`
	Discoverability *string `json:"discoverability,omitempty"`
}

// updateCity changes a place's description or who may learn of it. Its extent,
// coordinate reference, and vertical datum are what the place is, and are not
// changed here.
func (d *Dependencies) updateCity(w http.ResponseWriter, r *http.Request) {
	var request updateCityRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())
	cityID := r.PathValue("cityId")

	spec := city.UpdateSpec{Name: request.Name, Summary: request.Summary}
	if request.Discoverability != nil {
		discoverability, err := domain.ParseDiscoverability(*request.Discoverability)
		if err != nil {
			writeError(w, r, err)
			return
		}
		spec.Discoverability = &discoverability
	}

	var updated city.City
	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		updated, err = d.Cities.Update(r.Context(), conn, cityID, spec)
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.CityUpdate),
			SubjectKind: "city", SubjectID: cityID, Outcome: audit.Succeeded,
			Detail: map[string]any{"discoverability": updated.Discoverability},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, updated)
}

type grantRequest struct {
	SubjectKind string `json:"subjectKind"`
	SubjectID   string `json:"subjectId"`
	Role        string `json:"role"`
}

// grantCity shares a place with an organisation or a person.
//
// Nothing is copied: a grant is an edge, and revoking it takes effect on the
// next request.
func (d *Dependencies) grantCity(w http.ResponseWriter, r *http.Request) {
	var request grantRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())
	cityID := r.PathValue("cityId")

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
			ScopeKind:   policy.ScopeCity,
			ScopeID:     cityID,
			Role:        role,
			CreatedBy:   principal.ID,
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.CityGrant),
			SubjectKind: "city", SubjectID: cityID, Outcome: audit.Succeeded,
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
	cityID := r.PathValue("cityId")
	bindingID := r.PathValue("bindingId")

	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		if err := d.Authorizer.Revoke(r.Context(), conn, bindingID); err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.CityGrant),
			SubjectKind: "city", SubjectID: cityID, Outcome: audit.Succeeded,
			Detail: map[string]any{"revokedBindingId": bindingID},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}
