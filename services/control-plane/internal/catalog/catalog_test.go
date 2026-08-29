package catalog

import (
	"encoding/json"
	"errors"
	"testing"

	"github.com/jalalirs/auv/services/control-plane/internal/domain"
)

func wellFormedDynamics() Dynamics {
	return Dynamics{
		VersionID:         "ver_1",
		MassKg:            11.5,
		DisplacedVolumeM3: 0.0114,
		CentreOfGravity:   [3]float64{0, 0, 0},
		CentreOfBuoyancy:  [3]float64{0, 0, 0.01},
		InertiaTensor:     [9]float64{0.16, 0, 0, 0, 0.16, 0, 0, 0, 0.16},
		AddedMass:         json.RawMessage(`{"diagonal":[5.5,12.7,14.6,0.12,0.12,0.12]}`),
		LinearDamping:     json.RawMessage(`{"diagonal":[4.03,6.22,5.18,0.07,0.07,0.07]}`),
		QuadraticDamping:  json.RawMessage(`{"diagonal":[18.18,21.66,36.99,1.55,1.55,1.55]}`),
		Thrusters:         json.RawMessage(`[{"position":[0.156,0.111,0.085]}]`),
		Sensors:           json.RawMessage(`[{"kind":"imaging_sonar"}]`),
		TopicContract:     json.RawMessage(`{"publishes":["/sonar/image"]}`),
	}
}

func TestAVehicleWithCoincidentCentresIsRefused(t *testing.T) {
	// Not a style rule. The distance between the centre of gravity and the
	// centre of buoyancy is the lever arm that rights a vehicle when it rolls.
	// Let them coincide and the model has no restoring moment at all — which is
	// a silently wrong simulation rather than a failed one, and the worst kind
	// of thing for a platform whose product is trustworthy results.
	spec := wellFormedDynamics()
	spec.CentreOfBuoyancy = spec.CentreOfGravity

	if err := spec.Validate(); !errors.Is(err, domain.ErrInvalid) {
		t.Fatal("a vehicle whose centres of gravity and buoyancy coincide was accepted; " +
			"it would roll to any attitude and stay there")
	}
	if err := wellFormedDynamics().Validate(); err != nil {
		t.Fatalf("a vehicle with separated centres was refused: %v", err)
	}
}

func TestAVehicleHasMassAndDisplacesWater(t *testing.T) {
	for _, broken := range []func(Dynamics) Dynamics{
		func(d Dynamics) Dynamics { d.MassKg = 0; return d },
		func(d Dynamics) Dynamics { d.MassKg = -1; return d },
		func(d Dynamics) Dynamics { d.DisplacedVolumeM3 = 0; return d },
	} {
		if err := broken(wellFormedDynamics()).Validate(); !errors.Is(err, domain.ErrInvalid) {
			t.Error("a vehicle without mass or displacement was accepted; buoyancy is " +
				"computed from displaced volume, so neither is optional")
		}
	}
}

func TestEveryPartOfTheModelIsPresent(t *testing.T) {
	// A missing damping matrix does not fail loudly at run time — it produces a
	// vehicle that accelerates for ever. Refusing it here is cheaper than
	// discovering it in a result.
	for _, field := range []string{
		"AddedMass", "LinearDamping", "QuadraticDamping",
		"Thrusters", "Sensors", "TopicContract",
	} {
		spec := wellFormedDynamics()
		switch field {
		case "AddedMass":
			spec.AddedMass = nil
		case "LinearDamping":
			spec.LinearDamping = nil
		case "QuadraticDamping":
			spec.QuadraticDamping = nil
		case "Thrusters":
			spec.Thrusters = nil
		case "Sensors":
			spec.Sensors = nil
		case "TopicContract":
			spec.TopicContract = nil
		}
		if err := spec.Validate(); !errors.Is(err, domain.ErrInvalid) {
			t.Errorf("a vehicle missing %s was accepted", field)
		}
	}

	malformed := wellFormedDynamics()
	malformed.AddedMass = json.RawMessage(`{not json`)
	if err := malformed.Validate(); !errors.Is(err, domain.ErrInvalid) {
		t.Error("a vehicle whose model is not valid JSON was accepted")
	}
}

func TestOnlyACityOrAVehicleIsAnAsset(t *testing.T) {
	for _, good := range []string{"city", "vehicle"} {
		if _, err := ParseAssetKind(good); err != nil {
			t.Errorf("%q was refused: %v", good, err)
		}
	}
	for _, bad := range []string{"", "layer", "City", "reef"} {
		if _, err := ParseAssetKind(bad); !errors.Is(err, domain.ErrInvalid) {
			t.Errorf("%q was accepted as an asset kind", bad)
		}
	}
}

func TestACityStatesWhatItsDepthsAreMeasuredAgainst(t *testing.T) {
	// A depth without a vertical datum is a number, not a measurement, and a
	// dive that reports one is not reporting anything.
	spec := CitySpec{Slug: "mhl-tank", Name: "Marine Hydrodynamics Laboratory"}
	if err := spec.Validate(); !errors.Is(err, domain.ErrInvalid) {
		t.Error("a city without a vertical datum was accepted")
	}

	spec.VerticalDatum = "tank floor"
	if err := spec.Validate(); err != nil {
		t.Fatalf("a fully described city was refused: %v", err)
	}
}

func TestAnUnpublishedVersionIsADraft(t *testing.T) {
	draft := Version{ID: "ver_1"}
	if draft.Published() {
		t.Error("a version with no publication instant reported itself as published")
	}
}
