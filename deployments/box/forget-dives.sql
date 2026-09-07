-- Forget particular dives, named by id in the table this file expects to find.
--
-- clean-dives.sql empties the whole record, which is right before a
-- demonstration and wrong when a handful of runs were flown against an older
-- simulator and need flying again: re-flying without forgetting leaves two
-- runs under one name, and every reader of the record then has to guess which
-- one is meant.
--
-- The caller writes the ids into coral_forget first. As with clean-dives, the
-- stored bytes of a recording are left alone — they are addressed by their own
-- digest and may be shared — and what goes is every reference to them.
BEGIN;
SET LOCAL session_replication_role = replica;   -- the record's guards stand aside

DELETE FROM dive.artefact WHERE run_id IN (
    SELECT id FROM dive.run WHERE dive_id IN (SELECT id FROM coral_forget));
DELETE FROM dive.run_artefact WHERE run_id IN (
    SELECT id FROM dive.run WHERE dive_id IN (SELECT id FROM coral_forget));
DELETE FROM dive.run_event WHERE run_id IN (
    SELECT id FROM dive.run WHERE dive_id IN (SELECT id FROM coral_forget));
DELETE FROM dive.hold WHERE run_id IN (
    SELECT id FROM dive.run WHERE dive_id IN (SELECT id FROM coral_forget));
DELETE FROM dive.run WHERE dive_id IN (SELECT id FROM coral_forget);
DELETE FROM dive.dive WHERE id IN (SELECT id FROM coral_forget);

SELECT 'dives left' AS what, count(*) FROM dive.dive
UNION ALL SELECT 'runs left', count(*) FROM dive.run;
COMMIT;
