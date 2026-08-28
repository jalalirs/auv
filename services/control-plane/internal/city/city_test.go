package city

import (
	"testing"

	"github.com/jalalirs/auv/services/control-plane/internal/domain"
)

func valid() CreateSpec {
	return CreateSpec{
		Slug:            "al-fahal",
		Name:            "Al Fahal",
		Summary:         "A reef used by the platform.",
		Extent:          domain.Extent{West: 38.9, South: 22.2, East: 39.1, North: 22.4},
		CRS:             32637,
		VerticalDatum:   "mean sea level",
		Discoverability: domain.Unlisted,
		CreatedBy:       "prin_1",
	}
}

// A place without a coordinate reference or a vertical datum is not a place:
// nothing recorded in it could be located or compared.
func TestAPlaceMustBeLocatable(t *testing.T) {
	cases := []struct {
		name   string
		change func(*CreateSpec)
	}{
		{"a name", func(s *CreateSpec) { s.Name = " " }},
		{"a summary", func(s *CreateSpec) { s.Summary = "" }},
		{"a usable short name", func(s *CreateSpec) { s.Slug = "Al Fahal" }},
		{"a real extent", func(s *CreateSpec) { s.Extent = domain.Extent{} }},
		{"a coordinate reference", func(s *CreateSpec) { s.CRS = 0 }},
		{"a vertical datum", func(s *CreateSpec) { s.VerticalDatum = "" }},
		{"a known discoverability", func(s *CreateSpec) { s.Discoverability = "sometimes" }},
	}
	for _, test := range cases {
		t.Run("without "+test.name, func(t *testing.T) {
			spec := valid()
			test.change(&spec)
			if err := spec.Validate(); err == nil {
				t.Fatalf("a place without %s was accepted", test.name)
			}
		})
	}

	if err := valid().Validate(); err != nil {
		t.Fatalf("a fully described place was refused: %v", err)
	}
}

// A place is unlisted unless someone decides otherwise, so that founding one
// does not announce it.
func TestEveryDiscoverabilityIsExpressible(t *testing.T) {
	for _, state := range []domain.Discoverability{
		domain.ListedOpen, domain.ListedLocked, domain.Unlisted,
	} {
		spec := valid()
		spec.Discoverability = state
		if err := spec.Validate(); err != nil {
			t.Errorf("a %s place was refused: %v", state, err)
		}
	}
}
