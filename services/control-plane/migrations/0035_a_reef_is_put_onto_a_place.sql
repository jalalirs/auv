-- A reef made from a video, put onto a place.
--
-- Two ways. Onto a place that already exists: a job searches its seabed for
-- where the reef's own ground fits, somebody chooses one of the places it
-- found (or moves it by hand), and a second job lays the reef in. Or onto a
-- place of its own: a flat seabed is built for it first, and the reef is laid
-- in the middle. Either way the place gains a draft version with the reef in
-- it. The mapping is the record of that: what was asked, the jobs that ran,
-- what the search found, what was chosen, and the version it made.

CREATE TABLE catalog.mapping (
    id                text PRIMARY KEY,
    org_id            text NOT NULL REFERENCES identity.organisation (id) ON DELETE CASCADE,
    reconstruction_id text NOT NULL REFERENCES catalog.reconstruction (id) ON DELETE CASCADE,
    city_id           text NOT NULL REFERENCES catalog.city (id),
    mode              text NOT NULL,
    brief             jsonb NOT NULL,
    -- The version the reef is laid into: named, or the place's newest, or for
    -- a place of its own, the one its base build made.
    base_version_id   text REFERENCES catalog.version (id),
    build_id          text REFERENCES catalog.build (id),
    resolve_job_id    text REFERENCES exec.job (id),
    -- What the search found (candidates.json), read once from its output.
    candidates        jsonb,
    -- Where the reef is laid, as the lay job was told.
    chosen            jsonb,
    lay_job_id        text REFERENCES exec.job (id),
    version_id        text REFERENCES catalog.version (id),
    failure           text,
    created_by        text NOT NULL REFERENCES identity.principal (id),
    created_at        timestamptz NOT NULL DEFAULT now(),
    recorded_at       timestamptz,
    CONSTRAINT a_mapping_is_own_or_onto CHECK (mode IN ('own', 'onto'))
);

CREATE INDEX mapping_by_reconstruction ON catalog.mapping (reconstruction_id, created_at DESC);
CREATE INDEX mapping_by_city ON catalog.mapping (city_id);
