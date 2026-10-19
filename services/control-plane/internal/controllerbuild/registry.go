package controllerbuild

import (
	"archive/tar"
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"path"
	"path/filepath"
	"regexp"
	"strings"
)

// Images arrive as one OCI image layout in a tar (index.json, oci-layout,
// blobs/sha256/*), which is what a build without the host's Docker can make:
// one manifest per controller, named by its slug, their blobs shared. Hosts
// pull from a registry, so the platform puts each controller in its own as a
// repository of its own: each blob the registry does not already have (sent
// once, and mounted into the next repository rather than sent again), then
// the manifest, by its digest and as "latest". This speaks the registry's
// HTTP interface directly; it needs six calls, which is fewer than a client
// library's documentation.

// layout is an image layout unpacked onto disk, its blobs by digest.
type layout struct {
	dir string
	// manifests are the images index.json names.
	manifests []descriptor
}

type descriptor struct {
	MediaType   string            `json:"mediaType"`
	Digest      string            `json:"digest"`
	Size        int64             `json:"size"`
	Annotations map[string]string `json:"annotations,omitempty"`
}

// image finds the manifest a controller's image is, by the name the build
// gave it.
func (l layout) image(name string) (descriptor, bool) {
	for _, one := range l.manifests {
		if one.Annotations["org.opencontainers.image.ref.name"] == name ||
			strings.HasSuffix(one.Annotations["io.containerd.image.name"], ":"+name) {
			return one, true
		}
	}
	return descriptor{}, false
}

var blobPath = regexp.MustCompile(`^blobs/sha256/[0-9a-f]{64}$`)

// unpack writes an image layout's blobs to dir and reads which manifest it is.
func unpack(from io.Reader, dir string) (layout, error) {
	archive := tar.NewReader(from)
	var index []byte
	for {
		header, err := archive.Next()
		if errors.Is(err, io.EOF) {
			break
		}
		if err != nil {
			return layout{}, fmt.Errorf("reading the image: %w", err)
		}
		if header.Typeflag != tar.TypeReg {
			continue
		}
		name := path.Clean(strings.TrimPrefix(header.Name, "./"))
		switch {
		case name == "index.json":
			if index, err = io.ReadAll(io.LimitReader(archive, 1<<20)); err != nil {
				return layout{}, err
			}
		case blobPath.MatchString(name):
			file, err := os.Create(filepath.Join(dir, "sha256-"+path.Base(name)))
			if err != nil {
				return layout{}, err
			}
			_, err = io.CopyN(file, archive, header.Size)
			if closed := file.Close(); err == nil {
				err = closed
			}
			if err != nil {
				return layout{}, fmt.Errorf("reading %s from the image: %w", name, err)
			}
		}
	}
	if index == nil {
		return layout{}, errors.New("the image has no index.json, so it is not an OCI image layout")
	}
	var said struct {
		Manifests []descriptor `json:"manifests"`
	}
	if err := json.Unmarshal(index, &said); err != nil || len(said.Manifests) == 0 {
		return layout{}, errors.New("the image's index.json names no manifest")
	}
	return layout{dir: dir, manifests: said.Manifests}, nil
}

func (l layout) blob(digest string) (string, error) {
	hex, ok := strings.CutPrefix(digest, "sha256:")
	if !ok || len(hex) != 64 {
		return "", fmt.Errorf("%s is not a sha256 digest", digest)
	}
	at := filepath.Join(l.dir, "sha256-"+hex)
	if _, err := os.Stat(at); err != nil {
		return "", fmt.Errorf("the image names %s and does not hold it", digest)
	}
	return at, nil
}

// registry is a registry the platform pushes to.
type registry struct {
	base string
	http *http.Client
	// sent says which repository each blob was first put in, so the next
	// repository that needs it has it mounted rather than sent again.
	sent map[string]string
}

func newRegistry(address string) *registry {
	base := address
	if !strings.Contains(base, "://") {
		// The platform's own registry, on its own network, has no certificate.
		base = "http://" + base
	}
	return &registry{base: strings.TrimRight(base, "/"), http: &http.Client{}, sent: map[string]string{}}
}

// push puts one image of a layout in the registry under repository, and
// reports the manifest's digest as the registry has it.
func (r *registry) push(ctx context.Context, image layout, of descriptor, repository string) (string, error) {
	digest, err := r.pushManifest(ctx, image, repository, of)
	if err != nil {
		return "", err
	}
	at, err := image.blob(of.Digest)
	if err != nil {
		return "", err
	}
	raw, err := os.ReadFile(at)
	if err != nil {
		return "", err
	}
	if _, err := r.putManifest(ctx, repository, "latest", of.MediaType, raw); err != nil {
		return "", err
	}
	return digest, nil
}

// pushManifest pushes what a manifest refers to and then the manifest. An
// index of manifests (an image built for several platforms) has each of its
// manifests pushed first.
func (r *registry) pushManifest(ctx context.Context, image layout, repository string, of descriptor) (string, error) {
	at, err := image.blob(of.Digest)
	if err != nil {
		return "", err
	}
	raw, err := os.ReadFile(at)
	if err != nil {
		return "", err
	}
	var manifest struct {
		MediaType string       `json:"mediaType"`
		Config    *descriptor  `json:"config"`
		Layers    []descriptor `json:"layers"`
		Manifests []descriptor `json:"manifests"`
	}
	if err := json.Unmarshal(raw, &manifest); err != nil {
		return "", fmt.Errorf("the image's manifest %s cannot be read: %w", of.Digest, err)
	}
	for _, child := range manifest.Manifests {
		if _, err := r.pushManifest(ctx, image, repository, child); err != nil {
			return "", err
		}
	}
	blobs := append([]descriptor{}, manifest.Layers...)
	if manifest.Config != nil {
		blobs = append(blobs, *manifest.Config)
	}
	for _, one := range blobs {
		if err := r.pushBlob(ctx, image, repository, one.Digest); err != nil {
			return "", err
		}
	}
	media := of.MediaType
	if media == "" {
		media = manifest.MediaType
	}
	got, err := r.putManifest(ctx, repository, of.Digest, media, raw)
	if err == nil && got == "" {
		// A registry that does not say what it stored stored what it was
		// asked to, under that digest, or it would have refused.
		got = of.Digest
	}
	return got, err
}

func (r *registry) pushBlob(ctx context.Context, image layout, repository, digest string) error {
	at, err := image.blob(digest)
	if err != nil {
		return err
	}
	head, err := r.do(ctx, http.MethodHead, r.base+"/v2/"+repository+"/blobs/"+digest, nil, nil)
	if err == nil && head.StatusCode == http.StatusOK {
		return nil
	}
	start := r.base + "/v2/" + repository + "/blobs/uploads/"
	if from, ok := r.sent[digest]; ok && from != repository {
		// Already in another repository: the registry links it in place, and
		// says 201. One that will not says 202 and takes an upload instead.
		start += "?" + url.Values{"mount": {digest}, "from": {from}}.Encode()
	}
	started, err := r.do(ctx, http.MethodPost, start, nil, nil)
	if err != nil {
		return err
	}
	if started.StatusCode == http.StatusCreated {
		return nil
	}
	if started.StatusCode != http.StatusAccepted {
		return fmt.Errorf("the registry would not start an upload of %s: %s", digest, started.Status)
	}
	location, err := url.Parse(started.Header.Get("Location"))
	if err != nil || started.Header.Get("Location") == "" {
		return fmt.Errorf("the registry started an upload of %s and said nowhere to send it", digest)
	}
	target := location
	if !location.IsAbs() {
		base, _ := url.Parse(r.base)
		target = base.ResolveReference(location)
	}
	query := target.Query()
	query.Set("digest", digest)
	target.RawQuery = query.Encode()
	file, err := os.Open(at)
	if err != nil {
		return err
	}
	defer file.Close()
	info, err := file.Stat()
	if err != nil {
		return err
	}
	put, err := r.do(ctx, http.MethodPut, target.String(), file,
		map[string]string{"Content-Type": "application/octet-stream", "Content-Length": fmt.Sprint(info.Size())})
	if err != nil {
		return err
	}
	if put.StatusCode != http.StatusCreated {
		return fmt.Errorf("the registry refused %s: %s", digest, put.Status)
	}
	r.sent[digest] = repository
	return nil
}

func (r *registry) putManifest(ctx context.Context, repository, reference, mediaType string, raw []byte) (string, error) {
	put, err := r.do(ctx, http.MethodPut, r.base+"/v2/"+repository+"/manifests/"+reference,
		bytes.NewReader(raw), map[string]string{"Content-Type": mediaType})
	if err != nil {
		return "", err
	}
	if put.StatusCode != http.StatusCreated {
		return "", fmt.Errorf("the registry refused the image's manifest as %s: %s", reference, put.Status)
	}
	return put.Header.Get("Docker-Content-Digest"), nil
}

// do makes one call and reads its answer, so the connection is reused.
func (r *registry) do(ctx context.Context, method, to string, body io.Reader, headers map[string]string) (*http.Response, error) {
	request, err := http.NewRequestWithContext(ctx, method, to, body)
	if err != nil {
		return nil, err
	}
	for k, v := range headers {
		if k == "Content-Length" {
			fmt.Sscan(v, &request.ContentLength)
			continue
		}
		request.Header.Set(k, v)
	}
	response, err := r.http.Do(request)
	if err != nil {
		return nil, fmt.Errorf("reaching the registry: %w", err)
	}
	_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 1<<20))
	response.Body.Close()
	return response, nil
}
