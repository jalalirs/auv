package layer

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
)

// ErrTruthClassStrengthened reports an attempt to present derived material as
// better evidence than what it came from.
var ErrTruthClassStrengthened = errors.New("truth class does not strengthen down lineage")

// ErrTransition reports a publication step that the lifecycle does not allow.
var ErrTransition = errors.New("that publication step is not available")

// ManifestFile is one file within a version's payload. A version is a set of
// files because a tileset or a survey is many, and its identity is the digest
// over all of them.
type ManifestFile struct {
	RelativePath string `json:"relativePath"`
	ObjectID     string `json:"objectId"`
	SHA256       string `json:"sha256"`
	SizeBytes    int64  `json:"sizeBytes"`
	MediaType    string `json:"mediaType"`
}

// Version is immutable evidence: what was measured or computed, where, when,
// by what, and how well it is known.
type Version struct {
	ID            string            `json:"id"`
	LayerID       string            `json:"layerId"`
	Ordinal       int               `json:"ordinal"`
	ContentDigest string            `json:"contentDigest"`
	TruthClass    domain.TruthClass `json:"truthClass"`

	CRS           domain.CoordinateReference `json:"crsEpsg"`
	VerticalDatum string                     `json:"verticalDatum"`
	Extent        domain.Extent              `json:"extent"`

	ObservedFrom       time.Time `json:"observedFrom"`
	ObservedTo         time.Time `json:"observedTo"`
	ClockOffsetSeconds *float64  `json:"clockOffsetSeconds,omitempty"`

	Uncertainty domain.Uncertainty `json:"-"`
	Rights      string             `json:"rights"`
	Attribution string             `json:"attribution"`

	State      domain.LayerState `json:"state"`
	Visibility domain.Visibility `json:"visibility"`

	SupersedesID   string `json:"supersedesId,omitempty"`
	SupersededByID string `json:"supersededById,omitempty"`

	ProducerJobID       string `json:"producerJobId,omitempty"`
	ProducerPrincipalID string `json:"producerPrincipalId,omitempty"`
	RecipeID            string `json:"recipeId,omitempty"`
	ImageDigest         string `json:"imageDigest,omitempty"`

	CreatedAt        time.Time  `json:"createdAt"`
	PublishedAt      *time.Time `json:"publishedAt,omitempty"`
	RetractedAt      *time.Time `json:"retractedAt,omitempty"`
	RetractionReason string     `json:"retractionReason,omitempty"`

	Manifest []ManifestFile `json:"manifest,omitempty"`
}

// UncertaintyKind exposes how this version states what it does not know.
func (v Version) UncertaintyKind() domain.UncertaintyKind { return v.Uncertainty.Kind }

// VersionSpec describes evidence to record.
type VersionSpec struct {
	LayerID       string
	TruthClass    domain.TruthClass
	CRS           domain.CoordinateReference
	VerticalDatum string
	Extent        domain.Extent
	Time          domain.TimeBasis
	Uncertainty   domain.Uncertainty
	Rights        string
	Attribution   string
	Visibility    domain.Visibility

	// Files name the objects that make up the payload, by path.
	Files []ManifestInput
	// DerivedFrom names the versions this one was computed from. Their truth
	// classes decide what this version is permitted to claim.
	DerivedFrom []string

	SupersedesID string

	// Exactly one producer: the job that computed it, or the person who
	// uploaded it.
	ProducerJobID       string
	ProducerPrincipalID string
	RecipeID            string
	ImageDigest         string
}

// ManifestInput names one object and where it sits within the version.
type ManifestInput struct {
	RelativePath string
	ObjectID     string
}

// Validate reports whether the evidence is fully described. Nothing here is
// optional: a version without a coordinate reference, a vertical datum, a time
// basis, or a stated uncertainty is not evidence.
func (v VersionSpec) Validate() error {
	if v.LayerID == "" {
		return fmt.Errorf("%w: a version belongs to a layer", domain.ErrInvalid)
	}
	if _, err := domain.ParseTruthClass(string(v.TruthClass)); err != nil {
		return err
	}
	if err := v.CRS.Validate(); err != nil {
		return err
	}
	if strings.TrimSpace(v.VerticalDatum) == "" {
		return fmt.Errorf("%w: a version states the vertical datum its heights are measured against",
			domain.ErrInvalid)
	}
	if err := v.Extent.Validate(); err != nil {
		return err
	}
	if err := v.Time.Validate(); err != nil {
		return err
	}
	if err := v.Uncertainty.Validate(); err != nil {
		return err
	}
	if strings.TrimSpace(v.Rights) == "" {
		return fmt.Errorf("%w: a version states the rights under which it may be used",
			domain.ErrInvalid)
	}
	if strings.TrimSpace(v.Attribution) == "" {
		return fmt.Errorf("%w: a version states who it must be credited to", domain.ErrInvalid)
	}
	switch v.Visibility {
	case domain.Restricted, domain.Canonical:
	default:
		return fmt.Errorf("%w: visibility is restricted or canonical, not %q",
			domain.ErrInvalid, v.Visibility)
	}
	if len(v.Files) == 0 {
		return fmt.Errorf("%w: a version has at least one file", domain.ErrInvalid)
	}
	for _, file := range v.Files {
		if err := domain.ValidateRelativePath(file.RelativePath); err != nil {
			return err
		}
		if file.ObjectID == "" {
			return fmt.Errorf("%w: %q names no object", domain.ErrInvalid, file.RelativePath)
		}
	}
	if (v.ProducerJobID != "") == (v.ProducerPrincipalID != "") {
		return fmt.Errorf("%w: a version is produced by exactly one of a job or a person",
			domain.ErrInvalid)
	}
	if v.ProducerJobID != "" && (v.RecipeID == "" || v.ImageDigest == "") {
		return fmt.Errorf("%w: a computed version names the recipe and image digest that produced it",
			domain.ErrInvalid)
	}
	return nil
}

// CreateVersion records evidence.
//
// It resolves the payload's true digests from the object registry, computes the
// version's single citable content digest, and refuses any truth class stronger
// than the material it derives from. All of it happens in the caller's
// transaction, so a version, its manifest, and its lineage arrive together or
// not at all.
func (s *Store) CreateVersion(ctx context.Context, conn db.Conn, spec VersionSpec) (Version, error) {
	if err := spec.Validate(); err != nil {
		return Version{}, err
	}

	manifest, err := s.resolveManifest(ctx, conn, spec.Files)
	if err != nil {
		return Version{}, err
	}
	entries := make([]domain.ManifestEntry, 0, len(manifest))
	for _, file := range manifest {
		digest, err := domain.ParseDigest(file.SHA256)
		if err != nil {
			return Version{}, err
		}
		entries = append(entries, domain.ManifestEntry{
			RelativePath: file.RelativePath,
			Digest:       digest,
			SizeBytes:    file.SizeBytes,
			MediaType:    file.MediaType,
		})
	}
	contentDigest, err := domain.ManifestDigest(entries)
	if err != nil {
		return Version{}, err
	}

	inheritedClasses, err := s.truthClassesOf(ctx, conn, spec.DerivedFrom)
	if err != nil {
		return Version{}, err
	}
	required := domain.DerivedTruthClass(spec.TruthClass, inheritedClasses)
	if required != spec.TruthClass {
		return Version{}, fmt.Errorf(
			"%w: this version derives from a %s and must itself be a %s, not %s",
			ErrTruthClassStrengthened, domain.Scenario, required, spec.TruthClass)
	}

	var ordinal int
	err = conn.QueryRow(ctx,
		`SELECT coalesce(max(ordinal), 0) + 1 FROM layer.version WHERE layer_id = $1`,
		spec.LayerID).Scan(&ordinal)
	if err != nil {
		return Version{}, fmt.Errorf("numbering a version: %w", err)
	}

	id := ids.New(ids.KindVersion)
	_, err = conn.Exec(ctx, `
		INSERT INTO layer.version (
		    id, layer_id, ordinal, content_digest, truth_class,
		    crs_epsg, vertical_datum, extent,
		    observed_from, observed_to, clock_offset_seconds,
		    uncertainty_kind, uncertainty_value, uncertainty_note,
		    rights, attribution, visibility, supersedes_id,
		    producer_job_id, producer_principal_id, recipe_id, image_digest)
		VALUES (
		    $1, $2, $3, $4, $5::layer.truth_class,
		    $6, $7, ST_MakeEnvelope($8, $9, $10, $11, 4326)::geography,
		    $12, $13, $14,
		    $15::layer.uncertainty_kind, $16, $17,
		    $18, $19, $20::layer.visibility, $21,
		    $22, $23, $24, $25)`,
		id, spec.LayerID, ordinal, contentDigest.Bytes(), string(spec.TruthClass),
		int(spec.CRS), spec.VerticalDatum,
		spec.Extent.West, spec.Extent.South, spec.Extent.East, spec.Extent.North,
		spec.Time.From, spec.Time.To, spec.Time.ClockOffsetSeconds,
		string(spec.Uncertainty.Kind), spec.Uncertainty.Value, spec.Uncertainty.Note,
		spec.Rights, spec.Attribution, string(spec.Visibility), nullable(spec.SupersedesID),
		nullable(spec.ProducerJobID), nullable(spec.ProducerPrincipalID),
		spec.RecipeID, spec.ImageDigest)
	if err != nil {
		return Version{}, fmt.Errorf("recording a version: %w", err)
	}

	for _, file := range manifest {
		if _, err := conn.Exec(ctx,
			`INSERT INTO layer.version_object (version_id, relative_path, object_id)
			 VALUES ($1, $2, $3)`, id, file.RelativePath, file.ObjectID); err != nil {
			return Version{}, fmt.Errorf("recording %q in a version: %w", file.RelativePath, err)
		}
	}

	for _, input := range spec.DerivedFrom {
		if _, err := conn.Exec(ctx,
			`INSERT INTO layer.lineage (output_version_id, input_version_id) VALUES ($1, $2)`,
			id, input); err != nil {
			if message, raised := db.RaisedMessage(err); raised {
				return Version{}, fmt.Errorf("%w: %s", ErrTruthClassStrengthened, message)
			}
			return Version{}, fmt.Errorf("recording lineage: %w", err)
		}
	}

	return s.versionOn(ctx, conn, id)
}

func nullable(value string) *string {
	if value == "" {
		return nil
	}
	return &value
}

// resolveManifest reads each named object's true digest, size, and media type
// from the registry, so that a version's content digest is computed from what
// is actually stored rather than from what a caller said.
func (s *Store) resolveManifest(ctx context.Context, conn db.Conn, files []ManifestInput) ([]ManifestFile, error) {
	seen := make(map[string]struct{}, len(files))
	manifest := make([]ManifestFile, 0, len(files))
	for _, file := range files {
		if _, duplicate := seen[file.RelativePath]; duplicate {
			return nil, fmt.Errorf("%w: %q appears twice in one version",
				domain.ErrInvalid, file.RelativePath)
		}
		seen[file.RelativePath] = struct{}{}

		var (
			raw       []byte
			size      int64
			mediaType string
		)
		err := conn.QueryRow(ctx,
			`SELECT sha256, size_bytes, media_type FROM store.object WHERE id = $1`, file.ObjectID).
			Scan(&raw, &size, &mediaType)
		if errors.Is(db.Translate(err), db.ErrNotFound) {
			return nil, fmt.Errorf("%w: no stored object %q backs %q",
				domain.ErrInvalid, file.ObjectID, file.RelativePath)
		}
		if err != nil {
			return nil, fmt.Errorf("reading a stored object: %w", err)
		}
		digest, err := domain.DigestFromBytes(raw)
		if err != nil {
			return nil, err
		}
		manifest = append(manifest, ManifestFile{
			RelativePath: file.RelativePath,
			ObjectID:     file.ObjectID,
			SHA256:       digest.String(),
			SizeBytes:    size,
			MediaType:    mediaType,
		})
	}
	return manifest, nil
}

func (s *Store) truthClassesOf(ctx context.Context, conn db.Conn, versionIDs []string) ([]domain.TruthClass, error) {
	if len(versionIDs) == 0 {
		return nil, nil
	}
	rows, err := conn.Query(ctx,
		`SELECT id, truth_class FROM layer.version WHERE id = ANY($1)`, versionIDs)
	if err != nil {
		return nil, fmt.Errorf("reading input truth classes: %w", err)
	}
	defer rows.Close()

	found := make(map[string]domain.TruthClass, len(versionIDs))
	for rows.Next() {
		var id string
		var class domain.TruthClass
		if err := rows.Scan(&id, &class); err != nil {
			return nil, err
		}
		found[id] = class
	}
	if err := rows.Err(); err != nil {
		return nil, err
	}

	classes := make([]domain.TruthClass, 0, len(versionIDs))
	for _, id := range versionIDs {
		class, known := found[id]
		if !known {
			return nil, fmt.Errorf("%w: no version %q to derive from", domain.ErrInvalid, id)
		}
		classes = append(classes, class)
	}
	return classes, nil
}
