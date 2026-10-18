// Package mapping puts a reef made from a dive video onto a place.
//
// There are two ways. Onto a place that already exists: a job searches the
// place's seabed for where the reef's own ground fits, near where the video
// started, and reports the best few; somebody chooses one, or moves it by
// hand, and a second job lays the reef in. Or onto a place of its own, for a
// reef with no map: a flat seabed is built for it first, as an ordinary place
// build, and the reef is laid in its middle. Either way the place gains a
// draft version with the reef in it, which its curators publish like any
// other.
//
// Both jobs run the reconstruction module's image, with no network: the
// search on processors, the laying on a GPU.
package mapping

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"regexp"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/building"
	"github.com/jalalirs/auv/services/control-plane/internal/catalog"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/exec"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
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
	// Laying the reef in bakes its splats, which is work for a GPU.
	LayCPU             float64
	LayMemoryBytes     int64
	LayGPU             int
	LayWalltimeSeconds int
	// PackageBytes is the largest place package laying may make.
	PackageBytes int64
}

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
		if q.WithinM != 0 && (!finite(q.WithinM) || q.WithinM < 10 || q.WithinM > 5000) {
			return fmt.Errorf("%w: the search looks 10 m to 5 km from where the video starts", domain.ErrInvalid)
		}
		if d := q.DepthM; d != nil && (!finite(*d) || *d <= 0 || *d > 200) {
			return fmt.Errorf("%w: a reef is between the surface and 200 m down", domain.ErrInvalid)
		}
		if q.Count != 0 && (q.Count < 1 || q.Count > 20) {
			return fmt.Errorf("%w: the search reports 1 to 20 places", domain.ErrInvalid)
		}
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

// Choice is what somebody accepts: one of the places the search found, by
// its index, or a placement of their own.
type Choice struct {
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
		settings.LayWalltimeSeconds = 3 * 3600
	}
	if settings.PackageBytes == 0 {
		settings.PackageBytes = 40 << 30
	}
	return &Mapper{pool: pool, broker: broker, objects: objects, catalog: store, builder: builder,
		reconstructor: reconstructor, settings: settings}
}

// Mapping is the record of one mapping.
type Mapping struct {
	ID               string  `json:"id"`
	OrgID            string  `json:"orgId"`
	ReconstructionID string  `json:"reconstructionId"`
	CityID           string  `json:"cityId"`
	Mode             string  `json:"mode"`
	Brief            Request `json:"brief"`
	BaseVersionID    string  `json:"baseVersionId,omitempty"`
	BuildID          string  `json:"buildId,omitempty"`
	ResolveJobID     string  `json:"resolveJobId,omitempty"`
	// Candidates are the places the search found the reef fits, best first;
	// Start is where in the place's metres it searched from, when it knew,
	// and Searched how (candidates.json, read once from its output).
	Candidates []map[string]any `json:"candidates,omitempty"`
	Start      []float64        `json:"start,omitempty"`
	Searched   map[string]any   `json:"searched,omitempty"`
	// Chosen is where the reef is laid, as the lay job was told.
	Chosen     map[string]any `json:"chosen,omitempty"`
	LayJobID   string         `json:"layJobId,omitempty"`
	VersionID  string         `json:"versionId,omitempty"`
	Failure    string         `json:"failure,omitempty"`
	CreatedBy  string         `json:"createdBy"`
	CreatedAt  time.Time      `json:"createdAt"`
	RecordedAt *time.Time     `json:"recordedAt,omitempty"`
}

const selectMapping = `
	SELECT id, org_id, reconstruction_id, city_id, mode, brief, coalesce(base_version_id, ''),
	       coalesce(build_id, ''), coalesce(resolve_job_id, ''), candidates, chosen,
	       coalesce(lay_job_id, ''), coalesce(version_id, ''), coalesce(failure, ''),
	       created_by, created_at, recorded_at
	FROM catalog.mapping`

func scanMapping(row interface{ Scan(...any) error }) (Mapping, error) {
	var m Mapping
	var brief, candidates, chosen []byte
	if err := row.Scan(&m.ID, &m.OrgID, &m.ReconstructionID, &m.CityID, &m.Mode, &brief, &m.BaseVersionID,
		&m.BuildID, &m.ResolveJobID, &candidates, &chosen, &m.LayJobID, &m.VersionID, &m.Failure,
		&m.CreatedBy, &m.CreatedAt, &m.RecordedAt); err != nil {
		return Mapping{}, db.Translate(err)
	}
	if err := json.Unmarshal(brief, &m.Brief); err != nil {
		return Mapping{}, err
	}
	if len(candidates) > 0 {
		var found struct {
			Candidates []map[string]any `json:"candidates"`
			Start      []float64        `json:"start"`
			Searched   map[string]any   `json:"searched"`
		}
		if err := json.Unmarshal(candidates, &found); err != nil {
			return Mapping{}, err
		}
		m.Candidates, m.Start, m.Searched = found.Candidates, found.Start, found.Searched
		if m.Candidates == nil {
			m.Candidates = []map[string]any{}
		}
	}
	if len(chosen) > 0 {
		if err := json.Unmarshal(chosen, &m.Chosen); err != nil {
			return Mapping{}, err
		}
	}
	return m, nil
}

// Start asks for a reconstruction to be put onto a place. The work belongs to
// the reconstruction's organisation, and so does a place made for it.
func (m *Mapper) Start(ctx context.Context, principalID, reconstructionID string, request Request) (Mapping, error) {
	if m.settings.Image == "" {
		return Mapping{}, ErrNotConfigured
	}
	if err := request.Validate(); err != nil {
		return Mapping{}, err
	}
	watched, err := m.reconstructor.Watch(ctx, reconstructionID)
	if err != nil {
		return Mapping{}, err
	}
	if watched.State != "ready" {
		return Mapping{}, fmt.Errorf("%w: the reconstruction is %s; a reef is put onto a place once it is ready",
			domain.ErrInvalid, watched.State)
	}
	made := watched.Reconstruction
	request = withDefaults(request, made)
	mapping := Mapping{ID: ids.New(ids.KindMapping), OrgID: made.OrgID, ReconstructionID: made.ID,
		Mode: request.Mode, Brief: request, CreatedBy: principalID}

	switch request.Mode {
	case Onto:
		city, err := m.catalog.City(ctx, request.CityID)
		if err != nil {
			return Mapping{}, fmt.Errorf("%w: no place %s", domain.ErrInvalid, request.CityID)
		}
		version, err := m.versionOf(ctx, city.ID, request.VersionID)
		if err != nil {
			return Mapping{}, err
		}
		inputs, err := m.inputs(ctx, version.ID, made.ID, false)
		if err != nil {
			return Mapping{}, err
		}
		brief := map[string]any{"withinM": request.WithinM, "depthSlackM": 3.0, "count": request.Count}
		if request.Start != nil {
			brief["start"] = request.Start
		}
		if request.DepthM != nil {
			brief["depthM"] = *request.DepthM
		}
		said, err := json.Marshal(brief)
		if err != nil {
			return Mapping{}, err
		}
		job, err := m.broker.Submit(ctx, exec.JobSpec{
			OrgID: made.OrgID, SubmittedBy: principalID, RecipeID: ResolveRecipe,
			ImageDigest: m.settings.Image,
			Command:     []string{"python", "-m", "iocean_reconstruct.resolve"},
			Args:        []string{string(said)},
			Inputs:      inputs,
			Outputs: []exec.Output{{Name: "candidates", RelativePath: "candidates.json",
				MediaType: "application/json", MaxSizeBytes: 16 << 20}},
			RequestCPU: m.settings.ResolveCPU, RequestMemoryBytes: m.settings.ResolveMemoryBytes,
			WalltimeSeconds: m.settings.ResolveWalltimeSeconds,
			Egress:          exec.NoEgress,
		})
		if err != nil {
			return Mapping{}, err
		}
		mapping.CityID, mapping.BaseVersionID, mapping.ResolveJobID = city.ID, version.ID, job.ID
	case Own:
		city, err := m.found(ctx, principalID, made, request)
		if err != nil {
			return Mapping{}, err
		}
		coral := request.Pad == "coral"
		build, err := m.builder.Start(ctx, principalID, made.OrgID, city, building.Brief{
			Centre: [2]float64{request.Start.Lat, request.Start.Lon}, AcrossM: request.AcrossM,
			Sources: []string{}, FlatDepthM: request.DepthM, Coral: &coral,
			Label: "base for " + made.Name,
		})
		if err != nil {
			return Mapping{}, err
		}
		mapping.CityID, mapping.BuildID = city.ID, build.ID
	}

	said, err := json.Marshal(request)
	if err != nil {
		return Mapping{}, err
	}
	err = m.pool.QueryRow(ctx, `
		INSERT INTO catalog.mapping (id, org_id, reconstruction_id, city_id, mode, brief,
		                             base_version_id, build_id, resolve_job_id, created_by)
		VALUES ($1, $2, $3, $4, $5, $6, nullif($7, ''), nullif($8, ''), nullif($9, ''), $10)
		RETURNING created_at`,
		mapping.ID, mapping.OrgID, mapping.ReconstructionID, mapping.CityID, mapping.Mode, said,
		mapping.BaseVersionID, mapping.BuildID, mapping.ResolveJobID, principalID).Scan(&mapping.CreatedAt)
	if err != nil {
		return Mapping{}, fmt.Errorf("recording a mapping: %w", err)
	}
	return mapping, nil
}

// versionOf is the version of a place the reef is put onto: the one named,
// or the place's newest package, published or not.
func (m *Mapper) versionOf(ctx context.Context, cityID, versionID string) (catalog.Version, error) {
	if versionID != "" {
		version, err := m.catalog.Version(ctx, versionID)
		if err != nil || version.AssetKind != catalog.KindCity || version.AssetID != cityID {
			return catalog.Version{}, fmt.Errorf("%w: %s is not a version of %s", domain.ErrInvalid, versionID, cityID)
		}
		if len(version.Manifest) == 0 {
			return catalog.Version{}, fmt.Errorf("%w: %s is not a package of files", domain.ErrInvalid, versionID)
		}
		return version, nil
	}
	versions, err := m.catalog.Versions(ctx, catalog.KindCity, cityID)
	if err != nil {
		return catalog.Version{}, err
	}
	for _, version := range versions {
		if len(version.Manifest) > 0 {
			return version, nil
		}
	}
	return catalog.Version{}, fmt.Errorf("%w: %s has no version yet to put a reef onto", domain.ErrInvalid, cityID)
}

// found founds a place of the reef's own, the organisation's, the way a place
// is founded for a build: by name, with the next free slug.
func (m *Mapper) found(ctx context.Context, principalID string, made reconstructing.Reconstruction, request Request) (catalog.City, error) {
	extent := extentOf(*request.Start, request.AcrossM)
	base := handleOf(request.Name)
	if len(base) < 3 {
		base += "-place"
	}
	summary := "a flat seabed for the reef reconstructed as " + made.Name
	if request.StartAssumed {
		summary += "; where it is on Earth is assumed, because nobody said where the video starts"
	}
	for attempt := 0; attempt < 6; attempt++ {
		slug := base
		if attempt > 0 {
			slug = fmt.Sprintf("%s-%d", base, attempt+1)
		}
		var city catalog.City
		err := m.pool.InTransaction(ctx, func(conn db.Conn) error {
			var err error
			city, err = m.catalog.CreateCity(ctx, conn, catalog.CitySpec{
				Slug: slug, Name: strings.TrimSpace(request.Name), Summary: summary, Extent: &extent,
				VerticalDatum: "mean sea level", CreatedBy: principalID, OwnedByOrg: made.OrgID,
			})
			return err
		})
		if err == nil {
			return city, nil
		}
		if !errors.Is(err, domain.ErrInvalid) || !strings.Contains(err.Error(), "already exists") {
			return catalog.City{}, err
		}
	}
	return catalog.City{}, fmt.Errorf("%w: places called %s and five more like it exist; choose another name",
		domain.ErrInvalid, base)
}

// inputs stages a place's version under place/ and a reconstruction's files
// under reconstruction/, each at its own path.
func (m *Mapper) inputs(ctx context.Context, versionID, reconstructionID string, pieces bool) ([]exec.Input, error) {
	files, err := m.catalog.Files(ctx, versionID)
	if err != nil {
		return nil, err
	}
	inputs := make([]exec.Input, 0, len(files))
	for _, f := range files {
		at := "place/" + f.Path
		inputs = append(inputs, exec.Input{Name: at, RelativePath: at, ObjectID: f.ObjectID,
			SHA256: f.Digest.String(), MediaType: f.MediaType, SizeBytes: f.SizeBytes})
	}
	held, err := m.reconstructor.Objects(ctx, reconstructionID)
	if err != nil {
		return nil, err
	}
	for _, one := range held {
		if !wanted(one.Path, pieces) {
			continue
		}
		object, err := m.objects.Object(ctx, one.ObjectID)
		if err != nil {
			return nil, err
		}
		at := "reconstruction/" + one.Path
		inputs = append(inputs, exec.Input{Name: at, RelativePath: at, ObjectID: object.ID,
			SHA256: object.SHA256, MediaType: object.MediaType, SizeBytes: object.SizeBytes})
	}
	return inputs, nil
}

// OrgOf names the organisation a mapping belongs to.
func (m *Mapper) OrgOf(ctx context.Context, id string) (string, error) {
	var org string
	err := m.pool.QueryRow(ctx, `SELECT org_id FROM catalog.mapping WHERE id = $1`, id).Scan(&org)
	return org, db.Translate(err)
}

// Of lists a reconstruction's mappings, newest first.
func (m *Mapper) Of(ctx context.Context, reconstructionID string) ([]Mapping, error) {
	rows, err := m.pool.Query(ctx,
		selectMapping+` WHERE reconstruction_id = $1 ORDER BY created_at DESC LIMIT 50`, reconstructionID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	all := []Mapping{}
	for rows.Next() {
		one, err := scanMapping(rows)
		if err != nil {
			return nil, err
		}
		all = append(all, one)
	}
	return all, rows.Err()
}

// Step is one thing one of a mapping's jobs said it was doing, and which: the
// base build (base), the search (resolve), or laying the reef in (lay).
type Step struct {
	exec.Step
	Phase string `json:"phase"`
}

// View is a mapping as somebody watching it sees it.
type View struct {
	Mapping
	// State is the mapping's: building (its own place's seabed), resolving
	// (searching the place), choosing (waiting for somebody to accept a
	// candidate), laying, recording (the place's new version is being
	// kept), ready, or failed.
	State string `json:"state"`
	Steps []Step `json:"steps"`
	// Waiting says why the next job has not started yet, when the platform
	// refused it for now: the organisation's GPU is in use, say.
	Waiting string `json:"waiting,omitempty"`
	// Said is the end of what the failed job printed.
	Said string `json:"said,omitempty"`
}

const keptSteps = 200

// staleAfter is how long a claim to record a laid place is honoured without a
// result; past it, somebody watching claims it again.
const staleAfter = 2 * time.Hour

// Watch reads a mapping and moves it on when the job it waits for has
// finished: the base build made its version (start laying), the search
// reported (read what it found), the lay job made the place (keep it as a
// version). Each is done once, however many people are watching.
func (m *Mapper) Watch(ctx context.Context, id string) (View, error) {
	mp, err := scanMapping(m.pool.QueryRow(ctx, selectMapping+` WHERE id = $1`, id))
	if err != nil {
		return View{}, err
	}
	view := View{Steps: []Step{}}
	var said string

	if mp.BuildID != "" {
		base, err := m.builder.Watch(ctx, mp.BuildID)
		if err != nil {
			return View{}, err
		}
		view.Steps = append(view.Steps, phased("base", base.Steps)...)
		if mp.LayJobID == "" && mp.Failure == "" {
			switch base.State {
			case "ready":
				placement := map[string]any{"centre": true, "depthM": *mp.Brief.DepthM, "headingDeg": *mp.Brief.HeadingDeg}
				laid, err := m.lay(ctx, mp.ID, func(Mapping) (map[string]any, string, error) {
					return placement, base.VersionID, nil
				})
				var refusal *exec.Refusal
				switch {
				case errors.As(err, &refusal):
					view.State, view.Waiting = "building", refusal.Error()
				case err != nil:
					return View{}, err
				default:
					mp = laid
				}
			case "failed":
				view.State, said = "failed", base.Said
				view.Failure = "the place's flat seabed could not be built: " + base.Failure
			default:
				view.State = "building"
			}
		}
	}

	if mp.ResolveJobID != "" {
		job, steps, out, err := m.job(ctx, mp.ResolveJobID)
		if err != nil {
			return View{}, err
		}
		view.Steps = append(view.Steps, phased("resolve", steps)...)
		if mp.LayJobID == "" && mp.Failure == "" {
			switch job.State {
			case exec.Pending, exec.Admitted, exec.Running:
				view.State = "resolving"
			case exec.Succeeded:
				if mp.Candidates == nil {
					if mp, err = m.readCandidates(ctx, mp.ID); err != nil {
						return View{}, err
					}
				}
				view.State = "choosing"
			default:
				view.State, said = "failed", out
				view.Failure = fmt.Sprintf("the search's job %s (%s)", job.State, job.FailureClass)
			}
		}
	}

	if mp.LayJobID != "" {
		job, steps, out, err := m.job(ctx, mp.LayJobID)
		if err != nil {
			return View{}, err
		}
		view.Steps = append(view.Steps, phased("lay", steps)...)
		switch job.State {
		case exec.Pending, exec.Admitted, exec.Running:
			view.State = "laying"
		case exec.Succeeded:
			switch {
			case mp.VersionID != "":
				view.State = "ready"
			case mp.Failure != "":
				view.State = "failed"
			default:
				view.State = "recording"
				if err := m.claim(ctx, mp); err != nil {
					return View{}, err
				}
			}
		default:
			view.State, said = "failed", out
			view.Failure = fmt.Sprintf("the lay job %s (%s)", job.State, job.FailureClass)
		}
	}

	failure := view.Failure
	view.Mapping = mp
	switch {
	case mp.Failure != "":
		view.State = "failed"
	case failure != "":
		view.Failure = failure
	}
	if view.State == "failed" {
		view.Said = said
		if len(view.Said) > 4000 {
			view.Said = view.Said[len(view.Said)-4000:]
		}
	}
	if len(view.Steps) > keptSteps {
		view.Steps = view.Steps[len(view.Steps)-keptSteps:]
	}
	return view, nil
}

func phased(phase string, steps []exec.Step) []Step {
	out := make([]Step, 0, len(steps))
	for _, step := range steps {
		out = append(out, Step{Step: step, Phase: phase})
	}
	return out
}

// job reads one of a mapping's jobs and everything it reported.
func (m *Mapper) job(ctx context.Context, jobID string) (exec.Job, []exec.Step, string, error) {
	job, err := m.broker.Job(ctx, jobID)
	if err != nil {
		return exec.Job{}, nil, "", err
	}
	var events []exec.Event
	var after int64
	for page := 0; page < 50; page++ {
		some, err := m.broker.Events(ctx, jobID, after, 1000)
		if err != nil {
			return exec.Job{}, nil, "", err
		}
		events = append(events, some...)
		if len(some) < 1000 {
			break
		}
		after = some[len(some)-1].Sequence
	}
	steps, said := exec.Progress(events)
	return job, steps, said, nil
}

// errDone ends a locked transaction that found its work already done.
var errDone = errors.New("already done")

// locked runs act on a mapping's row, locked, so two watchers do not both
// move it on; it hands back the row as it is afterwards.
func (m *Mapper) locked(ctx context.Context, id string, act func(conn db.Conn, mp Mapping) error) (Mapping, error) {
	err := m.pool.InTransaction(ctx, func(conn db.Conn) error {
		mp, err := scanMapping(conn.QueryRow(ctx, selectMapping+` WHERE id = $1 FOR UPDATE`, id))
		if err != nil {
			return err
		}
		return act(conn, mp)
	})
	if err != nil && !errors.Is(err, errDone) {
		return Mapping{}, err
	}
	return scanMapping(m.pool.QueryRow(ctx, selectMapping+` WHERE id = $1`, id))
}

// readCandidates keeps what the search found.
func (m *Mapper) readCandidates(ctx context.Context, id string) (Mapping, error) {
	return m.locked(ctx, id, func(conn db.Conn, mp Mapping) error {
		if mp.Candidates != nil || mp.Failure != "" {
			return errDone
		}
		found, err := m.candidatesOf(ctx, mp.ResolveJobID)
		if err != nil {
			_, err := conn.Exec(ctx, `UPDATE catalog.mapping SET failure = $2 WHERE id = $1`, id, err.Error())
			return err
		}
		said, err := json.Marshal(found)
		if err != nil {
			return err
		}
		_, err = conn.Exec(ctx, `UPDATE catalog.mapping SET candidates = $2 WHERE id = $1`, id, said)
		return err
	})
}

func (m *Mapper) candidatesOf(ctx context.Context, jobID string) (map[string]any, error) {
	outputs, err := m.broker.Outputs(ctx, jobID)
	if err != nil {
		return nil, err
	}
	objectID, ok := outputs["candidates"]
	if !ok {
		return nil, errors.New("the search finished without saying what it found")
	}
	object, err := m.objects.Object(ctx, objectID)
	if err != nil {
		return nil, err
	}
	body, err := m.objects.Open(ctx, object)
	if err != nil {
		return nil, err
	}
	defer body.Close()
	raw, err := io.ReadAll(io.LimitReader(body, 16<<20))
	if err != nil {
		return nil, err
	}
	found, err := reconstructing.ReadObject(raw)
	if err != nil {
		return nil, fmt.Errorf("the search's candidates.json could not be read: %w", err)
	}
	if list, ok := found["candidates"].([]any); !ok || len(list) == 0 {
		return nil, errors.New("the search found nowhere in the place the reef fits; try a wider search, or a place of its own")
	}
	return found, nil
}

// Accept chooses where the reef goes, from what the search found or by hand,
// and starts laying it in.
func (m *Mapper) Accept(ctx context.Context, id string, choice Choice) (Mapping, error) {
	mp, err := scanMapping(m.pool.QueryRow(ctx, selectMapping+` WHERE id = $1`, id))
	if err != nil {
		return Mapping{}, err
	}
	if mp.LayJobID != "" {
		return Mapping{}, fmt.Errorf("%w: this mapping's reef is already being laid in", domain.ErrInvalid)
	}
	return m.lay(ctx, id, func(mp Mapping) (map[string]any, string, error) {
		if mp.Mode != Onto || mp.Candidates == nil || mp.LayJobID != "" || mp.Failure != "" {
			return nil, "", fmt.Errorf("%w: only a mapping choosing where its reef goes can be accepted", domain.ErrInvalid)
		}
		placement, err := placementOf(choice, mp.Candidates)
		return placement, mp.BaseVersionID, err
	})
}

// lay starts the job that lays the reef into a version of its place, once:
// choose says where, and into which version.
func (m *Mapper) lay(ctx context.Context, id string, choose func(Mapping) (map[string]any, string, error)) (Mapping, error) {
	return m.locked(ctx, id, func(conn db.Conn, mp Mapping) error {
		if mp.LayJobID != "" || mp.Failure != "" {
			return errDone
		}
		placement, versionID, err := choose(mp)
		if err != nil {
			return err
		}
		made, err := m.reconstructor.Reconstruction(ctx, mp.ReconstructionID)
		if err != nil {
			return err
		}
		inputs, err := m.inputs(ctx, versionID, made.ID, true)
		if err != nil {
			return err
		}
		said, err := json.Marshal(map[string]any{
			"name": handleOf(made.Name), "placement": placement,
			"video": map[string]any{"name": made.Brief.Video.Name, "objectId": made.Brief.Video.ObjectID,
				"reconstructionId": made.ID},
			"sink": 1.0, "clear": 1.5,
		})
		if err != nil {
			return err
		}
		job, err := m.broker.Submit(ctx, exec.JobSpec{
			OrgID: mp.OrgID, SubmittedBy: mp.CreatedBy, RecipeID: LayRecipe,
			ImageDigest: m.settings.Image,
			Command:     []string{"python", "-m", "iocean_reconstruct.lay"},
			Args:        []string{string(said)},
			Inputs:      inputs,
			Outputs: []exec.Output{{Name: "place", RelativePath: "place.tar",
				MediaType: "application/x-tar", MaxSizeBytes: m.settings.PackageBytes}},
			RequestCPU: m.settings.LayCPU, RequestMemoryBytes: m.settings.LayMemoryBytes,
			RequestGPU:      m.settings.LayGPU,
			WalltimeSeconds: m.settings.LayWalltimeSeconds,
			Egress:          exec.NoEgress,
		})
		if err != nil {
			return err
		}
		chosen, err := json.Marshal(placement)
		if err != nil {
			return err
		}
		_, err = conn.Exec(ctx, `
			UPDATE catalog.mapping SET chosen = $2, base_version_id = $3, lay_job_id = $4 WHERE id = $1`,
			id, chosen, versionID, job.ID)
		return err
	})
}

// claim starts keeping the place the lay job made, unless somebody else
// already is. Like a reconstruction's, it runs on its own: a place with a reef
// in it is tens of gigabytes.
func (m *Mapper) claim(ctx context.Context, mp Mapping) error {
	tag, err := m.pool.Exec(ctx, `
		UPDATE catalog.mapping SET recorded_at = now()
		WHERE id = $1 AND version_id IS NULL AND failure IS NULL
		  AND (recorded_at IS NULL OR recorded_at < now() - $2::interval)`,
		mp.ID, fmt.Sprintf("%d seconds", int(staleAfter.Seconds())))
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return nil
	}
	go func() {
		recording, cancel := context.WithTimeout(context.WithoutCancel(ctx), staleAfter)
		defer cancel()
		_ = m.record(recording, mp)
	}()
	return nil
}

// record keeps the place the lay job made as a draft version of it.
func (m *Mapper) record(ctx context.Context, mp Mapping) error {
	versionID, err := m.version(ctx, mp)
	if err == nil {
		_, err = m.pool.Exec(ctx, `UPDATE catalog.mapping SET version_id = $2 WHERE id = $1`, mp.ID, versionID)
	}
	if err != nil {
		_, _ = m.pool.Exec(context.WithoutCancel(ctx),
			`UPDATE catalog.mapping SET failure = $2 WHERE id = $1`, mp.ID, err.Error())
	}
	return err
}

func (m *Mapper) version(ctx context.Context, mp Mapping) (string, error) {
	outputs, err := m.broker.Outputs(ctx, mp.LayJobID)
	if err != nil {
		return "", err
	}
	objectID, ok := outputs["place"]
	if !ok {
		return "", errors.New("the lay job finished without a place")
	}
	made, err := m.reconstructor.Reconstruction(ctx, mp.ReconstructionID)
	if err != nil {
		return "", err
	}
	versionID, _, err := m.builder.Package(ctx, objectID, building.Made{
		CityID: mp.CityID, OrgID: mp.OrgID, CreatedBy: mp.CreatedBy,
		Label: made.Name + " laid in",
		Notes: fmt.Sprintf("the reef reconstructed as %s, laid in by %s", made.ID, mp.ID),
	})
	return versionID, err
}
