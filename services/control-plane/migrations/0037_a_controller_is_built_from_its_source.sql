-- A controller built from its source, on the platform's machines.
--
-- Somebody names a GitHub repository (a branch, a tag or a commit, a folder)
-- or uploads a zip; the platform runs the controller build as a job, which
-- finds the controller, builds its image without the host's Docker, and runs
-- it against the SDK's topic contract in a tank. A build that passes is pushed
-- to the platform's registry and registered as a new build of that
-- controller. The build is the record of that request: what was asked, the
-- job that ran it, what it reported, and the stack it registered.

CREATE TABLE catalog.controller_build (
    id          text PRIMARY KEY,
    org_id      text NOT NULL REFERENCES identity.organisation (id) ON DELETE CASCADE,
    job_id      text NOT NULL REFERENCES exec.job (id),
    brief       jsonb NOT NULL,
    slug        text NOT NULL,
    -- What the build said about itself (report.json): the controller it
    -- found, its topics, its tank check, the commit it was built from.
    report      jsonb,
    stack_id    text REFERENCES dive.autonomy_stack (id),
    failure     text,
    created_by  text NOT NULL REFERENCES identity.principal (id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    recorded_at timestamptz
);

CREATE INDEX controller_build_by_org ON catalog.controller_build (org_id, created_at DESC);
CREATE UNIQUE INDEX one_controller_build_per_job ON catalog.controller_build (job_id);

-- Where a build of a controller came from: a repository and the commit, or
-- the upload. Empty for one deployed from a terminal, which says nothing.
ALTER TABLE dive.autonomy_stack ADD COLUMN source jsonb;
