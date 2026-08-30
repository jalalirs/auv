// Package container runs one container and reports what happened.
//
// It speaks the container runtime's HTTP interface over a local socket
// directly, rather than depending on that project's client library: the worker
// needs six calls, and a dependency that large would be harder to audit than
// the calls themselves.
package container

import (
	"bytes"
	"context"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"net/http"
	"net/url"
	"strings"
	"time"
)

// The interface version is negotiated rather than fixed. Daemons refuse a
// version older than they support, and hosts in this platform's own deployment
// differ by several releases, so a constant would work on one host and fail on
// another.
//
// The negotiated version is never allowed above the newest this worker was
// written against, so a future daemon cannot silently change what these calls
// mean.
const (
	minimumVersion   = "1.43"
	preferredVersion = "1.44"
)

// Runtime is a local container runtime.
type Runtime struct {
	http *http.Client
	// version is the interface version agreed with the daemon, as a path
	// prefix. It is empty until Reachable has negotiated it.
	version string
}

// Open connects to the runtime over its local socket.
func Open(socket string) *Runtime {
	return &Runtime{http: &http.Client{
		Transport: &http.Transport{
			DialContext: func(ctx context.Context, _, _ string) (net.Conn, error) {
				return (&net.Dialer{}).DialContext(ctx, "unix", socket)
			},
		},
	}}
}

// Reachable checks that the runtime answers and agrees an interface version
// with it. A worker does this before claiming it can run anything, so that a
// host whose runtime is too old is reported at startup rather than when the
// first job arrives.
func (r *Runtime) Reachable(ctx context.Context) error {
	// The ping is the one call made without a version, because its purpose is
	// to discover which versions are available.
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, "http://runtime/_ping", nil)
	if err != nil {
		return err
	}
	response, err := r.http.Do(request)
	if err != nil {
		return fmt.Errorf("reaching the container runtime: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode >= 400 {
		return fmt.Errorf("the container runtime refused a ping: %s", response.Status)
	}

	daemon := response.Header.Get("Api-Version")
	if daemon == "" {
		daemon = minimumVersion
	}
	agreed := preferredVersion
	if olderThan(daemon, preferredVersion) {
		agreed = daemon
	}
	if olderThan(agreed, minimumVersion) {
		return fmt.Errorf(
			"the container runtime offers interface version %s, and this worker needs at least %s",
			daemon, minimumVersion)
	}
	r.version = "/v" + agreed
	return nil
}

// olderThan compares two dotted interface versions.
func olderThan(candidate, reference string) bool {
	parse := func(value string) (int, int) {
		major, minor := 0, 0
		fmt.Sscanf(value, "%d.%d", &major, &minor)
		return major, minor
	}
	candidateMajor, candidateMinor := parse(candidate)
	referenceMajor, referenceMinor := parse(reference)
	if candidateMajor != referenceMajor {
		return candidateMajor < referenceMajor
	}
	return candidateMinor < referenceMinor
}

// Spec describes one container to run.
//
// Everything a job supplies is treated as untrusted: it gets no network, no
// added capabilities, no way to gain privileges, a read-only root, and the
// processor and memory it was admitted for. A job that needs more must declare
// more and be admitted for it.
type Spec struct {
	Image       string
	Command     []string
	Args        []string
	Env         []string
	InputsHost  string
	OutputsHost string
	MemoryBytes int64
	CPUs        float64
	Name        string
	// Network is granted only to work the platform admitted with that
	// capability. Everything else runs with none (ADR-0012).
	Network bool

	// Mounts are for work whose inputs are not a single staged directory — a
	// dive, which needs a place, a vehicle and somewhere to write, each from
	// somewhere different.
	Mounts []Mount

	// GPUs names the devices this may use, by index. Empty means none.
	// Naming them rather than granting all is what stops one dive taking a
	// device another dive is holding.
	GPUs []string

	// JoinNetworkOf puts this container in another's network namespace.
	//
	// A dive is two processes that must hear each other over DDS and must not
	// hear anybody else's. Sharing one namespace gives them a loopback nobody
	// else is on, which is stronger than a shared bridge and simpler than
	// arranging discovery: neither can reach the host's network, and neither
	// can be reached from it.
	JoinNetworkOf string

	// WritableRoot relaxes the read-only root filesystem. A simulator writes
	// shader and asset caches all over its own installation and cannot run
	// without it; ordinary work can and does.
	WritableRoot bool
}

// Mount is a host directory made visible inside a container.
type Mount struct {
	Source   string
	Target   string
	ReadOnly bool
}

// Result is how a container ended.
type Result struct {
	ExitCode int
	Logs     string
}

// Present reports whether an image is already on the host.
//
// This platform's own images are built elsewhere and streamed to hosts that
// cannot reach a registry, so an image named by its content identity is
// verified to be here rather than fetched.
func (r *Runtime) Present(ctx context.Context, image string) error {
	response, err := r.do(ctx, http.MethodGet, "/images/"+url.PathEscape(image)+"/json", nil)
	if err != nil {
		return fmt.Errorf("image %s is not on this host: %w", image, err)
	}
	return response.Close()
}

// Pull fetches an image. The reference is pinned by digest, so what is fetched
// is what the job's provenance names.
func (r *Runtime) Pull(ctx context.Context, image string) error {
	query := url.Values{}
	query.Set("fromImage", image)
	response, err := r.do(ctx, http.MethodPost, "/images/create?"+query.Encode(), nil)
	if err != nil {
		return err
	}
	defer response.Close()
	// The daemon streams progress and reports a failure only within that
	// stream, so it must be read to the end before the pull is known to have
	// worked.
	body, err := io.ReadAll(io.LimitReader(response, 1<<20))
	if err != nil {
		return fmt.Errorf("fetching image %s: %w", image, err)
	}
	if bytes.Contains(body, []byte(`"error"`)) {
		return fmt.Errorf("fetching image %s: %s", image, firstError(body))
	}
	return nil
}

func firstError(stream []byte) string {
	for _, line := range bytes.Split(stream, []byte("\n")) {
		var frame struct {
			Error string `json:"error"`
		}
		if json.Unmarshal(line, &frame) == nil && frame.Error != "" {
			return frame.Error
		}
	}
	return "the runtime reported an error without describing it"
}

// Create prepares a container and reports its identifier.
func (r *Runtime) Create(ctx context.Context, spec Spec) (string, error) {
	command := append(append([]string{}, spec.Command...), spec.Args...)

	// No network unless the platform granted this work that capability. It is
	// the default for everything an institution submits (ADR-0012).
	network := "none"
	if spec.Network {
		network = "bridge"
	}

	binds := []string{}
	if spec.InputsHost != "" {
		binds = append(binds, spec.InputsHost+":/work/inputs:ro")
	}
	if spec.OutputsHost != "" {
		binds = append(binds, spec.OutputsHost+":/work/outputs:rw")
	}
	for _, mount := range spec.Mounts {
		mode := "rw"
		if mount.ReadOnly {
			mode = "ro"
		}
		binds = append(binds, mount.Source+":"+mount.Target+":"+mode)
	}

	if spec.JoinNetworkOf != "" {
		network = "container:" + spec.JoinNetworkOf
	}

	hostConfig := map[string]any{
		"Binds":          binds,
		"NetworkMode":    network,
		"ReadonlyRootfs": !spec.WritableRoot,
		"CapDrop":        []string{"ALL"},
		"SecurityOpt":    []string{"no-new-privileges"},
		"Privileged":     false,
		"Memory":         spec.MemoryBytes,
		"NanoCpus":       int64(spec.CPUs * 1e9),
		"PidsLimit":      512,
		"AutoRemove":     false,
		// A read-only root still needs somewhere to write scratch, and a
		// bounded temporary filesystem is safer than a writable root.
		"Tmpfs": map[string]string{"/tmp": "rw,noexec,nosuid,size=536870912"},
	}

	// Named devices rather than all of them: a dive that could see every GPU
	// on the host could take one another dive is holding.
	if len(spec.GPUs) > 0 {
		hostConfig["DeviceRequests"] = []map[string]any{{
			"Driver":       "",
			"DeviceIDs":    spec.GPUs,
			"Capabilities": [][]string{{"gpu"}},
		}}
	}

	request := map[string]any{
		"Image":           spec.Image,
		"Cmd":             command,
		"Env":             spec.Env,
		"WorkingDir":      "/work",
		"NetworkDisabled": !spec.Network,
		"HostConfig":      hostConfig,
	}

	query := ""
	if spec.Name != "" {
		query = "?name=" + url.QueryEscape(spec.Name)
	}
	response, err := r.do(ctx, http.MethodPost, "/containers/create"+query, request)
	if err != nil {
		return "", err
	}
	defer response.Close()

	var created struct {
		ID string `json:"Id"`
	}
	if err := json.NewDecoder(response).Decode(&created); err != nil {
		return "", fmt.Errorf("reading the created container: %w", err)
	}
	return created.ID, nil
}

// Start runs a prepared container.
func (r *Runtime) Start(ctx context.Context, id string) error {
	response, err := r.do(ctx, http.MethodPost, "/containers/"+id+"/start", nil)
	if err != nil {
		return err
	}
	return response.Close()
}

// Wait blocks until the container stops and reports its exit status.
func (r *Runtime) Wait(ctx context.Context, id string) (int, error) {
	response, err := r.do(ctx, http.MethodPost, "/containers/"+id+"/wait?condition=not-running", nil)
	if err != nil {
		return 0, err
	}
	defer response.Close()

	var result struct {
		StatusCode int `json:"StatusCode"`
		Error      *struct {
			Message string `json:"Message"`
		} `json:"Error"`
	}
	if err := json.NewDecoder(response).Decode(&result); err != nil {
		return 0, fmt.Errorf("reading how a container ended: %w", err)
	}
	if result.Error != nil && result.Error.Message != "" {
		return result.StatusCode, fmt.Errorf("the runtime reported: %s", result.Error.Message)
	}
	return result.StatusCode, nil
}

// Stop asks a container to end, and ends it if it does not.
func (r *Runtime) Stop(ctx context.Context, id string, grace time.Duration) error {
	seconds := int(grace.Seconds())
	if seconds < 1 {
		seconds = 1
	}
	response, err := r.do(ctx, http.MethodPost,
		fmt.Sprintf("/containers/%s/stop?t=%d", id, seconds), nil)
	if err != nil {
		return err
	}
	return response.Close()
}

// Logs reports the last of what a container wrote, which is what a person
// reads first when work fails.
func (r *Runtime) Logs(ctx context.Context, id string, lines int) (string, error) {
	response, err := r.do(ctx, http.MethodGet,
		fmt.Sprintf("/containers/%s/logs?stdout=1&stderr=1&tail=%d", id, lines), nil)
	if err != nil {
		return "", err
	}
	defer response.Close()

	raw, err := io.ReadAll(io.LimitReader(response, 1<<20))
	if err != nil {
		return "", fmt.Errorf("reading container output: %w", err)
	}
	return demultiplex(raw), nil
}

// demultiplex removes the eight-byte stream framing the runtime adds when a
// container has no terminal attached, so that what is stored is what the
// program actually wrote.
//
// A container that does have a terminal attached is not framed at all, and its
// output must be returned untouched. The two cannot be told apart from the
// request, so the framing is parsed strictly: every header must name a real
// stream and carry three zero bytes where the format requires them. Anything
// that does not parse is text, and is returned as it arrived.
func demultiplex(raw []byte) string {
	var out strings.Builder
	rest := raw
	for len(rest) >= 8 {
		stream := rest[0]
		if stream > 2 || rest[1] != 0 || rest[2] != 0 || rest[3] != 0 {
			return string(raw)
		}
		length := int(binary.BigEndian.Uint32(rest[4:8]))
		rest = rest[8:]
		if length > len(rest) {
			// The read was cut short mid-frame, which is expected when only the
			// tail of a long log was asked for.
			length = len(rest)
		}
		out.Write(rest[:length])
		rest = rest[length:]
	}
	if len(rest) > 0 {
		// Trailing bytes too short to be a header mean this was never framed.
		return string(raw)
	}
	return out.String()
}

// Remove deletes a container and the writable layer it used.
func (r *Runtime) Remove(ctx context.Context, id string) error {
	response, err := r.do(ctx, http.MethodDelete, "/containers/"+id+"?v=1&force=1", nil)
	if err != nil {
		return err
	}
	return response.Close()
}

func (r *Runtime) do(ctx context.Context, method, path string, body any) (io.ReadCloser, error) {
	var payload io.Reader
	if body != nil {
		encoded, err := json.Marshal(body)
		if err != nil {
			return nil, fmt.Errorf("encoding a runtime request: %w", err)
		}
		payload = bytes.NewReader(encoded)
	}

	if r.version == "" {
		return nil, fmt.Errorf("no interface version has been agreed with the container runtime")
	}
	request, err := http.NewRequestWithContext(ctx, method, "http://runtime"+r.version+path, payload)
	if err != nil {
		return nil, err
	}
	if body != nil {
		request.Header.Set("Content-Type", "application/json")
	}

	response, err := r.http.Do(request)
	if err != nil {
		return nil, fmt.Errorf("reaching the container runtime: %w", err)
	}
	if response.StatusCode >= 400 {
		defer response.Body.Close()
		raw, _ := io.ReadAll(io.LimitReader(response.Body, 1<<16))
		var reported struct {
			Message string `json:"message"`
		}
		_ = json.Unmarshal(raw, &reported)
		if reported.Message == "" {
			reported.Message = strings.TrimSpace(string(raw))
		}
		return nil, fmt.Errorf("the container runtime refused %s %s: %s",
			method, path, reported.Message)
	}
	return response.Body, nil
}

// Run creates a container, waits for it, collects its output, and removes it.
//
// The removal happens whatever else does, because a host that accumulates
// stopped containers runs out of disk eventually, and it does so slowly enough
// that nobody connects the two.
func (r *Runtime) Run(ctx context.Context, spec Spec) (Result, error) {
	id, err := r.Create(ctx, spec)
	if err != nil {
		return Result{}, err
	}
	defer func() {
		// On a context that outlives the caller's: a cancelled dive still has
		// to have its container removed, and the cancellation is exactly when
		// that is most likely to be forgotten.
		removing, stop := context.WithTimeout(context.WithoutCancel(ctx), 30*time.Second)
		defer stop()
		// Nothing to report it to from here — a runtime does not know which
		// dive this was. The caller logs; this just makes sure it happens.
		_ = r.Remove(removing, id)
	}()

	if err := r.Start(ctx, id); err != nil {
		return Result{}, err
	}

	code, err := r.Wait(ctx, id)
	if err != nil {
		// The wait was interrupted rather than the container finishing, so it
		// is still running and must be stopped before it is removed.
		stopping, stop := context.WithTimeout(context.WithoutCancel(ctx), 30*time.Second)
		defer stop()
		_ = r.Stop(stopping, id, 10*time.Second)
		return Result{}, err
	}

	// Read after waiting, so what is returned is the whole of it. Bounded,
	// because a simulator that failed at startup produces a great deal of it
	// and the useful part is the end.
	// An unreadable log is not a failed run: the exit code is what says
	// whether it worked, and the output is what says why.
	logs, _ := r.Logs(ctx, id, 200)
	return Result{ExitCode: code, Logs: logs}, nil
}
