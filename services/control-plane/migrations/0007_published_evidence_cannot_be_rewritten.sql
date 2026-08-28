-- Immutability and truth-class propagation, enforced by the database rather
-- than by convention, so that no future code path can quietly bypass them.

-- A published version may only change by being superseded or retracted. Every
-- other column is frozen, and nothing is ever deleted.
CREATE FUNCTION layer.protect_published_version() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'a layer version is evidence and is never deleted: %', OLD.id;
    END IF;

    IF OLD.state IN ('draft', 'in_review') THEN
        RETURN NEW;
    END IF;

    IF NEW.id                  IS DISTINCT FROM OLD.id
       OR NEW.layer_id         IS DISTINCT FROM OLD.layer_id
       OR NEW.ordinal          IS DISTINCT FROM OLD.ordinal
       OR NEW.content_digest   IS DISTINCT FROM OLD.content_digest
       OR NEW.truth_class      IS DISTINCT FROM OLD.truth_class
       OR NEW.crs_epsg         IS DISTINCT FROM OLD.crs_epsg
       OR NEW.vertical_datum   IS DISTINCT FROM OLD.vertical_datum
       OR NEW.extent::text     IS DISTINCT FROM OLD.extent::text
       OR NEW.observed_from    IS DISTINCT FROM OLD.observed_from
       OR NEW.observed_to      IS DISTINCT FROM OLD.observed_to
       OR NEW.uncertainty_kind IS DISTINCT FROM OLD.uncertainty_kind
       OR NEW.rights           IS DISTINCT FROM OLD.rights
       OR NEW.attribution      IS DISTINCT FROM OLD.attribution
       OR NEW.supersedes_id    IS DISTINCT FROM OLD.supersedes_id
       OR NEW.created_at       IS DISTINCT FROM OLD.created_at
       OR NEW.published_at     IS DISTINCT FROM OLD.published_at
    THEN
        RAISE EXCEPTION
            'a published layer version is immutable: % may only be superseded, retracted, or promoted',
            OLD.id;
    END IF;

    IF OLD.state = 'retracted' AND NEW.state <> 'retracted' THEN
        RAISE EXCEPTION 'a retracted layer version stays retracted: %', OLD.id;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER a_published_layer_version_is_immutable
    BEFORE UPDATE OR DELETE ON layer.version
    FOR EACH ROW EXECUTE FUNCTION layer.protect_published_version();

-- A version's manifest is fixed at creation. Changing what a version contains
-- would change what its digest claims.
CREATE FUNCTION layer.protect_manifest() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'a layer version manifest is fixed at creation: % is refused', TG_OP;
END;
$$;

CREATE TRIGGER a_version_manifest_is_fixed
    BEFORE UPDATE OR DELETE ON layer.version_object
    FOR EACH ROW EXECUTE FUNCTION layer.protect_manifest();

-- Anything derived from a scenario is a scenario. Truth class travels down
-- lineage and is never strengthened.
CREATE FUNCTION layer.enforce_truth_class_propagation() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    input_class  layer.truth_class;
    output_class layer.truth_class;
BEGIN
    SELECT truth_class INTO input_class FROM layer.version WHERE id = NEW.input_version_id;
    SELECT truth_class INTO output_class FROM layer.version WHERE id = NEW.output_version_id;

    IF input_class = 'scenario' AND output_class <> 'scenario' THEN
        RAISE EXCEPTION
            'truth class does not strengthen: % derives from scenario % and must itself be a scenario, not %',
            NEW.output_version_id, NEW.input_version_id, output_class;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER truth_class_travels_down_lineage
    AFTER INSERT ON layer.lineage
    FOR EACH ROW EXECUTE FUNCTION layer.enforce_truth_class_propagation();

CREATE FUNCTION layer.protect_lineage() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'lineage is a record of what happened: % is refused', TG_OP;
END;
$$;

CREATE TRIGGER lineage_is_never_rewritten
    BEFORE UPDATE OR DELETE ON layer.lineage
    FOR EACH ROW EXECUTE FUNCTION layer.protect_lineage();
