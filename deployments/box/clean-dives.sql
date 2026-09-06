-- Clear the record of dives, so a demonstration starts from nothing.
--
-- Every dive, every run, every recording and every constructed body of water
-- goes. What made them does not: the places, the vehicles, their published
-- packages, the controllers deployed to the institution, the queue and its
-- machines are all left exactly as they are, because those are the platform
-- and the dives are only what has been done with it.
--
-- The stored bytes of a recording are addressed by their own digest and may be
-- shared, so the objects are left in storage; what goes is every reference to
-- them from a run.
BEGIN;
SET LOCAL session_replication_role = replica;   -- the record's guards stand aside

DELETE FROM dive.artefact;
DELETE FROM dive.run_artefact;
DELETE FROM dive.hold;
DELETE FROM dive.run_event;
DELETE FROM dive.run;
DELETE FROM dive.dive;
-- Conditions are defined per dive by the application, so they go with them.
-- Anything observed rather than constructed is a measurement of the real sea
-- and is kept.
DELETE FROM dive.conditions WHERE kind = 'constructed';

SELECT 'dives' AS what, count(*) FROM dive.dive
UNION ALL SELECT 'runs', count(*) FROM dive.run
UNION ALL SELECT 'recordings', count(*) FROM dive.artefact
UNION ALL SELECT 'conditions', count(*) FROM dive.conditions
UNION ALL SELECT 'places kept', count(*) FROM catalog.city
UNION ALL SELECT 'vehicles kept', count(*) FROM catalog.vehicle
UNION ALL SELECT 'controllers kept', count(DISTINCT slug) FROM dive.autonomy_stack;
COMMIT;
