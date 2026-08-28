-- Object storage records. The database holds meaning; the object store holds
-- bytes. An object is identified by the digest of its content, so identity
-- survives migration between stores.

CREATE SCHEMA store;

-- Buckets differ by rule, not by convenience. Evidence is written once and
-- never rewritten; derived output is immutable per version; ephemeral holds
-- scratch that may expire.
CREATE TYPE store.bucket AS ENUM ('evidence', 'derived', 'ephemeral');

CREATE TABLE store.object (
    id          text PRIMARY KEY,
    bucket      store.bucket NOT NULL,
    sha256      bytea NOT NULL,
    size_bytes  bigint NOT NULL,
    media_type  text NOT NULL,
    uploaded_by text NOT NULL REFERENCES identity.principal (id),
    uploaded_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT a_digest_is_thirty_two_bytes CHECK (octet_length(sha256) = 32),
    CONSTRAINT an_object_has_content CHECK (size_bytes > 0),
    CONSTRAINT a_media_type_is_stated CHECK (media_type <> '')
);

-- The same bytes in the same bucket are one object, however many times they
-- are uploaded. Deduplication is a property of content addressing.
CREATE UNIQUE INDEX one_object_per_digest_and_bucket ON store.object (bucket, sha256);

-- An upload grant is a short-lived permission to place specific bytes at a
-- specific key. It is issued only after an access decision and it records what
-- the caller claimed, so the claim can be checked against what arrived.
CREATE TABLE store.upload_grant (
    id                text PRIMARY KEY,
    bucket            store.bucket NOT NULL,
    declared_sha256   bytea NOT NULL,
    declared_size     bigint NOT NULL,
    declared_media    text NOT NULL,
    issued_to         text NOT NULL REFERENCES identity.principal (id),
    issued_at         timestamptz NOT NULL DEFAULT now(),
    expires_at        timestamptz NOT NULL,
    confirmed_at      timestamptz,
    object_id         text REFERENCES store.object (id),
    CONSTRAINT a_declared_digest_is_thirty_two_bytes CHECK (octet_length(declared_sha256) = 32),
    CONSTRAINT a_declared_object_has_content CHECK (declared_size > 0),
    CONSTRAINT a_grant_expires_after_it_is_issued CHECK (expires_at > issued_at),
    CONSTRAINT a_confirmed_grant_names_its_object
        CHECK ((confirmed_at IS NULL) = (object_id IS NULL))
);

CREATE INDEX upload_grant_by_principal ON store.upload_grant (issued_to, issued_at DESC);

CREATE FUNCTION store.reject_rewrite() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'stored bytes are evidence: % on store.object is refused', TG_OP;
END;
$$;

CREATE TRIGGER stored_bytes_are_never_rewritten
    BEFORE UPDATE OR DELETE ON store.object
    FOR EACH ROW EXECUTE FUNCTION store.reject_rewrite();
