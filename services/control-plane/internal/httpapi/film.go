package httpapi

import (
	"encoding/json"
	"errors"
	"fmt"
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/dive"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// ReplayFile is the one file of a run its film is handed: every tick's command,
// as the runtime recorded it.
const ReplayFile = "commands.npy"

type filmRunRequest struct {
	// Where to run it; the original run's queue when left out.
	QueueID string `json:"queueId,omitempty"`
	// How to render it: {fps, width, height, spp, bitrate}, as a dive's
	// objective takes it.
	Film json.RawMessage `json:"film,omitempty"`
	// The views to take the camera through, and how long in each.
	Views      []string `json:"views,omitempty"`
	ViewEveryS float64  `json:"viewEveryS,omitempty"`
}

// filmRun asks for the path-traced film of a run that has been flown.
//
// A film cannot be rendered while somebody flies — a path-traced frame takes
// seconds — and a person at the keys or a stack over ROS 2 cannot be asked to
// fly the same dive twice. What they commanded can be: the runtime keeps every
// tick's command, and a dive given them plays them back instead of asking
// anybody. The same seed and the same commands are the same dive.
//
// So the film is a new dive whose every determinant is copied here, from the
// record, rather than taken from the request — the place and vehicle versions,
// the water, the arrangement, the starting state, what was asked for — with
// pictures on, no controller, and `replayOf` naming the run. It is run on the
// original's seed and runtime. Nothing in the request can point it at a run of
// another institution: the run named is the one in the path, under a dive the
// caller may run.
func (d *Dependencies) filmRun(w http.ResponseWriter, r *http.Request) {
	var request filmRunRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())
	diveID, runID := r.PathValue("diveId"), r.PathValue("runId")

	original, err := d.Dives.Run(r.Context(), runID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	if original.DiveID != diveID {
		writeError(w, r, fmt.Errorf("%w: run %s is not a run of dive %s", db.ErrNotFound, runID, diveID))
		return
	}
	if original.State != dive.Succeeded {
		writeError(w, r, fmt.Errorf("%w: run %s is %s; only a run that finished can be filmed",
			domain.ErrInvalid, runID, original.State))
		return
	}
	var recorded bool
	if err := d.Pool.QueryRow(r.Context(),
		`SELECT EXISTS (SELECT 1 FROM dive.artefact WHERE run_id = $1 AND path = $2)`,
		runID, ReplayFile).Scan(&recorded); err != nil {
		writeError(w, r, db.Translate(err))
		return
	}
	if !recorded {
		writeError(w, r, fmt.Errorf("%w: run %s kept no %s — it was flown before the runtime recorded "+
			"its commands, so it cannot be flown again exactly", domain.ErrInvalid, runID, ReplayFile))
		return
	}
	plan, err := d.Dives.Dive(r.Context(), diveID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	// Defining a dive is granted apart from running one, and this does both.
	if !d.permits(w, r, policy.DiveWrite, policy.Resource{Kind: policy.ResourceOrg, ID: plan.OrgID}) {
		return
	}
	queue := request.QueueID
	if queue == "" {
		queue = original.QueueID
	}
	if !d.permits(w, r, policy.QueueRead, policy.Resource{Kind: policy.ResourceQueue, ID: queue}) {
		return
	}

	overlay := map[string]any{"pictures": true, "replayOf": runID}
	if len(request.Film) > 0 {
		overlay["film"] = request.Film
	} else {
		overlay["film"] = map[string]any{"fps": 24, "width": 1280, "height": 720, "spp": 16, "bitrate": "10M"}
	}
	if len(request.Views) > 0 {
		overlay["views"] = request.Views
		every := request.ViewEveryS
		if every <= 0 {
			every = 6
		}
		overlay["viewEveryS"] = every
	}
	laid, err := json.Marshal(overlay)
	if err != nil {
		writeError(w, r, err)
		return
	}

	seed := original.Seed
	var created dive.Dive
	var run dive.Run
	err = d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		created, err = d.Dives.CreateDive(r.Context(), conn, dive.DiveSpec{
			OrgID:            plan.OrgID,
			Name:             "film of " + plan.Name,
			Summary:          fmt.Sprintf("the path-traced film of run %s, flown again from its commands", runID),
			CityVersionID:    plan.CityVersionID,
			LayoutVersionID:  plan.LayoutVersionID,
			LayoutChanges:    plan.LayoutChanges,
			VehicleVersionID: plan.VehicleVersionID,
			ConditionsID:     plan.ConditionsID,
			InitialState:     plan.InitialState,
			// Already composed from its mission when that dive was defined;
			// naming the mission again would compose it afresh.
			Objective:        plan.Objective,
			ObjectiveOverlay: laid,
			CreatedBy:        principal.ID,
		})
		if err != nil {
			return err
		}
		run, err = d.Dives.RequestRun(r.Context(), conn, dive.RunSpec{
			DiveID:         created.ID,
			QueueID:        queue,
			Mode:           dive.Batch,
			Seed:           &seed,
			RuntimeVersion: original.RuntimeVersion,
			RequestedBy:    principal.ID,
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.RunRequest),
			SubjectKind: "run", SubjectID: run.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"diveId": created.ID, "filmOf": runID, "seed": seed},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusAccepted, map[string]any{"dive": created, "run": run, "filmOf": runID})
}

// replayFor is the recorded commands a run is to play back, when its dive is
// the film of another run: that run's commands.npy, and only when both dives
// belong to the same institution. A dive's objective is whatever its author
// wrote, so `replayOf` is checked here, where the file is handed over, and not
// trusted because filmRun wrote it.
func (d *Dependencies) replayFor(r *http.Request, runID string) (objectID string, ok bool, err error) {
	err = d.Pool.QueryRow(r.Context(), `
		SELECT a.object_id
		  FROM dive.run r
		  JOIN dive.dive d ON d.id = r.dive_id
		  JOIN dive.run o ON o.id = d.objective ->> 'replayOf'
		  JOIN dive.dive od ON od.id = o.dive_id AND od.org_id = d.org_id
		  JOIN dive.artefact a ON a.run_id = o.id AND a.path = $2
		 WHERE r.id = $1`, runID, ReplayFile).Scan(&objectID)
	if err != nil {
		if errors.Is(db.Translate(err), db.ErrNotFound) {
			return "", false, nil
		}
		return "", false, db.Translate(err)
	}
	return objectID, true, nil
}
