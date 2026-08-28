package exec

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
	"github.com/jalalirs/auv/services/control-plane/internal/reqctx"
)

// Refusal is work the platform declined to admit, with the reason recorded.
// A refusal is a decision, not a fault: it is written down and returned in
// terms the caller can act on.
type Refusal struct {
	Reason ReasonCode
	Detail map[string]any
}

// Error renders the refusal for a caller.
func (r *Refusal) Error() string { return r.Reason.Explain(r.Detail) }

// ReasonCode names why work was refused.
type ReasonCode string

const (
	QuotaConcurrentJobsExhausted ReasonCode = "quota_concurrent_jobs_exhausted"
	QuotaCPUExhausted            ReasonCode = "quota_cpu_exhausted"
	QuotaMemoryExhausted         ReasonCode = "quota_memory_exhausted"
	QuotaGPUExhausted            ReasonCode = "quota_gpu_exhausted"
	NoTargetHasCapacity          ReasonCode = "no_target_has_capacity"
	NoTargetEnabled              ReasonCode = "no_target_enabled"
	OrganisationHasNoQuota       ReasonCode = "organisation_has_no_quota"
)

// Explain renders a reason as a sentence a person can act on.
func (c ReasonCode) Explain(detail map[string]any) string {
	switch c {
	case QuotaConcurrentJobsExhausted:
		return fmt.Sprintf("your organisation already has %v jobs in flight, which is its limit of %v",
			detail["inFlight"], detail["limit"])
	case QuotaCPUExhausted:
		return fmt.Sprintf("this job asks for %v processors on top of %v already committed, beyond the limit of %v",
			detail["requested"], detail["committed"], detail["limit"])
	case QuotaMemoryExhausted:
		return fmt.Sprintf("this job asks for %v bytes of memory on top of %v already committed, beyond the limit of %v",
			detail["requested"], detail["committed"], detail["limit"])
	case QuotaGPUExhausted:
		return fmt.Sprintf("this job asks for %v accelerators on top of %v already committed, beyond the limit of %v",
			detail["requested"], detail["committed"], detail["limit"])
	case NoTargetHasCapacity:
		return "no execution target advertises enough capacity for this job"
	case NoTargetEnabled:
		return "no execution target is currently enabled"
	case OrganisationHasNoQuota:
		return "your organisation has no compute quota, so no work can be admitted for it"
	default:
		return string(c)
	}
}

// Broker admits or refuses work.
//
// It decides nothing about who may submit: that is settled by the decision
// point before this is reached. What it decides is whether there is room, and
// it writes down either answer.
type Broker struct{ pool *db.Pool }

// NewBroker builds the admission component.
func NewBroker(pool *db.Pool) *Broker { return &Broker{pool: pool} }

// Submit admits work or refuses it, recording whichever happened.
//
// Admission and placement occur in one transaction with the quota reading they
// were based on, so two simultaneous submissions cannot both be admitted past
// the same limit.
func (b *Broker) Submit(ctx context.Context, spec JobSpec) (Job, error) {
	if err := spec.Validate(); err != nil {
		return Job{}, err
	}

	var job Job
	err := b.pool.InTransaction(ctx, func(conn db.Conn) error {
		quota, err := lockQuota(ctx, conn, spec.OrgID)
		if err != nil {
			if errors.Is(err, db.ErrNotFound) {
				return b.refuse(ctx, conn, spec, &Refusal{Reason: OrganisationHasNoQuota})
			}
			return err
		}

		committed, err := commitmentOf(ctx, conn, spec.OrgID)
		if err != nil {
			return err
		}
		if refusal := checkQuota(spec, quota, committed); refusal != nil {
			return b.refuse(ctx, conn, spec, refusal)
		}

		target, refusal, err := pickTarget(ctx, conn, spec)
		if err != nil {
			return err
		}
		if refusal != nil {
			return b.refuse(ctx, conn, spec, refusal)
		}

		job, err = insertJob(ctx, conn, spec, target.ID)
		if err != nil {
			return err
		}

		// What the result becomes is fixed here, at submission, and the record
		// refuses to let it change afterwards.
		if spec.Publish != nil {
			if _, err := conn.Exec(ctx, `
				INSERT INTO exec.publication
				    (job_id, layer_id, descriptor_output, publish, promote, supersede_previous)
				VALUES ($1, $2, $3, $4, $5, $6)`,
				job.ID, spec.Publish.LayerID, spec.Publish.DescriptorOutput,
				spec.Publish.Publish, spec.Publish.Promote,
				spec.Publish.SupersedePrevious); err != nil {
				return fmt.Errorf("recording what this job will publish: %w", err)
			}
		}

		snapshot, err := json.Marshal(map[string]any{
			"limit":     quota,
			"committed": committed,
		})
		if err != nil {
			return fmt.Errorf("recording the quota an admission was based on: %w", err)
		}
		if _, err := conn.Exec(ctx, `
			INSERT INTO exec.admission (id, job_id, target_id, quota_snapshot, request_id)
			VALUES ($1, $2, $3, $4, $5)`,
			ids.New(ids.KindAdmission), job.ID, target.ID, snapshot, reqctx.RequestID(ctx)); err != nil {
			return fmt.Errorf("recording an admission: %w", err)
		}

		return appendEvent(ctx, conn, job.ID, "", EventAdmitted, map[string]any{
			"targetId":   target.ID,
			"targetName": target.Name,
		})
	})
	if err != nil {
		return Job{}, err
	}
	return job, nil
}

// commitment is what an organisation already has in flight.
type commitment struct {
	Jobs        int     `json:"jobs"`
	CPU         float64 `json:"cpu"`
	MemoryBytes int64   `json:"memoryBytes"`
	GPU         int     `json:"gpu"`
}

func lockQuota(ctx context.Context, conn db.Conn, orgID string) (Quota, error) {
	var quota Quota
	// Locking the quota row serialises simultaneous submissions from one
	// organisation, so a limit cannot be crossed by two requests at once.
	err := conn.QueryRow(ctx, `
		SELECT org_id, max_concurrent_jobs, max_cpu, max_memory_bytes, max_gpu, updated_at
		FROM exec.quota WHERE org_id = $1 FOR UPDATE`, orgID).
		Scan(&quota.OrgID, &quota.MaxConcurrentJobs, &quota.MaxCPU,
			&quota.MaxMemoryBytes, &quota.MaxGPU, &quota.UpdatedAt)
	return quota, db.Translate(err)
}

func commitmentOf(ctx context.Context, conn db.Conn, orgID string) (commitment, error) {
	var current commitment
	err := conn.QueryRow(ctx, `
		SELECT count(*), coalesce(sum(request_cpu), 0), coalesce(sum(request_memory_bytes), 0),
		       coalesce(sum(request_gpu), 0)
		FROM exec.job
		WHERE org_id = $1 AND state IN ('pending', 'admitted', 'running')`, orgID).
		Scan(&current.Jobs, &current.CPU, &current.MemoryBytes, &current.GPU)
	if err != nil {
		return commitment{}, fmt.Errorf("reading what is already in flight: %w", err)
	}
	return current, nil
}

func checkQuota(spec JobSpec, quota Quota, committed commitment) *Refusal {
	if committed.Jobs+1 > quota.MaxConcurrentJobs {
		return &Refusal{Reason: QuotaConcurrentJobsExhausted, Detail: map[string]any{
			"inFlight": committed.Jobs, "limit": quota.MaxConcurrentJobs}}
	}
	if committed.CPU+spec.RequestCPU > quota.MaxCPU {
		return &Refusal{Reason: QuotaCPUExhausted, Detail: map[string]any{
			"requested": spec.RequestCPU, "committed": committed.CPU, "limit": quota.MaxCPU}}
	}
	if committed.MemoryBytes+spec.RequestMemoryBytes > quota.MaxMemoryBytes {
		return &Refusal{Reason: QuotaMemoryExhausted, Detail: map[string]any{
			"requested": spec.RequestMemoryBytes, "committed": committed.MemoryBytes,
			"limit": quota.MaxMemoryBytes}}
	}
	if committed.GPU+spec.RequestGPU > quota.MaxGPU {
		return &Refusal{Reason: QuotaGPUExhausted, Detail: map[string]any{
			"requested": spec.RequestGPU, "committed": committed.GPU, "limit": quota.MaxGPU}}
	}
	return nil
}

func pickTarget(ctx context.Context, conn db.Conn, spec JobSpec) (Target, *Refusal, error) {
	var enabled int
	if err := conn.QueryRow(ctx,
		`SELECT count(*) FROM exec.target WHERE enabled`).Scan(&enabled); err != nil {
		return Target{}, nil, fmt.Errorf("reading execution targets: %w", err)
	}
	if enabled == 0 {
		return Target{}, &Refusal{Reason: NoTargetEnabled}, nil
	}

	var target Target
	// The smallest target that fits is chosen, so that large capacity stays
	// available for work that needs it.
	err := conn.QueryRow(ctx, `
		SELECT id, name, kind, enabled, capacity_cpu, capacity_memory_bytes, capacity_gpu, created_at
		FROM exec.target
		WHERE enabled
		  AND capacity_cpu >= $1 AND capacity_memory_bytes >= $2 AND capacity_gpu >= $3
		ORDER BY capacity_gpu, capacity_cpu, capacity_memory_bytes
		LIMIT 1`,
		spec.RequestCPU, spec.RequestMemoryBytes, spec.RequestGPU).
		Scan(&target.ID, &target.Name, &target.Kind, &target.Enabled,
			&target.CapacityCPU, &target.CapacityMemoryBytes, &target.CapacityGPU, &target.CreatedAt)
	if errors.Is(db.Translate(err), db.ErrNotFound) {
		return Target{}, &Refusal{Reason: NoTargetHasCapacity}, nil
	}
	if err != nil {
		return Target{}, nil, fmt.Errorf("choosing an execution target: %w", err)
	}
	return target, nil, nil
}

func (b *Broker) refuse(ctx context.Context, conn db.Conn, spec JobSpec, refusal *Refusal) error {
	detail := refusal.Detail
	if detail == nil {
		detail = map[string]any{}
	}
	encoded, err := json.Marshal(detail)
	if err != nil {
		return fmt.Errorf("recording a refusal: %w", err)
	}
	if _, err := conn.Exec(ctx, `
		INSERT INTO exec.refusal (id, org_id, principal_id, reason, detail, request_id)
		VALUES ($1, $2, $3, $4::exec.refusal_reason, $5, $6)`,
		ids.New(ids.KindRefusal), spec.OrgID, spec.SubmittedBy,
		string(refusal.Reason), encoded, reqctx.RequestID(ctx)); err != nil {
		return fmt.Errorf("recording a refusal: %w", err)
	}
	return refusal
}

func insertJob(ctx context.Context, conn db.Conn, spec JobSpec, targetID string) (Job, error) {
	inputs, err := json.Marshal(spec.Inputs)
	if err != nil {
		return Job{}, fmt.Errorf("encoding job inputs: %w", err)
	}
	outputs, err := json.Marshal(spec.Outputs)
	if err != nil {
		return Job{}, fmt.Errorf("encoding job outputs: %w", err)
	}
	args := spec.Args
	if args == nil {
		args = []string{}
	}

	egress, err := ParseEgress(string(spec.Egress))
	if err != nil {
		return Job{}, err
	}

	id := ids.New(ids.KindJob)
	_, err = conn.Exec(ctx, `
		INSERT INTO exec.job (
		    id, org_id, submitted_by, recipe_id, image_digest, command, args,
		    inputs, outputs, request_cpu, request_memory_bytes, request_gpu,
		    walltime_seconds, target_id, egress, state)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14,
		        $15::exec.egress, 'admitted')`,
		id, spec.OrgID, spec.SubmittedBy, spec.RecipeID, spec.ImageDigest,
		spec.Command, args, inputs, outputs,
		spec.RequestCPU, spec.RequestMemoryBytes, spec.RequestGPU,
		spec.WalltimeSeconds, targetID, string(egress))
	if err != nil {
		return Job{}, fmt.Errorf("admitting work: %w", err)
	}
	return jobOn(ctx, conn, id)
}
