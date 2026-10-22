-- An asset is a reef, a structure or a seabed survey.
--
-- A reconstruction was a reef made from a dive video. It is now any asset an
-- organisation makes and uses in any number of places: a reef from a video, a
-- structure (a pipeline, a platform, a wind turbine's foundation, anything
-- else on the seabed) from a 3D model or a pipeline's route, or a bathymetry
-- survey from its file. Every one is made by a job; the import job that makes
-- a structure or a survey is recorded under its own recipe (asset-import/v1),
-- as the reconstruction's is under reconstruct-video/v1, so nothing in exec
-- changes. What each asset says about itself (asset.json, for the import
-- job's) is the manifest, as before. Every row made before this is a reef
-- from a video.

ALTER TABLE catalog.reconstruction
    ADD COLUMN kind      text NOT NULL DEFAULT 'reef',
    ADD COLUMN made_from text NOT NULL DEFAULT 'video',
    -- A structure's type and how it meets the seabed: {"type", "meets"}.
    ADD COLUMN structure jsonb,
    ADD CONSTRAINT an_asset_is_of_a_kind CHECK (kind IN ('reef', 'structure', 'bathymetry')),
    ADD CONSTRAINT an_asset_is_made_from_something CHECK (made_from IN ('video', 'survey', 'model', 'route')),
    ADD CONSTRAINT a_structure_says_what_it_is CHECK ((kind = 'structure') = (structure IS NOT NULL));

CREATE INDEX reconstruction_by_org_and_kind ON catalog.reconstruction (org_id, kind, created_at DESC);
