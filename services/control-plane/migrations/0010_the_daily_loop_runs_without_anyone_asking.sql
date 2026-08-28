-- Scheduled work. The platform keeps itself current: global observations and
-- forecasts arrive as new canonical layer versions on a schedule that nobody
-- triggers.

CREATE TABLE exec.schedule (
    id                   text PRIMARY KEY,
    name                 text NOT NULL UNIQUE,
    org_id               text NOT NULL REFERENCES identity.organisation (id),
    submitted_by         text NOT NULL REFERENCES identity.principal (id),
    recipe_id            text NOT NULL,
    image_digest         text NOT NULL,
    command              text[] NOT NULL,
    args                 text[] NOT NULL DEFAULT '{}',
    inputs               jsonb NOT NULL DEFAULT '[]'::jsonb,
    outputs              jsonb NOT NULL DEFAULT '[]'::jsonb,
    request_cpu          numeric(10, 2) NOT NULL,
    request_memory_bytes bigint NOT NULL,
    request_gpu          integer NOT NULL DEFAULT 0,
    walltime_seconds     integer NOT NULL,
    interval_seconds     integer NOT NULL,
    enabled              boolean NOT NULL DEFAULT true,
    next_run_at          timestamptz NOT NULL,
    last_job_id          text REFERENCES exec.job (id),
    created_at           timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT a_schedule_recurs CHECK (interval_seconds >= 60),
    CONSTRAINT a_scheduled_image_is_pinned_by_digest
        CHECK (image_digest ~ '^[a-z0-9.-]+(:[0-9]+)?/?.*@sha256:[0-9a-f]{64}$'),
    CONSTRAINT a_schedule_runs_something CHECK (cardinality(command) > 0),
    CONSTRAINT a_scheduled_request_is_positive CHECK (
        request_cpu > 0 AND request_memory_bytes > 0 AND request_gpu >= 0
    ),
    CONSTRAINT a_scheduled_job_has_a_deadline CHECK (walltime_seconds > 0)
);

CREATE INDEX schedule_due ON exec.schedule (next_run_at) WHERE enabled;
