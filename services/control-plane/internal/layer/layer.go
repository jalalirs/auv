// Package layer owns every datum the platform holds.
//
// Bathymetry, a survey mesh, an orthomosaic, a gridded forecast field, an
// observation series, an annotation, a simulation output: all of them are
// layers. A layer is contained by its scope — the platform, for the shared
// world, or one city — and attributed to the organisation that contributed it.
// Containment and attribution are different things, and keeping them apart is
// what lets a contribution be promoted without moving anything.
//
// A version is immutable evidence. Corrections create new versions; the
// database refuses to rewrite a published one.
package layer

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

// Layer is a named series of versions within one scope.
type Layer struct {
	ID              string           `json:"id"`
	ScopeKind       domain.ScopeKind `json:"scopeKind"`
	CityID          string           `json:"cityId,omitempty"`
	Slug            string           `json:"slug"`
	Kind            domain.LayerKind `json:"kind"`
	Title           string           `json:"title"`
	Description     string           `json:"description"`
	AttributedOrgID string           `json:"attributedOrgId"`
	CreatedBy       string           `json:"createdBy"`
	CreatedAt       time.Time        `json:"createdAt"`
}

// CreateSpec describes a layer to create.
type CreateSpec struct {
	ScopeKind       domain.ScopeKind
	CityID          string
	Slug            string
	Kind            domain.LayerKind
	Title           string
	Description     string
	AttributedOrgID string
	CreatedBy       string
}

// Validate reports whether the layer is fully described.
func (c CreateSpec) Validate() error {
	if _, err := domain.ParseScopeKind(string(c.ScopeKind)); err != nil {
		return err
	}
	if (c.ScopeKind == domain.CityScope) != (c.CityID != "") {
		return fmt.Errorf("%w: a city layer names its city and a platform layer does not",
			domain.ErrInvalid)
	}
	if err := domain.ValidateSlug(c.Slug); err != nil {
		return err
	}
	if _, err := domain.ParseLayerKind(string(c.Kind)); err != nil {
		return err
	}
	if strings.TrimSpace(c.Title) == "" {
		return fmt.Errorf("%w: a layer has a title", domain.ErrInvalid)
	}
	if strings.TrimSpace(c.Description) == "" {
		return fmt.Errorf("%w: a layer has a description saying what it holds", domain.ErrInvalid)
	}
	if c.AttributedOrgID == "" {
		return fmt.Errorf("%w: a layer is attributed to an organisation", domain.ErrInvalid)
	}
	return nil
}

// Store reads and writes layers and their versions.
type Store struct{ pool *db.Pool }

// NewStore builds the layer store.
func NewStore(pool *db.Pool) *Store { return &Store{pool: pool} }

const selectLayer = `
	SELECT id, scope_kind, coalesce(city_id, ''), slug, kind, title, description,
	       attributed_org_id, created_by, created_at
	FROM layer.layer`

func scanLayer(row interface{ Scan(...any) error }) (Layer, error) {
	var record Layer
	err := row.Scan(&record.ID, &record.ScopeKind, &record.CityID, &record.Slug,
		&record.Kind, &record.Title, &record.Description,
		&record.AttributedOrgID, &record.CreatedBy, &record.CreatedAt)
	return record, err
}

// Create adds a layer to a scope.
func (s *Store) Create(ctx context.Context, conn db.Conn, spec CreateSpec) (Layer, error) {
	if err := spec.Validate(); err != nil {
		return Layer{}, err
	}
	var cityID *string
	if spec.CityID != "" {
		cityID = &spec.CityID
	}

	id := ids.New(ids.KindLayer)
	_, err := conn.Exec(ctx, `
		INSERT INTO layer.layer
		    (id, scope_kind, city_id, slug, kind, title, description, attributed_org_id, created_by)
		VALUES ($1, $2::layer.scope_kind, $3, $4, $5::layer.kind, $6, $7, $8, $9)`,
		id, string(spec.ScopeKind), cityID, spec.Slug, string(spec.Kind),
		spec.Title, spec.Description, spec.AttributedOrgID, spec.CreatedBy)
	if err != nil {
		if db.IsUniqueViolation(err) {
			return Layer{}, fmt.Errorf("%w: a layer named %q already exists in that scope",
				domain.ErrInvalid, spec.Slug)
		}
		return Layer{}, fmt.Errorf("creating a layer: %w", err)
	}
	return scanLayer(conn.QueryRow(ctx, selectLayer+` WHERE id = $1`, id))
}

// Layer reads one layer.
func (s *Store) Layer(ctx context.Context, id string) (Layer, error) {
	record, err := scanLayer(s.pool.QueryRow(ctx, selectLayer+` WHERE id = $1`, id))
	return record, db.Translate(err)
}

// InScope lists the layers of a scope that hold at least one version the
// subject may see. A layer whose every version is invisible is itself
// invisible, so a listing never hints at contributions a caller may not read.
func (s *Store) InScope(ctx context.Context, scope domain.ScopeKind, cityID string, filter policy.VersionFilter) ([]Layer, error) {
	rows, err := s.pool.Query(ctx, selectLayer+` AS l
		WHERE l.scope_kind = $1::layer.scope_kind
		  AND coalesce(l.city_id, '') = $2
		  AND EXISTS (
		        SELECT 1 FROM layer.version v
		        WHERE v.layer_id = l.id AND `+visibilityPredicate("v", "l", 3)+`
		      )
		ORDER BY l.title`,
		string(scope), cityID,
		filter.Canonical, filter.RestrictedOfOrgs, filter.AllRestricted, filter.IncludeWithdrawn)
	if err != nil {
		return nil, fmt.Errorf("reading layers: %w", err)
	}
	defer rows.Close()

	layers := []Layer{}
	for rows.Next() {
		record, err := scanLayer(rows)
		if err != nil {
			return nil, err
		}
		layers = append(layers, record)
	}
	return layers, rows.Err()
}

// visibilityPredicate renders the decision point's version filter as SQL.
//
// It is written once, here, and used by every query that returns versions, so
// that no listing can accidentally be more generous than another. The filter
// itself is decided in the policy package; this only applies it.
//
// The four filter arguments begin at position first.
func visibilityPredicate(version, layer string, first int) string {
	canonical := fmt.Sprintf("$%d::boolean", first)
	orgs := fmt.Sprintf("$%d::text[]", first+1)
	allRestricted := fmt.Sprintf("$%d::boolean", first+2)
	withdrawn := fmt.Sprintf("$%d::boolean", first+3)

	return fmt.Sprintf(`(
		    (
		      -- The shared record: published or superseded canonical versions.
		      %[1]s AND %[5]s.visibility = 'canonical'
		          AND %[5]s.state IN ('published', 'superseded')
		    )
		 OR (
		      -- A contributor sees every state of its own organisation's work.
		      %[6]s.attributed_org_id = ANY(%[2]s)
		    )
		 OR (
		      -- A steward sees every contribution offered in the scope.
		      %[3]s
		    )
		)
		AND (%[4]s OR %[5]s.state <> 'retracted')`,
		canonical, orgs, allRestricted, withdrawn, version, layer)
}
