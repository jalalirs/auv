// Package publication turns what a job produced into evidence.
//
// A job writes a file describing its result; it holds no credential and reaches
// no route. When the job succeeds, this reads that file, checks it, and creates
// the layer version — recording the job as the producer, with the recipe and
// the image digest that ran. See ADR-0013.
//
// This is what lets the daily loop be a heartbeat rather than a queue of chores.
package publication

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/layer"
	"github.com/jalalirs/auv/services/control-plane/internal/storage"
)

// maxDescriptorBytes bounds what will be read and parsed. A descriptor states a
// few dozen facts; anything larger is a mistake or an attempt.
const maxDescriptorBytes = 256 << 10

// ErrDescriptor reports a result the platform cannot turn into evidence.
var ErrDescriptor = errors.New("this job's result does not describe itself usably")

// Descriptor is what a job writes to say what it produced.
//
// Everything a version must state appears here, because a version that does not
// state it is not evidence. The platform validates it exactly as it validates a
// version a person records: a job gets no easier path.
type Descriptor struct {
	TruthClass    string        `json:"truthClass"`
	CRSEpsg       int           `json:"crsEpsg"`
	VerticalDatum string        `json:"verticalDatum"`
	Extent        domain.Extent `json:"extent"`

	ObservedFrom       time.Time `json:"observedFrom"`
	ObservedTo         time.Time `json:"observedTo"`
	ClockOffsetSeconds *float64  `json:"clockOffsetSeconds,omitempty"`

	Uncertainty struct {
		Kind  string   `json:"kind"`
		Value *float64 `json:"value,omitempty"`
		Note  string   `json:"note,omitempty"`
	} `json:"uncertainty"`

	Rights      string `json:"rights"`
	Attribution string `json:"attribution"`
}

// Publisher materialises the results of finished work.
type Publisher struct {
	pool    *db.Pool
	layers  *layer.Store
	objects *storage.Objects
	audit   *audit.Recorder
}

// New builds the publisher.
func New(pool *db.Pool, layers *layer.Store, objects *storage.Objects, recorder *audit.Recorder) *Publisher {
	return &Publisher{pool: pool, layers: layers, objects: objects, audit: recorder}
}

// declaration is what the job was submitted to publish.
type declaration struct {
	JobID             string
	LayerID           string
	DescriptorOutput  string
	Publish           bool
	Promote           bool
	SupersedePrevious bool
	Materialised      bool
}

// Materialise turns a succeeded job's result into a layer version.
//
// It is idempotent: a job that has already produced a version produces no
// second one, whatever calls this and however often. That matters because both
// the worker's completion report and a background sweep call it.
func (p *Publisher) Materialise(ctx context.Context, jobID string) (layer.Version, bool, error) {
	declared, err := p.declarationFor(ctx, jobID)
	if errors.Is(err, db.ErrNotFound) {
		// Most jobs publish nothing. That is not a failure.
		return layer.Version{}, false, nil
	}
	if err != nil {
		return layer.Version{}, false, err
	}
	if declared.Materialised {
		return layer.Version{}, false, nil
	}

	var (
		state       string
		recipeID    string
		imageDigest string
		submittedBy string
		rawOutputs  []byte
	)
	if err := p.pool.QueryRow(ctx, `
		SELECT state, recipe_id, image_digest, submitted_by, outputs
		FROM exec.job WHERE id = $1`, jobID).
		Scan(&state, &recipeID, &imageDigest, &submittedBy, &rawOutputs); err != nil {
		return layer.Version{}, false, db.Translate(err)
	}
	if state != "succeeded" {
		// Only work that finished well produces evidence.
		return layer.Version{}, false, nil
	}

	var declaredOutputs []struct {
		Name         string `json:"name"`
		RelativePath string `json:"relativePath"`
	}
	if err := json.Unmarshal(rawOutputs, &declaredOutputs); err != nil {
		return layer.Version{}, false, fmt.Errorf("reading what this job declared: %w", err)
	}

	produced, err := p.producedObjects(ctx, jobID)
	if err != nil {
		return layer.Version{}, false, err
	}

	descriptorID, present := produced[declared.DescriptorOutput]
	if !present {
		return layer.Version{}, false, fmt.Errorf(
			"%w: it produced no output named %q", ErrDescriptor, declared.DescriptorOutput)
	}
	descriptor, err := p.readDescriptor(ctx, descriptorID)
	if err != nil {
		return layer.Version{}, false, err
	}

	// Every declared output but the descriptor is the payload, at the path the
	// job declared for it. Nothing else the job wrote is included, because
	// nothing else was declared.
	var payload []layer.ManifestInput
	for _, output := range declaredOutputs {
		if output.Name == declared.DescriptorOutput {
			continue
		}
		objectID, produced := produced[output.Name]
		if !produced {
			return layer.Version{}, false, fmt.Errorf(
				"%w: it declared output %q and produced nothing for it", ErrDescriptor, output.Name)
		}
		payload = append(payload, layer.ManifestInput{
			RelativePath: output.RelativePath, ObjectID: objectID,
		})
	}

	spec, err := descriptor.toVersionSpec(declared.LayerID, jobID, recipeID, imageDigest)
	if err != nil {
		return layer.Version{}, false, err
	}
	spec.Files = payload

	var version layer.Version
	err = p.pool.InTransaction(ctx, func(conn db.Conn) error {
		if declared.SupersedePrevious {
			var previous string
			err := conn.QueryRow(ctx, `
				SELECT id FROM layer.version
				WHERE layer_id = $1 AND state = 'published'
				ORDER BY ordinal DESC LIMIT 1`, declared.LayerID).Scan(&previous)
			if err != nil && !errors.Is(db.Translate(err), db.ErrNotFound) {
				return fmt.Errorf("looking for the version this supersedes: %w", err)
			}
			spec.SupersedesID = previous
		}

		version, err = p.layers.CreateVersion(ctx, conn, spec)
		if err != nil {
			return err
		}
		if declared.Publish {
			version, err = p.layers.Publish(ctx, conn, version.ID)
			if err != nil {
				return err
			}
		}
		if declared.Promote {
			version, err = p.layers.Promote(ctx, conn, version.ID)
			if err != nil {
				return err
			}
		}

		if _, err := conn.Exec(ctx, `
			UPDATE exec.publication SET version_id = $2, materialised_at = now()
			WHERE job_id = $1 AND version_id IS NULL`, jobID, version.ID); err != nil {
			return fmt.Errorf("recording what this job published: %w", err)
		}

		return p.audit.Record(ctx, conn, audit.Event{
			// The submitter is the actor: this is the result of what they asked
			// for, produced without anyone present.
			ActorID: submittedBy, Action: "layer.publish_from_job",
			SubjectKind: "version", SubjectID: version.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{
				"jobId": jobID, "layerId": declared.LayerID,
				"recipeId": recipeID, "imageDigest": imageDigest,
				"truthClass": string(version.TruthClass),
				"state":      string(version.State),
				"visibility": string(version.Visibility),
			},
		})
	})
	if err != nil {
		return layer.Version{}, false, err
	}
	return version, true, nil
}

// MaterialisePending finishes any publication whose job succeeded but whose
// version was never created — because the process ended between the two, or
// because storage was briefly unreachable. It reports how many it completed.
func (p *Publisher) MaterialisePending(ctx context.Context) (int, error) {
	rows, err := p.pool.Query(ctx, `
		SELECT p.job_id
		FROM exec.publication p
		JOIN exec.job j ON j.id = p.job_id
		WHERE p.materialised_at IS NULL AND j.state = 'succeeded'
		ORDER BY j.terminal_at
		LIMIT 50`)
	if err != nil {
		return 0, fmt.Errorf("looking for results that were never published: %w", err)
	}
	var pending []string
	for rows.Next() {
		var jobID string
		if err := rows.Scan(&jobID); err != nil {
			rows.Close()
			return 0, err
		}
		pending = append(pending, jobID)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return 0, err
	}

	published := 0
	for _, jobID := range pending {
		if _, created, err := p.Materialise(ctx, jobID); err != nil {
			return published, fmt.Errorf("publishing the result of %s: %w", jobID, err)
		} else if created {
			published++
		}
	}
	return published, nil
}

func (p *Publisher) declarationFor(ctx context.Context, jobID string) (declaration, error) {
	var declared declaration
	var materialisedAt *time.Time
	err := p.pool.QueryRow(ctx, `
		SELECT job_id, layer_id, descriptor_output, publish, promote, supersede_previous, materialised_at
		FROM exec.publication WHERE job_id = $1`, jobID).
		Scan(&declared.JobID, &declared.LayerID, &declared.DescriptorOutput,
			&declared.Publish, &declared.Promote, &declared.SupersedePrevious, &materialisedAt)
	if err != nil {
		return declaration{}, db.Translate(err)
	}
	declared.Materialised = materialisedAt != nil
	return declared, nil
}

func (p *Publisher) producedObjects(ctx context.Context, jobID string) (map[string]string, error) {
	rows, err := p.pool.Query(ctx,
		`SELECT name, object_id FROM exec.job_output WHERE job_id = $1`, jobID)
	if err != nil {
		return nil, fmt.Errorf("reading what this job produced: %w", err)
	}
	defer rows.Close()

	produced := map[string]string{}
	for rows.Next() {
		var name, objectID string
		if err := rows.Scan(&name, &objectID); err != nil {
			return nil, err
		}
		produced[name] = objectID
	}
	return produced, rows.Err()
}

func (p *Publisher) readDescriptor(ctx context.Context, objectID string) (Descriptor, error) {
	object, err := p.objects.Object(ctx, objectID)
	if err != nil {
		return Descriptor{}, err
	}
	if object.SizeBytes > maxDescriptorBytes {
		return Descriptor{}, fmt.Errorf(
			"%w: its description is %d bytes, beyond the %d a description needs",
			ErrDescriptor, object.SizeBytes, maxDescriptorBytes)
	}

	body, err := p.objects.Open(ctx, object)
	if err != nil {
		return Descriptor{}, err
	}
	defer body.Close()

	raw, err := io.ReadAll(io.LimitReader(body, maxDescriptorBytes))
	if err != nil {
		return Descriptor{}, fmt.Errorf("reading this job's description of its result: %w", err)
	}

	var descriptor Descriptor
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&descriptor); err != nil {
		return Descriptor{}, fmt.Errorf("%w: %s", ErrDescriptor, err)
	}
	return descriptor, nil
}

// toVersionSpec turns a description into the same specification a person's
// contribution goes through, so that a job's result is validated identically.
func (d Descriptor) toVersionSpec(layerID, jobID, recipeID, imageDigest string) (layer.VersionSpec, error) {
	truthClass, err := domain.ParseTruthClass(d.TruthClass)
	if err != nil {
		return layer.VersionSpec{}, fmt.Errorf("%w: %s", ErrDescriptor, err)
	}
	uncertainty := domain.Uncertainty{
		Kind:  domain.UncertaintyKind(d.Uncertainty.Kind),
		Value: d.Uncertainty.Value,
		Note:  d.Uncertainty.Note,
	}
	if err := uncertainty.Validate(); err != nil {
		return layer.VersionSpec{}, fmt.Errorf("%w: %s", ErrDescriptor, err)
	}

	return layer.VersionSpec{
		LayerID:       layerID,
		TruthClass:    truthClass,
		CRS:           domain.CoordinateReference(d.CRSEpsg),
		VerticalDatum: d.VerticalDatum,
		Extent:        d.Extent,
		Time: domain.TimeBasis{
			From:               d.ObservedFrom,
			To:                 d.ObservedTo,
			ClockOffsetSeconds: d.ClockOffsetSeconds,
		},
		Uncertainty: uncertainty,
		Rights:      d.Rights,
		Attribution: d.Attribution,
		// Ingested evidence is restricted until it is promoted, exactly like a
		// person's contribution. The declaration decides whether that happens.
		Visibility:    domain.Restricted,
		ProducerJobID: jobID,
		RecipeID:      recipeID,
		ImageDigest:   imageDigest,
	}, nil
}
