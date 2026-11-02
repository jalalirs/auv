// Package mapstore is the iOcean map store: the places the platform builds
// from public data, checks and publishes, open to everybody.
//
// A place is in the store when no organisation owns it, anybody may find it,
// and it is not retired. What the store shows of each is what somebody
// choosing one needs to see on a card: where it is, how deep, how much of its
// depth was measured, how much reef it has, and its picture. All of that is
// read from the place's newest published version, and a published version
// never changes, so it is read once and kept.
package mapstore

import (
	"context"
	"math"
	"sort"
	"sync"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/building"
	"github.com/jalalirs/auv/services/control-plane/internal/catalog"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
)

// Picture is the file a card shows.
type Picture struct {
	Path     string `json:"path"`
	ObjectID string `json:"objectId"`
}

// Place is one place in the store, as a card shows it.
type Place struct {
	ID      string        `json:"id"`
	Slug    string        `json:"slug"`
	Name    string        `json:"name"`
	Summary string        `json:"summary"`
	Extent  domain.Extent `json:"extent"`
	// VersionID is its newest published version, which the rest is read
	// from; FilesHref lists that version's files with URLs to fetch them.
	VersionID   string     `json:"versionId,omitempty"`
	PublishedAt *time.Time `json:"publishedAt,omitempty"`
	FilesHref   string     `json:"filesHref,omitempty"`
	Look
	// Adopted says one of the caller's organisations took it the old way, as
	// a share of the store's own place.
	Adopted bool `json:"adopted"`
	// Copies is how many copies of it the caller's organisations hold.
	Copies int `json:"copies"`
	// DistanceM is how far its middle is from the middle of the area asked
	// about, when one was.
	DistanceM *float64 `json:"distanceM,omitempty"`
}

// Look is what a version's site.json says that a card shows.
type Look struct {
	DeepestM    *float64 `json:"deepestM,omitempty"`
	ShallowestM *float64 `json:"shallowestM,omitempty"`
	// Surveyed and SurveyedFraction say how much of the depth was measured
	// rather than estimated from imagery or models.
	Surveyed         *bool    `json:"surveyed,omitempty"`
	SurveyedFraction *float64 `json:"surveyedFraction,omitempty"`
	Method           string   `json:"method,omitempty"`
	// Depth is the place's own account of its depth: which source made how
	// much of it, and where it is weak.
	Depth    map[string]any `json:"depth,omitempty"`
	Colonies *float64       `json:"colonies,omitempty"`
	Picture  *Picture       `json:"picture,omitempty"`
}

// Square is an area somebody is about to build: its middle and how wide.
type Square struct {
	Lat, Lon, AcrossM float64
}

// Store reads the map store.
type Store struct {
	catalog    *catalog.Store
	builder    *building.Builder
	authorizer *policy.Authorizer

	mu sync.Mutex
	// looks is what each published version's site.json says, by version.
	looks map[string]Look
}

// New builds a Store.
func New(store *catalog.Store, builder *building.Builder, authorizer *policy.Authorizer) *Store {
	return &Store{catalog: store, builder: builder, authorizer: authorizer, looks: map[string]Look{}}
}

// Places lists the store, marking those any of orgIDs already has. Given an
// area, only the places that overlap it, nearest first.
func (s *Store) Places(ctx context.Context, orgIDs []string, near *Square) ([]Place, error) {
	cities, err := s.catalog.Catalogue(ctx)
	if err != nil {
		return nil, err
	}
	held, err := s.authorizer.HeldByOrgs(ctx, orgIDs, policy.ScopeCity)
	if err != nil {
		return nil, err
	}
	copies, err := s.catalog.CopiesByOrgs(ctx, orgIDs)
	if err != nil {
		return nil, err
	}
	places := []Place{}
	for _, city := range cities {
		place := Place{ID: city.ID, Slug: city.Slug, Name: city.Name, Summary: city.Summary,
			Extent: city.Extent, Adopted: held[city.ID], Copies: copies[city.ID]}
		if near != nil {
			if !overlaps(city.Extent, *near) {
				continue
			}
			d := distanceM(city.Extent, *near)
			place.DistanceM = &d
		}
		version, ok, err := s.newest(ctx, city.ID)
		if err != nil {
			return nil, err
		}
		if ok {
			place.VersionID, place.PublishedAt = version.ID, version.PublishedAt
			place.FilesHref = "/api/v1/versions/" + version.ID + "/files"
			if place.Look, err = s.look(ctx, version.ID); err != nil {
				return nil, err
			}
		}
		places = append(places, place)
	}
	if near != nil {
		sort.SliceStable(places, func(i, j int) bool { return *places[i].DistanceM < *places[j].DistanceM })
	}
	return places, nil
}

// Listed reports whether a place is in the store.
func Listed(city catalog.City) bool {
	return city.OwnedByOrg == "" && city.Discoverable && city.RetiredAt == nil
}

func (s *Store) newest(ctx context.Context, cityID string) (catalog.Version, bool, error) {
	versions, err := s.catalog.Versions(ctx, catalog.KindCity, cityID)
	if err != nil {
		return catalog.Version{}, false, err
	}
	for _, version := range versions {
		if version.Published() && len(version.Manifest) > 0 {
			return version, true, nil
		}
	}
	return catalog.Version{}, false, nil
}

// look reads a version once. A version whose record cannot be read shows
// nothing but where it is, and is asked again next time: that it cannot be
// read now may not be true later.
func (s *Store) look(ctx context.Context, versionID string) (Look, error) {
	s.mu.Lock()
	kept, ok := s.looks[versionID]
	s.mu.Unlock()
	if ok {
		return kept, nil
	}
	files, err := s.catalog.Files(ctx, versionID)
	if err != nil {
		return Look{}, err
	}
	site, err := s.builder.Site(ctx, versionID)
	if err != nil {
		return lookOf(nil, files), nil
	}
	look := lookOf(site, files)
	s.mu.Lock()
	s.looks[versionID] = look
	s.mu.Unlock()
	return look, nil
}

// lookOf reads what a card shows from a place's record and its files.
func lookOf(site map[string]any, files []catalog.File) Look {
	var look Look
	number := func(v any) *float64 {
		if f, ok := v.(float64); ok {
			return &f
		}
		return nil
	}
	look.DeepestM, look.ShallowestM = number(site["deepestM"]), number(site["shallowestM"])
	if from, ok := site["from"].(map[string]any); ok {
		if surveyed, ok := from["surveyed"].(bool); ok {
			look.Surveyed = &surveyed
		}
		look.SurveyedFraction = number(from["surveyedFraction"])
		look.Method, _ = from["method"].(string)
		look.Depth, _ = from["depth"].(map[string]any)
	}
	if reef, ok := site["reef"].(map[string]any); ok {
		look.Colonies = number(reef["colonies"])
	}
	for _, f := range files {
		if f.Path == "picture.jpg" {
			look.Picture = &Picture{Path: f.Path, ObjectID: f.ObjectID}
		}
	}
	return look
}

const metresPerDegree = 111320.0

// boundsOf is the square asked about, in degrees.
func boundsOf(near Square) domain.Extent {
	halfLat := near.AcrossM / 2 / metresPerDegree
	halfLon := near.AcrossM / 2 / (metresPerDegree * math.Max(math.Cos(near.Lat*math.Pi/180), 1e-6))
	return domain.Extent{West: near.Lon - halfLon, South: near.Lat - halfLat,
		East: near.Lon + halfLon, North: near.Lat + halfLat}
}

// overlaps reports whether a place's extent and the area asked about share
// any ground. A place with no extent overlaps nothing.
func overlaps(extent domain.Extent, near Square) bool {
	if extent.West == 0 && extent.East == 0 && extent.South == 0 && extent.North == 0 {
		return false
	}
	asked := boundsOf(near)
	return extent.West <= asked.East && asked.West <= extent.East &&
		extent.South <= asked.North && asked.South <= extent.North
}

// distanceM is how far a place's middle is from the middle of the area, on
// the sphere.
func distanceM(extent domain.Extent, near Square) float64 {
	lat := (extent.South + extent.North) / 2 * math.Pi / 180
	lon := (extent.West + extent.East) / 2 * math.Pi / 180
	lat0, lon0 := near.Lat*math.Pi/180, near.Lon*math.Pi/180
	h := math.Pow(math.Sin((lat-lat0)/2), 2) + math.Cos(lat)*math.Cos(lat0)*math.Pow(math.Sin((lon-lon0)/2), 2)
	return 2 * 6371000 * math.Asin(math.Min(1, math.Sqrt(h)))
}
