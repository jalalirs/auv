package httpapi

import (
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/exec"
	"github.com/jalalirs/auv/services/control-plane/internal/storage"
)

// The work routes are how a worker takes work, reports on it, and hands back
// results. A worker authenticates as a service principal holding authority over
// the work queue and over nothing else, so a compromised worker cannot read a
// city or contribute a layer.

type takeWorkRequest struct {
	TargetName string `json:"targetName"`
}

// takeWork hands one admitted job to a worker, or reports that there is
// nothing to do.
func (d *Dependencies) takeWork(w http.ResponseWriter, r *http.Request) {
	var request takeWorkRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())

	target, err := d.Broker.TargetByName(r.Context(), request.TargetName)
	if err != nil {
		writeError(w, r, err)
		return
	}

	lease, err := d.Broker.Take(r.Context(), principal.ID, target.ID, d.LeaseDuration)
	if err != nil {
		writeError(w, r, err)
		return
	}
	if lease == nil {
		w.WriteHeader(http.StatusNoContent)
		return
	}
	writeJSON(w, r, http.StatusOK, lease)
}

type leaseHeldRequest struct {
	Token string `json:"token"`
}

// beat extends a lease and tells the worker whether it should stop. This is
// also how cancellation reaches work that is already running.
func (d *Dependencies) beat(w http.ResponseWriter, r *http.Request) {
	var request leaseHeldRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	beat, err := d.Broker.Beat(r.Context(), r.PathValue("attemptId"), request.Token, d.LeaseDuration)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, beat)
}

type startedRequest struct {
	Token        string `json:"token"`
	PlacementRef string `json:"placementRef"`
}

// reportStarted records that the container is running, and where.
func (d *Dependencies) reportStarted(w http.ResponseWriter, r *http.Request) {
	var request startedRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	if err := d.Broker.ReportStarted(r.Context(), r.PathValue("attemptId"),
		request.Token, request.PlacementRef); err != nil {
		writeError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

type progressRequest struct {
	Token  string         `json:"token"`
	Detail map[string]any `json:"detail"`
}

// reportProgress adds an entry to a job's account of itself while it runs.
func (d *Dependencies) reportProgress(w http.ResponseWriter, r *http.Request) {
	var request progressRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	if err := d.Broker.ReportProgress(r.Context(), r.PathValue("attemptId"),
		request.Token, request.Detail); err != nil {
		writeError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

type recordOutputRequest struct {
	Token    string `json:"token"`
	Name     string `json:"name"`
	ObjectID string `json:"objectId"`
}

// recordOutput records one file a job produced. An output is recorded once per
// name however many attempts the job took.
func (d *Dependencies) recordOutput(w http.ResponseWriter, r *http.Request) {
	var request recordOutputRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	if err := d.Broker.RecordOutput(r.Context(), r.PathValue("attemptId"),
		request.Token, request.Name, request.ObjectID); err != nil {
		writeError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

type finishRequest struct {
	Token        string `json:"token"`
	Outcome      string `json:"outcome"`
	ExitCode     int    `json:"exitCode"`
	FailureClass string `json:"failureClass"`
}

// finish records how an attempt ended and, with it, how the job ended.
func (d *Dependencies) finish(w http.ResponseWriter, r *http.Request) {
	var request finishRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	failure := exec.FailureClass(request.FailureClass)
	if failure == "" {
		failure = exec.NoFailure
	}
	job, err := d.Broker.Finish(r.Context(), r.PathValue("attemptId"), request.Token,
		exec.JobState(request.Outcome), request.ExitCode, failure)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, job)
}

type namedLeaseRequest struct {
	Token string `json:"token"`
	Name  string `json:"name"`
}

// inputURL issues a short-lived URL for one input of a leased job.
//
// A worker reaches bytes through the lease it holds. It has no authority over
// any organisation, so it cannot read anything it is not currently running.
func (d *Dependencies) inputURL(w http.ResponseWriter, r *http.Request) {
	var request namedLeaseRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	input, err := d.Broker.InputFor(r.Context(), r.PathValue("attemptId"), request.Token, request.Name)
	if err != nil {
		writeError(w, r, err)
		return
	}
	object, err := d.Objects.Object(r.Context(), input.ObjectID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	url, err := d.Objects.ReadURL(r.Context(), object, input.RelativePath, storage.Internal)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"input": input, "readUrl": url})
}

type workerUploadRequest struct {
	Token     string `json:"token"`
	Name      string `json:"name"`
	SHA256    string `json:"sha256"`
	SizeBytes int64  `json:"sizeBytes"`
}

// requestWorkerUpload issues a grant to place one declared output in storage.
//
// The size the job declared bounds what may be uploaded, so output beyond that
// declaration is refused before any bytes move rather than after.
func (d *Dependencies) requestWorkerUpload(w http.ResponseWriter, r *http.Request) {
	var request workerUploadRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())

	declared, err := d.Broker.OutputFor(r.Context(), r.PathValue("attemptId"), request.Token, request.Name)
	if err != nil {
		writeError(w, r, err)
		return
	}
	if request.SizeBytes > declared.MaxSizeBytes {
		writeError(w, r, &exec.OutputTooLarge{
			Name: request.Name, SizeBytes: request.SizeBytes, LimitBytes: declared.MaxSizeBytes,
		})
		return
	}

	digest, err := domain.ParseDigest(request.SHA256)
	if err != nil {
		writeError(w, r, err)
		return
	}
	grant, err := d.Objects.RequestUpload(r.Context(), principal.ID, storage.UploadRequest{
		// Job output is derived material, never evidence: only an observation
		// is evidence, and a job did not observe anything.
		Bucket:    domain.Derived,
		Digest:    digest,
		SizeBytes: request.SizeBytes,
		MediaType: declared.MediaType,
	}, storage.Internal)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, grant)
}

// confirmWorkerUpload verifies a worker's output against what it declared.
func (d *Dependencies) confirmWorkerUpload(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalOf(r.Context())
	object, err := d.Objects.ConfirmUpload(r.Context(), principal.ID, r.PathValue("grantId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, object)
}
