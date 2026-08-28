package exec

import (
	"context"
	"fmt"
	"strings"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
)

// TargetSpec describes a place work can run.
type TargetSpec struct {
	Name                string
	Kind                TargetKind
	CapacityCPU         float64
	CapacityMemoryBytes int64
	CapacityGPU         int
}

// Validate reports whether the target is usable.
func (t TargetSpec) Validate() error {
	if strings.TrimSpace(t.Name) == "" {
		return fmt.Errorf("%w: an execution target has a name", domain.ErrInvalid)
	}
	switch t.Kind {
	case LocalDocker, Kubernetes, Slurm:
	default:
		return fmt.Errorf("%w: %q is not an execution target kind", domain.ErrInvalid, t.Kind)
	}
	if t.CapacityCPU <= 0 || t.CapacityMemoryBytes <= 0 {
		return fmt.Errorf("%w: an execution target advertises processor and memory capacity",
			domain.ErrInvalid)
	}
	if t.CapacityGPU < 0 {
		return fmt.Errorf("%w: a capacity of %d accelerators is not a capacity",
			domain.ErrInvalid, t.CapacityGPU)
	}
	return nil
}

// RegisterTarget records a place work can run, or updates the capacity an
// existing one advertises.
func (b *Broker) RegisterTarget(ctx context.Context, conn db.Conn, spec TargetSpec) (Target, error) {
	if err := spec.Validate(); err != nil {
		return Target{}, err
	}
	var target Target
	err := conn.QueryRow(ctx, `
		INSERT INTO exec.target
		    (id, name, kind, capacity_cpu, capacity_memory_bytes, capacity_gpu)
		VALUES ($1, $2, $3::exec.target_kind, $4, $5, $6)
		ON CONFLICT (name) DO UPDATE SET
		    kind = EXCLUDED.kind,
		    capacity_cpu = EXCLUDED.capacity_cpu,
		    capacity_memory_bytes = EXCLUDED.capacity_memory_bytes,
		    capacity_gpu = EXCLUDED.capacity_gpu
		RETURNING id, name, kind, enabled, capacity_cpu, capacity_memory_bytes,
		          capacity_gpu, created_at`,
		ids.New(ids.KindTarget), spec.Name, string(spec.Kind),
		spec.CapacityCPU, spec.CapacityMemoryBytes, spec.CapacityGPU).
		Scan(&target.ID, &target.Name, &target.Kind, &target.Enabled,
			&target.CapacityCPU, &target.CapacityMemoryBytes, &target.CapacityGPU, &target.CreatedAt)
	if err != nil {
		return Target{}, fmt.Errorf("registering an execution target: %w", err)
	}
	return target, nil
}

// TargetByName reads one place work can run.
func (b *Broker) TargetByName(ctx context.Context, name string) (Target, error) {
	var target Target
	err := b.pool.QueryRow(ctx, `
		SELECT id, name, kind, enabled, capacity_cpu, capacity_memory_bytes, capacity_gpu, created_at
		FROM exec.target WHERE name = $1`, name).
		Scan(&target.ID, &target.Name, &target.Kind, &target.Enabled,
			&target.CapacityCPU, &target.CapacityMemoryBytes, &target.CapacityGPU, &target.CreatedAt)
	return target, db.Translate(err)
}

// Targets lists every place work can run.
func (b *Broker) Targets(ctx context.Context) ([]Target, error) {
	rows, err := b.pool.Query(ctx, `
		SELECT id, name, kind, enabled, capacity_cpu, capacity_memory_bytes, capacity_gpu, created_at
		FROM exec.target ORDER BY name`)
	if err != nil {
		return nil, fmt.Errorf("reading execution targets: %w", err)
	}
	defer rows.Close()

	targets := []Target{}
	for rows.Next() {
		var target Target
		if err := rows.Scan(&target.ID, &target.Name, &target.Kind, &target.Enabled,
			&target.CapacityCPU, &target.CapacityMemoryBytes, &target.CapacityGPU,
			&target.CreatedAt); err != nil {
			return nil, err
		}
		targets = append(targets, target)
	}
	return targets, rows.Err()
}

// SetQuota states what one organisation may consume at once.
func (b *Broker) SetQuota(ctx context.Context, conn db.Conn, quota Quota) (Quota, error) {
	if quota.MaxConcurrentJobs < 0 || quota.MaxCPU < 0 || quota.MaxMemoryBytes < 0 || quota.MaxGPU < 0 {
		return Quota{}, fmt.Errorf("%w: a quota is not negative", domain.ErrInvalid)
	}
	var stored Quota
	err := conn.QueryRow(ctx, `
		INSERT INTO exec.quota (org_id, max_concurrent_jobs, max_cpu, max_memory_bytes, max_gpu)
		VALUES ($1, $2, $3, $4, $5)
		ON CONFLICT (org_id) DO UPDATE SET
		    max_concurrent_jobs = EXCLUDED.max_concurrent_jobs,
		    max_cpu = EXCLUDED.max_cpu,
		    max_memory_bytes = EXCLUDED.max_memory_bytes,
		    max_gpu = EXCLUDED.max_gpu,
		    updated_at = now()
		RETURNING org_id, max_concurrent_jobs, max_cpu, max_memory_bytes, max_gpu, updated_at`,
		quota.OrgID, quota.MaxConcurrentJobs, quota.MaxCPU, quota.MaxMemoryBytes, quota.MaxGPU).
		Scan(&stored.OrgID, &stored.MaxConcurrentJobs, &stored.MaxCPU,
			&stored.MaxMemoryBytes, &stored.MaxGPU, &stored.UpdatedAt)
	if err != nil {
		return Quota{}, fmt.Errorf("setting a quota: %w", err)
	}
	return stored, nil
}

// Quota reads what one organisation may consume, and what it currently does.
func (b *Broker) Quota(ctx context.Context, orgID string) (Quota, map[string]any, error) {
	var quota Quota
	err := b.pool.QueryRow(ctx, `
		SELECT org_id, max_concurrent_jobs, max_cpu, max_memory_bytes, max_gpu, updated_at
		FROM exec.quota WHERE org_id = $1`, orgID).
		Scan(&quota.OrgID, &quota.MaxConcurrentJobs, &quota.MaxCPU,
			&quota.MaxMemoryBytes, &quota.MaxGPU, &quota.UpdatedAt)
	if err != nil {
		return Quota{}, nil, db.Translate(err)
	}
	current, err := commitmentOf(ctx, b.pool, orgID)
	if err != nil {
		return Quota{}, nil, err
	}
	return quota, map[string]any{
		"jobs":        current.Jobs,
		"cpu":         current.CPU,
		"memoryBytes": current.MemoryBytes,
		"gpu":         current.GPU,
	}, nil
}
