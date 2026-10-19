package controllerbuild

import (
	"archive/tar"
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync"
	"testing"
)

func TestABriefNamesARepositoryOnGitHubOrAZip(t *testing.T) {
	good := []Brief{
		{Source: Source{Kind: "git", URL: "https://github.com/iocean/wary"}},
		{Source: Source{Kind: "git", URL: "https://github.com/iocean/wary.git", Ref: "v1.2", Path: "controllers/wary"}},
		{Source: Source{Kind: "zip", ObjectID: "obj_1", Name: "Wary.ZIP"}, Slug: "wary", Controller: "wary.py:Wary", RateHz: 50},
		{Source: Source{Kind: "git", URL: "https://github.com/jalalirs/iocean-controllers"}, Controllers: []string{"station-hold", "sawtooth"}},
	}
	for _, brief := range good {
		if err := brief.Validate(); err != nil {
			t.Errorf("%+v: %v", brief, err)
		}
	}
	bad := map[string]Brief{
		"no source":            {},
		"GitLab":               {Source: Source{Kind: "git", URL: "https://gitlab.com/iocean/wary"}},
		"credentials in it":    {Source: Source{Kind: "git", URL: "https://token@github.com/iocean/wary"}},
		"plain http":           {Source: Source{Kind: "git", URL: "http://github.com/iocean/wary"}},
		"a ref climbing out":   {Source: Source{Kind: "git", URL: "https://github.com/iocean/wary", Ref: "../main"}},
		"a ref like an option": {Source: Source{Kind: "git", URL: "https://github.com/iocean/wary", Ref: "--upload-pack=x"}},
		"a folder climbing":    {Source: Source{Kind: "git", URL: "https://github.com/iocean/wary", Path: "../../etc"}},
		"a zip with no object": {Source: Source{Kind: "zip", Name: "a.zip"}},
		"a tarball":            {Source: Source{Kind: "zip", ObjectID: "obj_1", Name: "a.tar.gz"}},
		"a bad slug":           {Source: Source{Kind: "zip", ObjectID: "obj_1", Name: "a.zip"}, Slug: "Wary!"},
		"an entry point":       {Source: Source{Kind: "zip", ObjectID: "obj_1", Name: "a.zip"}, Controller: "wary:Wary"},
		"too fast":             {Source: Source{Kind: "zip", ObjectID: "obj_1", Name: "a.zip"}, RateHz: 1000},
	}
	for name, brief := range bad {
		if brief.Validate() == nil {
			t.Errorf("%s was accepted", name)
		}
	}
}

func TestABuildIsCalledByItsSource(t *testing.T) {
	cases := []struct {
		want  string
		brief Brief
	}{
		{"iocean-controllers", Brief{Slug: "wary", Source: Source{Kind: "git", URL: "https://github.com/jalalirs/iocean-controllers"}}},
		{"bluerov-hold", Brief{Source: Source{Kind: "git", URL: "https://github.com/iocean/BlueROV_Hold.git"}}},
		{"wary", Brief{Source: Source{Kind: "git", URL: "https://github.com/iocean/controllers", Path: "src/wary"}}},
		{"controller-2026-01", Brief{Source: Source{Kind: "zip", Name: "2026_01.zip"}}},
		{"controller-b", Brief{Source: Source{Kind: "git", URL: "https://github.com/a/b"}}},
	}
	for _, c := range cases {
		if got := slugOf(c.brief); got != c.want {
			t.Errorf("slugOf(%+v) = %q, want %q", c.brief.Source, got, c.want)
		}
	}
	if (Brief{Source: Source{Kind: "zip", ObjectID: "obj_1", Name: "a.zip"}, Controllers: []string{"Hold"}}).Validate() == nil {
		t.Error("a controller that is not a slug was asked for")
	}
	many := make([]string, 51)
	for i := range many {
		many[i] = "c" + strings.Repeat("x", i+1)
	}
	if (Brief{Source: Source{Kind: "zip", ObjectID: "obj_1", Name: "a.zip"}, Controllers: many}).Validate() == nil {
		t.Error("51 controllers were asked for")
	}
}

func TestEachControllerThatPassedBecomesAStackWithWhereItCameFrom(t *testing.T) {
	build := Build{ID: "ctlb_1", OrgID: "org_k", Slug: "iocean-controllers", CreatedBy: "prin_1",
		Brief: Brief{Source: Source{Kind: "git", URL: "https://github.com/jalalirs/iocean-controllers", Ref: "main"}}}
	digest := "sha256:" + strings.Repeat("a", 64)
	report := map[string]any{"ok": true,
		"source": map[string]any{"kind": "git", "url": "https://github.com/jalalirs/iocean-controllers", "commit": "abc123"},
		"controllers": []any{
			map[string]any{"ok": true, "slug": "station-hold", "name": "Station hold", "imageDigest": digest,
				"controller": "controllers/station-hold/controller.py:StationHold", "image": "station-hold",
				"subscribes": []any{"/odom"}, "publishes": []any{"/cmd_wrench"}, "needs": map[string]any{"cpu": 1.0}},
			map[string]any{"ok": false, "slug": "sawtooth", "failure": "the tank check raised"},
		}}
	ok := passed(report)
	if len(ok) != 1 || ok[0]["slug"] != "station-hold" {
		t.Fatalf("passed %v", ok)
	}
	spec, err := stackOf(build, report, ok[0])
	if err != nil || spec.Name != "Station hold" || spec.ImageDigest != digest || string(spec.Publishes) != `["/cmd_wrench"]` {
		t.Fatalf("%+v %v", spec, err)
	}
	var source map[string]any
	_ = json.Unmarshal(spec.Source, &source)
	if source["commit"] != "abc123" || source["controllerBuild"] != "ctlb_1" ||
		source["controller"] != "controllers/station-hold/controller.py:StationHold" {
		t.Fatalf("source %v", source)
	}
	if _, err := stackOf(build, report, map[string]any{"ok": true, "slug": "x"}); err == nil {
		t.Error("a passed controller with no image digest was registered")
	}

	build.Report, build.Stacks = report, []Registered{{Slug: "station-hold", StackID: "stack_1"}}
	shown := controllersOf(build)
	if len(shown) != 2 || shown[0]["stackId"] != "stack_1" || shown[1]["ok"] != false || shown[1]["stackId"] != nil {
		t.Fatalf("shown %v", shown)
	}
}

// fakeRegistry is enough of the registry's interface to push to, each
// repository holding its own blobs as a registry does.
type fakeRegistry struct {
	mu        sync.Mutex
	blobs     map[string][]byte // repository@digest
	manifests map[string][]byte // repository:reference
	uploads   int
	mounts    int
}

func (f *fakeRegistry) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	f.mu.Lock()
	defer f.mu.Unlock()
	path := strings.TrimPrefix(r.URL.Path, "/v2/")
	repository, rest, _ := strings.Cut(path, "/blobs/")
	switch {
	case r.Method == http.MethodHead && rest != "":
		if _, ok := f.blobs[repository+"@"+rest]; ok {
			w.WriteHeader(http.StatusOK)
			return
		}
		w.WriteHeader(http.StatusNotFound)
	case r.Method == http.MethodPost && rest == "uploads/":
		if digest, from := r.URL.Query().Get("mount"), r.URL.Query().Get("from"); digest != "" {
			if body, ok := f.blobs[from+"@"+digest]; ok {
				f.mounts++
				f.blobs[repository+"@"+digest] = body
				w.WriteHeader(http.StatusCreated)
				return
			}
		}
		f.uploads++
		w.Header().Set("Location", "/v2/"+repository+"/blobs/uploads/session-1")
		w.WriteHeader(http.StatusAccepted)
	case r.Method == http.MethodPut && strings.HasPrefix(rest, "uploads/"):
		body, _ := io.ReadAll(r.Body)
		digest := r.URL.Query().Get("digest")
		if digest != digestOf(body) {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		f.blobs[repository+"@"+digest] = body
		w.WriteHeader(http.StatusCreated)
	case r.Method == http.MethodPut && strings.Contains(path, "/manifests/"):
		repository, reference, _ := strings.Cut(path, "/manifests/")
		body, _ := io.ReadAll(r.Body)
		f.manifests[repository+":"+reference] = body
		w.Header().Set("Docker-Content-Digest", digestOf(body))
		w.WriteHeader(http.StatusCreated)
	default:
		w.WriteHeader(http.StatusNotFound)
	}
}

func digestOf(b []byte) string {
	sum := sha256.Sum256(b)
	return "sha256:" + hex.EncodeToString(sum[:])
}

// someImages is an OCI image layout in a tar holding two controllers that
// share their base layer, each named by its slug, as the build makes them.
func someImages(t *testing.T) ([]byte, map[string]string) {
	t.Helper()
	base, config := []byte("the ROS base"), []byte(`{"architecture":"amd64","os":"linux"}`)
	blobs := map[string][]byte{digestOf(base): base, digestOf(config): config}
	digests := map[string]string{}
	var described []any
	for _, slug := range []string{"station-hold", "sawtooth"} {
		own := []byte("the controller " + slug)
		blobs[digestOf(own)] = own
		manifest, _ := json.Marshal(map[string]any{
			"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
			"config": map[string]any{"mediaType": "application/vnd.oci.image.config.v1+json",
				"digest": digestOf(config), "size": len(config)},
			"layers": []any{
				map[string]any{"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip", "digest": digestOf(base), "size": len(base)},
				map[string]any{"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip", "digest": digestOf(own), "size": len(own)},
			},
		})
		blobs[digestOf(manifest)] = manifest
		digests[slug] = digestOf(manifest)
		described = append(described, map[string]any{
			"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": digestOf(manifest), "size": len(manifest),
			"annotations": map[string]any{"org.opencontainers.image.ref.name": slug,
				"io.containerd.image.name": "iocean/controller:" + slug}})
	}
	index, _ := json.Marshal(map[string]any{"schemaVersion": 2, "manifests": described})
	var out bytes.Buffer
	archive := tar.NewWriter(&out)
	write := func(name string, body []byte) {
		_ = archive.WriteHeader(&tar.Header{Name: name, Mode: 0o644, Size: int64(len(body)), Typeflag: tar.TypeReg})
		_, _ = archive.Write(body)
	}
	write("oci-layout", []byte(`{"imageLayoutVersion":"1.0.0"}`))
	write("index.json", index)
	for digest, body := range blobs {
		write("blobs/sha256/"+digest[7:], body)
	}
	_ = archive.Close()
	return out.Bytes(), digests
}

func TestEachControllerIsPushedToItsOwnRepositoryAndSharedBlobsAreSentOnce(t *testing.T) {
	fake := &fakeRegistry{blobs: map[string][]byte{}, manifests: map[string][]byte{}}
	server := httptest.NewServer(fake)
	defer server.Close()

	raw, want := someImages(t)
	images, err := unpack(bytes.NewReader(raw), t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	registry := newRegistry(server.URL)
	for _, slug := range []string{"station-hold", "sawtooth"} {
		image, ok := images.image(slug)
		if !ok || image.Digest != want[slug] {
			t.Fatalf("the layout's %s is %+v", slug, image)
		}
		repository := "autonomy/kaust/" + slug
		got, err := registry.push(t.Context(), images, image, repository)
		if err != nil || got != want[slug] {
			t.Fatalf("%s pushed as %q (%v), want %q", slug, got, err, want[slug])
		}
		if fake.manifests[repository+":"+want[slug]] == nil || fake.manifests[repository+":latest"] == nil {
			t.Fatalf("%s's manifest is not there by digest and as latest", slug)
		}
	}
	// Four blobs in all (base, config, two controllers); the second
	// repository has the base and the config mounted, not sent again.
	if fake.uploads != 4 || fake.mounts != 2 {
		t.Errorf("%d uploads and %d mounts", fake.uploads, fake.mounts)
	}
	if _, ok := images.image("learned-hold"); ok {
		t.Error("a controller the layout does not hold was found in it")
	}
}

func TestAnEmptyImageIsNotAnImage(t *testing.T) {
	var empty bytes.Buffer
	_ = tar.NewWriter(&empty).Close()
	if _, err := unpack(bytes.NewReader(empty.Bytes()), t.TempDir()); err == nil {
		t.Fatal("an empty tar was read as an image")
	}
}

func TestAnIndexIsReadForWhatItListsAndFoldersAddTheRest(t *testing.T) {
	listed := controllersInToml([]byte(`# The controllers in this repository
[[controller]]
slug = "station-hold"
name = "Station hold"
entry = "controllers/station-hold/controller.py:StationHold"

[[controller]]
name = "Sawtooth (glider)"
entry = "controllers/sawtooth/controller.py:Sawtooth"
[controller.needs]
cpu = 2
`))
	if len(listed) != 2 || listed[0].Name != "Station hold" || listed[1].Slug != "sawtooth" {
		t.Fatalf("%+v", listed)
	}
	all := merged(listed, []Found{{Slug: "wary", Entry: "controllers/wary/controller.py"}, {Slug: "sawtooth"}})
	if len(all) != 3 || all[2].Slug != "wary" {
		t.Fatalf("%+v", all)
	}
}

func TestARepositoryIsLookedIntoOnceAMinute(t *testing.T) {
	calls := 0
	github := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		switch {
		case !strings.Contains(r.URL.Path, "iocean-controllers"):
			w.WriteHeader(http.StatusNotFound)
		case strings.HasSuffix(r.URL.Path, "/iocean.toml"):
			_, _ = w.Write([]byte("[[controller]]\nslug = \"station-hold\"\nentry = \"controllers/station-hold/controller.py:StationHold\"\n"))
		case strings.Contains(r.URL.Path, "/git/trees/"):
			_, _ = w.Write([]byte(`{"tree": [{"path": "controllers/station-hold/controller.py", "type": "blob"},
				{"path": "controllers/wary/controller.py", "type": "blob"}, {"path": "README.md", "type": "blob"}]}`))
		default:
			w.WriteHeader(http.StatusNotFound)
		}
	}))
	defer github.Close()
	looker := NewLooker()
	looker.Raw, looker.API = github.URL, github.URL
	look, err := looker.Look(t.Context(), "https://github.com/jalalirs/iocean-controllers", "", "")
	if err != nil || len(look.Controllers) != 2 || look.Controllers[1].Slug != "wary" || look.Said != "" {
		t.Fatalf("%+v %v", look, err)
	}
	if _, err := looker.Look(t.Context(), "https://github.com/jalalirs/iocean-controllers", "", ""); err != nil || calls != 2 {
		t.Fatalf("looked again within the minute: %d calls (%v)", calls, err)
	}
	if _, err := looker.Look(t.Context(), "https://gitlab.com/a/b", "", ""); err == nil {
		t.Error("a repository not on GitHub was looked into")
	}
	empty, err := looker.Look(t.Context(), "https://github.com/someone/nothing", "main", "sub")
	if err != nil || len(empty.Controllers) != 0 || empty.Said == "" {
		t.Fatalf("a repository with nothing in it: %+v %v", empty, err)
	}
}
