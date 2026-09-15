package httpapi

import (
	"encoding/json"
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/dive"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// Sweeps — a mission against everything nobody can promise about it.
//
// Asking for one is asking for a hundred dives at once, so it is authorised as
// running dives is: composing an experiment costs nothing and running one holds
// a machine, and a sweep holds a machine ninety times over.

type createSweepRequest struct {
	Name             string          `json:"name"`
	MissionVersionID string          `json:"missionVersionId"`
	VehicleVersionID string          `json:"vehicleVersionId"`
	Water            json.RawMessage `json:"water,omitempty"`
	Doubts           json.RawMessage `json:"doubts"`
	Good             *float64        `json:"good,omitempty"`
	QueueID          string          `json:"queueId"`
	RuntimeVersion   string          `json:"runtimeVersion"`
}

// createSweep records a sweep and asks for every scenario in it.
func (d *Dependencies) createSweep(w http.ResponseWriter, r *http.Request) {
	var request createSweepRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())

	// Using a queue is granted separately from composing: a sweep asks for as
	// many machines as it has scenarios.
	if !d.permits(w, r, policy.QueueRead, policy.Resource{
		Kind: policy.ResourceQueue, ID: request.QueueID}) {
		return
	}

	good := 0.8
	if request.Good != nil {
		good = *request.Good
	}
	var made dive.Sweep
	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		made, err = d.Dives.CreateSweep(r.Context(), conn, dive.SweepSpec{
			OrgID:            r.PathValue("orgId"),
			MissionVersionID: request.MissionVersionID,
			VehicleVersionID: request.VehicleVersionID,
			Water:            request.Water,
			Name:             request.Name,
			Doubts:           request.Doubts,
			Good:             good,
			QueueID:          request.QueueID,
			RuntimeVersion:   request.RuntimeVersion,
			CreatedBy:        principal.ID,
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.RunRequest),
			SubjectKind: "sweep", SubjectID: made.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"name": made.Name, "scenarios": made.Scenarios},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, made)
}

// listSweeps gives an institution's sweeps, newest first.
func (d *Dependencies) listSweeps(w http.ResponseWriter, r *http.Request) {
	found, err := d.Dives.Sweeps(r.Context(), r.PathValue("orgId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"sweeps": found})
}

// readSweep gives one.
func (d *Dependencies) readSweep(w http.ResponseWriter, r *http.Request) {
	found, err := d.Dives.Sweep(r.Context(), r.PathValue("sweepId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, found)
}

// sweepFindings is the point of the whole thing: what breaks the mission, and
// what would fix it.
//
// Computed on asking rather than stored, because it is a reading of the runs
// and the runs are the record. A sweep half flown gives the answer so far,
// which is worth having at two in the morning.
func (d *Dependencies) sweepFindings(w http.ResponseWriter, r *http.Request) {
	found, err := d.Dives.Findings(r.Context(), r.PathValue("sweepId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, found)
}

// registerSweeps declares the routes a sweep needs.
func (rt *Router) registerSweeps() {
	d := rt.deps
	rt.register(Route{Method: "POST", Pattern: "/api/v1/organisations/{orgId}/sweeps",
		Summary: "fly a mission against everything that could go wrong with it",
		Action:  policy.RunRequest,
		Resource: fromPath(policy.ResourceOrganisation, "orgId"), Handle: d.createSweep})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/organisations/{orgId}/sweeps",
		Summary: "what has been swept", Action: policy.DiveRead,
		Resource: fromPath(policy.ResourceOrganisation, "orgId"), Handle: d.listSweeps})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/sweeps/{sweepId}",
		Summary: "one sweep", Action: policy.DiveRead,
		Resource: atPlatform(), Handle: d.readSweep})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/sweeps/{sweepId}/findings",
		Summary: "what breaks this mission, and what would fix it",
		Action:  policy.DiveRead,
		Resource: atPlatform(), Handle: d.sweepFindings})
}
