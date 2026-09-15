-- A sweep: one mission, flown against everything nobody can promise about it.
--
-- A dive that works is not the question. Ship time is the scarce thing,
-- weather windows close, and a season's outplanting happens or it does not.
-- What somebody planning a mission wants to know is not whether it works but
-- *what breaks it*, and there is no way to find that out except by going and
-- finding out — once, here, overnight, instead of once, there, in March.
--
-- It has lived in a terminal tool since it was written. The tool flies the
-- cross product through the ordinary platform and reads the answer back out of
-- the dive names, which works and is not a thing the platform knows about: a
-- sweep could not be looked at, shared, resumed, or shown on a screen, and the
-- runs of one were a hundred unrelated dives that happened to share a prefix.
-- Step 13 gave every run the scenario it answers; this gives the scenario
-- something to belong to.

BEGIN;

CREATE TABLE dive.sweep (
    id                 text PRIMARY KEY,
    org_id             text NOT NULL REFERENCES identity.organisation (id),

    -- The work being doubted. A sweep of a mission rather than of a dive: the
    -- whole point is that the same plan is flown many ways, and a plan that
    -- was not kept could not be flown twice by two people, let alone ninety.
    mission_version_id text NOT NULL REFERENCES catalog.version (id),

    -- The vehicle and the water that are *not* in doubt. Everything the doubts
    -- do is on top of these.
    vehicle_version_id text NOT NULL REFERENCES catalog.version (id),
    water              jsonb NOT NULL DEFAULT '{}'::jsonb,

    name               text NOT NULL,

    -- What nobody can promise: a dimension per key, a setting per value, and
    -- what each setting does to the water or to what was asked for.
    doubts             jsonb NOT NULL,

    -- What counts as having done the job. A threshold rather than a pass mark
    -- on each run, because the question is how many scenarios survive it.
    good               numeric(4, 3) NOT NULL DEFAULT 0.800,

    created_at         timestamptz NOT NULL DEFAULT now(),
    created_by         text NOT NULL REFERENCES identity.principal (id),

    CONSTRAINT a_sweep_has_a_name CHECK (length(name) > 0),
    CONSTRAINT a_threshold_is_a_fraction CHECK (good > 0 AND good <= 1),
    CONSTRAINT a_sweep_doubts_something CHECK (jsonb_typeof(doubts) = 'object')
);

CREATE INDEX sweep_of_an_institution ON dive.sweep (org_id, created_at DESC);

-- Which sweep a run belongs to. The scenario column step 13 added already
-- carries which question it answers; this is the foreign key that makes the
-- answers a sweep rather than a hundred dives with a prefix in common.
ALTER TABLE dive.run ADD COLUMN sweep_id text REFERENCES dive.sweep (id);
CREATE INDEX run_in_a_sweep ON dive.run (sweep_id) WHERE sweep_id IS NOT NULL;

COMMIT;
