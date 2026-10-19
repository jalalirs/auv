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

func TestABuildIsCalledByItsSlugOrItsSource(t *testing.T) {
	cases := []struct {
		want  string
		brief Brief
	}{
		{"wary", Brief{Slug: "wary", Source: Source{Kind: "git", URL: "https://github.com/a/b"}}},
		{"bluerov-hold", Brief{Source: Source{Kind: "git", URL: "https://github.com/iocean/BlueROV_Hold.git"}}},
		{"wary", Brief{Source: Source{Kind: "git", URL: "https://github.com/iocean/controllers", Path: "src/wary"}}},
		{"controller-2026-01", Brief{Source: Source{Kind: "zip", Name: "2026_01.zip"}}},
	}
	for _, c := range cases {
		if got := slugOf(c.brief); got != c.want {
			t.Errorf("slugOf(%+v) = %q, want %q", c.brief.Source, got, c.want)
		}
	}
}

func TestAPassedReportBecomesAStackWithWhereItCameFrom(t *testing.T) {
	build := Build{ID: "ctlb_1", OrgID: "org_k", Slug: "wary", CreatedBy: "prin_1",
		Brief: Brief{Source: Source{Kind: "git", URL: "https://github.com/iocean/wary", Ref: "main"}}}
	digest := "sha256:" + strings.Repeat("a", 64)
	spec, err := stackOf(build, map[string]any{"ok": true, "slug": "wary", "name": "Wary",
		"imageDigest": digest, "subscribes": []any{"/odom"}, "publishes": []any{"/cmd_wrench"},
		"wantsGpu": false, "needs": map[string]any{"cpu": 1.0},
		"source": map[string]any{"kind": "git", "url": "https://github.com/iocean/wary", "commit": "abc123"}})
	if err != nil || spec.Name != "Wary" || spec.ImageDigest != digest || string(spec.Publishes) != `["/cmd_wrench"]` {
		t.Fatalf("%+v %v", spec, err)
	}
	var source map[string]any
	_ = json.Unmarshal(spec.Source, &source)
	if source["commit"] != "abc123" || source["controllerBuild"] != "ctlb_1" {
		t.Fatalf("source %v", source)
	}
	if _, err := stackOf(build, map[string]any{"ok": true}); err == nil {
		t.Error("a passed report with no image digest was registered")
	}
}

// fakeRegistry is enough of the registry's interface to push to.
type fakeRegistry struct {
	mu        sync.Mutex
	blobs     map[string][]byte
	manifests map[string][]byte
	uploads   int
}

func (f *fakeRegistry) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	f.mu.Lock()
	defer f.mu.Unlock()
	path := r.URL.Path
	switch {
	case r.Method == http.MethodHead && strings.Contains(path, "/blobs/"):
		digest := path[strings.LastIndex(path, "/")+1:]
		if _, ok := f.blobs[digest]; ok {
			w.WriteHeader(http.StatusOK)
			return
		}
		w.WriteHeader(http.StatusNotFound)
	case r.Method == http.MethodPost && strings.HasSuffix(path, "/blobs/uploads/"):
		f.uploads++
		w.Header().Set("Location", path+"session-1")
		w.WriteHeader(http.StatusAccepted)
	case r.Method == http.MethodPut && strings.Contains(path, "/blobs/uploads/"):
		body, _ := io.ReadAll(r.Body)
		sum := sha256.Sum256(body)
		if want := r.URL.Query().Get("digest"); want != "sha256:"+hex.EncodeToString(sum[:]) {
			w.WriteHeader(http.StatusBadRequest)
			return
		}
		f.blobs[r.URL.Query().Get("digest")] = body
		w.WriteHeader(http.StatusCreated)
	case r.Method == http.MethodPut && strings.Contains(path, "/manifests/"):
		body, _ := io.ReadAll(r.Body)
		sum := sha256.Sum256(body)
		f.manifests[path[strings.LastIndex(path, "/")+1:]] = body
		w.Header().Set("Docker-Content-Digest", "sha256:"+hex.EncodeToString(sum[:]))
		w.WriteHeader(http.StatusCreated)
	default:
		w.WriteHeader(http.StatusNotFound)
	}
}

func digestOf(b []byte) string {
	sum := sha256.Sum256(b)
	return "sha256:" + hex.EncodeToString(sum[:])
}

// anImage is an OCI image layout in a tar: one layer, its config, its
// manifest and the index naming it.
func anImage(t *testing.T) ([]byte, string) {
	t.Helper()
	layer, config := []byte("a layer's bytes"), []byte(`{"architecture":"amd64","os":"linux"}`)
	manifest, _ := json.Marshal(map[string]any{
		"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
		"config": map[string]any{"mediaType": "application/vnd.oci.image.config.v1+json",
			"digest": digestOf(config), "size": len(config)},
		"layers": []any{map[string]any{"mediaType": "application/vnd.oci.image.layer.v1.tar+gzip",
			"digest": digestOf(layer), "size": len(layer)}},
	})
	index, _ := json.Marshal(map[string]any{"schemaVersion": 2, "manifests": []any{map[string]any{
		"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": digestOf(manifest), "size": len(manifest)}}})
	var out bytes.Buffer
	archive := tar.NewWriter(&out)
	for name, body := range map[string][]byte{
		"oci-layout": []byte(`{"imageLayoutVersion":"1.0.0"}`), "index.json": index,
		"blobs/sha256/" + digestOf(layer)[7:]:    layer,
		"blobs/sha256/" + digestOf(config)[7:]:   config,
		"blobs/sha256/" + digestOf(manifest)[7:]: manifest,
	} {
		_ = archive.WriteHeader(&tar.Header{Name: name, Mode: 0o644, Size: int64(len(body)), Typeflag: tar.TypeReg})
		_, _ = archive.Write(body)
	}
	_ = archive.Close()
	return out.Bytes(), digestOf(manifest)
}

func TestAnImageLayoutIsPushedBlobsFirstThenItsManifestByDigestAndAsLatest(t *testing.T) {
	fake := &fakeRegistry{blobs: map[string][]byte{}, manifests: map[string][]byte{}}
	server := httptest.NewServer(fake)
	defer server.Close()

	raw, want := anImage(t)
	image, err := unpack(bytes.NewReader(raw), t.TempDir())
	if err != nil {
		t.Fatal(err)
	}
	got, err := newRegistry(server.URL).push(t.Context(), image, "autonomy/kaust/wary")
	if err != nil || got != want {
		t.Fatalf("pushed as %q (%v), want %q", got, err, want)
	}
	if len(fake.blobs) != 2 || fake.manifests[want] == nil || fake.manifests["latest"] == nil {
		t.Fatalf("the registry holds %d blobs and manifests %v", len(fake.blobs), len(fake.manifests))
	}

	// Pushed again, the blobs it already has are not sent again.
	uploads := fake.uploads
	if _, err := newRegistry(server.URL).push(t.Context(), image, "autonomy/kaust/wary"); err != nil {
		t.Fatal(err)
	}
	if fake.uploads != uploads {
		t.Errorf("blobs the registry had were uploaded again")
	}
}

func TestAnEmptyImageIsNotAnImage(t *testing.T) {
	var empty bytes.Buffer
	_ = tar.NewWriter(&empty).Close()
	if _, err := unpack(bytes.NewReader(empty.Bytes()), t.TempDir()); err == nil {
		t.Fatal("an empty tar was read as an image")
	}
}
