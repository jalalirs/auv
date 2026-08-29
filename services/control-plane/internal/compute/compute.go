// Package compute owns the hardware a dive runs on.
//
// The governed resource is the queue, not the GPU. Access is granted to a
// queue; a queue holds however many devices it holds. That is what lets one
// workstation and, later, a rack or a cloud region be described the same way,
// and it is why adding hardware is an insert rather than a migration.
//
// Devices are claimed whole. The workstation this was written on cannot
// partition a GPU — MIG is a data-centre feature and an RTX 5880 Ada reports
// none — so a fractional claim would be a promise the hardware does not keep.
// A run still records the share it asked for, so the scheduler's arithmetic is
// already fractional on the day a device can honour it.
package compute

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
)

// Queue is a pool of devices that access is granted to.
type Queue struct {
	ID           string    `json:"id"`
	Slug         string    `json:"slug"`
	Name         string    `json:"name"`
	Summary      string    `json:"summary"`
	LeaseSeconds int       `json:"leaseSeconds"`
	Draining     bool      `json:"draining"`
	CreatedAt    time.Time `json:"createdAt"`
	CreatedBy    string    `json:"createdBy"`

	// Filled by listings, because "one free of two" is the only thing anyone
	// actually wants to know about a queue.
	Devices int `json:"devices"`
	Free    int `json:"free"`
}

// Device is one GPU, in one queue, on a host that runs an agent.
type Device struct {
	ID          string    `json:"id"`
	QueueID     string    `json:"queueId"`
	TargetID    string    `json:"targetId"`
	DeviceIndex int       `json:"deviceIndex"`
	UUID        string    `json:"uuid"`
	Model       string    `json:"model"`
	MemoryBytes int64     `json:"memoryBytes"`
	Enabled     bool      `json:"enabled"`
	CreatedAt   time.Time `json:"createdAt"`
}

// QueueSpec describes a queue to open.
type QueueSpec struct {
	Slug         string
	Name         string
	Summary      string
	LeaseSeconds int
	CreatedBy    string
}

// Validate reports whether the queue is described well enough to open.
func (q QueueSpec) Validate() error {
	if err := domain.ValidateSlug(q.Slug); err != nil {
		return err
	}
	if strings.TrimSpace(q.Name) == "" {
		return fmt.Errorf("%w: a queue has a name", domain.ErrInvalid)
	}
	// A lease shorter than a minute would expire while a node was still
	// fetching the city it was told to run in.
	if q.LeaseSeconds != 0 && q.LeaseSeconds < 60 {
		return fmt.Errorf("%w: a lease is at least sixty seconds, got %d",
			domain.ErrInvalid, q.LeaseSeconds)
	}
	return nil
}

// DeviceSpec describes a device to place in a queue.
type DeviceSpec struct {
	QueueID     string
	TargetID    string
	DeviceIndex int
	UUID        string
	Model       string
	MemoryBytes int64
}

// Validate reports whether the device is described well enough to admit.
func (d DeviceSpec) Validate() error {
	if strings.TrimSpace(d.UUID) == "" {
		return fmt.Errorf(
			"%w: a device is identified by its UUID, which survives a reboot reordering the indices",
			domain.ErrInvalid)
	}
	if d.DeviceIndex < 0 {
		return fmt.Errorf("%w: a device index is not negative", domain.ErrInvalid)
	}
	if d.MemoryBytes <= 0 {
		return fmt.Errorf("%w: a device has memory", domain.ErrInvalid)
	}
	return nil
}

// Store reads and writes queues and the devices in them.
type Store struct{ pool *db.Pool }

// NewStore builds the compute store.
func NewStore(pool *db.Pool) *Store { return &Store{pool: pool} }

// The counts are part of what a queue is to a caller, so every read carries
// them rather than leaving each caller to work them out differently.
const selectQueue = `
	SELECT q.id, q.slug, q.name, q.summary, q.lease_seconds, q.draining,
	       q.created_at, q.created_by,
	       count(d.id) FILTER (WHERE d.enabled),
	       count(d.id) FILTER (WHERE d.enabled AND r.id IS NULL)
	FROM compute.queue q
	LEFT JOIN compute.device d ON d.queue_id = q.id
	LEFT JOIN dive.run r ON r.device_id = d.id AND r.state IN ('preparing', 'running')`

const groupQueue = ` GROUP BY q.id`

func scanQueue(row interface{ Scan(...any) error }) (Queue, error) {
	var queue Queue
	err := row.Scan(&queue.ID, &queue.Slug, &queue.Name, &queue.Summary,
		&queue.LeaseSeconds, &queue.Draining, &queue.CreatedAt, &queue.CreatedBy,
		&queue.Devices, &queue.Free)
	return queue, err
}

// CreateQueue opens a queue.
func (s *Store) CreateQueue(ctx context.Context, conn db.Conn, spec QueueSpec) (Queue, error) {
	if err := spec.Validate(); err != nil {
		return Queue{}, err
	}
	lease := spec.LeaseSeconds
	if lease == 0 {
		lease = 3600
	}

	id := ids.New(ids.KindQueue)
	_, err := conn.Exec(ctx, `
		INSERT INTO compute.queue (id, slug, name, summary, lease_seconds, created_by)
		VALUES ($1, $2, $3, $4, $5, $6)`,
		id, spec.Slug, spec.Name, spec.Summary, lease, spec.CreatedBy)
	if err != nil {
		if db.IsUniqueViolation(err) {
			return Queue{}, fmt.Errorf("%w: a queue named %q already exists",
				domain.ErrInvalid, spec.Slug)
		}
		return Queue{}, fmt.Errorf("opening a queue: %w", err)
	}
	return scanQueue(conn.QueryRow(ctx, selectQueue+` WHERE q.id = $1`+groupQueue, id))
}

// Queue reads one queue.
func (s *Store) Queue(ctx context.Context, id string) (Queue, error) {
	queue, err := scanQueue(s.pool.QueryRow(ctx, selectQueue+` WHERE q.id = $1`+groupQueue, id))
	return queue, db.Translate(err)
}

// QueueBySlug reads one queue by its stable name.
func (s *Store) QueueBySlug(ctx context.Context, slug string) (Queue, error) {
	queue, err := scanQueue(s.pool.QueryRow(ctx, selectQueue+` WHERE q.slug = $1`+groupQueue, slug))
	return queue, db.Translate(err)
}

// Queues lists the queues a subject may submit to.
//
// There is no discoverable queue: hardware is granted or it is invisible.
// Someone who cannot run on a queue has no reason to learn it exists.
func (s *Store) Queues(ctx context.Context, all bool, boundIDs []string) ([]Queue, error) {
	rows, err := s.pool.Query(ctx, selectQueue+`
		WHERE $1::boolean OR q.id = ANY($2)`+groupQueue+` ORDER BY q.name`, all, boundIDs)
	if err != nil {
		return nil, fmt.Errorf("listing queues: %w", err)
	}
	defer rows.Close()

	queues := []Queue{}
	for rows.Next() {
		queue, err := scanQueue(rows)
		if err != nil {
			return nil, err
		}
		queues = append(queues, queue)
	}
	return queues, rows.Err()
}

// SetDraining stops a queue accepting new work while letting what it holds
// finish, which is how a host is taken out of service without killing a dive.
func (s *Store) SetDraining(ctx context.Context, conn db.Conn, id string, draining bool) error {
	tag, err := conn.Exec(ctx,
		`UPDATE compute.queue SET draining = $2 WHERE id = $1`, id, draining)
	if err != nil {
		return fmt.Errorf("draining a queue: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return db.ErrNotFound
	}
	return nil
}

const selectDevice = `
	SELECT id, queue_id, target_id, device_index, uuid, model, memory_bytes,
	       enabled, created_at
	FROM compute.device`

func scanDevice(row interface{ Scan(...any) error }) (Device, error) {
	var device Device
	err := row.Scan(&device.ID, &device.QueueID, &device.TargetID, &device.DeviceIndex,
		&device.UUID, &device.Model, &device.MemoryBytes, &device.Enabled, &device.CreatedAt)
	return device, err
}

// AddDevice places a device in a queue.
//
// Idempotent on the device's UUID, because an agent re-registers what it found
// every time it starts and a restarted host must not double its own capacity.
func (s *Store) AddDevice(ctx context.Context, conn db.Conn, spec DeviceSpec) (Device, error) {
	if err := spec.Validate(); err != nil {
		return Device{}, err
	}
	id := ids.New(ids.KindDevice)
	_, err := conn.Exec(ctx, `
		INSERT INTO compute.device
		    (id, queue_id, target_id, device_index, uuid, model, memory_bytes)
		VALUES ($1, $2, $3, $4, $5, $6, $7)
		ON CONFLICT (uuid) DO UPDATE SET
		    queue_id = excluded.queue_id,
		    target_id = excluded.target_id,
		    device_index = excluded.device_index,
		    model = excluded.model,
		    memory_bytes = excluded.memory_bytes`,
		id, spec.QueueID, spec.TargetID, spec.DeviceIndex, spec.UUID,
		spec.Model, spec.MemoryBytes)
	if err != nil {
		return Device{}, fmt.Errorf("adding a device: %w", err)
	}
	device, err := scanDevice(conn.QueryRow(ctx, selectDevice+` WHERE uuid = $1`, spec.UUID))
	return device, db.Translate(err)
}

// Devices lists the devices in a queue.
func (s *Store) Devices(ctx context.Context, queueID string) ([]Device, error) {
	rows, err := s.pool.Query(ctx, selectDevice+` WHERE queue_id = $1 ORDER BY target_id, device_index`,
		queueID)
	if err != nil {
		return nil, fmt.Errorf("listing devices: %w", err)
	}
	defer rows.Close()

	devices := []Device{}
	for rows.Next() {
		device, err := scanDevice(rows)
		if err != nil {
			return nil, err
		}
		devices = append(devices, device)
	}
	return devices, rows.Err()
}

// ClaimFree returns a device in the queue that no run is holding, or
// db.ErrNotFound when every device is busy.
//
// The row is locked for the caller's transaction, because two schedulers
// asking at the same moment is the case a scheduler cannot check for itself.
// The unique index on running runs is the second line of defence; this is the
// first.
func (s *Store) ClaimFree(ctx context.Context, conn db.Conn, queueID string) (Device, error) {
	device, err := scanDevice(conn.QueryRow(ctx, `
		SELECT d.id, d.queue_id, d.target_id, d.device_index, d.uuid, d.model,
		       d.memory_bytes, d.enabled, d.created_at
		FROM compute.device d
		JOIN compute.queue q ON q.id = d.queue_id
		WHERE d.queue_id = $1
		  AND d.enabled
		  AND NOT q.draining
		  AND NOT EXISTS (
		      SELECT 1 FROM dive.run r
		       WHERE r.device_id = d.id AND r.state IN ('preparing', 'running'))
		ORDER BY d.device_index
		FOR UPDATE OF d SKIP LOCKED
		LIMIT 1`, queueID))
	return device, db.Translate(err)
}
