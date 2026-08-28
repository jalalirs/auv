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

// imageDigestPattern requires an image to be pinned by digest. A tag can be
// moved; a digest cannot, and provenance that names a tag proves nothing.
var imageDigestPattern = regexp.MustCompile(`^[a-z0-9.-]+(:[0-9]+)?/?.*@sha256:[0-9a-f]{64}$`)

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
	if !imageDigestPattern.MatchString(j.ImageDigest) {
		return fmt.Errorf("%w: %q is not an image pinned by digest; a tag can be moved and proves nothing",
			domain.ErrInvalid, j.ImageDigest)
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
	return nil
}
