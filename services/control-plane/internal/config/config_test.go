package config

import (
	"strings"
	"testing"
	"time"
)

// withRequiredSettings sets the settings that have no safe default, so that a
// test can be about the setting it is actually exercising.
func withRequiredSettings(t *testing.T) {
	t.Helper()
	t.Setenv("CORAL_CITY_DATABASE_URL", "postgres://coral@localhost/coral")
	t.Setenv("CORAL_CITY_STORAGE_ENDPOINT", "localhost:9000")
	t.Setenv("CORAL_CITY_STORAGE_ACCESS_KEY", "access")
	t.Setenv("CORAL_CITY_STORAGE_SECRET_KEY", "secret")
}

func TestDefaultsAreApplied(t *testing.T) {
	withRequiredSettings(t)

	config, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if config.Address != ":8080" {
		t.Fatalf("Address = %q, want :8080", config.Address)
	}
	if config.ShutdownTimeout != 10*time.Second {
		t.Fatalf("ShutdownTimeout = %s, want 10s", config.ShutdownTimeout)
	}
	if config.MaxAttempts != 3 {
		t.Fatalf("MaxAttempts = %d, want 3", config.MaxAttempts)
	}
	if config.SecureCookies {
		t.Fatal("SecureCookies defaults to true, but a development deployment has no TLS")
	}
}

func TestOverridesAreRead(t *testing.T) {
	withRequiredSettings(t)
	t.Setenv("CORAL_CITY_HTTP_ADDRESS", "127.0.0.1:9090")
	t.Setenv("CORAL_CITY_HTTP_WRITE_TIMEOUT", "45s")
	t.Setenv("CORAL_CITY_MAX_ATTEMPTS", "5")
	t.Setenv("CORAL_CITY_SECURE_COOKIES", "true")

	config, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}
	if config.Address != "127.0.0.1:9090" {
		t.Fatalf("Address = %q, want 127.0.0.1:9090", config.Address)
	}
	if config.WriteTimeout != 45*time.Second {
		t.Fatalf("WriteTimeout = %s, want 45s", config.WriteTimeout)
	}
	if config.MaxAttempts != 5 {
		t.Fatalf("MaxAttempts = %d, want 5", config.MaxAttempts)
	}
	if !config.SecureCookies {
		t.Fatal("SecureCookies = false, want true")
	}
}

// A setting with no safe default must stop the process rather than be guessed
// at: a control plane pointed at the wrong record is worse than one that does
// not start.
func TestASettingWithNoSafeDefaultIsRequired(t *testing.T) {
	withRequiredSettings(t)
	t.Setenv("CORAL_CITY_DATABASE_URL", "")

	_, err := Load()
	if err == nil {
		t.Fatal("Load() succeeded without a database url")
	}
	if !strings.Contains(err.Error(), "CORAL_CITY_DATABASE_URL") {
		t.Fatalf("the error does not name the missing setting: %v", err)
	}
}

func TestAMalformedDurationIsRefused(t *testing.T) {
	withRequiredSettings(t)
	t.Setenv("CORAL_CITY_LEASE_DURATION", "soon")

	if _, err := Load(); err == nil {
		t.Fatal("Load() accepted a duration of \"soon\"")
	}
}
