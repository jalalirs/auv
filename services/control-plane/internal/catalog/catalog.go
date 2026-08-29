// Package catalog owns what the platform publishes: the places a dive happens
// in, and the vehicles it is flown in.
//
// Both are packages rather than records. A city is terrain and scenes; a
// vehicle is geometry, mass properties, hydrodynamic coefficients, thrusters
// and a sensor suite. Both are large, both are versioned, and a dive pins the
// version it used by content digest — because a dive that cannot be reproduced
// is an anecdote, and reproducibility is the reason to own a simulator rather
// than borrow one.
//
// Neither belongs to an organisation. A city exists at the platform and
// outlives the institutions granted access to it; a vehicle is ours to publish
// and grant. What a person brings is autonomy, which lives elsewhere.
package catalog

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

// AssetKind distinguishes the two things the platform publishes. Versions are
// one table discriminated by kind rather than two kept in step by hand.
type AssetKind string

const (
	KindCity    AssetKind = "city"
	KindVehicle AssetKind = "vehicle"
)

// ParseAssetKind accepts the kinds the record accepts and refuses the rest.
func ParseAssetKind(value string) (AssetKind, error) {
	switch AssetKind(value) {
	case KindCity:
		return KindCity, nil
	case KindVehicle:
		return KindVehicle, nil
	default:
		return "", fmt.Errorf("%w: %q is not a city or a vehicle", domain.ErrInvalid, value)
	}
}

// City is a place a dive happens in: a reef, a wreck, a test tank, a harbour.
type City struct {
	ID            string        `json:"id"`
	Slug          string        `json:"slug"`
	Name          string        `json:"name"`
	Summary       string        `json:"summary"`
	Extent        domain.Extent `json:"extent"`
	HorizontalCRS string        `json:"horizontalCrs"`
	VerticalDatum string        `json:"verticalDatum"`
	Discoverable  bool          `json:"discoverable"`
	CreatedAt     time.Time     `json:"createdAt"`
	CreatedBy     string        `json:"createdBy"`
	RetiredAt     *time.Time    `json:"retiredAt,omitempty"`
}

// Vehicle is what a dive is flown in.
type Vehicle struct {
	ID           string     `json:"id"`
	Slug         string     `json:"slug"`
	Name         string     `json:"name"`
	Summary      string     `json:"summary"`
	Manufacturer string     `json:"manufacturer"`
	Discoverable bool       `json:"discoverable"`
	CreatedAt    time.Time  `json:"createdAt"`
	CreatedBy    string     `json:"createdBy"`
	RetiredAt    *time.Time `json:"retiredAt,omitempty"`
}

// Version is one publication of a city or a vehicle.
//
// The manifest lists the package's files and their digests; the version digest
// is over the manifest. Pinning one digest therefore pins every byte, which is
// what lets a node treat its cache as append-only: a digest never changes
// meaning, so nothing it holds is ever stale.
type Version struct {
	ID          string                 `json:"id"`
	AssetKind   AssetKind              `json:"assetKind"`
	AssetID     string                 `json:"assetId"`
	Ordinal     int                    `json:"ordinal"`
	Label       string                 `json:"label"`
	Notes       string                 `json:"notes"`
	Digest      domain.Digest          `json:"digest"`
	Manifest    []domain.ManifestEntry `json:"manifest"`
	TotalBytes  int64                  `json:"totalBytes"`
	RuntimeMin  string                 `json:"runtimeMin"`
	PublishedAt *time.Time             `json:"publishedAt,omitempty"`
	CreatedAt   time.Time              `json:"createdAt"`
	CreatedBy   string                 `json:"createdBy"`
}

// Published reports whether anything may pin this version. An unpublished
// version is a draft its author can still change.
func (v Version) Published() bool { return v.PublishedAt != nil }

// Dynamics is what a simulator integrates: the difference between a vehicle
// that behaves like a submarine and one that is a box with gravity disabled.
//
// The matrices are carried as JSON rather than as columns because their shape
// belongs to the runtime that reads them, and a schema that pinned it here
// would have to change every time the model gained a term.
type Dynamics struct {
	VersionID string `json:"versionId"`

	MassKg            float64 `json:"massKg"`
	DisplacedVolumeM3 float64 `json:"displacedVolumeM3"`

	// Distinct points, and the distance between them is what rights a vehicle
	// when it rolls. A model that lets them coincide has no restoring moment.
	CentreOfGravity  [3]float64 `json:"centreOfGravityM"`
	CentreOfBuoyancy [3]float64 `json:"centreOfBuoyancyM"`
	InertiaTensor    [9]float64 `json:"inertiaTensor"`

	AddedMass        json.RawMessage `json:"addedMass"`
	LinearDamping    json.RawMessage `json:"linearDamping"`
	QuadraticDamping json.RawMessage `json:"quadraticDamping"`
	Thrusters        json.RawMessage `json:"thrusters"`
	Sensors          json.RawMessage `json:"sensors"`

	// What this vehicle publishes and subscribes to, so a stack expecting a
	// sonar on a vehicle that carries none is refused at admission rather than
	// discovering it mid-dive.
	TopicContract json.RawMessage `json:"topicContract"`
}

// Validate reports whether the vehicle is described well enough to fly.
func (d Dynamics) Validate() error {
	if d.MassKg <= 0 {
		return fmt.Errorf("%w: a vehicle has mass", domain.ErrInvalid)
	}
	if d.DisplacedVolumeM3 <= 0 {
		return fmt.Errorf("%w: a vehicle displaces water, or it cannot float", domain.ErrInvalid)
	}
	if d.CentreOfGravity == d.CentreOfBuoyancy {
		return fmt.Errorf(
			"%w: the centres of gravity and buoyancy coincide, which leaves the vehicle no restoring moment",
			domain.ErrInvalid)
	}
	for name, raw := range map[string]json.RawMessage{
		"addedMass":        d.AddedMass,
		"linearDamping":    d.LinearDamping,
		"quadraticDamping": d.QuadraticDamping,
		"thrusters":        d.Thrusters,
		"sensors":          d.Sensors,
		"topicContract":    d.TopicContract,
	} {
		if len(raw) == 0 || !json.Valid(raw) {
			return fmt.Errorf("%w: %s is missing or is not valid JSON", domain.ErrInvalid, name)
		}
	}
	return nil
}

// Scope describes which assets of one kind a subject may learn of.
//
// The decision point produces it and this package applies it unchanged, so
// that a listing and a read agree about what exists without either deciding
// for itself.
type Scope struct {
	// All admits every asset, which platform authority carries.
	All bool
	// BoundIDs admits assets the subject holds a binding on, whatever their
	// discoverability.
	BoundIDs []string
	// IncludeDiscoverable admits assets listed to anyone signed in. An
	// undiscoverable asset is never admitted by this, and is therefore
	// indistinguishable from one that does not exist.
	IncludeDiscoverable bool
}

// Store reads and writes the catalogue.
type Store struct{ pool *db.Pool }

// NewStore builds the catalogue store.
func NewStore(pool *db.Pool) *Store { return &Store{pool: pool} }

// ── Cities ───────────────────────────────────────────────────────────────────

// CitySpec describes a place to found.
type CitySpec struct {
	Slug          string
	Name          string
	Summary       string
	Extent        *domain.Extent
	HorizontalCRS string
	VerticalDatum string
	Discoverable  bool
	CreatedBy     string
}

// Validate reports whether the place is described well enough to found.
func (c CitySpec) Validate() error {
	if err := domain.ValidateSlug(c.Slug); err != nil {
		return err
	}
	if strings.TrimSpace(c.Name) == "" {
		return fmt.Errorf("%w: a city has a name", domain.ErrInvalid)
	}
	if c.Extent != nil {
		if err := c.Extent.Validate(); err != nil {
			return err
		}
	}
	if strings.TrimSpace(c.VerticalDatum) == "" {
		return fmt.Errorf("%w: a city states what its depths are measured against",
			domain.ErrInvalid)
	}
	return nil
}

const selectCity = `
	SELECT id, slug, name, summary,
	       coalesce(ST_XMin(extent), 0), coalesce(ST_YMin(extent), 0),
	       coalesce(ST_XMax(extent), 0), coalesce(ST_YMax(extent), 0),
	       horizontal_crs, vertical_datum, discoverable, created_at, created_by, retired_at
	FROM catalog.city`

func scanCity(row interface{ Scan(...any) error }) (City, error) {
	var place City
	err := row.Scan(&place.ID, &place.Slug, &place.Name, &place.Summary,
		&place.Extent.West, &place.Extent.South, &place.Extent.East, &place.Extent.North,
		&place.HorizontalCRS, &place.VerticalDatum, &place.Discoverable,
		&place.CreatedAt, &place.CreatedBy, &place.RetiredAt)
	return place, err
}

// CreateCity founds a place.
func (s *Store) CreateCity(ctx context.Context, conn db.Conn, spec CitySpec) (City, error) {
	if err := spec.Validate(); err != nil {
		return City{}, err
	}
	crs := spec.HorizontalCRS
	if crs == "" {
		crs = "EPSG:4326"
	}

	id := ids.New(ids.KindCity)
	var west, south, east, north *float64
	if spec.Extent != nil {
		west, south = &spec.Extent.West, &spec.Extent.South
		east, north = &spec.Extent.East, &spec.Extent.North
	}
	_, err := conn.Exec(ctx, `
		INSERT INTO catalog.city
		    (id, slug, name, summary, extent, horizontal_crs, vertical_datum,
		     discoverable, created_by)
		VALUES ($1, $2, $3, $4,
		        CASE WHEN $5::float8 IS NULL THEN NULL
		             ELSE ST_MakeEnvelope($5, $6, $7, $8, 4326) END,
		        $9, $10, $11, $12)`,
		id, spec.Slug, spec.Name, spec.Summary,
		west, south, east, north,
		crs, spec.VerticalDatum, spec.Discoverable, spec.CreatedBy)
	if err != nil {
		if db.IsUniqueViolation(err) {
			return City{}, fmt.Errorf("%w: a city named %q already exists",
				domain.ErrInvalid, spec.Slug)
		}
		return City{}, fmt.Errorf("founding a city: %w", err)
	}
	return scanCity(conn.QueryRow(ctx, selectCity+` WHERE id = $1`, id))
}

// City reads one place.
func (s *Store) City(ctx context.Context, id string) (City, error) {
	place, err := scanCity(s.pool.QueryRow(ctx, selectCity+` WHERE id = $1`, id))
	return place, db.Translate(err)
}

// CityBySlug reads one place by its stable name.
func (s *Store) CityBySlug(ctx context.Context, slug string) (City, error) {
	place, err := scanCity(s.pool.QueryRow(ctx, selectCity+` WHERE slug = $1`, slug))
	return place, db.Translate(err)
}

// Cities lists the places a subject may learn of.
func (s *Store) Cities(ctx context.Context, scope Scope) ([]City, error) {
	rows, err := s.pool.Query(ctx, selectCity+`
		WHERE retired_at IS NULL
		  AND ($1::boolean OR id = ANY($2) OR ($3::boolean AND discoverable))
		ORDER BY name`,
		scope.All, scope.BoundIDs, scope.IncludeDiscoverable)
	if err != nil {
		return nil, fmt.Errorf("listing cities: %w", err)
	}
	defer rows.Close()

	places := []City{}
	for rows.Next() {
		place, err := scanCity(rows)
		if err != nil {
			return nil, err
		}
		places = append(places, place)
	}
	return places, rows.Err()
}

// ── Vehicles ─────────────────────────────────────────────────────────────────

// VehicleSpec describes a vehicle to publish.
type VehicleSpec struct {
	Slug         string
	Name         string
	Summary      string
	Manufacturer string
	Discoverable bool
	CreatedBy    string
}

// Validate reports whether the vehicle is described well enough to publish.
func (v VehicleSpec) Validate() error {
	if err := domain.ValidateSlug(v.Slug); err != nil {
		return err
	}
	if strings.TrimSpace(v.Name) == "" {
		return fmt.Errorf("%w: a vehicle has a name", domain.ErrInvalid)
	}
	return nil
}

const selectVehicle = `
	SELECT id, slug, name, summary, manufacturer, discoverable,
	       created_at, created_by, retired_at
	FROM catalog.vehicle`

func scanVehicle(row interface{ Scan(...any) error }) (Vehicle, error) {
	var craft Vehicle
	err := row.Scan(&craft.ID, &craft.Slug, &craft.Name, &craft.Summary,
		&craft.Manufacturer, &craft.Discoverable,
		&craft.CreatedAt, &craft.CreatedBy, &craft.RetiredAt)
	return craft, err
}

// CreateVehicle publishes a vehicle.
func (s *Store) CreateVehicle(ctx context.Context, conn db.Conn, spec VehicleSpec) (Vehicle, error) {
	if err := spec.Validate(); err != nil {
		return Vehicle{}, err
	}
	id := ids.New(ids.KindVehicle)
	_, err := conn.Exec(ctx, `
		INSERT INTO catalog.vehicle
		    (id, slug, name, summary, manufacturer, discoverable, created_by)
		VALUES ($1, $2, $3, $4, $5, $6, $7)`,
		id, spec.Slug, spec.Name, spec.Summary, spec.Manufacturer,
		spec.Discoverable, spec.CreatedBy)
	if err != nil {
		if db.IsUniqueViolation(err) {
			return Vehicle{}, fmt.Errorf("%w: a vehicle named %q already exists",
				domain.ErrInvalid, spec.Slug)
		}
		return Vehicle{}, fmt.Errorf("publishing a vehicle: %w", err)
	}
	return scanVehicle(conn.QueryRow(ctx, selectVehicle+` WHERE id = $1`, id))
}

// Vehicle reads one vehicle.
func (s *Store) Vehicle(ctx context.Context, id string) (Vehicle, error) {
	craft, err := scanVehicle(s.pool.QueryRow(ctx, selectVehicle+` WHERE id = $1`, id))
	return craft, db.Translate(err)
}

// VehicleBySlug reads one vehicle by its stable name.
func (s *Store) VehicleBySlug(ctx context.Context, slug string) (Vehicle, error) {
	craft, err := scanVehicle(s.pool.QueryRow(ctx, selectVehicle+` WHERE slug = $1`, slug))
	return craft, db.Translate(err)
}

// Vehicles lists the vehicles a subject may learn of.
func (s *Store) Vehicles(ctx context.Context, scope Scope) ([]Vehicle, error) {
	rows, err := s.pool.Query(ctx, selectVehicle+`
		WHERE retired_at IS NULL
		  AND ($1::boolean OR id = ANY($2) OR ($3::boolean AND discoverable))
		ORDER BY name`,
		scope.All, scope.BoundIDs, scope.IncludeDiscoverable)
	if err != nil {
		return nil, fmt.Errorf("listing vehicles: %w", err)
	}
	defer rows.Close()

	craft := []Vehicle{}
	for rows.Next() {
		one, err := scanVehicle(rows)
		if err != nil {
			return nil, err
		}
		craft = append(craft, one)
	}
	return craft, rows.Err()
}

// ── Versions ─────────────────────────────────────────────────────────────────

// VersionSpec describes a package to record.
//
// The digest is computed from the manifest rather than supplied, so a caller
// cannot claim a digest its files do not add up to.
type VersionSpec struct {
	AssetKind  AssetKind
	AssetID    string
	Label      string
	Notes      string
	Manifest   []domain.ManifestEntry
	RuntimeMin string
	CreatedBy  string
}

const selectVersion = `
	SELECT id, asset_kind, asset_id, ordinal, label, notes, digest, manifest,
	       total_bytes, runtime_min, published_at, created_at, created_by
	FROM catalog.version`

func scanVersion(row interface{ Scan(...any) error }) (Version, error) {
	var version Version
	var digest []byte
	var manifest []byte
	err := row.Scan(&version.ID, &version.AssetKind, &version.AssetID, &version.Ordinal,
		&version.Label, &version.Notes, &digest, &manifest, &version.TotalBytes,
		&version.RuntimeMin, &version.PublishedAt, &version.CreatedAt, &version.CreatedBy)
	if err != nil {
		return Version{}, err
	}
	if version.Digest, err = domain.DigestFromBytes(digest); err != nil {
		return Version{}, fmt.Errorf("reading version %s: %w", version.ID, err)
	}
	if err := json.Unmarshal(manifest, &version.Manifest); err != nil {
		return Version{}, fmt.Errorf("reading the manifest of version %s: %w", version.ID, err)
	}
	return version, nil
}

// CreateVersion records a new package for an asset, unpublished.
//
// Publication is separate because a package is uploaded before it is complete,
// and a half-uploaded city that something could already pin would be worse than
// no city at all.
func (s *Store) CreateVersion(ctx context.Context, conn db.Conn, spec VersionSpec) (Version, error) {
	if _, err := ParseAssetKind(string(spec.AssetKind)); err != nil {
		return Version{}, err
	}
	if len(spec.Manifest) == 0 {
		return Version{}, fmt.Errorf("%w: a package version lists the files it contains",
			domain.ErrInvalid)
	}
	digest, err := domain.ManifestDigest(spec.Manifest)
	if err != nil {
		return Version{}, err
	}

	var total int64
	for _, entry := range spec.Manifest {
		total += entry.SizeBytes
	}
	manifest, err := json.Marshal(spec.Manifest)
	if err != nil {
		return Version{}, fmt.Errorf("recording the manifest: %w", err)
	}

	id := ids.New(ids.KindVersion)
	_, err = conn.Exec(ctx, `
		INSERT INTO catalog.version
		    (id, asset_kind, asset_id, ordinal, label, notes, digest, manifest,
		     total_bytes, runtime_min, created_by)
		VALUES ($1, $2::catalog.asset_kind, $3,
		        (SELECT coalesce(max(ordinal), 0) + 1 FROM catalog.version
		          WHERE asset_kind = $2::catalog.asset_kind AND asset_id = $3),
		        $4, $5, $6, $7, $8, $9, $10)`,
		id, string(spec.AssetKind), spec.AssetID, spec.Label, spec.Notes,
		digest[:], manifest, total, spec.RuntimeMin, spec.CreatedBy)
	if err != nil {
		return Version{}, fmt.Errorf("recording a version: %w", err)
	}
	return scanVersion(conn.QueryRow(ctx, selectVersion+` WHERE id = $1`, id))
}

// Version reads one package version.
func (s *Store) Version(ctx context.Context, id string) (Version, error) {
	version, err := scanVersion(s.pool.QueryRow(ctx, selectVersion+` WHERE id = $1`, id))
	return version, db.Translate(err)
}

// Versions lists an asset's packages, newest first.
func (s *Store) Versions(ctx context.Context, kind AssetKind, assetID string) ([]Version, error) {
	rows, err := s.pool.Query(ctx, selectVersion+`
		WHERE asset_kind = $1::catalog.asset_kind AND asset_id = $2
		ORDER BY ordinal DESC`, string(kind), assetID)
	if err != nil {
		return nil, fmt.Errorf("listing versions: %w", err)
	}
	defer rows.Close()

	versions := []Version{}
	for rows.Next() {
		version, err := scanVersion(rows)
		if err != nil {
			return nil, err
		}
		versions = append(versions, version)
	}
	return versions, rows.Err()
}

// Publish makes a version pinnable, and from then on unchangeable.
//
// A vehicle must know how it moves before anything may fly it, so publishing
// one without dynamics is refused here rather than discovered by a dive that
// has already claimed a GPU.
func (s *Store) Publish(ctx context.Context, conn db.Conn, id string) (Version, error) {
	version, err := scanVersion(conn.QueryRow(ctx, selectVersion+` WHERE id = $1`, id))
	if err != nil {
		return Version{}, db.Translate(err)
	}
	if version.Published() {
		return version, nil // Publishing twice is not an error; it is already true.
	}
	if version.AssetKind == KindVehicle {
		var present bool
		if err := conn.QueryRow(ctx, `
			SELECT exists(SELECT 1 FROM catalog.vehicle_dynamics WHERE version_id = $1)`,
			id).Scan(&present); err != nil {
			return Version{}, fmt.Errorf("checking for dynamics: %w", err)
		}
		if !present {
			return Version{}, fmt.Errorf(
				"%w: a vehicle version states how it moves before it can be published",
				domain.ErrInvalid)
		}
	}

	if _, err := conn.Exec(ctx,
		`UPDATE catalog.version SET published_at = now() WHERE id = $1`, id); err != nil {
		return Version{}, fmt.Errorf("publishing a version: %w", err)
	}
	return scanVersion(conn.QueryRow(ctx, selectVersion+` WHERE id = $1`, id))
}

// ── Dynamics ─────────────────────────────────────────────────────────────────

// SetDynamics records how a vehicle version moves. Refused once published,
// by the record itself as well as here.
func (s *Store) SetDynamics(ctx context.Context, conn db.Conn, spec Dynamics) error {
	if err := spec.Validate(); err != nil {
		return err
	}
	_, err := conn.Exec(ctx, `
		INSERT INTO catalog.vehicle_dynamics
		    (version_id, mass_kg, displaced_volume_m3, centre_of_gravity_m,
		     centre_of_buoyancy_m, inertia_tensor, added_mass, linear_damping,
		     quadratic_damping, thrusters, sensors, topic_contract)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)`,
		spec.VersionID, spec.MassKg, spec.DisplacedVolumeM3,
		spec.CentreOfGravity[:], spec.CentreOfBuoyancy[:], spec.InertiaTensor[:],
		spec.AddedMass, spec.LinearDamping, spec.QuadraticDamping,
		spec.Thrusters, spec.Sensors, spec.TopicContract)
	if err != nil {
		if message, ok := db.RaisedMessage(err); ok {
			return fmt.Errorf("%w: %s", domain.ErrInvalid, message)
		}
		if db.IsUniqueViolation(err) {
			return fmt.Errorf("%w: this version already states how it moves", domain.ErrInvalid)
		}
		return fmt.Errorf("recording dynamics: %w", err)
	}
	return nil
}

// Dynamics reads how a vehicle version moves.
func (s *Store) Dynamics(ctx context.Context, versionID string) (Dynamics, error) {
	var spec Dynamics
	var gravity, buoyancy, inertia []float64
	err := s.pool.QueryRow(ctx, `
		SELECT version_id, mass_kg, displaced_volume_m3, centre_of_gravity_m,
		       centre_of_buoyancy_m, inertia_tensor, added_mass, linear_damping,
		       quadratic_damping, thrusters, sensors, topic_contract
		FROM catalog.vehicle_dynamics WHERE version_id = $1`, versionID).
		Scan(&spec.VersionID, &spec.MassKg, &spec.DisplacedVolumeM3,
			&gravity, &buoyancy, &inertia, &spec.AddedMass, &spec.LinearDamping,
			&spec.QuadraticDamping, &spec.Thrusters, &spec.Sensors, &spec.TopicContract)
	if err != nil {
		return Dynamics{}, db.Translate(err)
	}
	copy(spec.CentreOfGravity[:], gravity)
	copy(spec.CentreOfBuoyancy[:], buoyancy)
	copy(spec.InertiaTensor[:], inertia)
	return spec, nil
}
