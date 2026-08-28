package exec

import (
	"errors"
	"strings"
	"testing"

	"github.com/jalalirs/auv/services/control-plane/internal/domain"
)

const pinned = "ghcr.io/example/reconstruct@sha256:" +
	"0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

func validSpec() JobSpec {
	return JobSpec{
		OrgID:              "org_1",
		SubmittedBy:        "prin_1",
		RecipeID:           "reconstruct@2.1.0",
		ImageDigest:        pinned,
		Command:            []string{"/usr/local/bin/reconstruct"},
		RequestCPU:         2,
		RequestMemoryBytes: 4 << 30,
		WalltimeSeconds:    600,
	}
}

// An image named by a tag proves nothing about what will run, because a tag can
// be moved after the fact. Provenance that cannot be relied on is worse than
// none, so work pinned by tag is refused.
func TestWorkMustBePinnedByDigest(t *testing.T) {
	refused := []string{
		"alpine:latest",
		"alpine",
		"ghcr.io/example/reconstruct:2.1.0",
		"ghcr.io/example/reconstruct@sha256:tooshort",
		"",
	}
	for _, image := range refused {
		spec := validSpec()
		spec.ImageDigest = image
		if err := spec.Validate(); err == nil {
			t.Errorf("work naming image %q was accepted", image)
		}
	}

	for _, image := range []string{
		pinned,
		"alpine@sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
		"registry.example.org:5000/team/tool@sha256:" + strings.Repeat("a", 64),
	} {
		spec := validSpec()
		spec.ImageDigest = image
		if err := spec.Validate(); err != nil {
			t.Errorf("work naming image %q was refused: %v", image, err)
		}
	}
}

func TestWorkMustBeFullyDescribed(t *testing.T) {
	cases := []struct {
		name   string
		change func(*JobSpec)
	}{
		{"work belongs to an institution", func(s *JobSpec) { s.OrgID = "" }},
		{"work names its recipe", func(s *JobSpec) { s.RecipeID = "" }},
		{"work runs a command", func(s *JobSpec) { s.Command = nil }},
		{"work requests processor", func(s *JobSpec) { s.RequestCPU = 0 }},
		{"work requests memory", func(s *JobSpec) { s.RequestMemoryBytes = 0 }},
		{"work states a deadline", func(s *JobSpec) { s.WalltimeSeconds = 0 }},
	}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			spec := validSpec()
			test.change(&spec)
			if err := spec.Validate(); !errors.Is(err, domain.ErrInvalid) {
				t.Fatalf("Validate() error = %v, want ErrInvalid", err)
			}
		})
	}
}

// An output with no stated size limit is an unbounded write into shared
// storage, so it is refused before anything runs.
func TestAnOutputStatesItsLimitAndItsType(t *testing.T) {
	spec := validSpec()
	spec.Outputs = []Output{{Name: "mesh", RelativePath: "mesh.glb", MediaType: "model/gltf-binary"}}
	if err := spec.Validate(); err == nil {
		t.Fatal("an output with no size limit was accepted")
	}

	spec.Outputs = []Output{{Name: "mesh", RelativePath: "mesh.glb", MaxSizeBytes: 1 << 20}}
	if err := spec.Validate(); err == nil {
		t.Fatal("an output with no media type was accepted")
	}

	spec.Outputs = []Output{{
		Name: "mesh", RelativePath: "mesh.glb",
		MediaType: "model/gltf-binary", MaxSizeBytes: 1 << 20,
	}}
	if err := spec.Validate(); err != nil {
		t.Fatalf("a fully described output was refused: %v", err)
	}
}

func TestTwoInputsCannotShareAName(t *testing.T) {
	spec := validSpec()
	spec.Inputs = []Input{
		{Name: "survey", RelativePath: "a.jpg", ObjectID: "obj_1"},
		{Name: "survey", RelativePath: "b.jpg", ObjectID: "obj_2"},
	}
	if err := spec.Validate(); err == nil {
		t.Fatal("two inputs sharing a name were accepted")
	}
}

// A path that escapes its directory would let a job read or write outside the
// space staged for it.
func TestAnInputPathCannotEscape(t *testing.T) {
	spec := validSpec()
	spec.Inputs = []Input{{Name: "survey", RelativePath: "../../etc/passwd", ObjectID: "obj_1"}}
	if err := spec.Validate(); err == nil {
		t.Fatal("an input escaping its directory was accepted")
	}
}

// Quota is checked against what is already committed, not only against what one
// request asks for, so that many small requests cannot cross a limit together.
func TestQuotaCountsWhatIsAlreadyCommitted(t *testing.T) {
	quota := Quota{MaxConcurrentJobs: 4, MaxCPU: 8, MaxMemoryBytes: 16 << 30, MaxGPU: 2}
	spec := validSpec()

	if refusal := checkQuota(spec, quota, commitment{}); refusal != nil {
		t.Fatalf("the first job was refused against an empty commitment: %v", refusal)
	}

	// Two processors are asked for; six are already committed against a limit
	// of eight, so this one fits and a third would not.
	if refusal := checkQuota(spec, quota, commitment{Jobs: 3, CPU: 6, MemoryBytes: 8 << 30}); refusal != nil {
		t.Fatalf("a job that fits was refused: %v", refusal)
	}
	refusal := checkQuota(spec, quota, commitment{Jobs: 3, CPU: 7, MemoryBytes: 8 << 30})
	if refusal == nil || refusal.Reason != QuotaCPUExhausted {
		t.Fatalf("refusal = %v, want quota_cpu_exhausted", refusal)
	}

	refusal = checkQuota(spec, quota, commitment{Jobs: 4})
	if refusal == nil || refusal.Reason != QuotaConcurrentJobsExhausted {
		t.Fatalf("refusal = %v, want quota_concurrent_jobs_exhausted", refusal)
	}

	refusal = checkQuota(spec, quota, commitment{Jobs: 1, CPU: 1, MemoryBytes: 15 << 30})
	if refusal == nil || refusal.Reason != QuotaMemoryExhausted {
		t.Fatalf("refusal = %v, want quota_memory_exhausted", refusal)
	}
}

// A refusal that a person cannot act on is barely better than silence.
func TestARefusalExplainsItselfInWords(t *testing.T) {
	refusal := &Refusal{Reason: QuotaCPUExhausted, Detail: map[string]any{
		"requested": 4, "committed": 7, "limit": 8,
	}}
	message := refusal.Error()
	for _, expected := range []string{"4", "7", "8", "processors"} {
		if !strings.Contains(message, expected) {
			t.Errorf("the refusal does not mention %q: %s", expected, message)
		}
	}
}

func TestATerminalStateIsRecognised(t *testing.T) {
	for _, state := range []JobState{Succeeded, Failed, Cancelled, Evicted, TimedOut} {
		if !state.IsTerminal() {
			t.Errorf("%s was not treated as an ending", state)
		}
	}
	for _, state := range []JobState{Pending, Admitted, Running} {
		if state.IsTerminal() {
			t.Errorf("%s was treated as an ending", state)
		}
	}
}
