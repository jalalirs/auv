package main

import (
	"testing"

	"github.com/jalalirs/auv/services/worker/internal/controlplane"
)

// While work on a GPU runs, the host says it has that much less, so the
// platform does not place a dive on what the work is using.
func TestAHostRunningWorkOnAGPUSaysItHasLess(t *testing.T) {
	host := controlplane.Capacity{CPU: 32, MemoryBytes: 128 << 30}
	if got := less(host, nil); got != host {
		t.Fatalf("an idle host said %+v", got)
	}
	got := less(host, &controlplane.Job{RequestCPU: 8, RequestMemoryBytes: 48 << 30, RequestGPU: 1})
	if got.CPU != 24 || got.MemoryBytes != 80<<30 {
		t.Fatalf("a host running a reconstruction said %+v", got)
	}
	if got := less(controlplane.Capacity{CPU: 4, MemoryBytes: 16 << 30},
		&controlplane.Job{RequestCPU: 8, RequestMemoryBytes: 48 << 30}); got.CPU <= 0 || got.MemoryBytes <= 0 {
		t.Fatalf("a host smaller than its work said %+v, which the platform ignores", got)
	}
}
