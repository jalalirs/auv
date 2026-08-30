package cache

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"io"
	"log/slog"
	"net/http"
	"net/http/httptest"
	"os"
	"path/filepath"
	"strings"
	"testing"
)

func quiet() *slog.Logger {
	return slog.New(slog.NewTextHandler(io.Discard, nil))
}

func digestOf(content string) string {
	sum := sha256.Sum256([]byte(content))
	return hex.EncodeToString(sum[:])
}

// serve stands in for object storage, and counts what was actually asked for so
// that a test can tell fetching from re-fetching.
func serve(t *testing.T, contents map[string]string, asked *int) *httptest.Server {
	t.Helper()
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body, ok := contents[strings.TrimPrefix(r.URL.Path, "/")]
		if !ok {
			w.WriteHeader(http.StatusNotFound)
			return
		}
		*asked++
		_, _ = io.WriteString(w, body)
	}))
	t.Cleanup(server.Close)
	return server
}

func TestSyncFetchesOnceAndAssemblesThePackage(t *testing.T) {
	asked := 0
	server := serve(t, map[string]string{
		"scene": "a tank, of sorts",
		"tex":   "some pixels",
	}, &asked)

	cache, err := New(t.TempDir(), quiet())
	if err != nil {
		t.Fatalf("opening the cache: %v", err)
	}

	files := []File{
		{Path: "scene.usd", Digest: digestOf("a tank, of sorts"), SizeBytes: 16,
			URL: server.URL + "/scene"},
		{Path: "textures/tex.jpg", Digest: digestOf("some pixels"), SizeBytes: 11,
			URL: server.URL + "/tex"},
	}

	first, err := cache.Sync(context.Background(), "ver_1", files)
	if err != nil {
		t.Fatalf("syncing: %v", err)
	}
	if first.Fetched != 2 || first.Held != 0 {
		t.Errorf("first sync fetched %d and held %d; expected to fetch both", first.Fetched, first.Held)
	}

	for _, path := range []string{"scene.usd", "textures/tex.jpg"} {
		if _, err := os.Stat(filepath.Join(first.Directory, path)); err != nil {
			t.Errorf("%s is not in the assembled package: %v", path, err)
		}
	}

	// A digest never changes meaning, so a second sync of the same version has
	// nothing to fetch. This is the whole reason packages are addressed by
	// content, and the thing that makes a 400 MB vehicle cheap to re-publish.
	second, err := cache.Sync(context.Background(), "ver_2", files)
	if err != nil {
		t.Fatalf("syncing again: %v", err)
	}
	if second.Fetched != 0 || second.Held != 2 {
		t.Errorf("second sync fetched %d and held %d; it should have fetched nothing",
			second.Fetched, second.Held)
	}
	if asked != 2 {
		t.Errorf("the store was asked %d times; it should have been asked twice in total", asked)
	}
}

func TestBytesThatAreNotWhatWasAskedForAreRefused(t *testing.T) {
	// A file that arrives corrupted and is cached is worse than one that fails
	// to arrive: the failure is loud and the corruption is silent, and every
	// dive afterwards would quietly use the wrong scene.
	asked := 0
	server := serve(t, map[string]string{"scene": "not what was promised"}, &asked)

	cache, err := New(t.TempDir(), quiet())
	if err != nil {
		t.Fatalf("opening the cache: %v", err)
	}

	_, err = cache.Sync(context.Background(), "ver_1", []File{
		{Path: "scene.usd", Digest: digestOf("something else entirely"),
			SizeBytes: 21, URL: server.URL + "/scene"},
	})
	if err == nil {
		t.Fatal("bytes that did not match their digest were accepted")
	}
	if !strings.Contains(err.Error(), "not the file the package names") {
		t.Errorf("the refusal did not say what was wrong: %v", err)
	}
	if cache.Holds(digestOf("something else entirely")) {
		t.Error("the cache kept bytes that were not what it asked for")
	}
}

func TestAPackageIsWholeOrAbsent(t *testing.T) {
	// A directory bearing a version's name must be the whole package. A
	// half-assembled one that a dive could pick up would be worse than none,
	// because the dive would run and the result would look real.
	asked := 0
	server := serve(t, map[string]string{"good": "fine"}, &asked)

	cache, err := New(t.TempDir(), quiet())
	if err != nil {
		t.Fatalf("opening the cache: %v", err)
	}

	report, err := cache.Sync(context.Background(), "ver_1", []File{
		{Path: "good.usd", Digest: digestOf("fine"), SizeBytes: 4, URL: server.URL + "/good"},
		{Path: "missing.usd", Digest: digestOf("never mind"), SizeBytes: 10,
			URL: server.URL + "/absent"},
	})
	if err == nil {
		t.Fatal("a package with an unfetchable file was assembled")
	}
	if _, statErr := os.Stat(report.Directory); !os.IsNotExist(statErr) {
		t.Error("a partial package was left where a dive could find it")
	}
}

func TestAPathCannotEscapeThePackage(t *testing.T) {
	asked := 0
	server := serve(t, map[string]string{"x": "harmless"}, &asked)

	root := t.TempDir()
	cache, err := New(root, quiet())
	if err != nil {
		t.Fatalf("opening the cache: %v", err)
	}

	_, err = cache.Sync(context.Background(), "ver_1", []File{
		{Path: "../../escaped.usd", Digest: digestOf("harmless"), SizeBytes: 8,
			URL: server.URL + "/x"},
	})
	if err == nil {
		t.Fatal("a path that leaves the package directory was accepted")
	}
	if _, statErr := os.Stat(filepath.Join(root, "escaped.usd")); !os.IsNotExist(statErr) {
		t.Error("a file was written outside the package")
	}
}
