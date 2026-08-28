package exec

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
)

const selectJob = `
	SELECT id, org_id, submitted_by, recipe_id, image_digest, command, args,
	       inputs, outputs, request_cpu, request_memory_bytes, request_gpu,
	       walltime_seconds, coalesce(target_id, ''), state, failure_class,
	       created_at, terminal_at
	FROM exec.job`

func scanJob(row interface{ Scan(...any) error }) (Job, error) {
	var job Job
	var inputs, outputs []byte
	err := row.Scan(&job.ID, &job.OrgID, &job.SubmittedBy, &job.RecipeID, &job.ImageDigest,
		&job.Command, &job.Args, &inputs, &outputs,
		&job.RequestCPU, &job.RequestMemoryBytes, &job.RequestGPU,
		&job.WalltimeSeconds, &job.TargetID, &job.State, &job.FailureClass,
		&job.CreatedAt, &job.TerminalAt)
	if err != nil {
		return Job{}, err
	}
	if err := json.Unmarshal(inputs, &job.Inputs); err != nil {
		return Job{}, fmt.Errorf("reading job inputs: %w", err)
	}
	if err := json.Unmarshal(outputs, &job.Outputs); err != nil {
		return Job{}, fmt.Errorf("reading job outputs: %w", err)
	}
	return job, nil
}

func jobOn(ctx context.Context, conn db.Conn, id string) (Job, error) {
	job, err := scanJob(conn.QueryRow(ctx, selectJob+` WHERE id = $1`, id))
	return job, db.Translate(err)
}

// Job reads one unit of work.
func (b *Broker) Job(ctx context.Context, id string) (Job, error) {
	return jobOn(ctx, b.pool, id)
}

// JobsForOrg lists an organisation's work, newest first.
func (b *Broker) JobsForOrg(ctx context.Context, orgID string, limit int) ([]Job, error) {
	rows, err := b.pool.Query(ctx, selectJob+` WHERE org_id = $1 ORDER BY created_at DESC LIMIT $2`,
		orgID, limit)
	if err != nil {
		return nil, fmt.Errorf("reading work: %w", err)
	}
	defer rows.Close()

	jobs := []Job{}
	for rows.Next() {
		job, err := scanJob(rows)
		if err != nil {
			return nil, err
		}
		jobs = append(jobs, job)
	}
	return jobs, rows.Err()
}

// appendEvent adds one entry to a job's ordered account of itself.
//
// The sequence comes from the job row itself, taken under a row lock, so two
// writers cannot produce the same sequence number and the stream never has a
// gap or a repeat.
func appendEvent(ctx context.Context, conn db.Conn, jobID, attemptID string, kind EventKind, detail map[string]any) error {
	if detail == nil {
		detail = map[string]any{}
	}
	encoded, err := json.Marshal(detail)
	if err != nil {
		return fmt.Errorf("encoding an event: %w", err)
	}

	var sequence int64
	if err := conn.QueryRow(ctx,
		`UPDATE exec.job SET next_sequence = next_sequence + 1 WHERE id = $1
		 RETURNING next_sequence - 1`, jobID).Scan(&sequence); err != nil {
		return fmt.Errorf("numbering an event: %w", err)
	}

	var attempt *string
	if attemptID != "" {
		attempt = &attemptID
	}
	_, err = conn.Exec(ctx, `
		INSERT INTO exec.event (id, job_id, attempt_id, sequence, kind, detail)
		VALUES ($1, $2, $3, $4, $5::exec.event_kind, $6)`,
		ids.New(ids.KindJobEvent), jobID, attempt, sequence, string(kind), encoded)
	if err != nil {
		return fmt.Errorf("recording an event: %w", err)
	}
	return nil
}

// Events reads a job's account of itself from a point in the stream, which is
// how a client resumes watching without missing or repeating anything.
func (b *Broker) Events(ctx context.Context, jobID string, after int64, limit int) ([]Event, error) {
	rows, err := b.pool.Query(ctx, `
		SELECT id, job_id, coalesce(attempt_id, ''), sequence, occurred_at, kind, detail
		FROM exec.event
		WHERE job_id = $1 AND sequence > $2
		ORDER BY sequence
		LIMIT $3`, jobID, after, limit)
	if err != nil {
		return nil, fmt.Errorf("reading events: %w", err)
	}
	defer rows.Close()

	events := []Event{}
	for rows.Next() {
		var event Event
		var detail []byte
		if err := rows.Scan(&event.ID, &event.JobID, &event.AttemptID, &event.Sequence,
			&event.OccurredAt, &event.Kind, &detail); err != nil {
			return nil, err
		}
		if err := json.Unmarshal(detail, &event.Detail); err != nil {
			return nil, fmt.Errorf("reading event detail: %w", err)
		}
		events = append(events, event)
	}
	return events, rows.Err()
}

// Attempts lists every placement of a job, which is what shows that a retry
// happened and why.
func (b *Broker) Attempts(ctx context.Context, jobID string) ([]Attempt, error) {
	rows, err := b.pool.Query(ctx, `
		SELECT id, job_id, ordinal, target_id, worker_id, state, lease_expires_at,
		       placement_ref, exit_code, failure_class, leased_at, started_at, finished_at
		FROM exec.attempt WHERE job_id = $1 ORDER BY ordinal`, jobID)
	if err != nil {
		return nil, fmt.Errorf("reading attempts: %w", err)
	}
	defer rows.Close()

	attempts := []Attempt{}
	for rows.Next() {
		var attempt Attempt
		if err := rows.Scan(&attempt.ID, &attempt.JobID, &attempt.Ordinal, &attempt.TargetID,
			&attempt.WorkerID, &attempt.State, &attempt.LeaseExpiresAt, &attempt.PlacementRef,
			&attempt.ExitCode, &attempt.FailureClass, &attempt.LeasedAt,
			&attempt.StartedAt, &attempt.FinishedAt); err != nil {
			return nil, err
		}
		attempts = append(attempts, attempt)
	}
	return attempts, rows.Err()
}

// Outputs lists what a job produced. An output is recorded once per name
// however many attempts a job took.
func (b *Broker) Outputs(ctx context.Context, jobID string) (map[string]string, error) {
	rows, err := b.pool.Query(ctx,
		`SELECT name, object_id FROM exec.job_output WHERE job_id = $1 ORDER BY name`, jobID)
	if err != nil {
		return nil, fmt.Errorf("reading job outputs: %w", err)
	}
	defer rows.Close()

	outputs := map[string]string{}
	for rows.Next() {
		var name, objectID string
		if err := rows.Scan(&name, &objectID); err != nil {
			return nil, err
		}
		outputs[name] = objectID
	}
	return outputs, rows.Err()
}

// Cancel stops work that has not finished. A running attempt is told to stop
// through its lease, which the worker observes on its next heartbeat.
func (b *Broker) Cancel(ctx context.Context, jobID string) (Job, error) {
	var job Job
	err := b.pool.InTransaction(ctx, func(conn db.Conn) error {
		tag, err := conn.Exec(ctx, `
			UPDATE exec.job
			SET state = 'cancelled', failure_class = 'cancelled_by_caller', terminal_at = now()
			WHERE id = $1 AND state IN ('pending', 'admitted', 'running')`, jobID)
		if err != nil {
			return fmt.Errorf("cancelling work: %w", err)
		}
		if tag.RowsAffected() == 0 {
			var exists bool
			if err := conn.QueryRow(ctx,
				`SELECT true FROM exec.job WHERE id = $1`, jobID).Scan(&exists); err != nil {
				return db.ErrNotFound
			}
			return fmt.Errorf("that work has already finished and cannot be cancelled")
		}

		if _, err := conn.Exec(ctx, `
			UPDATE exec.attempt SET state = 'cancelled', finished_at = now(),
			                        failure_class = 'cancelled_by_caller'
			WHERE job_id = $1 AND state IN ('leased', 'running')`, jobID); err != nil {
			return fmt.Errorf("cancelling an attempt: %w", err)
		}

		if err := appendEvent(ctx, conn, jobID, "", EventCancelled, nil); err != nil {
			return err
		}
		job, err = jobOn(ctx, conn, jobID)
		return err
	})
	return job, err
}
