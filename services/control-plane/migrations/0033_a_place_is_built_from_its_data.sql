-- A place built from its data, on the platform's machines.
--
-- Somebody names a square on Earth and the data to build it from (public
-- sources, their own surveys); the platform runs the build as a job and the
-- package it makes becomes a draft version of the place, which its members
-- then publish. The build is the record of that request: what was asked, the
-- job that ran it, the version it made, and what it found about where the
-- place is weak.

CREATE TABLE catalog.build (
    id          text PRIMARY KEY,
    city_id     text NOT NULL REFERENCES catalog.city (id),
    org_id      text NOT NULL REFERENCES identity.organisation (id) ON DELETE CASCADE,
    job_id      text NOT NULL REFERENCES exec.job (id),
    brief       jsonb NOT NULL,
    version_id  text REFERENCES catalog.version (id),
    -- What the build said about the place it made: the depth's sources and
    -- errors, where it is weak. Read once from the package, kept here.
    result      jsonb,
    failure     text,
    created_by  text NOT NULL REFERENCES identity.principal (id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    recorded_at timestamptz
);

CREATE INDEX build_by_city ON catalog.build (city_id, created_at DESC);
CREATE UNIQUE INDEX one_build_per_job ON catalog.build (job_id);
