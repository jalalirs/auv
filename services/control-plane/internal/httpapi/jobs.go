package httpapi

import (
	"net/http"
	"strconv"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/exec"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

type publicationRequest struct {
	LayerID           string `json:"layerId"`
	DescriptorOutput  string `json:"descriptorOutput"`
	Publish           bool   `json:"publish"`
	Promote           bool   `json:"promote"`
	SupersedePrevious bool   `json:"supersedePrevious"`
}

type submitJobRequest struct {
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

// submitJob asks the platform to run work.
//
// The decision point has already settled whether the caller may submit for this
// organisation. What happens here is the broker deciding whether there is room,
// and recording either answer.
func (d *Dependencies) submitJob(w http.ResponseWriter, r *http.Request) {
	var request submitJobRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())

	egress, err := exec.ParseEgress(request.Egress)
	if err != nil {
		writeError(w, r, err)
		return
	}
	// Reaching the network is a capability, not a setting. The sandbox is what
	// makes an organisation's container safe to run, so an exception to it is
	// the platform's decision and nobody else's.
	if egress.Privileged() && !d.permits(w, r, policy.JobSubmitPrivileged, policy.Platform()) {
		return
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
		// What the result becomes needs the authority it would need if a person
		// did it by hand, checked now rather than when the job finishes and
		// nobody is present to be told.
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

	// The institution the work belongs to is the one in the path, which the
	// decision point has already confirmed the caller may act for. Taking it
	// from the body instead would let a caller name a different one.
	job, err := d.Broker.Submit(r.Context(), exec.JobSpec{
		OrgID:              r.PathValue("orgId"),
		SubmittedBy:        principal.ID,
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
	})
	if err != nil {
		writeError(w, r, err)
		return
	}

	if err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.JobSubmit),
			SubjectKind: "job", SubjectID: job.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{
				"recipeId": job.RecipeID, "imageDigest": job.ImageDigest,
				"targetId": job.TargetID, "egress": string(job.Egress),
				"publishesTo": publishTarget(publish),
			},
		})
	}); err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusAccepted, job)
}

// listJobs lists an organisation's work.
func (d *Dependencies) listJobs(w http.ResponseWriter, r *http.Request) {
	jobs, err := d.Broker.JobsForOrg(r.Context(), r.PathValue("orgId"), queryLimit(r, 50, 200))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"jobs": jobs})
}

// readJob reports a job together with every placement of it and what it
// produced, which is what shows that a retry happened and what came of it.
func (d *Dependencies) readJob(w http.ResponseWriter, r *http.Request) {
	jobID := r.PathValue("jobId")
	job, err := d.Broker.Job(r.Context(), jobID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	attempts, err := d.Broker.Attempts(r.Context(), jobID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	outputs, err := d.Broker.Outputs(r.Context(), jobID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{
		"job": job, "attempts": attempts, "outputs": outputs,
	})
}

// readJobEvents reports a job's durable account of itself from a point in the
// stream, which is how a client resumes watching without missing or repeating
// anything.
func (d *Dependencies) readJobEvents(w http.ResponseWriter, r *http.Request) {
	after := int64(0)
	if raw := r.URL.Query().Get("after"); raw != "" {
		parsed, err := strconv.ParseInt(raw, 10, 64)
		if err != nil || parsed < 0 {
			writeProblem(w, r, http.StatusBadRequest, "invalid",
				"after is the sequence number to resume from", nil)
			return
		}
		after = parsed
	}
	events, err := d.Broker.Events(r.Context(), r.PathValue("jobId"), after, queryLimit(r, 200, 1000))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"events": events})
}

// cancelJob stops work that has not finished.
func (d *Dependencies) cancelJob(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalOf(r.Context())
	jobID := r.PathValue("jobId")

	job, err := d.Broker.Cancel(r.Context(), jobID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	if err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.JobCancel),
			SubjectKind: "job", SubjectID: jobID, Outcome: audit.Succeeded,
		})
	}); err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, job)
}

// readQuota reports what an organisation may consume and what it currently
// does, so that a refusal is understandable before it happens.
func (d *Dependencies) readQuota(w http.ResponseWriter, r *http.Request) {
	quota, inUse, err := d.Broker.Quota(r.Context(), r.PathValue("orgId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"quota": quota, "inUse": inUse})
}

func publishTarget(publication *exec.Publication) any {
	if publication == nil {
		return nil
	}
	return publication.LayerID
}

func queryLimit(r *http.Request, fallback, max int) int {
	raw := r.URL.Query().Get("limit")
	if raw == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(raw)
	if err != nil || parsed <= 0 {
		return fallback
	}
	if parsed > max {
		return max
	}
	return parsed
}
