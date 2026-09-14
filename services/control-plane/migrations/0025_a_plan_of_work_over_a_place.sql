-- A mission is a plan of work: this place, arranged this way, these stages in
-- this order. It is the thing a reef programme actually owns — "the September
-- transects at Al Fahal" — and until now it could only exist inside one dive's
-- objective, where it died with that dive.
--
-- The point of keeping it is comparison. Two people flying the same mission a
-- month apart produce two runs that can be read against each other, because
-- both pin the same three things: the place, the arrangement of it, and what
-- was asked. A mission that did not pin its layout would be a plan whose
-- transponders moved between flights, and the difference between the runs
-- would be the array rather than the work.
--
-- Structurally it is a layout with a different document in it, and it is built
-- that way on purpose: same table shape, same versioning, same pinning. What
-- differs is what the document says.

BEGIN;

ALTER TYPE catalog.asset_kind ADD VALUE IF NOT EXISTS 'mission';

COMMIT;

BEGIN;

CREATE TABLE catalog.mission (
    id                text PRIMARY KEY,

    -- A plan of work somewhere. Like a layout, a mission detached from its
    -- place means nothing: its stages point at things that were drawn on that
    -- seabed.
    city_id           text NOT NULL REFERENCES catalog.city (id),

    slug              text NOT NULL,
    name              text NOT NULL,
    summary           text NOT NULL DEFAULT '',
    discoverable      boolean NOT NULL DEFAULT false,

    created_at        timestamptz NOT NULL DEFAULT now(),
    created_by        text NOT NULL REFERENCES identity.principal (id),
    retired_at        timestamptz,

    UNIQUE (city_id, slug),
    CONSTRAINT a_mission_slug_is_a_handle CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$'),
    CONSTRAINT a_mission_has_a_name CHECK (length(name) > 0)
);

CREATE INDEX mission_of_a_city ON catalog.mission (city_id) WHERE retired_at IS NULL;

-- What a dive was composed from, when it was composed from anything. Nullable,
-- because a dive asked for directly is still a dive.
ALTER TABLE dive.dive ADD COLUMN mission_version_id text REFERENCES catalog.version (id);

COMMIT;
