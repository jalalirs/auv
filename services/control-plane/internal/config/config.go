// Package config reads the settings a process needs from its environment.
//
// Every setting is named, defaulted where a default is safe, and refused where
// it is not. A process that cannot be configured correctly does not start
// half-configured.
package config

import (
	"fmt"
	"os"
	"strconv"
	"time"
)

const (
	defaultAddress           = ":8080"
	defaultReadHeaderTimeout = 5 * time.Second
	defaultReadTimeout       = 15 * time.Second
	defaultWriteTimeout      = 30 * time.Second
	defaultIdleTimeout       = 60 * time.Second
	defaultShutdownTimeout   = 10 * time.Second

	defaultDatabaseConnections = 16
	defaultSessionLifetime     = 12 * time.Hour
	defaultUploadGrantLifetime = 15 * time.Minute
	defaultPresignLifetime     = 15 * time.Minute
	defaultLeaseDuration       = 60 * time.Second
	defaultReaperInterval      = 15 * time.Second
	defaultMaxAttempts         = 3
	defaultMaxObjectBytes      = int64(8) << 30
)

// Config is everything the control plane needs to run.
type Config struct {
	Address           string
	ReadHeaderTimeout time.Duration
	ReadTimeout       time.Duration
	WriteTimeout      time.Duration
	IdleTimeout       time.Duration
	ShutdownTimeout   time.Duration

	DatabaseURL         string
	DatabaseConnections int32

	StorageEndpoint       string
	StoragePublicEndpoint string
	StorageAccessKey      string
	StorageSecretKey      string
	StorageUseTLS         bool
	StoragePublicUseTLS   bool
	StorageRegion         string
	StorageBucketPrefix   string
	PresignLifetime       time.Duration
	UploadGrantLifetime   time.Duration
	MaxObjectBytes        int64

	SessionLifetime time.Duration
	SecureCookies   bool

	LeaseDuration  time.Duration
	ReaperInterval time.Duration
	MaxAttempts    int
}

// Load reads the environment. Settings with no safe default are required, and
// their absence is reported rather than guessed at.
func Load() (Config, error) {
	config := Config{
		Address:             valueOrDefault("CORAL_CITY_HTTP_ADDRESS", defaultAddress),
		StorageRegion:       valueOrDefault("CORAL_CITY_STORAGE_REGION", "us-east-1"),
		StorageBucketPrefix: os.Getenv("CORAL_CITY_STORAGE_BUCKET_PREFIX"),
		// Where a client reaches storage, when that differs from where this
		// process does. A presigned URL is signed over its host.
		StoragePublicEndpoint: os.Getenv("CORAL_CITY_STORAGE_PUBLIC_ENDPOINT"),
	}

	required := []struct {
		name        string
		destination *string
	}{
		{"CORAL_CITY_DATABASE_URL", &config.DatabaseURL},
		{"CORAL_CITY_STORAGE_ENDPOINT", &config.StorageEndpoint},
		{"CORAL_CITY_STORAGE_ACCESS_KEY", &config.StorageAccessKey},
		{"CORAL_CITY_STORAGE_SECRET_KEY", &config.StorageSecretKey},
	}
	for _, setting := range required {
		value := os.Getenv(setting.name)
		if value == "" {
			return Config{}, fmt.Errorf("%s must be set", setting.name)
		}
		*setting.destination = value
	}

	durations := []struct {
		name        string
		fallback    time.Duration
		destination *time.Duration
	}{
		{"CORAL_CITY_HTTP_READ_HEADER_TIMEOUT", defaultReadHeaderTimeout, &config.ReadHeaderTimeout},
		{"CORAL_CITY_HTTP_READ_TIMEOUT", defaultReadTimeout, &config.ReadTimeout},
		{"CORAL_CITY_HTTP_WRITE_TIMEOUT", defaultWriteTimeout, &config.WriteTimeout},
		{"CORAL_CITY_HTTP_IDLE_TIMEOUT", defaultIdleTimeout, &config.IdleTimeout},
		{"CORAL_CITY_SHUTDOWN_TIMEOUT", defaultShutdownTimeout, &config.ShutdownTimeout},
		{"CORAL_CITY_SESSION_LIFETIME", defaultSessionLifetime, &config.SessionLifetime},
		{"CORAL_CITY_UPLOAD_GRANT_LIFETIME", defaultUploadGrantLifetime, &config.UploadGrantLifetime},
		{"CORAL_CITY_PRESIGN_LIFETIME", defaultPresignLifetime, &config.PresignLifetime},
		{"CORAL_CITY_LEASE_DURATION", defaultLeaseDuration, &config.LeaseDuration},
		{"CORAL_CITY_REAPER_INTERVAL", defaultReaperInterval, &config.ReaperInterval},
	}
	for _, setting := range durations {
		value, err := duration(setting.name, setting.fallback)
		if err != nil {
			return Config{}, err
		}
		*setting.destination = value
	}

	connections, err := number("CORAL_CITY_DATABASE_CONNECTIONS", defaultDatabaseConnections)
	if err != nil {
		return Config{}, err
	}
	config.DatabaseConnections = int32(connections)

	attempts, err := number("CORAL_CITY_MAX_ATTEMPTS", defaultMaxAttempts)
	if err != nil {
		return Config{}, err
	}
	config.MaxAttempts = attempts

	maxObject, err := number64("CORAL_CITY_MAX_OBJECT_BYTES", defaultMaxObjectBytes)
	if err != nil {
		return Config{}, err
	}
	config.MaxObjectBytes = maxObject

	config.StorageUseTLS = boolean("CORAL_CITY_STORAGE_USE_TLS", false)
	config.StoragePublicUseTLS = boolean("CORAL_CITY_STORAGE_PUBLIC_USE_TLS", config.StorageUseTLS)
	config.SecureCookies = boolean("CORAL_CITY_SECURE_COOKIES", false)

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

func number(name string, fallback int) (int, error) {
	raw := os.Getenv(name)
	if raw == "" {
		return fallback, nil
	}
	value, err := strconv.Atoi(raw)
	if err != nil || value <= 0 {
		return 0, fmt.Errorf("%s must be a positive whole number: %q", name, raw)
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

func boolean(name string, fallback bool) bool {
	raw := os.Getenv(name)
	if raw == "" {
		return fallback
	}
	value, err := strconv.ParseBool(raw)
	if err != nil {
		return fallback
	}
	return value
}

func valueOrDefault(name, fallback string) string {
	if value := os.Getenv(name); value != "" {
		return value
	}
	return fallback
}
