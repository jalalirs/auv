package config

import (
	"testing"
	"time"
)

func TestLoadDefaults(t *testing.T) {
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
}

func TestLoadOverrides(t *testing.T) {
	t.Setenv("CORAL_CITY_HTTP_ADDRESS", "127.0.0.1:9090")
	t.Setenv("CORAL_CITY_HTTP_WRITE_TIMEOUT", "45s")

	config, err := Load()
	if err != nil {
		t.Fatalf("Load() error = %v", err)
	}

	if config.Address != "127.0.0.1:9090" {
		t.Fatalf("Address = %q", config.Address)
	}
	if config.WriteTimeout != 45*time.Second {
		t.Fatalf("WriteTimeout = %s, want 45s", config.WriteTimeout)
	}
}

func TestLoadRejectsInvalidDuration(t *testing.T) {
	t.Setenv("CORAL_CITY_HTTP_IDLE_TIMEOUT", "never")

	if _, err := Load(); err == nil {
		t.Fatal("Load() error = nil, want invalid duration error")
	}
}
