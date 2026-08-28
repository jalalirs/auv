// Package domain holds the value objects shared by every part of the platform.
//
// These types exist so that a coordinate reference, a truth class, or an
// uncertainty cannot be represented as a bare string that some caller forgot
// to fill in. Enumerations validate themselves; anything the database requires
// is required here too.
package domain

import (
	"errors"
	"fmt"
	"strings"
)

// ErrInvalid reports a value that cannot exist in the domain.
var ErrInvalid = errors.New("invalid value")

func invalid(what, got string, allowed []string) error {
	return fmt.Errorf("%w: %s %q is not one of %s", ErrInvalid, what, got, strings.Join(allowed, ", "))
}

// TruthClass states what a value is, epistemically. It travels down lineage
// and is never strengthened by a derived job.
type TruthClass string

const (
	// Observation is a measurement of the world.
	Observation TruthClass = "observation"
	// Analysis is derived from observation by a documented method.
	Analysis TruthClass = "analysis"
	// Forecast is a statement about a time that has not happened.
	Forecast TruthClass = "forecast"
	// Scenario is a hypothetical input chosen by a person.
	Scenario TruthClass = "scenario"
	// Simulation is the output of a model run.
	Simulation TruthClass = "simulation"
)

var truthClasses = []string{"observation", "analysis", "forecast", "scenario", "simulation"}

// ParseTruthClass validates a truth class.
func ParseTruthClass(value string) (TruthClass, error) {
	switch TruthClass(value) {
	case Observation, Analysis, Forecast, Scenario, Simulation:
		return TruthClass(value), nil
	}
	return "", invalid("truth class", value, truthClasses)
}

// DerivedTruthClass reports the truth class an output must carry given the
// truth classes it was derived from. A scenario input makes every downstream
// value a scenario, permanently.
func DerivedTruthClass(declared TruthClass, inputs []TruthClass) TruthClass {
	for _, input := range inputs {
		if input == Scenario {
			return Scenario
		}
	}
	return declared
}

// LayerKind names what sort of content a layer holds.
type LayerKind string

const (
	Bathymetry        LayerKind = "bathymetry"
	Mesh              LayerKind = "mesh"
	PointCloud        LayerKind = "point_cloud"
	Orthomosaic       LayerKind = "orthomosaic"
	Structure         LayerKind = "structure"
	Field             LayerKind = "field"
	ObservationSeries LayerKind = "observation_series"
	Annotation        LayerKind = "annotation"
	Telemetry         LayerKind = "telemetry"
	Tileset           LayerKind = "tileset"
	Imagery           LayerKind = "imagery"
)

var layerKinds = []string{
	"bathymetry", "mesh", "point_cloud", "orthomosaic", "structure", "field",
	"observation_series", "annotation", "telemetry", "tileset", "imagery",
}

// ParseLayerKind validates a layer kind.
func ParseLayerKind(value string) (LayerKind, error) {
	for _, known := range layerKinds {
		if value == known {
			return LayerKind(value), nil
		}
	}
	return "", invalid("layer kind", value, layerKinds)
}

// LayerState is where a version sits in the publication lifecycle.
type LayerState string

const (
	Draft      LayerState = "draft"
	InReview   LayerState = "in_review"
	Published  LayerState = "published"
	Superseded LayerState = "superseded"
	Retracted  LayerState = "retracted"
)

// IsTerminal reports whether a state can no longer change by ordinary means.
func (s LayerState) IsTerminal() bool { return s == Retracted }

// IsVisibleByDefault reports whether a version appears in listings that do not
// explicitly ask for withdrawn material.
func (s LayerState) IsVisibleByDefault() bool {
	return s == Published || s == Superseded
}

// Visibility distinguishes the shared record from restricted contributions.
type Visibility string

const (
	// Restricted layers are reachable only through a binding.
	Restricted Visibility = "restricted"
	// Canonical layers are part of the shared record of a place.
	Canonical Visibility = "canonical"
)

// ScopeKind says whether a layer belongs to the platform or to one city.
type ScopeKind string

const (
	PlatformScope ScopeKind = "platform"
	CityScope     ScopeKind = "city"
)

// ParseScopeKind validates a layer scope.
func ParseScopeKind(value string) (ScopeKind, error) {
	switch ScopeKind(value) {
	case PlatformScope, CityScope:
		return ScopeKind(value), nil
	}
	return "", invalid("scope", value, []string{"platform", "city"})
}

// Discoverability decides what a principal with no binding may learn about a
// city. It is separate from whether that principal may enter.
type Discoverability string

const (
	// ListedOpen appears in the catalogue and may be entered by anyone signed in.
	ListedOpen Discoverability = "listed_open"
	// ListedLocked appears in the catalogue but requires a binding to enter.
	ListedLocked Discoverability = "listed_locked"
	// Unlisted is indistinguishable from absent without a binding.
	Unlisted Discoverability = "unlisted"
)

var discoverabilities = []string{"listed_open", "listed_locked", "unlisted"}

// ParseDiscoverability validates a discoverability state.
func ParseDiscoverability(value string) (Discoverability, error) {
	switch Discoverability(value) {
	case ListedOpen, ListedLocked, Unlisted:
		return Discoverability(value), nil
	}
	return "", invalid("discoverability", value, discoverabilities)
}

// Bucket names a storage area with its own rule.
type Bucket string

const (
	// Evidence holds raw observation. It is written once and never rewritten.
	Evidence Bucket = "evidence"
	// Derived holds job output, immutable per version.
	Derived Bucket = "derived"
	// Ephemeral holds scratch, tiles, and previews that may expire.
	Ephemeral Bucket = "ephemeral"
)

var buckets = []string{"evidence", "derived", "ephemeral"}

// ParseBucket validates a bucket name.
func ParseBucket(value string) (Bucket, error) {
	switch Bucket(value) {
	case Evidence, Derived, Ephemeral:
		return Bucket(value), nil
	}
	return "", invalid("bucket", value, buckets)
}
