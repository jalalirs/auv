package names

import (
	"os"
	"testing"
)

func TestAnOldNameIsGivenItsNewOneAndANewOneIsKept(t *testing.T) {
	t.Setenv("CORAL_CITY_ROUND_TRIP_TEST", "old")
	t.Setenv("CORAL_CITY_KEPT_TEST", "old")
	t.Setenv("IOCEAN_KEPT_TEST", "new")
	os.Unsetenv("IOCEAN_ROUND_TRIP_TEST")
	defer os.Unsetenv("IOCEAN_ROUND_TRIP_TEST")
	Carry()
	if got := os.Getenv("IOCEAN_ROUND_TRIP_TEST"); got != "old" {
		t.Fatalf("IOCEAN_ROUND_TRIP_TEST = %q", got)
	}
	if got := os.Getenv("IOCEAN_KEPT_TEST"); got != "new" {
		t.Fatalf("IOCEAN_KEPT_TEST = %q, the new name should win", got)
	}
}
