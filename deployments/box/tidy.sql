-- Sweep the end-to-end script's litter out of the record.
--
-- Every run of tools/e2e founds a tank, a probe, an observation ROV, a queue
-- with fake cards and an institution, and the platform — rightly — has no
-- way to delete a published thing through its API. This is the operator's
-- broom: run against the box's own database, it removes what the script
-- made and nothing else, by the names the script gives things.
BEGIN;
SET LOCAL session_replication_role = replica;   -- the record's own guards stand aside for the broom

CREATE TEMP TABLE litter_city AS
    SELECT id FROM catalog.city WHERE slug ~ '^(tank|probe-city|nodatum|sneak)-';
CREATE TEMP TABLE litter_vehicle AS
    SELECT id FROM catalog.vehicle WHERE slug ~ '^rov-[0-9]+$';
CREATE TEMP TABLE litter_queue AS
    SELECT id FROM compute.queue WHERE slug ~ '^(box|brief)-[0-9]+$';
CREATE TEMP TABLE litter_org AS
    SELECT id FROM identity.organisation WHERE slug ~ '^other-[0-9]+$';
CREATE TEMP TABLE litter_stack AS
    SELECT id FROM dive.autonomy_stack
     WHERE org_id IN (SELECT id FROM litter_org)
        OR slug ~ '^hold-gpu[0-9]+-[0-9]+$' OR slug = 'station-hold-v2';
CREATE TEMP TABLE litter_version AS
    SELECT id FROM catalog.version
     WHERE (asset_kind = 'city' AND asset_id IN (SELECT id FROM litter_city))
        OR (asset_kind = 'vehicle' AND asset_id IN (SELECT id FROM litter_vehicle));
CREATE TEMP TABLE litter_dive AS
    SELECT id FROM dive.dive
     WHERE city_version_id IN (SELECT id FROM litter_version)
        OR vehicle_version_id IN (SELECT id FROM litter_version)
        OR org_id IN (SELECT id FROM litter_org)
        OR autonomy_stack_id IN (SELECT id FROM litter_stack);
CREATE TEMP TABLE litter_run AS
    SELECT id FROM dive.run
     WHERE dive_id IN (SELECT id FROM litter_dive) OR queue_id IN (SELECT id FROM litter_queue);

DELETE FROM dive.artefact  WHERE run_id IN (SELECT id FROM litter_run);
DELETE FROM dive.hold      WHERE run_id IN (SELECT id FROM litter_run);
DELETE FROM dive.run_event WHERE run_id IN (SELECT id FROM litter_run);
DELETE FROM dive.run       WHERE id IN (SELECT id FROM litter_run);
DELETE FROM dive.dive      WHERE id IN (SELECT id FROM litter_dive);
DELETE FROM dive.run_artefact WHERE run_id IN (SELECT id FROM litter_run);
DELETE FROM dive.autonomy_stack WHERE id IN (SELECT id FROM litter_stack);
DELETE FROM dive.conditions WHERE org_id IN (SELECT id FROM litter_org);
DELETE FROM compute.device WHERE queue_id IN (SELECT id FROM litter_queue);
DELETE FROM compute.queue  WHERE id IN (SELECT id FROM litter_queue);
DELETE FROM catalog.version_object WHERE version_id IN (SELECT id FROM litter_version);
DELETE FROM catalog.version WHERE id IN (SELECT id FROM litter_version);
DELETE FROM catalog.city    WHERE id IN (SELECT id FROM litter_city);
DELETE FROM catalog.vehicle WHERE id IN (SELECT id FROM litter_vehicle);
DELETE FROM identity.membership WHERE org_id IN (SELECT id FROM litter_org);
DELETE FROM identity.organisation WHERE id IN (SELECT id FROM litter_org);

SELECT 'cities' AS what, count(*) FROM catalog.city
UNION ALL SELECT 'vehicles', count(*) FROM catalog.vehicle
UNION ALL SELECT 'queues', count(*) FROM compute.queue
UNION ALL SELECT 'institutions', count(*) FROM identity.organisation
UNION ALL SELECT 'controllers', count(DISTINCT slug) FROM dive.autonomy_stack;
COMMIT;
