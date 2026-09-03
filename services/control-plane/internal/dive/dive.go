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
	"slices"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/exec"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
	"github.com/jalalirs/auv/services/control-plane/internal/reqctx"
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
	// What it needs beside the simulator — gpu, gpuMemoryBytes, cpu,
	// memoryBytes — written by whoever deployed it. What the scheduler places.
	Needs     json.RawMessage `json:"needs"`
	CreatedAt time.Time       `json:"createdAt"`
	CreatedBy string          `json:"createdBy"`
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
	Needs           json.RawMessage
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

	// What it was admitted needing, and where the scheduler put it — or where
	// it stands in line. Filled by the store on every read, because "where is
	// my dive" is the question a person asks while they wait.
	Needs     Needs      `json:"needs"`
	Placement *Placement `json:"placement,omitempty"`
	// How many files the run left behind, so a listing can offer to play it
	// back without asking about each run.
	Artefacts int `json:"artefacts"`

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
	       subscribes, publishes, wants_gpu, needs, created_at, created_by
	FROM dive.autonomy_stack`

func scanStack(row interface{ Scan(...any) error }) (AutonomyStack, error) {
	var stack AutonomyStack
	err := row.Scan(&stack.ID, &stack.OrgID, &stack.Slug, &stack.Name,
		&stack.ImageRepository, &stack.ImageDigest, &stack.Subscribes,
		&stack.Publishes, &stack.WantsGPU, &stack.Needs, &stack.CreatedAt, &stack.CreatedBy)
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
	needs := spec.Needs
	if len(needs) == 0 || string(needs) == "null" {
		needs = json.RawMessage(`{}`)
	} else {
		var part Part
		if err := json.Unmarshal(needs, &part); err != nil {
			return AutonomyStack{}, fmt.Errorf("%w: the stack's needs could not be read: %v", domain.ErrInvalid, err)
		}
		if part.GPUMemoryBytes < 0 || part.CPU < 0 || part.MemoryBytes < 0 {
			return AutonomyStack{}, fmt.Errorf("%w: a need is not negative", domain.ErrInvalid)
		}
	}

	id := ids.New(ids.KindStack)
	_, err := conn.Exec(ctx, `
		INSERT INTO dive.autonomy_stack
		    (id, org_id, slug, name, image_repository, image_digest,
		     subscribes, publishes, wants_gpu, needs, created_by)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)`,
		id, spec.OrgID, spec.Slug, spec.Name, spec.ImageRepository,
		spec.ImageDigest, subscribes, publishes, spec.WantsGPU, needs, spec.CreatedBy)
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

	// A stack and a vehicle that cannot talk to each other are found out here
	// rather than by a dive that claims a GPU, waits, and produces a result
	// that looks like a controller flying badly.
	if spec.AutonomyStackID != nil {
		var contract, subscribes, publishes json.RawMessage
		err := conn.QueryRow(ctx, `
			SELECT coalesce(d.topic_contract, '{}'::jsonb), s.subscribes, s.publishes
			  FROM dive.autonomy_stack s
			  LEFT JOIN catalog.vehicle_dynamics d ON d.version_id = $2
			 WHERE s.id = $1`, *spec.AutonomyStackID, spec.VehicleVersionID).
			Scan(&contract, &subscribes, &publishes)
		if err != nil {
			return Dive{}, fmt.Errorf("%w: no such autonomy, or no such vehicle version",
				domain.ErrInvalid)
		}
		if err := CheckContract(contract, subscribes, publishes); err != nil {
			return Dive{}, err
		}
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
	// What the request says the dive needs, over what the platform would
	// assemble from its parts. Optional.
	Needs json.RawMessage
}

const selectRun = `
	SELECT id, dive_id, queue_id, mode, state, city_digest, vehicle_digest,
	       conditions_digest, autonomy_digest, seed, runtime_version, device_id,
	       gpu_share, requested_at, requested_by, started_at, ended_at,
	       lease_expires_at, outcome, failure_reason, needs
	FROM dive.run`

func scanRun(row interface{ Scan(...any) error }) (Run, error) {
	var run Run
	var city, vehicle, conditions, needs []byte
	err := row.Scan(&run.ID, &run.DiveID, &run.QueueID, &run.Mode, &run.State,
		&city, &vehicle, &conditions, &run.AutonomyDigest, &run.Seed,
		&run.RuntimeVersion, &run.DeviceID, &run.GPUShare, &run.RequestedAt,
		&run.RequestedBy, &run.StartedAt, &run.EndedAt, &run.LeaseExpiresAt,
		&run.Outcome, &run.FailureReason, &needs)
	if err != nil {
		return Run{}, err
	}
	if len(needs) > 0 {
		_ = json.Unmarshal(needs, &run.Needs)
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

// RequestRun admits an execution of a dive, or refuses it with the reason.
//
// Every determinant is copied here rather than referenced, so that editing the
// dive afterwards cannot change what this result means. A run whose city or
// vehicle version is unpublished is refused: a draft can still be rewritten,
// and a result pinned to something rewritable is not a result.
//
// Then the scheduler's part. The dive's needs are assembled from its parts and
// held against the queue: a queue that is draining, hosts that do not offer
// the runtime, an institution at its quota, or cards that could never take the
// dive are refusals, written down with the reason. A dive that could fit but
// not now is admitted and queued, and told its place in line.
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

	// The conditions are identified by their content, the way a city is, so
	// that two runs in the same water are recognisably the same experiment.
	// Read here rather than taken from the caller: a caller who could choose it
	// could claim a result came from water it did not run in.
	conditions, err := scanConditions(conn.QueryRow(ctx, selectConditions+`
		WHERE id = (SELECT conditions_id FROM dive.dive WHERE id = $1)`, spec.DiveID))
	if err != nil {
		return Run{}, fmt.Errorf("%w: the dive does not exist, or names no conditions",
			domain.ErrInvalid)
	}
	conditionsDigest, err := conditions.Digest()
	if err != nil {
		return Run{}, err
	}

	// What the dive needs, from what it is made of.
	var orgID string
	var stackNeeds []byte
	var wantsGPU *bool
	var stackID *string
	err = conn.QueryRow(ctx, `
		SELECT d.org_id, d.autonomy_stack_id, s.needs, s.wants_gpu
		  FROM dive.dive d
		  LEFT JOIN dive.autonomy_stack s ON s.id = d.autonomy_stack_id
		 WHERE d.id = $1`, spec.DiveID).Scan(&orgID, &stackID, &stackNeeds, &wantsGPU)
	if err != nil {
		return Run{}, fmt.Errorf("%w: the dive does not exist", domain.ErrInvalid)
	}
	needs, err := NeedsFor(spec.Mode, stackNeeds, wantsGPU != nil && *wantsGPU, spec.Needs, stackID != nil)
	if err != nil {
		return Run{}, err
	}
	encodedNeeds, err := json.Marshal(needs)
	if err != nil {
		return Run{}, fmt.Errorf("encoding what the dive needs: %w", err)
	}

	if refusal, err := s.consider(ctx, conn, spec, orgID, needs); err != nil {
		return Run{}, err
	} else if refusal != nil {
		return Run{}, &Refused{Refusal: refusal, OrgID: orgID, PrincipalID: spec.RequestedBy}
	}

	id := ids.New(ids.KindRun)
	_, err = conn.Exec(ctx, `
		INSERT INTO dive.run
		    (id, dive_id, queue_id, mode, city_digest, vehicle_digest,
		     conditions_digest, autonomy_digest, seed, runtime_version,
		     gpu_share, requested_by, needs)
		SELECT $1, d.id, $2, $3::dive.run_mode,
		       city.digest, vehicle.digest, $4, stack.image_digest,
		       $5, $6, $7, $8, $10
		  FROM dive.dive d
		  JOIN catalog.version city ON city.id = d.city_version_id
		  JOIN catalog.version vehicle ON vehicle.id = d.vehicle_version_id
		  LEFT JOIN dive.autonomy_stack stack ON stack.id = d.autonomy_stack_id
		 WHERE d.id = $9
		   AND city.published_at IS NOT NULL
		   AND vehicle.published_at IS NOT NULL`,
		id, spec.QueueID, string(spec.Mode), conditionsDigest[:], seed, spec.RuntimeVersion,
		share, spec.RequestedBy, spec.DiveID, encodedNeeds)
	if err != nil {
		return Run{}, fmt.Errorf("requesting a run: %w", err)
	}

	run, err := scanRun(conn.QueryRow(ctx, selectRun+` WHERE id = $1`, id))
	if err != nil {
		return Run{}, fmt.Errorf(
			"%w: the dive does not exist, or its city or vehicle version is not published",
			domain.ErrInvalid)
	}
	run.Placement, err = s.placementOn(ctx, conn, run)
	if err != nil {
		return Run{}, err
	}
	return run, nil
}

// consider is the scheduler's part of admission: whether this dive could be
// placed on this queue at all, and whether its institution may have it.
func (s *Store) consider(ctx context.Context, conn db.Conn, spec RunSpec, orgID string,
	needs Needs) (*exec.Refusal, error) {
	var draining bool
	var runtimes []string
	err := conn.QueryRow(ctx, `
		SELECT q.draining,
		       coalesce((SELECT array_agg(DISTINCT runtime)
		                   FROM compute.device d
		                   JOIN exec.target t ON t.id = d.target_id
		                   CROSS JOIN LATERAL unnest(t.runtimes) AS runtime
		                  WHERE d.queue_id = q.id AND d.enabled), '{}')
		  FROM compute.queue q WHERE q.id = $1`, spec.QueueID).Scan(&draining, &runtimes)
	if err != nil {
		return nil, fmt.Errorf("%w: that queue does not exist", domain.ErrInvalid)
	}
	if draining {
		return &exec.Refusal{Reason: exec.QueueDraining}, nil
	}
	if !slices.Contains(runtimes, spec.RuntimeVersion) {
		return &exec.Refusal{Reason: exec.RuntimeUnavailable, Detail: map[string]any{
			"runtime": spec.RuntimeVersion, "offered": runtimes}}, nil
	}

	// The institution's quota, locked so two requests at once cannot both be
	// the last one allowed.
	var maxDives int
	var maxHours float64
	err = conn.QueryRow(ctx, `
		SELECT max_concurrent_dives, max_gpu_hours_daily
		  FROM exec.quota WHERE org_id = $1 FOR UPDATE`, orgID).Scan(&maxDives, &maxHours)
	if err != nil {
		if db.Translate(err) == db.ErrNotFound {
			return &exec.Refusal{Reason: exec.OrganisationHasNoQuota}, nil
		}
		return nil, fmt.Errorf("reading the quota: %w", err)
	}
	var inFlight int
	var hoursToday float64
	err = conn.QueryRow(ctx, `
		SELECT count(*) FILTER (WHERE r.state IN ('queued', 'preparing', 'running')),
		       coalesce(sum(
		           greatest(1, (SELECT count(DISTINCT device_id) FROM dive.hold h WHERE h.run_id = r.id))
		           * extract(epoch FROM (coalesce(r.ended_at, now()) - coalesce(r.started_at, r.requested_at))) / 3600.0
		       ) FILTER (WHERE r.started_at IS NOT NULL
		                   AND coalesce(r.ended_at, now()) > now() - interval '24 hours'), 0)
		  FROM dive.run r JOIN dive.dive d ON d.id = r.dive_id
		 WHERE d.org_id = $1`, orgID).Scan(&inFlight, &hoursToday)
	if err != nil {
		return nil, fmt.Errorf("reading what the institution has in flight: %w", err)
	}
	if inFlight+1 > maxDives {
		return &exec.Refusal{Reason: exec.QuotaDivesExhausted, Detail: map[string]any{
			"inFlight": inFlight, "limit": maxDives}}, nil
	}
	if hoursToday >= maxHours {
		return &exec.Refusal{Reason: exec.QuotaGPUHoursExhausted, Detail: map[string]any{
			"usedHours": fmt.Sprintf("%.1f", hoursToday), "limit": maxHours}}, nil
	}

	// Whether any host on this queue could ever take it.
	cards, hosts, err := cardsOnQueue(ctx, conn, spec.QueueID)
	if err != nil {
		return nil, err
	}
	if len(cards) == 0 {
		return &exec.Refusal{Reason: exec.NoDeviceFits, Detail: map[string]any{
			"why": "the queue has no devices"}}, nil
	}
	var why string
	for target, host := range hosts {
		var mine []Card
		for _, card := range cards {
			if card.TargetID == target {
				mine = append(mine, card)
			}
		}
		fits, reason := CouldEverFit(needs, mine, host)
		if fits {
			return nil, nil
		}
		why = reason
	}
	return &exec.Refusal{Reason: exec.NoDeviceFits, Detail: map[string]any{
		"why": why, "needs": needs}}, nil
}

// cardsOnQueue is every device on a queue and the host each sits on, with
// what is held on them now.
func cardsOnQueue(ctx context.Context, conn db.Conn, queueID string) ([]Card, map[string]Host, error) {
	rows, err := conn.Query(ctx, `
		SELECT d.id, d.target_id, d.device_index, d.uuid, d.model, d.memory_bytes, d.enabled,
		       coalesce((SELECT sum(h.gpu_memory_bytes) FROM dive.hold h
		                   JOIN dive.run r ON r.id = h.run_id
		                  WHERE h.device_id = d.id AND r.state IN ('preparing', 'running')), 0),
		       t.capacity_cpu, t.capacity_memory_bytes, t.enabled
		  FROM compute.device d
		  JOIN exec.target t ON t.id = d.target_id
		 WHERE d.queue_id = $1
		 ORDER BY d.target_id, d.device_index`, queueID)
	if err != nil {
		return nil, nil, fmt.Errorf("reading the queue's devices: %w", err)
	}
	defer rows.Close()
	cards := []Card{}
	hosts := map[string]Host{}
	for rows.Next() {
		var card Card
		var cpu float64
		var memory int64
		var targetEnabled bool
		if err := rows.Scan(&card.ID, &card.TargetID, &card.Index, &card.UUID, &card.Model,
			&card.MemoryBytes, &card.Enabled, &card.HeldBytes, &cpu, &memory, &targetEnabled); err != nil {
			return nil, nil, err
		}
		card.Enabled = card.Enabled && targetEnabled
		cards = append(cards, card)
		if _, seen := hosts[card.TargetID]; !seen {
			hosts[card.TargetID] = Host{CPU: cpu, MemoryBytes: memory}
		}
	}
	if err := rows.Err(); err != nil {
		return nil, nil, err
	}
	// What each host already carries, from the needs of the runs on it.
	for target := range hosts {
		held, err := conn.Query(ctx, `
			SELECT DISTINCT r.id, r.needs FROM dive.run r
			  JOIN dive.hold h ON h.run_id = r.id
			  JOIN compute.device d ON d.id = h.device_id
			 WHERE d.target_id = $1 AND r.state IN ('preparing', 'running')`, target)
		if err != nil {
			return nil, nil, fmt.Errorf("reading what a host carries: %w", err)
		}
		host := hosts[target]
		for held.Next() {
			var id string
			var raw []byte
			if err := held.Scan(&id, &raw); err != nil {
				held.Close()
				return nil, nil, err
			}
			var needs Needs
			_ = json.Unmarshal(raw, &needs)
			host.HeldCPU += needs.CPU()
			host.HeldMemoryBytes += needs.MemoryBytes()
		}
		held.Close()
		hosts[target] = host
	}
	return cards, hosts, nil
}

// Refused is a dive the scheduler declined, with who asked and for whom, so
// that it can be written down after the transaction that declined it has
// rolled back — a refusal recorded inside that transaction is a refusal
// recorded nowhere.
type Refused struct {
	Refusal     *exec.Refusal
	OrgID       string
	PrincipalID string
}

func (r *Refused) Error() string { return r.Refusal.Error() }
func (r *Refused) Unwrap() error { return r.Refusal }

// RecordRefusal writes a refusal where refused jobs are written.
func (s *Store) RecordRefusal(ctx context.Context, conn db.Conn, refused *Refused) error {
	refusal := refused.Refusal
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
		ids.New(ids.KindRefusal), refused.OrgID, refused.PrincipalID,
		string(refusal.Reason), encoded, reqctx.RequestID(ctx)); err != nil {
		return fmt.Errorf("recording a refusal: %w", err)
	}
	return nil
}

// placementOn says where a run stands: held on which cards of which host, or
// where in line and waiting for what.
func (s *Store) placementOn(ctx context.Context, conn db.Conn, run Run) (*Placement, error) {
	placement := &Placement{Holds: []Hold{}}
	switch {
	case run.State == Queued:
		placement.State = "queued"
		var ahead int
		if err := conn.QueryRow(ctx, `
			SELECT count(*) FROM dive.run
			 WHERE queue_id = $1 AND state = 'queued' AND requested_at < $2`,
			run.QueueID, run.RequestedAt).Scan(&ahead); err != nil {
			return nil, fmt.Errorf("counting the line: %w", err)
		}
		placement.Ahead = ahead
		placement.Position = ahead + 1
		placement.WaitingFor = WaitingFor(run.Needs)
		return placement, nil
	case run.State.Finished():
		placement.State = "over"
	default:
		placement.State = "placed"
	}
	rows, err := conn.Query(ctx, `
		SELECT h.part, h.device_id, d.device_index, d.uuid, d.model, h.gpu_memory_bytes, t.name
		  FROM dive.hold h
		  JOIN compute.device d ON d.id = h.device_id
		  JOIN exec.target t ON t.id = d.target_id
		 WHERE h.run_id = $1
		 ORDER BY h.part DESC`, run.ID)
	if err != nil {
		return nil, fmt.Errorf("reading what a run holds: %w", err)
	}
	defer rows.Close()
	for rows.Next() {
		var hold Hold
		if err := rows.Scan(&hold.Part, &hold.DeviceID, &hold.DeviceIndex, &hold.DeviceUUID,
			&hold.Model, &hold.GPUMemoryBytes, &placement.Target); err != nil {
			return nil, err
		}
		placement.Holds = append(placement.Holds, hold)
	}
	return placement, rows.Err()
}

// Run reads one run.
func (s *Store) Run(ctx context.Context, id string) (Run, error) {
	run, err := scanRun(s.pool.QueryRow(ctx, selectRun+` WHERE id = $1`, id))
	if err != nil {
		return Run{}, db.Translate(err)
	}
	run.Placement, err = s.placementOn(ctx, s.pool, run)
	if err != nil {
		return Run{}, err
	}
	err = s.pool.QueryRow(ctx, `SELECT count(*) FROM dive.artefact WHERE run_id = $1`, id).Scan(&run.Artefacts)
	return run, err
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
	if err := rows.Err(); err != nil {
		return nil, err
	}
	rows.Close()
	for i := range runs {
		placement, err := s.placementOn(ctx, s.pool, runs[i])
		if err != nil {
			return nil, err
		}
		runs[i].Placement = placement
		if err := s.pool.QueryRow(ctx, `SELECT count(*) FROM dive.artefact WHERE run_id = $1`,
			runs[i].ID).Scan(&runs[i].Artefacts); err != nil {
			return nil, err
		}
	}
	return runs, nil
}

// ── Running one ──────────────────────────────────────────────────────────────

// Claimed is a run an agent has taken, with everything needed to compose it.
//
// The packages are named by version so the agent can ask for their files, and
// the digests are the ones the run pinned rather than whatever those versions
// hold now — a version cannot change once published, so the two agree, and
// carrying both means the agent can check rather than trust.
type Claimed struct {
	Run              Run             `json:"run"`
	CityVersionID    string          `json:"cityVersionId"`
	VehicleVersionID string          `json:"vehicleVersionId"`
	Conditions       Conditions      `json:"conditions"`
	InitialState     json.RawMessage `json:"initialState"`
	Objective        json.RawMessage `json:"objective"`

	AutonomyImage  string          `json:"autonomyImage,omitempty"`
	AutonomyDigest string          `json:"autonomyDigest,omitempty"`
	AutonomyGPU    bool            `json:"autonomyWantsGpu"`
	Subscribes     json.RawMessage `json:"autonomySubscribes,omitempty"`
	Publishes      json.RawMessage `json:"autonomyPublishes,omitempty"`

	// The simulator's card, as it always was, and everything the run holds:
	// the controller's card may be the same one or another.
	DeviceIndex int    `json:"deviceIndex"`
	DeviceUUID  string `json:"deviceUuid"`
	Holds       []Hold `json:"holds"`
	Needs       Needs  `json:"needs"`

	// The run's slot on its host: the lowest not held by another dive there.
	// The DDS domain and the stream port come from it, so two dives sharing
	// a card neither hear nor watch each other.
	Slot int `json:"slot"`

	// Two dives on one host must not hear each other over DDS, and a domain is
	// how that is arranged. Derived from the device rather than drawn, so a run
	// that is retried lands on the same domain as the device it holds.
	ROSDomainID int `json:"rosDomainId"`
}

// ClaimNext takes the oldest queued run this host can place now, and holds
// what it needs.
//
// The host's cards are locked first, so two agents on one host asking at the
// same moment cannot both be told yes; hosts do not share cards, so agents on
// different hosts do not wait on each other. Then the queued runs on this
// host's queues are tried oldest first, and the first that fits is placed: a
// hold per part, the simulator's card recorded on the run as it always was.
//
// Returns db.ErrNotFound when there is nothing to do, which is the ordinary
// case and not an error.
func (s *Store) ClaimNext(ctx context.Context, conn db.Conn, targetName string,
	lease time.Duration) (Claimed, error) {
	var claimed Claimed

	// The host's cards, locked, with what is held on them.
	rows, err := conn.Query(ctx, `
		SELECT d.id, d.queue_id, d.target_id, d.device_index, d.uuid, d.model, d.memory_bytes,
		       d.enabled AND t.enabled AND NOT q.draining,
		       t.capacity_cpu, t.capacity_memory_bytes
		  FROM compute.device d
		  JOIN exec.target t ON t.id = d.target_id
		  JOIN compute.queue q ON q.id = d.queue_id
		 WHERE t.name = $1
		 ORDER BY d.device_index
		 FOR UPDATE OF d`, targetName)
	if err != nil {
		return Claimed{}, fmt.Errorf("locking the host's cards: %w", err)
	}
	cards := []Card{}
	queues := map[string][]Card{}
	host := Host{}
	for rows.Next() {
		var card Card
		var queueID string
		if err := rows.Scan(&card.ID, &queueID, &card.TargetID, &card.Index, &card.UUID, &card.Model,
			&card.MemoryBytes, &card.Enabled, &host.CPU, &host.MemoryBytes); err != nil {
			rows.Close()
			return Claimed{}, err
		}
		cards = append(cards, card)
		queues[queueID] = append(queues[queueID], card)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return Claimed{}, err
	}
	if len(cards) == 0 {
		return Claimed{}, db.ErrNotFound
	}
	held, err := conn.Query(ctx, `
		SELECT h.device_id, h.gpu_memory_bytes, r.id, r.needs
		  FROM dive.hold h
		  JOIN dive.run r ON r.id = h.run_id
		  JOIN compute.device d ON d.id = h.device_id
		  JOIN exec.target t ON t.id = d.target_id
		 WHERE t.name = $1 AND r.state IN ('preparing', 'running')`, targetName)
	if err != nil {
		return Claimed{}, fmt.Errorf("reading what the host carries: %w", err)
	}
	counted := map[string]bool{}
	for held.Next() {
		var deviceID, runID string
		var bytes int64
		var raw []byte
		if err := held.Scan(&deviceID, &bytes, &runID, &raw); err != nil {
			held.Close()
			return Claimed{}, err
		}
		for i := range cards {
			if cards[i].ID == deviceID {
				cards[i].HeldBytes += bytes
			}
		}
		for queueID := range queues {
			for i := range queues[queueID] {
				if queues[queueID][i].ID == deviceID {
					queues[queueID][i].HeldBytes += bytes
				}
			}
		}
		if !counted[runID] {
			counted[runID] = true
			var needs Needs
			_ = json.Unmarshal(raw, &needs)
			host.HeldCPU += needs.CPU()
			host.HeldMemoryBytes += needs.MemoryBytes()
		}
	}
	held.Close()

	// The line, oldest first, on the queues this host serves.
	queueIDs := make([]string, 0, len(queues))
	for id := range queues {
		queueIDs = append(queueIDs, id)
	}
	waiting, err := conn.Query(ctx, `
		SELECT r.id, r.queue_id, r.needs
		  FROM dive.run r
		 WHERE r.state = 'queued' AND r.queue_id = ANY($1)
		 ORDER BY r.requested_at
		 FOR UPDATE OF r SKIP LOCKED`, queueIDs)
	if err != nil {
		return Claimed{}, fmt.Errorf("reading the line: %w", err)
	}
	var runID string
	var holds []Hold
	for waiting.Next() {
		var id, queueID string
		var raw []byte
		if err := waiting.Scan(&id, &queueID, &raw); err != nil {
			waiting.Close()
			return Claimed{}, err
		}
		var needs Needs
		_ = json.Unmarshal(raw, &needs)
		if placed, ok := Place(needs, queues[queueID], host); ok {
			runID, holds = id, placed
			break
		}
	}
	waiting.Close()
	if runID == "" {
		return Claimed{}, db.ErrNotFound
	}

	simulator := holds[0]
	for _, hold := range holds {
		if _, err := conn.Exec(ctx, `
			INSERT INTO dive.hold (run_id, device_id, part, gpu_memory_bytes)
			VALUES ($1, $2, $3, $4)`, runID, hold.DeviceID, hold.Part, hold.GPUMemoryBytes); err != nil {
			return Claimed{}, fmt.Errorf("holding a card: %w", err)
		}
	}
	// The lowest slot no other dive on this host holds.
	taken, err := conn.Query(ctx, `
		SELECT DISTINCT r.host_slot FROM dive.run r
		  JOIN compute.device d ON d.id = r.device_id
		  JOIN exec.target t ON t.id = d.target_id
		 WHERE t.name = $1 AND r.state IN ('preparing', 'running') AND r.host_slot IS NOT NULL`, targetName)
	if err != nil {
		return Claimed{}, fmt.Errorf("reading the host's slots: %w", err)
	}
	used := map[int]bool{}
	for taken.Next() {
		var slot int
		if err := taken.Scan(&slot); err != nil {
			taken.Close()
			return Claimed{}, err
		}
		used[slot] = true
	}
	taken.Close()
	slot := 0
	for used[slot] {
		slot++
	}
	if _, err := conn.Exec(ctx, `
		UPDATE dive.run
		   SET state = 'preparing', device_id = $2, host_slot = $4,
		       lease_expires_at = now() + $3::interval
		 WHERE id = $1`, runID, simulator.DeviceID, lease.String(), slot); err != nil {
		return Claimed{}, fmt.Errorf("admitting the run: %w", err)
	}
	claimed.Slot = slot

	if claimed.Run, err = scanRun(conn.QueryRow(ctx, selectRun+` WHERE id = $1`, runID)); err != nil {
		return Claimed{}, err
	}
	claimed.Holds = holds
	claimed.Needs = claimed.Run.Needs
	claimed.DeviceIndex = simulator.DeviceIndex
	claimed.DeviceUUID = simulator.DeviceUUID

	var stackImage, stackDigest *string
	var wantsGPU *bool
	var subscribes, publishes []byte
	err = conn.QueryRow(ctx, `
		SELECT d.city_version_id, d.vehicle_version_id, d.initial_state, d.objective,
		       s.image_repository, s.image_digest, s.wants_gpu, s.subscribes, s.publishes
		  FROM dive.dive d
		  JOIN dive.run r ON r.dive_id = d.id
		  LEFT JOIN dive.autonomy_stack s ON s.id = d.autonomy_stack_id
		 WHERE r.id = $1`, runID).
		Scan(&claimed.CityVersionID, &claimed.VehicleVersionID,
			&claimed.InitialState, &claimed.Objective,
			&stackImage, &stackDigest, &wantsGPU, &subscribes, &publishes)
	if err != nil {
		return Claimed{}, fmt.Errorf("reading what the run needs: %w", err)
	}
	if stackImage != nil {
		claimed.AutonomyImage = *stackImage
		claimed.AutonomyDigest = *stackDigest
		claimed.AutonomyGPU = claimed.Needs.Controller != nil && claimed.Needs.Controller.GPU
		claimed.Subscribes = subscribes
		claimed.Publishes = publishes
	}

	if claimed.Conditions, err = scanConditions(conn.QueryRow(ctx, selectConditions+`
		WHERE id = (SELECT conditions_id FROM dive.dive
		             WHERE id = (SELECT dive_id FROM dive.run WHERE id = $1))`,
		runID)); err != nil {
		return Claimed{}, fmt.Errorf("reading the conditions: %w", err)
	}

	// Domains are 0–101 in the default DDS configuration; the slot keeps two
	// dives on one host apart, and the offset leaves domain 0 for anything a
	// person is running by hand.
	claimed.ROSDomainID = 1 + (claimed.Slot % 100)
	return claimed, nil
}

// Started records that the simulator is up and the run is under way.
func (s *Store) Started(ctx context.Context, conn db.Conn, runID string) error {
	tag, err := conn.Exec(ctx, `
		UPDATE dive.run SET state = 'running', started_at = now()
		 WHERE id = $1 AND state = 'preparing'`, runID)
	if err != nil {
		return fmt.Errorf("recording that a run started: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return fmt.Errorf("%w: this run is not preparing, so it cannot start", domain.ErrInvalid)
	}
	return nil
}

// Renew extends the lease on a run an agent is still working on.
//
// A lease that is not renewed expires and the device is released, which is what
// makes an agent that dies stop holding hardware. Renewing a finished run is
// refused rather than ignored, because an agent renewing something that ended
// has lost track of what it is doing.
func (s *Store) Renew(ctx context.Context, conn db.Conn, runID string, lease time.Duration) error {
	tag, err := conn.Exec(ctx, `
		UPDATE dive.run SET lease_expires_at = now() + $2::interval
		 WHERE id = $1 AND state IN ('preparing', 'running')`, runID, lease.String())
	if err != nil {
		return fmt.Errorf("renewing a lease: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return fmt.Errorf("%w: this run is not in progress", domain.ErrInvalid)
	}
	return nil
}

// Record appends to what happened during a run.
func (s *Store) Record(ctx context.Context, conn db.Conn, runID string,
	kind string, simulatedSeconds *float64, detail json.RawMessage) error {
	if len(detail) == 0 {
		detail = json.RawMessage(`{}`)
	}
	_, err := conn.Exec(ctx, `
		INSERT INTO dive.run_event (run_id, simulated_seconds, kind, detail)
		VALUES ($1, $2, $3, $4)`, runID, simulatedSeconds, kind, detail)
	if err != nil {
		return fmt.Errorf("recording what happened: %w", err)
	}
	return nil
}

// Finish ends a run, for good.
//
// The record refuses to rewrite a finished run afterwards, so this is the last
// thing anything says about it.
func (s *Store) Finish(ctx context.Context, conn db.Conn, runID string,
	state State, outcome json.RawMessage, failure string) error {
	if !state.Finished() {
		return fmt.Errorf("%w: %q is not a state a run finishes in", domain.ErrInvalid, state)
	}
	if (state == Failed) != (failure != "") {
		return fmt.Errorf("%w: a failed run says why, and a run that says why has failed",
			domain.ErrInvalid)
	}
	if len(outcome) == 0 {
		outcome = json.RawMessage(`{}`)
	}

	var reason *string
	if failure != "" {
		reason = &failure
	}
	tag, err := conn.Exec(ctx, `
		UPDATE dive.run
		   SET state = $2::dive.run_state, ended_at = now(), outcome = $3,
		       failure_reason = $4, lease_expires_at = NULL
		 WHERE id = $1 AND state IN ('queued', 'preparing', 'running')`,
		runID, string(state), outcome, reason)
	if err != nil {
		return fmt.Errorf("finishing a run: %w", err)
	}
	if tag.RowsAffected() == 0 {
		// A dive the person surfaced from is already over by their hand; what
		// the agent then says about how it went — where the vehicle settled,
		// the task's result, the recording — is added to it rather than
		// refused. Anything else finished twice is a mistake.
		merged, err := conn.Exec(ctx, `
			UPDATE dive.run
			   SET outcome = outcome || $2
			 WHERE id = $1 AND state = 'succeeded' AND (outcome ->> 'surfaced') = 'true'`,
			runID, outcome)
		if err != nil {
			return fmt.Errorf("adding to a surfaced run: %w", err)
		}
		if merged.RowsAffected() == 0 {
			return fmt.Errorf("%w: this run has already finished", domain.ErrInvalid)
		}
	}
	return nil
}

// Expire releases devices held by runs whose lease has run out.
//
// An agent that dies holds a GPU until this notices. Nothing else releases it,
// because nothing else can tell the difference between an agent that is slow
// and one that is gone — a lease is precisely the statement "I will say
// something again by this time", and its absence is the only evidence there is.
func (s *Store) Expire(ctx context.Context, conn db.Conn) (int64, error) {
	tag, err := conn.Exec(ctx, `
		UPDATE dive.run
		   SET state = 'expired', ended_at = now(), lease_expires_at = NULL
		 WHERE state IN ('preparing', 'running')
		   AND lease_expires_at IS NOT NULL
		   AND lease_expires_at < now()`)
	if err != nil {
		return 0, fmt.Errorf("expiring leases: %w", err)
	}
	return tag.RowsAffected(), nil
}

// ── What a stack may expect of a vehicle ─────────────────────────────────────

// ContractMismatch says what a stack asked for that its vehicle does not offer.
type ContractMismatch struct {
	Missing []string
	Unheard []string
}

// Error describes the mismatch in the terms somebody can act on.
func (m ContractMismatch) Error() string {
	parts := []string{}
	if len(m.Missing) > 0 {
		parts = append(parts, fmt.Sprintf(
			"it subscribes to %s, which this vehicle does not publish",
			strings.Join(m.Missing, ", ")))
	}
	if len(m.Unheard) > 0 {
		parts = append(parts, fmt.Sprintf(
			"it publishes %s, which this vehicle does not act on",
			strings.Join(m.Unheard, ", ")))
	}
	return strings.Join(parts, "; ")
}

// CheckContract reports whether a stack and a vehicle can talk to each other.
//
// Checked when a dive is defined rather than when it runs. A stack that
// subscribes to a sonar on a vehicle that carries none will wait for a message
// that never arrives — it will not fail, it will simply fly badly, and the
// dive will produce a result that looks like a controller performing poorly
// rather than a controller that was never told anything. That is the most
// expensive kind of wrong answer this platform could give, and it costs a GPU
// and a wait to find out.
//
// A stack that publishes something the vehicle ignores is reported too. It is
// less serious — nothing is silently missing — but it means one of the two is
// not what its author thinks it is.
func CheckContract(vehicleContract, subscribes, publishes json.RawMessage) error {
	offered, accepted, err := readContract(vehicleContract)
	if err != nil {
		return err
	}
	// A vehicle that states no contract cannot be checked against, and
	// pretending otherwise would refuse every stack rather than none.
	if len(offered) == 0 && len(accepted) == 0 {
		return nil
	}

	wanted, err := readTopics(subscribes)
	if err != nil {
		return err
	}
	sends, err := readTopics(publishes)
	if err != nil {
		return err
	}

	var mismatch ContractMismatch
	for _, topic := range wanted {
		if !slices.Contains(offered, topic) {
			mismatch.Missing = append(mismatch.Missing, topic)
		}
	}
	for _, topic := range sends {
		if !slices.Contains(accepted, topic) {
			mismatch.Unheard = append(mismatch.Unheard, topic)
		}
	}
	if len(mismatch.Missing) > 0 || len(mismatch.Unheard) > 0 {
		return fmt.Errorf("%w: %s", domain.ErrInvalid, mismatch.Error())
	}
	return nil
}

// readContract reads what a vehicle publishes and what it acts on.
func readContract(raw json.RawMessage) (publishes, subscribes []string, err error) {
	if len(raw) == 0 {
		return nil, nil, nil
	}
	var contract struct {
		Publishes []struct {
			Topic string `json:"topic"`
		} `json:"publishes"`
		Subscribes []struct {
			Topic string `json:"topic"`
		} `json:"subscribes"`
	}
	if err := json.Unmarshal(raw, &contract); err != nil {
		return nil, nil, fmt.Errorf("%w: the vehicle's topic contract is not readable: %v",
			domain.ErrInvalid, err)
	}
	for _, entry := range contract.Publishes {
		publishes = append(publishes, entry.Topic)
	}
	for _, entry := range contract.Subscribes {
		subscribes = append(subscribes, entry.Topic)
	}
	return publishes, subscribes, nil
}

// readTopics accepts either a list of names or a list of objects naming one,
// because a stack's author should not have to guess which this platform wanted.
func readTopics(raw json.RawMessage) ([]string, error) {
	if len(raw) == 0 {
		return nil, nil
	}
	var names []string
	if err := json.Unmarshal(raw, &names); err == nil {
		return names, nil
	}

	// A fresh slice, because a failed unmarshal into a slice leaves what it
	// managed to decode behind: reading ["a", {"topic":"b"}] into []string
	// appends "a" and then fails, and reusing that slice would silently prepend
	// an empty topic to everything decoded the second way.
	var entries []struct {
		Topic string `json:"topic"`
	}
	if err := json.Unmarshal(raw, &entries); err != nil {
		return nil, fmt.Errorf("%w: a topic list is names or objects naming a topic",
			domain.ErrInvalid)
	}
	topics := make([]string, 0, len(entries))
	for _, entry := range entries {
		topics = append(topics, entry.Topic)
	}
	return topics, nil
}


// ── What a run left behind ───────────────────────────────────────────────────

// Artefact is one file of a run's recording: an object in storage, named by
// its path within the recording.
type Artefact struct {
	RunID      string    `json:"runId"`
	Path       string    `json:"path"`
	ObjectID   string    `json:"objectId"`
	SizeBytes  int64     `json:"sizeBytes"`
	MediaType  string    `json:"mediaType"`
	RecordedAt time.Time `json:"recordedAt"`
}

// RecordArtefact names one file a run left, once its bytes are in storage.
func (s *Store) RecordArtefact(ctx context.Context, conn db.Conn, runID, path, objectID string,
	sizeBytes int64, mediaType string) (Artefact, error) {
	path = strings.TrimSpace(path)
	if path == "" || strings.HasPrefix(path, "/") || strings.Contains(path, "..") {
		return Artefact{}, fmt.Errorf("%w: an artefact is named by a path inside the recording", domain.ErrInvalid)
	}
	var artefact Artefact
	err := conn.QueryRow(ctx, `
		INSERT INTO dive.artefact (run_id, path, object_id, size_bytes, media_type)
		VALUES ($1, $2, $3, $4, $5)
		ON CONFLICT (run_id, path) DO UPDATE SET
		    object_id = EXCLUDED.object_id, size_bytes = EXCLUDED.size_bytes,
		    media_type = EXCLUDED.media_type, recorded_at = now()
		RETURNING run_id, path, object_id, size_bytes, media_type, recorded_at`,
		runID, path, objectID, sizeBytes, mediaType).
		Scan(&artefact.RunID, &artefact.Path, &artefact.ObjectID, &artefact.SizeBytes,
			&artefact.MediaType, &artefact.RecordedAt)
	if err != nil {
		if message, ok := db.RaisedMessage(err); ok {
			return Artefact{}, fmt.Errorf("%w: %s", domain.ErrInvalid, message)
		}
		return Artefact{}, fmt.Errorf("recording an artefact: %w", err)
	}
	return artefact, nil
}

// Artefacts lists what a run left, in path order.
func (s *Store) Artefacts(ctx context.Context, runID string) ([]Artefact, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT run_id, path, object_id, size_bytes, media_type, recorded_at
		  FROM dive.artefact WHERE run_id = $1 ORDER BY path`, runID)
	if err != nil {
		return nil, fmt.Errorf("listing a run's artefacts: %w", err)
	}
	defer rows.Close()
	artefacts := []Artefact{}
	for rows.Next() {
		var artefact Artefact
		if err := rows.Scan(&artefact.RunID, &artefact.Path, &artefact.ObjectID, &artefact.SizeBytes,
			&artefact.MediaType, &artefact.RecordedAt); err != nil {
			return nil, err
		}
		artefacts = append(artefacts, artefact)
	}
	return artefacts, rows.Err()
}

// RunBelongsToDive says whether a run is one of this dive's, so a listing
// under a dive cannot reach another dive's recording.
func (s *Store) RunBelongsToDive(ctx context.Context, diveID, runID string) (bool, error) {
	var count int
	err := s.pool.QueryRow(ctx, `SELECT count(*) FROM dive.run WHERE id = $1 AND dive_id = $2`,
		runID, diveID).Scan(&count)
	return count > 0, err
}
