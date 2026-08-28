package config

import (
	"fmt"
	"os"
	"time"
)

const (
	defaultAddress           = ":8080"
	defaultReadHeaderTimeout = 5 * time.Second
	defaultReadTimeout       = 15 * time.Second
	defaultWriteTimeout      = 30 * time.Second
	defaultIdleTimeout       = 60 * time.Second
	defaultShutdownTimeout   = 10 * time.Second
)

// Config contains the bounded settings needed by the HTTP process.
type Config struct {
	Address           string
	ReadHeaderTimeout time.Duration
	ReadTimeout       time.Duration
	WriteTimeout      time.Duration
	IdleTimeout       time.Duration
	ShutdownTimeout   time.Duration
}

// Load reads environment variables and applies safe development defaults.
func Load() (Config, error) {
	config := Config{Address: valueOrDefault("CORAL_CITY_HTTP_ADDRESS", defaultAddress)}

	settings := []struct {
		name        string
		fallback    time.Duration
		destination *time.Duration
	}{
		{"CORAL_CITY_HTTP_READ_HEADER_TIMEOUT", defaultReadHeaderTimeout, &config.ReadHeaderTimeout},
		{"CORAL_CITY_HTTP_READ_TIMEOUT", defaultReadTimeout, &config.ReadTimeout},
		{"CORAL_CITY_HTTP_WRITE_TIMEOUT", defaultWriteTimeout, &config.WriteTimeout},
		{"CORAL_CITY_HTTP_IDLE_TIMEOUT", defaultIdleTimeout, &config.IdleTimeout},
		{"CORAL_CITY_SHUTDOWN_TIMEOUT", defaultShutdownTimeout, &config.ShutdownTimeout},
	}

	for _, setting := range settings {
		value, err := duration(setting.name, setting.fallback)
		if err != nil {
			return Config{}, err
		}
		*setting.destination = value
	}

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

func valueOrDefault(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}
