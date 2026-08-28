-- Governance. One decision point covers every object, including compute. A
-- role binding attaches a role to a subject at a scope. Nothing else in the
-- system is permitted to decide access.

CREATE SCHEMA policy;

-- Roles are ordered by strength. A stronger role implies every weaker one.
CREATE TYPE policy.role AS ENUM ('viewer', 'contributor', 'steward', 'admin');

-- What a binding attaches to. 'platform' is the whole installation; 'org' is
-- one organisation's own work; 'city' is one place; 'work' is the execution
-- queue. Work is its own scope so that a worker can be given authority over
-- work without being given authority over anything else.
CREATE TYPE policy.scope_kind AS ENUM ('platform', 'org', 'city', 'work');

-- Who a binding attaches to. Binding an organisation grants the role to every
-- member, which is how a city is shared with an institution.
CREATE TYPE policy.subject_kind AS ENUM ('principal', 'org');

CREATE TABLE policy.binding (
    id           text PRIMARY KEY,
    subject_kind policy.subject_kind NOT NULL,
    subject_id   text NOT NULL,
    scope_kind   policy.scope_kind NOT NULL,
    scope_id     text,
    role         policy.role NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    created_by   text NOT NULL REFERENCES identity.principal (id),
    revoked_at   timestamptz,
    -- The platform and the work queue are each one thing, so a binding on
    -- either names no identifier. An organisation or a city binding names one.
    CONSTRAINT a_scope_that_is_one_thing_has_no_identifier
        CHECK ((scope_kind IN ('platform', 'work')) = (scope_id IS NULL))
);

CREATE UNIQUE INDEX one_live_binding_per_subject_scope_and_role
    ON policy.binding (subject_kind, subject_id, scope_kind, coalesce(scope_id, ''), role)
    WHERE revoked_at IS NULL;

CREATE INDEX binding_by_subject ON policy.binding (subject_kind, subject_id)
    WHERE revoked_at IS NULL;
CREATE INDEX binding_by_scope ON policy.binding (scope_kind, scope_id)
    WHERE revoked_at IS NULL;

-- Why access was denied is data, not a log line. 'hidden' denials are reported
-- to the caller as absence; 'visible' denials tell the caller the object exists
-- and access may be requested.
CREATE TYPE policy.denial_effect AS ENUM ('hidden', 'visible');

CREATE TABLE policy.denial (
    id            text PRIMARY KEY,
    occurred_at   timestamptz NOT NULL DEFAULT now(),
    principal_id  text REFERENCES identity.principal (id),
    action        text NOT NULL,
    resource_kind text NOT NULL,
    resource_id   text,
    effect        policy.denial_effect NOT NULL,
    reason        text NOT NULL,
    request_id    text NOT NULL
);

CREATE INDEX denial_by_principal ON policy.denial (principal_id, occurred_at DESC);
CREATE INDEX denial_by_resource ON policy.denial (resource_kind, resource_id, occurred_at DESC);
