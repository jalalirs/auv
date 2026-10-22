package mapping

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/building"
	"github.com/jalalirs/auv/services/control-plane/internal/catalog"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/exec"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
	"github.com/jalalirs/auv/services/control-plane/internal/reconstructing"
)

// Mapping is the record of one mapping: the place, the reefs, the job that
// laid them in and the version it made.
type Mapping struct {
	ID    string `json:"id"`
	OrgID string `json:"orgId"`
	// ReconstructionID is the first reef's, for a mapping asked for from a
	// reconstruction.
	ReconstructionID string     `json:"reconstructionId,omitempty"`
	CityID           string     `json:"cityId"`
	Mode             string     `json:"mode"`
	Brief            Request    `json:"brief"`
	BaseVersionID    string     `json:"baseVersionId,omitempty"`
	BuildID          string     `json:"buildId,omitempty"`
	LayJobID         string     `json:"layJobId,omitempty"`
	VersionID        string     `json:"versionId,omitempty"`
	Failure          string     `json:"failure,omitempty"`
	CreatedBy        string     `json:"createdBy"`
	CreatedAt        time.Time  `json:"createdAt"`
	RecordedAt       *time.Time `json:"recordedAt,omitempty"`
	Assets           []Asset    `json:"-"`
}

// Asset is one reef of a mapping: which reconstruction, what it is called in
// the place, what its search was told and found, and where it was put.
type Asset struct {
	Ordinal          int          `json:"ordinal"`
	ReconstructionID string       `json:"reconstructionId"`
	Name             string       `json:"name"`
	Brief            AssetRequest `json:"brief"`
	ResolveJobID     string       `json:"resolveJobId,omitempty"`
	// Candidates are the places the search found it fits, best first; Start
	// is where in the place's metres it searched from, when it knew, and
	// Searched how (candidates.json, read once from its output).
	Candidates []map[string]any `json:"candidates,omitempty"`
	Start      []float64        `json:"start,omitempty"`
	Searched   map[string]any   `json:"searched,omitempty"`
	// Chosen is where it is laid, as the lay job is told.
	Chosen    map[string]any `json:"chosen,omitempty"`
	Failure   string         `json:"failure,omitempty"`
	DroppedAt *time.Time     `json:"droppedAt,omitempty"`
}

const selectMapping = `
	SELECT id, org_id, coalesce(reconstruction_id, ''), city_id, mode, brief, coalesce(base_version_id, ''),
	       coalesce(build_id, ''), coalesce(lay_job_id, ''), coalesce(version_id, ''), coalesce(failure, ''),
	       created_by, created_at, recorded_at
	FROM catalog.mapping`

func scanMapping(row interface{ Scan(...any) error }) (Mapping, error) {
	var m Mapping
	var brief []byte
	if err := row.Scan(&m.ID, &m.OrgID, &m.ReconstructionID, &m.CityID, &m.Mode, &brief, &m.BaseVersionID,
		&m.BuildID, &m.LayJobID, &m.VersionID, &m.Failure, &m.CreatedBy, &m.CreatedAt, &m.RecordedAt); err != nil {
		return Mapping{}, db.Translate(err)
	}
	if err := json.Unmarshal(brief, &m.Brief); err != nil {
		return Mapping{}, err
	}
	return m, nil
}

// assetsOf reads a mapping's reefs, from the pool or inside a transaction.
func assetsOf(ctx context.Context, q db.Conn, mappingID string) ([]Asset, error) {
	rows, err := q.Query(ctx, `
		SELECT ordinal, reconstruction_id, name, brief, coalesce(resolve_job_id, ''), candidates, start,
		       searched, chosen, coalesce(failure, ''), dropped_at
		FROM catalog.mapping_asset WHERE mapping_id = $1 ORDER BY ordinal`, mappingID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	assets := []Asset{}
	for rows.Next() {
		var a Asset
		var brief, candidates, start, searched, chosen []byte
		if err := rows.Scan(&a.Ordinal, &a.ReconstructionID, &a.Name, &brief, &a.ResolveJobID, &candidates,
			&start, &searched, &chosen, &a.Failure, &a.DroppedAt); err != nil {
			return nil, err
		}
		for _, field := range []struct {
			raw  []byte
			into any
		}{{brief, &a.Brief}, {candidates, &a.Candidates}, {start, &a.Start}, {searched, &a.Searched}, {chosen, &a.Chosen}} {
			if len(field.raw) > 0 && string(field.raw) != "null" {
				if err := json.Unmarshal(field.raw, field.into); err != nil {
					return nil, err
				}
			}
		}
		if len(candidates) > 0 && a.Candidates == nil {
			a.Candidates = []map[string]any{}
		}
		assets = append(assets, a)
	}
	return assets, rows.Err()
}

// read reads a mapping and its reefs.
func (m *Mapper) read(ctx context.Context, id string) (Mapping, error) {
	mp, err := scanMapping(m.pool.QueryRow(ctx, selectMapping+` WHERE id = $1`, id))
	if err != nil {
		return Mapping{}, err
	}
	mp.Assets, err = assetsOf(ctx, m.pool, id)
	return mp, err
}

// Start asks for a reconstruction to be put onto a place: onto one that
// exists (a mapping of one reef), or one of its own. The work belongs to the
// reconstruction's organisation, and so does a place made for it.
func (m *Mapper) Start(ctx context.Context, principalID, reconstructionID string, request Request) (Mapping, error) {
	if m.settings.Image == "" {
		return Mapping{}, ErrNotConfigured
	}
	if err := request.Validate(); err != nil {
		return Mapping{}, err
	}
	if request.Mode == Onto {
		return m.StartOnto(ctx, principalID, request.CityID, PlaceRequest{VersionID: request.VersionID,
			Assets: []AssetRequest{request.asset(reconstructionID)}})
	}
	made, err := m.ready(ctx, reconstructionID)
	if err != nil {
		return Mapping{}, err
	}
	request = withDefaults(request, made)
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
	mapping := Mapping{ID: ids.New(ids.KindMapping), OrgID: made.OrgID, ReconstructionID: made.ID,
		CityID: city.ID, Mode: Own, Brief: request, BuildID: build.ID, CreatedBy: principalID,
		Assets: []Asset{{ReconstructionID: made.ID, Name: handleOf(made.Name), Brief: request.asset(made.ID)}}}
	return mapping, m.insert(ctx, &mapping)
}

// ready reads a reconstruction that can be put onto a place.
func (m *Mapper) ready(ctx context.Context, reconstructionID string) (reconstructing.Reconstruction, error) {
	watched, err := m.reconstructor.Watch(ctx, reconstructionID)
	if err != nil {
		return reconstructing.Reconstruction{}, err
	}
	if watched.State != "ready" {
		return reconstructing.Reconstruction{}, fmt.Errorf("%w: the reconstruction %s is %s; a reef is put onto a place once it is ready",
			domain.ErrInvalid, reconstructionID, watched.State)
	}
	return watched.Reconstruction, nil
}

// OrgOfReconstruction names the organisation a reconstruction belongs to,
// which is who a mapping of it is for.
func (m *Mapper) OrgOfReconstruction(ctx context.Context, reconstructionID string) (string, error) {
	return m.reconstructor.OrgOf(ctx, reconstructionID)
}

// StartOnto asks for reefs to be put onto a place that exists. They must all
// be one organisation's, which the work is for; each gets a search of its
// own, and as many as the organisation may run start now: the rest start as
// the first finish.
func (m *Mapper) StartOnto(ctx context.Context, principalID, cityID string, request PlaceRequest) (Mapping, error) {
	if m.settings.Image == "" {
		return Mapping{}, ErrNotConfigured
	}
	if err := request.Validate(); err != nil {
		return Mapping{}, err
	}
	city, err := m.catalog.City(ctx, cityID)
	if err != nil {
		return Mapping{}, fmt.Errorf("%w: no place %s", domain.ErrInvalid, cityID)
	}
	version, err := m.versionOf(ctx, city.ID, request.VersionID)
	if err != nil {
		return Mapping{}, err
	}
	mapping := Mapping{ID: ids.New(ids.KindMapping), CityID: city.ID, Mode: Onto,
		Brief: Request{Mode: Onto, CityID: city.ID, VersionID: request.VersionID}, BaseVersionID: version.ID,
		CreatedBy: principalID}
	names := make([]string, 0, len(request.Assets))
	for i, asked := range request.Assets {
		made, err := m.ready(ctx, asked.ReconstructionID)
		if err != nil {
			return Mapping{}, err
		}
		if i == 0 {
			mapping.OrgID, mapping.ReconstructionID = made.OrgID, made.ID
		} else if made.OrgID != mapping.OrgID {
			return Mapping{}, fmt.Errorf("%w: the reefs of one mapping are one organisation's; %s is another's",
				domain.ErrInvalid, made.ID)
		}
		mapping.Assets = append(mapping.Assets, Asset{Ordinal: i, ReconstructionID: made.ID,
			Brief: assetDefaults(asked, made)})
		names = append(names, made.Name)
	}
	for i, name := range namesOf(names) {
		mapping.Assets[i].Name = name
	}
	for i := range mapping.Assets {
		jobID, err := m.resolve(ctx, mapping, mapping.Assets[i])
		var refusal *exec.Refusal
		if errors.As(err, &refusal) && i > 0 {
			// The organisation is running as much as it may: the rest of the
			// searches start as these finish.
			break
		}
		if err != nil {
			return Mapping{}, err
		}
		mapping.Assets[i].ResolveJobID = jobID
	}
	return mapping, m.insert(ctx, &mapping)
}

// insert records a mapping and its reefs.
func (m *Mapper) insert(ctx context.Context, mapping *Mapping) error {
	said, err := json.Marshal(mapping.Brief)
	if err != nil {
		return err
	}
	return m.pool.InTransaction(ctx, func(conn db.Conn) error {
		err := conn.QueryRow(ctx, `
			INSERT INTO catalog.mapping (id, org_id, reconstruction_id, city_id, mode, brief,
			                             base_version_id, build_id, created_by)
			VALUES ($1, $2, nullif($3, ''), $4, $5, $6, nullif($7, ''), nullif($8, ''), $9)
			RETURNING created_at`,
			mapping.ID, mapping.OrgID, mapping.ReconstructionID, mapping.CityID, mapping.Mode, said,
			mapping.BaseVersionID, mapping.BuildID, mapping.CreatedBy).Scan(&mapping.CreatedAt)
		if err != nil {
			return fmt.Errorf("recording a mapping: %w", err)
		}
		for _, a := range mapping.Assets {
			brief, err := json.Marshal(a.Brief)
			if err != nil {
				return err
			}
			if _, err := conn.Exec(ctx, `
				INSERT INTO catalog.mapping_asset (mapping_id, ordinal, reconstruction_id, name, brief, resolve_job_id)
				VALUES ($1, $2, $3, $4, $5, nullif($6, ''))`,
				mapping.ID, a.Ordinal, a.ReconstructionID, a.Name, brief, a.ResolveJobID); err != nil {
				return fmt.Errorf("recording reef %d of a mapping: %w", a.Ordinal, err)
			}
		}
		return nil
	})
}

// resolve starts one reef's search of the place.
func (m *Mapper) resolve(ctx context.Context, mapping Mapping, asset Asset) (string, error) {
	files, err := m.catalog.Files(ctx, mapping.BaseVersionID)
	if err != nil {
		return "", err
	}
	inputs := building.Stage(files, "place")
	theirs, err := m.staged(ctx, asset.ReconstructionID, "reconstruction", false)
	if err != nil {
		return "", err
	}
	brief := map[string]any{"withinM": asset.Brief.WithinM, "depthSlackM": 3.0, "count": asset.Brief.Count}
	if asset.Brief.Start != nil {
		brief["start"] = asset.Brief.Start
	}
	if asset.Brief.DepthM != nil {
		brief["depthM"] = *asset.Brief.DepthM
	}
	said, err := json.Marshal(brief)
	if err != nil {
		return "", err
	}
	job, err := m.broker.Submit(ctx, exec.JobSpec{
		OrgID: mapping.OrgID, SubmittedBy: mapping.CreatedBy, RecipeID: ResolveRecipe,
		ImageDigest: m.settings.Image,
		Command:     []string{"python", "-m", "iocean_reconstruct.resolve"},
		Args:        []string{string(said)},
		Inputs:      append(inputs, theirs...),
		Outputs: []exec.Output{{Name: "candidates", RelativePath: "candidates.json",
			MediaType: "application/json", MaxSizeBytes: 16 << 20}},
		RequestCPU: m.settings.ResolveCPU, RequestMemoryBytes: m.settings.ResolveMemoryBytes,
		WalltimeSeconds: m.settings.ResolveWalltimeSeconds,
		Egress:          exec.NoEgress,
	})
	return job.ID, err
}

// versionOf is the version of a place the reefs are put onto: the one named,
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

// staged names a reconstruction's files as a job's inputs under dir, each at
// its own path; without the pieces unless asked.
func (m *Mapper) staged(ctx context.Context, reconstructionID, dir string, pieces bool) ([]exec.Input, error) {
	held, err := m.reconstructor.Objects(ctx, reconstructionID)
	if err != nil {
		return nil, err
	}
	inputs := []exec.Input{}
	for _, one := range held {
		if !wanted(one.Path, pieces) {
			continue
		}
		object, err := m.objects.Object(ctx, one.ObjectID)
		if err != nil {
			return nil, err
		}
		at := dir + "/" + one.Path
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

// Of lists the mappings a reconstruction is in, newest first.
func (m *Mapper) Of(ctx context.Context, reconstructionID string) ([]Mapping, error) {
	return m.list(ctx, `WHERE id IN (SELECT mapping_id FROM catalog.mapping_asset WHERE reconstruction_id = $1)`,
		reconstructionID)
}

// OfPlace lists a place's mappings, newest first.
func (m *Mapper) OfPlace(ctx context.Context, cityID string) ([]Mapping, error) {
	return m.list(ctx, `WHERE city_id = $1`, cityID)
}

func (m *Mapper) list(ctx context.Context, where string, arg string) ([]Mapping, error) {
	rows, err := m.pool.Query(ctx, selectMapping+" "+where+` ORDER BY created_at DESC LIMIT 50`, arg)
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
// base build (base), a reef's search (resolve, with the reef), or laying the
// reefs in (lay).
type Step struct {
	exec.Step
	Phase string `json:"phase"`
	Asset *int   `json:"asset,omitempty"`
}

// AssetView is one reef as somebody watching the mapping sees it.
type AssetView struct {
	Asset
	// State is the reef's: resolving (its search has not finished), choosing
	// (it waits for somebody to choose where it goes), chosen, failed (its
	// search failed, and it holds the others up until it is dropped), or
	// dropped.
	State string `json:"state"`
	Steps []Step `json:"steps"`
	Said  string `json:"said,omitempty"`
}

// View is a mapping as somebody watching it sees it.
type View struct {
	Mapping
	// State is the mapping's: building (its own place's seabed), resolving
	// (a reef's search has not finished), choosing (a reef waits for
	// somebody to choose, or for a failed one to be dropped), laying,
	// recording (the place's new version is being kept), ready, or failed.
	State  string      `json:"state"`
	Assets []AssetView `json:"assets"`
	Steps  []Step      `json:"steps"`
	// Laid and Overlaps are what the lay job said when it was done: where
	// each reef went, and which came within a metre of each other.
	Laid     []any    `json:"laid,omitempty"`
	Overlaps []string `json:"overlaps,omitempty"`
	// Waiting says what the mapping waits for that is not a job: a failed
	// reef to be dropped, or a job the platform refused for now.
	Waiting string `json:"waiting,omitempty"`
	// Said is the end of what the failed job printed.
	Said string `json:"said,omitempty"`
	// Candidates, Start, Searched and Chosen are the first reef's, as a
	// mapping of one reef always said them.
	Candidates []map[string]any `json:"candidates,omitempty"`
	Start      []float64        `json:"start,omitempty"`
	Searched   map[string]any   `json:"searched,omitempty"`
	Chosen     map[string]any   `json:"chosen,omitempty"`
}

const keptSteps = 200

// staleAfter is how long a claim to record a laid place is honoured without a
// result; past it, somebody watching claims it again.
const staleAfter = 2 * time.Hour

// Watch reads a mapping and moves it on when what it waits for has happened:
// the base build made its version (lay the reef in), a search reported (keep
// what it found, and start the next waiting), every reef has somewhere to go
// (lay them in), the lay job made the place (keep it as a version). Each is
// done once, however many people are watching.
func (m *Mapper) Watch(ctx context.Context, id string) (View, error) {
	mp, err := m.read(ctx, id)
	if err != nil {
		return View{}, err
	}
	view := View{Steps: []Step{}}
	var said, baseFailure string

	baseVersion := ""
	if mp.BuildID != "" {
		base, err := m.builder.Watch(ctx, mp.BuildID)
		if err != nil {
			return View{}, err
		}
		view.Steps = append(view.Steps, phased("base", nil, base.Steps)...)
		switch base.State {
		case "ready":
			baseVersion = base.VersionID
		case "failed":
			baseFailure, said = "the place's flat seabed could not be built: "+base.Failure, base.Said
		}
	}

	if mp.LayJobID == "" && mp.Failure == "" && baseFailure == "" {
		if view.Waiting, err = m.advance(ctx, mp.ID, baseVersion, nil); err != nil {
			return View{}, err
		}
		if mp, err = m.read(ctx, id); err != nil {
			return View{}, err
		}
	}

	resolving, choosing, blocked := false, false, []string{}
	for _, a := range mp.Assets {
		shown := AssetView{Asset: a, Steps: []Step{}}
		ordinal := a.Ordinal
		var job exec.Job
		if a.ResolveJobID != "" {
			var steps []exec.Step
			if job, steps, shown.Said, err = m.job(ctx, a.ResolveJobID); err != nil {
				return View{}, err
			}
			shown.Steps = phased("resolve", &ordinal, steps)
			view.Steps = append(view.Steps, shown.Steps...)
		}
		switch {
		case a.DroppedAt != nil:
			shown.State = "dropped"
		case a.Chosen != nil:
			shown.State = "chosen"
		case a.Failure != "":
			shown.State = "failed"
		case mp.Mode == Own:
			shown.State = "choosing"
		case a.ResolveJobID == "" || !job.State.IsTerminal() || (job.State == exec.Succeeded && a.Candidates == nil):
			shown.State, resolving = "resolving", true
		case job.State == exec.Succeeded:
			shown.State, choosing = "choosing", true
		default:
			shown.State = "failed"
			shown.Failure = fmt.Sprintf("its search's job %s (%s)", job.State, job.FailureClass)
		}
		if shown.State == "failed" {
			blocked = append(blocked, fmt.Sprintf("reef %d (%s): %s", a.Ordinal, a.Name, shown.Failure))
		} else {
			shown.Said = ""
		}
		view.Assets = append(view.Assets, shown)
	}
	if view.Assets == nil {
		view.Assets = []AssetView{}
	}

	switch {
	case mp.LayJobID != "":
		job, steps, out, err := m.job(ctx, mp.LayJobID)
		if err != nil {
			return View{}, err
		}
		laid := phased("lay", nil, steps)
		view.Steps = append(view.Steps, laid...)
		view.Laid, view.Overlaps = doneOf(steps)
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
			mp.Failure = fmt.Sprintf("the lay job %s (%s)", job.State, job.FailureClass)
		}
	case baseFailure != "":
		view.State, mp.Failure = "failed", baseFailure
	case mp.Failure != "":
		view.State = "failed"
	case mp.Mode == Own:
		view.State = "building"
	case resolving:
		view.State = "resolving"
	default:
		view.State = "choosing"
		if len(blocked) > 0 && !choosing {
			view.Waiting = joinWaiting(view.Waiting, "a reef's search failed, and the rest wait for it to be dropped: "+
				strings.Join(blocked, "; "))
		} else if len(blocked) > 0 {
			view.Waiting = joinWaiting(view.Waiting, "drop the reefs whose search failed to lay the rest: "+
				strings.Join(blocked, "; "))
		}
	}
	if mp.Failure != "" {
		view.State = "failed"
	}

	view.Mapping = mp
	if len(mp.Assets) > 0 {
		first := mp.Assets[0]
		view.Candidates, view.Start, view.Searched, view.Chosen = first.Candidates, first.Start, first.Searched, first.Chosen
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

func joinWaiting(before, now string) string {
	if before == "" {
		return now
	}
	return before + "; " + now
}

// doneOf reads what the lay job said when it was done.
func doneOf(steps []exec.Step) ([]any, []string) {
	for i := len(steps) - 1; i >= 0; i-- {
		detail := steps[i].Detail
		laid, hasLaid := detail["assets"].([]any)
		said, hasOverlaps := detail["overlaps"].([]any)
		if !hasLaid && !hasOverlaps {
			continue
		}
		overlaps := []string{}
		for _, one := range said {
			if text, ok := one.(string); ok {
				overlaps = append(overlaps, text)
			}
		}
		return laid, overlaps
	}
	return nil, nil
}

func phased(phase string, asset *int, steps []exec.Step) []Step {
	out := make([]Step, 0, len(steps))
	for _, step := range steps {
		out = append(out, Step{Step: step, Phase: phase, Asset: asset})
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

// advance moves a mapping on, with its row locked so two watchers do not both
// do it: change (when given) first, then whatever has become possible. It
// says what the mapping waits for that the platform refused for now.
//
// baseVersion is the version a place of the reef's own has, once its base
// build has made it.
func (m *Mapper) advance(ctx context.Context, id, baseVersion string, change func(conn db.Conn, mp *Mapping) error) (string, error) {
	waiting := ""
	err := m.pool.InTransaction(ctx, func(conn db.Conn) error {
		mp, err := scanMapping(conn.QueryRow(ctx, selectMapping+` WHERE id = $1 FOR UPDATE`, id))
		if err != nil {
			return err
		}
		if mp.Assets, err = assetsOf(ctx, conn, id); err != nil {
			return err
		}
		if change != nil {
			if err := change(conn, &mp); err != nil {
				return err
			}
		}
		if mp.LayJobID != "" || mp.Failure != "" {
			return nil
		}

		if mp.Mode == Own && baseVersion != "" && len(mp.Assets) > 0 && mp.Assets[0].Chosen == nil {
			placement := map[string]any{"centre": true, "depthM": *mp.Brief.DepthM, "headingDeg": *mp.Brief.HeadingDeg}
			if err := setChosen(ctx, conn, mp.ID, 0, placement); err != nil {
				return err
			}
			mp.Assets[0].Chosen, mp.BaseVersionID = placement, baseVersion
			if _, err := conn.Exec(ctx, `UPDATE catalog.mapping SET base_version_id = $2 WHERE id = $1`,
				mp.ID, baseVersion); err != nil {
				return err
			}
		}

		if mp.Mode == Onto {
			for i := range mp.Assets {
				a := &mp.Assets[i]
				if a.DroppedAt != nil || a.Failure != "" || a.Chosen != nil {
					continue
				}
				if a.ResolveJobID == "" {
					jobID, err := m.resolve(ctx, mp, *a)
					var refusal *exec.Refusal
					if errors.As(err, &refusal) {
						waiting = "reefs wait for their searches to start: " + refusal.Error()
						continue
					}
					if err != nil {
						return err
					}
					if _, err := conn.Exec(ctx, `UPDATE catalog.mapping_asset SET resolve_job_id = $3
						WHERE mapping_id = $1 AND ordinal = $2`, mp.ID, a.Ordinal, jobID); err != nil {
						return err
					}
					a.ResolveJobID = jobID
					continue
				}
				if a.Candidates == nil {
					job, err := m.broker.Job(ctx, a.ResolveJobID)
					if err != nil {
						return err
					}
					if job.State == exec.Succeeded {
						if err := m.keepCandidates(ctx, conn, mp.ID, a); err != nil {
							return err
						}
					}
				}
			}
		}

		left := 0
		for _, a := range mp.Assets {
			if a.DroppedAt == nil {
				left++
				if a.Chosen == nil {
					return nil
				}
			}
		}
		if left == 0 {
			_, err := conn.Exec(ctx, `UPDATE catalog.mapping SET failure = $2 WHERE id = $1`, mp.ID,
				"every reef was dropped, so there is nothing to lay in")
			return err
		}
		if mp.BaseVersionID == "" {
			return nil
		}
		jobID, err := m.lay(ctx, mp)
		var refusal *exec.Refusal
		if errors.As(err, &refusal) {
			waiting = "the reefs wait to be laid in: " + refusal.Error()
			return nil
		}
		if err != nil {
			return err
		}
		_, err = conn.Exec(ctx, `UPDATE catalog.mapping SET lay_job_id = $2 WHERE id = $1`, mp.ID, jobID)
		return err
	})
	return waiting, err
}

func setChosen(ctx context.Context, conn db.Conn, mappingID string, ordinal int, placement map[string]any) error {
	said, err := json.Marshal(placement)
	if err != nil {
		return err
	}
	_, err = conn.Exec(ctx, `UPDATE catalog.mapping_asset SET chosen = $3 WHERE mapping_id = $1 AND ordinal = $2`,
		mappingID, ordinal, said)
	return err
}

// keepCandidates keeps what a reef's search found, or why it found nothing.
func (m *Mapper) keepCandidates(ctx context.Context, conn db.Conn, mappingID string, a *Asset) error {
	found, err := m.candidatesOf(ctx, a.ResolveJobID)
	if err != nil {
		a.Failure = err.Error()
		_, err := conn.Exec(ctx, `UPDATE catalog.mapping_asset SET failure = $3 WHERE mapping_id = $1 AND ordinal = $2`,
			mappingID, a.Ordinal, a.Failure)
		return err
	}
	list, _ := json.Marshal(found["candidates"])
	start, _ := json.Marshal(found["start"])
	searched, _ := json.Marshal(found["searched"])
	_, err = conn.Exec(ctx, `
		UPDATE catalog.mapping_asset SET candidates = $3, start = $4, searched = $5
		WHERE mapping_id = $1 AND ordinal = $2`, mappingID, a.Ordinal, list, start, searched)
	a.Candidates = []map[string]any{}
	return err
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
		return nil, errors.New("the search found nowhere in the place the reef fits; try a wider search, or drop it")
	}
	return found, nil
}

// Accept chooses where one reef goes, from what its search found or by hand.
// When every reef has somewhere to go, they are laid in.
func (m *Mapper) Accept(ctx context.Context, id string, choice Choice) (Mapping, error) {
	ordinal := 0
	if choice.Asset != nil {
		ordinal = *choice.Asset
	}
	_, err := m.advance(ctx, id, "", func(conn db.Conn, mp *Mapping) error {
		if mp.Mode != Onto || mp.LayJobID != "" || mp.Failure != "" {
			return fmt.Errorf("%w: only a mapping choosing where its reefs go can be accepted", domain.ErrInvalid)
		}
		a, err := assetAt(mp, ordinal)
		if err != nil {
			return err
		}
		if a.Candidates == nil || a.Failure != "" {
			return fmt.Errorf("%w: reef %d is not choosing where it goes (its search %s)", domain.ErrInvalid, ordinal,
				map[bool]string{true: "failed", false: "has not finished"}[a.Failure != ""])
		}
		placement, err := placementOf(choice, a.Candidates)
		if err != nil {
			return err
		}
		if err := setChosen(ctx, conn, mp.ID, ordinal, placement); err != nil {
			return err
		}
		a.Chosen = placement
		return nil
	})
	if err != nil {
		return Mapping{}, err
	}
	return m.read(ctx, id)
}

// Drop takes a reef out of a mapping before it is laid in: one whose search
// failed, which holds the others up until it is, or one nobody wants after
// all. The rest are laid in once each has somewhere to go.
func (m *Mapper) Drop(ctx context.Context, id string, ordinal int) (Mapping, error) {
	_, err := m.advance(ctx, id, "", func(conn db.Conn, mp *Mapping) error {
		if mp.LayJobID != "" || mp.Failure != "" {
			return fmt.Errorf("%w: a reef is dropped before the reefs are laid in", domain.ErrInvalid)
		}
		a, err := assetAt(mp, ordinal)
		if err != nil {
			return err
		}
		now := time.Now()
		if _, err := conn.Exec(ctx, `UPDATE catalog.mapping_asset SET dropped_at = $3
			WHERE mapping_id = $1 AND ordinal = $2`, mp.ID, ordinal, now); err != nil {
			return err
		}
		a.DroppedAt = &now
		return nil
	})
	if err != nil {
		return Mapping{}, err
	}
	return m.read(ctx, id)
}

func assetAt(mp *Mapping, ordinal int) (*Asset, error) {
	for i := range mp.Assets {
		if mp.Assets[i].Ordinal == ordinal {
			if mp.Assets[i].DroppedAt != nil {
				return nil, fmt.Errorf("%w: reef %d was dropped", domain.ErrInvalid, ordinal)
			}
			return &mp.Assets[i], nil
		}
	}
	return nil, fmt.Errorf("%w: this mapping has no reef %d", domain.ErrInvalid, ordinal)
}

// layBrief is what the lay job is told: every reef still in the mapping, each
// with its files staged under reconstruction/<its reconstruction>.
func layBrief(assets []Asset, videos map[string]reconstructing.Reconstruction) map[string]any {
	laid := []any{}
	for _, a := range assets {
		if a.DroppedAt != nil {
			continue
		}
		made := videos[a.ReconstructionID]
		laid = append(laid, map[string]any{
			"name": a.Name, "path": "reconstruction/" + a.ReconstructionID, "placement": a.Chosen,
			"video": map[string]any{"name": made.Brief.Video.Name, "objectId": made.Brief.Video.ObjectID,
				"reconstructionId": made.ID},
		})
	}
	return map[string]any{"assets": laid, "sink": 1.0, "clear": 1.5}
}

// laySize is how long laying n reefs may take and how much it may make.
func laySize(n int, baseBytes int64, settings Settings) (int, int64) {
	walltime := 3600 + 2700*n
	if walltime > settings.LayWalltimeSeconds {
		walltime = settings.LayWalltimeSeconds
	}
	limit := baseBytes + int64(n)*settings.PackageBytes
	if limit > settings.PackageCapBytes {
		limit = settings.PackageCapBytes
	}
	return walltime, limit
}

// lay starts the one job that lays every reef in.
func (m *Mapper) lay(ctx context.Context, mp Mapping) (string, error) {
	files, err := m.catalog.Files(ctx, mp.BaseVersionID)
	if err != nil {
		return "", err
	}
	inputs := building.Stage(files, "place")
	var baseBytes int64
	for _, f := range files {
		baseBytes += f.SizeBytes
	}
	videos := map[string]reconstructing.Reconstruction{}
	n := 0
	for _, a := range mp.Assets {
		if a.DroppedAt != nil {
			continue
		}
		n++
		if _, staged := videos[a.ReconstructionID]; staged {
			continue
		}
		made, err := m.reconstructor.Reconstruction(ctx, a.ReconstructionID)
		if err != nil {
			return "", err
		}
		videos[made.ID] = made
		theirs, err := m.staged(ctx, made.ID, "reconstruction/"+made.ID, true)
		if err != nil {
			return "", err
		}
		inputs = append(inputs, theirs...)
	}
	said, err := json.Marshal(layBrief(mp.Assets, videos))
	if err != nil {
		return "", err
	}
	walltime, limit := laySize(n, baseBytes, m.settings)
	job, err := m.broker.Submit(ctx, exec.JobSpec{
		OrgID: mp.OrgID, SubmittedBy: mp.CreatedBy, RecipeID: LayRecipe,
		ImageDigest: m.settings.Image,
		Command:     []string{"python", "-m", "iocean_reconstruct.lay"},
		Args:        []string{string(said)},
		Inputs:      inputs,
		Outputs: []exec.Output{{Name: "place", RelativePath: "place.tar",
			MediaType: "application/x-tar", MaxSizeBytes: limit}},
		RequestCPU: m.settings.LayCPU, RequestMemoryBytes: m.settings.LayMemoryBytes,
		RequestGPU:      m.settings.LayGPU,
		WalltimeSeconds: walltime,
		Egress:          exec.NoEgress,
	})
	return job.ID, err
}

// claim starts keeping the place the lay job made, unless somebody else
// already is. Like a reconstruction's, it runs on its own: a place with reefs
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

// labelOf is what a version with reefs laid in is called, and its notes.
func labelOf(mp Mapping, names map[string]string) (string, string) {
	laid, from := []string{}, []string{}
	for _, a := range mp.Assets {
		if a.DroppedAt == nil {
			laid = append(laid, names[a.ReconstructionID])
			from = append(from, a.ReconstructionID)
		}
	}
	label := "reefs laid in"
	switch {
	case len(laid) == 1:
		label = laid[0] + " laid in"
	case len(laid) > 1:
		label = fmt.Sprintf("%s and %d more laid in", laid[0], len(laid)-1)
	}
	return label, fmt.Sprintf("the reefs reconstructed as %s, laid in by %s", strings.Join(from, ", "), mp.ID)
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
	if mp.Assets, err = assetsOf(ctx, m.pool, mp.ID); err != nil {
		return "", err
	}
	names := map[string]string{}
	for _, a := range mp.Assets {
		made, err := m.reconstructor.Reconstruction(ctx, a.ReconstructionID)
		if err != nil {
			return "", err
		}
		names[a.ReconstructionID] = made.Name
	}
	label, notes := labelOf(mp, names)
	versionID, _, err := m.builder.Package(ctx, objectID, building.Made{
		CityID: mp.CityID, OrgID: mp.OrgID, CreatedBy: mp.CreatedBy, Label: label, Notes: notes,
	})
	return versionID, err
}
