package layer

import (
	"context"
	"fmt"
	"strings"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

const selectVersion = `
	SELECT v.id, v.layer_id, v.ordinal, encode(v.content_digest, 'hex'), v.truth_class,
	       v.crs_epsg, v.vertical_datum,
	       ST_XMin(v.extent), ST_YMin(v.extent),
	       ST_XMax(v.extent), ST_YMax(v.extent),
	       v.observed_from, v.observed_to, v.clock_offset_seconds,
	       v.uncertainty_kind, v.uncertainty_value, v.uncertainty_note,
	       v.rights, v.attribution, v.state, v.visibility,
	       coalesce(v.supersedes_id, ''), coalesce(v.superseded_by_id, ''),
	       coalesce(v.producer_job_id, ''), coalesce(v.producer_principal_id, ''),
	       v.recipe_id, v.image_digest,
	       v.created_at, v.published_at, v.retracted_at, v.retraction_reason
	FROM layer.version v
	JOIN layer.layer l ON l.id = v.layer_id`

func scanVersion(row interface{ Scan(...any) error }) (Version, error) {
	var record Version
	err := row.Scan(&record.ID, &record.LayerID, &record.Ordinal, &record.ContentDigest,
		&record.TruthClass, &record.CRS, &record.VerticalDatum,
		&record.Extent.West, &record.Extent.South, &record.Extent.East, &record.Extent.North,
		&record.ObservedFrom, &record.ObservedTo, &record.ClockOffsetSeconds,
		&record.Uncertainty.Kind, &record.Uncertainty.Value, &record.Uncertainty.Note,
		&record.Rights, &record.Attribution, &record.State, &record.Visibility,
		&record.SupersedesID, &record.SupersededByID,
		&record.ProducerJobID, &record.ProducerPrincipalID,
		&record.RecipeID, &record.ImageDigest,
		&record.CreatedAt, &record.PublishedAt, &record.RetractedAt, &record.RetractionReason)
	return record, err
}

func (s *Store) versionOn(ctx context.Context, conn db.Conn, id string) (Version, error) {
	record, err := scanVersion(conn.QueryRow(ctx, selectVersion+` WHERE v.id = $1`, id))
	if err != nil {
		return Version{}, db.Translate(err)
	}
	record.Manifest, err = s.manifestOn(ctx, conn, id)
	if err != nil {
		return Version{}, err
	}
	return record, nil
}

// Version reads one version, including its manifest, if the subject's filter
// admits it. A version the filter excludes reports as absent.
func (s *Store) Version(ctx context.Context, id string, filter policy.VersionFilter) (Version, error) {
	record, err := scanVersion(s.pool.QueryRow(ctx,
		selectVersion+` WHERE v.id = $1 AND `+visibilityPredicate("v", "l", 2),
		id, filter.Canonical, filter.RestrictedOfOrgs, filter.AllRestricted, filter.IncludeWithdrawn))
	if err != nil {
		return Version{}, db.Translate(err)
	}
	record.Manifest, err = s.manifestOn(ctx, s.pool, id)
	if err != nil {
		return Version{}, err
	}
	return record, nil
}

// Versions lists a layer's versions, newest first, admitting only those the
// filter allows.
func (s *Store) Versions(ctx context.Context, layerID string, filter policy.VersionFilter) ([]Version, error) {
	rows, err := s.pool.Query(ctx,
		selectVersion+` WHERE v.layer_id = $1 AND `+visibilityPredicate("v", "l", 2)+`
		ORDER BY v.ordinal DESC`,
		layerID, filter.Canonical, filter.RestrictedOfOrgs, filter.AllRestricted, filter.IncludeWithdrawn)
	if err != nil {
		return nil, fmt.Errorf("reading versions: %w", err)
	}
	defer rows.Close()

	versions := []Version{}
	for rows.Next() {
		record, err := scanVersion(rows)
		if err != nil {
			return nil, err
		}
		versions = append(versions, record)
	}
	return versions, rows.Err()
}

func (s *Store) manifestOn(ctx context.Context, conn db.Conn, versionID string) ([]ManifestFile, error) {
	rows, err := conn.Query(ctx, `
		SELECT vo.relative_path, vo.object_id, encode(o.sha256, 'hex'), o.size_bytes, o.media_type
		FROM layer.version_object vo
		JOIN store.object o ON o.id = vo.object_id
		WHERE vo.version_id = $1
		ORDER BY vo.relative_path`, versionID)
	if err != nil {
		return nil, fmt.Errorf("reading a version manifest: %w", err)
	}
	defer rows.Close()

	manifest := []ManifestFile{}
	for rows.Next() {
		var file ManifestFile
		if err := rows.Scan(&file.RelativePath, &file.ObjectID,
			&file.SHA256, &file.SizeBytes, &file.MediaType); err != nil {
			return nil, err
		}
		manifest = append(manifest, file)
	}
	return manifest, rows.Err()
}

// Lineage lists the versions a version was derived from.
func (s *Store) Lineage(ctx context.Context, versionID string, filter policy.VersionFilter) ([]Version, error) {
	rows, err := s.pool.Query(ctx,
		selectVersion+`
		JOIN layer.lineage lin ON lin.input_version_id = v.id
		WHERE lin.output_version_id = $1 AND `+visibilityPredicate("v", "l", 2)+`
		ORDER BY v.created_at`,
		versionID, filter.Canonical, filter.RestrictedOfOrgs, filter.AllRestricted, filter.IncludeWithdrawn)
	if err != nil {
		return nil, fmt.Errorf("reading lineage: %w", err)
	}
	defer rows.Close()

	inputs := []Version{}
	for rows.Next() {
		record, err := scanVersion(rows)
		if err != nil {
			return nil, err
		}
		inputs = append(inputs, record)
	}
	return inputs, rows.Err()
}

// Submit offers a draft for review.
func (s *Store) Submit(ctx context.Context, conn db.Conn, versionID string) (Version, error) {
	return s.transition(ctx, conn, versionID, `
		UPDATE layer.version SET state = 'in_review'
		WHERE id = $1 AND state = 'draft'`,
		"only a draft can be offered for review")
}

// Publish makes a reviewed version part of the record.
//
// Publishing a version that supersedes another marks the earlier one
// superseded in the same transaction, so the two statements about the same
// subject never disagree.
func (s *Store) Publish(ctx context.Context, conn db.Conn, versionID string) (Version, error) {
	published, err := s.transition(ctx, conn, versionID, `
		UPDATE layer.version SET state = 'published', published_at = now()
		WHERE id = $1 AND state IN ('draft', 'in_review')`,
		"only a draft or a version under review can be published")
	if err != nil {
		return Version{}, err
	}

	if published.SupersedesID != "" {
		tag, err := conn.Exec(ctx, `
			UPDATE layer.version SET state = 'superseded', superseded_by_id = $2
			WHERE id = $1 AND state = 'published'`, published.SupersedesID, published.ID)
		if err != nil {
			return Version{}, fmt.Errorf("superseding the earlier version: %w", err)
		}
		if tag.RowsAffected() == 0 {
			return Version{}, fmt.Errorf(
				"%w: version %s cannot be superseded because it is not published",
				ErrTransition, published.SupersedesID)
		}
		return s.versionOn(ctx, conn, versionID)
	}
	return published, nil
}

// Promote makes a restricted contribution part of the shared record.
//
// Nothing moves: the object keys, the content digest, and the version number
// are unchanged. Only who may see it changes, and a record is written that it
// changed.
func (s *Store) Promote(ctx context.Context, conn db.Conn, versionID string) (Version, error) {
	return s.transition(ctx, conn, versionID, `
		UPDATE layer.version SET visibility = 'canonical'
		WHERE id = $1 AND visibility = 'restricted' AND state IN ('published', 'superseded')`,
		"only a published, restricted version can be promoted to the shared record")
}

// Retract withdraws a published version from default views. It is not deleted,
// and neither is its lineage: retraction is a statement about a version, not
// its erasure.
func (s *Store) Retract(ctx context.Context, conn db.Conn, versionID, reason string) (Version, error) {
	if strings.TrimSpace(reason) == "" {
		return Version{}, fmt.Errorf("%w: a retraction says why", domain.ErrInvalid)
	}
	record, err := s.transitionWithArgs(ctx, conn, versionID, `
		UPDATE layer.version SET state = 'retracted', retracted_at = now(), retraction_reason = $2
		WHERE id = $1 AND state IN ('published', 'superseded')`,
		"only a published version can be retracted", reason)
	return record, err
}

func (s *Store) transition(ctx context.Context, conn db.Conn, versionID, statement, refusal string) (Version, error) {
	return s.transitionWithArgs(ctx, conn, versionID, statement, refusal)
}

func (s *Store) transitionWithArgs(ctx context.Context, conn db.Conn, versionID, statement, refusal string, extra ...any) (Version, error) {
	args := append([]any{versionID}, extra...)
	tag, err := conn.Exec(ctx, statement, args...)
	if err != nil {
		if message, raised := db.RaisedMessage(err); raised {
			return Version{}, fmt.Errorf("%w: %s", ErrTransition, message)
		}
		return Version{}, fmt.Errorf("changing a version's publication state: %w", err)
	}
	if tag.RowsAffected() == 0 {
		// Either the version does not exist or it is not in a state this step
		// applies to. Distinguishing the two tells the caller which it is.
		var exists bool
		if err := conn.QueryRow(ctx,
			`SELECT true FROM layer.version WHERE id = $1`, versionID).Scan(&exists); err != nil {
			return Version{}, db.ErrNotFound
		}
		return Version{}, fmt.Errorf("%w: %s", ErrTransition, refusal)
	}
	return s.versionOn(ctx, conn, versionID)
}
