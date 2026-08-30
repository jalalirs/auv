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

	// SimImage is what a dive is simulated in. Named here rather than by the
	// platform because it is a property of this host — what it has, and what
	// its GPUs can run — and a host that lacks it should say so on startup
	// rather than accept a dive it cannot perform.
	SimImage string

	// StreamHost is the address somebody watching an interactive dive connects
	// to. The host knows which machine it is; the control plane does not, and
	// a platform that guessed would send people to a name that does not resolve
	// from where they are.
	StreamHost string

	// StreamSignalPort and StreamMediaPort are where an interactive dive is
	// watched. Deliberately below 32768.
	//
	// Isaac Sim's defaults are 49100 and 47998, and both sit inside Linux's
	// ephemeral port range — 32768 to 60999 on this host — which the kernel
	// hands out to any outgoing connection that asks. So the port is sometimes
	// free and sometimes not, for reasons that have nothing to do with this
	// platform, and the failure lands at container start with the dive already
	// scheduled. A port you intend to listen on should not be one the kernel
	// thinks it may give away.
	StreamSignalPort int
	StreamMediaPort  int
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

	config.SimImage = os.Getenv("CORAL_CITY_SIM_IMAGE")
	config.StreamHost = os.Getenv("CORAL_CITY_STREAM_HOST")
	config.StreamSignalPort = port("CORAL_CITY_STREAM_SIGNAL_PORT", 18100)
	config.StreamMediaPort = port("CORAL_CITY_STREAM_MEDIA_PORT", 18101)
	if config.SimImage == "" {
		config.SimImage = "coral-city/sim-runtime:r1"
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

// port reads a port from the environment, falling back to what this platform
// chose. A value that is not a number is a mistake worth ignoring loudly rather
// than turning into zero, which would ask the kernel for any port at all.
func port(name string, fallback int) int {
	raw := os.Getenv(name)
	if raw == "" {
		return fallback
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value <= 0 || value > 65535 {
		return fallback
	}
	return value
}
