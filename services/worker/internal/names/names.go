// Package names gives the settings their iocean names.
//
// Settings are IOCEAN_* now. A box configured before the rename still says
// CORAL_CITY_*, and Carry gives each of those to its IOCEAN_* name unless that
// is already set, so the new name wins and the old one keeps working. Called
// first thing in main, before anything reads a setting. The old names go in a
// later release (docs/plan/iocean-rename.md).
package names

import (
	"os"
	"strings"
)

const (
	old    = "CORAL_CITY_"
	latest = "IOCEAN_"
)

// Carry copies every CORAL_CITY_X in the environment to IOCEAN_X where that
// is unset, and says which it gave.
func Carry() []string {
	given := []string{}
	for _, pair := range os.Environ() {
		name, value, _ := strings.Cut(pair, "=")
		if !strings.HasPrefix(name, old) {
			continue
		}
		renamed := latest + strings.TrimPrefix(name, old)
		if _, set := os.LookupEnv(renamed); set {
			continue
		}
		if os.Setenv(renamed, value) == nil {
			given = append(given, renamed)
		}
	}
	return given
}
