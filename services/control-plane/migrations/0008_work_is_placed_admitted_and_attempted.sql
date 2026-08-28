-- Execution. A job is one finite containerised execution. A placement onto a
-- target is an attempt; retries create attempts, never new jobs, so provenance
-- stays singular. The control plane never runs scientific work itself.

CREATE SCHEMA exec;

CREATE TYPE exec.target_kind AS ENUM ('local_docker', 'kubernetes', 'slurm');

CREATE TABLE exec.target (
    id                    text PRIMARY KEY,
    name                  text NOT NULL UNIQUE,
    kind                  exec.target_kind NOT NULL,
    enabled               boolean NOT NULL DEFAULT true,
    capacity_cpu          numeric(10, 2) NOT NULL,
    capacity_memory_bytes bigint NOT NULL,
    capacity_gpu          integer NOT NULL DEFAULT 0,
    created_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT a_target_has_capacity CHECK (capacity_cpu > 0 AND capacity_memory_bytes > 0),
    CONSTRAINT capacity_is_not_negative CHECK (capacity_gpu >= 0)
);

CREATE TABLE exec.quota (
    org_id                text PRIMARY KEY REFERENCES identity.organisation (id) ON DELETE CASCADE,
    max_concurrent_jobs   integer NOT NULL,
    max_cpu               numeric(10, 2) NOT NULL,
    max_memory_bytes      bigint NOT NULL,
    max_gpu               integer NOT NULL DEFAULT 0,
    updated_at            timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT a_quota_is_not_negative CHECK (
        max_concurrent_jobs >= 0 AND max_cpu >= 0 AND max_memory_bytes >= 0 AND max_gpu >= 0
    )
);

CREATE TYPE exec.job_state AS ENUM (
    'pending', 'admitted', 'running',
    'succeeded', 'failed', 'cancelled', 'evicted', 'timed_out'
);

-- Why a job ended badly, in words a caller can act on.
CREATE TYPE exec.failure_class AS ENUM (
    'none', 'image_unavailable', 'input_unavailable', 'output_limit_exceeded',
    'nonzero_exit', 'walltime_exceeded', 'worker_lost', 'cancelled_by_caller',
    'internal_error'
);

CREATE TABLE exec.job (
    id                    text PRIMARY KEY,
    org_id                text NOT NULL REFERENCES identity.organisation (id),
    submitted_by          text NOT NULL REFERENCES identity.principal (id),
    recipe_id             text NOT NULL,
    image_digest          text NOT NULL,
    command               text[] NOT NULL,
    args                  text[] NOT NULL DEFAULT '{}',
    inputs                jsonb NOT NULL DEFAULT '[]'::jsonb,
    outputs               jsonb NOT NULL DEFAULT '[]'::jsonb,
    request_cpu           numeric(10, 2) NOT NULL,
    request_memory_bytes  bigint NOT NULL,
    request_gpu           integer NOT NULL DEFAULT 0,
    walltime_seconds      integer NOT NULL,
    target_id             text REFERENCES exec.target (id),
    state                 exec.job_state NOT NULL DEFAULT 'pending',
    failure_class         exec.failure_class NOT NULL DEFAULT 'none',
    next_sequence         bigint NOT NULL DEFAULT 1,
    created_at            timestamptz NOT NULL DEFAULT now(),
    terminal_at           timestamptz,
    CONSTRAINT an_image_is_pinned_by_digest CHECK (image_digest ~ '^[a-z0-9.-]+(:[0-9]+)?/?.*@sha256:[0-9a-f]{64}$'),
    CONSTRAINT a_job_runs_something CHECK (cardinality(command) > 0),
    CONSTRAINT a_request_is_positive CHECK (
        request_cpu > 0 AND request_memory_bytes > 0 AND request_gpu >= 0
    ),
    CONSTRAINT a_job_has_a_deadline CHECK (walltime_seconds > 0),
    CONSTRAINT a_terminal_job_records_when CHECK (
        (state IN ('succeeded', 'failed', 'cancelled', 'evicted', 'timed_out'))
        = (terminal_at IS NOT NULL)
    )
);

CREATE INDEX job_by_org ON exec.job (org_id, created_at DESC);
CREATE INDEX job_awaiting_placement ON exec.job (created_at) WHERE state = 'admitted';
CREATE INDEX job_in_flight ON exec.job (org_id) WHERE state IN ('pending', 'admitted', 'running');

-- A layer version produced by a job names that job. The reference is added
-- here because execution is defined after evidence.
ALTER TABLE layer.version
    ADD CONSTRAINT version_producer_job_exists
    FOREIGN KEY (producer_job_id) REFERENCES exec.job (id);

CREATE TYPE exec.attempt_state AS ENUM (
    'leased', 'running', 'succeeded', 'failed', 'cancelled', 'evicted', 'timed_out'
);

CREATE TABLE exec.attempt (
    id                text PRIMARY KEY,
    job_id            text NOT NULL REFERENCES exec.job (id),
    ordinal           integer NOT NULL,
    target_id         text NOT NULL REFERENCES exec.target (id),
    worker_id         text NOT NULL REFERENCES identity.principal (id),
    state             exec.attempt_state NOT NULL DEFAULT 'leased',
    lease_token_hash  bytea NOT NULL,
    lease_expires_at  timestamptz NOT NULL,
    placement_ref     text NOT NULL DEFAULT '',
    exit_code         integer,
    failure_class     exec.failure_class NOT NULL DEFAULT 'none',
    leased_at         timestamptz NOT NULL DEFAULT now(),
    started_at        timestamptz,
    finished_at       timestamptz,
    CONSTRAINT an_attempt_is_ordered CHECK (ordinal > 0),
    CONSTRAINT a_lease_token_is_thirty_two_bytes CHECK (octet_length(lease_token_hash) = 32),
    CONSTRAINT a_finished_attempt_records_when CHECK (
        (state IN ('succeeded', 'failed', 'cancelled', 'evicted', 'timed_out'))
        = (finished_at IS NOT NULL)
    )
);

CREATE UNIQUE INDEX one_ordinal_per_job ON exec.attempt (job_id, ordinal);
CREATE UNIQUE INDEX one_live_attempt_per_job
    ON exec.attempt (job_id) WHERE state IN ('leased', 'running');
CREATE INDEX attempt_by_lease_expiry
    ON exec.attempt (lease_expires_at) WHERE state IN ('leased', 'running');

-- The durable, ordered account of what happened to a job. This is what the
-- interface streams and what forensics reads.
CREATE TYPE exec.event_kind AS ENUM (
    'admitted', 'scheduled', 'started', 'progress', 'output_received',
    'succeeded', 'failed', 'cancelled', 'evicted', 'timed_out'
);

CREATE TABLE exec.event (
    id          text PRIMARY KEY,
    job_id      text NOT NULL REFERENCES exec.job (id),
    attempt_id  text REFERENCES exec.attempt (id),
    sequence    bigint NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT now(),
    kind        exec.event_kind NOT NULL,
    detail      jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT an_event_is_ordered CHECK (sequence > 0)
);

CREATE UNIQUE INDEX one_sequence_per_job ON exec.event (job_id, sequence);
CREATE INDEX event_by_job ON exec.event (job_id, sequence);

CREATE FUNCTION exec.protect_event() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'the job event stream is append-only: % is refused', TG_OP;
END;
$$;

CREATE TRIGGER a_job_event_stream_is_append_only
    BEFORE UPDATE OR DELETE ON exec.event
    FOR EACH ROW EXECUTE FUNCTION exec.protect_event();

-- What a job produced. Outputs are recorded once; a retried attempt does not
-- duplicate them.
CREATE TABLE exec.job_output (
    job_id      text NOT NULL REFERENCES exec.job (id),
    name        text NOT NULL,
    attempt_id  text NOT NULL REFERENCES exec.attempt (id),
    object_id   text NOT NULL REFERENCES store.object (id),
    recorded_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (job_id, name)
);
