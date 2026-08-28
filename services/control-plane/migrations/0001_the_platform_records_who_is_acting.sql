-- Identity. Three kinds of actor exist: people, organisations, and service
-- principals such as workers and edge stations. Nothing acts without a
-- principal, so every action is attributable.

CREATE SCHEMA identity;

CREATE TABLE identity.organisation (
    id          text PRIMARY KEY,
    slug        text NOT NULL UNIQUE,
    name        text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT organisation_slug_is_a_label CHECK (slug ~ '^[a-z][a-z0-9-]{0,61}[a-z0-9]$')
);

-- A principal is anything that can act. A person principal carries credentials
-- a human uses; a service principal carries credentials a program uses.
CREATE TYPE identity.principal_kind AS ENUM ('person', 'service');

CREATE TABLE identity.principal (
    id           text PRIMARY KEY,
    kind         identity.principal_kind NOT NULL,
    display_name text NOT NULL,
    email        text,
    org_id       text REFERENCES identity.organisation (id),
    disabled_at  timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT a_person_has_an_email CHECK (kind <> 'person' OR email IS NOT NULL),
    CONSTRAINT a_service_principal_belongs_to_something
        CHECK (kind <> 'service' OR org_id IS NOT NULL OR display_name <> '')
);

CREATE UNIQUE INDEX principal_email_is_unique
    ON identity.principal (lower(email)) WHERE email IS NOT NULL;

-- Credentials are stored only as verifier material. The secret itself is never
-- written down.
CREATE TABLE identity.credential (
    id           text PRIMARY KEY,
    principal_id text NOT NULL REFERENCES identity.principal (id) ON DELETE CASCADE,
    verifier     text NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    revoked_at   timestamptz
);

CREATE INDEX credential_by_principal ON identity.credential (principal_id);

-- A session is a short-lived, revocable bearer of a principal's identity. The
-- token is stored hashed so a database disclosure does not grant access.
CREATE TABLE identity.session (
    id           text PRIMARY KEY,
    principal_id text NOT NULL REFERENCES identity.principal (id) ON DELETE CASCADE,
    token_hash   bytea NOT NULL UNIQUE,
    issued_at    timestamptz NOT NULL DEFAULT now(),
    expires_at   timestamptz NOT NULL,
    revoked_at   timestamptz,
    CONSTRAINT a_session_expires_after_it_is_issued CHECK (expires_at > issued_at)
);

CREATE INDEX session_by_principal ON identity.session (principal_id);
CREATE INDEX session_by_expiry ON identity.session (expires_at) WHERE revoked_at IS NULL;

-- Membership binds a person to an organisation. It carries no permissions of
-- its own; permission is decided in one place (migration 0002).
CREATE TABLE identity.membership (
    org_id       text NOT NULL REFERENCES identity.organisation (id) ON DELETE CASCADE,
    principal_id text NOT NULL REFERENCES identity.principal (id) ON DELETE CASCADE,
    created_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, principal_id)
);

CREATE INDEX membership_by_principal ON identity.membership (principal_id);
