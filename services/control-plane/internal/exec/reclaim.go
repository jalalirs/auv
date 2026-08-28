package exec

import (
	"context"
	"fmt"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
)

// ReclaimExpiredLeases returns work whose worker stopped reporting.
//
// A worker that dies mid-attempt cannot say so. Its lease simply stops being
// renewed, and the platform takes the work back: the attempt is marked evicted
// and the job becomes available again, up to the retry limit. This is what
// makes worker failure recoverable without anyone intervening.
//
// It reports how many attempts were reclaimed.
func (b *Broker) ReclaimExpiredLeases(ctx context.Context, maxAttempts int) (int, error) {
	rows, err := b.pool.Query(ctx, `
		SELECT id, job_id FROM exec.attempt
		WHERE state IN ('leased', 'running') AND lease_expires_at <= now()`)
	if err != nil {
		return 0, fmt.Errorf("looking for expired leases: %w", err)
	}
	type expired struct{ attemptID, jobID string }
	var stale []expired
	for rows.Next() {
		var record expired
		if err := rows.Scan(&record.attemptID, &record.jobID); err != nil {
			rows.Close()
			return 0, err
		}
		stale = append(stale, record)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, err
	}

	reclaimed := 0
	for _, record := range stale {
		err := b.pool.InTransaction(ctx, func(conn db.Conn) error {
			// Re-check under the transaction: the worker may have reported in
			// between the scan and now, in which case there is nothing to take.
			tag, err := conn.Exec(ctx, `
				UPDATE exec.attempt
				SET state = 'evicted', finished_at = now(), failure_class = 'worker_lost'
				WHERE id = $1 AND state IN ('leased', 'running') AND lease_expires_at <= now()`,
				record.attemptID)
			if err != nil {
				return fmt.Errorf("reclaiming an attempt: %w", err)
			}
			if tag.RowsAffected() == 0 {
				return nil
			}

			var attempts int
			if err := conn.QueryRow(ctx,
				`SELECT count(*) FROM exec.attempt WHERE job_id = $1`, record.jobID).
				Scan(&attempts); err != nil {
				return fmt.Errorf("counting attempts: %w", err)
			}

			if err := appendEvent(ctx, conn, record.jobID, record.attemptID, EventEvicted,
				map[string]any{"reason": "the worker holding this attempt stopped reporting",
					"attempts": attempts}); err != nil {
				return err
			}

			if attempts < maxAttempts {
				_, err = conn.Exec(ctx,
					`UPDATE exec.job SET state = 'admitted' WHERE id = $1 AND state = 'running'`,
					record.jobID)
				if err != nil {
					return fmt.Errorf("returning work to the queue: %w", err)
				}
				reclaimed++
				return nil
			}

			if _, err := conn.Exec(ctx, `
				UPDATE exec.job
				SET state = 'failed', failure_class = 'worker_lost', terminal_at = now()
				WHERE id = $1 AND state = 'running'`, record.jobID); err != nil {
				return fmt.Errorf("ending work whose workers all stopped reporting: %w", err)
			}
			if err := appendEvent(ctx, conn, record.jobID, record.attemptID, EventFailed,
				map[string]any{"failureClass": string(WorkerLost), "attempts": attempts}); err != nil {
				return err
			}
			reclaimed++
			return nil
		})
		if err != nil {
			return reclaimed, err
		}
	}
	return reclaimed, nil
}

// EnforceWalltime ends work that has run longer than it declared it would.
//
// A job states the time after which it should be stopped, and that statement is
// enforced by the platform rather than trusted to the work itself.
func (b *Broker) EnforceWalltime(ctx context.Context) (int, error) {
	rows, err := b.pool.Query(ctx, `
		SELECT a.id, a.job_id
		FROM exec.attempt a
		JOIN exec.job j ON j.id = a.job_id
		WHERE a.state = 'running'
		  AND a.started_at IS NOT NULL
		  AND a.started_at + make_interval(secs => j.walltime_seconds) < now()`)
	if err != nil {
		return 0, fmt.Errorf("looking for work past its deadline: %w", err)
	}
	type overrun struct{ attemptID, jobID string }
	var late []overrun
	for rows.Next() {
		var record overrun
		if err := rows.Scan(&record.attemptID, &record.jobID); err != nil {
			rows.Close()
			return 0, err
		}
		late = append(late, record)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, err
	}

	stopped := 0
	for _, record := range late {
		err := b.pool.InTransaction(ctx, func(conn db.Conn) error {
			tag, err := conn.Exec(ctx, `
				UPDATE exec.attempt
				SET state = 'timed_out', finished_at = now(), failure_class = 'walltime_exceeded'
				WHERE id = $1 AND state = 'running'`, record.attemptID)
			if err != nil {
				return fmt.Errorf("stopping work past its deadline: %w", err)
			}
			if tag.RowsAffected() == 0 {
				return nil
			}
			if _, err := conn.Exec(ctx, `
				UPDATE exec.job
				SET state = 'timed_out', failure_class = 'walltime_exceeded', terminal_at = now()
				WHERE id = $1 AND state = 'running'`, record.jobID); err != nil {
				return fmt.Errorf("ending work past its deadline: %w", err)
			}
			if err := appendEvent(ctx, conn, record.jobID, record.attemptID, EventTimedOut,
				map[string]any{"failureClass": string(WalltimeExceeded)}); err != nil {
				return err
			}
			stopped++
			return nil
		})
		if err != nil {
			return stopped, err
		}
	}
	return stopped, nil
}
