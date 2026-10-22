// Package mapping puts reefs made from dive videos onto a place.
//
// There are two ways. Onto a place that already exists, any number of reefs
// at once: for each, a job searches the place's seabed for where the reef's
// own ground fits, near where its video started, and reports the best few;
// somebody chooses one for each, or moves it by hand, and one job lays them
// all in. Or onto a place of its own, for one reef with no map: a flat seabed
// is built for it first, as an ordinary place build, and the reef is laid in
// its middle. Either way the place gains a draft version with the reefs in
// it, which its curators publish like any other.
//
// Both jobs run the reconstruction module's image, with no network: the
// search on processors, the laying on a GPU.
package mapping

import (
	"errors"
	"fmt"
	"math"
	"regexp"
	"strings"

	"github.com/jalalirs/auv/services/control-plane/internal/building"
	"github.com/jalalirs/auv/services/control-plane/internal/catalog"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/exec"
	"github.com/jalalirs/auv/services/control-plane/internal/reconstructing"
	"github.com/jalalirs/auv/services/control-plane/internal/storage"
)

// The recipes the two jobs are recorded as having been made by.
const (
	ResolveRecipe = "resolve-reconstruction/v1"
	LayRecipe     = "lay-reconstruction/v1"
)

// The two ways a reef is put onto a place.
const (
	Own  = "own"
	Onto = "onto"
)

// NominalStart is where a reef with no stated start is put on Earth: the
// Red Sea off Thuwal, where video-reef puts it. It is a default nobody chose
// for this reef, and the mapping says so.
var NominalStart = reconstructing.Point{Lat: 22.30, Lon: 38.85}

// ErrNotConfigured reports a platform with no image to put reefs onto places
// with.
var ErrNotConfigured = errors.New("this platform has no image to put reconstructions onto places with")

// Settings are how a mapping's jobs run. The image is the reconstruction
// module's.
type Settings struct {
	Image string
	// The search is work for processors.
	ResolveCPU             float64
	ResolveMemoryBytes     int64
	ResolveWalltimeSeconds int
	// Laying the reefs in bakes their splats, which is work for a GPU. It is
	// given an hour and three quarters of an hour more for each reef, up to
	// LayWalltimeSeconds.
	LayCPU             float64
	LayMemoryBytes     int64
	LayGPU             int
	LayWalltimeSeconds int
	// PackageBytes is how much a reef may add to the place laying makes, and
	// PackageCapBytes the most it may make whatever it holds.
	PackageBytes    int64
	PackageCapBytes int64
}

// MostAssets is how many reefs one mapping lays into a place.
const MostAssets = 20

// Request is what somebody asks a mapping to do.
type Request struct {
	Mode string `json:"mode"`

	// Onto a place: which, and which of its versions (its newest when
	// nobody says).
	CityID    string `json:"cityId,omitempty"`
	VersionID string `json:"versionId,omitempty"`
	// Start is where the video starts; the reconstruction's own when nobody
	// says. The search looks within WithinM of it.
	Start   *reconstructing.Point `json:"start,omitempty"`
	WithinM float64               `json:"withinM,omitempty"`
	// DepthM is how deep the reef is, when somebody knows: onto a place, a
	// hint to the search; for a place of its own, the flat seabed's depth.
	DepthM *float64 `json:"depthM,omitempty"`
	Count  int      `json:"count,omitempty"`

	// A place of its own: what to call it, how wide, what the ground around
	// the reef is, and which way the reef faces.
	Name       string   `json:"name,omitempty"`
	AcrossM    float64  `json:"acrossM,omitempty"`
	Pad        string   `json:"pad,omitempty"`
	HeadingDeg *float64 `json:"headingDeg,omitempty"`

	// StartAssumed says the start is NominalStart, because neither the
	// request nor the reconstruction named one. Written by the platform.
	StartAssumed bool `json:"startAssumed,omitempty"`
}

func finite(v float64) bool { return !math.IsNaN(v) && !math.IsInf(v, 0) }

// Validate reports whether a request can be done.
func (q Request) Validate() error {
	if s := q.Start; s != nil && (!finite(s.Lat) || s.Lat < -90 || s.Lat > 90 || !finite(s.Lon) || s.Lon < -180 || s.Lon > 180) {
		return fmt.Errorf("%w: where the video starts is latitude and longitude in degrees", domain.ErrInvalid)
	}
	switch q.Mode {
	case Onto:
		if q.CityID == "" {
			return fmt.Errorf("%w: a reef is put onto a place that is named (cityId)", domain.ErrInvalid)
		}
		return q.asset("").Validate()
	case Own:
		if strings.TrimSpace(q.Name) == "" {
			return fmt.Errorf("%w: a place of the reef's own has a name", domain.ErrInvalid)
		}
		if q.AcrossM != 0 && (!finite(q.AcrossM) || q.AcrossM < 100 || q.AcrossM > 2000) {
			return fmt.Errorf("%w: a place of the reef's own is 100 m to 2 km across", domain.ErrInvalid)
		}
		if d := q.DepthM; d != nil && (!finite(*d) || *d < 0.5 || *d > 60) {
			return fmt.Errorf("%w: a flat seabed is between 0.5 m and 60 m deep", domain.ErrInvalid)
		}
		switch q.Pad {
		case "", "sand", "coral":
		default:
			return fmt.Errorf("%w: the ground around the reef is sand or coral, not %q", domain.ErrInvalid, q.Pad)
		}
		if h := q.HeadingDeg; h != nil && (!finite(*h) || *h < 0 || *h > 360) {
			return fmt.Errorf("%w: a heading is 0 to 360 degrees", domain.ErrInvalid)
		}
	default:
		return fmt.Errorf("%w: a reef is put onto a place (onto) or given one of its own (own), not %q",
			domain.ErrInvalid, q.Mode)
	}
	return nil
}

// asset is the one reef a request for a reconstruction's mapping asks about.
func (q Request) asset(reconstructionID string) AssetRequest {
	return AssetRequest{ReconstructionID: reconstructionID, Start: q.Start, WithinM: q.WithinM,
		DepthM: q.DepthM, Count: q.Count, HeadingDeg: q.HeadingDeg, StartAssumed: q.StartAssumed}
}

// AssetRequest is one reef a mapping puts onto a place, and what its search
// is told: where its video starts (the reconstruction's own when nobody
// says), how far from there to look, how deep it is when somebody knows, and
// how many places to report. For a place of its own, HeadingDeg is which way
// it faces.
type AssetRequest struct {
	ReconstructionID string                `json:"reconstructionId"`
	Start            *reconstructing.Point `json:"start,omitempty"`
	WithinM          float64               `json:"withinM,omitempty"`
	DepthM           *float64              `json:"depthM,omitempty"`
	Count            int                   `json:"count,omitempty"`
	HeadingDeg       *float64              `json:"headingDeg,omitempty"`
	// StartAssumed says the start is NominalStart. Written by the platform.
	StartAssumed bool `json:"startAssumed,omitempty"`
}

// Validate reports whether a reef's search can be done.
func (a AssetRequest) Validate() error {
	if s := a.Start; s != nil && (!finite(s.Lat) || s.Lat < -90 || s.Lat > 90 || !finite(s.Lon) || s.Lon < -180 || s.Lon > 180) {
		return fmt.Errorf("%w: where the video starts is latitude and longitude in degrees", domain.ErrInvalid)
	}
	if a.WithinM != 0 && (!finite(a.WithinM) || a.WithinM < 10 || a.WithinM > 5000) {
		return fmt.Errorf("%w: the search looks 10 m to 5 km from where the video starts", domain.ErrInvalid)
	}
	if d := a.DepthM; d != nil && (!finite(*d) || *d <= 0 || *d > 200) {
		return fmt.Errorf("%w: a reef is between the surface and 200 m down", domain.ErrInvalid)
	}
	if a.Count != 0 && (a.Count < 1 || a.Count > 20) {
		return fmt.Errorf("%w: the search reports 1 to 20 places", domain.ErrInvalid)
	}
	return nil
}

// PlaceRequest is what somebody asks for when they put reefs onto a place:
// which of its versions (its newest when nobody says), and the reefs.
type PlaceRequest struct {
	VersionID string         `json:"versionId,omitempty"`
	Assets    []AssetRequest `json:"assets"`
}

// Validate reports whether the reefs can be put onto a place.
func (q PlaceRequest) Validate() error {
	if len(q.Assets) == 0 || len(q.Assets) > MostAssets {
		return fmt.Errorf("%w: a mapping puts 1 to %d reefs onto a place", domain.ErrInvalid, MostAssets)
	}
	for i, one := range q.Assets {
		if one.ReconstructionID == "" {
			return fmt.Errorf("%w: reef %d names the reconstruction it is (reconstructionId)", domain.ErrInvalid, i)
		}
		if err := one.Validate(); err != nil {
			return fmt.Errorf("reef %d: %w", i, err)
		}
	}
	return nil
}

// assetDefaults writes down what a reef's search leaves to a default.
func assetDefaults(a AssetRequest, made reconstructing.Reconstruction) AssetRequest {
	if a.Start == nil && made.Brief.Start != nil {
		start := *made.Brief.Start
		a.Start = &start
	}
	if a.WithinM == 0 {
		a.WithinM = 400
	}
	if a.Count == 0 {
		a.Count = 5
	}
	return a
}

// withDefaults writes down what a request leaves to a default, so the record
// says what was done.
func withDefaults(q Request, made reconstructing.Reconstruction) Request {
	if q.Start == nil {
		if made.Brief.Start != nil {
			start := *made.Brief.Start
			q.Start = &start
		} else if q.Mode == Own {
			start := NominalStart
			q.Start, q.StartAssumed = &start, true
		}
	}
	switch q.Mode {
	case Onto:
		if q.WithinM == 0 {
			q.WithinM = 400
		}
		if q.Count == 0 {
			q.Count = 5
		}
	case Own:
		if q.AcrossM == 0 {
			q.AcrossM = 300
		}
		if q.DepthM == nil {
			depth := 8.0
			q.DepthM = &depth
		}
		if q.Pad == "" {
			q.Pad = "sand"
		}
		if q.HeadingDeg == nil {
			heading := 0.0
			q.HeadingDeg = &heading
		}
	}
	return q
}

// Placement is where somebody put the reef by hand: the reef's ground's
// centre at At in the place's metres, turned by HeadingDeg, raised by Dz.
type Placement struct {
	At         [2]float64 `json:"at"`
	HeadingDeg float64    `json:"headingDeg"`
	Dz         float64    `json:"dz"`
}

// Validate reports whether a placement is somewhere.
func (p Placement) Validate() error {
	if !finite(p.At[0]) || !finite(p.At[1]) || !finite(p.Dz) {
		return fmt.Errorf("%w: a placement is at [x, y] metres, raised by dz metres", domain.ErrInvalid)
	}
	if !finite(p.HeadingDeg) || p.HeadingDeg < 0 || p.HeadingDeg > 360 {
		return fmt.Errorf("%w: a heading is 0 to 360 degrees", domain.ErrInvalid)
	}
	return nil
}

// Choice is what somebody accepts for one reef (the first when they do not
// say which): one of the places its search found, by its index, or a
// placement of their own.
type Choice struct {
	Asset     *int       `json:"asset,omitempty"`
	Candidate *int       `json:"candidate,omitempty"`
	Placement *Placement `json:"placement,omitempty"`
}

// placementOf turns a choice into what the lay job is told.
func placementOf(choice Choice, found []map[string]any) (map[string]any, error) {
	switch {
	case choice.Candidate != nil && choice.Placement != nil:
		return nil, fmt.Errorf("%w: accept a candidate or a placement, not both", domain.ErrInvalid)
	case choice.Placement != nil:
		if err := choice.Placement.Validate(); err != nil {
			return nil, err
		}
		p := choice.Placement
		return map[string]any{"at": []float64{p.At[0], p.At[1]}, "headingDeg": p.HeadingDeg, "dz": p.Dz,
			"fit": map[string]any{"by": "hand"}}, nil
	case choice.Candidate != nil:
		i := *choice.Candidate
		if i < 0 || i >= len(found) {
			return nil, fmt.Errorf("%w: the search found %d places; there is no candidate %d", domain.ErrInvalid, len(found), i)
		}
		one := found[i]
		placement := map[string]any{}
		for _, key := range []string{"at", "headingDeg", "dz", "fit"} {
			if v, ok := one[key]; ok {
				placement[key] = v
			}
		}
		if placement["at"] == nil || placement["dz"] == nil {
			return nil, fmt.Errorf("candidate %d does not say where it is", i)
		}
		return placement, nil
	default:
		return nil, fmt.Errorf("%w: accept a candidate (its index) or a placement", domain.ErrInvalid)
	}
}

var notHandle = regexp.MustCompile(`[^a-z0-9]+`)

// namesOf is what each reef is called inside a place: its name, made a slug,
// and made unique by a number when two would be called the same.
func namesOf(names []string) []string {
	out := make([]string, len(names))
	taken := map[string]bool{}
	for i, name := range names {
		base := handleOf(name)
		handle := base
		for n := 2; taken[handle]; n++ {
			handle = fmt.Sprintf("%s-%d", base, n)
		}
		taken[handle], out[i] = true, handle
	}
	return out
}

// handleOf is what a reef is called inside a place: its name, made a slug.
func handleOf(name string) string {
	handle := strings.Trim(notHandle.ReplaceAllString(strings.ToLower(name), "-"), "-")
	if len(handle) > 48 {
		handle = strings.Trim(handle[:48], "-")
	}
	if handle == "" || handle[0] < 'a' || handle[0] > 'z' {
		handle = "reef-" + handle
	}
	return strings.TrimRight(handle, "-")
}

// extentOf is the square a place of the reef's own covers.
func extentOf(centre reconstructing.Point, acrossM float64) domain.Extent {
	halfLat := acrossM / 2 / 111320.0
	halfLon := acrossM / 2 / (111320.0 * math.Max(math.Cos(centre.Lat*math.Pi/180), 1e-6))
	return domain.Extent{West: centre.Lon - halfLon, South: centre.Lat - halfLat,
		East: centre.Lon + halfLon, North: centre.Lat + halfLat}
}

// wanted reports whether a reconstruction's file is staged for a job. The
// search reads the reef's ground and its manifest; only laying needs the
// pieces themselves, which are most of the bytes.
func wanted(path string, pieces bool) bool {
	return pieces || !strings.HasPrefix(path, "parts/")
}

// Mapper runs mappings.
type Mapper struct {
	pool          *db.Pool
	broker        *exec.Broker
	objects       *storage.Objects
	catalog       *catalog.Store
	builder       *building.Builder
	reconstructor *reconstructing.Reconstructor
	settings      Settings
}

// New builds a Mapper.
func New(pool *db.Pool, broker *exec.Broker, objects *storage.Objects, store *catalog.Store,
	builder *building.Builder, reconstructor *reconstructing.Reconstructor, settings Settings) *Mapper {
	if settings.ResolveCPU == 0 {
		settings.ResolveCPU = 4
	}
	if settings.ResolveMemoryBytes == 0 {
		settings.ResolveMemoryBytes = 8 << 30
	}
	if settings.ResolveWalltimeSeconds == 0 {
		settings.ResolveWalltimeSeconds = 3600
	}
	if settings.LayCPU == 0 {
		settings.LayCPU = 8
	}
	if settings.LayMemoryBytes == 0 {
		settings.LayMemoryBytes = 32 << 30
	}
	if settings.LayGPU == 0 {
		settings.LayGPU = 1
	}
	if settings.LayWalltimeSeconds == 0 {
		settings.LayWalltimeSeconds = 16 * 3600
	}
	if settings.PackageBytes == 0 {
		settings.PackageBytes = 40 << 30
	}
	if settings.PackageCapBytes == 0 {
		// The most one object may be on this platform by default.
		settings.PackageCapBytes = 64 << 30
	}
	return &Mapper{pool: pool, broker: broker, objects: objects, catalog: store, builder: builder,
		reconstructor: reconstructor, settings: settings}
}
