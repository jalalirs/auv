package httpapi

import (
	"errors"
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
	"github.com/jalalirs/auv/services/control-plane/internal/reconstructing"
	"github.com/jalalirs/auv/services/control-plane/internal/storage"
)

// startReconstruction asks for a reef to be made from a dive video the
// organisation holds.
func (d *Dependencies) startReconstruction(w http.ResponseWriter, r *http.Request) {
	var brief reconstructing.Brief
	if err := readJSON(r, &brief); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())
	orgID := r.PathValue("orgId")
	made, err := d.Reconstructor.Start(r.Context(), principal.ID, orgID, brief)
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
			SubjectKind: "reconstruction", SubjectID: made.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"orgId": orgID, "jobId": made.JobID, "video": made.Brief.Video.ObjectID},
		})
	}); err != nil {
		writeError(w, r, err)
		return
	}
	view, err := d.Reconstructor.Watch(r.Context(), made.ID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, view)
}

// listReconstructions lists an organisation's reconstructions, newest first,
// each as somebody watching it would see it.
func (d *Dependencies) listReconstructions(w http.ResponseWriter, r *http.Request) {
	made, err := d.Reconstructor.List(r.Context(), r.PathValue("orgId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	views := make([]reconstructing.View, 0, len(made))
	for _, one := range made {
		view, err := d.Reconstructor.Watch(r.Context(), one.ID)
		if err != nil {
			writeError(w, r, err)
			return
		}
		views = append(views, view)
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"reconstructions": views})
}

// watchReconstruction says how a reconstruction is going: the steps it has
// reported, and when it is done, what it says about the reef it made.
func (d *Dependencies) watchReconstruction(w http.ResponseWriter, r *http.Request) {
	view, err := d.Reconstructor.Watch(r.Context(), r.PathValue("reconstructionId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, view)
}

// reconstructionObjects lists the files a reconstruction made, each with a
// short-lived URL to fetch its bytes, signed for whoever asked.
func (d *Dependencies) reconstructionObjects(w http.ResponseWriter, r *http.Request) {
	objects, err := d.Reconstructor.Objects(r.Context(), r.PathValue("reconstructionId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	type fetchable struct {
		reconstructing.Object
		URL string `json:"url"`
	}
	answer := make([]fetchable, 0, len(objects))
	for _, one := range objects {
		object, err := d.Objects.Object(r.Context(), one.ObjectID)
		if err != nil {
			writeError(w, r, err)
			return
		}
		url, err := d.Objects.ReadURL(r.Context(), object, one.Path, storage.External)
		if err != nil {
			writeError(w, r, err)
			return
		}
		answer = append(answer, fetchable{Object: one, URL: url})
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"objects": answer})
}

// ofReconstruction names the organisation a reconstruction belongs to, which
// is who may see it.
func (d *Dependencies) ofReconstruction(segment string) ResourceOf {
	return func(r *http.Request) (policy.Resource, error) {
		org, err := d.Reconstructor.OrgOf(r.Context(), r.PathValue(segment))
		if err != nil {
			return policy.Resource{}, err
		}
		return policy.Org(org), nil
	}
}
