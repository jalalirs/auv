-- A run leaves a recording.
--
-- A survey's product is the data, and until now a dive left nothing behind but
-- what it said: a line per second of state and a result. The frames it saw,
-- the poses it took, what its sensors said — the things a survey is for — were
-- written beside the brief on the host and thrown away with it.
--
-- So a run may leave artefacts: files, each an object in storage addressed by
-- its digest as every other file the platform holds is, named by a path within
-- the recording. The agent records them as it uploads them after the dive, and
-- whoever may read the dive may list and fetch them. Derived material, never
-- evidence: a simulator did not observe anything.

CREATE TABLE dive.artefact (
    run_id       text NOT NULL REFERENCES dive.run (id) ON DELETE CASCADE,
    path         text NOT NULL,
    object_id    text NOT NULL REFERENCES store.object (id),
    size_bytes   bigint NOT NULL,
    media_type   text NOT NULL,
    recorded_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (run_id, path),
    CONSTRAINT an_artefact_path_stays_inside_the_recording
        CHECK (path <> '' AND path NOT LIKE '/%' AND path NOT LIKE '%/../%' AND path NOT LIKE '../%')
);

COMMENT ON TABLE dive.artefact IS
    'What a run left behind: the files of its recording, each an object in storage, named by path.';
