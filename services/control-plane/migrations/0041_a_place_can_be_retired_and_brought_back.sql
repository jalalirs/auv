-- A place can be retired, and brought back.
--
-- Retiring takes a place out of every listing and refuses new dives in it.
-- Nothing is erased: its versions, its runs and their files stay, a dive
-- already flown in it still replays, and reading it by its identifier says
-- that it is retired, when, and by whom. Bringing it back clears both.
--
-- retired_at has been on the table since 0013 and the listings already skip
-- it; what was missing is who did it, and a way to do it at all.

ALTER TABLE catalog.city
    ADD COLUMN IF NOT EXISTS retired_at timestamptz,
    ADD COLUMN retired_by text REFERENCES identity.principal (id),
    ADD CONSTRAINT who_retired_a_place_is_said_only_of_a_retired_one
        CHECK (retired_by IS NULL OR retired_at IS NOT NULL);
