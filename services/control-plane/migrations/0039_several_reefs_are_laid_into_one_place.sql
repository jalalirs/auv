-- Several reefs laid into one place, in one job.
--
-- A mapping put one reef onto a place. It now puts any number: each reef has
-- a search of its own, somebody chooses where each goes (or drops one whose
-- search found nothing), and one job lays them all into one version. What was
-- the reef's on the mapping (its search, what it found, where it went) is now
-- each reef's own row. A mapping made before this is one reef, and is moved
-- into its row here.

CREATE TABLE catalog.mapping_asset (
    mapping_id        text NOT NULL REFERENCES catalog.mapping (id) ON DELETE CASCADE,
    ordinal           integer NOT NULL,
    reconstruction_id text NOT NULL REFERENCES catalog.reconstruction (id) ON DELETE CASCADE,
    -- What the reef is called in the place: its reconstruction's name made a
    -- slug, unique within the place.
    name              text NOT NULL,
    -- What its search is told: where its video starts, how far to look, how
    -- deep it is, how many places to report; for a place of its own, which
    -- way it faces.
    brief             jsonb NOT NULL,
    resolve_job_id    text REFERENCES exec.job (id),
    candidates        jsonb,
    start             jsonb,
    searched          jsonb,
    chosen            jsonb,
    failure           text,
    dropped_at        timestamptz,
    PRIMARY KEY (mapping_id, ordinal)
);

CREATE INDEX mapping_asset_by_reconstruction ON catalog.mapping_asset (reconstruction_id);

INSERT INTO catalog.mapping_asset
    (mapping_id, ordinal, reconstruction_id, name, brief, resolve_job_id, candidates, start, searched, chosen)
SELECT m.id, 0, m.reconstruction_id,
       coalesce(nullif(trim(BOTH '-' FROM lower(regexp_replace(r.name, '[^A-Za-z0-9]+', '-', 'g'))), ''), 'reef'),
       jsonb_strip_nulls(jsonb_build_object(
           'reconstructionId', m.reconstruction_id, 'start', m.brief -> 'start',
           'withinM', m.brief -> 'withinM', 'depthM', m.brief -> 'depthM', 'count', m.brief -> 'count',
           'headingDeg', m.brief -> 'headingDeg', 'startAssumed', m.brief -> 'startAssumed')),
       m.resolve_job_id, m.candidates -> 'candidates', m.candidates -> 'start', m.candidates -> 'searched',
       m.chosen
FROM catalog.mapping m
JOIN catalog.reconstruction r ON r.id = m.reconstruction_id;

-- The mapping keeps the first reef's reconstruction, which is what one asked
-- for from a reconstruction is listed by; a mapping asked for from a place
-- names its reefs in their rows.
ALTER TABLE catalog.mapping
    DROP COLUMN resolve_job_id,
    DROP COLUMN candidates,
    DROP COLUMN chosen,
    ALTER COLUMN reconstruction_id DROP NOT NULL;
