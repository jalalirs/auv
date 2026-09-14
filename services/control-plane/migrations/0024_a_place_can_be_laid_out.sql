-- A layout is an arrangement of a place: the array where it will really be
-- laid, the ship where it will hold, the nursery frames where they are.
--
-- It is not a new kind of versioning. Everything this platform pins is a
-- catalog.version, and a layout is pinned for exactly the reason a package is
-- — a mission flown over an array is only repeatable if the array is as fixed
-- as the reef under it. So a layout is an asset like any other and its
-- versions are version rows like any other.
--
-- What differs is what a version *holds*. A city's version is a manifest of
-- files in object storage, because a seabed is thirty megabytes of mesh. A
-- layout is a few kilobytes of JSON that somebody edits and saves repeatedly,
-- and sending that through an upload grant, a confirmation and an object would
-- be the file machinery used for something that is not a file. So a version
-- may carry a document instead, and one of the two is always present.

BEGIN;

ALTER TYPE catalog.asset_kind ADD VALUE IF NOT EXISTS 'layout';

COMMIT;

BEGIN;

-- The columns every catalogued thing has, in the order the reader expects
-- them: a layout is read by id, by slug and by what a subject may see, through
-- the same three queries as a city.
CREATE TABLE catalog.layout (
    id                text PRIMARY KEY,

    -- An arrangement of somewhere. A layout detached from the ground it was
    -- drawn on means nothing: the depths its things sit at were resolved
    -- against this city's seabed and are wrong against any other.
    city_id           text NOT NULL REFERENCES catalog.city (id),

    slug              text NOT NULL,
    name              text NOT NULL,
    summary           text NOT NULL DEFAULT '',
    discoverable      boolean NOT NULL DEFAULT false,

    created_at        timestamptz NOT NULL DEFAULT now(),
    created_by        text NOT NULL REFERENCES identity.principal (id),
    retired_at        timestamptz,

    -- Unique within its place rather than globally: two reefs may both have a
    -- layout called "the array", and they are different arrays.
    UNIQUE (city_id, slug),
    CONSTRAINT a_layout_slug_is_a_handle CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$'),
    CONSTRAINT a_layout_has_a_name CHECK (length(name) > 0)
);

CREATE INDEX layout_of_a_city ON catalog.layout (city_id) WHERE retired_at IS NULL;

-- A version may be a package of files or a document, and is one or the other.
ALTER TABLE catalog.version ALTER COLUMN manifest DROP NOT NULL;
ALTER TABLE catalog.version ADD COLUMN document jsonb;
ALTER TABLE catalog.version
    ADD CONSTRAINT a_version_is_files_or_a_document
    CHECK ((manifest IS NOT NULL) <> (document IS NOT NULL));

-- What a dive was flown in: the place, and the arrangement of it. Nullable,
-- because most dives are flown over bare ground and always will be.
ALTER TABLE dive.dive ADD COLUMN layout_version_id text REFERENCES catalog.version (id);

COMMIT;
