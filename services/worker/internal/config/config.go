// Package config reads the settings a worker needs from its environment.
package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

// Config is everything a worker needs to take work and run it.
type Config struct {
	// ControlPlaneURL is where work is leased from and reported to.
	ControlPlaneURL string
	// Credential authenticates this worker as a service principal.
	Credential string
	// TargetName is the execution target this worker serves. A worker takes
	// only work placed on its own target.
	TargetName string

	// WorkDir is where inputs and outputs are staged, as this process sees it.
	WorkDir string
	// HostWorkDir is the same directory as the container runtime sees it. The
	// two differ when the worker itself runs in a container, because a bind
	// mount is resolved by the daemon on the host, not inside the worker.
	HostWorkDir string

	DockerSocket string

	PollInterval      time.Duration
	HeartbeatInterval time.Duration
	RequestTimeout    time.Duration
	// MaxInputBytes bounds what a worker will download for one input, so that
	// a malformed job cannot fill the disk.
	MaxInputBytes int64
}

// Load reads the environment, refusing anything that has no safe default.
func Load() (Config, error) {
	config := Config{
		ControlPlaneURL: os.Getenv("CORAL_CITY_CONTROL_PLANE_URL"),
		Credential:      os.Getenv("CORAL_CITY_WORKER_CREDENTIAL"),
		TargetName:      valueOrDefault("CORAL_CITY_WORKER_TARGET", "local-docker"),
		WorkDir:         valueOrDefault("CORAL_CITY_WORKER_WORKDIR", "/var/lib/coral-city/work"),
		DockerSocket:    valueOrDefault("CORAL_CITY_DOCKER_SOCKET", "/var/run/docker.sock"),
	}
	if config.ControlPlaneURL == "" {
		return Config{}, fmt.Errorf("CORAL_CITY_CONTROL_PLANE_URL must be set")
	}
	// A credential may be given directly or, where one process provisions the
	// worker and another runs it, through a file the two share.
	if file := os.Getenv("CORAL_CITY_WORKER_CREDENTIAL_FILE"); config.Credential == "" && file != "" {
		content, err := os.ReadFile(file)
		if err != nil {
			return Config{}, fmt.Errorf("reading the worker credential from %s: %w", file, err)
		}
		config.Credential = strings.TrimSpace(string(content))
	}
	if config.Credential == "" {
		return Config{}, fmt.Errorf(
			"CORAL_CITY_WORKER_CREDENTIAL or CORAL_CITY_WORKER_CREDENTIAL_FILE must be set")
	}

	config.HostWorkDir = valueOrDefault("CORAL_CITY_WORKER_HOST_WORKDIR", config.WorkDir)

	durations := []struct {
		name        string
		fallback    time.Duration
		destination *time.Duration
	}{
		{"CORAL_CITY_WORKER_POLL_INTERVAL", 2 * time.Second, &config.PollInterval},
		{"CORAL_CITY_WORKER_HEARTBEAT_INTERVAL", 15 * time.Second, &config.HeartbeatInterval},
		{"CORAL_CITY_WORKER_REQUEST_TIMEOUT", 30 * time.Second, &config.RequestTimeout},
	}
	for _, setting := range durations {
		value, err := duration(setting.name, setting.fallback)
		if err != nil {
			return Config{}, err
		}
		*setting.destination = value
	}

	maxInput, err := number64("CORAL_CITY_WORKER_MAX_INPUT_BYTES", int64(8)<<30)
	if err != nil {
		return Config{}, err
	}
	config.MaxInputBytes = maxInput

	return config, nil
}

func duration(name string, fallback time.Duration) (time.Duration, error) {
	raw := os.Getenv(name)
	if raw == "" {
		return fallback, nil
	}
	value, err := time.ParseDuration(raw)
	if err != nil || value <= 0 {
		return 0, fmt.Errorf("%s must be a positive duration: %q", name, raw)
	}
	return value, nil
}

func number64(name string, fallback int64) (int64, error) {
	raw := os.Getenv(name)
	if raw == "" {
		return fallback, nil
	}
	value, err := strconv.ParseInt(raw, 10, 64)
	if err != nil || value <= 0 {
		return 0, fmt.Errorf("%s must be a positive whole number: %q", name, raw)
	}
	return value, nil
}

func valueOrDefault(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}
