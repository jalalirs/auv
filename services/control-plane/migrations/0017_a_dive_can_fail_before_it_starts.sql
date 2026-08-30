-- A run may end without ever having started.
--
-- The constraint said that anything with an end had a beginning, which sounds
-- obviously true and is not. A dive spends its first minutes preparing: the
-- agent is fetching a place that may be hundreds of megabytes and a vehicle
-- that may be more, and either fetch can fail. When it does, the run ends
-- having never started, and that is exactly the case worth recording — a
-- platform that cannot say "this failed before the simulator came up" leaves
-- somebody guessing at the difference between a package that would not
-- download and a simulation that would not run.
--
-- Refusing it also cost the reason. The agent tried to report why the dive had
-- failed, the record refused the report, and the failure that actually
-- happened was never written down; all anyone could see was that reporting had
-- gone wrong. A constraint that turns a recorded failure into an unrecorded one
-- is worse than no constraint.
--
-- What remains true, and is now what is checked: a run that started before it
-- ended did not end before it started.

ALTER TABLE dive.run DROP CONSTRAINT a_run_that_ended_started;

ALTER TABLE dive.run ADD CONSTRAINT a_run_does_not_end_before_it_starts
    CHECK (started_at IS NULL OR ended_at IS NULL OR ended_at >= started_at);
