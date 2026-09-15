-- How many times each scenario is flown.
--
-- One run per scenario makes a coin flip look like a finding, and the sweep
-- that proved it was flown from the application: the same water, twice the
-- allowance, and the score went from 0.971 to 0.429. Nothing about "how long
-- the day is" caused that — the vehicle was dead reckoning for forty minutes
-- and one seed drifted where the other did not. The answer reported it as a
-- dimension that changes the outcome by fifty per cent, because with one run
-- either side of a setting, one flipped run *is* fifty per cent.
--
-- So a scenario is a sample, not a run. Three by default: enough that a single
-- unlucky seed cannot carry a dimension on its own, and cheap enough that
-- nobody thinks twice about it. A scenario survives when more than half of its
-- runs did, and its score is the median of them.

BEGIN;

ALTER TABLE dive.sweep ADD COLUMN repeats integer NOT NULL DEFAULT 1;
ALTER TABLE dive.sweep
    ADD CONSTRAINT a_scenario_is_flown_at_least_once CHECK (repeats >= 1 AND repeats <= 25);

COMMIT;
