-- A place an organisation owns can be offered in the store, as an object can
-- (0044): any organisation may then copy it. The store's own places are the
-- platform's discoverable ones, as before; an organisation's place is in the
-- store only while in_store holds, and is copied, never shared in place.

ALTER TABLE catalog.city
    ADD COLUMN in_store boolean NOT NULL DEFAULT false;
