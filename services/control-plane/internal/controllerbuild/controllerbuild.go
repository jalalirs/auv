// Package controllerbuild builds controllers from their source on the
// platform's machines.
//
// Somebody names a GitHub repository (a branch, a tag or a commit, and a
// folder) or uploads a zip. One source may hold several controllers, listed
// in an iocean.toml at its root or each in a folder of its own under
// controllers/. The platform runs the controller build as a job: it fetches
// the source, finds the controllers, builds each one's image without the
// host's Docker, and flies each in a tank against the SDK's topic contract.
// Each that passes is put in the platform's registry and registered as a new
// build of that controller, with the commit or the upload it came from; each
// that does not says why, and does not stop the others.
//
// The job's image is the platform's, named in configuration, and nothing in
// the brief chooses what runs: that is why it may reach the network (to fetch
// the repository, and the package index for what the controller needs) when
// an organisation's own job may not (ADR-0012).
package controllerbuild

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"os"
	"path"
	"regexp"
	"strings"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/audit"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/dive"
	"github.com/jalalirs/auv/services/control-plane/internal/domain"
	"github.com/jalalirs/auv/services/control-plane/internal/exec"
	"github.com/jalalirs/auv/services/control-plane/internal/ids"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
	"github.com/jalalirs/auv/services/control-plane/internal/storage"
)

// Recipe is what the job is recorded as having been made by.
const Recipe = "controller-build/v1"

// ErrNotConfigured reports a platform with no image to build controllers
// with, or no registry to put what it builds in.
var ErrNotConfigured = errors.New("this platform has no image to build controllers with, or no registry to put them in")

// Settings are how a controller build runs, and where what it makes goes.
type Settings struct {
	// Image is the controller build's image, by digest.
	Image           string
	CPU             float64
	MemoryBytes     int64
	WalltimeSeconds int
	// ImageBytes is the largest image a build may make.
	ImageBytes int64
	// RegistryPush is where the control plane puts images (on the platform's
	// own network); RegistryPull is where hosts fetch them from, which is the
	// address a stack's image is named by.
	RegistryPush string
	RegistryPull string
}

// Source is where a controller comes from: a zip somebody uploaded, or a
// GitHub repository.
type Source struct {
	Kind string `json:"kind"`
	// A zip: the object it was uploaded as, its name, and where the job
	// finds it (filled in when the build starts).
	ObjectID string `json:"objectId,omitempty"`
	Name     string `json:"name,omitempty"`
	// A repository: its address, the branch, tag or commit (the repository's
	// default branch when empty), and the folder the controller is in.
	URL string `json:"url,omitempty"`
	Ref string `json:"ref,omitempty"`
	// Path is the folder in a repository, or where the job finds a zip.
	Path string `json:"path,omitempty"`
}

// Brief is what a build is asked to make.
type Brief struct {
	Source Source `json:"source"`
	// Controllers are which of the source's controllers to build, by slug;
	// every one found when empty.
	Controllers []string `json:"controllers,omitempty"`
	// Slug, Name, Controller and RateHz say one controller outright, for a
	// source with no index: what it is called, its entry point, its rate.
	Slug string `json:"slug,omitempty"`
	Name string `json:"name,omitempty"`
	// Controller names the entry point, file.py:Class, when the job should
	// not look for it.
	Controller string `json:"controller,omitempty"`
	// RateHz is how often the controller is asked for a command.
	RateHz float64 `json:"rateHz,omitempty"`
}

var (
	github     = regexp.MustCompile(`^https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?(\.git)?/?$`)
	refShape   = regexp.MustCompile(`^[A-Za-z0-9_./-]{1,200}$`)
	entryPoint = regexp.MustCompile(`^[A-Za-z0-9_./-]+\.py(:[A-Za-z_][A-Za-z0-9_]*)?$`)
	zipName    = regexp.MustCompile(`(?i)\.zip$`)
)

// Validate reports whether a brief describes something that can be built.
// Whether the organisation holds a zip is checked when the build starts.
func (b Brief) Validate() error {
	switch b.Source.Kind {
	case "git":
		if !github.MatchString(b.Source.URL) {
			return fmt.Errorf("%w: a repository is https://github.com/owner/repository, with no credentials in it", domain.ErrInvalid)
		}
		if b.Source.Ref != "" && (!refShape.MatchString(b.Source.Ref) || strings.Contains(b.Source.Ref, "..") ||
			strings.HasPrefix(b.Source.Ref, "-")) {
			return fmt.Errorf("%w: %q is not a branch, tag or commit", domain.ErrInvalid, b.Source.Ref)
		}
		if p := b.Source.Path; p != "" && (strings.Contains(p, "..") || path.IsAbs(p) || strings.HasPrefix(p, "-")) {
			return fmt.Errorf("%w: the folder is a path inside the repository", domain.ErrInvalid)
		}
		if b.Source.ObjectID != "" {
			return fmt.Errorf("%w: a repository is not also an upload", domain.ErrInvalid)
		}
	case "zip":
		if b.Source.ObjectID == "" {
			return fmt.Errorf("%w: a zip names the object it was uploaded as", domain.ErrInvalid)
		}
		if !zipName.MatchString(b.Source.Name) {
			return fmt.Errorf("%w: a controller is uploaded as a .zip", domain.ErrInvalid)
		}
		if b.Source.URL != "" || b.Source.Ref != "" {
			return fmt.Errorf("%w: an upload is not also a repository", domain.ErrInvalid)
		}
	default:
		return fmt.Errorf("%w: a controller comes from a repository (git) or an upload (zip), not %q",
			domain.ErrInvalid, b.Source.Kind)
	}
	if b.Slug != "" {
		if err := domain.ValidateSlug(b.Slug); err != nil {
			return err
		}
	}
	if len(b.Controllers) > 50 {
		return fmt.Errorf("%w: a build makes at most 50 controllers", domain.ErrInvalid)
	}
	for _, slug := range b.Controllers {
		if err := domain.ValidateSlug(slug); err != nil {
			return err
		}
	}
	if b.Controller != "" && (!entryPoint.MatchString(b.Controller) || strings.Contains(b.Controller, "..")) {
		return fmt.Errorf("%w: a controller is named file.py:Class", domain.ErrInvalid)
	}
	if b.RateHz != 0 && (b.RateHz < 1 || b.RateHz > 200) {
		return fmt.Errorf("%w: a controller is asked 1 to 200 times a second", domain.ErrInvalid)
	}
	return nil
}

var notSlug = regexp.MustCompile(`[^a-z0-9]+`)

// slugOf is what a build is called: its source, the repository's (or the
// folder's) or the zip's name made a slug. The controllers it makes have
// their own.
func slugOf(brief Brief) string {
	name := brief.Source.Name
	if brief.Source.Kind == "git" {
		name = path.Base(strings.TrimSuffix(strings.TrimSuffix(brief.Source.URL, "/"), ".git"))
		if brief.Source.Path != "" {
			name = path.Base(brief.Source.Path)
		}
	}
	name = strings.TrimSuffix(name, path.Ext(name))
	slug := strings.Trim(notSlug.ReplaceAllString(strings.ToLower(name), "-"), "-")
	if len(slug) > 60 {
		slug = strings.Trim(slug[:60], "-")
	}
	if len(slug) < 2 || slug[0] < 'a' || slug[0] > 'z' {
		slug = "controller-" + slug
	}
	return strings.Trim(slug, "-")
}

var safeName = regexp.MustCompile(`[^A-Za-z0-9._-]+`)

// Builder runs controller builds.
type Builder struct {
	pool     *db.Pool
	broker   *exec.Broker
	objects  *storage.Objects
	dives    *dive.Store
	audit    *audit.Recorder
	settings Settings
}

// New builds a Builder.
func New(pool *db.Pool, broker *exec.Broker, objects *storage.Objects, dives *dive.Store, recorder *audit.Recorder, settings Settings) *Builder {
	if settings.CPU == 0 {
		settings.CPU = 4
	}
	if settings.MemoryBytes == 0 {
		settings.MemoryBytes = 8 << 30
	}
	if settings.WalltimeSeconds == 0 {
		settings.WalltimeSeconds = 3600
	}
	if settings.ImageBytes == 0 {
		settings.ImageBytes = 8 << 30
	}
	return &Builder{pool: pool, broker: broker, objects: objects, dives: dives, audit: recorder, settings: settings}
}

// Build is the record of one controller build.
type Build struct {
	ID    string `json:"id"`
	OrgID string `json:"orgId"`
	JobID string `json:"jobId"`
	Brief Brief  `json:"brief"`
	Slug  string `json:"slug"`
	// Report is what the build said about itself (report.json), once read.
	Report map[string]any `json:"report,omitempty"`
	// Stacks are what it registered: a stack for each controller that
	// passed, or why one that passed could not be.
	Stacks     []Registered `json:"stacks,omitempty"`
	Failure    string       `json:"failure,omitempty"`
	CreatedBy  string       `json:"createdBy"`
	CreatedAt  time.Time    `json:"createdAt"`
	RecordedAt *time.Time   `json:"recordedAt,omitempty"`
}

// Registered is what became of one controller that passed.
type Registered struct {
	Slug    string `json:"slug"`
	StackID string `json:"stackId,omitempty"`
	Failure string `json:"failure,omitempty"`
}

// Start asks for a source's controllers to be built for an organisation.
func (b *Builder) Start(ctx context.Context, principalID, orgID string, brief Brief) (Build, error) {
	if b.settings.Image == "" || b.settings.RegistryPush == "" || b.settings.RegistryPull == "" {
		return Build{}, ErrNotConfigured
	}
	if err := brief.Validate(); err != nil {
		return Build{}, err
	}
	var inputs []exec.Input
	if brief.Source.Kind == "zip" {
		object, err := b.objects.Object(ctx, brief.Source.ObjectID)
		if err != nil {
			return Build{}, fmt.Errorf("%w: no object %s", domain.ErrInvalid, brief.Source.ObjectID)
		}
		var held bool
		if err := b.pool.QueryRow(ctx,
			`SELECT EXISTS (SELECT 1 FROM store.holding WHERE org_id = $1 AND object_id = $2)`,
			orgID, object.ID).Scan(&held); err != nil {
			return Build{}, err
		}
		if !held {
			return Build{}, fmt.Errorf("%w: the organisation does not hold %s; upload it first", domain.ErrInvalid, object.ID)
		}
		name := safeName.ReplaceAllString(path.Base(brief.Source.Name), "_")
		if !zipName.MatchString(name) || strings.HasPrefix(name, ".") {
			name = "controller.zip"
		}
		brief.Source.Path = "source/" + name
		inputs = append(inputs, exec.Input{Name: "source", RelativePath: brief.Source.Path, ObjectID: object.ID,
			SHA256: object.SHA256, MediaType: object.MediaType, SizeBytes: object.SizeBytes})
	}
	if brief.RateHz == 0 {
		brief.RateHz = 20
	}
	said, err := json.Marshal(brief)
	if err != nil {
		return Build{}, err
	}

	job, err := b.broker.Submit(ctx, exec.JobSpec{
		OrgID: orgID, SubmittedBy: principalID, RecipeID: Recipe,
		ImageDigest: b.settings.Image,
		Command:     []string{"python3", "-m", "iocean_controller_build.job"},
		Args:        []string{string(said)},
		Inputs:      inputs,
		Outputs: []exec.Output{
			// Every controller built, in one image layout: their blobs are
			// shared, so the ROS base is in it once.
			{Name: "images", RelativePath: "images.oci.tar", MediaType: "application/x-tar",
				MaxSizeBytes: b.settings.ImageBytes},
			{Name: "report", RelativePath: "report.json", MediaType: "application/json",
				MaxSizeBytes: 1 << 20},
		},
		RequestCPU: b.settings.CPU, RequestMemoryBytes: b.settings.MemoryBytes,
		WalltimeSeconds: b.settings.WalltimeSeconds,
		// A repository is fetched from GitHub, and what a controller says it
		// needs from the package index, for a zip as much as a repository:
		// which a zip asks for is not known until the job has opened it.
		Egress: exec.InternetEgress,
	})
	if err != nil {
		return Build{}, err
	}

	build := Build{ID: ids.New(ids.KindControllerBuild), OrgID: orgID, JobID: job.ID, Brief: brief,
		Slug: slugOf(brief), CreatedBy: principalID}
	err = b.pool.QueryRow(ctx, `
		INSERT INTO catalog.controller_build (id, org_id, job_id, brief, slug, created_by)
		VALUES ($1, $2, $3, $4, $5, $6) RETURNING created_at`,
		build.ID, orgID, job.ID, said, build.Slug, principalID).Scan(&build.CreatedAt)
	if err != nil {
		return Build{}, fmt.Errorf("recording a controller build: %w", err)
	}
	return build, nil
}

// Again builds the same source again: for a repository, the same branch or
// tag and folder, so it builds the newest commit there.
func (b *Builder) Again(ctx context.Context, principalID, id string) (Build, error) {
	before, err := b.Build(ctx, id)
	if err != nil {
		return Build{}, err
	}
	brief := before.Brief
	if brief.Source.Kind == "zip" {
		brief.Source.Path = ""
	}
	return b.Start(ctx, principalID, before.OrgID, brief)
}

const selectBuild = `
	SELECT id, org_id, job_id, brief, slug, report, stacks, coalesce(failure, ''),
	       created_by, created_at, recorded_at
	FROM catalog.controller_build`

func scanBuild(row interface{ Scan(...any) error }) (Build, error) {
	var build Build
	var brief, report, stacks []byte
	if err := row.Scan(&build.ID, &build.OrgID, &build.JobID, &brief, &build.Slug, &report, &stacks,
		&build.Failure, &build.CreatedBy, &build.CreatedAt, &build.RecordedAt); err != nil {
		return Build{}, db.Translate(err)
	}
	if err := json.Unmarshal(brief, &build.Brief); err != nil {
		return Build{}, err
	}
	if len(report) > 0 {
		if err := json.Unmarshal(report, &build.Report); err != nil {
			return Build{}, err
		}
	}
	if len(stacks) > 0 {
		if err := json.Unmarshal(stacks, &build.Stacks); err != nil {
			return Build{}, err
		}
	}
	return build, nil
}

// Build reads one build's record.
func (b *Builder) Build(ctx context.Context, id string) (Build, error) {
	return scanBuild(b.pool.QueryRow(ctx, selectBuild+` WHERE id = $1`, id))
}

// OrgOf names the organisation a build belongs to.
func (b *Builder) OrgOf(ctx context.Context, id string) (string, error) {
	var org string
	err := b.pool.QueryRow(ctx, `SELECT org_id FROM catalog.controller_build WHERE id = $1`, id).Scan(&org)
	return org, db.Translate(err)
}

// List lists an organisation's controller builds, newest first.
func (b *Builder) List(ctx context.Context, orgID string) ([]Build, error) {
	rows, err := b.pool.Query(ctx,
		selectBuild+` WHERE org_id = $1 ORDER BY created_at DESC LIMIT 50`, orgID)
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

// View is a build as somebody watching it sees it.
type View struct {
	Build
	// State is the build's: queued, running, recording (its images are being
	// put in the registry and registered), ready (at least one controller
	// registered), or failed.
	State    string      `json:"state"`
	JobState string      `json:"jobState"`
	Steps    []exec.Step `json:"steps"`
	// Controllers are each controller the build reported, whether it passed
	// and why not, and the stack it registered.
	Controllers []map[string]any `json:"controllers"`
	// Said is the end of what the build printed, when it failed.
	Said string `json:"said,omitempty"`
}

// staleAfter is how long a claim to record a build is honoured without a
// result; past it, somebody watching claims it again.
const staleAfter = time.Hour

// Watch reads a build, and when its job has finished, puts the image it made
// in the registry and registers it, once.
func (b *Builder) Watch(ctx context.Context, id string) (View, error) {
	build, err := b.Build(ctx, id)
	if err != nil {
		return View{}, err
	}
	job, err := b.broker.Job(ctx, build.JobID)
	if err != nil {
		return View{}, err
	}
	events, err := b.broker.Events(ctx, build.JobID, 0, 1000)
	if err != nil {
		return View{}, err
	}
	view := View{Build: build, JobState: string(job.State), Controllers: controllersOf(build)}
	view.Steps, view.Said = exec.Progress(events)

	switch job.State {
	case exec.Pending, exec.Admitted:
		view.State = "queued"
	case exec.Running:
		view.State = "running"
	case exec.Succeeded:
		switch {
		case build.Stacks != nil && build.Failure == "":
			view.State = "ready"
		case build.Failure != "":
			view.State = "failed"
		default:
			view.State = "recording"
			if err := b.claim(ctx, build); err != nil {
				return View{}, err
			}
		}
	default:
		view.State = "failed"
		if view.Failure == "" {
			view.Failure = fmt.Sprintf("the controller build's job %s (%s)", job.State, job.FailureClass)
		}
	}
	if view.State != "failed" {
		view.Said = ""
	} else if len(view.Said) > 4000 {
		view.Said = view.Said[len(view.Said)-4000:]
	}
	return view, nil
}

// claim starts recording a finished build, unless somebody else already is.
// It runs on its own: an image is gigabytes, and a watcher who gave up would
// otherwise cancel the push halfway.
func (b *Builder) claim(ctx context.Context, build Build) error {
	tag, err := b.pool.Exec(ctx, `
		UPDATE catalog.controller_build SET recorded_at = now()
		WHERE id = $1 AND stacks IS NULL AND failure IS NULL
		  AND (recorded_at IS NULL OR recorded_at < now() - $2::interval)`,
		build.ID, fmt.Sprintf("%d seconds", int(staleAfter.Seconds())))
	if err != nil {
		return err
	}
	if tag.RowsAffected() == 0 {
		return nil
	}
	go func() {
		recording, cancel := context.WithTimeout(context.WithoutCancel(ctx), staleAfter)
		defer cancel()
		_ = b.record(recording, build)
	}()
	return nil
}

// record reads what a finished build reported and, if it passed, puts its
// image in the registry and registers it as a build of the controller.
func (b *Builder) record(ctx context.Context, build Build) error {
	report, err := b.report(ctx, build)
	if err == nil {
		said, _ := json.Marshal(report)
		if _, err = b.pool.Exec(ctx, `UPDATE catalog.controller_build SET report = $2 WHERE id = $1`,
			build.ID, said); err == nil {
			if ok, _ := report["ok"].(bool); !ok {
				failure, _ := report["failure"].(string)
				if failure == "" {
					failure = "no controller in the source passed its checks"
				}
				err = errors.New(failure)
			} else {
				err = b.register(ctx, build, report)
			}
		}
	}
	if err != nil {
		_, _ = b.pool.Exec(context.WithoutCancel(ctx),
			`UPDATE catalog.controller_build SET failure = $2 WHERE id = $1`, build.ID, err.Error())
	}
	return err
}

func (b *Builder) output(ctx context.Context, build Build, name string) (io.ReadCloser, error) {
	outputs, err := b.broker.Outputs(ctx, build.JobID)
	if err != nil {
		return nil, err
	}
	objectID, ok := outputs[name]
	if !ok {
		return nil, fmt.Errorf("the build finished without its %s", name)
	}
	object, err := b.objects.Object(ctx, objectID)
	if err != nil {
		return nil, err
	}
	return b.objects.Open(ctx, object)
}

func (b *Builder) report(ctx context.Context, build Build) (map[string]any, error) {
	body, err := b.output(ctx, build, "report")
	if err != nil {
		return nil, err
	}
	defer body.Close()
	raw, err := io.ReadAll(io.LimitReader(body, 1<<20))
	if err != nil {
		return nil, err
	}
	var report map[string]any
	if err := json.Unmarshal(raw, &report); err != nil || report == nil {
		return nil, errors.New("the build's report.json cannot be read")
	}
	return report, nil
}

// register puts every controller that passed in the registry and records
// each as a build of that controller, the same way autonomy brought from a
// terminal is. One that cannot be registered is said to have failed beside
// the others; the build fails only when none could be.
func (b *Builder) register(ctx context.Context, build Build, report map[string]any) error {
	var orgSlug string
	if err := b.pool.QueryRow(ctx, `SELECT slug FROM identity.organisation WHERE id = $1`,
		build.OrgID).Scan(&orgSlug); err != nil {
		return err
	}
	body, err := b.output(ctx, build, "images")
	if err != nil {
		return err
	}
	defer body.Close()
	scratch, err := os.MkdirTemp("", "iocean-controller-*")
	if err != nil {
		return err
	}
	defer os.RemoveAll(scratch)
	images, err := unpack(body, scratch)
	if err != nil {
		return err
	}
	registry := newRegistry(b.settings.RegistryPush)

	stacks := []Registered{}
	for _, one := range passed(report) {
		done := Registered{}
		done.Slug, _ = one["slug"].(string)
		spec, err := stackOf(build, report, one)
		if err == nil {
			done.StackID, err = b.registerOne(ctx, build, images, registry, orgSlug, one, spec)
		}
		if err != nil {
			done.Failure = err.Error()
		}
		stacks = append(stacks, done)
	}
	registered := 0
	for _, one := range stacks {
		if one.Failure == "" {
			registered++
		}
	}
	said, err := json.Marshal(stacks)
	if err != nil {
		return err
	}
	if _, err := b.pool.Exec(ctx, `UPDATE catalog.controller_build SET stacks = $2 WHERE id = $1`,
		build.ID, said); err != nil {
		return err
	}
	if registered == 0 {
		return errors.New("no controller that passed could be registered: " + stacks[0].Failure)
	}
	return nil
}

// registerOne pushes one controller's image and registers it, and says the
// stack it registered.
func (b *Builder) registerOne(ctx context.Context, build Build, images layout, registry *registry,
	orgSlug string, one map[string]any, spec dive.StackSpec) (string, error) {
	name, _ := one["image"].(string)
	if name == "" {
		name = spec.Slug
	}
	image, ok := images.image(name)
	if !ok {
		return "", fmt.Errorf("the build passed %s and its images hold none named %q", spec.Slug, name)
	}
	if image.Digest != spec.ImageDigest {
		return "", fmt.Errorf("the image named %s is %s, and the build reported %s", name, image.Digest, spec.ImageDigest)
	}
	repository := "autonomy/" + orgSlug + "/" + spec.Slug
	digest, err := registry.push(ctx, images, image, repository)
	if err != nil {
		return "", err
	}
	if digest != spec.ImageDigest {
		return "", fmt.Errorf("the registry holds %s as %s, and the build reported %s", spec.Slug, digest, spec.ImageDigest)
	}
	spec.ImageRepository = strings.TrimRight(b.settings.RegistryPull, "/") + "/" + repository

	var stackID string
	err = b.pool.InTransaction(ctx, func(conn db.Conn) error {
		stack, err := b.dives.CreateStack(ctx, conn, spec)
		if err != nil {
			return err
		}
		stackID = stack.ID
		return b.audit.Record(ctx, conn, audit.Event{
			ActorID: build.CreatedBy, Action: string(policy.DiveWrite),
			SubjectKind: "autonomy", SubjectID: stack.ID, Outcome: audit.Succeeded,
			Detail: map[string]any{"slug": stack.Slug, "image": stack.ImageRepository, "controllerBuild": build.ID},
		})
	})
	return stackID, err
}

// passed are the controllers a report says passed.
func passed(report map[string]any) []map[string]any {
	all, _ := report["controllers"].([]any)
	out := []map[string]any{}
	for _, one := range all {
		if controller, ok := one.(map[string]any); ok {
			if ok, _ := controller["ok"].(bool); ok {
				out = append(out, controller)
			}
		}
	}
	return out
}

// controllersOf is what a view shows of each controller: what the report
// said, and the stack it registered or why it could not be.
func controllersOf(build Build) []map[string]any {
	all, _ := build.Report["controllers"].([]any)
	out := make([]map[string]any, 0, len(all))
	for _, one := range all {
		controller, ok := one.(map[string]any)
		if !ok {
			continue
		}
		shown := make(map[string]any, len(controller)+1)
		for k, v := range controller {
			shown[k] = v
		}
		for _, done := range build.Stacks {
			if done.Slug == controller["slug"] {
				if done.StackID != "" {
					shown["stackId"] = done.StackID
				}
				if done.Failure != "" {
					shown["registered"] = false
					shown["failure"] = done.Failure
				}
			}
		}
		out = append(out, shown)
	}
	return out
}

// stackOf is what a controller that passed registers: the stack its entry
// in the report describes, with where the source came from. The stack's own
// rules (a slug, a name, a digest not a tag, needs that are not negative) are
// the stack's to apply, when it is created.
func stackOf(build Build, report, one map[string]any) (dive.StackSpec, error) {
	text := func(key string) string { v, _ := one[key].(string); return v }
	raw := func(key string) json.RawMessage {
		if v, ok := one[key]; ok && v != nil {
			said, _ := json.Marshal(v)
			return said
		}
		return nil
	}
	slug := text("slug")
	if slug == "" {
		return dive.StackSpec{}, errors.New("the build passed a controller and did not say what it is called")
	}
	name := text("name")
	if name == "" {
		name = slug
	}
	digest := text("imageDigest")
	if digest == "" {
		return dive.StackSpec{Slug: slug}, fmt.Errorf("the build passed %s and reported no image digest", slug)
	}
	wantsGPU, _ := one["wantsGpu"].(bool)
	source := map[string]any{"kind": build.Brief.Source.Kind, "controllerBuild": build.ID}
	if from, ok := report["source"].(map[string]any); ok {
		for k, v := range from {
			source[k] = v
		}
	} else if build.Brief.Source.Kind == "git" {
		source["url"], source["ref"], source["path"] = build.Brief.Source.URL, build.Brief.Source.Ref, build.Brief.Source.Path
	} else {
		source["objectId"], source["name"] = build.Brief.Source.ObjectID, build.Brief.Source.Name
	}
	if entry := text("controller"); entry != "" {
		source["controller"] = entry
	}
	said, _ := json.Marshal(source)
	return dive.StackSpec{
		OrgID: build.OrgID, Slug: slug, Name: name, ImageDigest: digest,
		Subscribes: raw("subscribes"), Publishes: raw("publishes"), WantsGPU: wantsGPU, Needs: raw("needs"),
		Source: said, CreatedBy: build.CreatedBy,
	}, nil
}
