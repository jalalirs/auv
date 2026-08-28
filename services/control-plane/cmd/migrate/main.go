// Command migrate prepares the record for a build of the control plane.
//
// Applying a schema change is a deliberate operation, never something a serving
// process does on startup: a service that migrated as it booted would change
// the record every time it was restarted, including when it was restarted by
// accident.
//
// It also performs the one act that cannot be performed through the API — the
// first sign-in — because there is nobody yet to authorise it.
package main

import (
	"bytes"
	"context"
	"errors"
	"flag"
	"fmt"
	"log/slog"
	"os"
	"time"

	"github.com/jalalirs/auv/services/control-plane/internal/config"
	"github.com/jalalirs/auv/services/control-plane/internal/db"
	"github.com/jalalirs/auv/services/control-plane/internal/exec"
	"github.com/jalalirs/auv/services/control-plane/internal/identity"
	"github.com/jalalirs/auv/services/control-plane/internal/policy"
	"github.com/jalalirs/auv/services/control-plane/internal/storage"
)

func main() {
	logger := slog.New(slog.NewTextHandler(os.Stdout, &slog.HandlerOptions{Level: slog.LevelInfo}))
	if err := run(logger, os.Args[1:]); err != nil {
		logger.Error("migration stopped", "error", err)
		os.Exit(1)
	}
}

func usage() error {
	return errors.New("usage: migrate up | migrate bootstrap -email … -secret … -name … -organisation …")
}

func run(logger *slog.Logger, args []string) error {
	if len(args) == 0 {
		return usage()
	}

	settings, err := config.Load()
	if err != nil {
		return err
	}
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()

	pool, err := db.Open(ctx, settings.DatabaseURL, settings.DatabaseConnections)
	if err != nil {
		return err
	}
	defer pool.Close()

	switch args[0] {
	case "up":
		return up(ctx, logger, pool, settings)
	case "bootstrap":
		return bootstrap(ctx, logger, pool, settings, args[1:])
	default:
		return usage()
	}
}

// up applies every migration this build carries and creates any bucket that
// does not yet exist.
func up(ctx context.Context, logger *slog.Logger, pool *db.Pool, settings config.Config) error {
	applied, err := db.Migrate(ctx, pool)
	if err != nil {
		return err
	}
	if len(applied) == 0 {
		logger.Info("the schema is already current")
	}
	for _, name := range applied {
		logger.Info("applied", "migration", name)
	}

	blobs, err := openBlobs(settings)
	if err != nil {
		return err
	}
	created, err := blobs.EnsureBuckets(ctx)
	if err != nil {
		return err
	}
	for _, bucket := range created {
		logger.Info("created", "bucket", bucket)
	}
	if len(created) == 0 {
		logger.Info("every bucket already exists")
	}
	return nil
}

// bootstrap creates the first institution, the first person who can sign in,
// and the authority that person needs to create everyone else.
//
// It is safe to run more than once: an existing installation is reported and
// left alone, rather than being given a second administrator.
func bootstrap(ctx context.Context, logger *slog.Logger, pool *db.Pool, settings config.Config, args []string) error {
	flags := flag.NewFlagSet("bootstrap", flag.ContinueOnError)
	email := flags.String("email", "", "the first administrator's email address")
	secret := flags.String("secret", "", "the first administrator's sign-in secret")
	name := flags.String("name", "", "the first administrator's display name")
	orgSlug := flags.String("organisation", "", "the first institution's short name")
	orgName := flags.String("organisation-name", "", "the first institution's full name")
	targetName := flags.String("target", "local-docker", "the name of the first execution target")
	workerFile := flags.String("worker-credential-file", "",
		"write a worker's credential here, creating the worker if that file is empty")
	if err := flags.Parse(args); err != nil {
		return err
	}
	if *email == "" || *secret == "" || *name == "" || *orgSlug == "" {
		flags.Usage()
		return errors.New("bootstrap needs -email, -secret, -name, and -organisation")
	}
	if *orgName == "" {
		*orgName = *orgSlug
	}

	identities := identity.NewStore(pool, settings.SessionLifetime)
	authorizer := policy.NewAuthorizer(pool)
	broker := exec.NewBroker(pool)

	var existing int
	if err := pool.QueryRow(ctx, `
		SELECT count(*) FROM policy.binding
		WHERE scope_kind = 'platform' AND role = 'admin' AND revoked_at IS NULL`).
		Scan(&existing); err != nil {
		return fmt.Errorf("checking whether this installation is already established: %w", err)
	}
	if existing > 0 {
		logger.Info("this installation already has an administrator",
			"administrators", existing)
		return provisionWorker(ctx, logger, pool, identities, authorizer, *orgSlug, *workerFile)
	}

	err := pool.InTransaction(ctx, func(conn db.Conn) error {
		person, err := identities.CreatePerson(ctx, conn, identity.PersonSpec{
			DisplayName: *name, Email: *email, Secret: *secret,
		})
		if err != nil {
			return err
		}
		org, err := identities.CreateOrganisation(ctx, conn, *orgSlug, *orgName)
		if err != nil {
			return err
		}
		if err := identities.AddMember(ctx, conn, org.ID, person.ID); err != nil {
			return err
		}

		grants := []policy.GrantSpec{
			// The first administrator, without whom nothing else can be created.
			{SubjectKind: policy.SubjectPrincipal, SubjectID: person.ID,
				ScopeKind: policy.ScopePlatform, Role: policy.RoleAdmin, CreatedBy: person.ID},
			// Every member of an institution may do that institution's work.
			{SubjectKind: policy.SubjectOrg, SubjectID: org.ID,
				ScopeKind: policy.ScopeOrg, ScopeID: org.ID,
				Role: policy.RoleContributor, CreatedBy: person.ID},
		}
		for _, grant := range grants {
			if _, err := authorizer.Grant(ctx, conn, grant); err != nil {
				return err
			}
		}

		if _, err := broker.SetQuota(ctx, conn, exec.Quota{
			OrgID: org.ID, MaxConcurrentJobs: 4, MaxCPU: 8,
			MaxMemoryBytes: 16 << 30, MaxGPU: 0,
		}); err != nil {
			return err
		}
		if _, err := broker.RegisterTarget(ctx, conn, exec.TargetSpec{
			Name: *targetName, Kind: exec.LocalDocker,
			CapacityCPU: 8, CapacityMemoryBytes: 16 << 30, CapacityGPU: 0,
		}); err != nil {
			return err
		}

		logger.Info("established", "organisation", org.Slug, "administrator", person.Email,
			"principalId", person.ID, "organisationId", org.ID)
		return nil
	})
	if err != nil {
		return err
	}
	return provisionWorker(ctx, logger, pool, identities, authorizer, *orgSlug, *workerFile)
}

// provisionWorker makes sure a worker exists whose credential is in the named
// file.
//
// The credential cannot be recovered once issued, so a file that already holds
// one is left alone: re-running bootstrap must not orphan the worker that is
// already using it.
func provisionWorker(ctx context.Context, logger *slog.Logger, pool *db.Pool, identities *identity.Store, authorizer *policy.Authorizer, orgSlug, path string) error {
	if path == "" {
		return nil
	}
	if existing, err := os.ReadFile(path); err == nil && len(bytes.TrimSpace(existing)) > 0 {
		logger.Info("a worker credential is already in place", "file", path)
		return nil
	} else if err != nil && !errors.Is(err, os.ErrNotExist) {
		return fmt.Errorf("reading %s: %w", path, err)
	}

	org, err := identities.OrganisationBySlug(ctx, orgSlug)
	if err != nil {
		return fmt.Errorf("finding the institution %q the worker belongs to: %w", orgSlug, err)
	}

	return pool.InTransaction(ctx, func(conn db.Conn) error {
		worker, credential, err := identities.CreateServicePrincipal(ctx, conn, "worker", org.ID)
		if err != nil {
			return err
		}
		// A worker holds authority over the work queue and over nothing else:
		// it cannot read a city, contribute a layer, or act for an institution.
		if _, err := authorizer.Grant(ctx, conn, policy.GrantSpec{
			SubjectKind: policy.SubjectPrincipal, SubjectID: worker.ID,
			ScopeKind: policy.ScopeWork, Role: policy.RoleAdmin, CreatedBy: worker.ID,
		}); err != nil {
			return err
		}

		// The credential cannot be recovered once this process ends, so it is
		// written inside the transaction: a write that fails leaves no worker
		// behind whose credential nobody holds.
		if err := os.WriteFile(path, []byte(credential+"\n"), 0o600); err != nil {
			return fmt.Errorf("writing the worker credential to %s: %w", path, err)
		}
		logger.Info("provisioned a worker", "principalId", worker.ID, "file", path)
		return nil
	})
}

func openBlobs(settings config.Config) (*storage.Blobs, error) {
	return storage.OpenBlobs(storage.Settings{
		Endpoint:        settings.StorageEndpoint,
		PublicEndpoint:  settings.StoragePublicEndpoint,
		AccessKey:       settings.StorageAccessKey,
		SecretKey:       settings.StorageSecretKey,
		UseTLS:          settings.StorageUseTLS,
		PublicUseTLS:    settings.StoragePublicUseTLS,
		Region:          settings.StorageRegion,
		BucketPrefix:    settings.StorageBucketPrefix,
		PresignLifetime: settings.PresignLifetime,
	})
}
