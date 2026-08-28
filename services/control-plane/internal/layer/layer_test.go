package layer

import (
	"errors"
	"testing"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/domain"
)

func validLayer() CreateSpec {
	return CreateSpec{
		ScopeKind:       domain.CityScope,
		CityID:          "city_1",
		Slug:            "soundings",
		Kind:            domain.Bathymetry,
		Title:           "Soundings",
		Description:     "Depth soundings.",
		AttributedOrgID: "org_1",
		CreatedBy:       "prin_1",
	}
}

func TestALayerNamesItsScopeCorrectly(t *testing.T) {
	// A city layer names its city; a platform layer must not, because it is not
	// in one.
	spec := validLayer()
	spec.ScopeKind = domain.PlatformScope
	if err := spec.Validate(); err == nil {
		t.Fatal("a platform layer naming a city was accepted")
	}

	spec = validLayer()
	spec.CityID = ""
	if err := spec.Validate(); err == nil {
		t.Fatal("a city layer naming no city was accepted")
	}
}

func TestALayerIsAttributedToAnInstitution(t *testing.T) {
	spec := validLayer()
	spec.AttributedOrgID = ""
	if err := spec.Validate(); !errors.Is(err, domain.ErrInvalid) {
		t.Fatalf("Validate() error = %v, want ErrInvalid", err)
	}
}

func measured() domain.TimeBasis {
	from := time.Date(2026, 4, 12, 6, 0, 0, 0, time.UTC)
	return domain.TimeBasis{From: from, To: from.Add(3 * time.Hour)}
}

func validVersion() VersionSpec {
	metres := 0.14
	return VersionSpec{
		LayerID:             "layer_1",
		TruthClass:          domain.Observation,
		CRS:                 32637,
		VerticalDatum:       "mean sea level",
		Extent:              domain.Extent{West: 38.9, South: 22.2, East: 39.1, North: 22.4},
		Time:                measured(),
		Uncertainty:         domain.Uncertainty{Kind: domain.UncertaintyAbsoluteMetres, Value: &metres},
		Rights:              "CC-BY-4.0",
		Attribution:         "An institution",
		Visibility:          domain.Restricted,
		Files:               []ManifestInput{{RelativePath: "sounding.txt", ObjectID: "obj_1"}},
		ProducerPrincipalID: "prin_1",
	}
}

// Nothing a version must state is optional. A value without its reference
// system, datum, time basis, rights, or uncertainty is not evidence, whatever
// it looks like.
func TestEvidenceMustBeFullyStated(t *testing.T) {
	cases := []struct {
		name   string
		change func(*VersionSpec)
	}{
		{"a coordinate reference", func(s *VersionSpec) { s.CRS = 0 }},
		{"a vertical datum", func(s *VersionSpec) { s.VerticalDatum = "  " }},
		{"a real extent", func(s *VersionSpec) { s.Extent = domain.Extent{} }},
		{"a time basis", func(s *VersionSpec) { s.Time = domain.TimeBasis{} }},
		{"an uncertainty", func(s *VersionSpec) { s.Uncertainty = domain.Uncertainty{} }},
		{"rights", func(s *VersionSpec) { s.Rights = "" }},
		{"attribution", func(s *VersionSpec) { s.Attribution = "" }},
		{"at least one file", func(s *VersionSpec) { s.Files = nil }},
		{"a truth class", func(s *VersionSpec) { s.TruthClass = "" }},
	}
	for _, test := range cases {
		t.Run("without "+test.name, func(t *testing.T) {
			spec := validVersion()
			test.change(&spec)
			if err := spec.Validate(); err == nil {
				t.Fatalf("evidence without %s was accepted", test.name)
			}
		})
	}

	if err := validVersion().Validate(); err != nil {
		t.Fatalf("fully stated evidence was refused: %v", err)
	}
}

// "Unknown" is a legitimate statement about uncertainty. Refusing it would push
// people towards inventing a number, which is the opposite of the intent.
func TestAnUndeterminedUncertaintyIsAcceptable(t *testing.T) {
	spec := validVersion()
	spec.Uncertainty = domain.Uncertainty{Kind: domain.UncertaintyUnknown}
	if err := spec.Validate(); err != nil {
		t.Fatalf("evidence stating that its uncertainty is unknown was refused: %v", err)
	}
}

// Exactly one producer: a job computed it, or a person recorded it. Both or
// neither would leave the record unable to say where it came from.
func TestEvidenceHasExactlyOneProducer(t *testing.T) {
	spec := validVersion()
	spec.ProducerJobID = "job_1"
	if err := spec.Validate(); err == nil {
		t.Fatal("evidence claiming two producers was accepted")
	}

	spec = validVersion()
	spec.ProducerPrincipalID = ""
	if err := spec.Validate(); err == nil {
		t.Fatal("evidence claiming no producer was accepted")
	}
}

// Computed evidence names the recipe and the exact image that produced it, or
// its reproducibility claim is empty.
func TestComputedEvidenceNamesWhatComputedIt(t *testing.T) {
	spec := validVersion()
	spec.ProducerPrincipalID = ""
	spec.ProducerJobID = "job_1"
	if err := spec.Validate(); err == nil {
		t.Fatal("computed evidence naming no recipe was accepted")
	}

	spec.RecipeID = "reconstruct@2.1.0"
	spec.ImageDigest = "ghcr.io/example/x@sha256:abc"
	if err := spec.Validate(); err != nil {
		t.Fatalf("computed evidence naming its recipe was refused: %v", err)
	}
}

func TestAFileWithinAVersionCannotEscape(t *testing.T) {
	spec := validVersion()
	spec.Files = []ManifestInput{{RelativePath: "../outside", ObjectID: "obj_1"}}
	if err := spec.Validate(); err == nil {
		t.Fatal("a file escaping its version was accepted")
	}
}

func TestPublicationStatesKnowWhatTheyAre(t *testing.T) {
	if !domain.Published.IsVisibleByDefault() || !domain.Superseded.IsVisibleByDefault() {
		t.Fatal("published and superseded evidence should be visible by default")
	}
	if domain.Retracted.IsVisibleByDefault() || domain.Draft.IsVisibleByDefault() {
		t.Fatal("withdrawn and unfinished evidence should not be visible by default")
	}
	if !domain.Retracted.IsTerminal() {
		t.Fatal("a retracted version stays retracted")
	}
}
