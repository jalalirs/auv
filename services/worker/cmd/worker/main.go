// Command worker takes work from the control plane and runs it.
//
// It holds authority over the work queue and over nothing else: it cannot read
// a city, contribute a layer, or act for an organisation. Everything it reaches
// while running a job, it reaches through the lease it holds on that job.
package main

import (
	"context"
	"errors"
	"log/slog"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/jalalirs/auv/services/worker/internal/config"
	"github.com/jalalirs/auv/services/worker/internal/container"
	"github.com/jalalirs/auv/services/worker/internal/controlplane"
	"github.com/jalalirs/auv/services/worker/internal/runner"
)

func main() {
	logger := slog.New(slog.NewJSONHandler(os.Stdout, nil))
	if err := run(logger); err != nil {
		logger.Error("worker stopped", "error", err)
		os.Exit(1)
	}
}

func run(logger *slog.Logger) error {
	settings, err := config.Load()
	if err != nil {
		return err
	}

	runtime := container.Open(settings.DockerSocket)
	startup, cancelStartup := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancelStartup()
	if err := runtime.Reachable(startup); err != nil {
		return err
	}

	if err := os.MkdirAll(settings.WorkDir, 0o755); err != nil {
		return err
	}

	client := controlplane.New(settings.ControlPlaneURL, settings.Credential, settings.RequestTimeout)
	execute := runner.New(client, runtime, settings, logger)

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()

	logger.Info("worker ready",
		"controlPlane", settings.ControlPlaneURL,
		"target", settings.TargetName,
		"workDir", settings.WorkDir)

	idle := time.NewTimer(0)
	defer idle.Stop()

	for {
		select {
		case <-ctx.Done():
			logger.Info("worker stopping")
			return nil
		case <-idle.C:
		}

		// Taking work is bounded; running it is not, because a job runs for as
		// long as its declared walltime allows.
		take, cancelTake := context.WithTimeout(ctx, settings.RequestTimeout)
		lease, err := client.Take(take, settings.TargetName)
		cancelTake()

		switch {
		case err != nil:
			logger.Warn("could not take work", "error", err)
			idle.Reset(settings.PollInterval)
			continue
		case lease == nil:
			idle.Reset(settings.PollInterval)
			continue
		}

		logger.Info("took work", "jobId", lease.Job.ID, "attemptId", lease.AttemptID)
		if err := execute.Run(ctx, lease); err != nil {
			if errors.Is(err, runner.ErrLeaseLost) {
				logger.Warn("the platform reclaimed this work while it was running",
					"jobId", lease.Job.ID, "attemptId", lease.AttemptID)
			} else {
				logger.Error("could not complete work",
					"jobId", lease.Job.ID, "attemptId", lease.AttemptID, "error", err)
			}
		}
		// There may be more work waiting, so the next attempt is immediate.
		idle.Reset(0)
	}
}
