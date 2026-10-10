-- A place can belong to an organisation.
--
-- Until now every place was the platform's: founded by a platform
-- administrator, listed to whoever was granted it. An institution that builds
-- a place from its own surveys and videos owns it: its members see it,
-- publish versions of it and share it, and nobody else learns that it exists
-- unless they do. A place with no owner is the platform's catalogue, as before.

ALTER TABLE catalog.city
    ADD COLUMN owned_by_org text REFERENCES identity.organisation (id);

CREATE INDEX city_by_owner ON catalog.city (owned_by_org) WHERE owned_by_org IS NOT NULL;
