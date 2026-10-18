-- A reef made from a dive video, on the platform's machines.
--
-- Somebody uploads a video of a swim over a reef; the platform runs the
-- reconstruction as a job on a GPU, and what it makes (the reef as splats in
-- pieces, the ground under it, the path the camera took) is kept as objects
-- the organisation holds. The reconstruction is the record of that request:
-- what was asked, the job that ran it, and the files it made. Laying it into
-- a place is a separate act, recorded elsewhere.

CREATE TABLE catalog.reconstruction (
    id          text PRIMARY KEY,
    org_id      text NOT NULL REFERENCES identity.organisation (id) ON DELETE CASCADE,
    job_id      text NOT NULL REFERENCES exec.job (id),
    brief       jsonb NOT NULL,
    name        text NOT NULL,
    -- What the reconstruction said about itself (reconstruction.json): its
    -- pieces, its extent, how its scale was found. Read once from the
    -- package, kept here.
    manifest    jsonb,
    failure     text,
    created_by  text NOT NULL REFERENCES identity.principal (id),
    created_at  timestamptz NOT NULL DEFAULT now(),
    recorded_at timestamptz
);

CREATE INDEX reconstruction_by_org ON catalog.reconstruction (org_id, created_at DESC);
CREATE UNIQUE INDEX one_reconstruction_per_job ON catalog.reconstruction (job_id);

-- The files a reconstruction made, by the path the job wrote them at. Each is
-- an object the organisation holds, so it is kept for as long as the
-- reconstruction refers to it.
CREATE TABLE catalog.reconstruction_object (
    reconstruction_id text NOT NULL REFERENCES catalog.reconstruction (id) ON DELETE CASCADE,
    path              text NOT NULL,
    object_id         text NOT NULL REFERENCES store.object (id),
    size_bytes        bigint NOT NULL,
    media_type        text NOT NULL,
    PRIMARY KEY (reconstruction_id, path)
);

CREATE INDEX reconstruction_object_by_object ON catalog.reconstruction_object (object_id);
