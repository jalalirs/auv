package exec

import (
	"context"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
)

// Schedule is work the platform runs for itself, without anyone asking.
//
// The daily loop is built from these: observations and forecasts arrive as new
// canonical layer versions on a cadence, which is what makes the platform
// current rather than an archive.
type Schedule struct {
	ID              string    `json:"id"`
	Name            string    `json:"name"`
	OrgID           string    `json:"orgId"`
	Spec            JobSpec   `json:"-"`
	IntervalSeconds int       `json:"intervalSeconds"`
	Enabled         bool      `json:"enabled"`
	NextRunAt       time.Time `json:"nextRunAt"`
	LastJobID       string    `json:"lastJobId,omitempty"`
	CreatedAt       time.Time `json:"createdAt"`
	RecipeID        string    `json:"recipeId"`
	ImageDigest     string    `json:"imageDigest"`
}

// ScheduleSpec describes recurring work to create.
type ScheduleSpec struct {
	Name            string
	Job             JobSpec
	IntervalSeconds int
	FirstRunAt      time.Time
}

// Validate reports whether the recurring work is fully described.
func (s ScheduleSpec) Validate() error {
	if strings.TrimSpace(s.Name) == "" {
		return fmt.Errorf("%w: recurring work has a name", domain.ErrInvalid)
	}
	if s.IntervalSeconds < 60 {
		return fmt.Errorf("%w: recurring work repeats no more often than once a minute",
			domain.ErrInvalid)
	}
	if s.FirstRunAt.IsZero() {
		return fmt.Errorf("%w: recurring work states when it first runs", domain.ErrInvalid)
	}
	return s.Job.Validate()
}

// CreateSchedule records recurring work, or updates it if the name is known.
func (b *Broker) CreateSchedule(ctx context.Context, conn db.Conn, spec ScheduleSpec) (Schedule, error) {
	if err := spec.Validate(); err != nil {
		return Schedule{}, err
	}
	inputs, err := json.Marshal(spec.Job.Inputs)
	if err != nil {
		return Schedule{}, fmt.Errorf("encoding scheduled inputs: %w", err)
	}
	outputs, err := json.Marshal(spec.Job.Outputs)
	if err != nil {
		return Schedule{}, fmt.Errorf("encoding scheduled outputs: %w", err)
	}
	args := spec.Job.Args
	if args == nil {
		args = []string{}
	}

	id := ids.New(ids.KindSchedule)
	_, err = conn.Exec(ctx, `
		INSERT INTO exec.schedule (
		    id, name, org_id, submitted_by, recipe_id, image_digest, command, args,
		    inputs, outputs, request_cpu, request_memory_bytes, request_gpu,
		    walltime_seconds, interval_seconds, next_run_at)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16)
		ON CONFLICT (name) DO UPDATE SET
		    recipe_id = EXCLUDED.recipe_id,
		    image_digest = EXCLUDED.image_digest,
		    command = EXCLUDED.command,
		    args = EXCLUDED.args,
		    inputs = EXCLUDED.inputs,
		    outputs = EXCLUDED.outputs,
		    request_cpu = EXCLUDED.request_cpu,
		    request_memory_bytes = EXCLUDED.request_memory_bytes,
		    request_gpu = EXCLUDED.request_gpu,
		    walltime_seconds = EXCLUDED.walltime_seconds,
		    interval_seconds = EXCLUDED.interval_seconds`,
		id, spec.Name, spec.Job.OrgID, spec.Job.SubmittedBy, spec.Job.RecipeID,
		spec.Job.ImageDigest, spec.Job.Command, args, inputs, outputs,
		spec.Job.RequestCPU, spec.Job.RequestMemoryBytes, spec.Job.RequestGPU,
		spec.Job.WalltimeSeconds, spec.IntervalSeconds, spec.FirstRunAt)
	if err != nil {
		return Schedule{}, fmt.Errorf("recording recurring work: %w", err)
	}
	return b.ScheduleByName(ctx, spec.Name)
}

const selectSchedule = `
	SELECT id, name, org_id, submitted_by, recipe_id, image_digest, command, args,
	       inputs, outputs, request_cpu, request_memory_bytes, request_gpu,
	       walltime_seconds, interval_seconds, enabled, next_run_at,
	       coalesce(last_job_id, ''), created_at
	FROM exec.schedule`

func scanSchedule(row interface{ Scan(...any) error }) (Schedule, error) {
	var schedule Schedule
	var inputs, outputs []byte
	err := row.Scan(&schedule.ID, &schedule.Name, &schedule.OrgID, &schedule.Spec.SubmittedBy,
		&schedule.RecipeID, &schedule.ImageDigest, &schedule.Spec.Command, &schedule.Spec.Args,
		&inputs, &outputs, &schedule.Spec.RequestCPU, &schedule.Spec.RequestMemoryBytes,
		&schedule.Spec.RequestGPU, &schedule.Spec.WalltimeSeconds, &schedule.IntervalSeconds,
		&schedule.Enabled, &schedule.NextRunAt, &schedule.LastJobID, &schedule.CreatedAt)
	if err != nil {
		return Schedule{}, err
	}
	if err := json.Unmarshal(inputs, &schedule.Spec.Inputs); err != nil {
		return Schedule{}, fmt.Errorf("reading scheduled inputs: %w", err)
	}
	if err := json.Unmarshal(outputs, &schedule.Spec.Outputs); err != nil {
		return Schedule{}, fmt.Errorf("reading scheduled outputs: %w", err)
	}
	schedule.Spec.OrgID = schedule.OrgID
	schedule.Spec.RecipeID = schedule.RecipeID
	schedule.Spec.ImageDigest = schedule.ImageDigest
	return schedule, nil
}

// ScheduleByName reads recurring work by its stable name.
func (b *Broker) ScheduleByName(ctx context.Context, name string) (Schedule, error) {
	schedule, err := scanSchedule(b.pool.QueryRow(ctx, selectSchedule+` WHERE name = $1`, name))
	return schedule, db.Translate(err)
}

// Schedules lists every piece of recurring work.
func (b *Broker) Schedules(ctx context.Context) ([]Schedule, error) {
	rows, err := b.pool.Query(ctx, selectSchedule+` ORDER BY name`)
	if err != nil {
		return nil, fmt.Errorf("reading recurring work: %w", err)
	}
	defer rows.Close()

	schedules := []Schedule{}
	for rows.Next() {
		schedule, err := scanSchedule(rows)
		if err != nil {
			return nil, err
		}
		schedules = append(schedules, schedule)
	}
	return schedules, rows.Err()
}

// RunDueSchedules submits work for every schedule whose time has come.
//
// The next run is claimed before the job is submitted, so a schedule that fails
// to submit waits for its next turn rather than being retried immediately in a
// loop. Recurring work that must not be missed is better expressed as a shorter
// interval than as a retry storm.
//
// It reports how many jobs were submitted.
func (b *Broker) RunDueSchedules(ctx context.Context) (int, error) {
	rows, err := b.pool.Query(ctx, selectSchedule+` WHERE enabled AND next_run_at <= now()`)
	if err != nil {
		return 0, fmt.Errorf("looking for recurring work that is due: %w", err)
	}
	var due []Schedule
	for rows.Next() {
		schedule, err := scanSchedule(rows)
		if err != nil {
			rows.Close()
			return 0, err
		}
		due = append(due, schedule)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, err
	}

	submitted := 0
	for _, schedule := range due {
		claimed, err := b.claimSchedule(ctx, schedule)
		if err != nil {
			return submitted, err
		}
		if !claimed {
			continue
		}

		job, err := b.Submit(ctx, schedule.Spec)
		if err != nil {
			// The claim stands: the schedule will try again at its next turn,
			// and the refusal, if that is what it was, is already recorded.
			return submitted, fmt.Errorf("submitting scheduled work %q: %w", schedule.Name, err)
		}
		if _, err := b.pool.Exec(ctx,
			`UPDATE exec.schedule SET last_job_id = $2 WHERE id = $1`, schedule.ID, job.ID); err != nil {
			return submitted, fmt.Errorf("recording what recurring work submitted: %w", err)
		}
		submitted++
	}
	return submitted, nil
}

// claimSchedule moves a schedule's next run forward, and reports whether this
// caller is the one that moved it. Two control planes running at once will not
// both submit the same scheduled job.
func (b *Broker) claimSchedule(ctx context.Context, schedule Schedule) (bool, error) {
	tag, err := b.pool.Exec(ctx, `
		UPDATE exec.schedule
		SET next_run_at = greatest(next_run_at, now()) + make_interval(secs => interval_seconds)
		WHERE id = $1 AND enabled AND next_run_at <= now()`, schedule.ID)
	if err != nil {
		return false, fmt.Errorf("claiming recurring work: %w", err)
	}
	return tag.RowsAffected() == 1, nil
}
