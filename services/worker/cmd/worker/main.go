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

	"github.com/jalalirs/auv/services/worker/internal/cache"
	"github.com/jalalirs/auv/services/worker/internal/config"
	"github.com/jalalirs/auv/services/worker/internal/container"
	"github.com/jalalirs/auv/services/worker/internal/controlplane"
	"github.com/jalalirs/auv/services/worker/internal/diver"
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

	// Packages are cached beside the work directory and shared by every dive
	// on this host, which is the point: a city fetched once is a city fetched.
	packages, err := cache.New(settings.WorkDir, logger)
	if err != nil {
		return err
	}
	if held, bytes, err := packages.Usage(); err == nil {
		logger.Info("package cache", "files", held, "bytes", bytes)
	}
	dive := diver.New(&platform{client}, runtime, packages,
		settings.SimImage, settings.WorkDir, settings.HostWorkDir, settings.StreamHost,
		// Comfortably shorter than the lease, so one missed renewal does not
		// cost the device.
		settings.HeartbeatInterval, logger)

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

		// A dive first: it holds a GPU, and hardware left idle while a job runs
		// is the expensive kind of waiting.
		claim, cancelClaim := context.WithTimeout(ctx, settings.RequestTimeout)
		var claimed diver.Claimed
		claimErr := client.ClaimDive(claim, settings.TargetName, &claimed)
		cancelClaim()

		if claimErr == nil {
			if err := dive.Dive(ctx, claimed); err != nil {
				logger.Error("could not complete a dive",
					"runId", claimed.Run.ID, "error", err)
			}
			idle.Reset(0)
			continue
		}
		if !errors.Is(claimErr, controlplane.ErrNothingToRun) {
			logger.Warn("could not ask for a dive", "error", claimErr)
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

// platform adapts the control-plane client to what a diver needs, so that the
// diver depends on the four things it actually does rather than on the whole
// client.
type platform struct{ client *controlplane.Client }

func (p *platform) RunPackages(ctx context.Context, runID string) (diver.Package, diver.Package, error) {
	city, vehicle, err := p.client.RunPackages(ctx, runID)
	if err != nil {
		return diver.Package{}, diver.Package{}, err
	}
	return convert(city), convert(vehicle), nil
}

func convert(contents controlplane.PackageContents) diver.Package {
	files := make([]cache.File, 0, len(contents.Files))
	for _, file := range contents.Files {
		files = append(files, cache.File{
			Path: file.Path, Digest: file.Digest,
			SizeBytes: file.SizeBytes, MediaType: file.MediaType, URL: file.URL,
		})
	}
	return diver.Package{VersionID: contents.VersionID, Files: files}
}

func (p *platform) Started(ctx context.Context, runID string) error {
	return p.client.DiveStarted(ctx, runID)
}

func (p *platform) Renew(ctx context.Context, runID string) error {
	return p.client.RenewDive(ctx, runID)
}

func (p *platform) Record(ctx context.Context, runID, kind string,
	simulated *float64, detail any) error {
	return p.client.RecordDiveEvent(ctx, runID, kind, simulated, detail)
}

func (p *platform) Finish(ctx context.Context, runID, state string,
	outcome any, failure string) error {
	return p.client.FinishDive(ctx, runID, state, outcome, failure)
}
