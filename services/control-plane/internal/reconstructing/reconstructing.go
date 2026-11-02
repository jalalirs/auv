// Package reconstructing makes reefs from dive videos on the platform's
// machines.
//
// Somebody uploads a video of a swim over a reef and asks for it to be
// reconstructed. The platform runs the reconstruction module as a job on a
// GPU with that brief, the job reports each step as it goes, and what it makes
// (the reef as Gaussian splats in pieces, the ground surface under it, the
// path the camera took, pictures of it) becomes objects the organisation
// holds. A reconstruction is an asset of its own: laying it into a place is a
// separate act, and this package does not do it.
//
// The job's image is the platform's, named in configuration, and it runs with
// no network at all: its weights are in the image, and the video is the only
// thing it reads.
package reconstructing

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

	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/exec"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
	"github.com/jalalirs/auv/services/control-plane/internal/storage"
)

// Recipe is what the job is recorded as having been made by.
const Recipe = "reconstruct-video/v1"

// Manifest is the file in the package that says what the rest of it is.
const Manifest = "reconstruction.json"

// ErrNotConfigured reports a platform with no image to reconstruct reefs with.
var ErrNotConfigured = errors.New("this platform has no image to reconstruct reefs with")

// Settings are how a reconstruction runs.
type Settings struct {
	// Image is the reconstruction module's image, by digest.
	Image           string
	CPU             float64
	MemoryBytes     int64
	GPU             int
	WalltimeSeconds int
	// PackageBytes is the largest package a reconstruction may make.
	PackageBytes int64
	// The import job, which makes a structure or a survey into an asset in
	// the same image, is work for processors: no GPU.
	ImportCPU             float64
	ImportMemoryBytes     int64
	ImportWalltimeSeconds int
	ImportPackageBytes    int64
}

// Video is the dive video a reconstruction is made from.
type Video struct {
	ObjectID string `json:"objectId"`
	// Name is the file's own name, which is what the job is told it is.
	Name string `json:"name,omitempty"`
	// Path is where the job finds it, filled in when the reconstruction
	// starts.
	Path string `json:"path,omitempty"`
}

// Point is somewhere on Earth, in degrees.
type Point struct {
	Lat float64 `json:"lat"`
	Lon float64 `json:"lon"`
}

// Brief is what a reconstruction is asked to make.
type Brief struct {
	Video Video  `json:"video"`
	Label string `json:"label,omitempty"`
	// CameraHeightM is how high over the reef the camera was, in metres,
	// which is what gives the reef its scale. When nobody says, the job
	// assumes 1.92 m and says that it did.
	CameraHeightM *float64 `json:"cameraHeightM,omitempty"`
	// Start is where the video starts. It is recorded, not used: placing the
	// reef is mapping's work.
	Start *Point `json:"start,omitempty"`
	// FPS is how many frames a second of video are read. Two when nobody
	// says.
	FPS float64 `json:"fps,omitempty"`
	// Tape is what is done with a survey tape in the frames: auto finds it
	// and takes it out, keep leaves it in.
	Tape string `json:"tape,omitempty"`
	// Structure, when the video is of a structure rather than a reef (a
	// pipeline an AUV followed, say): what it is. Its splats are made and laid
	// as a reef's are; the asset is a structure of that type.
	Structure *Structure `json:"structure,omitempty"`
	// Poses, when the vehicle's own navigation says where the camera was in
	// every frame: a CSV the organisation holds (image, t, x, y, z, qw, qx,
	// qy, qz, altitudeM), used instead of COLMAP's solve, which murky water
	// defeats. Camera is the lens, at the video's resolution, and goes with it.
	Poses  *Video  `json:"poses,omitempty"`
	Camera *Camera `json:"camera,omitempty"`
	// Enhance lifts the frames' contrast before features and training
	// ("clahe"), or leaves them ("").
	Enhance string `json:"enhance,omitempty"`
}

// Camera is a lens as OpenCV's model has it, in pixels at Width by Height.
type Camera struct {
	Model  string  `json:"model"`
	Width  int     `json:"width"`
	Height int     `json:"height"`
	Fx     float64 `json:"fx"`
	Fy     float64 `json:"fy"`
	Cx     float64 `json:"cx"`
	Cy     float64 `json:"cy"`
	K1     float64 `json:"k1"`
	K2     float64 `json:"k2"`
	P1     float64 `json:"p1"`
	P2     float64 `json:"p2"`
}

// Validate reports whether a brief describes something that can be
// reconstructed. Whether the video is one, and whether the organisation holds
// it, is checked against the object when the reconstruction starts.
func (b Brief) Validate() error {
	if b.Video.ObjectID == "" {
		return fmt.Errorf("%w: a reconstruction names the video it is made from (video.objectId)", domain.ErrInvalid)
	}
	if h := b.CameraHeightM; h != nil && (math.IsNaN(*h) || *h <= 0.2 || *h > 20) {
		return fmt.Errorf("%w: the camera is between 0.2 m and 20 m over the reef", domain.ErrInvalid)
	}
	if s := b.Start; s != nil && (math.IsNaN(s.Lat) || s.Lat < -90 || s.Lat > 90 ||
		math.IsNaN(s.Lon) || s.Lon < -180 || s.Lon > 180) {
		return fmt.Errorf("%w: where the video starts is latitude and longitude in degrees", domain.ErrInvalid)
	}
	if b.FPS != 0 && (math.IsNaN(b.FPS) || b.FPS < 0.5 || b.FPS > 5) {
		return fmt.Errorf("%w: a video is read at 0.5 to 5 frames a second", domain.ErrInvalid)
	}
	switch b.Tape {
	case "", "auto", "keep":
	default:
		return fmt.Errorf("%w: a survey tape is taken out (auto) or kept (keep), not %q", domain.ErrInvalid, b.Tape)
	}
	if b.Poses != nil {
		if b.Poses.ObjectID == "" {
			return fmt.Errorf("%w: navigation poses name the file they are in (poses.objectId)", domain.ErrInvalid)
		}
		c := b.Camera
		if c == nil || c.Model != "OPENCV" || c.Width <= 0 || c.Height <= 0 || c.Fx <= 0 || c.Fy <= 0 {
			return fmt.Errorf("%w: navigation poses need the lens they were taken with (camera: OPENCV, width, height, fx, fy, cx, cy, k1, k2, p1, p2)", domain.ErrInvalid)
		}
	}
	switch b.Enhance {
	case "", "clahe":
	default:
		return fmt.Errorf("%w: frames are enhanced by clahe or not at all, not %q", domain.ErrInvalid, b.Enhance)
	}
	if s := b.Structure; s != nil && !StructureTypes[s.Type] {
		return fmt.Errorf("%w: a structure is a pipeline, platform, wind-foundation or other, not %q", domain.ErrInvalid, s.Type)
	}
	return nil
}

var videoNames = regexp.MustCompile(`(?i)\.(mp4|mov|mkv)$`)

// isVideo reports whether an object is a video, by what it was stored as or
// by what its file is called. A camera's files are often stored as
// application/octet-stream, and their name is then the better witness.
func isVideo(mediaType, name string) bool {
	return strings.HasPrefix(strings.ToLower(mediaType), "video/") || videoNames.MatchString(name)
}

var safeName = regexp.MustCompile(`[^A-Za-z0-9._-]+`)

// pathOf is where the job finds the video: its own name, made safe.
func pathOf(name, mediaType string) string {
	safe := safeName.ReplaceAllString(path.Base(name), "_")
	if safe == "" || safe == "." || safe == "_" || strings.HasPrefix(safe, "..") {
		safe = "video" + extensionOf(mediaType)
	}
	return "video/" + safe
}

func extensionOf(mediaType string) string {
	switch strings.ToLower(mediaType) {
	case "video/quicktime":
		return ".mov"
	case "video/x-matroska", "video/matroska":
		return ".mkv"
	default:
		return ".mp4"
	}
}

// nameOf is what a reconstruction is called when nobody named it: its label,
// or the video it came from.
func nameOf(brief Brief) string {
	if label := strings.TrimSpace(brief.Label); label != "" {
		return label
	}
	name := path.Base(brief.Video.Path)
	if stem := strings.TrimSuffix(name, path.Ext(name)); stem != "" {
		return stem
	}
	return "a reconstruction"
}

// held reads an object the organisation holds, or says why it cannot be used.
func (r *Reconstructor) held(ctx context.Context, orgID, objectID string) (storage.Object, error) {
	object, err := r.objects.Object(ctx, objectID)
	if err != nil {
		return storage.Object{}, fmt.Errorf("%w: no object %s", domain.ErrInvalid, objectID)
	}
	var held bool
	if err := r.pool.QueryRow(ctx,
		`SELECT EXISTS (SELECT 1 FROM store.holding WHERE org_id = $1 AND object_id = $2)`,
		orgID, object.ID).Scan(&held); err != nil {
		return storage.Object{}, err
	}
	if !held {
		return storage.Object{}, fmt.Errorf("%w: the organisation does not hold %s; upload it first", domain.ErrInvalid, object.ID)
	}
	return object, nil
}

// Reconstructor runs reconstructions.
type Reconstructor struct {
	pool     *db.Pool
	broker   *exec.Broker
	objects  *storage.Objects
	settings Settings
}

// New builds a Reconstructor.
func New(pool *db.Pool, broker *exec.Broker, objects *storage.Objects, settings Settings) *Reconstructor {
	if settings.CPU == 0 {
		settings.CPU = 8
	}
	if settings.MemoryBytes == 0 {
		settings.MemoryBytes = 48 << 30
	}
	if settings.GPU == 0 {
		settings.GPU = 1
	}
	if settings.WalltimeSeconds == 0 {
		settings.WalltimeSeconds = 14 * 3600
	}
	if settings.PackageBytes == 0 {
		settings.PackageBytes = 40 << 30
	}
	if settings.ImportCPU == 0 {
		settings.ImportCPU = 4
	}
	if settings.ImportMemoryBytes == 0 {
		settings.ImportMemoryBytes = 8 << 30
	}
	if settings.ImportWalltimeSeconds == 0 {
		settings.ImportWalltimeSeconds = 2 * 3600
	}
	if settings.ImportPackageBytes == 0 {
		// A survey is carried as it was uploaded, beside its preview.
		settings.ImportPackageBytes = 16 << 30
	}
	return &Reconstructor{pool: pool, broker: broker, objects: objects, settings: settings}
}

// Reconstruction is the record of one reconstruction: a reef from a video,
// or any other asset (a structure, a survey) the import job made.
type Reconstruction struct {
	ID    string `json:"id"`
	OrgID string `json:"orgId"`
	JobID string `json:"jobId"`
	// Brief is a reef's, made from a video; Asset is the import job's brief
	// for anything else.
	Brief Brief       `json:"brief"`
	Asset *AssetBrief `json:"asset,omitempty"`
	Name  string      `json:"name"`
	// Kind is reef, structure or bathymetry; MadeFrom is video, survey, model
	// or route; Structure is a structure's type and how it meets the seabed.
	Kind      string     `json:"kind"`
	MadeFrom  string     `json:"madeFrom"`
	Structure *Structure `json:"structure,omitempty"`
	// Manifest is what the reconstruction said about itself, once it has
	// been recorded.
	Manifest   map[string]any `json:"manifest,omitempty"`
	Failure    string         `json:"failure,omitempty"`
	CreatedBy  string         `json:"createdBy"`
	CreatedAt  time.Time      `json:"createdAt"`
	RecordedAt *time.Time     `json:"recordedAt,omitempty"`
}

// Start asks for a reef to be reconstructed from a video the organisation
// holds. orgID is the organisation the work and what it makes belong to.
func (r *Reconstructor) Start(ctx context.Context, principalID, orgID string, brief Brief) (Reconstruction, error) {
	if r.settings.Image == "" {
		return Reconstruction{}, ErrNotConfigured
	}
	if err := brief.Validate(); err != nil {
		return Reconstruction{}, err
	}
	object, err := r.held(ctx, orgID, brief.Video.ObjectID)
	if err != nil {
		return Reconstruction{}, err
	}
	if !isVideo(object.MediaType, brief.Video.Name) {
		return Reconstruction{}, fmt.Errorf("%w: %s is %s, not a video (an .mp4, .mov or .mkv)",
			domain.ErrInvalid, object.ID, object.MediaType)
	}
	brief.Video.Path = pathOf(brief.Video.Name, object.MediaType)
	if brief.Video.Name == "" {
		brief.Video.Name = path.Base(brief.Video.Path)
	}
	// Written down as the job will use them, so the record says what was
	// done rather than what was left to a default.
	if brief.FPS == 0 {
		brief.FPS = 2
	}
	if brief.Tape == "" {
		brief.Tape = "auto"
	}
	inputs := []exec.Input{{Name: "video", RelativePath: brief.Video.Path, ObjectID: object.ID,
		SHA256: object.SHA256, MediaType: object.MediaType, SizeBytes: object.SizeBytes}}
	if brief.Poses != nil {
		poses, err := r.held(ctx, orgID, brief.Poses.ObjectID)
		if err != nil {
			return Reconstruction{}, err
		}
		if brief.Poses.Name == "" {
			brief.Poses.Name = "poses.csv"
		}
		brief.Poses.Path = "poses/" + path.Base(brief.Poses.Name)
		inputs = append(inputs, exec.Input{Name: "poses", RelativePath: brief.Poses.Path, ObjectID: poses.ID,
			SHA256: poses.SHA256, MediaType: poses.MediaType, SizeBytes: poses.SizeBytes})
	}
	said, err := json.Marshal(brief)
	if err != nil {
		return Reconstruction{}, err
	}

	job, err := r.broker.Submit(ctx, exec.JobSpec{
		OrgID: orgID, SubmittedBy: principalID, RecipeID: Recipe,
		ImageDigest: r.settings.Image,
		Command:     []string{"python", "-m", "iocean_reconstruct.job"},
		Args:        []string{string(said)},
		Inputs:      inputs,
		Outputs: []exec.Output{{Name: "reconstruction", RelativePath: "reconstruction.tar",
			MediaType: "application/x-tar", MaxSizeBytes: r.settings.PackageBytes}},
		RequestCPU: r.settings.CPU, RequestMemoryBytes: r.settings.MemoryBytes,
		RequestGPU:      r.settings.GPU,
		WalltimeSeconds: r.settings.WalltimeSeconds,
		// The weights are in the image and the video is staged: there is
		// nothing on the network the job needs.
		Egress: exec.NoEgress,
	})
	if err != nil {
		return Reconstruction{}, err
	}

	made := Reconstruction{ID: ids.New(ids.KindReconstruction), OrgID: orgID, JobID: job.ID,
		Brief: brief, Name: nameOf(brief), Kind: KindReef, MadeFrom: FromVideo, CreatedBy: principalID}
	var structure []byte
	if brief.Structure != nil {
		made.Kind, made.Structure = KindStructure, &Structure{Type: brief.Structure.Type, Meets: Rebuilt}
		if structure, err = json.Marshal(made.Structure); err != nil {
			return Reconstruction{}, err
		}
	}
	err = r.pool.QueryRow(ctx, `
		INSERT INTO catalog.reconstruction (id, org_id, job_id, brief, name, created_by, kind, structure)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8) RETURNING created_at`,
		made.ID, made.OrgID, made.JobID, said, made.Name, principalID, made.Kind, structure).Scan(&made.CreatedAt)
	if err != nil {
		return Reconstruction{}, fmt.Errorf("recording a reconstruction: %w", err)
	}
	return made, nil
}

const selectReconstruction = `
	SELECT id, org_id, job_id, brief, name, manifest, coalesce(failure, ''),
	       created_by, created_at, recorded_at, kind, made_from, structure
	FROM catalog.reconstruction`

func scanReconstruction(row interface{ Scan(...any) error }) (Reconstruction, error) {
	var made Reconstruction
	var brief, manifest, structure []byte
	if err := row.Scan(&made.ID, &made.OrgID, &made.JobID, &brief, &made.Name, &manifest,
		&made.Failure, &made.CreatedBy, &made.CreatedAt, &made.RecordedAt,
		&made.Kind, &made.MadeFrom, &structure); err != nil {
		return Reconstruction{}, db.Translate(err)
	}
	if made.MadeFrom == FromVideo {
		if err := json.Unmarshal(brief, &made.Brief); err != nil {
			return Reconstruction{}, err
		}
	} else {
		made.Asset = &AssetBrief{}
		if err := json.Unmarshal(brief, made.Asset); err != nil {
			return Reconstruction{}, err
		}
	}
	if len(structure) > 0 && string(structure) != "null" {
		made.Structure = &Structure{}
		if err := json.Unmarshal(structure, made.Structure); err != nil {
			return Reconstruction{}, err
		}
	}
	if len(manifest) > 0 {
		if err := json.Unmarshal(manifest, &made.Manifest); err != nil {
			return Reconstruction{}, err
		}
	}
	return made, nil
}

// Reconstruction reads one reconstruction's record.
func (r *Reconstructor) Reconstruction(ctx context.Context, id string) (Reconstruction, error) {
	return scanReconstruction(r.pool.QueryRow(ctx, selectReconstruction+` WHERE id = $1`, id))
}

// OrgOf names the organisation a reconstruction belongs to.
func (r *Reconstructor) OrgOf(ctx context.Context, id string) (string, error) {
	var org string
	err := r.pool.QueryRow(ctx, `SELECT org_id FROM catalog.reconstruction WHERE id = $1`, id).Scan(&org)
	return org, db.Translate(err)
}

// List lists an organisation's reconstructions, newest first: its reefs made
// from videos, which is what the reconstruction routes have always listed.
func (r *Reconstructor) List(ctx context.Context, orgID string) ([]Reconstruction, error) {
	return r.list(ctx, `WHERE org_id = $1 AND made_from = 'video' AND archived_at IS NULL`, orgID)
}

// Archive takes one out of its organisation's listings, keeping it: a place
// it was laid into, and a run flown there, still read it by its identifier.
// Archiving what is already archived is no error.
func (r *Reconstructor) Archive(ctx context.Context, principalID, id string) error {
	tag, err := r.pool.Exec(ctx, `
		UPDATE catalog.reconstruction SET archived_at = now(), archived_by = $2
		WHERE id = $1 AND archived_at IS NULL`, id, principalID)
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		_, err := r.OrgOf(ctx, id)
		return err
	}
	return nil
}

func (r *Reconstructor) list(ctx context.Context, where string, args ...any) ([]Reconstruction, error) {
	rows, err := r.pool.Query(ctx,
		selectReconstruction+" "+where+` ORDER BY created_at DESC LIMIT 100`, args...)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	made := []Reconstruction{}
	for rows.Next() {
		one, err := scanReconstruction(rows)
		if err != nil {
			return nil, err
		}
		made = append(made, one)
	}
	return made, rows.Err()
}

// Object is one file a reconstruction made, by the path the job wrote it at.
type Object struct {
	Path      string `json:"path"`
	ObjectID  string `json:"objectId"`
	SizeBytes int64  `json:"sizeBytes"`
	MediaType string `json:"mediaType"`
}

// Objects lists the files a reconstruction made, which is what a job that
// lays it into a place stages.
func (r *Reconstructor) Objects(ctx context.Context, id string) ([]Object, error) {
	rows, err := r.pool.Query(ctx, `
		SELECT path, object_id, size_bytes, media_type
		FROM catalog.reconstruction_object WHERE reconstruction_id = $1 ORDER BY path`, id)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	objects := []Object{}
	for rows.Next() {
		var one Object
		if err := rows.Scan(&one.Path, &one.ObjectID, &one.SizeBytes, &one.MediaType); err != nil {
			return nil, err
		}
		objects = append(objects, one)
	}
	return objects, rows.Err()
}

// Step is one thing a reconstruction said it was doing.
type Step = exec.Step

// View is a reconstruction as somebody watching it sees it.
type View struct {
	Reconstruction
	// State is the reconstruction's, not the job's: queued, running,
	// recording (what it made is being kept), ready, or failed.
	State    string `json:"state"`
	JobState string `json:"jobState"`
	// Steps are the last of what it reported. A reconstruction runs for
	// hours and says a great deal; the end is what somebody watching needs.
	Steps []Step `json:"steps"`
	// Said is the end of what the reconstruction printed, when it failed.
	Said string `json:"said,omitempty"`
}

// keptSteps is how many of a reconstruction's steps a view carries.
const keptSteps = 200

// staleAfter is how long a claim to record a reconstruction is honoured
// without a result. Recording runs beside the request that noticed the job had
// finished, and a control plane that restarted under it leaves the claim
// behind; past this, somebody watching claims it again. Recording the same
// files twice is harmless, because objects are stored by their content.
const staleAfter = 2 * time.Hour

// Watch reads a reconstruction, and when its job has finished, keeps what it
// made as objects the organisation holds, once.
func (r *Reconstructor) Watch(ctx context.Context, id string) (View, error) {
	made, err := scanReconstruction(r.pool.QueryRow(ctx, selectReconstruction+` WHERE id = $1`, id))
	if err != nil {
		return View{}, err
	}
	job, err := r.broker.Job(ctx, made.JobID)
	if err != nil {
		return View{}, err
	}
	view := View{Reconstruction: made, JobState: string(job.State)}
	var events []exec.Event
	var after int64
	// Every event, a page at a time, so the steps are the latest rather than
	// the first thousand.
	for page := 0; page < 50; page++ {
		some, err := r.broker.Events(ctx, made.JobID, after, 1000)
		if err != nil {
			return View{}, err
		}
		events = append(events, some...)
		if len(some) < 1000 {
			break
		}
		after = some[len(some)-1].Sequence
	}
	view.Steps, view.Said = exec.Progress(events)
	if len(view.Steps) > keptSteps {
		view.Steps = view.Steps[len(view.Steps)-keptSteps:]
	}

	switch job.State {
	case exec.Pending, exec.Admitted:
		view.State = "queued"
	case exec.Running:
		view.State = "running"
	case exec.Succeeded:
		switch {
		case made.Manifest != nil:
			view.State = "ready"
		case made.Failure != "":
			view.State = "failed"
		default:
			view.State = "recording"
			if err := r.claim(ctx, made); err != nil {
				return View{}, err
			}
		}
	default:
		view.State = "failed"
		if view.Failure == "" {
			view.Failure = fmt.Sprintf("the %s's job %s (%s)", map[bool]string{true: "reconstruction", false: "import"}[made.MadeFrom == FromVideo],
				job.State, job.FailureClass)
		}
	}
	if view.State != "failed" {
		view.Said = ""
	} else if len(view.Said) > 4000 {
		view.Said = view.Said[len(view.Said)-4000:]
	}
	return view, nil
}

// claim starts recording a finished reconstruction, unless somebody else
// already is.
//
// The recording runs on its own rather than on the request that noticed: a
// package is tens of gigabytes, and a watcher that gave up waiting would
// otherwise cancel it halfway and leave it failed for good.
func (r *Reconstructor) claim(ctx context.Context, made Reconstruction) error {
	tag, err := r.pool.Exec(ctx, `
		UPDATE catalog.reconstruction SET recorded_at = now()
		WHERE id = $1 AND manifest IS NULL AND failure IS NULL
		  AND (recorded_at IS NULL OR recorded_at < now() - $2::interval)`,
		made.ID, fmt.Sprintf("%d seconds", int(staleAfter.Seconds())))
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return nil
	}
	go func() {
		recording, cancel := context.WithTimeout(context.WithoutCancel(ctx), staleAfter)
		defer cancel()
		_ = r.record(recording, made)
	}()
	return nil
}

// record keeps what a finished reconstruction made, and says so in its
// record; or says why it could not.
func (r *Reconstructor) record(ctx context.Context, made Reconstruction) error {
	objects, manifest, err := r.unpack(ctx, made)
	if err == nil {
		err = r.pool.InTransaction(ctx, func(conn db.Conn) error {
			for _, one := range objects {
				if _, err := conn.Exec(ctx, `
					INSERT INTO catalog.reconstruction_object
					    (reconstruction_id, path, object_id, size_bytes, media_type)
					VALUES ($1, $2, $3, $4, $5)
					ON CONFLICT (reconstruction_id, path) DO UPDATE SET
					    object_id = EXCLUDED.object_id, size_bytes = EXCLUDED.size_bytes,
					    media_type = EXCLUDED.media_type`,
					made.ID, one.Path, one.ObjectID, one.SizeBytes, one.MediaType); err != nil {
					return fmt.Errorf("recording %s: %w", one.Path, err)
				}
			}
			said, err := json.Marshal(manifest)
			if err != nil {
				return err
			}
			_, err = conn.Exec(ctx,
				`UPDATE catalog.reconstruction SET manifest = $2 WHERE id = $1`, made.ID, said)
			return err
		})
	}
	if err != nil {
		_, _ = r.pool.Exec(context.WithoutCancel(ctx),
			`UPDATE catalog.reconstruction SET failure = $2 WHERE id = $1`, made.ID, err.Error())
	}
	return err
}

func (r *Reconstructor) unpack(ctx context.Context, made Reconstruction) ([]Object, map[string]any, error) {
	outputs, err := r.broker.Outputs(ctx, made.JobID)
	if err != nil {
		return nil, nil, err
	}
	output, manifestName := "reconstruction", Manifest
	if made.MadeFrom != FromVideo {
		output, manifestName = "asset", AssetManifest
	}
	objectID, ok := outputs[output]
	if !ok {
		return nil, nil, fmt.Errorf("the %s job finished without a package", output)
	}
	object, err := r.objects.Object(ctx, objectID)
	if err != nil {
		return nil, nil, err
	}
	body, err := r.objects.Open(ctx, object)
	if err != nil {
		return nil, nil, err
	}
	defer body.Close()

	var objects []Object
	var manifest []byte
	archive := tar.NewReader(body)
	for {
		header, err := archive.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return nil, nil, fmt.Errorf("reading the package: %w", err)
		}
		if header.Typeflag != tar.TypeReg {
			continue
		}
		name := path.Clean(strings.TrimPrefix(header.Name, "./"))
		if name == "." || strings.HasPrefix(name, "..") || path.IsAbs(name) {
			return nil, nil, fmt.Errorf("the package names a file outside itself: %s", header.Name)
		}
		one, contents, err := r.keep(ctx, made, name, archive, header.Size, name == manifestName)
		if err != nil {
			return nil, nil, err
		}
		if contents != nil {
			manifest = contents
		}
		objects = append(objects, one)
	}
	if manifest == nil {
		return nil, nil, fmt.Errorf("the package has no %s, so nothing could read it", manifestName)
	}
	record, err := ReadObject(manifest)
	if err != nil {
		return nil, nil, fmt.Errorf("the package's %s is not a JSON object: %w", manifestName, err)
	}
	paths := map[string]bool{}
	for _, one := range objects {
		paths[one.Path] = true
	}
	check := checkManifest
	if made.MadeFrom != FromVideo {
		check = func(record map[string]any, paths map[string]bool) error { return checkAsset(made, record, paths) }
	}
	if err := check(record, paths); err != nil {
		return nil, nil, err
	}
	return objects, record, nil
}

// keep stores one file of the package as evidence the organisation holds; it
// hands back the manifest's contents.
func (r *Reconstructor) keep(ctx context.Context, made Reconstruction, name string, from io.Reader, size int64, wanted bool) (Object, []byte, error) {
	scratch, err := os.CreateTemp("", "iocean-reconstruction-*")
	if err != nil {
		return Object{}, nil, err
	}
	defer os.Remove(scratch.Name())
	defer scratch.Close()
	if _, err := io.CopyN(scratch, from, size); err != nil {
		return Object{}, nil, fmt.Errorf("reading %s from the package: %w", name, err)
	}
	if _, err := scratch.Seek(0, io.SeekStart); err != nil {
		return Object{}, nil, err
	}
	media := mediaTypeOf(name)
	object, err := r.objects.Ingest(ctx, made.CreatedBy, made.OrgID, domain.Evidence, scratch, size, media)
	if err != nil {
		return Object{}, nil, err
	}
	var contents []byte
	if wanted {
		if _, err := scratch.Seek(0, io.SeekStart); err != nil {
			return Object{}, nil, err
		}
		if contents, err = io.ReadAll(scratch); err != nil {
			return Object{}, nil, err
		}
	}
	return Object{Path: name, ObjectID: object.ID, SizeBytes: size, MediaType: media}, contents, nil
}

func mediaTypeOf(name string) string {
	switch strings.ToLower(path.Ext(name)) {
	case ".usd", ".usda", ".usdc", ".usdz":
		return "model/vnd.usd"
	case ".jpg", ".jpeg":
		return "image/jpeg"
	case ".png":
		return "image/png"
	case ".json":
		return "application/json"
	case ".tif", ".tiff":
		return "image/tiff"
	case ".csv":
		return "text/csv"
	default:
		// The splats' checkpoints (.pt) and the surface's grid (.f32) are
		// bytes only the reconstruction module reads.
		return "application/octet-stream"
	}
}

// notANumber finds the non-numbers Python's json writes, outside strings well
// enough for a record whose strings never hold them.
var notANumber = regexp.MustCompile(`([:\[,]\s*)(?:NaN|-?Infinity)\b`)

// ReadObject reads a JSON object the reconstruction module wrote. The module
// writes NaN where a fit had nothing to say, which Python reads and JSON does
// not; it is read as null, which is what it means.
func ReadObject(raw []byte) (map[string]any, error) {
	var record map[string]any
	if err := json.Unmarshal(notANumber.ReplaceAll(raw, []byte("${1}null")), &record); err != nil {
		return nil, err
	}
	if record == nil {
		return nil, errors.New("it is not a JSON object")
	}
	return record, nil
}

// readManifest reads reconstruction.json.
func readManifest(raw []byte) (map[string]any, error) {
	record, err := ReadObject(raw)
	if err != nil {
		return nil, fmt.Errorf("the package's %s is not a JSON object: %w", Manifest, err)
	}
	return record, nil
}

// checkManifest refuses a manifest that names files the package does not
// hold: whatever lays the reef into a place later stages them by these names.
func checkManifest(record map[string]any, paths map[string]bool) error {
	pieces, _ := record["pieces"].([]any)
	if len(pieces) == 0 {
		return fmt.Errorf("the package's %s names no pieces of the reef", Manifest)
	}
	for i, one := range pieces {
		piece, _ := one.(map[string]any)
		part, _ := piece["part"].(string)
		if part == "" {
			return fmt.Errorf("piece %d of the reef names no part", i+1)
		}
		if !paths[path.Clean(part)] {
			return fmt.Errorf("piece %d of the reef is %s, which the package does not hold", i+1, part)
		}
		if checkpoint, _ := piece["checkpoint"].(string); checkpoint != "" && !paths[path.Clean(checkpoint)] {
			return fmt.Errorf("piece %d of the reef was trained to %s, which the package does not hold", i+1, checkpoint)
		}
	}
	if surface, ok := record["surface"].(map[string]any); ok {
		if file, _ := surface["file"].(string); file != "" && !paths[path.Clean(file)] {
			return fmt.Errorf("the ground surface is %s, which the package does not hold", file)
		}
	}
	for _, key := range []string{"path", "preview"} {
		if file, _ := record[key].(string); file != "" && !paths[path.Clean(file)] {
			return fmt.Errorf("the manifest's %s is %s, which the package does not hold", key, file)
		}
	}
	return nil
}
