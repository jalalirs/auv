package domain

import "fmt"

// UncertaintyKind names how a layer version expresses what it does not know.
// There is no absent uncertainty: "unknown" is an answer that must be given.
type UncertaintyKind string

const (
	// UncertaintyUnknown states plainly that uncertainty was not determined.
	UncertaintyUnknown UncertaintyKind = "unknown"
	// UncertaintyAbsoluteMetres carries a distance in metres.
	UncertaintyAbsoluteMetres UncertaintyKind = "absolute_metres"
	// UncertaintyRelativeFraction carries a dimensionless fraction of the value.
	UncertaintyRelativeFraction UncertaintyKind = "relative_fraction"
	// UncertaintyDescribed carries a written statement where no single number applies.
	UncertaintyDescribed UncertaintyKind = "described"
)

// Uncertainty is a complete statement of what a version does not know.
type Uncertainty struct {
	Kind  UncertaintyKind
	Value *float64
	Note  string
}

// Validate reports whether the uncertainty is fully stated for its kind.
func (u Uncertainty) Validate() error {
	switch u.Kind {
	case UncertaintyUnknown:
		if u.Value != nil {
			return fmt.Errorf("%w: an unknown uncertainty carries no number", ErrInvalid)
		}
	case UncertaintyAbsoluteMetres, UncertaintyRelativeFraction:
		if u.Value == nil {
			return fmt.Errorf("%w: a %s uncertainty must carry a number", ErrInvalid, u.Kind)
		}
		if *u.Value < 0 {
			return fmt.Errorf("%w: an uncertainty of %v is not a magnitude", ErrInvalid, *u.Value)
		}
		if u.Kind == UncertaintyRelativeFraction && *u.Value > 1 {
			return fmt.Errorf("%w: a relative uncertainty of %v exceeds the whole value", ErrInvalid, *u.Value)
		}
	case UncertaintyDescribed:
		if u.Note == "" {
			return fmt.Errorf("%w: a described uncertainty must carry its description", ErrInvalid)
		}
		if u.Value != nil {
			return fmt.Errorf("%w: a described uncertainty carries no number", ErrInvalid)
		}
	default:
		return invalid("uncertainty kind", string(u.Kind),
			[]string{"unknown", "absolute_metres", "relative_fraction", "described"})
	}
	return nil
}
