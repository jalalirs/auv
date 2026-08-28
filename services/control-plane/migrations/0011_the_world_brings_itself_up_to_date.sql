-- The daily loop. Two capabilities that ingestion needs and that ordinary work
-- must not have: reaching the outside world, and turning a result into
-- evidence without a person.

-- Work runs with no network. Ingestion exists to bring the outside world in, so
-- it needs one. Granting that is a decision, recorded per job, and refused
-- unless the submitter holds authority at the platform.
--
-- It is all or nothing. Narrowing it to named hosts needs a proxy the
-- containers are forced through; recording an allowlist that nothing enforces
-- would read as a control and would not be one.
CREATE TYPE exec.egress AS ENUM ('none', 'internet');

-- An image must name exactly one image. A registry digest does; so does the
-- content identity of an image already on the host, which is how this
-- platform's own images reach hosts that cannot reach a registry. Neither can
-- be moved, which is the whole requirement.
ALTER TABLE exec.job DROP CONSTRAINT an_image_is_pinned_by_digest;
ALTER TABLE exec.job ADD CONSTRAINT an_image_names_exactly_one_image CHECK (
    image_digest ~ '^[a-z0-9.-]+(:[0-9]+)?/?.*@sha256:[0-9a-f]{64}$'
    OR image_digest ~ '^sha256:[0-9a-f]{64}$'
);

ALTER TABLE exec.schedule DROP CONSTRAINT a_scheduled_image_is_pinned_by_digest;
ALTER TABLE exec.schedule ADD CONSTRAINT a_scheduled_image_names_exactly_one_image CHECK (
    image_digest ~ '^[a-z0-9.-]+(:[0-9]+)?/?.*@sha256:[0-9a-f]{64}$'
    OR image_digest ~ '^sha256:[0-9a-f]{64}$'
);

ALTER TABLE exec.job
    ADD COLUMN egress exec.egress NOT NULL DEFAULT 'none';

ALTER TABLE exec.schedule
    ADD COLUMN egress exec.egress NOT NULL DEFAULT 'none';

-- What a job's result becomes.
--
-- The job writes a descriptor saying what its output is — truth class,
-- reference system, datum, extent, time basis, uncertainty, rights — and the
-- platform reads it when the job succeeds. The job holds no credential and
-- reaches no route; it writes a file.
CREATE TABLE exec.publication (
    job_id            text PRIMARY KEY REFERENCES exec.job (id),
    layer_id          text NOT NULL REFERENCES layer.layer (id),
    -- The output whose content describes the version. Every other declared
    -- output becomes the version's payload.
    descriptor_output text NOT NULL,
    -- Whether the result should be published, and whether it should become part
    -- of the shared record. Both are decided when the job is submitted, so a
    -- job cannot promote itself.
    publish           boolean NOT NULL DEFAULT false,
    promote           boolean NOT NULL DEFAULT false,
    -- Whether this result supersedes the layer's current published version,
    -- which is what makes a recurring ingestion a chain rather than a pile.
    supersede_previous boolean NOT NULL DEFAULT false,
    -- Set when the platform has materialised the version, so that a retried or
    -- re-reported job cannot produce a second one.
    version_id        text REFERENCES layer.version (id),
    materialised_at   timestamptz,
    CONSTRAINT a_descriptor_is_named CHECK (descriptor_output <> ''),
    CONSTRAINT a_materialised_publication_names_its_version
        CHECK ((materialised_at IS NULL) = (version_id IS NULL)),
    CONSTRAINT promotion_requires_publication CHECK (publish OR NOT promote)
);

CREATE INDEX publication_by_layer ON exec.publication (layer_id);

-- The declaration is fixed at submission. What a job was asked to produce
-- cannot change because of what it produced.
CREATE FUNCTION exec.protect_publication() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'a publication declaration is part of the job record: % is refused', TG_OP;
    END IF;
    IF NEW.job_id            IS DISTINCT FROM OLD.job_id
       OR NEW.layer_id          IS DISTINCT FROM OLD.layer_id
       OR NEW.descriptor_output IS DISTINCT FROM OLD.descriptor_output
       OR NEW.publish            IS DISTINCT FROM OLD.publish
       OR NEW.promote            IS DISTINCT FROM OLD.promote
       OR NEW.supersede_previous IS DISTINCT FROM OLD.supersede_previous
    THEN
        RAISE EXCEPTION
            'what a job was submitted to publish cannot change: %', OLD.job_id;
    END IF;
    IF OLD.version_id IS NOT NULL AND NEW.version_id IS DISTINCT FROM OLD.version_id THEN
        RAISE EXCEPTION 'this job has already produced version %', OLD.version_id;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER what_a_job_publishes_is_fixed_at_submission
    BEFORE UPDATE OR DELETE ON exec.publication
    FOR EACH ROW EXECUTE FUNCTION exec.protect_publication();

-- Recurring work declares a publication the same way, and every job it submits
-- inherits it.
CREATE TABLE exec.schedule_publication (
    schedule_id       text PRIMARY KEY REFERENCES exec.schedule (id) ON DELETE CASCADE,
    layer_id          text NOT NULL REFERENCES layer.layer (id),
    descriptor_output text NOT NULL,
    publish            boolean NOT NULL DEFAULT false,
    promote            boolean NOT NULL DEFAULT false,
    supersede_previous boolean NOT NULL DEFAULT false,
    CONSTRAINT a_scheduled_descriptor_is_named CHECK (descriptor_output <> ''),
    CONSTRAINT scheduled_promotion_requires_publication CHECK (publish OR NOT promote)
);
