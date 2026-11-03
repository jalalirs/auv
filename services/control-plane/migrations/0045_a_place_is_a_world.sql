-- A place is a world: one scene of layers (water, terrain, seabed, reef,
-- structures, life), each pointing at a library asset, saved as versions.
--
-- It is a third thing made of a place, beside the layout and the mission, and
-- built the same way: a name in a table, its versions documents in
-- catalog.version. What differs is that a place has one world and not many.
-- The arrangements were parallel variants of a place, and nobody could tell
-- which one a dive flew; a world has a history to go back to instead, and a
-- different design is a different world.
--
-- The package a dive runs in becomes a bake of a world version: the world's
-- document names the package version it was baked into.

BEGIN;

ALTER TYPE catalog.asset_kind ADD VALUE IF NOT EXISTS 'world';

COMMIT;

BEGIN;

CREATE TABLE catalog.world (
    id                text PRIMARY KEY,
    city_id           text NOT NULL REFERENCES catalog.city (id),

    slug              text NOT NULL,
    name              text NOT NULL,
    summary           text NOT NULL DEFAULT '',
    discoverable      boolean NOT NULL DEFAULT false,

    created_at        timestamptz NOT NULL DEFAULT now(),
    created_by        text NOT NULL REFERENCES identity.principal (id),
    retired_at        timestamptz,

    UNIQUE (city_id, slug),
    CONSTRAINT a_world_slug_is_a_handle CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$'),
    CONSTRAINT a_world_has_a_name CHECK (length(name) > 0)
);

-- One world per place while it is in use.
CREATE UNIQUE INDEX one_world_of_a_city ON catalog.world (city_id) WHERE retired_at IS NULL;

COMMIT;
