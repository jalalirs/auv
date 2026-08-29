package dive

import (
	"encoding/json"
	"errors"
	"testing"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/domain"
)

func TestAutonomyIsPinnedByDigestAndNotByTag(t *testing.T) {
	base := StackSpec{
		OrgID:           "org_1",
		Slug:            "depth-hold",
		Name:            "Depth hold",
		ImageRepository: "registry.example/depth-hold",
		CreatedBy:       "prin_1",
	}

	for _, notADigest := range []string{
		"latest",
		"v1.2.3",
		"",
		"sha256:short",
		"sha1:da39a3ee5e6b4b0d3255bfef95601890afd80709",
	} {
		spec := base
		spec.ImageDigest = notADigest
		if err := spec.Validate(); !errors.Is(err, domain.ErrInvalid) {
			t.Errorf("an image pinned by %q was accepted; a tag can be moved, so a re-run "+
				"of the same dive would not be a re-run of the same program", notADigest)
		}
	}

	spec := base
	spec.ImageDigest = "sha256:abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
	if err := spec.Validate(); err != nil {
		t.Fatalf("a properly pinned image was refused: %v", err)
	}
}

func TestConditionsSayWhetherTheWaterWasMeasuredOrInvented(t *testing.T) {
	instant := time.Date(2024, 3, 14, 9, 0, 0, 0, time.UTC)

	observedWithoutInstant := ConditionsSpec{Kind: Observed, Name: "Red Sea, March"}
	if err := observedWithoutInstant.Validate(); !errors.Is(err, domain.ErrInvalid) {
		t.Error("observed conditions were accepted without the instant they were drawn from, " +
			"which is the whole of what makes them observed")
	}

	constructedWithInstant := ConditionsSpec{
		Kind: Constructed, Name: "Two knot current", ObservedAt: &instant,
	}
	if err := constructedWithInstant.Validate(); !errors.Is(err, domain.ErrInvalid) {
		t.Error("constructed conditions were allowed to name an instant, which claims a " +
			"provenance they do not have")
	}

	good := []ConditionsSpec{
		{Kind: Observed, Name: "Red Sea, March", ObservedAt: &instant},
		{Kind: Constructed, Name: "Two knot current"},
	}
	for _, spec := range good {
		if err := spec.Validate(); err != nil {
			t.Errorf("%s conditions were refused: %v", spec.Kind, err)
		}
	}
}

func TestAFinishedRunIsFinished(t *testing.T) {
	for _, state := range []State{Succeeded, Failed, Cancelled, Expired} {
		if !state.Finished() {
			t.Errorf("%s should count as finished; the record refuses to rewrite it", state)
		}
	}
	for _, state := range []State{Queued, Preparing, Running} {
		if state.Finished() {
			t.Errorf("%s should not count as finished", state)
		}
	}
}

func TestConditionsWithTheSameContentHaveTheSameDigest(t *testing.T) {
	// A run pins conditions the way it pins a city. Two sets that would produce
	// the same water must therefore identify identically, whoever recorded them
	// and whenever they did.
	instant := time.Date(2024, 3, 14, 9, 0, 0, 0, time.UTC)
	elsewhere := instant.In(time.FixedZone("UTC+3", 3*60*60))

	first := Conditions{
		ID: "cond_1", Kind: Observed, Name: "Red Sea", ObservedAt: &instant,
		Sources:    json.RawMessage(`[{"dataset":"glorys12"}]`),
		Parameters: json.RawMessage(`{}`),
		CreatedBy:  "prin_1",
	}
	second := Conditions{
		ID: "cond_2", Kind: Observed, Name: "A different label", ObservedAt: &elsewhere,
		Sources:    json.RawMessage(`[{"dataset":"glorys12"}]`),
		Parameters: json.RawMessage(`{}`),
		CreatedBy:  "prin_2",
	}

	a, err := first.Digest()
	if err != nil {
		t.Fatalf("identifying conditions: %v", err)
	}
	b, err := second.Digest()
	if err != nil {
		t.Fatalf("identifying conditions: %v", err)
	}
	if a != b {
		t.Error("the same water recorded twice produced two identities, so a re-run could " +
			"not be recognised as the same experiment")
	}

	third := second
	third.Parameters = json.RawMessage(`{"turbidity":0.4}`)
	c, err := third.Digest()
	if err != nil {
		t.Fatalf("identifying conditions: %v", err)
	}
	if a == c {
		t.Error("different water produced the same identity")
	}
}

func TestADiveNamesEverythingADiveNeeds(t *testing.T) {
	full := DiveSpec{
		OrgID: "org_1", Name: "Hold depth in the tank",
		CityVersionID: "ver_1", VehicleVersionID: "ver_2", ConditionsID: "cond_1",
		CreatedBy: "prin_1",
	}
	if err := full.Validate(); err != nil {
		t.Fatalf("a fully described dive was refused: %v", err)
	}

	for _, missing := range []func(DiveSpec) DiveSpec{
		func(s DiveSpec) DiveSpec { s.Name = ""; return s },
		func(s DiveSpec) DiveSpec { s.CityVersionID = ""; return s },
		func(s DiveSpec) DiveSpec { s.VehicleVersionID = ""; return s },
		func(s DiveSpec) DiveSpec { s.ConditionsID = ""; return s },
	} {
		if err := missing(full).Validate(); !errors.Is(err, domain.ErrInvalid) {
			t.Error("a dive missing one of its four determinants was accepted")
		}
	}
}
