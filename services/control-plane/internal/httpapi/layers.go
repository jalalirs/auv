package httpapi

import (
	"context"
	"net/http"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/layer"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
	"github.com/jalalirs/auv/services/control-plane/internal/storage"
)

// listLayers lists the layers of a scope that hold something the caller may
// see. The filter comes from the decision point; this only applies it.
func (d *Dependencies) listLayers(scope domain.ScopeKind) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		cityID := r.PathValue("cityId")
		if scope == domain.PlatformScope {
			cityID = ""
		}
		layers, err := d.Layers.InScope(r.Context(), scope, cityID, decisionOf(r.Context()).Visible)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, r, http.StatusOK, map[string]any{"layers": layers})
	}
}

type createLayerRequest struct {
	Slug            string `json:"slug"`
	Kind            string `json:"kind"`
	Title           string `json:"title"`
	Description     string `json:"description"`
	AttributedOrgID string `json:"attributedOrgId"`
}

// createLayer adds a layer to a scope. It is contained by that scope and
// attributed to the organisation the caller named, which must be one the
// caller may act for.
func (d *Dependencies) createLayer(scope domain.ScopeKind) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var request createLayerRequest
		if err := readJSON(r, &request); err != nil {
			writeError(w, r, err)
			return
		}
		if !d.requireOrg(w, r, request.AttributedOrgID) {
			return
		}
		principal, _ := principalOf(r.Context())

		kind, err := domain.ParseLayerKind(request.Kind)
		if err != nil {
			writeError(w, r, err)
			return
		}
		cityID := r.PathValue("cityId")
		if scope == domain.PlatformScope {
			cityID = ""
		}

		var created layer.Layer
		err = d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
			var err error
			created, err = d.Layers.Create(r.Context(), conn, layer.CreateSpec{
				ScopeKind:       scope,
				CityID:          cityID,
				Slug:            request.Slug,
				Kind:            kind,
				Title:           request.Title,
				Description:     request.Description,
				AttributedOrgID: request.AttributedOrgID,
				CreatedBy:       principal.ID,
			})
			if err != nil {
				return err
			}
			return d.Audit.Record(r.Context(), conn, audit.Event{
				ActorID: principal.ID, Action: string(policy.LayerCreate),
				SubjectKind: "layer", SubjectID: created.ID, Outcome: audit.Succeeded,
				Detail: map[string]any{"scope": string(scope), "cityId": cityID, "slug": created.Slug},
			})
		})
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, r, http.StatusCreated, created)
	}
}

// readLayer reads one layer together with the versions the caller may see.
func (d *Dependencies) readLayer(w http.ResponseWriter, r *http.Request) {
	layerID := r.PathValue("layerId")
	record, err := d.Layers.Layer(r.Context(), layerID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	versions, err := d.Layers.Versions(r.Context(), layerID, decisionOf(r.Context()).Visible)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"layer": record, "versions": versions})
}

type uncertaintyRequest struct {
	Kind  string   `json:"kind"`
	Value *float64 `json:"value,omitempty"`
	Note  string   `json:"note,omitempty"`
}

type createVersionRequest struct {
	TruthClass    string        `json:"truthClass"`
	CRSEpsg       int           `json:"crsEpsg"`
	VerticalDatum string        `json:"verticalDatum"`
	Extent        domain.Extent `json:"extent"`

	ObservedFrom       time.Time `json:"observedFrom"`
	ObservedTo         time.Time `json:"observedTo"`
	ClockOffsetSeconds *float64  `json:"clockOffsetSeconds,omitempty"`

	Uncertainty uncertaintyRequest `json:"uncertainty"`
	Rights      string             `json:"rights"`
	Attribution string             `json:"attribution"`
	Visibility  string             `json:"visibility"`

	Files []struct {
		RelativePath string `json:"relativePath"`
		ObjectID     string `json:"objectId"`
	} `json:"files"`
	DerivedFrom  []string `json:"derivedFrom,omitempty"`
	SupersedesID string   `json:"supersedesId,omitempty"`
}

// createVersion records evidence against a layer.
//
// Everything a version must state is required here: a coordinate reference, a
// vertical datum, a time basis, rights, attribution, and an uncertainty — of
// which "unknown" is a legal answer and absence is not.
func (d *Dependencies) createVersion(w http.ResponseWriter, r *http.Request) {
	var request createVersionRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())
	layerID := r.PathValue("layerId")

	truthClass, err := domain.ParseTruthClass(request.TruthClass)
	if err != nil {
		writeError(w, r, err)
		return
	}
	visibility := domain.Visibility(request.Visibility)
	if visibility == "" {
		// A contribution is restricted until a steward decides otherwise.
		visibility = domain.Restricted
	}

	files := make([]layer.ManifestInput, 0, len(request.Files))
	for _, file := range request.Files {
		files = append(files, layer.ManifestInput{
			RelativePath: file.RelativePath, ObjectID: file.ObjectID,
		})
	}

	spec := layer.VersionSpec{
		LayerID:       layerID,
		TruthClass:    truthClass,
		CRS:           domain.CoordinateReference(request.CRSEpsg),
		VerticalDatum: request.VerticalDatum,
		Extent:        request.Extent,
		Time: domain.TimeBasis{
			From:               request.ObservedFrom,
			To:                 request.ObservedTo,
			ClockOffsetSeconds: request.ClockOffsetSeconds,
		},
		Uncertainty: domain.Uncertainty{
			Kind:  domain.UncertaintyKind(request.Uncertainty.Kind),
			Value: request.Uncertainty.Value,
			Note:  request.Uncertainty.Note,
		},
		Rights:              request.Rights,
		Attribution:         request.Attribution,
		Visibility:          visibility,
		Files:               files,
		DerivedFrom:         request.DerivedFrom,
		SupersedesID:        request.SupersedesID,
		ProducerPrincipalID: principal.ID,
	}

	var created layer.Version
	err = d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		created, err = d.Layers.CreateVersion(r.Context(), conn, spec)
		if err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.LayerCreate),
			SubjectKind: "version", SubjectID: created.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{
				"layerId": layerID, "ordinal": created.Ordinal,
				"truthClass": string(created.TruthClass), "contentDigest": created.ContentDigest,
			},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, created)
}

// readVersion reads one version, if the caller may see it.
func (d *Dependencies) readVersion(w http.ResponseWriter, r *http.Request) {
	record, err := d.Layers.Version(r.Context(), r.PathValue("versionId"), decisionOf(r.Context()).Visible)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{
		"version": record,
		"uncertainty": map[string]any{
			"kind": record.Uncertainty.Kind, "value": record.Uncertainty.Value,
			"note": record.Uncertainty.Note,
		},
	})
}

// readLineage reports what a version was derived from, which is what makes a
// claim traceable to the material behind it.
func (d *Dependencies) readLineage(w http.ResponseWriter, r *http.Request) {
	inputs, err := d.Layers.Lineage(r.Context(), r.PathValue("versionId"), decisionOf(r.Context()).Visible)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"derivedFrom": inputs})
}

// publicationStep performs one step of a version's publication lifecycle and
// records that it happened.
type publicationStep func(ctx context.Context, conn db.Conn, versionID, reason string) (layer.Version, error)

// versionStep turns a publication step into a route handler, so that submit,
// publish, promote, and retract share one path through validation, the
// transaction, and the audit record.
func (d *Dependencies) versionStep(action policy.Action, step publicationStep, needsReason bool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		principal, _ := principalOf(r.Context())
		versionID := r.PathValue("versionId")

		reason := ""
		if needsReason {
			var request struct {
				Reason string `json:"reason"`
			}
			if err := readJSON(r, &request); err != nil {
				writeError(w, r, err)
				return
			}
			reason = request.Reason
		}

		var updated layer.Version
		err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
			var err error
			updated, err = step(r.Context(), conn, versionID, reason)
			if err != nil {
				return err
			}
			detail := map[string]any{
				"layerId": updated.LayerID, "ordinal": updated.Ordinal,
				"state": string(updated.State), "visibility": string(updated.Visibility),
			}
			if reason != "" {
				detail["reason"] = reason
			}
			return d.Audit.Record(r.Context(), conn, audit.Event{
				ActorID: principal.ID, Action: string(action),
				SubjectKind: "version", SubjectID: versionID, Outcome: audit.Succeeded,
				Detail: detail,
			})
		})
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, r, http.StatusOK, updated)
	}
}

// readVersionFile issues a short-lived URL to read one file of a version.
//
// Access to bytes follows access to the evidence that contains them: the file
// is found through its version, so a caller who may not see the version cannot
// reach its bytes by knowing an object identifier.
func (d *Dependencies) readVersionFile(w http.ResponseWriter, r *http.Request) {
	version, err := d.Layers.Version(r.Context(), r.PathValue("versionId"), decisionOf(r.Context()).Visible)
	if err != nil {
		writeError(w, r, err)
		return
	}

	wanted := r.PathValue("path")
	for _, file := range version.Manifest {
		if file.RelativePath != wanted {
			continue
		}
		object, err := d.Objects.Object(r.Context(), file.ObjectID)
		if err != nil {
			writeError(w, r, err)
			return
		}
		url, err := d.Objects.ReadURL(r.Context(), object, file.RelativePath, storage.External)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, r, http.StatusOK, map[string]any{
			"file": file, "readUrl": url,
		})
		return
	}
	writeProblem(w, r, http.StatusNotFound, "not_found",
		"this version contains no file at that path", nil)
}
