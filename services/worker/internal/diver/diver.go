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
	"math"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/jalalirs/auv/services/worker/internal/cache"
	"github.com/jalalirs/auv/services/worker/internal/container"
	"github.com/jalalirs/auv/services/worker/internal/controlplane"
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

	// Everything the run holds, per part. The simulator's card is DeviceIndex
	// as it always was; the controller's may be another.
	Holds []Hold `json:"holds"`
	Needs Needs  `json:"needs"`
	Slot  int    `json:"slot"`
}

// Hold is one part of the run on one card.
type Hold struct {
	Part           string `json:"part"`
	DeviceIndex    int    `json:"deviceIndex"`
	DeviceUUID     string `json:"deviceUuid"`
	GPUMemoryBytes int64  `json:"gpuMemoryBytes"`
}

// Part is what one half of the dive needs of the machine.
type Part struct {
	GPU            bool    `json:"gpu"`
	GPUMemoryBytes int64   `json:"gpuMemoryBytes"`
	CPU            float64 `json:"cpu"`
	MemoryBytes    int64   `json:"memoryBytes"`
}

// Needs is what the dive was admitted needing.
type Needs struct {
	Simulator  Part  `json:"simulator"`
	Controller *Part `json:"controller"`
}

// controllerDevice is the card the controller was given, or -1 for none.
func (c Claimed) controllerDevice() int {
	for _, hold := range c.Holds {
		if hold.Part == "controller" {
			return hold.DeviceIndex
		}
	}
	return -1
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
	// Keep puts one file of the run's recording in storage and names it.
	Keep(ctx context.Context, runID, path, localPath, mediaType string) error
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
	Running(ctx context.Context, id string) (bool, error)
}

// ErrHandedOver is what Dive reports when the agent is stopping and has left
// the dive running for its successor to pick up.
var ErrHandedOver = errors.New("the dive was handed over to the next agent")

// handles is what a successor needs to take over a running dive: written
// beside the brief while the dive runs, read by the agent that starts next.
type handles struct {
	Claimed     Claimed `json:"claimed"`
	Simulator   string  `json:"simulator"`
	Network     string  `json:"network"`
	Autonomy    string  `json:"autonomy,omitempty"`
	BriefDir    string  `json:"briefDir"`
	SignalPort  int     `json:"signalPort"`
	HandedOver  bool    `json:"handedOver"`
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

	// signalPort is where an interactive dive on this host is watched. Offset
	// by the device a dive claimed, so that two dives on one host are watched
	// on different ports rather than the second failing to start on a port the
	// first is using.
	signalPort int

	// RenewEvery is how often the lease is extended. Comfortably shorter than
	// the lease itself, so that one missed renewal does not lose the device.
	renewEvery time.Duration

	// stopping says whether the agent itself is going away, which is the
	// difference between a dive that was ended and one to hand over.
	stopping func() bool
}

// Stopping tells the diver how to know the agent is shutting down.
func (d *Diver) Stopping(is func() bool) { d.stopping = is }


// AnHour is how long an interactive dive is given.
//
// Not because an hour is meaningful, but because a person flying a vehicle
// stops when they stop, and the alternative to a generous bound is no bound at
// all — which is a dive holding a GPU after everybody has gone home.
const anHour = 3600.0

// durationOf is how long a dive should last, in simulated seconds.
//
// An interactive dive lasts until the person leaves, bounded by an hour. A
// batch dive lasts as long as its task needs: the seconds a hold asks for with
// a little settling on top, a mission's time limit, five minutes for a task
// that named neither, and ten seconds — enough to settle a controller and
// record where it sat — for a dive that is for nothing in particular.
func durationOf(claimed Claimed) float64 {
	if claimed.Run.Mode == "interactive" {
		return anHour
	}
	var objective map[string]any
	if len(claimed.Objective) > 0 && json.Unmarshal(claimed.Objective, &objective) == nil && len(objective) > 0 {
		if seconds, ok := objective["seconds"].(float64); ok && seconds > 0 {
			return math.Min(anHour, seconds+5.0)
		}
		if limit, ok := objective["timeLimitS"].(float64); ok && limit > 0 {
			return math.Min(anHour, limit)
		}
		return 300.0
	}
	return 10.0
}

// runtimeUser is the user the simulation runtime runs as, declared in its
// image. Named here because the agent prepares directories the runtime writes
// to, and a directory owned by whoever created it is one the runtime cannot use.
const runtimeUser = 1234

// New builds a diver.
func New(platform Platform, runtime Runtime, packages *cache.Cache,
	simImage, workDir, hostWorkDir, streamHost string,
	signalPort int, renewEvery time.Duration,
	logger *slog.Logger) *Diver {
	return &Diver{
		platform: platform, runtime: runtime, cache: packages,
		simImage: simImage, workDir: workDir, hostWorkDir: hostWorkDir,
		streamHost: streamHost, signalPort: signalPort,
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
	//
	// The dive runs under a context the lease can end, so that a cancellation
	// arriving at the renewal stops the thing being cancelled rather than
	// merely being noted next to it.
	diving, over := context.WithCancel(ctx)
	defer over()
	holding, release := context.WithCancel(ctx)
	go d.hold(holding, claimed.Run.ID, over, log)

	state, outcome, failure := d.perform(diving, claimed, log)
	release()

	// The agent itself is stopping — being redeployed, most likely — and the
	// dive is still running. It is left exactly as it is, with its handles
	// written beside its brief, for the agent that starts next to pick up.
	// Restarting the agent used to end every dive it was running, which meant
	// shipping a fix cost whoever was in the water their dive.
	if state == "handed over" {
		log.Info("dive handed over to the next agent")
		return ErrHandedOver
	}

	// A dive somebody ended did not fail. It did what was asked of it, which
	// was to stop.
	if diving.Err() != nil && ctx.Err() == nil {
		state, failure = "cancelled", ""
	}

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

// hold keeps the lease alive until the dive is over, and ends the dive when the
// platform says it already is.
//
// The renewal is how a cancellation reaches this agent. Nothing pushes to a
// host — it may be behind anything — so the way it learns that somebody ended
// their dive is by being told, next time it says it is still here, that there
// is nothing to be still here for.
//
// Which makes the difference between the platform refusing and the platform not
// answering the important distinction in this loop. Not answering is a blip and
// a lease outlives several. Answering "this run is not in progress" is a fact
// that will not change by asking again — and treating it as a blip is exactly
// what happened: the agent renewed a cancelled run every fifteen seconds
// forever, never finished it, never asked for other work, and held a GPU for a
// dive nobody wanted while somebody waited for a machine.
func (d *Diver) hold(ctx context.Context, runID string, over context.CancelFunc,
	log *slog.Logger) {
	ticker := time.NewTicker(d.renewEvery)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			err := d.platform.Renew(ctx, runID)
			if err == nil || ctx.Err() != nil {
				continue
			}
			if errors.Is(err, controlplane.ErrRunIsOver) {
				log.Info("the dive was ended by whoever asked for it")
				over()
				return
			}
			log.Warn("could not renew the lease", "error", err)
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
		// Whether anything is coming to fly this. The simulator waits for
		// autonomy to appear before it starts, and a dive with none was
		// spending its first minute waiting for a stack that was never going
		// to arrive.
		"autonomyImage": claimed.AutonomyImage,
		// How long there is to be. A batch dive is as long as it was defined to
		// be; an interactive one lasts until the person flying it leaves, which
		// is not a number, so it is given an hour and ended early when they go.
		// Ten seconds is the right length for a dive nobody watches and an
		// absurd one for a dive somebody is trying to fly — it was over before
		// the application could connect.
		"durationSeconds": durationOf(claimed),
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
	// Handed to the simulator, which does not run as root and has things to
	// leave here — the frames it photographed, at least. Without this the
	// directory belongs to this agent and the simulator's writes fail with a
	// permission error that Kit's asynchronous capture swallows: the dive
	// reports taking a photograph, and there is no photograph.
	if err := os.Chown(briefDir, runtimeUser, runtimeUser); err != nil {
		log.Warn("the simulator may not be able to write beside its brief", "error", err)
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
	// What a successor would need to take this dive over, filled in as the
	// pieces come up and written beside the brief.
	kept := handles{Claimed: claimed, BriefDir: briefDir}
	network, err := d.runtime.CreateNetwork(ctx, "coral-dive-"+claimed.Run.ID)
	if err != nil {
		return "failed", nil, fmt.Sprintf("the dive's network could not be created: %v", err)
	}
	defer func() {
		if kept.HandedOver {
			return
		}
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
	// A dive that is for something records what it sees, and seeing needs the
	// renderer: a batch dive with a task runs the application headless rather
	// than the runner alone, so its recording carries frames. It is not
	// watched, so nothing is published.
	rendering := watching || recording(claimed)
	// One port per dive on this host, from the slot the platform gave it; two
	// simulators sharing a card would otherwise be watched on one port.
	signal := d.signalPort + claimed.Slot
	if rendering {
		simulator.Command = []string{"/isaac-sim/kit/kit"}
		simulator.Args = []string{"/isaac-sim/apps/coral_city.kit", "--no-window"}
	}
	if watching {
		// Told the port rather than carrying it, so that what the host
		// publishes, what the run recorded, and what the dive listens on are
		// one number decided in one place.
		simulator.Env = append(simulator.Env,
			fmt.Sprintf("CORAL_CITY_WATCH_PORT=%d", signal))
		simulator.Attach = "bridge"
		simulator.Publish = []container.Port{{Number: signal, Protocol: "tcp"}}
	}

	// Created and started explicitly rather than run in one call, because the
	// agent waits on this container's output before starting the autonomy and
	// so needs a handle on it.
	simID, err := d.runtime.Create(ctx, simulator)
	if err != nil {
		return "failed", nil, fmt.Sprintf("the simulator could not be created: %v", err)
	}
	defer func() {
		if kept.HandedOver {
			return
		}
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
	kept.Simulator, kept.Network, kept.SignalPort = simID, network, signal
	_ = writeHandles(briefDir, kept)
	defer func() {
		if !kept.HandedOver {
			_ = os.Remove(filepath.Join(briefDir, "handles.json"))
		}
	}()

	// What the simulator says while it opens — the place, the seabed, the
	// water, the hull, the vehicle placed — reaches the run as it is said, so
	// whoever is waiting sees the scene opening rather than a minute of
	// nothing. The per-second state lines are left for the end.
	relayed := &relay{seen: map[string]bool{}}
	relaying, stopRelay := context.WithCancel(ctx)
	go d.relayEvents(relaying, claimed.Run.ID, simID, relayed, log)
	defer stopRelay()

	if watching {
		// Only once it is actually listening. Recorded at container start, this
		// told the application where to connect roughly a minute before there
		// was anything there — Isaac Sim takes that long to come up — so the
		// first thing somebody saw after asking to dive was a connection
		// refused. The simulator says when it is ready on its own output, which
		// this agent already reads.
		if err := d.await(ctx, simID, `"event": "watch_open"`,
			"the dive can be watched", log); err != nil {
			log.Warn("the dive never opened a window", "error", err)
		}

		// Where to watch it. Recorded on the run rather than printed, because
		// whoever asked for the dive is not the process that started it and may
		// not be at a terminal at all.
		_ = d.platform.Record(ctx, claimed.Run.ID, "stream_open", nil, map[string]any{
			"host":       d.streamHost,
			"signalPort": signal,
			"transport":  "coral",
		})
		log.Info("the dive can be watched", "host", d.streamHost, "signalPort", signal)
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
			kept.Autonomy = autonomy
			_ = writeHandles(briefDir, kept)
			defer func() {
				if !kept.HandedOver {
					d.landFlyer(ctx, claimed.Run.ID, autonomy, log)
				}
			}()
		}
	}

	code, err := d.runtime.Wait(ctx, simID)
	elapsed := time.Since(started)
	ended := false
	if err != nil {
		stopping, stop := context.WithTimeout(context.WithoutCancel(ctx), 60*time.Second)
		defer stop()
		if ctx.Err() == nil {
			_ = d.runtime.Stop(stopping, simID, 10*time.Second)
			return "failed", nil, fmt.Sprintf("the simulator did not finish: %v", err)
		}
		if d.stopping != nil && d.stopping() {
			// Not the dive being ended: this agent going away. Leave the
			// simulator, the autonomy and the network as they are, mark the
			// handles, and let the next agent take over.
			kept.HandedOver = true
			_ = writeHandles(briefDir, kept)
			return "handed over", nil, ""
		}
		// Ended by whoever asked for it. The simulator is asked to stop and
		// given time to close the dive — flush its recording, say where the
		// vehicle settled — because a dive somebody surfaced from is a dive
		// that happened, and what it left is worth keeping.
		ended = true
		_ = d.runtime.Stop(stopping, simID, 20*time.Second)
		ctx = stopping
		code = 0
	}
	output, _ := d.runtime.Logs(ctx, simID, 400)
	result := container.Result{ExitCode: code, Logs: output}

	// What the simulator said, kept as run events. Without this the trajectory
	// exists only in a container's output and the container is gone: a dive
	// that ran and left no record of what happened is a dive nobody can learn
	// anything from, which is most of the point of running it.
	stopRelay()
	summary := d.keep(ctx, claimed.Run.ID, result.Logs, relayed, log)
	if files := d.keepRecording(ctx, claimed.Run.ID, filepath.Join(briefDir, "recording"), log); files > 0 {
		summary["recording"] = map[string]any{"files": files}
	}

	if result.ExitCode != 0 && !ended {
		return "failed", map[string]any{
			"exitCode": result.ExitCode, "seconds": elapsed.Seconds(),
		}, fmt.Sprintf("the simulator exited %d", result.ExitCode)
	}

	outcome = map[string]any{"seconds": elapsed.Seconds(), "exitCode": 0}
	for key, value := range summary {
		outcome[key] = value
	}
	if ended {
		return "cancelled", outcome, ""
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
func (d *Diver) keep(ctx context.Context, runID, output string, relayed *relay, log *slog.Logger) map[string]any {
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
		// Already relayed while the dive ran: counted, not recorded twice —
		// but what it said about how the dive ended still goes in the summary.
		if relayed != nil && relayed.was(line) {
			kept++
			if kind == "settled" || kind == "succeeded" || kind == "stopped" {
				for key, value := range reported {
					summary[key] = value
				}
			}
			continue
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
		// Bounded to what it was admitted needing, because a stack in a loop
		// should not take the host down with it. What it was admitted needing
		// is what its stack declared, or the platform's default of two
		// processors and four gigabytes.
		MemoryBytes: controllerMemory(claimed),
		CPUs:        controllerCPUs(claimed),
		// The dive's own network: the vehicle is on it, nothing else is, and
		// being internal it has no route to the host and none back in.
		Attach: network,
	}
	if device := claimed.controllerDevice(); device >= 0 {
		// Inference needs a card, and the scheduler said which: the
		// simulator's when it fits beside it, another when it does not.
		spec.GPUs = []string{fmt.Sprint(device)}
	} else if claimed.AutonomyGPU {
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
		"rosDomainId": claimed.ROSDomainID, "gpu": len(spec.GPUs) > 0,
		"device": claimed.controllerDevice(), "cpus": spec.CPUs, "memoryBytes": spec.MemoryBytes,
	})
	return id, nil
}

func controllerMemory(claimed Claimed) int64 {
	if claimed.Needs.Controller != nil && claimed.Needs.Controller.MemoryBytes > 0 {
		return claimed.Needs.Controller.MemoryBytes
	}
	return 4 << 30
}

func controllerCPUs(claimed Claimed) float64 {
	if claimed.Needs.Controller != nil && claimed.Needs.Controller.CPU > 0 {
		return claimed.Needs.Controller.CPU
	}
	return 2
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
func (d *Diver) awaitVehicle(ctx context.Context, simID string, log *slog.Logger) error {
	if err := d.await(ctx, simID, `"event": "bridge_open"`,
		"the vehicle is publishing", log); err != nil {
		return err
	}
	return nil
}

// await waits for the simulator to say something on its own output.
//
// Polling a log is cruder than being told, and it is honest: the simulator is
// the only thing that knows when it is ready, the agent already reads what it
// says, and inventing a side channel for one fact would be a second thing to
// keep working.
//
// Generous, because what is being waited for is a simulator opening a scene
// that may be hundreds of megabytes on a machine that may be busy. Waiting too
// little produces a dive that failed for a reason having nothing to do with the
// dive.
func (d *Diver) await(ctx context.Context, simID, marker, said string,
	log *slog.Logger) error {
	deadline := time.Now().Add(5 * time.Minute)

	for time.Now().Before(deadline) {
		if err := ctx.Err(); err != nil {
			return err
		}
		output, err := d.runtime.Logs(ctx, simID, 400)
		if err == nil && strings.Contains(output, marker) {
			log.Info(said)
			return nil
		}
		if err == nil && strings.Contains(output, `"event": "bridge_unavailable"`) {
			return fmt.Errorf("the vehicle could not open its side of the boundary")
		}
		if err == nil && strings.Contains(output, `"event": "watch_unavailable"`) {
			return fmt.Errorf("the dive could not open a window to be watched through")
		}
		select {
		case <-ctx.Done():
			return ctx.Err()
		case <-time.After(2 * time.Second):
		}
	}
	return fmt.Errorf("the simulator did not report %s within five minutes", said)
}


// keepRecording puts what the dive left in its recording directory into
// storage, file by file, and names each against the run. Best effort: a file
// that will not upload is logged and the rest still go, because a recording
// with one frame missing is worth more than none.
func (d *Diver) keepRecording(ctx context.Context, runID, root string, log *slog.Logger) int {
	if _, err := os.Stat(root); err != nil {
		return 0
	}
	kept, failed := 0, 0
	keeping, stop := context.WithTimeout(context.WithoutCancel(ctx), 10*time.Minute)
	defer stop()
	_ = filepath.WalkDir(root, func(path string, entry os.DirEntry, err error) error {
		if err != nil || entry.IsDir() {
			return nil
		}
		relative, err := filepath.Rel(root, path)
		if err != nil {
			return nil
		}
		relative = filepath.ToSlash(relative)
		if err := d.platform.Keep(keeping, runID, relative, path, mediaTypeOf(relative)); err != nil {
			failed++
			if failed <= 3 {
				log.Warn("a recording file could not be kept", "path", relative, "error", err)
			}
			return nil
		}
		kept++
		return nil
	})
	log.Info("recording kept", "files", kept, "failed", failed)
	_ = d.platform.Record(keeping, runID, "recording_kept", nil, map[string]any{"files": kept, "failed": failed})
	return kept
}

// mediaTypeOf is the media type a recording file is stored under, by name.
func mediaTypeOf(path string) string {
	switch strings.ToLower(filepath.Ext(path)) {
	case ".jpg", ".jpeg":
		return "image/jpeg"
	case ".png":
		return "image/png"
	case ".json":
		return "application/json"
	case ".jsonl":
		return "application/x-ndjson"
	case ".csv":
		return "text/csv"
	default:
		return "application/octet-stream"
	}
}


// recording says whether a dive will leave a recording: it does when it is
// for something, which is what the objective says.
func recording(claimed Claimed) bool {
	var objective map[string]any
	return len(claimed.Objective) > 0 && json.Unmarshal(claimed.Objective, &objective) == nil && len(objective) > 0
}


// relay remembers which of the simulator's lines have already reached the run.
type relay struct {
	mu   sync.Mutex
	seen map[string]bool
}

func (r *relay) was(line string) bool {
	r.mu.Lock()
	defer r.mu.Unlock()
	return r.seen[line]
}

func (r *relay) mark(line string) {
	r.mu.Lock()
	defer r.mu.Unlock()
	r.seen[line] = true
}

// relayEvents records the simulator's events as they appear on its output,
// every second, until told to stop. State lines, one a second for the whole
// dive, are left for the end; everything else — the scene opening, the task
// set, a photograph — is what somebody waiting wants to see now.
func (d *Diver) relayEvents(ctx context.Context, runID, simID string, relayed *relay, log *slog.Logger) {
	for {
		select {
		case <-ctx.Done():
			return
		case <-time.After(time.Second):
		}
		output, err := d.runtime.Logs(ctx, simID, 400)
		if err != nil {
			continue
		}
		for _, line := range strings.Split(output, "\n") {
			line = strings.TrimSpace(line)
			if !strings.HasPrefix(line, "{") || relayed.was(line) {
				continue
			}
			var reported map[string]any
			if err := json.Unmarshal([]byte(line), &reported); err != nil {
				continue
			}
			kind, ok := reported["event"].(string)
			if !ok || kind == "state" {
				continue
			}
			delete(reported, "event")
			var simulated *float64
			if at, ok := reported["t"].(float64); ok {
				simulated = &at
			}
			if err := d.platform.Record(ctx, runID, kind, simulated, reported); err != nil {
				log.Warn("could not relay what the simulator said", "kind", kind, "error", err)
				continue
			}
			relayed.mark(line)
		}
	}
}


// ── Handing over ─────────────────────────────────────────────────────────────

func writeHandles(briefDir string, kept handles) error {
	encoded, err := json.MarshalIndent(kept, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(briefDir, "handles.json"), encoded, 0o644)
}

// Adopt picks up the dives the previous agent left running, one goroutine
// each, and attends them to their end as if this agent had started them.
func (d *Diver) Adopt(ctx context.Context, wg *sync.WaitGroup) int {
	entries, err := os.ReadDir(d.workDir)
	if err != nil {
		return 0
	}
	adopted := 0
	for _, entry := range entries {
		if !entry.IsDir() || !strings.HasPrefix(entry.Name(), "run_") {
			continue
		}
		raw, err := os.ReadFile(filepath.Join(d.workDir, entry.Name(), "handles.json"))
		if err != nil {
			continue
		}
		var kept handles
		if err := json.Unmarshal(raw, &kept); err != nil || !kept.HandedOver || kept.Simulator == "" {
			continue
		}
		running, err := d.runtime.Running(ctx, kept.Simulator)
		if err != nil || !running {
			// Gone while nobody was watching. Nothing to attend; the platform's
			// lease will expire it, and the handles are stale.
			_ = os.Remove(filepath.Join(d.workDir, entry.Name(), "handles.json"))
			continue
		}
		kept.BriefDir = filepath.Join(d.workDir, entry.Name())
		adopted++
		wg.Add(1)
		go func(kept handles) {
			defer wg.Done()
			if err := d.resume(ctx, kept); err != nil && !errors.Is(err, ErrHandedOver) {
				d.logger.Error("could not attend an adopted dive", "runId", kept.Claimed.Run.ID, "error", err)
			}
		}(kept)
	}
	return adopted
}

// resume attends a dive another agent started: renews its lease, relays what
// the simulator says, waits for it to end, keeps what it left, and reports.
func (d *Diver) resume(ctx context.Context, kept handles) error {
	claimed := kept.Claimed
	log := d.logger.With("runId", claimed.Run.ID, "device", claimed.DeviceUUID, "adopted", true)
	log.Info("dive adopted from the previous agent", "simulator", kept.Simulator[:12])
	kept.HandedOver = false
	_ = writeHandles(kept.BriefDir, kept)

	diving, over := context.WithCancel(ctx)
	defer over()
	holding, release := context.WithCancel(ctx)
	go d.hold(holding, claimed.Run.ID, over, log)
	_ = d.platform.Record(ctx, claimed.Run.ID, "adopted", nil, map[string]any{"by": "the agent that started next"})

	relayed := &relay{seen: map[string]bool{}}
	relaying, stopRelay := context.WithCancel(diving)
	go d.relayEvents(relaying, claimed.Run.ID, kept.Simulator, relayed, log)

	started := time.Now()
	code, err := d.runtime.Wait(diving, kept.Simulator)
	release()
	stopRelay()
	ended := false
	if err != nil {
		stopping, stop := context.WithTimeout(context.WithoutCancel(ctx), 60*time.Second)
		defer stop()
		if d.stopping != nil && d.stopping() {
			kept.HandedOver = true
			_ = writeHandles(kept.BriefDir, kept)
			return ErrHandedOver
		}
		ended = true
		_ = d.runtime.Stop(stopping, kept.Simulator, 20*time.Second)
		ctx = stopping
		code = 0
	}
	output, _ := d.runtime.Logs(ctx, kept.Simulator, 400)
	summary := d.keep(ctx, claimed.Run.ID, output, relayed, log)
	if files := d.keepRecording(ctx, claimed.Run.ID, filepath.Join(kept.BriefDir, "recording"), log); files > 0 {
		summary["recording"] = map[string]any{"files": files}
	}
	if kept.Autonomy != "" {
		d.landFlyer(ctx, claimed.Run.ID, kept.Autonomy, log)
	}
	removing, stopRemoving := context.WithTimeout(context.WithoutCancel(ctx), 30*time.Second)
	defer stopRemoving()
	_ = d.runtime.Remove(removing, kept.Simulator)
	if kept.Network != "" {
		_ = d.runtime.RemoveNetwork(removing, kept.Network)
	}
	_ = os.Remove(filepath.Join(kept.BriefDir, "handles.json"))

	outcome := map[string]any{"seconds": time.Since(started).Seconds(), "exitCode": code, "adopted": true}
	for key, value := range summary {
		outcome[key] = value
	}
	state, failure := "succeeded", ""
	if ended {
		state = "cancelled"
	} else if code != 0 {
		state, failure = "failed", fmt.Sprintf("the simulator exited %d", code)
	}
	reporting, stop := context.WithTimeout(context.WithoutCancel(ctx), 30*time.Second)
	defer stop()
	if err := d.platform.Finish(reporting, claimed.Run.ID, state, outcome, failure); err != nil {
		log.Error("could not report how the adopted dive ended", "state", state, "error", err)
		return err
	}
	log.Info("adopted dive ended", "state", state)
	return nil
}
