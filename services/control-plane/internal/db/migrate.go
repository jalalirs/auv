package db

import (
	"context"
	"fmt"

	"github.com/jalalirs/auv/services/control-plane/migrations"
)

const migrationLedger = `
CREATE TABLE IF NOT EXISTS schema_migration (
    name        text PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now()
)`

// Migrate applies every migration that has not been applied, in order, each in
// its own transaction. Applying is explicit: no service does this on startup,
// so a schema change is always a deliberate operation.
//
// It reports the names it applied.
func Migrate(ctx context.Context, pool *Pool) ([]string, error) {
	if _, err := pool.Exec(ctx, migrationLedger); err != nil {
		return nil, fmt.Errorf("preparing the migration ledger: %w", err)
	}

	available, err := migrations.All()
	if err != nil {
		return nil, err
	}

	applied, err := appliedMigrations(ctx, pool)
	if err != nil {
		return nil, err
	}

	var ran []string
	for _, migration := range available {
		if _, done := applied[migration.Name]; done {
			continue
		}
		err := pool.InTransaction(ctx, func(conn Conn) error {
			if _, err := conn.Exec(ctx, migration.SQL); err != nil {
				return fmt.Errorf("applying %s: %w", migration.Name, err)
			}
			_, err := conn.Exec(ctx,
				`INSERT INTO schema_migration (name) VALUES ($1)`, migration.Name)
			return err
		})
		if err != nil {
			return ran, err
		}
		ran = append(ran, migration.Name)
	}
	return ran, nil
}

// PendingMigrations reports migrations this build carries that the database
// has not applied. Readiness depends on this being empty.
func PendingMigrations(ctx context.Context, pool *Pool) ([]string, error) {
	available, err := migrations.All()
	if err != nil {
		return nil, err
	}
	applied, err := appliedMigrations(ctx, pool)
	if err != nil {
		return nil, err
	}
	var pending []string
	for _, migration := range available {
		if _, done := applied[migration.Name]; !done {
			pending = append(pending, migration.Name)
		}
	}
	return pending, nil
}

func appliedMigrations(ctx context.Context, pool *Pool) (map[string]struct{}, error) {
	rows, err := pool.Query(ctx, `SELECT name FROM schema_migration`)
	if err != nil {
		return nil, fmt.Errorf("reading the migration ledger: %w", err)
	}
	defer rows.Close()

	applied := make(map[string]struct{})
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			return nil, err
		}
		applied[name] = struct{}{}
	}
	return applied, rows.Err()
}
