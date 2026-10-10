// Package building builds places from their data on the platform's machines.
//
// Somebody names a square on Earth and the data to build it from: the public
// sources (the global depth grid, satellite imagery, the laser altimeter's
// depths, the coral atlas) and their own files (a depth survey, soundings, a
// photo mosaic). The platform runs the places module as a job with that brief,
// the job reports each step as it goes, and the package it makes becomes a
// draft version of the place, which the place's curators then publish.
//
// The job's image is the platform's, named in configuration, and nothing in
// the brief chooses what runs: that is why a build may reach the network to
// fetch public data when an organisation's own job may not (ADR-0012).
package building

import (
	"archive/tar"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math"
	"os"
	"path"
	"regexp"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/catalog"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/exec"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
	"github.com/jalalirs/auv/services/control-plane/internal/storage"
)

// Recipe is what the job is recorded as having been made by.
const Recipe = "places-build/v1"

// ErrNotConfigured reports a platform with no image to build places with.
var ErrNotConfigured = errors.New("this platform has no image to build places with")

// Settings are how a build runs.
type Settings struct {
	// Image is the places module's image, by digest.
	Image           string
	CPU             float64
	MemoryBytes     int64
	WalltimeSeconds int
	// PackageBytes is the largest package a build may make.
	PackageBytes int64
}

// Sources are the public data a build may draw on, in the words the places
// module uses.
var Sources = map[string]string{
	"gebco":             "the global depth grid (GEBCO): everywhere, coarse",
	"sentinel2":         "satellite imagery (Sentinel-2): depth estimated from colour in clear shallow water",
	"icesat2":           "the laser altimeter's depths (ICESat-2): measured, along tracks",
	"allen-coral-atlas": "the Allen Coral Atlas: where reef, sand and seagrass are",
	"learned-depth":     "the learned depth model: depth from imagery, corrected by the laser's depths",
}

// FileUses are the kinds of file somebody can add.
var FileUses = map[string]string{
	"raster": "a depth map (GeoTIFF or any grid GDAL reads)",
	"points": "soundings (XYZ or CSV)",
	"ortho":  "a photo mosaic (orthomosaic GeoTIFF)",
}

// File is one of somebody's own files a build uses.
type File struct {
	ObjectID string  `json:"objectId"`
	Use      string  `json:"use"`
	Name     string  `json:"name,omitempty"`
	ErrorM   float64 `json:"errorM,omitempty"`
	Datum    string  `json:"datum,omitempty"`
	Citation string  `json:"citation,omitempty"`
	// Path is where the job finds it, filled in when the build starts.
	Path string `json:"path,omitempty"`
}

// Brief is what a build is asked to make.
type Brief struct {
	// Centre is latitude, longitude in degrees.
	Centre  [2]float64 `json:"centre"`
	AcrossM float64    `json:"acrossM"`
	Cells   int        `json:"cells,omitempty"`
	Sources []string   `json:"sources"`
	Files   []File     `json:"files,omitempty"`
	Label   string     `json:"label,omitempty"`
	// Name and slug of the place, for the package's own record.
	Name string `json:"name,omitempty"`
	Slug string `json:"slug,omitempty"`
}

// Validate reports whether a brief describes something that can be built.
func (b Brief) Validate() error {
	lat, lon := b.Centre[0], b.Centre[1]
	if math.IsNaN(lat) || lat < -85 || lat > 85 || math.IsNaN(lon) || lon < -180 || lon > 180 {
		return fmt.Errorf("%w: the centre is latitude, longitude in degrees", domain.ErrInvalid)
	}
	if b.AcrossM < 100 || b.AcrossM > 20000 {
		return fmt.Errorf("%w: a place is between 100 m and 20 km across", domain.ErrInvalid)
	}
	if b.Cells != 0 && (b.Cells < 64 || b.Cells > 2048) {
		return fmt.Errorf("%w: a place is 64 to 2048 cells across", domain.ErrInvalid)
	}
	depth := false
	for _, s := range b.Sources {
		if _, known := Sources[s]; !known {
			return fmt.Errorf("%w: no source called %q (there are: %s)", domain.ErrInvalid, s, sourceNames())
		}
		if s != "allen-coral-atlas" {
			depth = true
		}
	}
	for _, f := range b.Files {
		if _, known := FileUses[f.Use]; !known {
			return fmt.Errorf("%w: a file is used as raster, points or ortho, not %q", domain.ErrInvalid, f.Use)
		}
		if f.ObjectID == "" {
			return fmt.Errorf("%w: a file names the object it was uploaded as", domain.ErrInvalid)
		}
		if f.Use != "ortho" {
			depth = true
		}
	}
	if !depth {
		return fmt.Errorf("%w: a place needs something that says how deep it is (gebco is everywhere)",
			domain.ErrInvalid)
	}
	return nil
}

func sourceNames() string {
	names := make([]string, 0, len(Sources))
	for name := range Sources {
		names = append(names, name)
	}
	return strings.Join(names, ", ")
}

// Builder runs builds.
type Builder struct {
	pool     *db.Pool
	broker   *exec.Broker
	objects  *storage.Objects
	catalog  *catalog.Store
	settings Settings
}

// New builds a Builder.
func New(pool *db.Pool, broker *exec.Broker, objects *storage.Objects, store *catalog.Store, settings Settings) *Builder {
	if settings.CPU == 0 {
		settings.CPU = 4
	}
	if settings.MemoryBytes == 0 {
		settings.MemoryBytes = 12 << 30
	}
	if settings.WalltimeSeconds == 0 {
		settings.WalltimeSeconds = 3 * 3600
	}
	if settings.PackageBytes == 0 {
		settings.PackageBytes = 8 << 30
	}
	return &Builder{pool: pool, broker: broker, objects: objects, catalog: store, settings: settings}
}

// Build is the record of one build.
type Build struct {
	ID         string         `json:"id"`
	CityID     string         `json:"cityId"`
	OrgID      string         `json:"orgId"`
	JobID      string         `json:"jobId"`
	Brief      Brief          `json:"brief"`
	VersionID  string         `json:"versionId,omitempty"`
	Result     map[string]any `json:"result,omitempty"`
	Failure    string         `json:"failure,omitempty"`
	CreatedBy  string         `json:"createdBy"`
	CreatedAt  time.Time      `json:"createdAt"`
	RecordedAt *time.Time     `json:"recordedAt,omitempty"`
}

var safeName = regexp.MustCompile(`[^A-Za-z0-9._-]+`)

// Start asks for a place to be built. orgID is the organisation the work and
// the package's bytes belong to.
func (b *Builder) Start(ctx context.Context, principalID, orgID string, city catalog.City, brief Brief) (Build, error) {
	if b.settings.Image == "" {
		return Build{}, ErrNotConfigured
	}
	if err := brief.Validate(); err != nil {
		return Build{}, err
	}
	brief.Name, brief.Slug = city.Name, city.Slug

	inputs := make([]exec.Input, 0, len(brief.Files))
	for i := range brief.Files {
		f := &brief.Files[i]
		object, err := b.objects.Object(ctx, f.ObjectID)
		if err != nil {
			return Build{}, fmt.Errorf("%w: no object %s", domain.ErrInvalid, f.ObjectID)
		}
		var held bool
		if err := b.pool.QueryRow(ctx,
			`SELECT EXISTS (SELECT 1 FROM store.holding WHERE org_id = $1 AND object_id = $2)`,
			orgID, f.ObjectID).Scan(&held); err != nil {
			return Build{}, err
		}
		if !held {
			return Build{}, fmt.Errorf("%w: the organisation does not hold %s; upload it first", domain.ErrInvalid, f.ObjectID)
		}
		name := safeName.ReplaceAllString(path.Base(f.Name), "_")
		if name == "" || name == "." || name == "_" {
			name = "file"
		}
		f.Path = fmt.Sprintf("files/%02d-%s", i+1, name)
		inputs = append(inputs, exec.Input{
			Name: fmt.Sprintf("file-%02d", i+1), RelativePath: f.Path, ObjectID: object.ID,
			SHA256: object.SHA256, MediaType: object.MediaType, SizeBytes: object.SizeBytes,
		})
	}
	said, err := json.Marshal(brief)
	if err != nil {
		return Build{}, err
	}

	job, err := b.broker.Submit(ctx, exec.JobSpec{
		OrgID: orgID, SubmittedBy: principalID, RecipeID: Recipe,
		ImageDigest: b.settings.Image,
		Command:     []string{"python", "-m", "iocean_places.job"},
		Args:        []string{string(said)},
		Inputs:      inputs,
		Outputs: []exec.Output{{Name: "place", RelativePath: "place.tar",
			MediaType: "application/x-tar", MaxSizeBytes: b.settings.PackageBytes}},
		RequestCPU: b.settings.CPU, RequestMemoryBytes: b.settings.MemoryBytes,
		WalltimeSeconds: b.settings.WalltimeSeconds,
		// Public data is fetched from where it is published.
		Egress: exec.InternetEgress,
	})
	if err != nil {
		return Build{}, err
	}

	build := Build{ID: ids.New(ids.KindBuild), CityID: city.ID, OrgID: orgID, JobID: job.ID,
		Brief: brief, CreatedBy: principalID}
	err = b.pool.QueryRow(ctx, `
		INSERT INTO catalog.build (id, city_id, org_id, job_id, brief, created_by)
		VALUES ($1, $2, $3, $4, $5, $6) RETURNING created_at`,
		build.ID, build.CityID, build.OrgID, build.JobID, said, principalID).Scan(&build.CreatedAt)
	if err != nil {
		return Build{}, fmt.Errorf("recording a build: %w", err)
	}
	return build, nil
}

const selectBuild = `
	SELECT id, city_id, org_id, job_id, brief, coalesce(version_id, ''), result,
	       coalesce(failure, ''), created_by, created_at, recorded_at
	FROM catalog.build`

func scanBuild(row interface{ Scan(...any) error }) (Build, error) {
	var b Build
	var brief, result []byte
	if err := row.Scan(&b.ID, &b.CityID, &b.OrgID, &b.JobID, &brief, &b.VersionID, &result,
		&b.Failure, &b.CreatedBy, &b.CreatedAt, &b.RecordedAt); err != nil {
		return Build{}, db.Translate(err)
	}
	if err := json.Unmarshal(brief, &b.Brief); err != nil {
		return Build{}, err
	}
	if len(result) > 0 {
		if err := json.Unmarshal(result, &b.Result); err != nil {
			return Build{}, err
		}
	}
	return b, nil
}

// CityOf names the place a build is of.
func (b *Builder) CityOf(ctx context.Context, buildID string) (string, error) {
	var city string
	err := b.pool.QueryRow(ctx, `SELECT city_id FROM catalog.build WHERE id = $1`, buildID).Scan(&city)
	return city, db.Translate(err)
}

// Builds lists a place's builds, newest first.
func (b *Builder) Builds(ctx context.Context, cityID string) ([]Build, error) {
	rows, err := b.pool.Query(ctx, selectBuild+` WHERE city_id = $1 ORDER BY created_at DESC LIMIT 50`, cityID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	builds := []Build{}
	for rows.Next() {
		one, err := scanBuild(rows)
		if err != nil {
			return nil, err
		}
		builds = append(builds, one)
	}
	return builds, rows.Err()
}

// Step is one thing a build said it was doing.
type Step struct {
	At     time.Time      `json:"at"`
	Step   string         `json:"step"`
	Say    string         `json:"say"`
	N      int            `json:"n,omitempty"`
	Of     int            `json:"of,omitempty"`
	Detail map[string]any `json:"detail,omitempty"`
}

// View is a build as somebody watching it sees it.
type View struct {
	Build
	// State is the build's, not the job's: queued, running, recording (the
	// package is being turned into a version), ready, or failed.
	State    string `json:"state"`
	JobState string `json:"jobState"`
	Steps    []Step `json:"steps"`
	// Said is the end of what the build printed, when it failed.
	Said string `json:"said,omitempty"`
}

// Watch reads a build, and when its job has finished, turns the package it
// made into a draft version of the place, once.
func (b *Builder) Watch(ctx context.Context, buildID string) (View, error) {
	build, err := scanBuild(b.pool.QueryRow(ctx, selectBuild+` WHERE id = $1`, buildID))
	if err != nil {
		return View{}, err
	}
	job, err := b.broker.Job(ctx, build.JobID)
	if err != nil {
		return View{}, err
	}
	view := View{Build: build, JobState: string(job.State), Steps: []Step{}}
	events, err := b.broker.Events(ctx, build.JobID, 0, 1000)
	if err != nil {
		return View{}, err
	}
	for _, e := range events {
		if e.Kind != exec.EventProgress {
			continue
		}
		if said, ok := e.Detail["progress"].(map[string]any); ok {
			view.Steps = append(view.Steps, stepOf(e.OccurredAt, said))
		}
		if out, ok := e.Detail["output"].(string); ok {
			view.Said = out
		}
	}

	switch job.State {
	case exec.Pending, exec.Admitted:
		view.State = "queued"
	case exec.Running:
		view.State = "running"
	case exec.Succeeded:
		if build.VersionID == "" && build.Failure == "" {
			if err := b.record(ctx, &view.Build); err != nil {
				view.Failure = err.Error()
			}
		}
		switch {
		case view.VersionID != "":
			view.State = "ready"
		case view.Failure != "":
			view.State = "failed"
		default:
			view.State = "recording"
		}
	default:
		view.State = "failed"
		if view.Failure == "" {
			view.Failure = fmt.Sprintf("the build's job %s (%s)", job.State, job.FailureClass)
		}
	}
	if view.State != "failed" {
		view.Said = ""
	} else if len(view.Said) > 4000 {
		view.Said = view.Said[len(view.Said)-4000:]
	}
	return view, nil
}

func stepOf(at time.Time, said map[string]any) Step {
	step := Step{At: at, Detail: map[string]any{}}
	for k, v := range said {
		switch k {
		case "step":
			step.Step, _ = v.(string)
		case "say":
			step.Say, _ = v.(string)
		case "n":
			if f, ok := v.(float64); ok {
				step.N = int(f)
			}
		case "of":
			if f, ok := v.(float64); ok {
				step.Of = int(f)
			}
		default:
			step.Detail[k] = v
		}
	}
	if len(step.Detail) == 0 {
		step.Detail = nil
	}
	return step
}

// record turns the package a finished build made into a draft version.
func (b *Builder) record(ctx context.Context, build *Build) error {
	// Claimed first, so two people watching do not both record it.
	tag, err := b.pool.Exec(ctx,
		`UPDATE catalog.build SET recorded_at = now() WHERE id = $1 AND recorded_at IS NULL`, build.ID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return nil
	}
	versionID, result, err := b.unpack(ctx, *build)
	if err != nil {
		_, _ = b.pool.Exec(context.WithoutCancel(ctx),
			`UPDATE catalog.build SET failure = $2 WHERE id = $1`, build.ID, err.Error())
		build.Failure = err.Error()
		return err
	}
	said, _ := json.Marshal(result)
	if _, err := b.pool.Exec(ctx,
		`UPDATE catalog.build SET version_id = $2, result = $3 WHERE id = $1`,
		build.ID, versionID, said); err != nil {
		return err
	}
	build.VersionID, build.Result = versionID, result
	return nil
}

func (b *Builder) unpack(ctx context.Context, build Build) (string, map[string]any, error) {
	outputs, err := b.broker.Outputs(ctx, build.JobID)
	if err != nil {
		return "", nil, err
	}
	objectID, ok := outputs["place"]
	if !ok {
		return "", nil, errors.New("the build finished without a package")
	}
	object, err := b.objects.Object(ctx, objectID)
	if err != nil {
		return "", nil, err
	}
	body, err := b.objects.Open(ctx, object)
	if err != nil {
		return "", nil, err
	}
	defer body.Close()

	var manifest []domain.ManifestEntry
	var site []byte
	archive := tar.NewReader(body)
	for {
		header, err := archive.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return "", nil, fmt.Errorf("reading the package: %w", err)
		}
		if header.Typeflag != tar.TypeReg {
			continue
		}
		name := path.Clean(strings.TrimPrefix(header.Name, "./"))
		if name == "." || strings.HasPrefix(name, "..") || path.IsAbs(name) {
			return "", nil, fmt.Errorf("the package names a file outside itself: %s", header.Name)
		}
		entry, contents, err := b.keep(ctx, build, name, archive, header.Size, name == "site.json")
		if err != nil {
			return "", nil, err
		}
		if contents != nil {
			site = contents
		}
		manifest = append(manifest, entry)
	}
	if site == nil {
		return "", nil, errors.New("the package has no site.json, so nothing could open it")
	}

	label := build.Brief.Label
	if label == "" {
		label = "built " + time.Now().UTC().Format("2006-01-02")
	}
	var version catalog.Version
	err = b.pool.InTransaction(ctx, func(conn db.Conn) error {
		var err error
		version, err = b.catalog.CreateVersion(ctx, conn, catalog.VersionSpec{
			AssetKind: catalog.KindCity, AssetID: build.CityID, Label: label,
			Notes:    fmt.Sprintf("built by %s from %s", build.ID, describe(build.Brief)),
			Manifest: manifest, CreatedBy: build.CreatedBy,
		})
		return err
	})
	if err != nil {
		return "", nil, err
	}
	return version.ID, resultOf(site), nil
}

// keep stores one file of the package; it hands back site.json's contents.
func (b *Builder) keep(ctx context.Context, build Build, name string, from io.Reader, size int64, wanted bool) (domain.ManifestEntry, []byte, error) {
	scratch, err := os.CreateTemp("", "iocean-build-*")
	if err != nil {
		return domain.ManifestEntry{}, nil, err
	}
	defer os.Remove(scratch.Name())
	defer scratch.Close()
	if _, err := io.CopyN(scratch, from, size); err != nil {
		return domain.ManifestEntry{}, nil, fmt.Errorf("reading %s from the package: %w", name, err)
	}
	if _, err := scratch.Seek(0, io.SeekStart); err != nil {
		return domain.ManifestEntry{}, nil, err
	}
	media := mediaTypeOf(name)
	object, err := b.objects.Ingest(ctx, build.CreatedBy, build.OrgID, domain.Evidence, scratch, size, media)
	if err != nil {
		return domain.ManifestEntry{}, nil, err
	}
	var contents []byte
	if wanted {
		if _, err := scratch.Seek(0, io.SeekStart); err != nil {
			return domain.ManifestEntry{}, nil, err
		}
		if contents, err = io.ReadAll(scratch); err != nil {
			return domain.ManifestEntry{}, nil, err
		}
	}
	return domain.ManifestEntry{RelativePath: name, Digest: object.Digest, SizeBytes: size, MediaType: media}, contents, nil
}

func mediaTypeOf(name string) string {
	switch strings.ToLower(path.Ext(name)) {
	case ".usd", ".usda", ".usdc", ".usdz":
		return "model/vnd.usd"
	case ".png":
		return "image/png"
	case ".jpg", ".jpeg":
		return "image/jpeg"
	case ".json":
		return "application/json"
	case ".mdl":
		return "text/plain"
	default:
		return "application/octet-stream"
	}
}

func describe(brief Brief) string {
	parts := append([]string{}, brief.Sources...)
	for _, f := range brief.Files {
		parts = append(parts, f.Use+" "+f.Name)
	}
	return strings.Join(parts, ", ")
}

// resultOf keeps what a place's record says about how it was made and where
// it is weak.
func resultOf(site []byte) map[string]any {
	var record map[string]any
	if json.Unmarshal(site, &record) != nil {
		return nil
	}
	result := map[string]any{}
	if from, ok := record["from"].(map[string]any); ok {
		if depth, ok := from["depth"]; ok {
			result["depth"] = depth
		}
	}
	for _, key := range []string{"deepestM", "shallowestM", "beginAt", "perCell", "reef", "name"} {
		if v, ok := record[key]; ok {
			result[key] = v
		}
	}
	return result
}
