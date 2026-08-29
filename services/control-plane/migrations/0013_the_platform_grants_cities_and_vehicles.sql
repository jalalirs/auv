-- Cities and vehicles are the platform's assets, and access to them is granted.
--
-- The record until now described a catalogue of measurements: layers, versions,
-- lineage, provenance. That is a real thing to want, and it is not this
-- platform. What a person does here is dive — they take a vehicle we publish
-- into a city we publish, under conditions they choose, driven by autonomy they
-- bring. Everything below exists to make that sentence a row.
--
-- Both are packages rather than records. A city is terrain and scenes; a
-- vehicle is geometry, mass properties, hydrodynamic coefficients, thrusters
-- and a sensor suite. Both are large, both are versioned, and both are pinned
-- by content digest when a dive uses them — because a dive that cannot be
-- reproduced is an anecdote, and reproducibility is the whole reason to own a
-- simulator rather than borrow one.

CREATE SCHEMA catalog;

-- ── Cities ───────────────────────────────────────────────────────────────────
--
-- A city is a place a dive happens in: a reef, a wreck, a test tank, a harbour.
-- It exists at the platform, not inside an organisation, and outlives the
-- institutions granted access to it. Ownership is a governance question
-- answered in policy, never a column here.

CREATE TABLE catalog.city (
    id                text PRIMARY KEY,
    slug              text NOT NULL UNIQUE,
    name              text NOT NULL,
    summary           text NOT NULL DEFAULT '',

    -- Where on Earth, so a city can be found on a globe and so environmental
    -- forcing can be fetched for it. Geometry rather than geography: a global
    -- extent has an edge at the antimeridian that geography cannot represent.
    extent            geometry(Polygon, 4326),

    -- The frame the scene's coordinates are in, and what z=0 means. A dive that
    -- does not know its vertical datum cannot report a depth.
    horizontal_crs    text NOT NULL DEFAULT 'EPSG:4326',
    vertical_datum    text NOT NULL DEFAULT 'unknown',

    -- Discoverable cities are listed to anyone signed in; the rest are visible
    -- only to those granted access, and the platform does not distinguish
    -- "does not exist" from "not yours to know about".
    discoverable      boolean NOT NULL DEFAULT false,

    created_at        timestamptz NOT NULL DEFAULT now(),
    created_by        text NOT NULL REFERENCES identity.principal (id),
    retired_at        timestamptz,

    CONSTRAINT a_city_slug_is_a_handle CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$'),
    CONSTRAINT a_city_has_a_name CHECK (length(name) > 0)
);

CREATE INDEX city_by_extent ON catalog.city USING gist (extent);
CREATE INDEX city_that_is_discoverable ON catalog.city (slug) WHERE retired_at IS NULL AND discoverable;

-- ── Vehicles ─────────────────────────────────────────────────────────────────
--
-- A vehicle is what a dive is flown in, and it is ours: users bring autonomy,
-- not hulls. Publishing one is how "we support the BlueROV 2" becomes something
-- that can be granted.

CREATE TABLE catalog.vehicle (
    id                text PRIMARY KEY,
    slug              text NOT NULL UNIQUE,
    name              text NOT NULL,
    summary           text NOT NULL DEFAULT '',
    manufacturer      text NOT NULL DEFAULT '',
    discoverable      boolean NOT NULL DEFAULT false,
    created_at        timestamptz NOT NULL DEFAULT now(),
    created_by        text NOT NULL REFERENCES identity.principal (id),
    retired_at        timestamptz,

    CONSTRAINT a_vehicle_slug_is_a_handle CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$'),
    CONSTRAINT a_vehicle_has_a_name CHECK (length(name) > 0)
);

CREATE INDEX vehicle_that_is_discoverable ON catalog.vehicle (slug) WHERE retired_at IS NULL AND discoverable;

-- ── Versions ─────────────────────────────────────────────────────────────────
--
-- A city and a vehicle version are the same shape, so they are one table
-- discriminated by kind rather than two tables kept in step by hand.
--
-- The manifest lists the files in the package and their digests; the package
-- digest is over the manifest, so pinning one digest pins every byte. This is
-- what makes a dive replayable and what makes a node's cache safe to treat as
-- append-only: a digest never changes meaning, so nothing is ever stale.

CREATE TYPE catalog.asset_kind AS ENUM ('city', 'vehicle');

CREATE TABLE catalog.version (
    id                text PRIMARY KEY,
    asset_kind        catalog.asset_kind NOT NULL,
    asset_id          text NOT NULL,

    -- Ordinal rather than semantic: a version is the nth publication of this
    -- asset, and nothing about the number promises compatibility.
    ordinal           integer NOT NULL,
    label             text NOT NULL DEFAULT '',
    notes             text NOT NULL DEFAULT '',

    -- Over the manifest, which is over the bytes.
    digest            bytea NOT NULL,
    manifest          jsonb NOT NULL,
    total_bytes       bigint NOT NULL,

    -- What this version needs of the runtime that will load it. A vehicle
    -- authored against a newer sensor API must not be silently flown by an
    -- older simulator.
    runtime_min       text NOT NULL DEFAULT '',

    published_at      timestamptz,
    created_at        timestamptz NOT NULL DEFAULT now(),
    created_by        text NOT NULL REFERENCES identity.principal (id),

    CONSTRAINT a_package_digest_is_thirty_two_bytes CHECK (octet_length(digest) = 32),
    CONSTRAINT a_package_has_content CHECK (total_bytes > 0),
    CONSTRAINT a_version_is_counted_from_one CHECK (ordinal >= 1),
    UNIQUE (asset_kind, asset_id, ordinal)
);

CREATE INDEX version_by_asset ON catalog.version (asset_kind, asset_id, ordinal DESC);
CREATE INDEX version_by_digest ON catalog.version (digest);

-- The files in a package, so a node can fetch only what its cache is missing
-- rather than the whole package on every change.
CREATE TABLE catalog.version_object (
    version_id        text NOT NULL REFERENCES catalog.version (id) ON DELETE CASCADE,
    path              text NOT NULL,
    object_id         text NOT NULL REFERENCES store.object (id),
    PRIMARY KEY (version_id, path),
    CONSTRAINT a_path_is_relative CHECK (path !~ '^/' AND path !~ '\.\.')
);

CREATE INDEX version_object_by_object ON catalog.version_object (object_id);

-- ── What a vehicle is, mechanically ──────────────────────────────────────────
--
-- Separated from the version's manifest because these are the numbers a
-- simulator integrates, not files it loads, and because they are the whole
-- difference between a vehicle that behaves like a submarine and one that is a
-- box with gravity switched off.
--
-- Held as jsonb rather than sixty columns: the hydrodynamic model is a set of
-- matrices whose shape belongs to the runtime that reads it, and a schema that
-- pinned it here would have to change every time the model gains a term.

CREATE TABLE catalog.vehicle_dynamics (
    version_id            text PRIMARY KEY REFERENCES catalog.version (id) ON DELETE CASCADE,

    mass_kg               numeric(12, 4) NOT NULL,
    displaced_volume_m3   numeric(12, 6) NOT NULL,

    -- Both are needed and they are not the same point. The distance between
    -- them is what rights a vehicle when it rolls, so a model that assumes they
    -- coincide has no restoring moment.
    centre_of_gravity_m   numeric(10, 5)[] NOT NULL,
    centre_of_buoyancy_m  numeric(10, 5)[] NOT NULL,
    inertia_tensor        numeric(14, 6)[] NOT NULL,

    -- Fossen's terms: 6x6 added mass, and linear plus quadratic drag.
    added_mass            jsonb NOT NULL,
    linear_damping        jsonb NOT NULL,
    quadratic_damping     jsonb NOT NULL,

    -- Position, orientation, thrust curve and saturation per thruster, plus
    -- the allocation that turns a wrench into per-thruster commands.
    thrusters             jsonb NOT NULL,

    -- Which sensors are mounted where, and with what parameters.
    sensors               jsonb NOT NULL,

    -- What this vehicle publishes and subscribes to, so a stack that expects a
    -- sonar on a vehicle that has none is refused at admission rather than
    -- discovering it mid-dive.
    topic_contract        jsonb NOT NULL,

    CONSTRAINT a_vehicle_has_mass CHECK (mass_kg > 0),
    CONSTRAINT a_vehicle_displaces_water CHECK (displaced_volume_m3 > 0),
    CONSTRAINT a_point_in_space_has_three_components
        CHECK (array_length(centre_of_gravity_m, 1) = 3
           AND array_length(centre_of_buoyancy_m, 1) = 3),
    CONSTRAINT an_inertia_tensor_is_three_by_three
        CHECK (array_length(inertia_tensor, 1) = 9)
);

-- ── Publication is final ─────────────────────────────────────────────────────
--
-- A published version is what somebody's dive is pinned to. Rewriting it would
-- change the meaning of a result that has already been recorded, so the record
-- refuses rather than trusting every future code path to remember.

CREATE FUNCTION catalog.reject_rewrite_of_published() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        IF OLD.published_at IS NOT NULL THEN
            RAISE EXCEPTION
                'version % is published and dives are pinned to it: DELETE is refused', OLD.id;
        END IF;
        RETURN OLD;
    END IF;

    IF OLD.published_at IS NOT NULL THEN
        -- Retiring an asset is allowed; rewriting what it contained is not.
        IF NEW.digest IS DISTINCT FROM OLD.digest
           OR NEW.manifest IS DISTINCT FROM OLD.manifest
           OR NEW.asset_id IS DISTINCT FROM OLD.asset_id
           OR NEW.asset_kind IS DISTINCT FROM OLD.asset_kind
           OR NEW.ordinal IS DISTINCT FROM OLD.ordinal
           OR NEW.published_at IS DISTINCT FROM OLD.published_at THEN
            RAISE EXCEPTION
                'version % is published: its content, identity and publication cannot be rewritten', OLD.id;
        END IF;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER a_published_version_is_not_rewritten
    BEFORE UPDATE OR DELETE ON catalog.version
    FOR EACH ROW EXECUTE FUNCTION catalog.reject_rewrite_of_published();

CREATE FUNCTION catalog.reject_rewrite_of_published_contents() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    published timestamptz;
BEGIN
    SELECT published_at INTO published FROM catalog.version
     WHERE id = COALESCE(NEW.version_id, OLD.version_id);
    IF published IS NOT NULL THEN
        RAISE EXCEPTION
            'version % is published: the files it contains cannot change',
            COALESCE(NEW.version_id, OLD.version_id);
    END IF;
    RETURN COALESCE(NEW, OLD);
END;
$$;

CREATE TRIGGER a_published_version_keeps_its_files
    BEFORE INSERT OR UPDATE OR DELETE ON catalog.version_object
    FOR EACH ROW EXECUTE FUNCTION catalog.reject_rewrite_of_published_contents();

CREATE TRIGGER a_published_vehicle_keeps_its_dynamics
    BEFORE INSERT OR UPDATE OR DELETE ON catalog.vehicle_dynamics
    FOR EACH ROW EXECUTE FUNCTION catalog.reject_rewrite_of_published_contents();

-- ── Access ───────────────────────────────────────────────────────────────────
--
-- A vehicle is granted the way a city is, so policy learns one new scope rather
-- than the platform growing a second way of deciding who may do what. The
-- existing constraint says a scope that is one thing carries no identifier;
-- a vehicle is many things, so it carries one.

ALTER TYPE policy.scope_kind ADD VALUE 'vehicle';
