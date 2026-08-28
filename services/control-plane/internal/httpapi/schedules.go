package httpapi

import (
	"net/http"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/exec"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// Recurring work is the platform's own: the daily loop that brings the outside
// world in without anyone asking it to. It is created and read at the platform,
// not by any institution, because no institution owns it.

type scheduleRequest struct {
	Name            string `json:"name"`
	IntervalSeconds int    `json:"intervalSeconds"`
	FirstRunAt      string `json:"firstRunAt,omitempty"`

	OrgID       string        `json:"orgId"`
	RecipeID    string        `json:"recipeId"`
	ImageDigest string        `json:"imageDigest"`
	Command     []string      `json:"command"`
	Args        []string      `json:"args,omitempty"`
	Inputs      []exec.Input  `json:"inputs,omitempty"`
	Outputs     []exec.Output `json:"outputs,omitempty"`

	RequestCPU         float64 `json:"requestCpu"`
	RequestMemoryBytes int64   `json:"requestMemoryBytes"`
	RequestGPU         int     `json:"requestGpu,omitempty"`
	WalltimeSeconds    int     `json:"walltimeSeconds"`

	Egress  string              `json:"egress,omitempty"`
	Publish *publicationRequest `json:"publish,omitempty"`
}

// createSchedule records recurring work, or updates it if the name is known.
func (d *Dependencies) createSchedule(w http.ResponseWriter, r *http.Request) {
	var request scheduleRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	actor, _ := principalOf(r.Context())

	egress, err := exec.ParseEgress(request.Egress)
	if err != nil {
		writeError(w, r, err)
		return
	}
	// Recurring work needs the same authority its jobs would need, asked once
	// here rather than every time it runs with nobody present.
	if egress.Privileged() && !d.permits(w, r, policy.JobSubmitPrivileged, policy.Platform()) {
		return
	}

	firstRunAt := time.Now()
	if request.FirstRunAt != "" {
		parsed, err := time.Parse(time.RFC3339, request.FirstRunAt)
		if err != nil {
			writeProblem(w, r, http.StatusBadRequest, "invalid",
				"firstRunAt is a moment in RFC 3339 form", nil)
			return
		}
		firstRunAt = parsed
	}

	var publish *exec.Publication
	if request.Publish != nil {
		publish = &exec.Publication{
			LayerID:           request.Publish.LayerID,
			DescriptorOutput:  request.Publish.DescriptorOutput,
			Publish:           request.Publish.Publish,
			Promote:           request.Publish.Promote,
			SupersedePrevious: request.Publish.SupersedePrevious,
		}
		if !d.permits(w, r, policy.LayerCreate, policy.Layer(publish.LayerID)) {
			return
		}
		if publish.Publish && !d.permits(w, r, policy.LayerPublish, policy.Layer(publish.LayerID)) {
			return
		}
		if publish.Promote && !d.permits(w, r, policy.LayerPromote, policy.Layer(publish.LayerID)) {
			return
		}
	}

	var schedule exec.Schedule
	err = d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		schedule, err = d.Broker.CreateSchedule(r.Context(), conn, exec.ScheduleSpec{
			Name:            request.Name,
			IntervalSeconds: request.IntervalSeconds,
			FirstRunAt:      firstRunAt,
			Job: exec.JobSpec{
				OrgID:              request.OrgID,
				SubmittedBy:        actor.ID,
				RecipeID:           request.RecipeID,
				ImageDigest:        request.ImageDigest,
				Command:            request.Command,
				Args:               request.Args,
				Inputs:             request.Inputs,
				Outputs:            request.Outputs,
				RequestCPU:         request.RequestCPU,
				RequestMemoryBytes: request.RequestMemoryBytes,
				RequestGPU:         request.RequestGPU,
				WalltimeSeconds:    request.WalltimeSeconds,
				Egress:             egress,
				Publish:            publish,
			},
		})
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: actor.ID, Action: string(policy.ScheduleWrite),
			SubjectKind: "schedule", SubjectID: schedule.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{
				"name": schedule.Name, "intervalSeconds": schedule.IntervalSeconds,
				"recipeId": schedule.RecipeID, "egress": string(schedule.Egress),
				"publishesTo": publishTarget(publish),
			},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, schedule)
}

// listSchedules reports the platform's recurring work and when each next runs.
func (d *Dependencies) listSchedules(w http.ResponseWriter, r *http.Request) {
	schedules, err := d.Broker.Schedules(r.Context())
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"schedules": schedules})
}
