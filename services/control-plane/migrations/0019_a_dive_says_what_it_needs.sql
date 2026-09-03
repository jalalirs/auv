-- A dive says what it needs, and a run holds what it was given.
--
-- Until now a run held one whole GPU, chosen by the agent, and nothing else
-- was counted: not the card's memory, not the host's processors, not what a
-- controller that is a model would need beside the simulator. That was right
-- when every dive was one simulator and a person at the keys. It stops being
-- right the day a policy needing ten gigabytes is placed beside a simulator
-- needing twenty on a twenty-four gigabyte card, and nothing notices until
-- the container dies.
--
-- So a dive declares its needs, assembled from its parts — the simulator's,
-- the controller's, the mode's — and a run holds an allocation: one or more
-- devices, each with an amount. The simulator and the controller may share a
-- card when its memory allows, or take two; the platform decides, not the
-- agent. A device may therefore carry parts of several runs, which is why the
-- rule that a device carries one run goes.

ALTER TABLE dive.autonomy_stack
    ADD COLUMN needs jsonb NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN dive.autonomy_stack.needs IS
    'What the controller needs beside the simulator: gpu, gpuMemoryBytes, cpu, memoryBytes. Written by whoever deploys it.';

ALTER TABLE dive.run
    ADD COLUMN needs jsonb NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN dive.run.needs IS
    'What this run was admitted needing, assembled at admission and copied so that the stack changing afterwards cannot change what was placed.';

CREATE TABLE dive.hold (
    run_id            text NOT NULL REFERENCES dive.run (id) ON DELETE CASCADE,
    device_id         text NOT NULL REFERENCES compute.device (id),
    part              text NOT NULL,
    gpu_memory_bytes  bigint NOT NULL,
    PRIMARY KEY (run_id, part),
    CONSTRAINT a_part_is_the_simulator_or_the_controller
        CHECK (part IN ('simulator', 'controller')),
    CONSTRAINT a_hold_is_not_negative CHECK (gpu_memory_bytes >= 0)
);

CREATE INDEX hold_by_device ON dive.hold (device_id);

COMMENT ON TABLE dive.hold IS
    'What a run holds on which device, per part. Counted against the device while the run is preparing or running.';

DROP INDEX dive.a_device_carries_one_run;

-- A refused dive says why, in the same ledger a refused job does.
ALTER TYPE exec.refusal_reason ADD VALUE IF NOT EXISTS 'no_device_fits';
ALTER TYPE exec.refusal_reason ADD VALUE IF NOT EXISTS 'queue_draining';
ALTER TYPE exec.refusal_reason ADD VALUE IF NOT EXISTS 'runtime_unavailable';
ALTER TYPE exec.refusal_reason ADD VALUE IF NOT EXISTS 'quota_dives_exhausted';
ALTER TYPE exec.refusal_reason ADD VALUE IF NOT EXISTS 'quota_gpu_hours_exhausted';

-- Quotas on dives, as there are on jobs: how many at once, and how many
-- GPU-hours in a day. Two dives at once and a day of one card are what a
-- workstation can give a small institution without anyone noticing.
ALTER TABLE exec.quota
    ADD COLUMN max_concurrent_dives integer NOT NULL DEFAULT 2,
    ADD COLUMN max_gpu_hours_daily  numeric(8, 2) NOT NULL DEFAULT 24;

-- What the host has, said by the host when it asks for work. Processors and
-- memory sit on the target because they are the host's, not any one card's.
COMMENT ON COLUMN exec.target.capacity_cpu IS
    'Processors on the host, as it last reported when asking for work.';
COMMENT ON COLUMN exec.target.capacity_memory_bytes IS
    'Memory on the host, as it last reported when asking for work.';
