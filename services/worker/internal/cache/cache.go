// Package cache holds the packages a node has fetched, addressed by content.
//
// A digest never changes meaning, so this cache is append-only: nothing it
// holds can go stale, there is no invalidation, and syncing a new version of a
// city means fetching the files whose digests are new rather than the package
// again. That is the whole reason packages are content-addressed, and it is
// what makes a 400 MB vehicle cheap to re-publish.
//
// Files are stored under their own digest and a package is assembled from them
// by hard link where the filesystem allows it, so two versions sharing a
// texture cost one copy of it.
package cache

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net/http"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"time"
)

// File is one file in a package, as the control plane describes it.
type File struct {
	Path      string `json:"path"`
	Digest    string `json:"digest"`
	SizeBytes int64  `json:"sizeBytes"`
	MediaType string `json:"mediaType"`
	URL       string `json:"url"`
}

// Cache is a directory of content-addressed files and assembled packages.
type Cache struct {
	root   string
	client *http.Client
	logger *slog.Logger
}

// New opens a cache rooted at a directory, creating it if it is not there.
func New(root string, logger *slog.Logger) (*Cache, error) {
	for _, dir := range []string{filepath.Join(root, "objects"), filepath.Join(root, "packages")} {
		if err := os.MkdirAll(dir, 0o755); err != nil {
			return nil, fmt.Errorf("preparing the cache at %s: %w", root, err)
		}
	}
	return &Cache{
		root: root,
		// Long, because a city is hundreds of megabytes and a slow link is not
		// a failure. The context the caller passes is what cancels this.
		client: &http.Client{Timeout: 30 * time.Minute},
		logger: logger,
	}, nil
}

// objectPath is where a digest's bytes live: fanned out by the first byte, so
// that a directory listing stays usable when there are a hundred thousand of
// them.
func (c *Cache) objectPath(digest string) string {
	if len(digest) < 2 {
		return filepath.Join(c.root, "objects", digest)
	}
	return filepath.Join(c.root, "objects", digest[:2], digest)
}

// Holds reports whether the cache already has these bytes.
func (c *Cache) Holds(digest string) bool {
	info, err := os.Stat(c.objectPath(digest))
	return err == nil && info.Mode().IsRegular()
}

// Report is what a sync did, so that a node can say why it took as long as it
// did without anyone reading a log.
type Report struct {
	Directory string
	Fetched   int
	Held      int
	Bytes     int64
	Took      time.Duration
}

// Sync makes a package present under a directory named by its version, and
// returns where it put it.
//
// Only files the cache lacks are fetched. Every fetch is verified against the
// digest it was asked for before it is kept, because a file that arrives
// corrupted and is cached is worse than one that fails to arrive: the failure
// is loud and the corruption is not.
func (c *Cache) Sync(ctx context.Context, versionID string, files []File) (Report, error) {
	started := time.Now()
	report := Report{Directory: filepath.Join(c.root, "packages", versionID)}

	// Assembled under a temporary name and moved into place at the end, so
	// that a directory bearing a version's name is either the whole package or
	// absent. A half-assembled one that a dive could pick up would be worse
	// than none.
	staging := report.Directory + ".partial"
	if err := os.RemoveAll(staging); err != nil {
		return report, fmt.Errorf("clearing a previous attempt: %w", err)
	}
	if err := os.MkdirAll(staging, 0o755); err != nil {
		return report, fmt.Errorf("preparing to assemble %s: %w", versionID, err)
	}
	defer os.RemoveAll(staging)

	// Largest first: the long pole starts as early as possible, and a failure
	// on a big file is found before time is spent on small ones.
	ordered := make([]File, len(files))
	copy(ordered, files)
	sort.Slice(ordered, func(i, j int) bool { return ordered[i].SizeBytes > ordered[j].SizeBytes })

	for _, file := range ordered {
		if err := ctx.Err(); err != nil {
			return report, err
		}
		if c.Holds(file.Digest) {
			report.Held++
		} else {
			if err := c.fetch(ctx, file); err != nil {
				return report, err
			}
			report.Fetched++
			report.Bytes += file.SizeBytes
		}
		if err := c.place(staging, file); err != nil {
			return report, err
		}
	}

	if err := os.RemoveAll(report.Directory); err != nil {
		return report, fmt.Errorf("replacing an earlier copy of %s: %w", versionID, err)
	}
	if err := os.Rename(staging, report.Directory); err != nil {
		return report, fmt.Errorf("putting %s in place: %w", versionID, err)
	}

	report.Took = time.Since(started)
	return report, nil
}

// fetch downloads one file and keeps it only if it is what was asked for.
func (c *Cache) fetch(ctx context.Context, file File) error {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, file.URL, nil)
	if err != nil {
		return fmt.Errorf("asking for %s: %w", file.Path, err)
	}
	response, err := c.client.Do(request)
	if err != nil {
		return fmt.Errorf("fetching %s: %w", file.Path, err)
	}
	defer response.Body.Close()

	if response.StatusCode != http.StatusOK {
		return fmt.Errorf("fetching %s: the store answered %s", file.Path, response.Status)
	}

	final := c.objectPath(file.Digest)
	if err := os.MkdirAll(filepath.Dir(final), 0o755); err != nil {
		return fmt.Errorf("preparing to store %s: %w", file.Path, err)
	}

	// Written beside its destination and moved only once it has been checked,
	// so an interrupted fetch cannot leave something under a digest that does
	// not describe it.
	partial, err := os.CreateTemp(filepath.Dir(final), ".fetching-*")
	if err != nil {
		return fmt.Errorf("preparing to store %s: %w", file.Path, err)
	}
	defer os.Remove(partial.Name())

	hasher := sha256.New()
	written, err := io.Copy(io.MultiWriter(partial, hasher), response.Body)
	if closeErr := partial.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		return fmt.Errorf("storing %s: %w", file.Path, err)
	}

	if got := hex.EncodeToString(hasher.Sum(nil)); !strings.EqualFold(got, file.Digest) {
		return fmt.Errorf(
			"%s arrived as %s but was asked for as %s, so it is not the file the package names",
			file.Path, got[:12], file.Digest[:12])
	}
	if written != file.SizeBytes {
		return fmt.Errorf("%s is %d bytes and the package says %d",
			file.Path, written, file.SizeBytes)
	}

	if err := os.Chmod(partial.Name(), 0o444); err != nil {
		return fmt.Errorf("sealing %s: %w", file.Path, err)
	}
	if err := os.Rename(partial.Name(), final); err != nil && !errors.Is(err, os.ErrExist) {
		return fmt.Errorf("keeping %s: %w", file.Path, err)
	}
	c.logger.Debug("fetched", "path", file.Path, "bytes", written, "digest", file.Digest[:12])
	return nil
}

// place makes a cached object appear at its path within an assembled package.
func (c *Cache) place(staging string, file File) error {
	target := filepath.Join(staging, filepath.FromSlash(file.Path))

	// A path from the platform is checked here as well as there, because this
	// one is about to be written to a filesystem and a package that escapes its
	// own directory would be writing wherever it liked.
	if !strings.HasPrefix(filepath.Clean(target)+string(os.PathSeparator),
		filepath.Clean(staging)+string(os.PathSeparator)) {
		return fmt.Errorf("%s would be written outside the package", file.Path)
	}
	if err := os.MkdirAll(filepath.Dir(target), 0o755); err != nil {
		return fmt.Errorf("preparing %s: %w", file.Path, err)
	}

	// Hard link where the filesystem allows it, so two versions sharing a
	// texture cost one copy. Where it does not, copy: correctness first.
	if err := os.Link(c.objectPath(file.Digest), target); err == nil {
		return nil
	}
	source, err := os.Open(c.objectPath(file.Digest))
	if err != nil {
		return fmt.Errorf("reading cached %s: %w", file.Path, err)
	}
	defer source.Close()

	destination, err := os.Create(target)
	if err != nil {
		return fmt.Errorf("writing %s: %w", file.Path, err)
	}
	_, err = io.Copy(destination, source)
	if closeErr := destination.Close(); err == nil {
		err = closeErr
	}
	if err != nil {
		return fmt.Errorf("writing %s: %w", file.Path, err)
	}
	return nil
}

// Usage is how much room the cache is taking.
func (c *Cache) Usage() (files int, bytes int64, err error) {
	err = filepath.WalkDir(filepath.Join(c.root, "objects"), func(_ string, entry os.DirEntry, err error) error {
		if err != nil || entry.IsDir() {
			return err
		}
		info, err := entry.Info()
		if err != nil {
			return err
		}
		files++
		bytes += info.Size()
		return nil
	})
	return files, bytes, err
}
