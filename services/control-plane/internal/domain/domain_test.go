package domain

import (
	"errors"
	"testing"
	"time"
)

// A scenario input makes every downstream value a scenario. This is the rule
// that stops a hypothetical from being presented later as a measurement.
func TestTruthClassDoesNotStrengthen(t *testing.T) {
	cases := []struct {
		name     string
		declared TruthClass
		inputs   []TruthClass
		want     TruthClass
	}{
		{"an analysis of observations stays an analysis",
			Analysis, []TruthClass{Observation, Observation}, Analysis},
		{"anything derived from a scenario is a scenario",
			Analysis, []TruthClass{Observation, Scenario}, Scenario},
		{"a simulation over a scenario is still a scenario",
			Simulation, []TruthClass{Scenario}, Scenario},
		{"derived from nothing, a declaration stands",
			Observation, nil, Observation},
		{"a forecast over observations stays a forecast",
			Forecast, []TruthClass{Observation}, Forecast},
	}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			if got := DerivedTruthClass(test.declared, test.inputs); got != test.want {
				t.Fatalf("DerivedTruthClass(%s, %v) = %s, want %s",
					test.declared, test.inputs, got, test.want)
			}
		})
	}
}

func TestAnUnknownTruthClassIsRefused(t *testing.T) {
	if _, err := ParseTruthClass("probably"); !errors.Is(err, ErrInvalid) {
		t.Fatalf("ParseTruthClass(\"probably\") error = %v, want ErrInvalid", err)
	}
}

// Uncertainty is always stated. "Unknown" is an answer; absence is not, and a
// number that does not belong to its kind is not either.
func TestUncertaintyMustBeFullyStated(t *testing.T) {
	metres := 0.14
	negative := -1.0
	tooMuch := 1.5

	cases := []struct {
		name        string
		uncertainty Uncertainty
		valid       bool
	}{
		{"unknown is a legitimate answer", Uncertainty{Kind: UncertaintyUnknown}, true},
		{"a measured uncertainty carries its number",
			Uncertainty{Kind: UncertaintyAbsoluteMetres, Value: &metres}, true},
		{"a measured uncertainty without a number is incomplete",
			Uncertainty{Kind: UncertaintyAbsoluteMetres}, false},
		{"unknown carries no number",
			Uncertainty{Kind: UncertaintyUnknown, Value: &metres}, false},
		{"a magnitude is not negative",
			Uncertainty{Kind: UncertaintyAbsoluteMetres, Value: &negative}, false},
		{"a fraction of a value does not exceed the value",
			Uncertainty{Kind: UncertaintyRelativeFraction, Value: &tooMuch}, false},
		{"a described uncertainty carries its description",
			Uncertainty{Kind: UncertaintyDescribed, Note: "varies with depth"}, true},
		{"a description is not optional when the kind is described",
			Uncertainty{Kind: UncertaintyDescribed}, false},
		{"an absent kind is not a kind", Uncertainty{}, false},
	}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			err := test.uncertainty.Validate()
			if test.valid && err != nil {
				t.Fatalf("Validate() error = %v, want nil", err)
			}
			if !test.valid && err == nil {
				t.Fatal("Validate() accepted an incompletely stated uncertainty")
			}
		})
	}
}

func TestAnExtentDescribesARealRegion(t *testing.T) {
	cases := []struct {
		name   string
		extent Extent
		valid  bool
	}{
		{"a region of the sea", Extent{West: 38.9, South: 22.2, East: 39.1, North: 22.4}, true},
		{"north of south", Extent{West: 0, South: 10, East: 1, North: 5}, false},
		{"east of west", Extent{West: 10, South: 0, East: 5, North: 1}, false},
		{"a point is not a region", Extent{West: 1, South: 1, East: 1, North: 1}, false},
		{"off the globe", Extent{West: -181, South: 0, East: 1, North: 1}, false},
	}
	for _, test := range cases {
		t.Run(test.name, func(t *testing.T) {
			err := test.extent.Validate()
			if test.valid != (err == nil) {
				t.Fatalf("Validate() error = %v, valid = %v", err, test.valid)
			}
		})
	}
}

func TestATimeBasisDescribesARealInterval(t *testing.T) {
	now := time.Now()
	if err := (TimeBasis{From: now, To: now.Add(time.Hour)}).Validate(); err != nil {
		t.Fatalf("a forward interval was refused: %v", err)
	}
	if err := (TimeBasis{From: now, To: now.Add(-time.Hour)}).Validate(); err == nil {
		t.Fatal("an interval that ends before it begins was accepted")
	}
	if err := (TimeBasis{}).Validate(); err == nil {
		t.Fatal("a version with no time basis was accepted")
	}
}

// A path that reaches storage must be reproducible on any filesystem, and must
// not be able to escape the version that contains it.
func TestARelativePathCannotEscape(t *testing.T) {
	refused := []string{
		"", "/absolute/path", "../outside", "tiles/../../outside",
		`windows\path`, "trailing/", "double//segment", ".",
	}
	for _, path := range refused {
		if err := ValidateRelativePath(path); err == nil {
			t.Errorf("ValidateRelativePath(%q) accepted an unsafe path", path)
		}
	}
	accepted := []string{"tileset.json", "tiles/0/0/0.b3dm", "a.b.c/d-e_f.tif"}
	for _, path := range accepted {
		if err := ValidateRelativePath(path); err != nil {
			t.Errorf("ValidateRelativePath(%q) error = %v", path, err)
		}
	}
}

func TestASlugIsAStableName(t *testing.T) {
	refused := []string{"", "a", "1leading-digit", "Upper", "has space", "trailing-",
		"under_score"}
	for _, slug := range refused {
		if err := ValidateSlug(slug); err == nil {
			t.Errorf("ValidateSlug(%q) accepted an unusable name", slug)
		}
	}
	for _, slug := range []string{"al-fahal", "site2", "north-reef-01"} {
		if err := ValidateSlug(slug); err != nil {
			t.Errorf("ValidateSlug(%q) error = %v", slug, err)
		}
	}
}
