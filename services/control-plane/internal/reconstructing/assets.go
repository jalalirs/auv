package reconstructing

import (
	"context"
	"encoding/json"
	"fmt"
	"math"
	"path"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/exec"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
	"github.com/jalalirs/auv/services/control-plane/internal/storage"
)

// An asset is anything an organisation makes once and uses in any number of
// places: a reef from a dive video (the reconstruction above), a structure on
// the seabed from a 3D model or a pipeline's route, or a seabed survey from
// its file. Every one is a row of catalog.reconstruction, made by a job; a
// structure or a survey by the import job, in the reconstruction module's
// image, on processors.

// The kinds of asset.
const (
	KindReef       = "reef"
	KindStructure  = "structure"
	KindBathymetry = "bathymetry"
)

// What an asset is made from.
const (
	FromVideo  = "video"
	FromSurvey = "survey"
	FromModel  = "model"
	FromRoute  = "route"
)

// How a structure meets the seabed: it stands on it at a placement, drapes
// along its own route, or was rebuilt from a video with the ground it lies on
// and is fitted to a place's seabed by a search, as a reef is.
const (
	Stands  = "stands"
	Drapes  = "drapes"
	Rebuilt = "rebuilt"
)

// ImportRecipe is what the import job is recorded as having been made by.
const ImportRecipe = "asset-import/v1"

// AssetManifest is the file in the import job's package that says what the
// rest of it is.
const AssetManifest = "asset.json"

// StructureTypes are what a structure can be.
var StructureTypes = map[string]bool{"pipeline": true, "platform": true, "wind-foundation": true, "other": true}

// Structure is what a structure is and how it meets the seabed.
type Structure struct {
	Type  string `json:"type"`
	Meets string `json:"meets"`
}

// SourceFile is a survey's file, as uploaded.
type SourceFile struct {
	// Path is where the job finds it, filled in when the import starts.
	Path   string `json:"path,omitempty"`
	Name   string `json:"name,omitempty"`
	Format string `json:"format,omitempty"`
}

// Model is a structure's 3D model file, as uploaded: in its own units times
// Scale, with Up its up axis.
type Model struct {
	Path   string  `json:"path,omitempty"`
	Name   string  `json:"name,omitempty"`
	Format string  `json:"format,omitempty"`
	Scale  float64 `json:"scale,omitempty"`
	Up     string  `json:"up,omitempty"`
}

// Route is a pipeline nobody has a model of: where it runs, as latitude,
// longitude pairs, how wide it is, and how deep it is buried.
type Route struct {
	Points    [][2]float64 `json:"points"`
	DiameterM float64      `json:"diameterM"`
	Burial    *float64     `json:"burial,omitempty"`
}

// AssetBrief is what an import is asked to make, and, without Object and
// Label, what the import job is told.
type AssetBrief struct {
	Kind  string `json:"kind"`
	Type  string `json:"type,omitempty"`
	Meets string `json:"meets,omitempty"`
	// A survey: its file, its vertical datum, how wrong its depths may be,
	// and what to cite it as.
	File     *SourceFile `json:"file,omitempty"`
	Datum    string      `json:"datum,omitempty"`
	ErrorM   float64     `json:"errorM,omitempty"`
	Citation string      `json:"citation,omitempty"`
	// A structure: its model, or for a pipeline its route.
	Model *Model `json:"model,omitempty"`
	Route *Route `json:"route,omitempty"`
	// Object is the uploaded file (a survey or a model; not a route).
	Object string `json:"object,omitempty"`
	Label  string `json:"label,omitempty"`
}

var (
	surveyFormats = map[string]string{".tif": "geotiff", ".tiff": "geotiff", ".geotiff": "geotiff",
		".xyz": "xyz", ".csv": "xyz", ".txt": "xyz"}
	modelFormats = map[string]string{".glb": "glb", ".gltf": "gltf", ".obj": "obj"}
)

// madeFrom is what an asset with this brief is made from.
func (b AssetBrief) madeFrom() string {
	switch {
	case b.Kind == KindBathymetry:
		return FromSurvey
	case b.Route != nil:
		return FromRoute
	default:
		return FromModel
	}
}

// withDefaults writes down what a brief leaves to a default: a file's format
// from its name, a model's scale and up axis, and how a structure meets the
// seabed (a model stands, a route drapes).
func (b AssetBrief) withDefaults() AssetBrief {
	if b.Kind == KindBathymetry && b.File == nil {
		b.File = &SourceFile{}
	}
	if b.File != nil {
		file := *b.File
		if file.Format == "" {
			file.Format = surveyFormats[strings.ToLower(path.Ext(file.Name))]
		}
		b.File = &file
	}
	if b.Model != nil {
		model := *b.Model
		if model.Format == "" {
			model.Format = modelFormats[strings.ToLower(path.Ext(model.Name))]
		}
		if model.Scale == 0 {
			model.Scale = 1
		}
		if model.Up == "" {
			model.Up = "y"
		}
		b.Model = &model
	}
	if b.Kind == KindStructure && b.Meets == "" {
		if b.Route != nil {
			b.Meets = Drapes
		} else {
			b.Meets = Stands
		}
	}
	return b
}

func finite(v float64) bool { return !math.IsNaN(v) && !math.IsInf(v, 0) }

func onEarth(lat, lon float64) bool {
	return finite(lat) && finite(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180
}

// Validate reports whether a brief describes an asset the import job can make.
// Whether the organisation holds the object is checked when the import starts.
func (b AssetBrief) Validate() error {
	switch b.Kind {
	case KindBathymetry:
		if b.File == nil || b.Object == "" {
			return fmt.Errorf("%w: a survey is a file the organisation uploaded (object, file.name)", domain.ErrInvalid)
		}
		if b.Model != nil || b.Route != nil || b.Type != "" || b.Meets != "" {
			return fmt.Errorf("%w: a survey has a file, not a model, a route or a structure's type", domain.ErrInvalid)
		}
		if b.File.Format != "geotiff" && b.File.Format != "xyz" {
			return fmt.Errorf("%w: a survey is a GeoTIFF raster (geotiff) or soundings, lat,lon,depth (xyz), not %q",
				domain.ErrInvalid, b.File.Format)
		}
		if datum := strings.TrimSpace(b.Datum); datum == "" || len(datum) > 40 {
			return fmt.Errorf("%w: a survey says the datum its depths are from (MSL, LAT, ...)", domain.ErrInvalid)
		}
		if !finite(b.ErrorM) || b.ErrorM <= 0 || b.ErrorM > 100 {
			return fmt.Errorf("%w: a survey says how wrong its depths may be, more than 0 m and at most 100 m (errorM)", domain.ErrInvalid)
		}
	case KindStructure:
		if !StructureTypes[b.Type] {
			return fmt.Errorf("%w: a structure is a pipeline, platform, wind-foundation or other, not %q", domain.ErrInvalid, b.Type)
		}
		if b.Meets != Stands && b.Meets != Drapes {
			return fmt.Errorf("%w: a structure stands on the seabed or drapes over it, not %q", domain.ErrInvalid, b.Meets)
		}
		if b.File != nil {
			return fmt.Errorf("%w: a structure is made from a model or a route, not a survey's file", domain.ErrInvalid)
		}
		switch {
		case (b.Model == nil) == (b.Route == nil):
			return fmt.Errorf("%w: a structure is made from a model or, for a pipeline, a route: one of them", domain.ErrInvalid)
		case b.Model != nil:
			m := b.Model
			if b.Object == "" {
				return fmt.Errorf("%w: a model is a file the organisation uploaded (object)", domain.ErrInvalid)
			}
			if m.Format != "glb" && m.Format != "gltf" && m.Format != "obj" {
				return fmt.Errorf("%w: a model is glb, gltf or obj, not %q", domain.ErrInvalid, m.Format)
			}
			if !finite(m.Scale) || m.Scale <= 0 || m.Scale > 1000 {
				return fmt.Errorf("%w: a model's scale is more than 0 and at most 1000", domain.ErrInvalid)
			}
			if m.Up != "y" && m.Up != "z" {
				return fmt.Errorf("%w: a model's up axis is y or z, not %q", domain.ErrInvalid, m.Up)
			}
			if b.Meets != Stands {
				return fmt.Errorf("%w: a model stands on the seabed where it is placed; a structure that drapes is given as a route", domain.ErrInvalid)
			}
		default:
			r := b.Route
			if b.Object != "" {
				return fmt.Errorf("%w: a route is its points, not an uploaded file", domain.ErrInvalid)
			}
			if b.Type != "pipeline" {
				return fmt.Errorf("%w: a route is a pipeline's", domain.ErrInvalid)
			}
			if b.Meets != Drapes {
				return fmt.Errorf("%w: a pipeline from a route drapes along it", domain.ErrInvalid)
			}
			if len(r.Points) < 2 || len(r.Points) > 10000 {
				return fmt.Errorf("%w: a route is 2 to 10000 points, [latitude, longitude]", domain.ErrInvalid)
			}
			for i, p := range r.Points {
				if !onEarth(p[0], p[1]) {
					return fmt.Errorf("%w: point %d of the route is not latitude, longitude in degrees", domain.ErrInvalid, i)
				}
			}
			if !finite(r.DiameterM) || r.DiameterM <= 0 || r.DiameterM > 20 {
				return fmt.Errorf("%w: a pipeline is more than 0 m and at most 20 m across (diameterM)", domain.ErrInvalid)
			}
			if r.Burial != nil && (!finite(*r.Burial) || *r.Burial < 0 || *r.Burial > 1) {
				return fmt.Errorf("%w: burial is the share of a pipeline's diameter under the seabed, 0 to 1", domain.ErrInvalid)
			}
		}
	case KindReef, "":
		return fmt.Errorf("%w: a reef is made from a dive video, by a reconstruction; an import makes a structure or a bathymetry survey",
			domain.ErrInvalid)
	default:
		return fmt.Errorf("%w: an asset is a structure or a bathymetry survey, not %q", domain.ErrInvalid, b.Kind)
	}
	return nil
}

// sourcePath is where the job finds the uploaded file: its own name, made
// safe, or one by its format when it had none.
func sourcePath(name, format string) string {
	safe := safeName.ReplaceAllString(path.Base(name), "_")
	if safe == "" || safe == "." || safe == "_" || strings.HasPrefix(safe, "..") {
		safe = map[string]string{"geotiff": "survey.tif", "xyz": "survey.xyz", "glb": "model.glb",
			"gltf": "model.gltf", "obj": "model.obj"}[format]
	}
	return "source/" + safe
}

// assetName is what an asset is called when nobody named it: its file, or
// what it is.
func assetName(b AssetBrief) string {
	if label := strings.TrimSpace(b.Label); label != "" {
		return label
	}
	name := ""
	switch {
	case b.File != nil:
		name = b.File.Name
	case b.Model != nil:
		name = b.Model.Name
	}
	if stem := strings.TrimSuffix(path.Base(name), path.Ext(name)); stem != "" && stem != "." {
		return stem
	}
	if b.Kind == KindBathymetry {
		return "a survey"
	}
	return "a " + b.Type
}

// StartAsset asks for a structure or a survey to be made into an asset, from
// a file the organisation holds or a pipeline's route.
func (r *Reconstructor) StartAsset(ctx context.Context, principalID, orgID string, brief AssetBrief) (Reconstruction, error) {
	if r.settings.Image == "" {
		return Reconstruction{}, ErrNotConfigured
	}
	brief = brief.withDefaults()
	if err := brief.Validate(); err != nil {
		return Reconstruction{}, err
	}
	var inputs []exec.Input
	if brief.Object != "" {
		object, err := r.held(ctx, orgID, brief.Object)
		if err != nil {
			return Reconstruction{}, err
		}
		if isVideo(object.MediaType, "") {
			return Reconstruction{}, fmt.Errorf("%w: %s is a video; a reef is made from one by a reconstruction", domain.ErrInvalid, object.ID)
		}
		at := ""
		if brief.File != nil {
			brief.File.Path = sourcePath(brief.File.Name, brief.File.Format)
			at = brief.File.Path
			if brief.File.Name == "" {
				brief.File.Name = path.Base(at)
			}
		} else {
			brief.Model.Path = sourcePath(brief.Model.Name, brief.Model.Format)
			at = brief.Model.Path
			if brief.Model.Name == "" {
				brief.Model.Name = path.Base(at)
			}
		}
		inputs = append(inputs, exec.Input{Name: "source", RelativePath: at, ObjectID: object.ID,
			SHA256: object.SHA256, MediaType: object.MediaType, SizeBytes: object.SizeBytes})
	}
	said, err := json.Marshal(brief)
	if err != nil {
		return Reconstruction{}, err
	}
	// The job is told what to make, not which object or what to call it.
	told := brief
	told.Object, told.Label = "", ""
	job, err := json.Marshal(told)
	if err != nil {
		return Reconstruction{}, err
	}

	submitted, err := r.broker.Submit(ctx, exec.JobSpec{
		OrgID: orgID, SubmittedBy: principalID, RecipeID: ImportRecipe,
		ImageDigest: r.settings.Image,
		Command:     []string{"python", "-m", "iocean_reconstruct.asset"},
		Args:        []string{string(job)},
		Inputs:      inputs,
		Outputs: []exec.Output{{Name: "asset", RelativePath: "asset.tar",
			MediaType: "application/x-tar", MaxSizeBytes: r.settings.ImportPackageBytes}},
		RequestCPU: r.settings.ImportCPU, RequestMemoryBytes: r.settings.ImportMemoryBytes,
		WalltimeSeconds: r.settings.ImportWalltimeSeconds,
		Egress:          exec.NoEgress,
	})
	if err != nil {
		return Reconstruction{}, err
	}

	made := Reconstruction{ID: ids.New(ids.KindReconstruction), OrgID: orgID, JobID: submitted.ID,
		Asset: &brief, Name: assetName(brief), Kind: brief.Kind, MadeFrom: brief.madeFrom(), CreatedBy: principalID}
	var structure []byte
	if brief.Kind == KindStructure {
		made.Structure = &Structure{Type: brief.Type, Meets: brief.Meets}
		if structure, err = json.Marshal(made.Structure); err != nil {
			return Reconstruction{}, err
		}
	}
	err = r.pool.QueryRow(ctx, `
		INSERT INTO catalog.reconstruction (id, org_id, job_id, brief, name, created_by, kind, made_from, structure)
		VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9) RETURNING created_at`,
		made.ID, made.OrgID, made.JobID, said, made.Name, principalID, made.Kind, made.MadeFrom, structure,
	).Scan(&made.CreatedAt)
	if err != nil {
		return Reconstruction{}, fmt.Errorf("recording an asset: %w", err)
	}
	return made, nil
}

// ListAssets lists an organisation's assets of every kind, or of one, newest
// first.
func (r *Reconstructor) ListAssets(ctx context.Context, orgID, kind string) ([]Reconstruction, error) {
	if kind != "" {
		return r.list(ctx, `WHERE org_id = $1 AND kind = $2 AND archived_at IS NULL`, orgID, kind)
	}
	return r.list(ctx, `WHERE org_id = $1 AND archived_at IS NULL`, orgID)
}

// checkAsset refuses an import's manifest that is not the asset that was
// asked for, or names files the package does not hold: laying a structure or
// building a place on a survey stages them by these names.
func checkAsset(made Reconstruction, record map[string]any, paths map[string]bool) error {
	if kind, _ := record["kind"].(string); kind != made.Kind {
		return fmt.Errorf("the import was asked for a %s and its %s says it made %q", made.Kind, AssetManifest, kind)
	}
	if _, ok := record["footprint"].(map[string]any); !ok {
		return fmt.Errorf("the package's %s says nothing of the asset's footprint", AssetManifest)
	}
	switch made.MadeFrom {
	case FromSurvey:
		file := surveyFileOf(record)
		if file == "" || !paths[path.Clean(file)] {
			return fmt.Errorf("the survey's file is %q, which the package does not hold", file)
		}
	case FromModel:
		model, _ := record["model"].(string)
		if model == "" {
			model = "model.usdc"
		}
		if !paths[path.Clean(model)] {
			return fmt.Errorf("the structure's model is %s, which the package does not hold", model)
		}
	}
	if file, _ := record["preview"].(string); file != "" && !paths[path.Clean(file)] {
		return fmt.Errorf("the manifest's preview is %s, which the package does not hold", file)
	}
	return nil
}

// surveyFileOf is where in its package a survey's file is, by what its
// manifest's "file" says: a path, or {name, format}.
func surveyFileOf(record map[string]any) string {
	switch file := record["file"].(type) {
	case string:
		return file
	case map[string]any:
		if at, _ := file["path"].(string); at != "" {
			return at
		}
		name, _ := file["name"].(string)
		return name
	}
	return ""
}

// AssetView is an asset of any kind as the library shows it: what it is, how
// it was made, how it is going, its footprint and what it says about itself,
// and a short-lived link to its picture.
type AssetView struct {
	ID       string `json:"id"`
	OrgID    string `json:"orgId"`
	JobID    string `json:"jobId"`
	Name     string `json:"name"`
	Kind     string `json:"kind"`
	Type     string `json:"type,omitempty"`
	Meets    string `json:"meets,omitempty"`
	MadeFrom string `json:"madeFrom"`
	// State is the asset's: queued, running, recording, ready, or failed.
	State    string `json:"state"`
	JobState string `json:"jobState"`
	// Footprint is {sizeM: [x, y, z]} in local metres for a model or a reef,
	// or {bbox: [south, west, north, east]} in degrees for a survey or a
	// route. Stats is what the job measured of it.
	Footprint map[string]any `json:"footprint,omitempty"`
	Stats     map[string]any `json:"stats,omitempty"`
	Preview   string         `json:"preview,omitempty"`
	// Brief is what was asked: a reconstruction's brief for a reef, the
	// import's for anything else.
	Brief     any            `json:"brief"`
	Manifest  map[string]any `json:"manifest,omitempty"`
	Steps     []Step         `json:"steps"`
	Failure   string         `json:"failure,omitempty"`
	Said      string         `json:"said,omitempty"`
	CreatedBy string         `json:"createdBy"`
	CreatedAt time.Time      `json:"createdAt"`
}

// asAsset turns a reconstruction as somebody watching it sees it into an
// asset as the library shows it.
func asAsset(view View) AssetView {
	made := view.Reconstruction
	out := AssetView{ID: made.ID, OrgID: made.OrgID, JobID: made.JobID, Name: made.Name, Kind: made.Kind,
		MadeFrom: made.MadeFrom, State: view.State, JobState: view.JobState, Manifest: made.Manifest,
		Steps: view.Steps, Failure: view.Failure, Said: view.Said, CreatedBy: made.CreatedBy,
		CreatedAt: made.CreatedAt}
	if made.Structure != nil {
		out.Type, out.Meets = made.Structure.Type, made.Structure.Meets
	}
	if made.Asset != nil {
		out.Brief = made.Asset
	} else {
		out.Brief = made.Brief
	}
	manifest := made.Manifest
	if manifest == nil {
		return out
	}
	if made.MadeFrom != FromVideo {
		out.Footprint, _ = manifest["footprint"].(map[string]any)
		out.Stats, _ = manifest["stats"].(map[string]any)
		return out
	}
	// A reef from a video says its size and what it is made of in its own
	// words (reconstruction.json).
	if extent, ok := manifest["extentM"].([]any); ok {
		out.Footprint = map[string]any{"sizeM": extent}
	}
	pieces, _ := manifest["pieces"].([]any)
	splats := 0.0
	for _, one := range pieces {
		if piece, ok := one.(map[string]any); ok {
			n, _ := piece["splats"].(float64)
			splats += n
		}
	}
	out.Stats = map[string]any{"pieces": len(pieces), "splats": splats}
	for _, key := range []string{"frames", "registered", "scale"} {
		if v, ok := manifest[key]; ok {
			out.Stats[key] = v
		}
	}
	return out
}

// WatchAsset reads an asset of any kind as the library shows it, moving it on
// as Watch does, with a link to its picture when it has one.
func (r *Reconstructor) WatchAsset(ctx context.Context, id string) (AssetView, error) {
	view, err := r.Watch(ctx, id)
	if err != nil {
		return AssetView{}, err
	}
	out := asAsset(view)
	preview, _ := view.Manifest["preview"].(string)
	if preview == "" || view.State != "ready" {
		return out, nil
	}
	held, err := r.Objects(ctx, id)
	if err != nil {
		return AssetView{}, err
	}
	for _, one := range held {
		if one.Path != path.Clean(preview) {
			continue
		}
		object, err := r.objects.Object(ctx, one.ObjectID)
		if err != nil {
			return AssetView{}, err
		}
		if out.Preview, err = r.objects.ReadURL(ctx, object, path.Base(one.Path), storage.External); err != nil {
			return AssetView{}, err
		}
	}
	return out, nil
}

// Survey is a ready bathymetry asset as a place build uses it: the survey
// file it holds, and what it says of it.
type Survey struct {
	ObjectID string
	// Name is the file's own name; Use is raster for a GeoTIFF, points for
	// soundings.
	Name     string
	Use      string
	Datum    string
	ErrorM   float64
	Citation string
}

// Survey reads a bathymetry asset an organisation holds, ready to build a
// place on.
func (r *Reconstructor) Survey(ctx context.Context, orgID, id string) (Survey, error) {
	view, err := r.Watch(ctx, id)
	if err != nil {
		return Survey{}, fmt.Errorf("%w: no survey %s", domain.ErrInvalid, id)
	}
	made := view.Reconstruction
	switch {
	case made.OrgID != orgID:
		return Survey{}, fmt.Errorf("%w: the survey %s is another organisation's", domain.ErrInvalid, id)
	case made.Kind != KindBathymetry || made.Asset == nil || made.Asset.File == nil:
		return Survey{}, fmt.Errorf("%w: %s is a %s, not a bathymetry survey", domain.ErrInvalid, id, made.Kind)
	case view.State != "ready":
		return Survey{}, fmt.Errorf("%w: the survey %s is %s; a place is built on it once it is ready", domain.ErrInvalid, id, view.State)
	}
	file := surveyFileOf(made.Manifest)
	held, err := r.Objects(ctx, id)
	if err != nil {
		return Survey{}, err
	}
	for _, one := range held {
		if one.Path != path.Clean(file) {
			continue
		}
		brief := made.Asset
		use := "raster"
		if brief.File.Format == "xyz" {
			use = "points"
		}
		citation := brief.Citation
		if citation == "" {
			citation = fmt.Sprintf("the organisation's survey %s (%s), %s, ±%g m", made.Name, made.ID, brief.Datum, brief.ErrorM)
		}
		return Survey{ObjectID: one.ObjectID, Name: path.Base(one.Path), Use: use, Datum: brief.Datum,
			ErrorM: brief.ErrorM, Citation: citation}, nil
	}
	return Survey{}, fmt.Errorf("the survey %s holds no file %q", id, file)
}
