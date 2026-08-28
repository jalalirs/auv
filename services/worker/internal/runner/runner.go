// Package runner executes one leased job and reports what happened.
//
// It stages the inputs the job declared, verifying each against the digest its
// provenance names; runs the container under the constraints the platform
// admitted it for; collects only the outputs the job declared; and reports the
// outcome. Anything it cannot do, it reports as a failure with a reason,
// because silence would leave the job apparently running forever.
package runner

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
	"path/filepath"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/worker/internal/config"
	"github.com/jalalirs/auv/services/worker/internal/container"
	"github.com/jalalirs/auv/services/worker/internal/controlplane"
)

// Outcomes and failure reasons, in the words the control plane records.
const (
	outcomeSucceeded = "succeeded"
	outcomeFailed    = "failed"
	outcomeCancelled = "cancelled"

	noFailure           = "none"
	imageUnavailable    = "image_unavailable"
	inputUnavailable    = "input_unavailable"
	outputLimitExceeded = "output_limit_exceeded"
	nonzeroExit         = "nonzero_exit"
	cancelledByCaller   = "cancelled_by_caller"
	internalError       = "internal_error"
)

// ErrLeaseLost reports that the platform took the work back while it was being
// run, in which case the worker stops rather than writing results the platform
// has already reclaimed.
var ErrLeaseLost = errors.New("the lease was reclaimed")

// Runner executes leased work.
type Runner struct {
	client   *controlplane.Client
	runtime  *container.Runtime
	settings config.Config
	logger   *slog.Logger
	http     *http.Client
}

// New builds a runner.
func New(client *controlplane.Client, runtime *container.Runtime, settings config.Config, logger *slog.Logger) *Runner {
	return &Runner{
		client:   client,
		runtime:  runtime,
		settings: settings,
		logger:   logger,
		// Staging and uploading move whole payloads, so they are not bound by
		// the short timeout that suits a control-plane call.
		http: &http.Client{Timeout: 0},
	}
}

// Run executes one lease from beginning to end.
func (r *Runner) Run(ctx context.Context, lease *controlplane.Lease) error {
	log := r.logger.With("jobId", lease.Job.ID, "attemptId", lease.AttemptID,
		"recipeId", lease.Job.RecipeID)

	// The heartbeat runs for as long as the work does. If the platform says the
	// work was cancelled, this context is cancelled and everything below unwinds.
	work, stopWork := context.WithCancel(ctx)
	defer stopWork()
	cancelled := r.beat(work, stopWork, lease, log)

	inputs, outputs, cleanup, err := r.stage(work, lease)
	if err != nil {
		return r.fail(ctx, lease, inputUnavailable, err, log)
	}
	defer cleanup()

	// An image named by a registry digest is fetched; one named by its content
	// identity is already on the host and is verified to be, because that is
	// how this platform's own images reach hosts with no registry.
	if strings.Contains(lease.Job.ImageDigest, "@") {
		if err := r.runtime.Pull(work, lease.Job.ImageDigest); err != nil {
			return r.fail(ctx, lease, imageUnavailable, err, log)
		}
	} else if err := r.runtime.Present(work, lease.Job.ImageDigest); err != nil {
		return r.fail(ctx, lease, imageUnavailable, err, log)
	}

	id, err := r.runtime.Create(work, container.Spec{
		Image:       lease.Job.ImageDigest,
		Command:     lease.Job.Command,
		Args:        lease.Job.Args,
		Env:         []string{"CORAL_CITY_JOB_ID=" + lease.Job.ID},
		InputsHost:  r.hostPath(inputs),
		OutputsHost: r.hostPath(outputs),
		MemoryBytes: lease.Job.RequestMemoryBytes,
		CPUs:        lease.Job.RequestCPU,
		Name:        "coral-" + lease.AttemptID,
		Network:     lease.Job.Egress == "internet",
	})
	if err != nil {
		return r.fail(ctx, lease, internalError, err, log)
	}
	defer func() {
		removal, cancel := context.WithTimeout(context.WithoutCancel(ctx), 30*time.Second)
		defer cancel()
		if err := r.runtime.Remove(removal, id); err != nil {
			log.Warn("could not remove a container", "error", err)
		}
	}()

	if err := r.runtime.Start(work, id); err != nil {
		return r.fail(ctx, lease, internalError, err, log)
	}
	if err := r.client.ReportStarted(ctx, lease.AttemptID, lease.Token, id); err != nil {
		return r.translate(err)
	}
	log.Info("running")

	exitCode, waitErr := r.runtime.Wait(work, id)

	// Cancellation reaches running work through the heartbeat, so it is checked
	// before the exit status is interpreted.
	if isCancelled(cancelled) {
		stopContext, cancel := context.WithTimeout(context.WithoutCancel(ctx), time.Minute)
		defer cancel()
		if err := r.runtime.Stop(stopContext, id, 10*time.Second); err != nil {
			log.Warn("could not stop a cancelled container", "error", err)
		}
		return r.finish(ctx, lease, outcomeCancelled, exitCode, cancelledByCaller, log)
	}
	if waitErr != nil {
		return r.fail(ctx, lease, internalError, waitErr, log)
	}

	if logs, err := r.runtime.Logs(context.WithoutCancel(ctx), id, 200); err == nil && logs != "" {
		if err := r.client.ReportProgress(ctx, lease.AttemptID, lease.Token,
			map[string]any{"output": tail(logs, 8000)}); err != nil {
			return r.translate(err)
		}
	}

	if exitCode != 0 {
		return r.finish(ctx, lease, outcomeFailed, exitCode, nonzeroExit, log)
	}

	if err := r.collect(ctx, lease, outputs, log); err != nil {
		if errors.Is(err, ErrLeaseLost) {
			return err
		}
		reason := internalError
		var tooLarge *outputTooLarge
		if errors.As(err, &tooLarge) {
			reason = outputLimitExceeded
		}
		return r.fail(ctx, lease, reason, err, log)
	}

	return r.finish(ctx, lease, outcomeSucceeded, 0, noFailure, log)
}

// beat keeps the lease alive while the work runs, and cancels the work when the
// platform says it has been cancelled or when the lease can no longer be held.
func (r *Runner) beat(ctx context.Context, stop context.CancelFunc, lease *controlplane.Lease, log *slog.Logger) <-chan struct{} {
	cancelled := make(chan struct{})
	go func() {
		ticker := time.NewTicker(r.settings.HeartbeatInterval)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case <-ticker.C:
			}
			beat, err := r.client.Beat(ctx, lease.AttemptID, lease.Token)
			if err != nil {
				if ctx.Err() != nil {
					return
				}
				log.Warn("could not report that this worker is alive", "error", err)
				var failure *controlplane.Failure
				if errors.As(err, &failure) && failure.LeaseLost() {
					// The platform has taken the work back. Continuing would
					// mean writing results it has already reclaimed.
					stop()
					return
				}
				continue
			}
			if beat.Cancelled {
				close(cancelled)
				return
			}
		}
	}()
	return cancelled
}

func isCancelled(signal <-chan struct{}) bool {
	select {
	case <-signal:
		return true
	default:
		return false
	}
}

// stage writes the job's declared inputs into a fresh directory, verifying each
// against the digest the job names. A job reads what its provenance says it
// reads, or it does not run.
func (r *Runner) stage(ctx context.Context, lease *controlplane.Lease) (inputs, outputs string, cleanup func(), err error) {
	root := filepath.Join(r.settings.WorkDir, lease.AttemptID)
	inputs = filepath.Join(root, "inputs")
	outputs = filepath.Join(root, "outputs")
	cleanup = func() {
		if err := os.RemoveAll(root); err != nil {
			r.logger.Warn("could not clear a working directory", "path", root, "error", err)
		}
	}

	for _, dir := range []string{inputs, outputs} {
		if err := os.MkdirAll(dir, 0o777); err != nil {
			return "", "", cleanup, fmt.Errorf("preparing %s: %w", dir, err)
		}
		// The container runs as its image's own user, which this worker does
		// not choose; the staging directories must be writable by it.
		if err := os.Chmod(dir, 0o777); err != nil {
			return "", "", cleanup, fmt.Errorf("preparing %s: %w", dir, err)
		}
	}

	for _, declared := range lease.Job.Inputs {
		input, readURL, err := r.client.InputURL(ctx, lease.AttemptID, lease.Token, declared.Name)
		if err != nil {
			return "", "", cleanup, fmt.Errorf("locating input %q: %w", declared.Name, err)
		}
		target := filepath.Join(inputs, filepath.FromSlash(input.RelativePath))
		if err := os.MkdirAll(filepath.Dir(target), 0o777); err != nil {
			return "", "", cleanup, err
		}
		if err := r.download(ctx, readURL, target, input.SHA256); err != nil {
			return "", "", cleanup, fmt.Errorf("staging input %q: %w", declared.Name, err)
		}
	}
	return inputs, outputs, cleanup, nil
}

func (r *Runner) download(ctx context.Context, from, to, expected string) error {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, from, nil)
	if err != nil {
		return err
	}
	response, err := r.http.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode >= 400 {
		return fmt.Errorf("storage refused the read: %s", response.Status)
	}

	file, err := os.Create(to)
	if err != nil {
		return err
	}
	defer file.Close()

	hasher := sha256.New()
	if _, err := io.Copy(io.MultiWriter(file, hasher), io.LimitReader(response.Body, r.settings.MaxInputBytes)); err != nil {
		return err
	}
	if actual := hex.EncodeToString(hasher.Sum(nil)); actual != expected {
		return fmt.Errorf("the stored bytes are %s, but this job's provenance names %s",
			actual, expected)
	}
	return file.Chmod(0o644)
}

// outputTooLarge reports output beyond what the job declared it would produce.
type outputTooLarge struct {
	name  string
	size  int64
	limit int64
}

func (e *outputTooLarge) Error() string {
	return fmt.Sprintf("output %q is %d bytes, beyond the %d it declared", e.name, e.size, e.limit)
}

// collect uploads the outputs the job declared, and only those. A file the job
// did not declare is left where it is: an undeclared output has no provenance
// and no size limit, so it is not evidence of anything.
func (r *Runner) collect(ctx context.Context, lease *controlplane.Lease, outputs string, log *slog.Logger) error {
	for _, declared := range lease.Job.Outputs {
		path := filepath.Join(outputs, filepath.FromSlash(declared.RelativePath))
		info, err := os.Stat(path)
		if err != nil {
			return fmt.Errorf("the job declared output %q at %q but produced nothing there",
				declared.Name, declared.RelativePath)
		}
		if info.Size() > declared.MaxSizeBytes {
			return &outputTooLarge{name: declared.Name, size: info.Size(), limit: declared.MaxSizeBytes}
		}

		digest, err := digestOf(path)
		if err != nil {
			return err
		}
		grant, err := r.client.RequestUpload(ctx, lease.AttemptID, lease.Token,
			declared.Name, digest, info.Size())
		if err != nil {
			return r.translate(err)
		}
		if err := r.upload(ctx, grant.UploadURL, path, declared.MediaType, info.Size()); err != nil {
			return fmt.Errorf("uploading output %q: %w", declared.Name, err)
		}
		objectID, err := r.client.ConfirmUpload(ctx, lease.AttemptID, grant.ID)
		if err != nil {
			return r.translate(err)
		}
		if err := r.client.RecordOutput(ctx, lease.AttemptID, lease.Token,
			declared.Name, objectID); err != nil {
			return r.translate(err)
		}
		log.Info("recorded output", "name", declared.Name, "sizeBytes", info.Size())
	}
	return nil
}

func digestOf(path string) (string, error) {
	file, err := os.Open(path)
	if err != nil {
		return "", err
	}
	defer file.Close()
	hasher := sha256.New()
	if _, err := io.Copy(hasher, file); err != nil {
		return "", err
	}
	return hex.EncodeToString(hasher.Sum(nil)), nil
}

func (r *Runner) upload(ctx context.Context, to, path, mediaType string, size int64) error {
	file, err := os.Open(path)
	if err != nil {
		return err
	}
	defer file.Close()

	request, err := http.NewRequestWithContext(ctx, http.MethodPut, to, file)
	if err != nil {
		return err
	}
	request.ContentLength = size
	request.Header.Set("Content-Type", mediaType)

	response, err := r.http.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()
	if response.StatusCode >= 400 {
		raw, _ := io.ReadAll(io.LimitReader(response.Body, 4096))
		return fmt.Errorf("storage refused the write: %s: %s", response.Status, raw)
	}
	return nil
}

func (r *Runner) fail(ctx context.Context, lease *controlplane.Lease, reason string, cause error, log *slog.Logger) error {
	log.Error("work failed", "failureClass", reason, "error", cause)
	if err := r.client.ReportProgress(context.WithoutCancel(ctx), lease.AttemptID, lease.Token,
		map[string]any{"failure": cause.Error()}); err != nil {
		return r.translate(err)
	}
	return r.finish(ctx, lease, outcomeFailed, -1, reason, log)
}

func (r *Runner) finish(ctx context.Context, lease *controlplane.Lease, outcome string, exitCode int, reason string, log *slog.Logger) error {
	// Reporting the outcome must happen even when the work was cancelled, so it
	// is done on a context that the cancellation did not end.
	report, cancel := context.WithTimeout(context.WithoutCancel(ctx), r.settings.RequestTimeout)
	defer cancel()

	if err := r.client.Finish(report, lease.AttemptID, lease.Token, outcome, exitCode, reason); err != nil {
		return r.translate(err)
	}
	log.Info("work finished", "outcome", outcome, "exitCode", exitCode, "failureClass", reason)
	return nil
}

// translate reports a lost lease as such, so the worker stops rather than
// retrying against work the platform has taken back.
func (r *Runner) translate(err error) error {
	var failure *controlplane.Failure
	if errors.As(err, &failure) && failure.LeaseLost() {
		return fmt.Errorf("%w: %s", ErrLeaseLost, failure.Message)
	}
	return err
}

func (r *Runner) hostPath(path string) string {
	relative, err := filepath.Rel(r.settings.WorkDir, path)
	if err != nil {
		return path
	}
	return filepath.Join(r.settings.HostWorkDir, relative)
}

func tail(text string, limit int) string {
	if len(text) <= limit {
		return text
	}
	return "…" + text[len(text)-limit:]
}
