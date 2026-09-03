-- A dive has a slot on its host.
--
-- Two dives on one host must not hear each other over DDS, and two watched
-- dives must not be watched on one port. Both used to be derived from the
-- device index, which was fine while a device carried one dive. Now two
-- simulators may share a card when its memory allows, and two dives on card
-- zero would have shared a domain and a port. So a run is given a slot on its
-- host when it is placed — the lowest not held by another dive there — and the
-- domain and the port come from that.

ALTER TABLE dive.run ADD COLUMN host_slot integer;

COMMENT ON COLUMN dive.run.host_slot IS
    'The run''s slot on its host while it prepares or runs: its DDS domain is 1 + slot, its stream port the host''s base + slot.';

CREATE INDEX run_slot_in_use ON dive.run (device_id, host_slot) WHERE state IN ('preparing', 'running');
