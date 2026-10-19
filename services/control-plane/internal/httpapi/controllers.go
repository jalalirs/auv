package httpapi

import (
	"errors"
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/controllerbuild"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// startControllerBuild asks for a controller to be built from its source.
func (d *Dependencies) startControllerBuild(w http.ResponseWriter, r *http.Request) {
	var brief controllerbuild.Brief
	if err := readJSON(r, &brief); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())
	d.answerControllerBuild(w, r, func() (controllerbuild.Build, error) {
		return d.Controllers.Start(r.Context(), principal.ID, r.PathValue("orgId"), brief)
	})
}

// againControllerBuild builds a controller's source again, which for a
// repository is its newest commit on the same branch: Pull latest.
func (d *Dependencies) againControllerBuild(w http.ResponseWriter, r *http.Request) {
	principal, _ := principalOf(r.Context())
	d.answerControllerBuild(w, r, func() (controllerbuild.Build, error) {
		return d.Controllers.Again(r.Context(), principal.ID, r.PathValue("buildId"))
	})
}

func (d *Dependencies) answerControllerBuild(w http.ResponseWriter, r *http.Request, start func() (controllerbuild.Build, error)) {
	build, err := start()
	if errors.Is(err, controllerbuild.ErrNotConfigured) {
		writeProblem(w, r, http.StatusServiceUnavailable, "not_configured", err.Error(), nil)
		return
	}
	if err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())
	if err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.DiveWrite),
			SubjectKind: "controller_build", SubjectID: build.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"orgId": build.OrgID, "jobId": build.JobID, "source": build.Brief.Source},
		})
	}); err != nil {
		writeError(w, r, err)
		return
	}
	view, err := d.Controllers.Watch(r.Context(), build.ID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, view)
}

// listControllerBuilds lists an institution's controller builds, newest
// first, each as somebody watching it sees it.
func (d *Dependencies) listControllerBuilds(w http.ResponseWriter, r *http.Request) {
	builds, err := d.Controllers.List(r.Context(), r.PathValue("orgId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	views := make([]controllerbuild.View, 0, len(builds))
	for _, one := range builds {
		view, err := d.Controllers.Watch(r.Context(), one.ID)
		if err != nil {
			writeError(w, r, err)
			return
		}
		views = append(views, view)
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"builds": views})
}

// watchControllerBuild says how a controller build is going.
func (d *Dependencies) watchControllerBuild(w http.ResponseWriter, r *http.Request) {
	view, err := d.Controllers.Watch(r.Context(), r.PathValue("buildId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, view)
}

// ofControllerBuild names the organisation a controller build belongs to.
func (d *Dependencies) ofControllerBuild(segment string) ResourceOf {
	return func(r *http.Request) (policy.Resource, error) {
		org, err := d.Controllers.OrgOf(r.Context(), r.PathValue(segment))
		if err != nil {
			return policy.Resource{}, err
		}
		return policy.Org(org), nil
	}
}
