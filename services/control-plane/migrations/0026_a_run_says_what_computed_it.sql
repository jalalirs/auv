-- What computed a run, and which question it was an answer to.
--
-- The record pins the place, the vehicle, the water and the seed, and pinned
-- none of that mattered while the simulator itself was moving under it: the
-- physics changed six times in one day and every result from before became
-- incomparable with every result after, silently. The runtime version tag did
-- not help — it stayed `r1` through all six, because a tag names a release and
-- not a behaviour.
--
-- Two columns for that, because they answer two different questions. The image
-- digest says *exactly* what ran, which is what a reproduction needs. The
-- physics version says whether the answer would have been the same, which is
-- what a table needs — a runtime rebuilt with a new base image has a different
-- digest and the same physics, and refusing to compare those would make the
-- platform useless by being right too often.
--
-- And a third: which scenario this run is an answer to. A sweep asks one
-- mission against a list of doubts — current from the north-east at half a
-- knot, no Doppler log, murky water — and every run in it is the same mission
-- under one of them. Without this the runs of a sweep are a hundred unrelated
-- dives that happen to share a name. Added in the same migration because the
-- run table should be altered once.

BEGIN;

ALTER TABLE dive.run ADD COLUMN sim_image_digest text;
ALTER TABLE dive.run ADD COLUMN physics_version integer;

-- What was varied, and to what. Free-form on purpose: a doubt is whatever
-- somebody could not promise, and the platform should not hold a list of the
-- weather it is allowed to worry about.
ALTER TABLE dive.run ADD COLUMN scenario jsonb;

-- The runs of one sweep, found by the sweep they belong to.
CREATE INDEX run_of_a_sweep ON dive.run ((scenario ->> 'sweep'))
    WHERE scenario IS NOT NULL;

COMMIT;
