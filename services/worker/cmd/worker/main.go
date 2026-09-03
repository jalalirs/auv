// Command worker takes work from the control plane and runs it.
//
// It holds authority over the work queue and over nothing else: it cannot read
// a city, contribute a layer, or act for an organisation. Everything it reaches
// while running a job, it reaches through the lease it holds on that job.
package main

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"runtime"
	"strconv"
	"strings"
	"sync"
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
		settings.StreamSignalPort,
		// Comfortably shorter than the lease, so one missed renewal does not
		// cost the device.
		settings.HeartbeatInterval, logger)

	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	// The diver tells a dive being ended from the agent going away by this.
	dive.Stopping(func() bool { return ctx.Err() != nil })

	logger.Info("worker ready",
		"controlPlane", settings.ControlPlaneURL,
		"target", settings.TargetName,
		"workDir", settings.WorkDir)

	idle := time.NewTimer(0)
	defer idle.Stop()

	// Dives in flight on this host, waited for on the way out so a stop does
	// not abandon a vehicle mid-water without saying so.
	var diving sync.WaitGroup
	defer diving.Wait()

	// Whatever the previous agent left running is picked up first. A dive
	// survives the agent being redeployed under it.
	if adopted := dive.Adopt(ctx, &diving); adopted > 0 {
		logger.Info("adopted dives left by the previous agent", "dives", adopted)
	}

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
		claimErr := client.ClaimDive(claim, settings.TargetName,
			settings.Runtimes(), hostCapacity(), &claimed)
		cancelClaim()

		if claimErr == nil {
			// Beside whatever else is running, not after it. The platform
			// placed this dive knowing what this host already carries; an agent
			// that ran dives one at a time would leave the second card idle
			// while a dive waited for it, which is what it did.
			diving.Add(1)
			go func(claimed diver.Claimed) {
				defer diving.Done()
				if err := dive.Dive(ctx, claimed); err != nil && !errors.Is(err, diver.ErrHandedOver) {
					logger.Error("could not complete a dive",
						"runId", claimed.Run.ID, "error", err)
				}
			}(claimed)
			idle.Reset(2 * time.Second)
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

// hostCapacity is what this machine has: its processors, and its memory as
// the kernel reports it. Read every time rather than once, because it costs
// nothing and a value read once is a value that can be wrong for a year.
func hostCapacity() controlplane.Capacity {
	capacity := controlplane.Capacity{CPU: float64(runtime.NumCPU())}
	if raw, err := os.ReadFile("/proc/meminfo"); err == nil {
		for _, line := range strings.Split(string(raw), "\n") {
			if strings.HasPrefix(line, "MemTotal:") {
				fields := strings.Fields(line)
				if len(fields) >= 2 {
					if kib, err := strconv.ParseInt(fields[1], 10, 64); err == nil {
						capacity.MemoryBytes = kib * 1024
					}
				}
			}
		}
	}
	return capacity
}


// Keep puts one file of a run's recording in storage and names it against the
// run: the bytes are declared by digest, put where the grant says, checked,
// and only then recorded — the same three steps every file the platform holds
// goes through.
func (p *platform) Keep(ctx context.Context, runID, path, localPath, mediaType string) error {
	file, err := os.Open(localPath)
	if err != nil {
		return err
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil {
		return err
	}
	hasher := sha256.New()
	if _, err := io.Copy(hasher, file); err != nil {
		return err
	}
	if _, err := file.Seek(0, io.SeekStart); err != nil {
		return err
	}
	grant, err := p.client.RequestRunUpload(ctx, runID, hex.EncodeToString(hasher.Sum(nil)), mediaType, info.Size())
	if err != nil {
		return err
	}
	request, err := http.NewRequestWithContext(ctx, http.MethodPut, grant.UploadURL, file)
	if err != nil {
		return err
	}
	request.ContentLength = info.Size()
	request.Header.Set("Content-Type", mediaType)
	response, err := http.DefaultClient.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode >= 400 {
		raw, _ := io.ReadAll(io.LimitReader(response.Body, 2048))
		return fmt.Errorf("storage refused the write: %s: %s", response.Status, raw)
	}
	objectID, err := p.client.ConfirmRunUpload(ctx, runID, grant.ID)
	if err != nil {
		return err
	}
	return p.client.RecordArtefact(ctx, runID, path, objectID)
}
