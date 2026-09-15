-- What a dive found that the chart does not say.
--
-- A sweep could already ask what half a knot does, because half a knot is a
-- number and numbers go in the conditions. It could not ask *the mooring is
-- thirty metres from where it was laid*, or *the array has a transponder
-- down*, or *there is a net where the chart says clear water* — and those are
-- the things that actually go wrong, because they are the things nobody
-- measured.
--
-- Kept on the dive rather than folded into the layout, and deliberately: a
-- layout is what somebody drew and pinned, and a scenario that edited it would
-- make the pin worthless. This is what happened to it.

BEGIN;

ALTER TABLE dive.dive ADD COLUMN layout_changes jsonb;

COMMIT;
