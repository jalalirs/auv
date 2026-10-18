package runner

import (
	"slices"
	"strings"
	"testing"

	"github.com/jalalirs/auv/services/worker/internal/container"
)

// Work that needs no card is given none, whatever the host offers.
func TestWorkThatNeedsNoGPUIsGivenNone(t *testing.T) {
	gpus, err := devicesFor(0, []string{"1"})
	if err != nil || gpus != nil {
		t.Fatalf("devicesFor(0) = %v, %v", gpus, err)
	}
}

// A job that needs a card and cannot have one fails, and says where the cards
// are named, rather than running on the processor for days.
func TestWorkThatNeedsAGPUIsRefusedWithoutOne(t *testing.T) {
	if _, err := devicesFor(1, nil); err == nil || !strings.Contains(err.Error(), "IOCEAN_WORKER_JOB_GPUS") {
		t.Fatalf("a GPU job on a host offering none: %v", err)
	}
	if _, err := devicesFor(2, []string{"1"}); err == nil {
		t.Fatal("a job needing two cards was given one")
	}
	gpus, err := devicesFor(1, []string{"1", "2"})
	if err != nil || !slices.Equal(gpus, []string{"1"}) {
		t.Fatalf("devicesFor(1, [1 2]) = %v, %v", gpus, err)
	}
}

// Work on a GPU gets its cards, the shared memory and threads it needs, and
// scratch on the host's disk that is not among its outputs.
func TestWorkOnAGPUGetsWhatItNeeds(t *testing.T) {
	spec := container.Spec{Env: []string{"IOCEAN_JOB_ID=job_1"}}
	onGPU(&spec, []string{"1"}, "/srv/work/att_1/scratch")
	if !slices.Equal(spec.GPUs, []string{"1"}) || spec.ShmBytes != 16<<30 || spec.PidsLimit <= 512 {
		t.Fatalf("%+v", spec)
	}
	if len(spec.Mounts) != 1 || spec.Mounts[0].Target != Scratch || spec.Mounts[0].ReadOnly ||
		strings.Contains(spec.Mounts[0].Source, "outputs") {
		t.Fatalf("scratch: %+v", spec.Mounts)
	}
	if !slices.Contains(spec.Env, "IOCEAN_JOB_SCRATCH="+Scratch) || !slices.Contains(spec.Env, "TMPDIR="+Scratch) ||
		!slices.Contains(spec.Env, "IOCEAN_JOB_ID=job_1") {
		t.Fatalf("env: %v", spec.Env)
	}
}
