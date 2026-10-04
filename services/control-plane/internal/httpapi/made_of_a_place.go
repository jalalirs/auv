package httpapi

import (
	"context"
	"encoding/json"
	"net/http"

	"github.com/jalalirs/auv/services/control-plane/internal/catalog"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// What somebody has made of a place: a layout and a mission.
//
// A **layout** is an arrangement of a place — where the array was laid, where
// the ship holds, where the nursery frames are. A **mission** is a plan of
// work over one: an ordered list of stages, each pointing at something in that
// arrangement.
//
// They hang off a city rather than standing on their own, because that is what
// they are: things about somewhere, whose depths were resolved against that
// seabed and whose stages point at things drawn on it. Whoever may read a
// place may read what has been made of it, so both are authorised against the
// city rather than against a permission of their own.
//
// One set of handlers serves both. They differ in a noun and in what their
// document says, and two copies of five handlers would have been ten handlers
// to keep in step by hand.

type createMadeOfAPlaceRequest struct {
	Slug         string `json:"slug"`
	Name         string `json:"name"`
	Summary      string `json:"summary"`
	Discoverable bool   `json:"discoverable"`
}

type saveMadeOfAPlaceRequest struct {
	Label    string          `json:"label"`
	Notes    string          `json:"notes"`
	Document json.RawMessage `json:"document"`
}

// madeOfAPlace is one sort of thing made about a place, and what it is called
// in a URL, in a message and in the record.
type madeOfAPlace struct {
	kind   catalog.AssetKind
	path   string // the plural, as it appears in a route
	id     string // the path value naming one of them
	create func(context.Context, db.Conn, catalog.MadeOfAPlaceSpec) (catalog.MadeOfAPlace, error)
	read   func(context.Context, string) (catalog.MadeOfAPlace, error)
	ofCity func(context.Context, string) ([]catalog.MadeOfAPlace, error)
	retire func(context.Context, db.Conn, string) (catalog.MadeOfAPlace, error)
}

func (d *Dependencies) layoutsAre() madeOfAPlace {
	return madeOfAPlace{
		kind: catalog.KindLayout, path: "layouts", id: "layoutId",
		create: func(ctx context.Context, conn db.Conn, spec catalog.MadeOfAPlaceSpec) (catalog.MadeOfAPlace, error) {
			return d.Catalog.CreateLayout(ctx, conn, spec)
		},
		read:   d.Catalog.Layout,
		ofCity: d.Catalog.LayoutsOf,
		retire: d.Catalog.RetireLayout,
	}
}

func (d *Dependencies) missionsAre() madeOfAPlace {
	return madeOfAPlace{
		kind: catalog.KindMission, path: "missions", id: "missionId",
		create: func(ctx context.Context, conn db.Conn, spec catalog.MadeOfAPlaceSpec) (catalog.MadeOfAPlace, error) {
			return d.Catalog.CreateMission(ctx, conn, spec)
		},
		read:   d.Catalog.Mission,
		ofCity: d.Catalog.MissionsOf,
		retire: d.Catalog.RetireMission,
	}
}

// list gives what has been made of one place.
func (d *Dependencies) list(what madeOfAPlace) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		found, err := what.ofCity(r.Context(), r.PathValue("cityId"))
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, r, http.StatusOK, map[string]any{what.path: found})
	}
}

// start records one, empty until a version of it is saved: it is a name for a
// series of documents, the way a city is a name for a series of packages.
func (d *Dependencies) start(what madeOfAPlace) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var request createMadeOfAPlaceRequest
		if err := readJSON(r, &request); err != nil {
			writeError(w, r, err)
			return
		}
		subject, _ := subjectOf(r.Context())
		var made catalog.MadeOfAPlace
		err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
			var err error
			made, err = what.create(r.Context(), conn, catalog.MadeOfAPlaceSpec{
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
}

// read gives one of them.
func (d *Dependencies) read(what madeOfAPlace) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		found, err := what.read(r.Context(), r.PathValue(what.id))
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, r, http.StatusOK, found)
	}
}

// versions gives what has been saved of one of them.
func (d *Dependencies) versions(what madeOfAPlace) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		d.listVersionsOf(w, r, what.kind, r.PathValue(what.id))
	}
}

// save records a document, unpublished.
//
// Unpublished, like a package, and for the same reason: somebody saving one is
// part way through, and a half-arranged site or a half-written plan that a
// dive could already pin would be worse than none.

// cityOf names the place an arrangement belongs to, so that authority over it
// is authority over that place rather than over the installation.
//
// The layout's own id is in the path and its city is not, so this reads it.
// A resource a caller describes is a resource a caller can lie about, which is
// why the decision point loads what it needs itself.
func (d *Dependencies) cityOf(what madeOfAPlace) ResourceOf {
	return func(r *http.Request) (policy.Resource, error) {
		found, err := what.read(r.Context(), r.PathValue(what.id))
		if err != nil {
			return policy.Resource{}, err
		}
		return policy.City(found.CityID), nil
	}
}

// itsOwn refuses to save over somebody else's arrangement.
//
// This is what lets the role be viewer. Anybody who can look at a place can
// have their own scenarios over it — that is most of what a shared place is for
// — and what separates one person's plot from another's is who made it, not
// what they are allowed to do in general. A steward of the city may still
// curate anything on it.
//
// Refuses in the decision point's own terms rather than with an error of its
// own, so that the reason a person reads is written the way every other refusal
// on this platform is written.
func (d *Dependencies) itsOwn(r *http.Request, what madeOfAPlace) (policy.Decision, error) {
	found, err := what.read(r.Context(), r.PathValue(what.id))
	if err != nil {
		return policy.Decision{}, err
	}
	subject, _ := subjectOf(r.Context())
	if found.CreatedBy == subject.PrincipalID {
		return policy.Decision{Effect: policy.EffectAllow}, nil
	}
	// A steward of the place curates what is on it, including other people's.
	said, err := d.Authorizer.Decide(r.Context(), subject, policy.CityGrant,
		policy.City(found.CityID))
	if err != nil {
		return policy.Decision{}, err
	}
	if said.Effect == policy.EffectAllow {
		return said, nil
	}
	return policy.Decision{
		Effect: policy.EffectDenyVisible,
		Reason: "that arrangement is somebody else's; start your own of this place instead",
	}, nil
}

func (d *Dependencies) save(what madeOfAPlace) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		var request saveMadeOfAPlaceRequest
		if err := readJSON(r, &request); err != nil {
			writeError(w, r, err)
			return
		}
		mine, err := d.itsOwn(r, what)
		if err != nil {
			writeError(w, r, err)
			return
		}
		if mine.Effect != policy.EffectAllow {
			writeDenied(w, r, mine)
			return
		}
		subject, _ := subjectOf(r.Context())
		var made catalog.Version
		err = d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
			var err error
			made, err = d.Catalog.CreateDocumentVersion(r.Context(), conn, catalog.VersionSpec{
				AssetKind: what.kind,
				AssetID:   r.PathValue(what.id),
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
}

// archive takes one out of the listings, by its author or the place's
// steward, as saving a version of it is. Archived rather than deleted: a run
// that pinned a version of it must go on saying what it flew.
func (d *Dependencies) archive(what madeOfAPlace) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		mine, err := d.itsOwn(r, what)
		if err != nil {
			writeError(w, r, err)
			return
		}
		if mine.Effect != policy.EffectAllow {
			writeDenied(w, r, mine)
			return
		}
		var retired catalog.MadeOfAPlace
		err = d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
			var err error
			retired, err = what.retire(r.Context(), conn, r.PathValue(what.id))
			return err
		})
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, r, http.StatusOK, retired)
	}
}

// cost says what a plan of work takes, from the last time somebody flew it.
//
// From the record rather than from the arithmetic of its stages: a plan that
// has never been in the water has no cost to state, and the platform says so
// instead of guessing one.
func (d *Dependencies) missionCost(w http.ResponseWriter, r *http.Request) {
	// That the plan exists is asked first, and separately.
	//
	// What this costs is read from the runs flown against it, and a plan
	// nobody has flown has none — which is exactly what a plan that does not
	// exist has. So without this the platform answered for anything: a
	// deleted mission, a typo, the word "banana", all of them came back two
	// hundred with a working day of eight hours and nothing in it. A cost is
	// a statement about a thing, and the first duty of a statement about a
	// thing is that the thing is there.
	if _, err := d.Catalog.Mission(r.Context(), r.PathValue("missionId")); err != nil {
		writeError(w, r, err)
		return
	}
	found, err := d.Dives.WhatAMissionCosts(r.Context(), r.PathValue("missionId"))
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, found)
}

// registerMadeOfAPlace declares the five routes each of them needs.
func (rt *Router) registerMadeOfAPlace() {
	d := rt.deps
	for _, what := range []madeOfAPlace{d.layoutsAre(), d.missionsAre()} {
		noun := map[catalog.AssetKind]string{
			catalog.KindLayout:  "arrangement",
			catalog.KindMission: "plan of work",
		}[what.kind]
		rt.register(Route{Method: "GET", Pattern: "/api/v1/cities/{cityId}/" + what.path,
			Summary:  "what has been made of this place: every " + noun,
			Action:   policy.CityRead,
			Resource: fromPath(policy.ResourceCity, "cityId"), Handle: d.list(what)})
		rt.register(Route{Method: "POST", Pattern: "/api/v1/cities/{cityId}/" + what.path,
			Summary: "start a " + noun + " for this place", Action: policy.CityArrange,
			Resource: fromPath(policy.ResourceCity, "cityId"), Handle: d.start(what)})
		rt.register(Route{Method: "GET", Pattern: "/api/v1/" + what.path + "/{" + what.id + "}",
			Summary: "one " + noun, Action: policy.PlatformReadCatalogue,
			Resource: atPlatform(), Handle: d.read(what)})
		rt.register(Route{Method: "GET", Pattern: "/api/v1/" + what.path + "/{" + what.id + "}/versions",
			Summary:  "what has been saved of this " + noun,
			Action:   policy.PlatformReadCatalogue,
			Resource: atPlatform(), Handle: d.versions(what)})
		rt.register(Route{Method: "POST", Pattern: "/api/v1/" + what.path + "/{" + what.id + "}/versions",
			Summary: "save this " + noun, Action: policy.CityArrange,
			Resource: d.cityOf(what), Handle: d.save(what)})
		rt.register(Route{Method: "POST", Pattern: "/api/v1/" + what.path + "/{" + what.id + "}/archive",
			Summary: "archive this " + noun + ": out of the listings, kept in the record",
			Action:  policy.CityArrange, Resource: d.cityOf(what), Handle: d.archive(what)})
	}
	// And one only a plan of work has: what it costs.
	rt.register(Route{Method: "GET", Pattern: "/api/v1/missions/{missionId}/cost",
		Summary:  "what this plan of work takes, from the last time it was flown",
		Action:   policy.PlatformReadCatalogue,
		Resource: atPlatform(), Handle: d.missionCost})
}
