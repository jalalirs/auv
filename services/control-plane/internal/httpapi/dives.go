package httpapi

import (
	"encoding/json"
	"net/http"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/dive"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// ── Autonomy ─────────────────────────────────────────────────────────────────

type registerStackRequest struct {
	Slug            string          `json:"slug"`
	Name            string          `json:"name"`
	ImageRepository string          `json:"imageRepository"`
	ImageDigest     string          `json:"imageDigest"`
	Subscribes      json.RawMessage `json:"subscribes,omitempty"`
	Publishes       json.RawMessage `json:"publishes,omitempty"`
	WantsGPU        bool            `json:"wantsGpu"`
}

// registerStack records autonomy somebody brought.
//
// The image is pinned by digest and a tag is refused, because a dive re-run
// against a tag that has moved is measuring a different program while reporting
// it as the same one.
func (d *Dependencies) registerStack(w http.ResponseWriter, r *http.Request) {
	var request registerStackRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())
	orgID := r.PathValue("orgId")

	var created dive.AutonomyStack
	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		created, err = d.Dives.CreateStack(r.Context(), conn, dive.StackSpec{
			OrgID:           orgID,
			Slug:            request.Slug,
			Name:            request.Name,
			ImageRepository: request.ImageRepository,
			ImageDigest:     request.ImageDigest,
			Subscribes:      request.Subscribes,
			Publishes:       request.Publishes,
			WantsGPU:        request.WantsGPU,
			CreatedBy:       principal.ID,
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.DiveWrite),
			SubjectKind: "autonomy", SubjectID: created.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"slug": created.Slug, "image": created.ImageRepository},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, created)
}

// listStacks lists an institution's autonomy.
func (d *Dependencies) listStacks(w http.ResponseWriter, r *http.Request) {
	stacks, err := d.Dives.Stacks(r.Context(), r.PathValue("orgId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"autonomy": stacks})
}

// ── Conditions ───────────────────────────────────────────────────────────────

type createConditionsRequest struct {
	Kind       string          `json:"kind"`
	Name       string          `json:"name"`
	ObservedAt *time.Time      `json:"observedAt,omitempty"`
	Sources    json.RawMessage `json:"sources,omitempty"`
	Parameters json.RawMessage `json:"parameters,omitempty"`
}

// createConditions records the water a dive happens in.
//
// Observed conditions must name the instant they are drawn from and constructed
// conditions must not, because the difference between water that was measured
// and water that was invented is the platform's most important claim about a
// result and nothing should be able to blur it by omission.
func (d *Dependencies) createConditions(w http.ResponseWriter, r *http.Request) {
	var request createConditionsRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())
	orgID := r.PathValue("orgId")

	kind, err := dive.ParseConditionsKind(request.Kind)
	if err != nil {
		writeError(w, r, err)
		return
	}

	var created dive.Conditions
	err = d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		created, err = d.Dives.CreateConditions(r.Context(), conn, dive.ConditionsSpec{
			Kind:       kind,
			Name:       request.Name,
			ObservedAt: request.ObservedAt,
			Sources:    request.Sources,
			Parameters: request.Parameters,
			OrgID:      &orgID,
			CreatedBy:  principal.ID,
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.DiveWrite),
			SubjectKind: "conditions", SubjectID: created.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"kind": string(created.Kind), "name": created.Name},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, created)
}

// ── Dives ────────────────────────────────────────────────────────────────────

type createDiveRequest struct {
	Name             string          `json:"name"`
	Summary          string          `json:"summary"`
	CityVersionID    string          `json:"cityVersionId"`
	VehicleVersionID string          `json:"vehicleVersionId"`
	ConditionsID     string          `json:"conditionsId"`
	AutonomyStackID  *string         `json:"autonomyStackId,omitempty"`
	InitialState     json.RawMessage `json:"initialState,omitempty"`
	Objective        json.RawMessage `json:"objective,omitempty"`
}

// createDive defines a dive.
//
// It names versions rather than assets, so that publishing a newer vehicle does
// not silently turn somebody's experiment into a different one.
func (d *Dependencies) createDive(w http.ResponseWriter, r *http.Request) {
	var request createDiveRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())
	orgID := r.PathValue("orgId")

	var created dive.Dive
	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		created, err = d.Dives.CreateDive(r.Context(), conn, dive.DiveSpec{
			OrgID:            orgID,
			Name:             request.Name,
			Summary:          request.Summary,
			CityVersionID:    request.CityVersionID,
			VehicleVersionID: request.VehicleVersionID,
			ConditionsID:     request.ConditionsID,
			AutonomyStackID:  request.AutonomyStackID,
			InitialState:     request.InitialState,
			Objective:        request.Objective,
			CreatedBy:        principal.ID,
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.DiveWrite),
			SubjectKind: "dive", SubjectID: created.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"name": created.Name},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, created)
}

// listDives lists an institution's dives.
func (d *Dependencies) listDives(w http.ResponseWriter, r *http.Request) {
	dives, err := d.Dives.Dives(r.Context(), r.PathValue("orgId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"dives": dives})
}

// readDive reads one dive.
func (d *Dependencies) readDive(w http.ResponseWriter, r *http.Request) {
	plan, err := d.Dives.Dive(r.Context(), r.PathValue("diveId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, plan)
}

// ── Runs ─────────────────────────────────────────────────────────────────────

type requestRunRequest struct {
	QueueID        string   `json:"queueId"`
	Mode           string   `json:"mode"`
	Seed           *int64   `json:"seed,omitempty"`
	RuntimeVersion string   `json:"runtimeVersion"`
	GPUShare       *float64 `json:"gpuShare,omitempty"`
}

// requestRun asks for a dive to be executed.
//
// Every determinant is copied from the dive as the run is admitted — the city
// and vehicle digests, the conditions, the autonomy image, the seed and the
// runtime version — so that editing the dive afterwards cannot change what a
// recorded result means. Supplying a seed asks for an earlier run again,
// exactly; leaving it out draws one.
func (d *Dependencies) requestRun(w http.ResponseWriter, r *http.Request) {
	var request requestRunRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())

	mode, err := dive.ParseMode(request.Mode)
	if err != nil {
		writeError(w, r, err)
		return
	}

	// Using a queue is granted separately from defining a dive: composing an
	// experiment costs nothing, and running one holds a GPU.
	if !d.permits(w, r, policy.QueueRead, policy.Resource{
		Kind: policy.ResourceQueue, ID: request.QueueID}) {
		return
	}

	var share float64
	if request.GPUShare != nil {
		share = *request.GPUShare
	}

	var run dive.Run
	err = d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		run, err = d.Dives.RequestRun(r.Context(), conn, dive.RunSpec{
			DiveID:         r.PathValue("diveId"),
			QueueID:        request.QueueID,
			Mode:           mode,
			Seed:           request.Seed,
			RuntimeVersion: request.RuntimeVersion,
			GPUShare:       share,
			RequestedBy:    principal.ID,
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.RunRequest),
			SubjectKind: "run", SubjectID: run.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{
				"diveId": run.DiveID, "queueId": run.QueueID,
				"mode": string(run.Mode), "seed": run.Seed,
				"runtimeVersion": run.RuntimeVersion,
			},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusAccepted, run)
}

// listRuns lists a dive's executions, newest first.
func (d *Dependencies) listRuns(w http.ResponseWriter, r *http.Request) {
	runs, err := d.Dives.Runs(r.Context(), r.PathValue("diveId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"runs": runs})
}
