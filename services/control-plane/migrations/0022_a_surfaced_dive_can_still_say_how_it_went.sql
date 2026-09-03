-- A surfaced dive can still say how it went.
--
-- A person leaving a dive they were flying ends it by their own hand, and the
-- run is over the moment they do: succeeded, surfaced. The simulator is then
-- asked to stop and, a few seconds later, says where the vehicle settled, how
-- the task went, and that its recording was kept. That report used to be
-- refused — the run had finished, and a result is not edited — so a flown
-- dive kept no result and no recording, which is the one kind of dive a
-- person is certain to want back.
--
-- The rule stays: a finished run's state and determinants never change, and
-- an outcome is never taken away. What is now allowed is for a run the person
-- surfaced from to have more said about it, as long as everything already said
-- is still in it.

CREATE OR REPLACE FUNCTION dive.reject_rewrite_of_finished_run() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'run % is a result: DELETE is refused', OLD.id;
    END IF;
    IF OLD.state IN ('succeeded', 'failed', 'cancelled', 'expired') THEN
        IF OLD.state = 'succeeded'
           AND (OLD.outcome ->> 'surfaced') = 'true'
           AND NEW.state = OLD.state
           AND NEW.outcome @> OLD.outcome
           AND NEW.ended_at = OLD.ended_at
           AND NEW.failure_reason IS NOT DISTINCT FROM OLD.failure_reason
           AND NEW.device_id IS NOT DISTINCT FROM OLD.device_id
           AND NEW.host_slot IS NOT DISTINCT FROM OLD.host_slot THEN
            RETURN NEW;
        END IF;
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
