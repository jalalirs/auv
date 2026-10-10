-- What an organisation has put in storage, and how much it may.
--
-- Bytes are still addressed by their content and stored once, however many
-- organisations upload them. What is new is who holds them: an organisation
-- holds an object it uploaded, its usage is the size of what it holds, and
-- it can let go of an object it no longer wants. An object nobody holds and
-- nothing refers to (no place version, no job's output, no run's recording)
-- is collected: its record and its bytes go. Evidence that something still
-- refers to is never collected, because the references below are foreign keys
-- and the delete fails.

-- Which organisation a grant was issued for, so the object it confirms is
-- held by that organisation. Grants issued to the platform's own work (a run's
-- recording, a job's output) name none.
ALTER TABLE store.upload_grant
    ADD COLUMN org_id text REFERENCES identity.organisation (id) ON DELETE CASCADE,
    -- A grant for bytes that arrive in parts: the store's multipart upload,
    -- and how large each part is. Parts can be sent again, so an upload that
    -- drops halfway resumes rather than starts over.
    ADD COLUMN multipart_id text,
    ADD COLUMN part_bytes bigint,
    ADD CONSTRAINT a_part_has_content CHECK (part_bytes IS NULL OR part_bytes > 0);

CREATE INDEX upload_grant_open_by_org ON store.upload_grant (org_id)
    WHERE confirmed_at IS NULL;

-- A grant is the permission an object arrived under, not a reference that
-- keeps it: when an object is collected its spent grants go with it (the
-- audit log keeps the upload).
ALTER TABLE store.upload_grant
    DROP CONSTRAINT upload_grant_object_id_fkey,
    ADD CONSTRAINT upload_grant_object_id_fkey
        FOREIGN KEY (object_id) REFERENCES store.object (id) ON DELETE CASCADE;

CREATE TABLE store.holding (
    org_id     text NOT NULL REFERENCES identity.organisation (id) ON DELETE CASCADE,
    object_id  text NOT NULL REFERENCES store.object (id) ON DELETE CASCADE,
    held_by    text NOT NULL REFERENCES identity.principal (id),
    held_since timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, object_id)
);

CREATE INDEX holding_by_object ON store.holding (object_id);

-- How much an organisation may hold. An organisation with no row has the
-- platform's default, which the control plane is configured with.
CREATE TABLE store.quota (
    org_id    text PRIMARY KEY REFERENCES identity.organisation (id) ON DELETE CASCADE,
    max_bytes bigint NOT NULL,
    set_by    text NOT NULL REFERENCES identity.principal (id),
    set_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT a_limit_is_not_negative CHECK (max_bytes >= 0)
);

-- What was stored before this: held by the organisations its uploader
-- belongs to, which is the nearest record there is of whose it was.
INSERT INTO store.holding (org_id, object_id, held_by, held_since)
SELECT m.org_id, o.id, o.uploaded_by, o.uploaded_at
FROM store.object o
JOIN identity.membership m ON m.principal_id = o.uploaded_by
ON CONFLICT DO NOTHING;

-- Stored bytes are still never rewritten. They may now be removed, but only
-- by the collector, which says so for its own transaction; anything else that
-- tries is refused as before.
CREATE OR REPLACE FUNCTION store.reject_rewrite() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' AND current_setting('store.collecting', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'stored bytes are evidence: % on store.object is refused', TG_OP;
END;
$$;
