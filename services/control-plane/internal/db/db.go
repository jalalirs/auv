// Package db owns the connection to the system of record and the transaction
// discipline every other package uses.
//
// No package outside db constructs a pool or writes SQL against a raw
// connection: they receive a Conn, which a pool and a transaction both satisfy,
// so the same repository code runs inside or outside a transaction.
package db

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Conn is the subset of pgx a repository needs. A pool and a transaction both
// satisfy it, so repositories do not know whether they are in a transaction.
type Conn interface {
	Exec(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error)
	Query(ctx context.Context, sql string, args ...any) (pgx.Rows, error)
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
}

// Pool is a connection pool that can also run work in a transaction.
type Pool struct {
	pool *pgxpool.Pool
}

// Open connects to the system of record and verifies it answers.
func Open(ctx context.Context, url string, maxConnections int32) (*Pool, error) {
	config, err := pgxpool.ParseConfig(url)
	if err != nil {
		return nil, fmt.Errorf("reading the database url: %w", err)
	}
	config.MaxConns = maxConnections
	config.MaxConnLifetime = time.Hour
	config.MaxConnIdleTime = 5 * time.Minute
	config.HealthCheckPeriod = 30 * time.Second

	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		return nil, fmt.Errorf("opening the connection pool: %w", err)
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("reaching the database: %w", err)
	}
	return &Pool{pool: pool}, nil
}

// Exec runs a statement outside a transaction.
func (p *Pool) Exec(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error) {
	return p.pool.Exec(ctx, sql, args...)
}

// Query runs a query outside a transaction.
func (p *Pool) Query(ctx context.Context, sql string, args ...any) (pgx.Rows, error) {
	return p.pool.Query(ctx, sql, args...)
}

// QueryRow runs a single-row query outside a transaction.
func (p *Pool) QueryRow(ctx context.Context, sql string, args ...any) pgx.Row {
	return p.pool.QueryRow(ctx, sql, args...)
}

// InTransaction runs work atomically. The transaction commits when work
// returns nil and rolls back otherwise, including on panic, so a half-applied
// change cannot reach the record.
func (p *Pool) InTransaction(ctx context.Context, work func(Conn) error) error {
	tx, err := p.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("beginning a transaction: %w", err)
	}
	committed := false
	defer func() {
		if !committed {
			// The context may already be cancelled, so the rollback gets its
			// own deadline; otherwise a cancelled request leaks the connection.
			rollbackCtx, cancel := context.WithTimeout(context.WithoutCancel(ctx), 5*time.Second)
			defer cancel()
			_ = tx.Rollback(rollbackCtx)
		}
	}()

	if err := work(tx); err != nil {
		return err
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("committing: %w", err)
	}
	committed = true
	return nil
}

// Ping reports whether the database is reachable.
func (p *Pool) Ping(ctx context.Context) error { return p.pool.Ping(ctx) }

// Close releases every connection.
func (p *Pool) Close() { p.pool.Close() }

// ErrNotFound reports that a requested row does not exist. Callers translate
// it into whatever their access decision permits them to reveal.
var ErrNotFound = errors.New("not found")

// Translate converts a driver error into a domain-meaningful one, so callers
// match on intent rather than on driver internals.
func Translate(err error) error {
	if err == nil {
		return nil
	}
	if errors.Is(err, pgx.ErrNoRows) {
		return ErrNotFound
	}
	return err
}

// IsUniqueViolation reports whether an error is the database refusing a
// duplicate, which callers usually present as a conflict rather than a fault.
func IsUniqueViolation(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && pgErr.Code == "23505"
}

// IsCheckViolation reports whether an error is the database refusing a value
// that breaks a stated rule.
func IsCheckViolation(err error) bool {
	var pgErr *pgconn.PgError
	return errors.As(err, &pgErr) && (pgErr.Code == "23514" || pgErr.Code == "23502")
}

// RaisedMessage returns the message from a rule the database enforced with a
// trigger, so that an immutability refusal reaches the caller in the words the
// schema used. The second result reports whether the error was such a refusal.
func RaisedMessage(err error) (string, bool) {
	var pgErr *pgconn.PgError
	if errors.As(err, &pgErr) && pgErr.Code == "P0001" {
		return pgErr.Message, true
	}
	return "", false
}
