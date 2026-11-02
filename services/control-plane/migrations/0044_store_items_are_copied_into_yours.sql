-- What you take from the store is a copy of your own.
--
-- A place taken from the store was a share of iOcean's own place. Now it is
-- a new place the organisation owns, whose first version holds the same files
-- (bound to the same bytes, so nothing is stored twice), and which it may
-- change as it likes; the store's place never changes. Taking one again makes
-- another copy. copied_from says which store place each came from.
--
-- Objects work the same way: an object iOcean lists in the store (in_store)
-- is copied into an organisation as an object of its own. A copy shares the
-- original's finished job and files, so one job may now stand behind several
-- objects; the rule that a job made one object holds for originals only.

ALTER TABLE catalog.city
    ADD COLUMN copied_from text REFERENCES catalog.city (id);
CREATE INDEX city_by_copied_from ON catalog.city (copied_from) WHERE copied_from IS NOT NULL;

ALTER TABLE catalog.reconstruction
    ADD COLUMN in_store boolean NOT NULL DEFAULT false,
    ADD COLUMN copied_from text REFERENCES catalog.reconstruction (id);
ALTER TABLE catalog.reconstruction DROP CONSTRAINT IF EXISTS one_reconstruction_per_job;
DROP INDEX IF EXISTS catalog.one_reconstruction_per_job;
CREATE UNIQUE INDEX one_reconstruction_per_job ON catalog.reconstruction (job_id) WHERE copied_from IS NULL;
CREATE INDEX reconstruction_in_store ON catalog.reconstruction (created_at DESC) WHERE in_store AND archived_at IS NULL;
