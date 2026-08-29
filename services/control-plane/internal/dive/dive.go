// Package dive owns what the platform exists to do.
//
//	Dive = Vehicle × City × Conditions × Autonomy
//
// A dive is a definition; a run is what happened when one was executed. The
// separation matters because a definition can be edited and a result cannot:
// a run copies every determinant at the moment it is admitted, so that editing
// the dive afterwards does not quietly change what a recorded result means.
//
// Interactive and batch are the same object. One holds a video stream and a
// human, the other does not. Making them two kinds of thing would mean two
// schedulers, two records, and eventually two answers to the same question.
package dive

import (
	"context"
	"crypto/rand"
	"encoding/binary"
	"encoding/json"
	"fmt"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
)

// ── What a person brings ─────────────────────────────────────────────────────

// AutonomyStack is the one thing here that is not ours: somebody's own code,
// as a container image, pinned by digest rather than tag. A dive re-run against
// a tag that has moved is measuring a different program and reporting it as the
// same one.
type AutonomyStack struct {
	ID              string          `json:"id"`
	OrgID           string          `json:"orgId"`
	Slug            string          `json:"slug"`
	Name            string          `json:"name"`
	ImageRepository string          `json:"imageRepository"`
	ImageDigest     string          `json:"imageDigest"`
	Subscribes      json.RawMessage `json:"subscribes"`
	Publishes       json.RawMessage `json:"publishes"`
	WantsGPU        bool            `json:"wantsGpu"`
	CreatedAt       time.Time       `json:"createdAt"`
	CreatedBy       string          `json:"createdBy"`
}

// StackSpec describes autonomy to register.
type StackSpec struct {
	OrgID           string
	Slug            string
	Name            string
	ImageRepository string
	ImageDigest     string
	Subscribes      json.RawMessage
	Publishes       json.RawMessage
	WantsGPU        bool
	CreatedBy       string
}

// Validate reports whether the stack is described well enough to admit.
func (s StackSpec) Validate() error {
	if err := domain.ValidateSlug(s.Slug); err != nil {
		return err
	}
	if strings.TrimSpace(s.Name) == "" {
		return fmt.Errorf("%w: an autonomy stack has a name", domain.ErrInvalid)
	}
	if strings.TrimSpace(s.ImageRepository) == "" {
		return fmt.Errorf("%w: an autonomy stack names the image it runs", domain.ErrInvalid)
	}
	// A tag can be moved; a digest cannot. Refusing tags here is what makes a
	// re-run of the same dive a re-run of the same program.
	if !strings.HasPrefix(s.ImageDigest, "sha256:") || len(s.ImageDigest) != 71 {
		return fmt.Errorf(
			"%w: an image is pinned by digest (sha256:…), not by tag, or a re-run is not a re-run",
			domain.ErrInvalid)
	}
	return nil
}

// ── Conditions ───────────────────────────────────────────────────────────────

// ConditionsKind separates water that was measured from water that was
// invented. The distinction is the platform's most important claim about a
// result, so it is a column and not a convention.
type ConditionsKind string

const (
	// Observed conditions are drawn from the ocean as it was at an instant.
	Observed ConditionsKind = "observed"
	// Constructed conditions are a situation somebody chose.
	Constructed ConditionsKind = "constructed"
)

// ParseConditionsKind accepts the kinds the record accepts.
func ParseConditionsKind(value string) (ConditionsKind, error) {
	switch ConditionsKind(value) {
	case Observed:
		return Observed, nil
	case Constructed:
		return Constructed, nil
	default:
		return "", fmt.Errorf("%w: conditions are observed or constructed, not %q",
			domain.ErrInvalid, value)
	}
}

// Conditions is the water a dive happens in.
type Conditions struct {
	ID         string          `json:"id"`
	Kind       ConditionsKind  `json:"kind"`
	Name       string          `json:"name"`
	ObservedAt *time.Time      `json:"observedAt,omitempty"`
	Sources    json.RawMessage `json:"sources"`
	Parameters json.RawMessage `json:"parameters"`
	OrgID      *string         `json:"orgId,omitempty"`
	CreatedAt  time.Time       `json:"createdAt"`
	CreatedBy  string          `json:"createdBy"`
}

// ConditionsSpec describes water to record.
type ConditionsSpec struct {
	Kind       ConditionsKind
	Name       string
	ObservedAt *time.Time
	Sources    json.RawMessage
	Parameters json.RawMessage
	OrgID      *string
	CreatedBy  string
}

// Validate reports whether the conditions are described well enough to dive in.
func (c ConditionsSpec) Validate() error {
	if _, err := ParseConditionsKind(string(c.Kind)); err != nil {
		return err
	}
	if strings.TrimSpace(c.Name) == "" {
		return fmt.Errorf("%w: conditions have a name", domain.ErrInvalid)
	}
	if c.Kind == Observed && c.ObservedAt == nil {
		return fmt.Errorf(
			"%w: observed conditions name the instant the ocean state is drawn from",
			domain.ErrInvalid)
	}
	if c.Kind == Constructed && c.ObservedAt != nil {
		return fmt.Errorf(
			"%w: constructed conditions were not observed at any instant, so naming one would be a claim they do not support",
			domain.ErrInvalid)
	}
	return nil
}

// ── The dive ─────────────────────────────────────────────────────────────────

// Dive is a definition, not an execution. It names versions rather than
// assets, so it does not silently become a different experiment when a newer
// vehicle is published.
type Dive struct {
	ID               string          `json:"id"`
	OrgID            string          `json:"orgId"`
	Name             string          `json:"name"`
	Summary          string          `json:"summary"`
	CityVersionID    string          `json:"cityVersionId"`
	VehicleVersionID string          `json:"vehicleVersionId"`
	ConditionsID     string          `json:"conditionsId"`
	AutonomyStackID  *string         `json:"autonomyStackId,omitempty"`
	InitialState     json.RawMessage `json:"initialState"`
	Objective        json.RawMessage `json:"objective"`
	CreatedAt        time.Time       `json:"createdAt"`
	CreatedBy        string          `json:"createdBy"`
}

// DiveSpec describes a dive to define.
type DiveSpec struct {
	OrgID            string
	Name             string
	CityVersionID    string
	VehicleVersionID string
	ConditionsID     string
	AutonomyStackID  *string
	Summary          string
	InitialState     json.RawMessage
	Objective        json.RawMessage
	CreatedBy        string
}

// Validate reports whether the dive names everything a dive needs.
func (d DiveSpec) Validate() error {
	if strings.TrimSpace(d.Name) == "" {
		return fmt.Errorf("%w: a dive has a name", domain.ErrInvalid)
	}
	for label, value := range map[string]string{
		"a city version":    d.CityVersionID,
		"a vehicle version": d.VehicleVersionID,
		"conditions":        d.ConditionsID,
	} {
		if strings.TrimSpace(value) == "" {
			return fmt.Errorf("%w: a dive names %s", domain.ErrInvalid, label)
		}
	}
	return nil
}

// ── The run ──────────────────────────────────────────────────────────────────

// Mode says whether a human is watching.
type Mode string

const (
	// Interactive holds a device, a stream, and somebody's attention.
	Interactive Mode = "interactive"
	// Batch holds a device and nothing else, and is where the value is: a
	// person watches one dive, a pipeline runs five hundred.
	Batch Mode = "batch"
)

// ParseMode accepts the modes the record accepts.
func ParseMode(value string) (Mode, error) {
	switch Mode(value) {
	case Interactive:
		return Interactive, nil
	case Batch:
		return Batch, nil
	default:
		return "", fmt.Errorf("%w: a run is interactive or batch, not %q", domain.ErrInvalid, value)
	}
}

// State is where a run has got to.
type State string

const (
	Queued    State = "queued"
	Preparing State = "preparing"
	Running   State = "running"
	Succeeded State = "succeeded"
	Failed    State = "failed"
	Cancelled State = "cancelled"
	Expired   State = "expired"
)

// Finished reports whether the run has stopped for good. The record refuses to
// rewrite a run in any of these states.
func (s State) Finished() bool {
	switch s {
	case Succeeded, Failed, Cancelled, Expired:
		return true
	default:
		return false
	}
}

// Run is one execution of a dive, and everything needed to have it again.
type Run struct {
	ID      string `json:"id"`
	DiveID  string `json:"diveId"`
	QueueID string `json:"queueId"`
	Mode    Mode   `json:"mode"`
	State   State  `json:"state"`

	CityDigest       domain.Digest `json:"cityDigest"`
	VehicleDigest    domain.Digest `json:"vehicleDigest"`
	ConditionsDigest domain.Digest `json:"conditionsDigest"`
	AutonomyDigest   *string       `json:"autonomyDigest,omitempty"`

	// Same seed and same digests means the same run. Everything the platform
	// claims about a result rests on this.
	Seed int64 `json:"seed"`

	// The runtime is a determinant too: a physics fix changes results, so
	// comparing across versions has to be refused rather than done quietly.
	RuntimeVersion string `json:"runtimeVersion"`

	DeviceID *string `json:"deviceId,omitempty"`
	GPUShare float64 `json:"gpuShare"`

	RequestedAt    time.Time       `json:"requestedAt"`
	RequestedBy    string          `json:"requestedBy"`
	StartedAt      *time.Time      `json:"startedAt,omitempty"`
	EndedAt        *time.Time      `json:"endedAt,omitempty"`
	LeaseExpiresAt *time.Time      `json:"leaseExpiresAt,omitempty"`
	Outcome        json.RawMessage `json:"outcome"`
	FailureReason  *string         `json:"failureReason,omitempty"`
}

// Store reads and writes dives and their runs.
type Store struct{ pool *db.Pool }

// NewStore builds the dive store.
func NewStore(pool *db.Pool) *Store { return &Store{pool: pool} }

// ── Autonomy stacks ──────────────────────────────────────────────────────────

const selectStack = `
	SELECT id, org_id, slug, name, image_repository, image_digest,
	       subscribes, publishes, wants_gpu, created_at, created_by
	FROM dive.autonomy_stack`

func scanStack(row interface{ Scan(...any) error }) (AutonomyStack, error) {
	var stack AutonomyStack
	err := row.Scan(&stack.ID, &stack.OrgID, &stack.Slug, &stack.Name,
		&stack.ImageRepository, &stack.ImageDigest, &stack.Subscribes,
		&stack.Publishes, &stack.WantsGPU, &stack.CreatedAt, &stack.CreatedBy)
	return stack, err
}

// CreateStack registers autonomy.
func (s *Store) CreateStack(ctx context.Context, conn db.Conn, spec StackSpec) (AutonomyStack, error) {
	if err := spec.Validate(); err != nil {
		return AutonomyStack{}, err
	}
	subscribes, publishes := spec.Subscribes, spec.Publishes
	if len(subscribes) == 0 {
		subscribes = json.RawMessage(`[]`)
	}
	if len(publishes) == 0 {
		publishes = json.RawMessage(`[]`)
	}

	id := ids.New(ids.KindStack)
	_, err := conn.Exec(ctx, `
		INSERT INTO dive.autonomy_stack
		    (id, org_id, slug, name, image_repository, image_digest,
		     subscribes, publishes, wants_gpu, created_by)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)`,
		id, spec.OrgID, spec.Slug, spec.Name, spec.ImageRepository,
		spec.ImageDigest, subscribes, publishes, spec.WantsGPU, spec.CreatedBy)
	if err != nil {
		if db.IsUniqueViolation(err) {
			return AutonomyStack{}, fmt.Errorf("%w: this organisation already has a stack named %q",
				domain.ErrInvalid, spec.Slug)
		}
		if message, ok := db.RaisedMessage(err); ok {
			return AutonomyStack{}, fmt.Errorf("%w: %s", domain.ErrInvalid, message)
		}
		return AutonomyStack{}, fmt.Errorf("registering an autonomy stack: %w", err)
	}
	return scanStack(conn.QueryRow(ctx, selectStack+` WHERE id = $1`, id))
}

// Stack reads one autonomy stack.
func (s *Store) Stack(ctx context.Context, id string) (AutonomyStack, error) {
	stack, err := scanStack(s.pool.QueryRow(ctx, selectStack+` WHERE id = $1`, id))
	return stack, db.Translate(err)
}

// Stacks lists an organisation's autonomy.
func (s *Store) Stacks(ctx context.Context, orgID string) ([]AutonomyStack, error) {
	rows, err := s.pool.Query(ctx, selectStack+
		` WHERE org_id = $1 AND retired_at IS NULL ORDER BY name`, orgID)
	if err != nil {
		return nil, fmt.Errorf("listing autonomy stacks: %w", err)
	}
	defer rows.Close()

	stacks := []AutonomyStack{}
	for rows.Next() {
		stack, err := scanStack(rows)
		if err != nil {
			return nil, err
		}
		stacks = append(stacks, stack)
	}
	return stacks, rows.Err()
}

// ── Conditions ───────────────────────────────────────────────────────────────

const selectConditions = `
	SELECT id, kind, name, observed_at, sources, parameters, org_id, created_at, created_by
	FROM dive.conditions`

func scanConditions(row interface{ Scan(...any) error }) (Conditions, error) {
	var conditions Conditions
	err := row.Scan(&conditions.ID, &conditions.Kind, &conditions.Name,
		&conditions.ObservedAt, &conditions.Sources, &conditions.Parameters,
		&conditions.OrgID, &conditions.CreatedAt, &conditions.CreatedBy)
	return conditions, err
}

// CreateConditions records water to dive in.
func (s *Store) CreateConditions(ctx context.Context, conn db.Conn, spec ConditionsSpec) (Conditions, error) {
	if err := spec.Validate(); err != nil {
		return Conditions{}, err
	}
	sources, parameters := spec.Sources, spec.Parameters
	if len(sources) == 0 {
		sources = json.RawMessage(`[]`)
	}
	if len(parameters) == 0 {
		parameters = json.RawMessage(`{}`)
	}

	id := ids.New(ids.KindConditions)
	_, err := conn.Exec(ctx, `
		INSERT INTO dive.conditions
		    (id, kind, name, observed_at, sources, parameters, org_id, created_by)
		VALUES ($1, $2::dive.conditions_kind, $3, $4, $5, $6, $7, $8)`,
		id, string(spec.Kind), spec.Name, spec.ObservedAt, sources, parameters,
		spec.OrgID, spec.CreatedBy)
	if err != nil {
		return Conditions{}, fmt.Errorf("recording conditions: %w", err)
	}
	return scanConditions(conn.QueryRow(ctx, selectConditions+` WHERE id = $1`, id))
}

// Conditions reads one set of conditions.
func (s *Store) Conditions(ctx context.Context, id string) (Conditions, error) {
	conditions, err := scanConditions(s.pool.QueryRow(ctx, selectConditions+` WHERE id = $1`, id))
	return conditions, db.Translate(err)
}

// Digest identifies conditions by their content, so a run can pin them the way
// it pins a city. Two sets of conditions that would produce the same water have
// the same digest, whoever recorded them.
func (c Conditions) Digest() (domain.Digest, error) {
	instant := ""
	if c.ObservedAt != nil {
		instant = c.ObservedAt.UTC().Format(time.RFC3339Nano)
	}
	canonical := struct {
		Kind       ConditionsKind  `json:"kind"`
		ObservedAt string          `json:"observedAt"`
		Sources    json.RawMessage `json:"sources"`
		Parameters json.RawMessage `json:"parameters"`
	}{c.Kind, instant, c.Sources, c.Parameters}

	encoded, err := json.Marshal(canonical)
	if err != nil {
		return domain.Digest{}, fmt.Errorf("identifying conditions: %w", err)
	}
	return domain.DigestOf(encoded), nil
}

// ── Dives ────────────────────────────────────────────────────────────────────

const selectDive = `
	SELECT id, org_id, name, summary, city_version_id, vehicle_version_id,
	       conditions_id, autonomy_stack_id, initial_state, objective,
	       created_at, created_by
	FROM dive.dive`

func scanDive(row interface{ Scan(...any) error }) (Dive, error) {
	var plan Dive
	err := row.Scan(&plan.ID, &plan.OrgID, &plan.Name, &plan.Summary,
		&plan.CityVersionID, &plan.VehicleVersionID, &plan.ConditionsID,
		&plan.AutonomyStackID, &plan.InitialState, &plan.Objective,
		&plan.CreatedAt, &plan.CreatedBy)
	return plan, err
}

// CreateDive defines a dive.
func (s *Store) CreateDive(ctx context.Context, conn db.Conn, spec DiveSpec) (Dive, error) {
	if err := spec.Validate(); err != nil {
		return Dive{}, err
	}
	initial, objective := spec.InitialState, spec.Objective
	if len(initial) == 0 {
		initial = json.RawMessage(`{}`)
	}
	if len(objective) == 0 {
		objective = json.RawMessage(`{}`)
	}

	id := ids.New(ids.KindDive)
	_, err := conn.Exec(ctx, `
		INSERT INTO dive.dive
		    (id, org_id, name, summary, city_version_id, vehicle_version_id,
		     conditions_id, autonomy_stack_id, initial_state, objective, created_by)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)`,
		id, spec.OrgID, spec.Name, spec.Summary, spec.CityVersionID,
		spec.VehicleVersionID, spec.ConditionsID, spec.AutonomyStackID,
		initial, objective, spec.CreatedBy)
	if err != nil {
		return Dive{}, fmt.Errorf("defining a dive: %w", err)
	}
	return scanDive(conn.QueryRow(ctx, selectDive+` WHERE id = $1`, id))
}

// Dive reads one dive.
func (s *Store) Dive(ctx context.Context, id string) (Dive, error) {
	plan, err := scanDive(s.pool.QueryRow(ctx, selectDive+` WHERE id = $1`, id))
	return plan, db.Translate(err)
}

// Dives lists an organisation's dives.
func (s *Store) Dives(ctx context.Context, orgID string) ([]Dive, error) {
	rows, err := s.pool.Query(ctx, selectDive+
		` WHERE org_id = $1 AND archived_at IS NULL ORDER BY created_at DESC`, orgID)
	if err != nil {
		return nil, fmt.Errorf("listing dives: %w", err)
	}
	defer rows.Close()

	dives := []Dive{}
	for rows.Next() {
		plan, err := scanDive(rows)
		if err != nil {
			return nil, err
		}
		dives = append(dives, plan)
	}
	return dives, rows.Err()
}

// ── Runs ─────────────────────────────────────────────────────────────────────

// RunSpec describes an execution to request.
//
// The digests are not here: they are read from the dive at admission, because a
// caller that could choose them could claim a result came from a city it did
// not run in.
type RunSpec struct {
	DiveID  string
	QueueID string
	Mode    Mode

	// Supplying a seed re-runs an earlier run exactly; leaving it unset draws
	// one. Being able to say "the same again" is what makes a failure
	// something to investigate rather than something to remember.
	Seed *int64

	RuntimeVersion string
	GPUShare       float64
	RequestedBy    string
}

const selectRun = `
	SELECT id, dive_id, queue_id, mode, state, city_digest, vehicle_digest,
	       conditions_digest, autonomy_digest, seed, runtime_version, device_id,
	       gpu_share, requested_at, requested_by, started_at, ended_at,
	       lease_expires_at, outcome, failure_reason
	FROM dive.run`

func scanRun(row interface{ Scan(...any) error }) (Run, error) {
	var run Run
	var city, vehicle, conditions []byte
	err := row.Scan(&run.ID, &run.DiveID, &run.QueueID, &run.Mode, &run.State,
		&city, &vehicle, &conditions, &run.AutonomyDigest, &run.Seed,
		&run.RuntimeVersion, &run.DeviceID, &run.GPUShare, &run.RequestedAt,
		&run.RequestedBy, &run.StartedAt, &run.EndedAt, &run.LeaseExpiresAt,
		&run.Outcome, &run.FailureReason)
	if err != nil {
		return Run{}, err
	}
	if run.CityDigest, err = domain.DigestFromBytes(city); err != nil {
		return Run{}, err
	}
	if run.VehicleDigest, err = domain.DigestFromBytes(vehicle); err != nil {
		return Run{}, err
	}
	if run.ConditionsDigest, err = domain.DigestFromBytes(conditions); err != nil {
		return Run{}, err
	}
	return run, nil
}

// RequestRun admits an execution of a dive.
//
// Every determinant is copied here rather than referenced, so that editing the
// dive afterwards cannot change what this result means. A run whose city or
// vehicle version is unpublished is refused: a draft can still be rewritten,
// and a result pinned to something rewritable is not a result.
func (s *Store) RequestRun(ctx context.Context, conn db.Conn, spec RunSpec) (Run, error) {
	if _, err := ParseMode(string(spec.Mode)); err != nil {
		return Run{}, err
	}
	if strings.TrimSpace(spec.RuntimeVersion) == "" {
		return Run{}, fmt.Errorf(
			"%w: a run records the runtime that produced it, or results cannot be compared across a physics change",
			domain.ErrInvalid)
	}
	share := spec.GPUShare
	if share == 0 {
		share = 1
	}
	if share <= 0 || share > 1 {
		return Run{}, fmt.Errorf("%w: a share is a fraction of one device, got %v",
			domain.ErrInvalid, share)
	}

	seed := int64(0)
	if spec.Seed != nil {
		seed = *spec.Seed
	} else {
		var raw [8]byte
		if _, err := rand.Read(raw[:]); err != nil {
			return Run{}, fmt.Errorf("drawing a seed: %w", err)
		}
		// Kept non-negative so a seed reads the same in every language a
		// runtime might be written in.
		seed = int64(binary.BigEndian.Uint64(raw[:]) >> 1)
	}

	id := ids.New(ids.KindRun)
	_, err := conn.Exec(ctx, `
		INSERT INTO dive.run
		    (id, dive_id, queue_id, mode, city_digest, vehicle_digest,
		     conditions_digest, autonomy_digest, seed, runtime_version,
		     gpu_share, requested_by)
		SELECT $1, d.id, $2, $3::dive.run_mode,
		       city.digest, vehicle.digest, $4, stack.image_digest,
		       $5, $6, $7, $8
		  FROM dive.dive d
		  JOIN catalog.version city ON city.id = d.city_version_id
		  JOIN catalog.version vehicle ON vehicle.id = d.vehicle_version_id
		  LEFT JOIN dive.autonomy_stack stack ON stack.id = d.autonomy_stack_id
		 WHERE d.id = $9
		   AND city.published_at IS NOT NULL
		   AND vehicle.published_at IS NOT NULL`,
		id, spec.QueueID, string(spec.Mode), nil, seed, spec.RuntimeVersion,
		share, spec.RequestedBy, spec.DiveID)
	if err != nil {
		return Run{}, fmt.Errorf("requesting a run: %w", err)
	}

	run, err := scanRun(conn.QueryRow(ctx, selectRun+` WHERE id = $1`, id))
	if err != nil {
		return Run{}, fmt.Errorf(
			"%w: the dive does not exist, or its city or vehicle version is not published",
			domain.ErrInvalid)
	}
	return run, nil
}

// Run reads one run.
func (s *Store) Run(ctx context.Context, id string) (Run, error) {
	run, err := scanRun(s.pool.QueryRow(ctx, selectRun+` WHERE id = $1`, id))
	return run, db.Translate(err)
}

// Runs lists a dive's executions, newest first.
func (s *Store) Runs(ctx context.Context, diveID string) ([]Run, error) {
	rows, err := s.pool.Query(ctx, selectRun+` WHERE dive_id = $1 ORDER BY requested_at DESC`, diveID)
	if err != nil {
		return nil, fmt.Errorf("listing runs: %w", err)
	}
	defer rows.Close()

	runs := []Run{}
	for rows.Next() {
		run, err := scanRun(rows)
		if err != nil {
			return nil, err
		}
		runs = append(runs, run)
	}
	return runs, rows.Err()
}
