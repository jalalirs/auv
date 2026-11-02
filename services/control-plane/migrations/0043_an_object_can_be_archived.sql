-- An object can be archived.
--
-- Archiving takes a reef, a structure or a survey out of its organisation's
-- listings. Nothing is erased: a place it was laid into still has it, a run
-- that flew there still replays, and reading it by its identifier still
-- works. Who archived it and when are kept with it.

ALTER TABLE catalog.reconstruction
    ADD COLUMN archived_at timestamptz,
    ADD COLUMN archived_by text REFERENCES identity.principal (id),
    ADD CONSTRAINT who_archived_an_object_is_said_only_of_an_archived_one
        CHECK (archived_by IS NULL OR archived_at IS NOT NULL);
