package controllerbuild

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"path"
	"regexp"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/domain"
)

// Before somebody builds from a repository, they are shown what is in it, so
// they can choose which controllers to build. A repository says so in an
// iocean.toml at its root (or at the folder named), as [[controller]] entries;
// a folder under controllers/ holding a controller.py is a controller too.
// Both are read from GitHub's public content, without credentials, so only a
// public repository can be looked into.

// Found is a controller a source holds.
type Found struct {
	Slug  string `json:"slug"`
	Name  string `json:"name,omitempty"`
	Entry string `json:"entry,omitempty"`
}

// Look is what a repository holds, as far as could be seen.
type Look struct {
	Controllers []Found `json:"controllers"`
	// Said is what could not be seen, or why there is nothing: a build then
	// looks for one controller in the source itself.
	Said string `json:"said,omitempty"`
}

// Looker looks into repositories, and remembers what it saw for a minute, so
// somebody choosing does not spend GitHub's patience for everyone.
type Looker struct {
	// Raw serves files (raw.githubusercontent.com); API answers questions
	// about a repository (api.github.com).
	Raw, API string
	http     *http.Client

	mu   sync.Mutex
	seen map[string]seen
}

type seen struct {
	look Look
	at   time.Time
}

// NewLooker builds a Looker over GitHub.
func NewLooker() *Looker {
	return &Looker{Raw: "https://raw.githubusercontent.com", API: "https://api.github.com",
		http: &http.Client{Timeout: 10 * time.Second}, seen: map[string]seen{}}
}

const remembered = time.Minute

// Look says which controllers a repository holds at ref, under folder.
func (l *Looker) Look(ctx context.Context, repository, ref, folder string) (Look, error) {
	source := Source{Kind: "git", URL: repository, Ref: ref, Path: folder}
	if err := (Brief{Source: source}).Validate(); err != nil {
		return Look{}, err
	}
	owner, repo := ownerAndRepo(repository)
	key := owner + "/" + repo + "@" + ref + ":" + folder
	l.mu.Lock()
	if kept, ok := l.seen[key]; ok && time.Since(kept.at) < remembered {
		l.mu.Unlock()
		return kept.look, nil
	}
	l.mu.Unlock()

	at := ref
	if at == "" {
		at = "HEAD"
	}
	root := strings.Trim(folder, "/")
	var said []string
	listed, err := l.index(ctx, owner, repo, at, root)
	if err != nil {
		said = append(said, err.Error())
	}
	folders, err := l.folders(ctx, owner, repo, at, root)
	if err != nil {
		said = append(said, err.Error())
	}
	look := Look{Controllers: merged(listed, folders)}
	if len(look.Controllers) == 0 {
		said = append(said, "it lists no controllers in an iocean.toml and has no controllers/<name>/controller.py; "+
			"a build will look for one controller in it")
	}
	look.Said = strings.Join(said, "; ")

	l.mu.Lock()
	l.seen[key] = seen{look: look, at: time.Now()}
	l.mu.Unlock()
	return look, nil
}

func ownerAndRepo(repository string) (string, string) {
	parts := strings.Split(strings.TrimSuffix(strings.TrimSuffix(strings.TrimPrefix(repository, "https://github.com/"), "/"), ".git"), "/")
	return parts[0], parts[1]
}

// index reads the controllers an iocean.toml lists.
func (l *Looker) index(ctx context.Context, owner, repo, at, root string) ([]Found, error) {
	file := path.Join(root, "iocean.toml")
	body, status, err := l.get(ctx, l.Raw+"/"+owner+"/"+repo+"/"+at+"/"+file)
	if err != nil {
		return nil, err
	}
	if status == http.StatusNotFound {
		return nil, nil
	}
	if status != http.StatusOK {
		return nil, fmt.Errorf("GitHub would not give %s: %d", file, status)
	}
	return controllersInToml(body), nil
}

// folders finds controllers/<slug>/controller.py, in one question about the
// repository's whole tree.
func (l *Looker) folders(ctx context.Context, owner, repo, at, root string) ([]Found, error) {
	body, status, err := l.get(ctx, l.API+"/repos/"+owner+"/"+repo+"/git/trees/"+url.PathEscape(at)+"?recursive=1")
	if err != nil {
		return nil, err
	}
	if status == http.StatusForbidden || status == http.StatusTooManyRequests {
		return nil, fmt.Errorf("GitHub is not answering questions from here for now, so only the index was read")
	}
	if status != http.StatusOK {
		return nil, fmt.Errorf("GitHub does not know %s/%s at %s (%d); is it public?", owner, repo, at, status)
	}
	var tree struct {
		Tree []struct {
			Path string `json:"path"`
			Type string `json:"type"`
		} `json:"tree"`
	}
	if err := json.Unmarshal(body, &tree); err != nil {
		return nil, fmt.Errorf("GitHub's answer could not be read: %w", err)
	}
	prefix := "controllers/"
	if root != "" {
		prefix = root + "/controllers/"
	}
	found := []Found{}
	for _, one := range tree.Tree {
		rest, ok := strings.CutPrefix(one.Path, prefix)
		if !ok || one.Type != "blob" {
			continue
		}
		slug, file, ok := strings.Cut(rest, "/")
		if ok && file == "controller.py" && domain.ValidateSlug(slug) == nil {
			found = append(found, Found{Slug: slug, Entry: strings.TrimPrefix(one.Path, root+"/")})
		}
	}
	return found, nil
}

func (l *Looker) get(ctx context.Context, to string) ([]byte, int, error) {
	request, err := http.NewRequestWithContext(ctx, http.MethodGet, to, nil)
	if err != nil {
		return nil, 0, err
	}
	response, err := l.http.Do(request)
	if err != nil {
		return nil, 0, fmt.Errorf("GitHub could not be reached: %w", err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(io.LimitReader(response.Body, 8<<20))
	return body, response.StatusCode, err
}

// merged is what the index lists, then any folder it does not, by slug.
func merged(listed, folders []Found) []Found {
	out := append([]Found{}, listed...)
	have := map[string]bool{}
	for _, one := range listed {
		have[one.Slug] = true
	}
	sort.Slice(folders, func(i, j int) bool { return folders[i].Slug < folders[j].Slug })
	for _, one := range folders {
		if !have[one.Slug] {
			out = append(out, one)
		}
	}
	return out
}

var tomlLine = regexp.MustCompile(`^\s*([A-Za-z_]+)\s*=\s*"([^"]*)"`)

// controllersInToml reads the [[controller]] entries of an iocean.toml: their
// slug, name and entry, which are all the choosing needs. It reads only that
// much of the format; the build reads the whole file.
func controllersInToml(raw []byte) []Found {
	found := []Found{}
	current := -1
	lines := bufio.NewScanner(strings.NewReader(string(raw)))
	for lines.Scan() {
		line := strings.TrimSpace(lines.Text())
		switch {
		case line == "[[controller]]":
			found = append(found, Found{})
			current = len(found) - 1
		case strings.HasPrefix(line, "["):
			current = -1
		case current >= 0:
			if said := tomlLine.FindStringSubmatch(line); said != nil {
				switch said[1] {
				case "slug":
					found[current].Slug = said[2]
				case "name":
					found[current].Name = said[2]
				case "entry":
					found[current].Entry = said[2]
				}
			}
		}
	}
	out := found[:0]
	for _, one := range found {
		if one.Slug == "" && one.Entry != "" {
			one.Slug = path.Base(path.Dir(strings.SplitN(one.Entry, ":", 2)[0]))
		}
		if domain.ValidateSlug(one.Slug) == nil {
			out = append(out, one)
		}
	}
	return out
}
