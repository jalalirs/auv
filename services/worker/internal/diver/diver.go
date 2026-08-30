// Package diver runs one dive.
//
// It takes what the control plane handed over, makes the packages present on
// this host, starts the simulator on the device it was given, keeps the lease
// alive while the dive runs, records what happened, and says how it ended —
// then releases the device whether or not anything went well.
//
// The last part is the one worth being careful about. A dive that fails and
// keeps its GPU is worse than one that fails loudly, because the hardware is
// the scarce thing and nobody notices it is gone until somebody else cannot
// run. Every path out of here releases.
package diver

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/worker/internal/cache"
	"github.com/jalalirs/auv/services/worker/internal/container"
)

// Claimed is the dive the control plane handed over.
type Claimed struct {
	Run struct {
		ID             string  `json:"id"`
		DiveID         string  `json:"diveId"`
		Mode           string  `json:"mode"`
		Seed           int64   `json:"seed"`
		RuntimeVersion string  `json:"runtimeVersion"`
		GPUShare       float64 `json:"gpuShare"`
	} `json:"run"`

	CityVersionID    string          `json:"cityVersionId"`
	VehicleVersionID string          `json:"vehicleVersionId"`
	Conditions       json.RawMessage `json:"conditions"`
	InitialState     json.RawMessage `json:"initialState"`
	Objective        json.RawMessage `json:"objective"`

	AutonomyImage  string `json:"autonomyImage"`
	AutonomyDigest string `json:"autonomyDigest"`
	AutonomyGPU    bool   `json:"autonomyWantsGpu"`

	DeviceIndex int    `json:"deviceIndex"`
	DeviceUUID  string `json:"deviceUuid"`
	ROSDomainID int    `json:"rosDomainId"`
}

// Platform is what the diver needs from the control plane.
type Platform interface {
	// RunPackages asks through the run rather than by naming a package,
	// because an agent may see the two packages its dive needs and no others.
	RunPackages(ctx context.Context, runID string) (city, vehicle Package, err error)
	Started(ctx context.Context, runID string) error
	Renew(ctx context.Context, runID string) error
	Record(ctx context.Context, runID, kind string, simulated *float64, detail any) error
	Finish(ctx context.Context, runID, state string, outcome any, failure string) error
}

// Runtime is what it needs from the container runtime.
type Runtime interface {
	Run(ctx context.Context, spec container.Spec) (container.Result, error)
}

// Diver runs dives on one host.
type Diver struct {
	platform Platform
	runtime  Runtime
	cache    *cache.Cache
	logger   *slog.Logger

	// SimImage is what a dive is simulated in. Named by the run's runtime
	// version where one is given, so that a result pinned to a runtime is run
	// by that runtime rather than by whatever this host happens to have.
	simImage string
	workDir  string

	// hostWorkDir is the same directory as workDir, named as the host names it.
	//
	// A bind mount is resolved by the container runtime on the host, and this
	// agent is itself a container: the path it knows a directory by is not the
	// path the daemon will look for. Passing its own path produces a mount of
	// nothing, silently, and a simulator that starts to an empty scene.
	hostWorkDir string

	// RenewEvery is how often the lease is extended. Comfortably shorter than
	// the lease itself, so that one missed renewal does not lose the device.
	renewEvery time.Duration
}

// New builds a diver.
func New(platform Platform, runtime Runtime, packages *cache.Cache,
	simImage, workDir, hostWorkDir string, renewEvery time.Duration,
	logger *slog.Logger) *Diver {
	return &Diver{
		platform: platform, runtime: runtime, cache: packages,
		simImage: simImage, workDir: workDir, hostWorkDir: hostWorkDir,
		renewEvery: renewEvery, logger: logger,
	}
}

// onHost translates a path this agent knows into the path the container
// runtime will resolve it by.
func (d *Diver) onHost(path string) string {
	if d.hostWorkDir == "" || !strings.HasPrefix(path, d.workDir) {
		return path
	}
	return filepath.Join(d.hostWorkDir, strings.TrimPrefix(path, d.workDir))
}

// Dive runs one, and always releases the device.
func (d *Diver) Dive(ctx context.Context, claimed Claimed) error {
	log := d.logger.With("runId", claimed.Run.ID, "device", claimed.DeviceUUID)
	log.Info("dive claimed",
		"mode", claimed.Run.Mode, "seed", claimed.Run.Seed,
		"runtime", claimed.Run.RuntimeVersion, "rosDomain", claimed.ROSDomainID)

	// The lease is held for as long as this function runs and no longer.
	// Cancelling it before reporting the outcome would let the run expire out
	// from under the report.
	holding, release := context.WithCancel(ctx)
	go d.hold(holding, claimed.Run.ID, log)

	state, outcome, failure := d.perform(ctx, claimed, log)
	release()

	// Reported on a context of its own, because the one above may already be
	// cancelled — and a dive whose outcome went unrecorded is a dive nobody can
	// learn anything from.
	reporting, stop := context.WithTimeout(context.WithoutCancel(ctx), 30*time.Second)
	defer stop()
	if err := d.platform.Finish(reporting, claimed.Run.ID, state, outcome, failure); err != nil {
		log.Error("could not report how the dive ended", "state", state, "error", err)
		return err
	}
	log.Info("dive ended", "state", state, "failure", failure)
	return nil
}

// hold keeps the lease alive until the dive is over.
func (d *Diver) hold(ctx context.Context, runID string, log *slog.Logger) {
	ticker := time.NewTicker(d.renewEvery)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if err := d.platform.Renew(ctx, runID); err != nil && ctx.Err() == nil {
				// Not fatal on its own: the lease outlives several renewals, so
				// one failure is a blip and a run of them is a problem the
				// expiry sweep will settle.
				log.Warn("could not renew the lease", "error", err)
			}
		}
	}
}

// perform does the dive and reports what state it ended in.
func (d *Diver) perform(ctx context.Context, claimed Claimed, log *slog.Logger,
) (state string, outcome map[string]any, failure string) {
	started := time.Now()

	cityPackage, vehiclePackage, err := d.platform.RunPackages(ctx, claimed.Run.ID)
	if err != nil {
		return "failed", nil, fmt.Sprintf("could not ask what this dive needs: %v", err)
	}

	city, err := d.sync(ctx, claimed.Run.ID, "city", cityPackage, log)
	if err != nil {
		return "failed", nil, fmt.Sprintf("could not make the place present: %v", err)
	}
	vehicle, err := d.sync(ctx, claimed.Run.ID, "vehicle", vehiclePackage, log)
	if err != nil {
		return "failed", nil, fmt.Sprintf("could not make the vehicle present: %v", err)
	}

	// What the simulator is told about the dive. Written to the work directory
	// rather than passed as arguments because it is a page of JSON, and because
	// a file is something somebody can look at afterwards and see exactly what
	// was run.
	brief := map[string]any{
		"runId":          claimed.Run.ID,
		"diveId":         claimed.Run.DiveID,
		"mode":           claimed.Run.Mode,
		"seed":           claimed.Run.Seed,
		"runtimeVersion": claimed.Run.RuntimeVersion,
		"cityPath":       "/dive/city",
		"vehiclePath":    "/dive/vehicle",
		"conditions":     claimed.Conditions,
		"initialState":   claimed.InitialState,
		"objective":      claimed.Objective,
		"rosDomainId":    claimed.ROSDomainID,
		"deviceIndex":    claimed.DeviceIndex,
	}
	briefDir := filepath.Join(d.workDir, claimed.Run.ID)
	if err := os.MkdirAll(briefDir, 0o755); err != nil {
		return "failed", nil, fmt.Sprintf("could not prepare the work directory: %v", err)
	}
	encoded, err := json.MarshalIndent(brief, "", "  ")
	if err != nil {
		return "failed", nil, fmt.Sprintf("could not write the brief: %v", err)
	}
	if err := os.WriteFile(filepath.Join(briefDir, "dive.json"), encoded, 0o644); err != nil {
		return "failed", nil, fmt.Sprintf("could not write the brief: %v", err)
	}

	if err := d.platform.Started(ctx, claimed.Run.ID); err != nil {
		return "failed", nil, fmt.Sprintf("could not report that the dive started: %v", err)
	}
	_ = d.platform.Record(ctx, claimed.Run.ID, "packages_present", nil, map[string]any{
		"city": city, "vehicle": vehicle,
	})

	image := d.simImage
	log.Info("starting the simulator", "image", image, "city", city, "vehicle", vehicle)

	result, err := d.runtime.Run(ctx, container.Spec{
		Image: image,
		Env: []string{
			// The licence is accepted by whoever runs this, and the platform
			// runs it on an operator's behalf.
			"ACCEPT_EULA=Y",
			"PRIVACY_CONSENT=Y",
			// Two dives on one host must not hear each other over DDS.
			"ROS_DOMAIN_ID=" + fmt.Sprint(claimed.ROSDomainID),
			// Same seed and same packages is the same run. Everything the
			// platform claims about a result rests on the simulator honouring
			// this rather than drawing its own.
			"CORAL_CITY_SEED=" + fmt.Sprint(claimed.Run.Seed),
			"CORAL_CITY_BRIEF=/dive/dive.json",
		},
		// A simulator writes shader and asset caches all over its own
		// installation and cannot start without somewhere to put them.
		WritableRoot: true,
		Mounts: []container.Mount{
			{Source: d.onHost(briefDir), Target: "/dive", ReadOnly: false},
			{Source: d.onHost(city), Target: "/dive/city", ReadOnly: true},
			{Source: d.onHost(vehicle), Target: "/dive/vehicle", ReadOnly: true},
		},
		// The device it was given, and only that one. A dive that could see
		// every GPU on the host could take one another dive is holding.
		GPUs: []string{fmt.Sprint(claimed.DeviceIndex)},
	})

	elapsed := time.Since(started)
	if err != nil {
		return "failed", nil, fmt.Sprintf("the simulator could not be started: %v", err)
	}

	// What the simulator said, kept as run events. Without this the trajectory
	// exists only in a container's output and the container is gone: a dive
	// that ran and left no record of what happened is a dive nobody can learn
	// anything from, which is most of the point of running it.
	summary := d.keep(ctx, claimed.Run.ID, result.Logs, log)

	if result.ExitCode != 0 {
		return "failed", map[string]any{
			"exitCode": result.ExitCode, "seconds": elapsed.Seconds(),
		}, fmt.Sprintf("the simulator exited %d", result.ExitCode)
	}

	outcome = map[string]any{"seconds": elapsed.Seconds(), "exitCode": 0}
	for key, value := range summary {
		outcome[key] = value
	}
	return "succeeded", outcome, ""
}

// Package is one package the platform says this dive needs.
type Package struct {
	VersionID string
	Files     []cache.File
}

// sync makes a package present on this host and says where it put it.
func (d *Diver) sync(ctx context.Context, runID, what string, packaged Package,
	log *slog.Logger) (string, error) {
	versionID := packaged.VersionID
	if len(packaged.Files) == 0 {
		return "", fmt.Errorf("%s %s has no files, so there is nothing to run", what, versionID)
	}

	report, err := d.cache.Sync(ctx, versionID, packaged.Files)
	if err != nil {
		return "", err
	}
	log.Info("package present", "what", what, "version", versionID,
		"fetched", report.Fetched, "held", report.Held,
		"bytes", report.Bytes, "took", report.Took.Round(time.Millisecond))

	_ = d.platform.Record(ctx, runID, "package_synced", nil, map[string]any{
		"what": what, "versionId": versionID,
		"fetched": report.Fetched, "alreadyHeld": report.Held,
		"bytes": report.Bytes, "seconds": report.Took.Seconds(),
	})
	return report.Directory, nil
}

// ErrNothingToDo is what a claim reports when the platform has no work, which
// is the ordinary case rather than a failure.
var ErrNothingToDo = errors.New("nothing to run")

// keep records what the simulator reported, and returns what is worth summarising.
//
// The simulator writes one JSON object per line to its own output rather than
// posting to the control plane. It has no credential and should not have one:
// a simulator that had to authenticate would be a simulator that could be
// locked out of reporting its own results, and the agent is already holding
// the run's lease and already reading this.
//
// Anything that is not one of those objects is the simulator's ordinary noise —
// Isaac Sim says a great deal on the way up — and is left out rather than
// recorded as though it meant something.
func (d *Diver) keep(ctx context.Context, runID, output string, log *slog.Logger) map[string]any {
	summary := map[string]any{}
	kept := 0

	for _, line := range strings.Split(output, "\n") {
		line = strings.TrimSpace(line)
		if !strings.HasPrefix(line, "{") {
			continue
		}
		var reported map[string]any
		if err := json.Unmarshal([]byte(line), &reported); err != nil {
			continue
		}
		kind, ok := reported["event"].(string)
		if !ok {
			continue
		}
		delete(reported, "event")

		var simulated *float64
		if at, ok := reported["t"].(float64); ok {
			simulated = &at
		}
		if err := d.platform.Record(ctx, runID, kind, simulated, reported); err != nil {
			log.Warn("could not record what the simulator said", "kind", kind, "error", err)
			continue
		}
		kept++

		// The last thing it said about where the vehicle got to is what a
		// person asks first.
		if kind == "settled" || kind == "succeeded" {
			for key, value := range reported {
				summary[key] = value
			}
		}
	}

	log.Info("recorded what the simulator said", "events", kept)
	summary["events"] = kept
	return summary
}
