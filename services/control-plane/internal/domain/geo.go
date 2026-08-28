package domain

import (
	"fmt"
	"time"
)

// Extent is the bounded region a city or a layer version covers, in WGS 84
// degrees. It is stored as a polygon, so a richer footprint than a rectangle
// can be accepted later without changing the schema.
type Extent struct {
	West  float64 `json:"west"`
	South float64 `json:"south"`
	East  float64 `json:"east"`
	North float64 `json:"north"`
}

// Validate reports whether the extent describes a real region of the globe.
func (e Extent) Validate() error {
	switch {
	case e.West < -180 || e.West > 180:
		return fmt.Errorf("%w: western longitude %v is off the globe", ErrInvalid, e.West)
	case e.East < -180 || e.East > 180:
		return fmt.Errorf("%w: eastern longitude %v is off the globe", ErrInvalid, e.East)
	case e.South < -90 || e.South > 90:
		return fmt.Errorf("%w: southern latitude %v is off the globe", ErrInvalid, e.South)
	case e.North < -90 || e.North > 90:
		return fmt.Errorf("%w: northern latitude %v is off the globe", ErrInvalid, e.North)
	case e.North <= e.South:
		return fmt.Errorf("%w: northern latitude %v is not north of %v", ErrInvalid, e.North, e.South)
	case e.East <= e.West:
		return fmt.Errorf("%w: eastern longitude %v is not east of %v", ErrInvalid, e.East, e.West)
	}
	return nil
}

// CoordinateReference is an EPSG code. It is required everywhere a position is
// recorded, because a coordinate without a reference is not a position.
type CoordinateReference int

// WGS84 is the geographic reference the platform exchanges positions in.
const WGS84 CoordinateReference = 4326

// Validate reports whether the code could name a reference system.
func (c CoordinateReference) Validate() error {
	if c <= 0 {
		return fmt.Errorf("%w: EPSG code %d does not name a reference system", ErrInvalid, int(c))
	}
	return nil
}

// TimeBasis records when the content of a version was measured, and the
// instrument clock offset where it is known.
type TimeBasis struct {
	From time.Time
	To   time.Time
	// ClockOffsetSeconds is the instrument clock's offset from UTC, where it
	// was determined. Nil means it was not determined, which is different from
	// zero, which means it was determined to be correct.
	ClockOffsetSeconds *float64
}

// Validate reports whether the time basis describes a real interval.
func (t TimeBasis) Validate() error {
	if t.From.IsZero() || t.To.IsZero() {
		return fmt.Errorf("%w: a time basis states when the content was measured", ErrInvalid)
	}
	if t.To.Before(t.From) {
		return fmt.Errorf("%w: the interval ends at %s, before it begins at %s",
			ErrInvalid, t.To.Format(time.RFC3339), t.From.Format(time.RFC3339))
	}
	return nil
}
