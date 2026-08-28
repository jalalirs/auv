package exec

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"fmt"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
)

// ErrLeaseInvalid reports a worker acting on an attempt it does not hold.
// A worker whose lease has expired receives this rather than being allowed to
// write results the platform has already reclaimed.
var ErrLeaseInvalid = errors.New("that lease is not valid")

// Lease is work handed to a worker, together with the token that proves the
// worker holds it.
type Lease struct {
	AttemptID string    `json:"attemptId"`
	Token     string    `json:"token"`
	ExpiresAt time.Time `json:"expiresAt"`
	Job       Job       `json:"job"`
}

// Heartbeat is what a worker learns each time it reports that it is alive.
type Heartbeat struct {
	ExpiresAt time.Time `json:"expiresAt"`
	// Cancelled tells the worker to stop, which is how cancellation reaches
	// work that is already running.
	Cancelled bool `json:"cancelled"`
}

func newLeaseToken() (token string, digest []byte, err error) {
	raw := make([]byte, 32)
	if _, err := rand.Read(raw); err != nil {
		return "", nil, fmt.Errorf("drawing a lease token: %w", err)
	}
	token = base64.RawURLEncoding.EncodeToString(raw)
	sum := sha256.Sum256([]byte(token))
	return token, sum[:], nil
}

func leaseDigest(token string) []byte {
	sum := sha256.Sum256([]byte(token))
	return sum[:]
}

// Take hands one admitted job to a worker, or reports that there is nothing to
// do.
//
// The job row is locked while the attempt is created, and locked rows are
// skipped rather than waited for, so many workers can take work at once
// without any of them taking the same job.
func (b *Broker) Take(ctx context.Context, workerID, targetID string, leaseFor time.Duration) (*Lease, error) {
	var lease *Lease
	err := b.pool.InTransaction(ctx, func(conn db.Conn) error {
		var jobID string
		err := conn.QueryRow(ctx, `
			SELECT id FROM exec.job
			WHERE state = 'admitted' AND target_id = $1
			ORDER BY created_at
			FOR UPDATE SKIP LOCKED
			LIMIT 1`, targetID).Scan(&jobID)
		if errors.Is(db.Translate(err), db.ErrNotFound) {
			return nil
		}
		if err != nil {
			return fmt.Errorf("looking for work: %w", err)
		}

		token, digest, err := newLeaseToken()
		if err != nil {
			return err
		}
		expiresAt := time.Now().Add(leaseFor)

		var ordinal int
		if err := conn.QueryRow(ctx,
			`SELECT coalesce(max(ordinal), 0) + 1 FROM exec.attempt WHERE job_id = $1`,
			jobID).Scan(&ordinal); err != nil {
			return fmt.Errorf("numbering an attempt: %w", err)
		}

		attemptID := ids.New(ids.KindAttempt)
		if _, err := conn.Exec(ctx, `
			INSERT INTO exec.attempt
			    (id, job_id, ordinal, target_id, worker_id, lease_token_hash, lease_expires_at)
			VALUES ($1, $2, $3, $4, $5, $6, $7)`,
			attemptID, jobID, ordinal, targetID, workerID, digest, expiresAt); err != nil {
			return fmt.Errorf("recording an attempt: %w", err)
		}

		if _, err := conn.Exec(ctx,
			`UPDATE exec.job SET state = 'running' WHERE id = $1`, jobID); err != nil {
			return fmt.Errorf("marking work as running: %w", err)
		}

		if err := appendEvent(ctx, conn, jobID, attemptID, EventScheduled, map[string]any{
			"attempt": ordinal, "workerId": workerID,
		}); err != nil {
			return err
		}

		job, err := jobOn(ctx, conn, jobID)
		if err != nil {
			return err
		}
		lease = &Lease{AttemptID: attemptID, Token: token, ExpiresAt: expiresAt, Job: job}
		return nil
	})
	if err != nil {
		return nil, err
	}
	return lease, nil
}

// holdsLease reports the job an attempt belongs to, if the token is the one
// that was issued and the attempt has not finished.
func holdsLease(ctx context.Context, conn db.Conn, attemptID, token string) (string, error) {
	var jobID string
	err := conn.QueryRow(ctx, `
		SELECT job_id FROM exec.attempt
		WHERE id = $1 AND lease_token_hash = $2
		  AND state IN ('leased', 'running') AND lease_expires_at > now()`,
		attemptID, leaseDigest(token)).Scan(&jobID)
	if errors.Is(db.Translate(err), db.ErrNotFound) {
		return "", ErrLeaseInvalid
	}
	if err != nil {
		return "", fmt.Errorf("checking a lease: %w", err)
	}
	return jobID, nil
}

// Beat extends a lease and tells the worker whether it should stop.
func (b *Broker) Beat(ctx context.Context, attemptID, token string, leaseFor time.Duration) (Heartbeat, error) {
	var beat Heartbeat
	err := b.pool.InTransaction(ctx, func(conn db.Conn) error {
		jobID, err := holdsLease(ctx, conn, attemptID, token)
		if err != nil {
			return err
		}
		beat.ExpiresAt = time.Now().Add(leaseFor)
		if _, err := conn.Exec(ctx,
			`UPDATE exec.attempt SET lease_expires_at = $2 WHERE id = $1`,
			attemptID, beat.ExpiresAt); err != nil {
			return fmt.Errorf("extending a lease: %w", err)
		}

		var state JobState
		if err := conn.QueryRow(ctx,
			`SELECT state FROM exec.job WHERE id = $1`, jobID).Scan(&state); err != nil {
			return fmt.Errorf("reading job state: %w", err)
		}
		beat.Cancelled = state == Cancelled
		return nil
	})
	return beat, err
}

// ReportStarted records that the container is running, and where.
func (b *Broker) ReportStarted(ctx context.Context, attemptID, token, placementRef string) error {
	return b.pool.InTransaction(ctx, func(conn db.Conn) error {
		jobID, err := holdsLease(ctx, conn, attemptID, token)
		if err != nil {
			return err
		}
		if _, err := conn.Exec(ctx, `
			UPDATE exec.attempt SET state = 'running', started_at = now(), placement_ref = $2
			WHERE id = $1 AND state = 'leased'`, attemptID, placementRef); err != nil {
			return fmt.Errorf("recording that an attempt started: %w", err)
		}
		return appendEvent(ctx, conn, jobID, attemptID, EventStarted,
			map[string]any{"placementRef": placementRef})
	})
}

// ReportProgress adds a progress entry to a job's account of itself.
func (b *Broker) ReportProgress(ctx context.Context, attemptID, token string, detail map[string]any) error {
	return b.pool.InTransaction(ctx, func(conn db.Conn) error {
		jobID, err := holdsLease(ctx, conn, attemptID, token)
		if err != nil {
			return err
		}
		return appendEvent(ctx, conn, jobID, attemptID, EventProgress, detail)
	})
}

// RecordOutput records one file a job produced.
//
// An output is recorded once per name however many attempts a job takes: a
// retry that produces the same output again does not duplicate it, which is
// what makes a retried job's result singular.
func (b *Broker) RecordOutput(ctx context.Context, attemptID, token, name, objectID string) error {
	return b.pool.InTransaction(ctx, func(conn db.Conn) error {
		jobID, err := holdsLease(ctx, conn, attemptID, token)
		if err != nil {
			return err
		}

		declared, err := outputDeclaration(ctx, conn, jobID, name)
		if err != nil {
			return err
		}

		var size int64
		if err := conn.QueryRow(ctx,
			`SELECT size_bytes FROM store.object WHERE id = $1`, objectID).Scan(&size); err != nil {
			if errors.Is(db.Translate(err), db.ErrNotFound) {
				return fmt.Errorf("no stored object %q to record as output %q", objectID, name)
			}
			return fmt.Errorf("reading a produced object: %w", err)
		}
		if size > declared.MaxSizeBytes {
			return &OutputTooLarge{Name: name, SizeBytes: size, LimitBytes: declared.MaxSizeBytes}
		}

		tag, err := conn.Exec(ctx, `
			INSERT INTO exec.job_output (job_id, name, attempt_id, object_id)
			VALUES ($1, $2, $3, $4)
			ON CONFLICT (job_id, name) DO NOTHING`, jobID, name, attemptID, objectID)
		if err != nil {
			return fmt.Errorf("recording an output: %w", err)
		}
		if tag.RowsAffected() == 0 {
			// A previous attempt already produced this output. The record keeps
			// the first, and this is not an error: the job's result is singular.
			return nil
		}
		return appendEvent(ctx, conn, jobID, attemptID, EventOutputReceived, map[string]any{
			"name": name, "objectId": objectID, "sizeBytes": size,
		})
	})
}

// OutputTooLarge reports output beyond what the job declared it would produce.
// No partial result is recorded.
type OutputTooLarge struct {
	Name       string
	SizeBytes  int64
	LimitBytes int64
}

func (e *OutputTooLarge) Error() string {
	return fmt.Sprintf("output %q is %d bytes, beyond the %d bytes it declared",
		e.Name, e.SizeBytes, e.LimitBytes)
}

func outputDeclaration(ctx context.Context, conn db.Conn, jobID, name string) (Output, error) {
	job, err := jobOn(ctx, conn, jobID)
	if err != nil {
		return Output{}, err
	}
	for _, output := range job.Outputs {
		if output.Name == name {
			return output, nil
		}
	}
	return Output{}, fmt.Errorf("this job declares no output named %q", name)
}

// Finish records how an attempt ended and, with it, how the job ended.
func (b *Broker) Finish(ctx context.Context, attemptID, token string, outcome JobState, exitCode int, failure FailureClass) (Job, error) {
	if !outcome.IsTerminal() {
		return Job{}, fmt.Errorf("%q is not a way for work to end", outcome)
	}
	var job Job
	err := b.pool.InTransaction(ctx, func(conn db.Conn) error {
		jobID, err := holdsLease(ctx, conn, attemptID, token)
		if err != nil {
			return err
		}

		if _, err := conn.Exec(ctx, `
			UPDATE exec.attempt
			SET state = $2::exec.attempt_state, finished_at = now(),
			    exit_code = $3, failure_class = $4::exec.failure_class
			WHERE id = $1`,
			attemptID, string(outcome), exitCode, string(failure)); err != nil {
			return fmt.Errorf("recording how an attempt ended: %w", err)
		}

		// Cancellation already gave the job its ending; a worker reporting
		// afterwards does not overwrite it.
		if _, err := conn.Exec(ctx, `
			UPDATE exec.job
			SET state = $2::exec.job_state, failure_class = $3::exec.failure_class,
			    terminal_at = now()
			WHERE id = $1 AND state = 'running'`,
			jobID, string(outcome), string(failure)); err != nil {
			return fmt.Errorf("recording how work ended: %w", err)
		}

		kind := EventSucceeded
		switch outcome {
		case Failed:
			kind = EventFailed
		case Cancelled:
			kind = EventCancelled
		case Evicted:
			kind = EventEvicted
		case TimedOut:
			kind = EventTimedOut
		}
		if err := appendEvent(ctx, conn, jobID, attemptID, kind, map[string]any{
			"exitCode": exitCode, "failureClass": string(failure),
		}); err != nil {
			return err
		}

		job, err = jobOn(ctx, conn, jobID)
		return err
	})
	return job, err
}

// InputFor reports one input a leased job declares.
//
// A worker reaches the bytes it needs through the lease it holds, not through
// authority over an organisation, so a worker that is not running a job cannot
// read that job's inputs.
func (b *Broker) InputFor(ctx context.Context, attemptID, token, name string) (Input, error) {
	var input Input
	err := b.pool.InTransaction(ctx, func(conn db.Conn) error {
		jobID, err := holdsLease(ctx, conn, attemptID, token)
		if err != nil {
			return err
		}
		job, err := jobOn(ctx, conn, jobID)
		if err != nil {
			return err
		}
		for _, declared := range job.Inputs {
			if declared.Name == name {
				input = declared
				return nil
			}
		}
		return fmt.Errorf("this job declares no input named %q", name)
	})
	return input, err
}

// OutputFor reports one output a leased job is expected to produce, which is
// what bounds the size the worker may upload.
func (b *Broker) OutputFor(ctx context.Context, attemptID, token, name string) (Output, error) {
	var output Output
	err := b.pool.InTransaction(ctx, func(conn db.Conn) error {
		jobID, err := holdsLease(ctx, conn, attemptID, token)
		if err != nil {
			return err
		}
		output, err = outputDeclaration(ctx, conn, jobID, name)
		return err
	})
	return output, err
}
