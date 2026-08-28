// Package migrations carries the numbered, named changes to the schema.
//
// The files live beside this source and are compiled into every binary, so the
// schema a build applies is the schema that build was tested against. Their
// names are sentences, because the schema is the platform's ledger of
// decisions and a reader should be able to follow it.
package migrations

import (
	"embed"
	"fmt"
	"io/fs"
	"sort"
	"strings"
)

//go:embed all:*.sql
var files embed.FS

// Migration is one numbered, named change to the schema.
type Migration struct {
	Name string
	SQL  string
}

// All returns every migration in application order.
func All() ([]Migration, error) {
	entries, err := fs.ReadDir(files, ".")
	if err != nil {
		return nil, fmt.Errorf("reading embedded migrations: %w", err)
	}

	names := make([]string, 0, len(entries))
	for _, entry := range entries {
		if entry.IsDir() || !strings.HasSuffix(entry.Name(), ".sql") {
			continue
		}
		names = append(names, entry.Name())
	}
	sort.Strings(names)

	loaded := make([]Migration, 0, len(names))
	for _, name := range names {
		body, err := fs.ReadFile(files, name)
		if err != nil {
			return nil, fmt.Errorf("reading migration %s: %w", name, err)
		}
		loaded = append(loaded, Migration{Name: name, SQL: string(body)})
	}
	if len(loaded) == 0 {
		return nil, fmt.Errorf("no migrations are embedded in this build")
	}
	return loaded, nil
}
