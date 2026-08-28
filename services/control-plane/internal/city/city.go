// Package city owns places.
//
// A city is a bounded, curated, navigable region: a reef, an offshore
// installation, a port, a fishing ground. It exists at the platform and is
// addressed permanently, so that citations, layer references, and scenario pins
// survive every change of who may enter it. An organisation is granted access
// to a city; it never contains one.
package city

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// City is a place.
type City struct {
	ID              string                     `json:"id"`
	Slug            string                     `json:"slug"`
	Name            string                     `json:"name"`
	Summary         string                     `json:"summary"`
	Extent          domain.Extent              `json:"extent"`
	CRS             domain.CoordinateReference `json:"crsEpsg"`
	VerticalDatum   string                     `json:"verticalDatum"`
	Discoverability domain.Discoverability     `json:"discoverability"`
	CreatedAt       time.Time                  `json:"createdAt"`
	CreatedBy       string                     `json:"createdBy"`
}

// CreateSpec describes a place to found.
type CreateSpec struct {
	Slug            string
	Name            string
	Summary         string
	Extent          domain.Extent
	CRS             domain.CoordinateReference
	VerticalDatum   string
	Discoverability domain.Discoverability
	CreatedBy       string
}

// Validate reports whether the place is fully described. A city without a
// coordinate reference or a vertical datum is not a place, so neither is
// optional.
func (c CreateSpec) Validate() error {
	if err := domain.ValidateSlug(c.Slug); err != nil {
		return err
	}
	if strings.TrimSpace(c.Name) == "" {
		return fmt.Errorf("%w: a city has a name", domain.ErrInvalid)
	}
	if strings.TrimSpace(c.Summary) == "" {
		return fmt.Errorf("%w: a city has a summary saying what place it is", domain.ErrInvalid)
	}
	if err := c.Extent.Validate(); err != nil {
		return err
	}
	if err := c.CRS.Validate(); err != nil {
		return err
	}
	if strings.TrimSpace(c.VerticalDatum) == "" {
		return fmt.Errorf("%w: a city states the vertical datum its depths are measured against",
			domain.ErrInvalid)
	}
	if _, err := domain.ParseDiscoverability(string(c.Discoverability)); err != nil {
		return err
	}
	return nil
}

// Store reads and writes places.
type Store struct{ pool *db.Pool }

// NewStore builds the city store.
func NewStore(pool *db.Pool) *Store { return &Store{pool: pool} }

const selectCity = `
	SELECT id, slug, name, summary,
	       ST_XMin(extent), ST_YMin(extent),
	       ST_XMax(extent), ST_YMax(extent),
	       crs_epsg, vertical_datum, discoverability, created_at, created_by
	FROM city.city`

func scanCity(row interface{ Scan(...any) error }) (City, error) {
	var place City
	err := row.Scan(&place.ID, &place.Slug, &place.Name, &place.Summary,
		&place.Extent.West, &place.Extent.South, &place.Extent.East, &place.Extent.North,
		&place.CRS, &place.VerticalDatum, &place.Discoverability,
		&place.CreatedAt, &place.CreatedBy)
	return place, err
}

// Create founds a place.
func (s *Store) Create(ctx context.Context, conn db.Conn, spec CreateSpec) (City, error) {
	if err := spec.Validate(); err != nil {
		return City{}, err
	}

	id := ids.New(ids.KindCity)
	_, err := conn.Exec(ctx, `
		INSERT INTO city.city
		    (id, slug, name, summary, extent, crs_epsg, vertical_datum, discoverability, created_by)
		VALUES ($1, $2, $3, $4,
		        ST_MakeEnvelope($5, $6, $7, $8, 4326),
		        $9, $10, $11::city.discoverability, $12)`,
		id, spec.Slug, spec.Name, spec.Summary,
		spec.Extent.West, spec.Extent.South, spec.Extent.East, spec.Extent.North,
		int(spec.CRS), spec.VerticalDatum, string(spec.Discoverability), spec.CreatedBy)
	if err != nil {
		if db.IsUniqueViolation(err) {
			return City{}, fmt.Errorf("%w: a city named %q already exists", domain.ErrInvalid, spec.Slug)
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

// BySlug reads one place by its stable name.
func (s *Store) BySlug(ctx context.Context, slug string) (City, error) {
	place, err := scanCity(s.pool.QueryRow(ctx, selectCity+` WHERE slug = $1`, slug))
	return place, db.Translate(err)
}

// UpdateSpec describes changes to a place's description. A city's extent,
// coordinate reference, and vertical datum are what it is, and changing them
// would make it a different place, so they are not changed here.
type UpdateSpec struct {
	Name            *string
	Summary         *string
	Discoverability *domain.Discoverability
}

// Update changes a place's description or who may learn of it.
func (s *Store) Update(ctx context.Context, conn db.Conn, id string, spec UpdateSpec) (City, error) {
	if spec.Name != nil && strings.TrimSpace(*spec.Name) == "" {
		return City{}, fmt.Errorf("%w: a city has a name", domain.ErrInvalid)
	}
	if spec.Summary != nil && strings.TrimSpace(*spec.Summary) == "" {
		return City{}, fmt.Errorf("%w: a city has a summary", domain.ErrInvalid)
	}
	if spec.Discoverability != nil {
		if _, err := domain.ParseDiscoverability(string(*spec.Discoverability)); err != nil {
			return City{}, err
		}
	}

	var discoverability *string
	if spec.Discoverability != nil {
		value := string(*spec.Discoverability)
		discoverability = &value
	}
	tag, err := conn.Exec(ctx, `
		UPDATE city.city SET
		    name = coalesce($2, name),
		    summary = coalesce($3, summary),
		    discoverability = coalesce($4::city.discoverability, discoverability)
		WHERE id = $1`,
		id, spec.Name, spec.Summary, discoverability)
	if err != nil {
		return City{}, fmt.Errorf("updating a city: %w", err)
	}
	if tag.RowsAffected() == 0 {
		return City{}, db.ErrNotFound
	}
	return scanCity(conn.QueryRow(ctx, selectCity+` WHERE id = $1`, id))
}

// Catalogue lists the places a subject may learn of.
//
// The predicate comes from the decision point; this method only applies it, so
// that listing and entering agree about what exists.
func (s *Store) Catalogue(ctx context.Context, scope policy.CatalogueScope) ([]City, error) {
	rows, err := s.pool.Query(ctx, selectCity+`
		WHERE $1::boolean
		   OR id = ANY($2)
		   OR ($3::boolean AND discoverability IN ('listed_open', 'listed_locked'))
		ORDER BY name`,
		scope.AllCities, scope.BoundCityIDs, scope.IncludeListed)
	if err != nil {
		return nil, fmt.Errorf("reading the catalogue: %w", err)
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
