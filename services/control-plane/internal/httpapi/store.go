package httpapi

import (
	"errors"
	"fmt"
	"net/http"
	"strconv"
	"strings"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/catalog"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
	"github.com/jalalirs/auv/services/control-plane/internal/mapstore"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// storePlaces lists the map store, each place as a card shows it. Given
// ?near=lat,lon&acrossM=N, only the places that overlap that area, nearest
// first, which is how somebody about to build a place is told that iOcean
// already has it.
func (d *Dependencies) storePlaces(w http.ResponseWriter, r *http.Request) {
	near, err := squareOf(r)
	if err != nil {
		writeError(w, r, err)
		return
	}
	subject, _ := subjectOf(r.Context())
	places, err := d.MapStore.Places(r.Context(), subject.OrgIDs, near)
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusOK, map[string]any{"places": places})
}

// squareOf reads the area a store listing is asked about, if any.
func squareOf(r *http.Request) (*mapstore.Square, error) {
	raw := r.URL.Query().Get("near")
	if raw == "" {
		return nil, nil
	}
	refused := errors.Join(domain.ErrInvalid, errors.New("near is latitude,longitude in degrees, and acrossM metres"))
	lat, lon, ok := strings.Cut(raw, ",")
	if !ok {
		return nil, refused
	}
	square := mapstore.Square{AcrossM: 1000}
	var err error
	if square.Lat, err = strconv.ParseFloat(strings.TrimSpace(lat), 64); err != nil || square.Lat < -90 || square.Lat > 90 {
		return nil, refused
	}
	if square.Lon, err = strconv.ParseFloat(strings.TrimSpace(lon), 64); err != nil || square.Lon < -180 || square.Lon > 180 {
		return nil, refused
	}
	if across := r.URL.Query().Get("acrossM"); across != "" {
		if square.AcrossM, err = strconv.ParseFloat(across, 64); err != nil || square.AcrossM <= 0 || square.AcrossM > 200000 {
			return nil, refused
		}
	}
	return &square, nil
}

// adoptStorePlace adds a place from the map store to an organisation's
// places: a share like any other, marked as taken from the store. Taking one
// already taken changes nothing.
func (d *Dependencies) adoptStorePlace(w http.ResponseWriter, r *http.Request) {
	orgID, cityID := r.PathValue("orgId"), r.PathValue("cityId")
	if !d.inStore(w, r, cityID) {
		return
	}
	// An organisation's place in the store is copied: sharing it in place
	// would hand another organisation the owner's own place.
	if city, err := d.Catalog.City(r.Context(), cityID); err != nil || city.OwnedByOrg != "" {
		if err == nil {
			err = fmt.Errorf("%w: %s is an organisation's place; copy it instead", domain.ErrInvalid, city.Name)
		}
		writeError(w, r, err)
		return
	}
	principal, _ := principalOf(r.Context())
	binding, err := d.recordGrant(r, policy.CityAdopt, "city", policy.GrantSpec{
		SubjectKind: policy.SubjectOrg, SubjectID: orgID,
		ScopeKind: policy.ScopeCity, ScopeID: cityID,
		Role: policy.RoleViewer, CreatedBy: principal.ID, Via: policy.GrantedViaStore,
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, binding)
}

// unadoptStorePlace lets go of a place an organisation took from the map
// store. Only what taking it gave is withdrawn: a share somebody granted on
// purpose stays.
func (d *Dependencies) unadoptStorePlace(w http.ResponseWriter, r *http.Request) {
	orgID, cityID := r.PathValue("orgId"), r.PathValue("cityId")
	principal, _ := principalOf(r.Context())
	err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		revoked, err := d.Authorizer.RevokeVia(r.Context(), conn, policy.SubjectOrg, orgID,
			policy.ScopeCity, cityID, policy.GrantedViaStore)
		if err != nil {
			return err
		}
		if revoked == 0 {
			return fmt.Errorf("%w: the organisation did not take %s from the map store", db.ErrNotFound, cityID)
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.CityAdopt),
			SubjectKind: "city", SubjectID: cityID, Outcome: audit.Succeeded,
			Detail: map[string]any{"orgId": orgID, "revoked": revoked, "via": policy.GrantedViaStore},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

// inStore refuses a place that is not in the map store, as absent: a place an
// organisation owns is not somebody else's to learn of by asking.
func (d *Dependencies) inStore(w http.ResponseWriter, r *http.Request, cityID string) bool {
	city, err := d.Catalog.City(r.Context(), cityID)
	if err == nil && !mapstore.Listed(city) {
		err = db.ErrNotFound
	}
	if err != nil {
		writeError(w, r, err)
		return false
	}
	return true
}

// copyStorePlace copies a place from the map store into an organisation: a
// new place it owns, whose first version holds the store place's newest
// published files. The store's place never changes, and taking it again
// makes another copy.
func (d *Dependencies) copyStorePlace(w http.ResponseWriter, r *http.Request) {
	orgID, cityID := r.PathValue("orgId"), r.PathValue("cityId")
	if !d.inStore(w, r, cityID) {
		return
	}
	principal, _ := principalOf(r.Context())
	source, err := d.Catalog.City(r.Context(), cityID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	versions, err := d.Catalog.Versions(r.Context(), catalog.KindCity, cityID)
	if err != nil {
		writeError(w, r, err)
		return
	}
	var newest *catalog.Version
	for i := range versions {
		if versions[i].Published() && len(versions[i].Manifest) > 0 {
			newest = &versions[i]
			break
		}
	}
	if newest == nil {
		writeError(w, r, fmt.Errorf("%w: %s has no published version to copy", domain.ErrInvalid, source.Name))
		return
	}
	var made catalog.City
	err = d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
		extent := source.Extent
		var err error
		made, err = d.Catalog.CreateCity(r.Context(), conn, catalog.CitySpec{
			Slug: copySlug(source.Slug), Name: source.Name, Summary: source.Summary, Extent: &extent,
			HorizontalCRS: source.HorizontalCRS, VerticalDatum: source.VerticalDatum,
			CreatedBy: principal.ID, OwnedByOrg: orgID,
		})
		if err != nil {
			return err
		}
		if err := d.Catalog.MarkCopy(r.Context(), conn, made.ID, cityID); err != nil {
			return err
		}
		version, err := d.Catalog.CreateVersion(r.Context(), conn, catalog.VersionSpec{
			AssetKind: catalog.KindCity, AssetID: made.ID, Manifest: newest.Manifest,
			Label: "copied from the store", Notes: "from " + newest.ID, RuntimeMin: newest.RuntimeMin,
			CreatedBy: principal.ID,
		})
		if err != nil {
			return err
		}
		if _, err := d.Catalog.Publish(r.Context(), conn, version.ID); err != nil {
			return err
		}
		return d.Audit.Record(r.Context(), conn, audit.Event{
			ActorID: principal.ID, Action: string(policy.CityAdopt),
			SubjectKind: "city", SubjectID: made.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"orgId": orgID, "copiedFrom": cityID, "version": newest.ID},
		})
	})
	if err != nil {
		writeError(w, r, err)
		return
	}
	writeJSON(w, r, http.StatusCreated, made)
}

// copySlug is a store place's slug with a short tail of its own: copies of
// one place sit side by side, each under its own name in a URL.
func copySlug(of string) string {
	tail := strings.ToLower(ids.New(ids.KindCity))
	tail = tail[len(tail)-6:]
	if len(of) > 63-7 {
		of = strings.TrimRight(of[:63-7], "-")
	}
	return of + "-" + tail
}

// offerPlace puts an organisation's place in the store, or takes it out. The
// copies already made stay theirs.
func (d *Dependencies) offerPlace(on bool) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		principal, _ := principalOf(r.Context())
		id := r.PathValue("cityId")
		err := d.Pool.InTransaction(r.Context(), func(conn db.Conn) error {
			if err := d.Catalog.OfferCity(r.Context(), conn, id, on); err != nil {
				return err
			}
			return d.Audit.Record(r.Context(), conn, audit.Event{
				ActorID: principal.ID, Action: string(policy.CityGrant),
				SubjectKind: "city", SubjectID: id, Outcome: audit.Succeeded,
				Detail: map[string]any{"inStore": on},
			})
		})
		if err != nil {
			writeError(w, r, err)
			return
		}
		city, err := d.Catalog.City(r.Context(), id)
		if err != nil {
			writeError(w, r, err)
			return
		}
		writeJSON(w, r, http.StatusOK, city)
	}
}
