// Command control-plane serves the Coral City platform API.
//
// It owns identity, governance, places, layers, provenance, work, and the
// record of all of it. It runs no scientific work itself: workers lease that.
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/catalog"
	"github.com/jalalirs/auv/services/control-plane/internal/compute"
	"github.com/jalalirs/auv/services/control-plane/internal/config"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/dive"
	"github.com/jalalirs/auv/services/control-plane/internal/exec"
	"github.com/jalalirs/auv/services/control-plane/internal/httpapi"
	"github.com/jalalirs/auv/services/control-plane/internal/identity"
	"github.com/jalalirs/auv/services/control-plane/internal/platform"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
	"github.com/jalalirs/auv/services/control-plane/internal/storage"
)

var (
	version = "development"
	commit  = "unknown"
	builtAt = "unknown"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	// Components that cannot be handed a logger — the transport's last-resort
	// error path among them — still have to be able to say what went wrong.
	slog.SetDefault(logger)
	if err := run(logger); err != nil {
		logger.Error("control plane stopped", "error", err)
		os.Exit(1)
	}
}

func run(logger *slog.Logger) error {
	settings, err := config.Load()
	if err != nil {
		return err
	}

	startup, cancelStartup := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancelStartup()

	pool, err := db.Open(startup, settings.DatabaseURL, settings.DatabaseConnections)
	if err != nil {
		return err
	}
	defer pool.Close()

	blobs, err := storage.OpenBlobs(storage.Settings{
		Endpoint:        settings.StorageEndpoint,
		PublicEndpoint:  settings.StoragePublicEndpoint,
		AccessKey:       settings.StorageAccessKey,
		SecretKey:       settings.StorageSecretKey,
		UseTLS:          settings.StorageUseTLS,
		PublicUseTLS:    settings.StoragePublicUseTLS,
		Region:          settings.StorageRegion,
		BucketPrefix:    settings.StorageBucketPrefix,
		PresignLifetime: settings.PresignLifetime,
	})
	if err != nil {
		return err
	}

	broker := exec.NewBroker(pool)
	identities := identity.NewStore(pool, settings.SessionLifetime)
	objects := storage.NewObjects(pool, blobs, settings.UploadGrantLifetime, settings.MaxObjectBytes)
	recorder := audit.NewRecorder()

	deps := &httpapi.Dependencies{
		Info:            platform.Build(version, commit, builtAt),
		Pool:            pool,
		Identity:        identities,
		Authorizer:      policy.NewAuthorizer(pool),
		Audit:           recorder,
		Catalog:         catalog.NewStore(pool),
		Compute:         compute.NewStore(pool),
		Dives:           dive.NewStore(pool),
		Objects:         objects,
		Blobs:           blobs,
		Broker:          broker,
		Logger:          logger,
		LeaseDuration:   settings.LeaseDuration,
		SessionLifetime: settings.SessionLifetime,
		SecureCookies:   settings.SecureCookies,
	}

	router := httpapi.NewRouter(deps)
	server := httpapi.NewServer(settings, router.Handler(), logger)

	background, stopBackground := context.WithCancel(context.Background())
	defer stopBackground()
	tending := attend(background, logger, broker, identities, settings)

	serverErrors := make(chan error, 1)
	go func() {
		logger.Info("control plane listening",
			"address", settings.Address,
			"version", deps.Info.Version,
			"commit", deps.Info.Commit,
			"routes", len(router.Routes()))
		serverErrors <- server.ListenAndServe()
	}()

	signals := make(chan os.Signal, 1)
	signal.Notify(signals, syscall.SIGINT, syscall.SIGTERM)
	defer signal.Stop(signals)

	select {
	case received := <-signals:
		logger.Info("shutdown requested", "signal", received.String())
	case err := <-serverErrors:
		if err != nil && !errors.Is(err, http.ErrServerClosed) {
			return err
		}
	}

	shutdown, cancel := context.WithTimeout(context.Background(), settings.ShutdownTimeout)
	defer cancel()
	if err := server.Shutdown(shutdown); err != nil {
		return err
	}
	stopBackground()
	<-tending
	return nil
}

// attend runs the work the platform does for itself: reclaiming work from
// workers that stopped reporting, ending work that outran its deadline,
// submitting recurring work whose time has come, and clearing sessions that
// can no longer authenticate anyone.
//
// None of it belongs on a request, and all of it must keep happening whether or
// not anyone is looking.
func attend(ctx context.Context, logger *slog.Logger, broker *exec.Broker, identities *identity.Store, settings config.Config) <-chan struct{} {
	done := make(chan struct{})
	go func() {
		defer close(done)
		ticker := time.NewTicker(settings.ReaperInterval)
		defer ticker.Stop()

		sinceSweep := 0
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
			}

			if reclaimed, err := broker.ReclaimExpiredLeases(ctx, settings.MaxAttempts); err != nil {
				logger.Error("could not reclaim expired leases", "error", err)
			} else if reclaimed > 0 {
				logger.Info("reclaimed work from workers that stopped reporting",
					"attempts", reclaimed)
			}

			if stopped, err := broker.EnforceWalltime(ctx); err != nil {
				logger.Error("could not enforce walltime", "error", err)
			} else if stopped > 0 {
				logger.Info("stopped work past its deadline", "jobs", stopped)
			}

			if submitted, err := broker.RunDueSchedules(ctx); err != nil {
				logger.Error("could not submit recurring work", "error", err)
			} else if submitted > 0 {
				logger.Info("submitted recurring work", "jobs", submitted)
			}

			// Expired sessions are cleared rarely: they authenticate nobody in
			// the meantime, so the only cost of waiting is storage.
			sinceSweep++
			if sinceSweep >= int(time.Hour/settings.ReaperInterval)+1 {
				sinceSweep = 0
				if purged, err := identities.PurgeExpiredSessions(ctx, 24*time.Hour); err != nil {
					logger.Error("could not clear expired sessions", "error", err)
				} else if purged > 0 {
					logger.Info("cleared expired sessions", "sessions", purged)
				}
			}
		}
	}()
	return done
}
