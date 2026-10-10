package httpapi

import (
	"errors"
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/building"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

type startBuildRequest struct {
	building.Brief
	// OrgID is the organisation the work is for, when the place belongs to
	// none (the platform's catalogue). A place an organisation owns is
	// always built for it.
	OrgID string `json:"orgId,omitempty"`
}

// startBuild asks for a place to be built from its data.
func (d *Dependencies) startBuild(w http.ResponseWriter, r *http.Request) {
	var request startBuildRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())
	subject, _ := subjectOf(r.Context())
	city, err := d.Catalog.City(r.Context(), r.PathValue("cityId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	orgID := city.OwnedByOrg
	if orgID == "" {
		orgID = request.OrgID
		if orgID == "" || !subject.InOrg(orgID) {
			writeError(w, r, errors.Join(domain.ErrInvalid,
				errors.New("say which of your organisations the build is for (orgId)")))
			return
		}
	}
	build, err := d.Builder.Start(r.Context(), principal.ID, orgID, city, request.Brief)
	if errors.Is(err, building.ErrNotConfigured) {
		writeProblem(w, r, http.StatusServiceUnavailable, "not_configured", err.Error(), nil)
		return
	}
	if err != nil {
		writeError(w, r, err)
		return
	}
	if err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.CityPublish),
			SubjectKind: "build", SubjectID: build.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"cityId": city.ID, "jobId": build.JobID, "orgId": orgID},
		})
	}); err != nil {
		writeError(w, r, err)
		return
	}
	view, err := d.Builder.Watch(r.Context(), build.ID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusAccepted, view)
}

// listBuilds lists a place's builds, newest first.
func (d *Dependencies) listBuilds(w http.ResponseWriter, r *http.Request) {
	builds, err := d.Builder.Builds(r.Context(), r.PathValue("cityId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"builds": builds})
}

// watchBuild says how a build is going: the steps it has reported, and when
// it is done, the version it made and where that place is weak.
func (d *Dependencies) watchBuild(w http.ResponseWriter, r *http.Request) {
	view, err := d.Builder.Watch(r.Context(), r.PathValue("buildId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, view)
}

// buildSources lists what a build can be made from.
func (d *Dependencies) buildSources(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, r, http.StatusOK, map[string]any{"sources": building.Sources, "fileUses": building.FileUses})
}

// ofBuild names the place a build is of.
func (d *Dependencies) ofBuild(segment string) ResourceOf {
	return func(r *http.Request) (policy.Resource, error) {
		city, err := d.Builder.CityOf(r.Context(), r.PathValue(segment))
		if err != nil {
			return policy.Resource{}, err
		}
		return policy.City(city), nil
	}
}
