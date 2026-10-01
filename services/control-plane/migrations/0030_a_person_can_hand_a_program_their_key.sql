-- A token a person makes for a program to act as them.
--
-- Somebody pointing their own assistant at this platform should not have to
-- hand it their sign-in secret, and should not need an administrator to issue
-- the assistant a principal of its own. So a person makes a token in the
-- application, names it after what will hold it, and can see when it was last
-- used and revoke it in one click.
--
-- Opaque rather than a signed token carrying claims, deliberately. A token that
-- leaks has to stop working the moment it is revoked, and a self-contained one
-- keeps working until it expires unless every check consults a list anyway —
-- at which point it is a lookup with extra steps. And claims about a person go
-- stale the moment their grants change; this resolves to the person on every
-- request, so what a token can do is always what that person can do now.
--
-- The token is never stored. Its digest is, as a session's is: a token is
-- thirty-two random bytes rather than something a person chose, so a fast hash
-- is enough and a slow one would only cost every request.
CREATE TABLE identity.api_token (
    id           text PRIMARY KEY,
    principal_id text NOT NULL REFERENCES identity.principal (id) ON DELETE CASCADE,

    -- What the person called it — "my Claude", "the lab laptop" — so that a
    -- list of tokens can be read by the person who made them.
    name         text NOT NULL,

    -- The first characters, to recognise one in a list or a log without the
    -- rest of it ever being shown again.
    prefix       text NOT NULL,
    token_hash   bytea NOT NULL UNIQUE,

    created_at   timestamptz NOT NULL DEFAULT now(),
    -- Optional. A token for an afternoon's experiment should be able to say so.
    expires_at   timestamptz,
    last_used_at timestamptz,
    revoked_at   timestamptz,

    CONSTRAINT a_token_has_a_name CHECK (length(trim(name)) > 0),
    CONSTRAINT a_token_expires_after_it_is_made CHECK (expires_at IS NULL OR expires_at > created_at)
);

CREATE INDEX api_token_of_a_person ON identity.api_token (principal_id) WHERE revoked_at IS NULL;
