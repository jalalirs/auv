package httpapi

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/dive"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
	"github.com/jalalirs/auv/services/control-plane/internal/storage"
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

// ── What an agent does ───────────────────────────────────────────────────────

// claimRun hands an agent the next dive its host can run, and a device to run
// it on.
//
// Answers 204 when there is nothing to do, which is the ordinary case: an agent
// asks constantly and mostly there is no work, and treating that as an error
// would fill the log with the platform working correctly.
func (d *Dependencies) claimRun(w http.ResponseWriter, r *http.Request) {
	var request struct {
		TargetID string `json:"targetId"`
	}
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}

	var claimed dive.Claimed
	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		claimed, err = d.Dives.ClaimNext(r.Context(), conn, request.TargetID, d.LeaseDuration)
		if err != nil {
			return err
		}
		return d.Dives.Record(r.Context(), conn, claimed.Run.ID, "claimed", nil,
			json.RawMessage(fmt.Sprintf(
				`{"target":%q,"device":%q,"rosDomainId":%d}`,
				request.TargetID, claimed.DeviceUUID, claimed.ROSDomainID)))
	})
	if errors.Is(err, db.ErrNotFound) {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, claimed)
}

// runStarted records that the simulator is up.
func (d *Dependencies) runStarted(w http.ResponseWriter, r *http.Request) {
	runID := r.PathValue("runId")
	if err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		if err := d.Dives.Started(r.Context(), conn, runID); err != nil {
			return err
		}
		return d.Dives.Record(r.Context(), conn, runID, "started", nil, nil)
	}); err != nil {
		writeError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// renewRun extends the lease on a run still under way.
//
// An agent that stops saying this loses the device, which is the only way to
// tell an agent that is slow from one that is gone.
func (d *Dependencies) renewRun(w http.ResponseWriter, r *http.Request) {
	if err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		return d.Dives.Renew(r.Context(), conn, r.PathValue("runId"), d.LeaseDuration)
	}); err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{
		"leaseSeconds": int(d.LeaseDuration.Seconds()),
	})
}

// recordRunEvent appends to what happened during a run.
func (d *Dependencies) recordRunEvent(w http.ResponseWriter, r *http.Request) {
	var request struct {
		Kind             string          `json:"kind"`
		SimulatedSeconds *float64        `json:"simulatedSeconds,omitempty"`
		Detail           json.RawMessage `json:"detail,omitempty"`
	}
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	if err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		return d.Dives.Record(r.Context(), conn, r.PathValue("runId"),
			request.Kind, request.SimulatedSeconds, request.Detail)
	}); err != nil {
		writeError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// finishRun ends a run, and the record refuses to rewrite it afterwards.
func (d *Dependencies) finishRun(w http.ResponseWriter, r *http.Request) {
	var request struct {
		State         string          `json:"state"`
		Outcome       json.RawMessage `json:"outcome,omitempty"`
		FailureReason string          `json:"failureReason,omitempty"`
	}
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	runID := r.PathValue("runId")

	if err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		if err := d.Dives.Finish(r.Context(), conn, runID,
			dive.State(request.State), request.Outcome, request.FailureReason); err != nil {
			return err
		}
		return d.Dives.Record(r.Context(), conn, runID, "finished", nil,
			json.RawMessage(fmt.Sprintf(`{"state":%q}`, request.State)))
	}); err != nil {
		writeError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// runPackages lists the files of the packages a run needs.
//
// Scoped to the run rather than to the catalogue. An agent holds authority over
// work and over nothing else — it cannot read a place or a vehicle — so asking
// it to fetch a package by naming one would have meant widening what an agent
// may see to everything the platform publishes. Asking through the run it holds
// widens nothing: it can fetch the two packages that dive needs and no others.
func (d *Dependencies) runPackages(w http.ResponseWriter, r *http.Request) {
	runID := r.PathValue("runId")

	var cityVersion, vehicleVersion string
	if err := d.Pool.QueryRow(r.Context(), `
		SELECT d.city_version_id, d.vehicle_version_id
		  FROM dive.run r JOIN dive.dive d ON d.id = r.dive_id
		 WHERE r.id = $1 AND r.state IN ('preparing', 'running')`,
		runID).Scan(&cityVersion, &vehicleVersion); err != nil {
		writeError(w, r, db.Translate(err))
		return
	}

	answer := map[string]any{}
	for name, versionID := range map[string]string{
		"city": cityVersion, "vehicle": vehicleVersion,
	} {
		files, err := d.Catalog.Files(r.Context(), versionID)
		if err != nil {
			writeError(w, r, err)
			return
		}
		fetchable := make([]map[string]any, 0, len(files))
		for _, file := range files {
			object, err := d.Objects.Object(r.Context(), file.ObjectID)
			if err != nil {
				writeError(w, r, err)
				return
			}
			// Signed for a node on the network rather than a browser on
			// somebody's desk: the same URL signed over the wrong host verifies
			// and cannot be reached.
			url, err := d.Objects.ReadURL(r.Context(), object, file.Path, storage.Internal)
			if err != nil {
				writeError(w, r, err)
				return
			}
			fetchable = append(fetchable, map[string]any{
				"path": file.Path, "digest": file.Digest.String(),
				"sizeBytes": file.SizeBytes, "mediaType": file.MediaType, "url": url,
			})
		}
		answer[name] = map[string]any{"versionId": versionID, "files": fetchable}
	}
	writeJSON(w, r, http.StatusOK, answer)
}

// listRunEvents lists what happened during a run, in order.
//
// The whole of it rather than a page: a dive of a few minutes produces tens of
// events, not thousands, because telemetry is emitted on simulated time and a
// run that recorded every physics step would be recording the integrator
// rather than the dive.
func (d *Dependencies) listRunEvents(w http.ResponseWriter, r *http.Request) {
	rows, err := d.Pool.Query(r.Context(), `
		SELECT id, occurred_at, simulated_seconds, kind, detail
		  FROM dive.run_event WHERE run_id = $1 ORDER BY id`, r.PathValue("runId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	defer rows.Close()

	type event struct {
		ID               int64           `json:"id"`
		OccurredAt       time.Time       `json:"occurredAt"`
		SimulatedSeconds *float64        `json:"simulatedSeconds,omitempty"`
		Kind             string          `json:"kind"`
		Detail           json.RawMessage `json:"detail"`
	}
	events := []event{}
	for rows.Next() {
		var one event
		if err := rows.Scan(&one.ID, &one.OccurredAt, &one.SimulatedSeconds,
			&one.Kind, &one.Detail); err != nil {
			writeError(w, r, err)
			return
		}
		events = append(events, one)
	}
	if err := rows.Err(); err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"events": events})
}
