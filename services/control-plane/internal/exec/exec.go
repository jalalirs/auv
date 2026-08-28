// Package exec owns work.
//
// A job is one finite containerised execution. A placement of that job onto a
// target is an attempt; retries create attempts rather than new jobs, so the
// record of what produced a result stays singular. The control plane never
// runs scientific work itself: it admits work, records what happened, and lets
// workers lease it.
package exec

import (
	"fmt"
	"regexp"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/domain"
)

// TargetKind names a place work can run. Adapters are added without changing
// the job model, which is the point of the abstraction.
type TargetKind string

const (
	LocalDocker TargetKind = "local_docker"
	Kubernetes  TargetKind = "kubernetes"
	Slurm       TargetKind = "slurm"
)

// Target is a place work can run, with the capacity it advertises.
type Target struct {
	ID                  string     `json:"id"`
	Name                string     `json:"name"`
	Kind                TargetKind `json:"kind"`
	Enabled             bool       `json:"enabled"`
	CapacityCPU         float64    `json:"capacityCpu"`
	CapacityMemoryBytes int64      `json:"capacityMemoryBytes"`
	CapacityGPU         int        `json:"capacityGpu"`
	CreatedAt           time.Time  `json:"createdAt"`
}

// Quota bounds what one organisation may consume at once. Compute is governed
// the same way data is: through the decision point, then against a stated
// limit.
type Quota struct {
	OrgID             string    `json:"orgId"`
	MaxConcurrentJobs int       `json:"maxConcurrentJobs"`
	MaxCPU            float64   `json:"maxCpu"`
	MaxMemoryBytes    int64     `json:"maxMemoryBytes"`
	MaxGPU            int       `json:"maxGpu"`
	UpdatedAt         time.Time `json:"updatedAt"`
}

// JobState is where a job sits in its life.
type JobState string

const (
	Pending   JobState = "pending"
	Admitted  JobState = "admitted"
	Running   JobState = "running"
	Succeeded JobState = "succeeded"
	Failed    JobState = "failed"
	Cancelled JobState = "cancelled"
	Evicted   JobState = "evicted"
	TimedOut  JobState = "timed_out"
)

// IsTerminal reports whether a job has finished, however it finished.
func (s JobState) IsTerminal() bool {
	switch s {
	case Succeeded, Failed, Cancelled, Evicted, TimedOut:
		return true
	}
	return false
}

// FailureClass says why work ended badly, in terms a caller can act on.
type FailureClass string

const (
	NoFailure           FailureClass = "none"
	ImageUnavailable    FailureClass = "image_unavailable"
	InputUnavailable    FailureClass = "input_unavailable"
	OutputLimitExceeded FailureClass = "output_limit_exceeded"
	NonzeroExit         FailureClass = "nonzero_exit"
	WalltimeExceeded    FailureClass = "walltime_exceeded"
	WorkerLost          FailureClass = "worker_lost"
	CancelledByCaller   FailureClass = "cancelled_by_caller"
	InternalError       FailureClass = "internal_error"
)

// EventKind names something that happened to a job.
type EventKind string

const (
	EventAdmitted       EventKind = "admitted"
	EventScheduled      EventKind = "scheduled"
	EventStarted        EventKind = "started"
	EventProgress       EventKind = "progress"
	EventOutputReceived EventKind = "output_received"
	EventSucceeded      EventKind = "succeeded"
	EventFailed         EventKind = "failed"
	EventCancelled      EventKind = "cancelled"
	EventEvicted        EventKind = "evicted"
	EventTimedOut       EventKind = "timed_out"
)

// Input is one file a job reads, named by the object holding it. Inputs are
// addressed by content, so a job cannot silently read different bytes than the
// ones its provenance names.
type Input struct {
	Name         string `json:"name"`
	RelativePath string `json:"relativePath"`
	ObjectID     string `json:"objectId"`
	SHA256       string `json:"sha256"`
	MediaType    string `json:"mediaType"`
	SizeBytes    int64  `json:"sizeBytes"`
}

// Output is one file a job is expected to produce, with the size beyond which
// it will be refused.
type Output struct {
	Name         string `json:"name"`
	RelativePath string `json:"relativePath"`
	MediaType    string `json:"mediaType"`
	MaxSizeBytes int64  `json:"maxSizeBytes"`
}

// Job is one finite containerised execution.
type Job struct {
	ID          string   `json:"id"`
	OrgID       string   `json:"orgId"`
	SubmittedBy string   `json:"submittedBy"`
	RecipeID    string   `json:"recipeId"`
	ImageDigest string   `json:"imageDigest"`
	Command     []string `json:"command"`
	Args        []string `json:"args"`
	Inputs      []Input  `json:"inputs"`
	Outputs     []Output `json:"outputs"`

	RequestCPU         float64 `json:"requestCpu"`
	RequestMemoryBytes int64   `json:"requestMemoryBytes"`
	RequestGPU         int     `json:"requestGpu"`
	WalltimeSeconds    int     `json:"walltimeSeconds"`

	Egress       Egress       `json:"egress"`
	TargetID     string       `json:"targetId,omitempty"`
	State        JobState     `json:"state"`
	FailureClass FailureClass `json:"failureClass"`
	CreatedAt    time.Time    `json:"createdAt"`
	TerminalAt   *time.Time   `json:"terminalAt,omitempty"`
}

// Attempt is one placement of a job onto a target.
type Attempt struct {
	ID             string       `json:"id"`
	JobID          string       `json:"jobId"`
	Ordinal        int          `json:"ordinal"`
	TargetID       string       `json:"targetId"`
	WorkerID       string       `json:"workerId"`
	State          string       `json:"state"`
	LeaseExpiresAt time.Time    `json:"leaseExpiresAt"`
	PlacementRef   string       `json:"placementRef,omitempty"`
	ExitCode       *int         `json:"exitCode,omitempty"`
	FailureClass   FailureClass `json:"failureClass"`
	LeasedAt       time.Time    `json:"leasedAt"`
	StartedAt      *time.Time   `json:"startedAt,omitempty"`
	FinishedAt     *time.Time   `json:"finishedAt,omitempty"`
}

// Event is one entry in a job's durable, ordered account of itself.
type Event struct {
	ID         string         `json:"id"`
	JobID      string         `json:"jobId"`
	AttemptID  string         `json:"attemptId,omitempty"`
	Sequence   int64          `json:"sequence"`
	OccurredAt time.Time      `json:"occurredAt"`
	Kind       EventKind      `json:"kind"`
	Detail     map[string]any `json:"detail"`
}

// Egress says whether a job's container may reach the network.
//
// It is a capability, not a setting: `none` is what every organisation's work
// gets, and `internet` is granted only to a job whose submitter holds authority
// at the platform. See ADR-0012, which also records that it is all or nothing.
type Egress string

const (
	// NoEgress gives the container no network at all.
	NoEgress Egress = "none"
	// InternetEgress gives it ordinary outbound networking.
	InternetEgress Egress = "internet"
)

// ParseEgress validates an egress capability.
func ParseEgress(value string) (Egress, error) {
	switch Egress(value) {
	case NoEgress, InternetEgress:
		return Egress(value), nil
	case "":
		return NoEgress, nil
	}
	return "", fmt.Errorf("%w: egress is none or internet, not %q", domain.ErrInvalid, value)
}

// Privileged reports whether this capability may only be granted by an
// administrator of the platform.
func (e Egress) Privileged() bool { return e != NoEgress }

// An image must be named by a content address, because a tag can be moved and
// provenance that names one proves nothing. Two forms are content addresses:
//
//   - a registry digest, `repository@sha256:…`, which the worker pulls;
//   - a bare `sha256:…`, the identity of an image already on the host, which
//     the worker verifies is present rather than fetching.
//
// The second exists because this platform's own images are built elsewhere and
// streamed to hosts that cannot reach a registry. Neither can be moved.
var (
	registryDigestPattern = regexp.MustCompile(`^[a-z0-9.-]+(:[0-9]+)?/?.*@sha256:[0-9a-f]{64}$`)
	localImagePattern     = regexp.MustCompile(`^sha256:[0-9a-f]{64}$`)
)

// IsContentAddressed reports whether an image reference names exactly one image.
func IsContentAddressed(image string) bool {
	return registryDigestPattern.MatchString(image) || localImagePattern.MatchString(image)
}

// Publication is what a job's result becomes.
//
// It is declared when the job is submitted and cannot change, so a job cannot
// decide to publish something it was not asked to publish. See ADR-0013.
type Publication struct {
	// LayerID is the layer the result belongs to.
	LayerID string `json:"layerId"`
	// DescriptorOutput names the declared output whose content states what the
	// version is. Every other declared output becomes the version's payload.
	DescriptorOutput string `json:"descriptorOutput"`
	// Publish moves the version out of draft on success.
	Publish bool `json:"publish"`
	// Promote makes it part of the shared record, which still requires the
	// submitter to hold steward authority in the scope.
	Promote bool `json:"promote"`
	// SupersedePrevious marks the layer's current published version superseded,
	// which is what makes a recurring ingestion a chain rather than a pile.
	SupersedePrevious bool `json:"supersedePrevious"`

	// VersionID is set once the platform has materialised the version.
	VersionID string `json:"versionId,omitempty"`
}

// Validate reports whether the declaration is expressible.
func (p Publication) Validate(outputs []Output) error {
	if p.LayerID == "" {
		return fmt.Errorf("%w: a publication names the layer it belongs to", domain.ErrInvalid)
	}
	if p.DescriptorOutput == "" {
		return fmt.Errorf("%w: a publication names the output that describes it", domain.ErrInvalid)
	}
	if p.Promote && !p.Publish {
		return fmt.Errorf("%w: a version cannot become part of the shared record without being published",
			domain.ErrInvalid)
	}

	var described, payload int
	for _, output := range outputs {
		if output.Name == p.DescriptorOutput {
			described++
			continue
		}
		payload++
	}
	if described == 0 {
		return fmt.Errorf("%w: this job declares no output named %q to describe its result",
			domain.ErrInvalid, p.DescriptorOutput)
	}
	if payload == 0 {
		return fmt.Errorf("%w: a version has at least one file, and every declared output but %q is its payload",
			domain.ErrInvalid, p.DescriptorOutput)
	}
	return nil
}

// JobSpec describes work to run.
type JobSpec struct {
	OrgID       string
	SubmittedBy string
	RecipeID    string
	ImageDigest string
	Command     []string
	Args        []string
	Inputs      []Input
	Outputs     []Output

	RequestCPU         float64
	RequestMemoryBytes int64
	RequestGPU         int
	WalltimeSeconds    int

	// Egress is refused unless the submitter holds authority at the platform.
	Egress Egress
	// Publish, when set, is what this job's result becomes.
	Publish *Publication
}

// Validate reports whether the work is fully and safely described.
func (j JobSpec) Validate() error {
	if j.OrgID == "" {
		return fmt.Errorf("%w: work belongs to an organisation", domain.ErrInvalid)
	}
	if strings.TrimSpace(j.RecipeID) == "" {
		return fmt.Errorf("%w: work names the recipe that produced its specification",
			domain.ErrInvalid)
	}
	if !IsContentAddressed(j.ImageDigest) {
		return fmt.Errorf(
			"%w: %q does not name exactly one image; use repository@sha256:… or sha256:… , because a tag can be moved and proves nothing",
			domain.ErrInvalid, j.ImageDigest)
	}
	if _, err := ParseEgress(string(j.Egress)); err != nil {
		return err
	}
	if len(j.Command) == 0 {
		return fmt.Errorf("%w: work runs a command", domain.ErrInvalid)
	}
	if j.RequestCPU <= 0 || j.RequestMemoryBytes <= 0 {
		return fmt.Errorf("%w: work requests processor and memory", domain.ErrInvalid)
	}
	if j.RequestGPU < 0 {
		return fmt.Errorf("%w: a request for %d accelerators is not a request", domain.ErrInvalid, j.RequestGPU)
	}
	if j.WalltimeSeconds <= 0 {
		return fmt.Errorf("%w: work states the time after which it should be stopped",
			domain.ErrInvalid)
	}

	seenInput := map[string]struct{}{}
	for _, input := range j.Inputs {
		if input.Name == "" || input.ObjectID == "" {
			return fmt.Errorf("%w: an input names itself and the object holding it", domain.ErrInvalid)
		}
		if _, duplicate := seenInput[input.Name]; duplicate {
			return fmt.Errorf("%w: two inputs are both named %q", domain.ErrInvalid, input.Name)
		}
		seenInput[input.Name] = struct{}{}
		if err := domain.ValidateRelativePath(input.RelativePath); err != nil {
			return err
		}
	}

	seenOutput := map[string]struct{}{}
	for _, output := range j.Outputs {
		if output.Name == "" {
			return fmt.Errorf("%w: an output names itself", domain.ErrInvalid)
		}
		if _, duplicate := seenOutput[output.Name]; duplicate {
			return fmt.Errorf("%w: two outputs are both named %q", domain.ErrInvalid, output.Name)
		}
		seenOutput[output.Name] = struct{}{}
		if err := domain.ValidateRelativePath(output.RelativePath); err != nil {
			return err
		}
		if output.MaxSizeBytes <= 0 {
			return fmt.Errorf("%w: output %q states the size beyond which it is refused",
				domain.ErrInvalid, output.Name)
		}
		if output.MediaType == "" {
			return fmt.Errorf("%w: output %q states its media type", domain.ErrInvalid, output.Name)
		}
	}

	if j.Publish != nil {
		if err := j.Publish.Validate(j.Outputs); err != nil {
			return err
		}
	}
	return nil
}
