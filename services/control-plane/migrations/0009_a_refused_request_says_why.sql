-- Admission and refusal. A job that is allowed to run records why it was
-- allowed; a job that is not records why it was not. Neither is a log line.

CREATE TABLE exec.admission (
    id             text PRIMARY KEY,
    job_id         text NOT NULL UNIQUE REFERENCES exec.job (id),
    decided_at     timestamptz NOT NULL DEFAULT now(),
    target_id      text NOT NULL REFERENCES exec.target (id),
    quota_snapshot jsonb NOT NULL,
    request_id     text NOT NULL
);

CREATE TYPE exec.refusal_reason AS ENUM (
    'quota_concurrent_jobs_exhausted',
    'quota_cpu_exhausted',
    'quota_memory_exhausted',
    'quota_gpu_exhausted',
    'no_target_has_capacity',
    'no_target_enabled',
    'organisation_has_no_quota'
);

CREATE TABLE exec.refusal (
    id           text PRIMARY KEY,
    occurred_at  timestamptz NOT NULL DEFAULT now(),
    org_id       text NOT NULL REFERENCES identity.organisation (id),
    principal_id text NOT NULL REFERENCES identity.principal (id),
    reason       exec.refusal_reason NOT NULL,
    detail       jsonb NOT NULL DEFAULT '{}'::jsonb,
    request_id   text NOT NULL
);

CREATE INDEX refusal_by_org ON exec.refusal (org_id, occurred_at DESC);

CREATE FUNCTION exec.protect_decision() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'an admission or refusal is a record of a decision: % is refused', TG_OP;
END;
$$;

CREATE TRIGGER an_admission_is_never_rewritten
    BEFORE UPDATE OR DELETE ON exec.admission
    FOR EACH ROW EXECUTE FUNCTION exec.protect_decision();

CREATE TRIGGER a_refusal_is_never_rewritten
    BEFORE UPDATE OR DELETE ON exec.refusal
    FOR EACH ROW EXECUTE FUNCTION exec.protect_decision();
