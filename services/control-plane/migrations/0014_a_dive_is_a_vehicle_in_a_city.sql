-- A dive is the platform's central noun, and a run is what happened when one
-- was executed.
--
--     Dive = Vehicle × City × Conditions × Autonomy
--
-- Everything the platform owns exists to make that composition possible, and
-- everything it records exists to make the result of it trustworthy. A run
-- pins each of the four by digest or by seed, so that "scenario 147 failed" can
-- be opened tomorrow and fail identically. Without that the platform produces
-- anecdotes.

CREATE SCHEMA compute;
CREATE SCHEMA dive;

-- ── Queues ───────────────────────────────────────────────────────────────────
--
-- The governed resource is the queue, not the GPU. Access is granted to a
-- queue; the queue holds however many GPUs it holds. That is what lets one
-- workstation and, later, a rack or a cloud region be described the same way,
-- and it is why adding hardware is an insert rather than a migration.

CREATE TABLE compute.queue (
    id                text PRIMARY KEY,
    slug              text NOT NULL UNIQUE,
    name              text NOT NULL,
    summary           text NOT NULL DEFAULT '',

    -- How long a dive may hold a device before it must ask again. An
    -- interactive session that loses its human should not hold a GPU until
    -- somebody notices.
    lease_seconds     integer NOT NULL DEFAULT 3600,

    -- A queue that is draining accepts nothing new and lets what it has finish,
    -- which is how a host is taken out of service without killing a dive.
    draining          boolean NOT NULL DEFAULT false,

    created_at        timestamptz NOT NULL DEFAULT now(),
    created_by        text NOT NULL REFERENCES identity.principal (id),

    CONSTRAINT a_queue_slug_is_a_handle CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$'),
    CONSTRAINT a_lease_is_at_least_a_minute CHECK (lease_seconds >= 60)
);

-- A device is a GPU in a queue, on a host that runs an agent.
--
-- Whole devices, not fractions. The workstation this was written on cannot
-- partition a GPU — MIG is a data-centre feature and an RTX 5880 Ada reports
-- none — so a fractional claim here would be a promise the hardware does not
-- keep. The share column records what a dive asked for so that the scheduler's
-- arithmetic is already fractional on the day a device can honour it.

CREATE TABLE compute.device (
    id                text PRIMARY KEY,
    queue_id          text NOT NULL REFERENCES compute.queue (id) ON DELETE CASCADE,
    target_id         text NOT NULL REFERENCES exec.target (id) ON DELETE CASCADE,

    -- The index the host's driver knows it by, and the UUID that survives a
    -- reboot reordering them.
    device_index      integer NOT NULL,
    uuid              text NOT NULL UNIQUE,
    model             text NOT NULL,
    memory_bytes      bigint NOT NULL,

    enabled           boolean NOT NULL DEFAULT true,
    created_at        timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT a_device_has_memory CHECK (memory_bytes > 0),
    CONSTRAINT a_device_index_is_not_negative CHECK (device_index >= 0),
    UNIQUE (target_id, device_index)
);

CREATE INDEX device_by_queue ON compute.device (queue_id) WHERE enabled;

-- ── What a person brings ─────────────────────────────────────────────────────
--
-- Autonomy is the one thing here that is not ours. It arrives as a container
-- image, pinned by digest rather than tag, because a dive re-run against a tag
-- that has moved is measuring a different program and reporting it as the same
-- one.

CREATE TABLE dive.autonomy_stack (
    id                text PRIMARY KEY,
    org_id            text NOT NULL REFERENCES identity.organisation (id) ON DELETE CASCADE,
    slug              text NOT NULL,
    name              text NOT NULL,

    image_repository  text NOT NULL,
    image_digest      text NOT NULL,

    -- What it expects to receive and what it will send. Checked against the
    -- vehicle's contract at admission, so a mismatch is a refusal with a reason
    -- rather than a dive that quietly does nothing.
    subscribes        jsonb NOT NULL DEFAULT '[]'::jsonb,
    publishes         jsonb NOT NULL DEFAULT '[]'::jsonb,

    -- Inference needs a device too, and on a single-GPU host it shares one with
    -- the simulator.
    wants_gpu         boolean NOT NULL DEFAULT false,

    created_at        timestamptz NOT NULL DEFAULT now(),
    created_by        text NOT NULL REFERENCES identity.principal (id),
    retired_at        timestamptz,

    CONSTRAINT a_stack_slug_is_a_handle CHECK (slug ~ '^[a-z0-9][a-z0-9-]{1,62}[a-z0-9]$'),
    CONSTRAINT a_stack_is_pinned_by_digest CHECK (image_digest ~ '^sha256:[0-9a-f]{64}$'),
    UNIQUE (org_id, slug)
);

-- ── Conditions ───────────────────────────────────────────────────────────────
--
-- Either the ocean as it was on a date, or a situation somebody constructed.
-- The distinction is the platform's most important claim about a result, so it
-- is a column and not a convention: a conclusion drawn from measured water is
-- worth more than one drawn from invented water, and nothing should be able to
-- confuse them by omission.

CREATE TYPE dive.conditions_kind AS ENUM ('observed', 'constructed');

CREATE TABLE dive.conditions (
    id                text PRIMARY KEY,
    kind              dive.conditions_kind NOT NULL,
    name              text NOT NULL,

    -- For observed conditions: the instant the ocean state is drawn from, and
    -- the sources it came from with the digest of each, so the same water can
    -- be assembled again.
    observed_at       timestamptz,
    sources           jsonb NOT NULL DEFAULT '[]'::jsonb,

    -- For constructed conditions: the parameters somebody chose.
    parameters        jsonb NOT NULL DEFAULT '{}'::jsonb,

    org_id            text REFERENCES identity.organisation (id) ON DELETE CASCADE,
    created_at        timestamptz NOT NULL DEFAULT now(),
    created_by        text NOT NULL REFERENCES identity.principal (id),

    CONSTRAINT observed_conditions_name_an_instant
        CHECK ((kind = 'observed') = (observed_at IS NOT NULL))
);

-- ── The dive ─────────────────────────────────────────────────────────────────
--
-- A definition, not an execution. It names versions rather than assets, so a
-- dive does not silently become a different experiment when a new vehicle is
-- published.

CREATE TABLE dive.dive (
    id                text PRIMARY KEY,
    org_id            text NOT NULL REFERENCES identity.organisation (id) ON DELETE CASCADE,
    name              text NOT NULL,
    summary           text NOT NULL DEFAULT '',

    city_version_id   text NOT NULL REFERENCES catalog.version (id),
    vehicle_version_id text NOT NULL REFERENCES catalog.version (id),
    conditions_id     text NOT NULL REFERENCES dive.conditions (id),
    autonomy_stack_id text REFERENCES dive.autonomy_stack (id),

    -- Where the vehicle starts, and what would count as having succeeded.
    initial_state     jsonb NOT NULL DEFAULT '{}'::jsonb,
    objective         jsonb NOT NULL DEFAULT '{}'::jsonb,

    created_at        timestamptz NOT NULL DEFAULT now(),
    created_by        text NOT NULL REFERENCES identity.principal (id),
    archived_at       timestamptz
);

CREATE INDEX dive_by_org ON dive.dive (org_id, created_at DESC) WHERE archived_at IS NULL;

-- ── The run ──────────────────────────────────────────────────────────────────
--
-- Interactive and batch are the same object. One holds a video stream and a
-- human; the other does not. Making them two kinds of thing would mean two
-- schedulers, two records, and eventually two answers to the same question.

CREATE TYPE dive.run_mode AS ENUM ('interactive', 'batch');

CREATE TYPE dive.run_state AS ENUM (
    'queued',      -- admitted, waiting for a device
    'preparing',   -- a device is held; the node is fetching what it lacks
    'running',
    'succeeded',
    'failed',
    'cancelled',
    'expired'      -- the lease ran out and nobody renewed it
);

CREATE TABLE dive.run (
    id                text PRIMARY KEY,
    dive_id           text NOT NULL REFERENCES dive.dive (id),
    queue_id          text NOT NULL REFERENCES compute.queue (id),
    mode              dive.run_mode NOT NULL,
    state             dive.run_state NOT NULL DEFAULT 'queued',

    -- Every determinant of the result, copied rather than referenced. The dive
    -- may be edited afterwards; what ran must not change when it is.
    city_digest       bytea NOT NULL,
    vehicle_digest    bytea NOT NULL,
    autonomy_digest   text,
    conditions_digest bytea NOT NULL,

    -- Same seed and same digests means the same run. This is the property the
    -- whole platform rests on: replay costs nothing, a regression is real
    -- rather than noise, and a failure can be reopened and watched.
    seed              bigint NOT NULL,

    -- The runtime is a determinant too. A physics fix changes results, so
    -- comparing across versions has to be refused rather than done quietly.
    runtime_version   text NOT NULL,

    -- What it was granted, and what it asked for.
    device_id         text REFERENCES compute.device (id),
    gpu_share         numeric(4, 3) NOT NULL DEFAULT 1.000,

    requested_at      timestamptz NOT NULL DEFAULT now(),
    requested_by      text NOT NULL REFERENCES identity.principal (id),
    started_at        timestamptz,
    ended_at          timestamptz,
    lease_expires_at  timestamptz,

    outcome           jsonb NOT NULL DEFAULT '{}'::jsonb,
    failure_reason    text,

    CONSTRAINT a_digest_is_thirty_two_bytes
        CHECK (octet_length(city_digest) = 32
           AND octet_length(vehicle_digest) = 32
           AND octet_length(conditions_digest) = 32),
    CONSTRAINT a_share_is_a_fraction_of_one_device
        CHECK (gpu_share > 0 AND gpu_share <= 1),
    CONSTRAINT a_run_that_ended_started CHECK (ended_at IS NULL OR started_at IS NOT NULL),
    CONSTRAINT a_failed_run_says_why
        CHECK ((state = 'failed') = (failure_reason IS NOT NULL))
);

CREATE INDEX run_by_dive ON dive.run (dive_id, requested_at DESC);
CREATE INDEX run_waiting ON dive.run (queue_id, requested_at) WHERE state = 'queued';
CREATE INDEX run_holding_a_device ON dive.run (device_id) WHERE state IN ('preparing', 'running');

-- A device carries one running dive at a time. Enforced here rather than in the
-- scheduler, because two schedulers racing is exactly the case a scheduler
-- cannot check for itself.
CREATE UNIQUE INDEX a_device_carries_one_run
    ON dive.run (device_id) WHERE state IN ('preparing', 'running');

-- ── What happened ────────────────────────────────────────────────────────────
--
-- Telemetry is always recorded and is small: poses, commands, events. Sensor
-- frames are gigabytes per minute and are recorded only when frames are the
-- deliverable — which is a data-generation product, not a logging default.
-- Because a run is deterministic, reviewing one does not need recorded video;
-- it can be rendered again from the seed.

CREATE TABLE dive.run_event (
    id                bigserial PRIMARY KEY,
    run_id            text NOT NULL REFERENCES dive.run (id) ON DELETE CASCADE,
    occurred_at       timestamptz NOT NULL DEFAULT now(),
    simulated_seconds numeric(12, 4),
    kind              text NOT NULL,
    detail            jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX run_event_by_run ON dive.run_event (run_id, id);

CREATE TABLE dive.run_artefact (
    run_id            text NOT NULL REFERENCES dive.run (id) ON DELETE CASCADE,
    path              text NOT NULL,
    object_id         text NOT NULL REFERENCES store.object (id),
    kind              text NOT NULL,
    PRIMARY KEY (run_id, path),
    CONSTRAINT an_artefact_path_is_relative CHECK (path !~ '^/' AND path !~ '\.\.')
);

-- ── A result is not edited ───────────────────────────────────────────────────

CREATE FUNCTION dive.reject_rewrite_of_finished_run() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'run % is a result: DELETE is refused', OLD.id;
    END IF;
    IF OLD.state IN ('succeeded', 'failed', 'cancelled', 'expired') THEN
        RAISE EXCEPTION
            'run % finished as %: what happened cannot be rewritten', OLD.id, OLD.state;
    END IF;
    -- What was pinned is what ran, for the whole life of the row.
    IF NEW.seed IS DISTINCT FROM OLD.seed
       OR NEW.city_digest IS DISTINCT FROM OLD.city_digest
       OR NEW.vehicle_digest IS DISTINCT FROM OLD.vehicle_digest
       OR NEW.conditions_digest IS DISTINCT FROM OLD.conditions_digest
       OR NEW.autonomy_digest IS DISTINCT FROM OLD.autonomy_digest
       OR NEW.runtime_version IS DISTINCT FROM OLD.runtime_version THEN
        RAISE EXCEPTION 'run %: what determined the result cannot be changed', OLD.id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER a_finished_run_is_not_rewritten
    BEFORE UPDATE OR DELETE ON dive.run
    FOR EACH ROW EXECUTE FUNCTION dive.reject_rewrite_of_finished_run();

CREATE FUNCTION dive.reject_rewrite_of_event() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'a run event is a record of what happened: % is refused', TG_OP;
END;
$$;

CREATE TRIGGER a_run_event_is_append_only
    BEFORE UPDATE OR DELETE ON dive.run_event
    FOR EACH ROW EXECUTE FUNCTION dive.reject_rewrite_of_event();
