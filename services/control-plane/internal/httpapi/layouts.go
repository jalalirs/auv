package httpapi

import (
	"encoding/json"
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/catalog"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// Layouts — the arrangements somebody has made of a place.
//
// They hang off a city rather than standing on their own, because that is what
// they are: an arrangement of somewhere, whose things sit at depths resolved
// against that seabed and nowhere else. Whoever may read a place may read how
// it has been laid out, so these are authorised against the city rather than
// against a permission of their own.

type createLayoutRequest struct {
	Slug         string `json:"slug"`
	Name         string `json:"name"`
	Summary      string `json:"summary"`
	Discoverable bool   `json:"discoverable"`
}

// listLayouts gives the arrangements of one place.
func (d *Dependencies) listLayouts(w http.ResponseWriter, r *http.Request) {
	city := r.PathValue("cityId")
	found, err := d.Catalog.LayoutsOf(r.Context(), city)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"layouts": found})
}

// createLayout starts an arrangement of a place. Empty until a version of it
// is recorded: a layout is a name for a series of documents, the way a city is
// a name for a series of packages.
func (d *Dependencies) createLayout(w http.ResponseWriter, r *http.Request) {
	var request createLayoutRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	subject, _ := subjectOf(r.Context())
	var made catalog.Layout
	err := d.Database.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		made, err = d.Catalog.CreateLayout(r.Context(), conn, catalog.LayoutSpec{
			CityID:       r.PathValue("cityId"),
			Slug:         request.Slug,
			Name:         request.Name,
			Summary:      request.Summary,
			Discoverable: request.Discoverable,
			CreatedBy:    subject.PrincipalID,
		})
		return err
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, made)
}

// readLayout gives one arrangement.
func (d *Dependencies) readLayout(w http.ResponseWriter, r *http.Request) {
	found, err := d.Catalog.Layout(r.Context(), r.PathValue("layoutId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, found)
}

// listLayoutVersions gives what has been saved of one arrangement.
func (d *Dependencies) listLayoutVersions(w http.ResponseWriter, r *http.Request) {
	d.listVersionsOf(w, r, catalog.KindLayout, r.PathValue("layoutId"))
}

type saveLayoutRequest struct {
	Label    string          `json:"label"`
	Notes    string          `json:"notes"`
	Document json.RawMessage `json:"document"`
}

// saveLayout records what the editor drew, unpublished.
//
// Unpublished, like a package, and for the same reason: somebody saving a
// layout is part way through arranging a site, and a half-arranged one that a
// dive could already pin would be worse than none.
func (d *Dependencies) saveLayout(w http.ResponseWriter, r *http.Request) {
	var request saveLayoutRequest
	if err := readJSON(r, &request); err != nil {
		writeError(w, r, err)
		return
	}
	subject, _ := subjectOf(r.Context())
	var made catalog.Version
	err := d.Database.InTransaction(r.Context(), func(conn db.Conn) error {
		var err error
		made, err = d.Catalog.CreateDocumentVersion(r.Context(), conn, catalog.VersionSpec{
			AssetKind: catalog.KindLayout,
			AssetID:   r.PathValue("layoutId"),
			Label:     request.Label,
			Notes:     request.Notes,
			CreatedBy: subject.PrincipalID,
		}, request.Document)
		return err
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, made)
}

// registerLayouts declares the routes an arrangement needs.
func (rt *Router) registerLayouts() {
	d := rt.deps
	rt.register(Route{Method: "GET", Pattern: "/api/v1/cities/{cityId}/layouts",
		Summary: "how this place has been laid out", Action: policy.CityRead,
		Resource: fromPath(policy.ResourceCity, "cityId"), Handle: d.listLayouts})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/cities/{cityId}/layouts",
		Summary: "start an arrangement of this place", Action: policy.CityCreate,
		Resource: atPlatform(), Handle: d.createLayout})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/layouts/{layoutId}",
		Summary: "one arrangement", Action: policy.PlatformReadCatalogue,
		Resource: atPlatform(), Handle: d.readLayout})
	rt.register(Route{Method: "GET", Pattern: "/api/v1/layouts/{layoutId}/versions",
		Summary: "what has been saved of this arrangement",
		Action:   policy.PlatformReadCatalogue,
		Resource: atPlatform(), Handle: d.listLayoutVersions})
	rt.register(Route{Method: "POST", Pattern: "/api/v1/layouts/{layoutId}/versions",
		Summary: "save what the editor drew", Action: policy.CityCreate,
		Resource: atPlatform(), Handle: d.saveLayout})
}
