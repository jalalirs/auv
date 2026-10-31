-- People sign in with Google, and institutions approve them by email.
--
-- Anyone with a Google account gets a person and a personal organisation of
-- their own on first sign-in: no form and no password. An institution, made
-- by the platform's administrator, lists the email addresses it approves, and
-- the administrator may give it whole domains. A person whose email matches
-- becomes a member of that institution, works inside it on its quota, and
-- stops being one when the approval is withdrawn.

-- Who a Google account is. The subject is Google's stable id for the account;
-- the email can change, and the hosted domain is the Workspace the account
-- belongs to, which is what makes a domain approval mean anything.
CREATE TABLE identity.login (
    provider        text NOT NULL,
    subject         text NOT NULL,
    principal_id    text NOT NULL REFERENCES identity.principal (id) ON DELETE CASCADE,
    email           text NOT NULL,
    hosted_domain   text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    last_used_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, subject),
    CONSTRAINT a_login_is_from_a_known_provider CHECK (provider IN ('google'))
);

CREATE INDEX login_by_principal ON identity.login (principal_id);

-- A personal organisation belongs to one person. Every other organisation is
-- an institution.
ALTER TABLE identity.organisation
    ADD COLUMN personal_of text UNIQUE REFERENCES identity.principal (id) ON DELETE SET NULL;

-- The addresses an institution approves. Its own administrator keeps the list.
CREATE TABLE identity.approved_email (
    org_id      text NOT NULL REFERENCES identity.organisation (id) ON DELETE CASCADE,
    email       text NOT NULL,
    added_by    text NOT NULL REFERENCES identity.principal (id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT an_approved_email_is_an_address CHECK (email ~ '^[^@\s]+@[^@\s]+$')
);

CREATE UNIQUE INDEX approved_email_once_per_institution
    ON identity.approved_email (org_id, lower(email));
CREATE INDEX approved_email_by_address ON identity.approved_email (lower(email));

-- Whole domains, given by the platform's administrator only, so nobody can
-- claim gmail.com. A domain belongs to one institution.
CREATE TABLE identity.approved_domain (
    domain      text PRIMARY KEY,
    org_id      text NOT NULL REFERENCES identity.organisation (id) ON DELETE CASCADE,
    added_by    text NOT NULL REFERENCES identity.principal (id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT an_approved_domain_is_a_lowercase_name
        CHECK (domain ~ '^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$')
);

CREATE INDEX approved_domain_by_institution ON identity.approved_domain (org_id);

-- A membership an approval made is withdrawn with the approval; one an
-- administrator made by hand is not.
ALTER TABLE identity.membership
    ADD COLUMN by_approval boolean NOT NULL DEFAULT false;

-- A desktop app signs in through the system browser and comes back through
-- iocean://. What comes back is a code, not a session: single use, a minute
-- long, and stored only as its digest.
CREATE TABLE identity.handoff (
    code_hash     bytea PRIMARY KEY,
    principal_id  text NOT NULL REFERENCES identity.principal (id) ON DELETE CASCADE,
    expires_at    timestamptz NOT NULL,
    used_at       timestamptz,
    created_at    timestamptz NOT NULL DEFAULT now()
);

-- Dives a calendar month, beside dives at once and GPU-hours a day. Empty is
-- no limit, which is what every organisation that existed before this has.
ALTER TABLE exec.quota
    ADD COLUMN max_dives_monthly integer,
    ADD CONSTRAINT monthly_dives_are_not_negative CHECK (max_dives_monthly IS NULL OR max_dives_monthly >= 0);

ALTER TYPE exec.refusal_reason ADD VALUE IF NOT EXISTS 'quota_monthly_dives_exhausted';
