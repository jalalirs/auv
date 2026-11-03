package httpapi

import (
	"errors"
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
	"github.com/jalalirs/auv/services/control-plane/internal/reconstructing"
)

// startAsset asks for a structure or a seabed survey to be made into an
// asset by the import job: from a file the organisation holds, or a
// pipeline's route.
func (d *Dependencies) startAsset(w http.ResponseWriter, r *http.Request) {
	var brief reconstructing.AssetBrief
	if err := readJSON(r, &brief); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())
	orgID := r.PathValue("orgId")
	made, err := d.Reconstructor.StartAsset(r.Context(), principal.ID, orgID, brief)
	if errors.Is(err, reconstructing.ErrNotConfigured) {
		writeProblem(w, r, http.StatusServiceUnavailable, "not_configured", err.Error(), nil)
		return
	}
	if err != nil {
		writeError(w, r, err)
		return
	}
	if err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.CityFound),
			SubjectKind: "asset", SubjectID: made.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"orgId": orgID, "jobId": made.JobID, "kind": made.Kind,
				"madeFrom": made.MadeFrom, "object": made.Asset.Object},
		})
	}); err != nil {
		writeError(w, r, err)
		return
	}
	view, err := d.Reconstructor.WatchAsset(r.Context(), made.ID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, view)
}

// listAssets lists an organisation's assets of every kind (or of the one
// asked for), newest first, each as the library shows it.
func (d *Dependencies) listAssets(w http.ResponseWriter, r *http.Request) {
	kind := r.URL.Query().Get("kind")
	switch kind {
	case "", reconstructing.KindReef, reconstructing.KindStructure, reconstructing.KindBathymetry:
	default:
		writeError(w, r, errors.Join(domain.ErrInvalid, errors.New("an asset is a reef, a structure or a bathymetry survey")))
		return
	}
	made, err := d.Reconstructor.ListAssets(r.Context(), r.PathValue("orgId"), kind)
	if err != nil {
		writeError(w, r, err)
		return
	}
	views := make([]reconstructing.AssetView, 0, len(made))
	for _, one := range made {
		view, err := d.Reconstructor.WatchAsset(r.Context(), one.ID)
		if err != nil {
			writeError(w, r, err)
			return
		}
		views = append(views, view)
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"assets": views})
}

// watchAsset says how an asset is going, and when it is ready, what it is.
// archiveAsset takes an asset out of its organisation's listings and says
// what it is now. Already archived is no error.
func (d *Dependencies) archiveAsset(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalOf(r.Context())
	id := r.PathValue("assetId")
	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		if err := d.Reconstructor.Archive(r.Context(), principal.ID, id); err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.CityFound),
			SubjectKind: "asset", SubjectID: id, Outcome: audit.Succeeded,
			Detail: map[string]any{"archived": true},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	view, err := d.Reconstructor.WatchAsset(r.Context(), id)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, view)
}

// offerAsset puts an asset in the store, or takes it out, and says what it
// is now.
func (d *Dependencies) offerAsset(on bool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		principal, _ := principalOf(r.Context())
		id := r.PathValue("assetId")
		err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
			if err := d.Reconstructor.Offer(r.Context(), id, on); err != nil {
				return err
			}
			return d.Audit.Record(r.Context(), conn, audit.Event{
				ActorID: principal.ID, Action: string(policy.CityFound),
				SubjectKind: "asset", SubjectID: id, Outcome: audit.Succeeded,
				Detail: map[string]any{"inStore": on},
			})
		})
		if err != nil {
			writeError(w, r, err)
			return
		}
		view, err := d.Reconstructor.WatchAsset(r.Context(), id)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, r, http.StatusOK, view)
	}
}

func (d *Dependencies) watchAsset(w http.ResponseWriter, r *http.Request) {
	view, err := d.Reconstructor.WatchAsset(r.Context(), r.PathValue("assetId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, view)
}

// storeObjects lists the objects iOcean offers in the store, as assets.
func (d *Dependencies) storeObjects(w http.ResponseWriter, r *http.Request) {
	made, err := d.Reconstructor.InStore(r.Context())
	if err != nil {
		writeError(w, r, err)
		return
	}
	views := make([]reconstructing.AssetView, 0, len(made))
	for _, one := range made {
		view, err := d.Reconstructor.WatchAsset(r.Context(), one.ID)
		if err != nil {
			writeError(w, r, err)
			return
		}
		views = append(views, view)
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"assets": views})
}

// copyStoreObject copies an object from the store into an organisation's
// objects and says what the copy is.
func (d *Dependencies) copyStoreObject(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalOf(r.Context())
	orgID, from := r.PathValue("orgId"), r.PathValue("assetId")
	made, err := d.Reconstructor.Copy(r.Context(), principal.ID, orgID, from)
	if err != nil {
		writeError(w, r, err)
		return
	}
	if err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.CityFound),
			SubjectKind: "asset", SubjectID: made, Outcome: audit.Succeeded,
			Detail: map[string]any{"orgId": orgID, "copiedFrom": from},
		})
	}); err != nil {
		writeError(w, r, err)
		return
	}
	view, err := d.Reconstructor.WatchAsset(r.Context(), made)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, view)
}
