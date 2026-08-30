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
	Create(ctx context.Context, spec container.Spec) (string, error)
	Pull(ctx context.Context, image string) error
	Present(ctx context.Context, image string) error
	Start(ctx context.Context, id string) error
	Wait(ctx context.Context, id string) (int, error)
	Stop(ctx context.Context, id string, grace time.Duration) error
	Logs(ctx context.Context, id string, lines int) (string, error)
	Remove(ctx context.Context, id string) error
	CreateNetwork(ctx context.Context, name string) (string, error)
	RemoveNetwork(ctx context.Context, id string) error
	JoinNetwork(ctx context.Context, network, id string) error
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

	// streamHost is the address a person watching an interactive dive connects
	// to. A property of the host rather than of the platform: this agent knows
	// which machine it is running on, and the control plane does not.
	streamHost string

	// RenewEvery is how often the lease is extended. Comfortably shorter than
	// the lease itself, so that one missed renewal does not lose the device.
	renewEvery time.Duration
}

// The ports Coral City streams on. Named here and set in the application to the
// same numbers; a viewer is told them rather than left to guess, and they are
// published unchanged so that what the run recorded is what the host listens on.
const (
	signalPort = 49100
	streamPort = 47998
)

// New builds a diver.
func New(platform Platform, runtime Runtime, packages *cache.Cache,
	simImage, workDir, hostWorkDir, streamHost string, renewEvery time.Duration,
	logger *slog.Logger) *Diver {
	return &Diver{
		platform: platform, runtime: runtime, cache: packages,
		simImage: simImage, workDir: workDir, hostWorkDir: hostWorkDir,
		streamHost: streamHost, renewEvery: renewEvery, logger: logger,
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
		// Whether anything is flying this vehicle. A dive that is flown paces
		// itself to real time so the controller has time to exist in; one that
		// is not runs as fast as the machine allows.
		"autonomy": claimed.AutonomyImage != "",
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

	// Fetched if this host has not got it. The runtime lives in the registry
	// rather than as a local tag, because a local tag is a name anything with a
	// docker socket can remove and on a shared host things do.
	if err := d.runtime.Present(ctx, d.simImage); err != nil {
		log.Info("fetching the simulation runtime", "image", d.simImage)
		if err := d.runtime.Pull(ctx, d.simImage); err != nil {
			return "failed", nil, fmt.Sprintf("the simulation runtime could not be fetched: %v", err)
		}
	}

	// A network for this dive and nothing else, created before either half of
	// it. Internal, so there is no route off it in either direction.
	network, err := d.runtime.CreateNetwork(ctx, "coral-dive-"+claimed.Run.ID)
	if err != nil {
		return "failed", nil, fmt.Sprintf("the dive's network could not be created: %v", err)
	}
	defer func() {
		removing, stop := context.WithTimeout(context.WithoutCancel(ctx), 30*time.Second)
		defer stop()
		if err := d.runtime.RemoveNetwork(removing, network); err != nil {
			log.Warn("the dive's network could not be removed", "error", err)
		}
	}()

	log.Info("starting the simulator", "image", d.simImage, "city", city, "vehicle", vehicle,
		"autonomy", claimed.AutonomyImage)

	// Where the autonomy will find the vehicle. Docker resolves a container's
	// name on the network it is attached to, so this is an address on the
	// dive's network and nowhere else.
	vehicleHost := "coral-sim-" + claimed.Run.ID

	simulator := container.Spec{
		Image: d.simImage,
		Env: []string{
			// The licence is accepted by whoever runs this, and the platform
			// runs it on an operator's behalf.
			"ACCEPT_EULA=Y",
			"PRIVACY_CONSENT=Y",
			// Two dives on one host must not hear each other over DDS, and the
			// vehicle must scope discovery the same way its autonomy does or
			// they will not find one another.
			"ROS_DOMAIN_ID=" + fmt.Sprint(claimed.ROSDomainID),
			// No multicast. The dive's network is internal — no route off it
			// in either direction — and an internal bridge does not carry the
			// multicast that automatic discovery is built on, so a vehicle
			// left to announce itself that way announces to nobody.
			//
			// It does not need to. The autonomy is told where the vehicle is
			// and introduces itself directly, which is what happens when you
			// point a stack at a real vehicle, and the vehicle learns of it
			// from the introduction. Only one side has to know, and it has to
			// be this one that is not told: the simulator starts first, and a
			// peer named before it exists cannot be resolved.
			"ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST",
			"ROS_LOG_DIR=/tmp/ros",
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
		GPUs:   []string{fmt.Sprint(claimed.DeviceIndex)},
		Name:   vehicleHost,
		Attach: network,
	}

	// An interactive dive is watched, and the machine it is watched from is not
	// this one. So the simulator runs Coral City rather than the headless
	// runner, and the stream is published to the host.
	//
	// It is put on an ordinary network as well as the dive's own, because a
	// port cannot be published from a network with no route off it. That is the
	// simulator only: it is ours, and the thing being kept from the outside is
	// the autonomy, which stays on the internal network and nothing else.
	watching := claimed.Run.Mode == "interactive"
	if watching {
		simulator.Command = []string{"/isaac-sim/kit/kit"}
		simulator.Args = []string{"/isaac-sim/apps/coral_city.kit", "--no-window"}
		simulator.Attach = "bridge"
		simulator.Publish = []container.Port{
			{Number: signalPort, Protocol: "tcp"},
			{Number: streamPort, Protocol: "udp"},
		}
	}

	// Created and started explicitly rather than run in one call, because the
	// agent waits on this container's output before starting the autonomy and
	// so needs a handle on it.
	simID, err := d.runtime.Create(ctx, simulator)
	if err != nil {
		return "failed", nil, fmt.Sprintf("the simulator could not be created: %v", err)
	}
	defer func() {
		removing, stop := context.WithTimeout(context.WithoutCancel(ctx), 30*time.Second)
		defer stop()
		_ = d.runtime.Remove(removing, simID)
	}()

	if watching {
		// Joined before it is started, so that the vehicle is on the dive's
		// network by the time it announces itself. Attaching afterwards would
		// mean a window in which it is publishing where its autonomy cannot
		// hear it.
		if err := d.runtime.JoinNetwork(ctx, network, simID); err != nil {
			return "failed", nil, fmt.Sprintf("the simulator could not join the dive's network: %v", err)
		}
	}

	if err := d.runtime.Start(ctx, simID); err != nil {
		return "failed", nil, fmt.Sprintf("the simulator could not be started: %v", err)
	}

	if watching {
		// Where to watch it. Recorded on the run rather than printed, because
		// whoever asked for the dive is not the process that started it and may
		// not be at a terminal at all.
		_ = d.platform.Record(ctx, claimed.Run.ID, "stream_open", nil, map[string]any{
			"host":       d.streamHost,
			"signalPort": signalPort,
			"streamPort": streamPort,
			"transport":  "webrtc",
		})
		log.Info("the dive can be watched", "host", d.streamHost, "signalPort", signalPort)
	}

	// Somebody's own program, on the dive's network and no other — and started
	// only once the vehicle is actually publishing.
	//
	// Order matters here in a way that is not obvious and cost a long time to
	// find. A controller started first finds nobody and does not discover the
	// vehicle when it appears sixty seconds later; started afterwards it sees
	// every topic at once. Whatever the mechanism inside DDS, the behaviour is
	// the one reality already has: nobody starts the controller before the
	// vehicle is powered.
	if claimed.AutonomyImage != "" {
		if err := d.awaitVehicle(ctx, simID, log); err != nil {
			log.Warn("the vehicle never came up; the dive continues untended", "error", err)
			_ = d.platform.Record(ctx, claimed.Run.ID, "autonomy_skipped", nil,
				map[string]any{"why": err.Error()})
			claimed.AutonomyImage = ""
		}
	}
	if claimed.AutonomyImage != "" {
		autonomy, err := d.flyer(ctx, claimed, network, vehicleHost, log)
		if err != nil {
			log.Warn("the autonomy would not start; the dive continues untended",
				"error", err)
			_ = d.platform.Record(ctx, claimed.Run.ID, "autonomy_failed", nil,
				map[string]any{"why": err.Error()})
		} else {
			defer d.landFlyer(ctx, claimed.Run.ID, autonomy, log)
		}
	}

	code, err := d.runtime.Wait(ctx, simID)
	elapsed := time.Since(started)
	if err != nil {
		stopping, stop := context.WithTimeout(context.WithoutCancel(ctx), 30*time.Second)
		defer stop()
		_ = d.runtime.Stop(stopping, simID, 10*time.Second)
		return "failed", nil, fmt.Sprintf("the simulator did not finish: %v", err)
	}
	output, _ := d.runtime.Logs(ctx, simID, 400)
	result := container.Result{ExitCode: code, Logs: output}

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

// flyer starts the autonomy container beside the simulator.
//
// It is untrusted code — somebody else's program, on this host, holding a GPU —
// so it gets nothing it does not need. No docker socket, no host network, no
// egress: it talks to the vehicle over DDS on the loopback of the network
// namespace it shares with the simulator, and to nothing else. A stack that
// wanted to reach the internet would be a stack doing something other than
// flying a vehicle.
func (d *Diver) flyer(ctx context.Context, claimed Claimed, network, vehicleHost string,
	log *slog.Logger) (string, error) {
	image := claimed.AutonomyImage + "@" + claimed.AutonomyDigest

	spec := container.Spec{
		Image: image,
		Name:  "coral-autonomy-" + claimed.Run.ID,
		Env: []string{
			// The same domain as the vehicle, so they hear each other; a domain
			// of their own, so no other dive on this host does.
			"ROS_DOMAIN_ID=" + fmt.Sprint(claimed.ROSDomainID),
			// Told where the vehicle is rather than left to find it. The
			// dive's network is internal and carries no multicast, so nothing
			// is discovered by announcement; this introduces itself to the
			// vehicle directly, and the vehicle learns of it from that.
			//
			// It is also how a stack reaches a real vehicle, which is the
			// point: nothing here is a simulator-only arrangement.
			//
			// ROS_LOCALHOST_ONLY did this sort of thing and is deprecated in
			// Jazzy; the range is what replaced it, and setting both would
			// make the old one win and the new one be ignored.
			"ROS_AUTOMATIC_DISCOVERY_RANGE=LOCALHOST",
			"ROS_STATIC_PEERS=" + vehicleHost,
			// The root filesystem is read-only, because this is somebody
			// else's program running on our host. ROS insists on a log
			// directory and gets the bounded temporary one, which is writable
			// and is thrown away with the container.
			"ROS_LOG_DIR=/tmp/ros",
			"HOME=/tmp",
		},
		// Bounded, because a stack in a loop should not take the host down with
		// it. A vehicle controller that needs more than this is doing something
		// other than controlling a vehicle.
		MemoryBytes: 4 << 30,
		CPUs:        2,
		// The dive's own network: the vehicle is on it, nothing else is, and
		// being internal it has no route to the host and none back in.
		Attach: network,
	}
	if claimed.AutonomyGPU {
		// Inference needs a device, and on a single-GPU host it shares the one
		// the simulator is using rather than taking a second.
		spec.GPUs = []string{fmt.Sprint(claimed.DeviceIndex)}
	}

	// Autonomy comes from a registry, unlike this platform's own images, which
	// are built on the host that runs them. Pinned by digest, so pulling it
	// fetches exactly what the dive named and nothing that has since moved.
	if err := d.runtime.Present(ctx, image); err != nil {
		log.Info("fetching the autonomy", "image", image)
		if err := d.runtime.Pull(ctx, image); err != nil {
			return "", fmt.Errorf("fetching %s: %w", image, err)
		}
	}

	id, err := d.runtime.Create(ctx, spec)
	if err != nil {
		return "", err
	}
	if err := d.runtime.Start(ctx, id); err != nil {
		_ = d.runtime.Remove(ctx, id)
		return "", err
	}

	log.Info("autonomy flying", "image", image, "container", id[:12])
	_ = d.platform.Record(ctx, claimed.Run.ID, "autonomy_started", nil, map[string]any{
		"image": claimed.AutonomyImage, "digest": claimed.AutonomyDigest,
		"rosDomainId": claimed.ROSDomainID, "gpu": claimed.AutonomyGPU,
	})
	return id, nil
}

// landFlyer stops the autonomy container and keeps what it said.
//
// What it said is often the only account of why a dive went the way it did —
// the vehicle's trajectory says what happened and the controller's log says
// what it thought was happening — so it is recorded rather than discarded with
// the container.
func (d *Diver) landFlyer(ctx context.Context, runID, id string, log *slog.Logger) {
	stopping, stop := context.WithTimeout(context.WithoutCancel(ctx), 45*time.Second)
	defer stop()

	if output, err := d.runtime.Logs(stopping, id, 100); err == nil && output != "" {
		lines := strings.Split(strings.TrimSpace(output), "\n")
		if len(lines) > 40 {
			lines = lines[len(lines)-40:]
		}
		_ = d.platform.Record(stopping, runID, "autonomy_said", nil, map[string]any{
			"lines": lines,
		})
	}
	if err := d.runtime.Stop(stopping, id, 5*time.Second); err != nil {
		log.Warn("could not stop the autonomy", "container", id[:12], "error", err)
	}
	_ = d.runtime.Remove(stopping, id)
}

// awaitVehicle waits until the simulator is publishing before anything is
// started to talk to it.
//
// The simulator says so on its own output, which the agent is already reading.
// Polling that is cruder than being told, and it is honest: there is nothing
// else that knows, and inventing a side channel for one fact would be a second
// thing to keep working.
func (d *Diver) awaitVehicle(ctx context.Context, simID string, log *slog.Logger) error {
	// Generous, because it is waiting for a simulator to open a scene that may
	// be hundreds of megabytes, and a dive that waited too little would run
	// untended for a reason that had nothing to do with the autonomy.
	deadline := time.Now().Add(5 * time.Minute)

	for time.Now().Before(deadline) {
		if err := ctx.Err(); err != nil {
			return err
		}
		output, err := d.runtime.Logs(ctx, simID, 200)
		if err == nil && strings.Contains(output, `"event": "bridge_open"`) {
			log.Info("the vehicle is publishing")
			return nil
		}
		if err == nil && strings.Contains(output, `"event": "bridge_unavailable"`) {
			return fmt.Errorf("the vehicle could not open its side of the boundary")
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(2 * time.Second):
		}
	}
	return fmt.Errorf("the vehicle did not start publishing within five minutes")
}
