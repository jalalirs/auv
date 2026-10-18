package httpapi

import (
	"errors"
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/mapping"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// startMapping asks for a reconstruction to be put onto a place: one that
// exists, which the caller must be able to make versions of, or one of its
// own, founded for the reconstruction's organisation.
func (d *Dependencies) startMapping(w http.ResponseWriter, r *http.Request) {
	var request mapping.Request
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	request.StartAssumed = false
	if request.Mode == mapping.Onto {
		if request.CityID == "" {
			writeError(w, r, errors.Join(domain.ErrInvalid, errors.New("name the place to put the reef onto (cityId)")))
			return
		}
		// Laying a reef in makes a version of the place, so the caller must
		// be one who may.
		if !d.permits(w, r, policy.CityPublish, policy.City(request.CityID)) {
			return
		}
	}
	principal, _ := principalOf(r.Context())
	made, err := d.Mapper.Start(r.Context(), principal.ID, r.PathValue("reconstructionId"), request)
	if errors.Is(err, mapping.ErrNotConfigured) {
		writeProblem(w, r, http.StatusServiceUnavailable, "not_configured", err.Error(), nil)
		return
	}
	if err != nil {
		writeError(w, r, err)
		return
	}
	if err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.CityFound),
			SubjectKind: "mapping", SubjectID: made.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"reconstructionId": made.ReconstructionID, "cityId": made.CityID,
				"mode": made.Mode, "orgId": made.OrgID},
		})
	}); err != nil {
		writeError(w, r, err)
		return
	}
	view, err := d.Mapper.Watch(r.Context(), made.ID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, view)
}

// acceptMapping chooses where a reef goes, from what the search found or by
// hand, and starts laying it in.
func (d *Dependencies) acceptMapping(w http.ResponseWriter, r *http.Request) {
	var choice mapping.Choice
	if err := readJSON(r, &choice); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())
	made, err := d.Mapper.Accept(r.Context(), r.PathValue("mappingId"), choice)
	if err != nil {
		writeError(w, r, err)
		return
	}
	if err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.CityFound),
			SubjectKind: "mapping", SubjectID: made.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"chosen": made.Chosen, "layJobId": made.LayJobID},
		})
	}); err != nil {
		writeError(w, r, err)
		return
	}
	view, err := d.Mapper.Watch(r.Context(), made.ID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, view)
}

// watchMapping says how a mapping is going.
func (d *Dependencies) watchMapping(w http.ResponseWriter, r *http.Request) {
	view, err := d.Mapper.Watch(r.Context(), r.PathValue("mappingId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, view)
}

// listMappings lists a reconstruction's mappings, newest first.
func (d *Dependencies) listMappings(w http.ResponseWriter, r *http.Request) {
	all, err := d.Mapper.Of(r.Context(), r.PathValue("reconstructionId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	views := make([]mapping.View, 0, len(all))
	for _, one := range all {
		view, err := d.Mapper.Watch(r.Context(), one.ID)
		if err != nil {
			writeError(w, r, err)
			return
		}
		views = append(views, view)
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"mappings": views})
}

// ofMapping names the organisation a mapping belongs to.
func (d *Dependencies) ofMapping(segment string) ResourceOf {
	return func(r *http.Request) (policy.Resource, error) {
		org, err := d.Mapper.OrgOf(r.Context(), r.PathValue(segment))
		if err != nil {
			return policy.Resource{}, err
		}
		return policy.Org(org), nil
	}
}
