-- What a world is built from is kept, not fetched and thrown away.
--
-- A seabed grid from a public source (GEBCO, a depth model on Sentinel-2,
-- ICESat-2 soundings) is a bathymetry asset like a survey, made from public
-- data or derived from others; the coral atlas's habitat classes are a cover
-- asset; the species seen at a place are a species asset. Every one is cited
-- and licensed in what it says about itself.

ALTER TABLE catalog.reconstruction
    DROP CONSTRAINT an_asset_is_of_a_kind,
    ADD CONSTRAINT an_asset_is_of_a_kind
        CHECK (kind IN ('reef', 'structure', 'bathymetry', 'cover', 'species')),
    DROP CONSTRAINT an_asset_is_made_from_something,
    ADD CONSTRAINT an_asset_is_made_from_something
        CHECK (made_from IN ('video', 'survey', 'model', 'route', 'public', 'derived'));
