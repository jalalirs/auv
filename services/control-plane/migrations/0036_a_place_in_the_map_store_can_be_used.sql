-- A place in the map store, used by an organisation.
--
-- The map store is the platform's own places that anybody may find: built
-- from public data, checked and published by iOcean. An organisation that
-- uses one is given it to see, as a binding like any other share; what is
-- new is that the binding says why it exists, so that letting go of a place
-- taken from the store withdraws only what taking it gave, and never a share
-- somebody granted on purpose.

ALTER TABLE policy.binding ADD COLUMN granted_via text;
