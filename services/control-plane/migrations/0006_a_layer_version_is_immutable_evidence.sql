-- Layers. Every datum in the platform is a layer: bathymetry, a mesh, a
-- gridded field, an observation series, an annotation, a simulation output.
-- A layer is contained by its scope and attributed to an organisation; those
-- are different things.

CREATE SCHEMA layer;

CREATE TYPE layer.scope_kind AS ENUM ('platform', 'city');

CREATE TYPE layer.kind AS ENUM (
    'bathymetry', 'mesh', 'point_cloud', 'orthomosaic', 'structure',
    'field', 'observation_series', 'annotation', 'telemetry', 'tileset', 'imagery'
);

-- What a value is, epistemically. This travels down lineage and can never be
-- strengthened by a derived job.
CREATE TYPE layer.truth_class AS ENUM (
    'observation', 'analysis', 'forecast', 'scenario', 'simulation'
);

CREATE TYPE layer.state AS ENUM (
    'draft', 'in_review', 'published', 'superseded', 'retracted'
);

-- Canonical layers are the shared record. Restricted layers are visible only
-- through a binding. Promotion moves a layer from restricted to canonical and
-- changes nothing else.
CREATE TYPE layer.visibility AS ENUM ('restricted', 'canonical');

-- Uncertainty is always stated. 'unknown' is an answer; absence is not.
CREATE TYPE layer.uncertainty_kind AS ENUM (
    'unknown', 'absolute_metres', 'relative_fraction', 'described'
);

CREATE TABLE layer.layer (
    id                 text PRIMARY KEY,
    scope_kind         layer.scope_kind NOT NULL,
    city_id            text REFERENCES city.city (id),
    slug               text NOT NULL,
    kind               layer.kind NOT NULL,
    title              text NOT NULL,
    description        text NOT NULL,
    attributed_org_id  text NOT NULL REFERENCES identity.organisation (id),
    created_by         text NOT NULL REFERENCES identity.principal (id),
    created_at         timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT layer_slug_is_a_label CHECK (slug ~ '^[a-z][a-z0-9-]{0,61}[a-z0-9]$'),
    CONSTRAINT a_city_layer_names_its_city CHECK ((scope_kind = 'city') = (city_id IS NOT NULL))
);

CREATE UNIQUE INDEX one_layer_slug_per_scope
    ON layer.layer (scope_kind, coalesce(city_id, ''), slug);
CREATE INDEX layer_by_city ON layer.layer (city_id) WHERE city_id IS NOT NULL;
CREATE INDEX layer_by_org ON layer.layer (attributed_org_id);

CREATE TABLE layer.version (
    id                    text PRIMARY KEY,
    layer_id              text NOT NULL REFERENCES layer.layer (id),
    ordinal               integer NOT NULL,

    -- Identity of the content: the digest over this version's sorted manifest.
    content_digest        bytea NOT NULL,

    truth_class           layer.truth_class NOT NULL,
    crs_epsg              integer NOT NULL,
    vertical_datum        text NOT NULL,
    extent                geography(Polygon, 4326) NOT NULL,

    -- Time basis. The instrument clock offset is recorded where it is known.
    observed_from         timestamptz NOT NULL,
    observed_to           timestamptz NOT NULL,
    clock_offset_seconds  double precision,

    uncertainty_kind      layer.uncertainty_kind NOT NULL,
    uncertainty_value     double precision,
    uncertainty_note      text NOT NULL DEFAULT '',

    rights                text NOT NULL,
    attribution           text NOT NULL,

    state                 layer.state NOT NULL DEFAULT 'draft',
    visibility            layer.visibility NOT NULL DEFAULT 'restricted',

    supersedes_id         text REFERENCES layer.version (id),
    superseded_by_id      text REFERENCES layer.version (id),

    -- Exactly one producer: a job, or a person who uploaded it directly.
    producer_job_id       text,
    producer_principal_id text REFERENCES identity.principal (id),
    recipe_id             text NOT NULL DEFAULT '',
    image_digest          text NOT NULL DEFAULT '',

    created_at            timestamptz NOT NULL DEFAULT now(),
    published_at          timestamptz,
    retracted_at          timestamptz,
    retraction_reason     text NOT NULL DEFAULT '',

    CONSTRAINT a_version_is_ordered CHECK (ordinal > 0),
    CONSTRAINT a_content_digest_is_thirty_two_bytes CHECK (octet_length(content_digest) = 32),
    CONSTRAINT a_version_states_its_vertical_datum CHECK (vertical_datum <> ''),
    CONSTRAINT a_version_states_a_real_projection CHECK (crs_epsg > 0),
    CONSTRAINT a_version_states_its_rights CHECK (rights <> ''),
    CONSTRAINT a_version_states_its_attribution CHECK (attribution <> ''),
    CONSTRAINT time_runs_forwards CHECK (observed_to >= observed_from),
    CONSTRAINT a_measured_uncertainty_carries_a_number CHECK (
        (uncertainty_kind IN ('absolute_metres', 'relative_fraction')) = (uncertainty_value IS NOT NULL)
    ),
    CONSTRAINT a_described_uncertainty_carries_a_description CHECK (
        uncertainty_kind <> 'described' OR uncertainty_note <> ''
    ),
    CONSTRAINT exactly_one_producer CHECK (
        (producer_job_id IS NOT NULL) <> (producer_principal_id IS NOT NULL)
    ),
    -- Anything that has left review carries the moment it was published, and
    -- keeps it: a retracted version was published once, and the record says so.
    CONSTRAINT a_published_version_records_when CHECK (
        (state IN ('draft', 'in_review')) = (published_at IS NULL)
    ),
    CONSTRAINT a_retracted_version_says_why CHECK (
        (state = 'retracted') = (retracted_at IS NOT NULL)
        AND (state <> 'retracted' OR retraction_reason <> '')
    )
);

CREATE UNIQUE INDEX one_ordinal_per_layer ON layer.version (layer_id, ordinal);
CREATE INDEX version_by_layer ON layer.version (layer_id, ordinal DESC);
CREATE INDEX version_by_state ON layer.version (state);
CREATE INDEX version_by_extent ON layer.version USING gist (extent);
CREATE INDEX version_by_time ON layer.version (observed_from, observed_to);

-- A version's payload is a manifest of objects, because a tileset or a survey
-- is many files. The manifest, sorted by path, is what content_digest covers.
CREATE TABLE layer.version_object (
    version_id    text NOT NULL REFERENCES layer.version (id),
    relative_path text NOT NULL,
    object_id     text NOT NULL REFERENCES store.object (id),
    PRIMARY KEY (version_id, relative_path),
    CONSTRAINT a_relative_path_is_portable CHECK (
        relative_path <> ''
        AND relative_path !~ '^/'
        AND relative_path !~ '(^|/)\.\.(/|$)'
        AND relative_path !~ '\\'
    )
);

CREATE INDEX version_object_by_object ON layer.version_object (object_id);

-- Lineage is the record of what a version was derived from.
CREATE TABLE layer.lineage (
    output_version_id text NOT NULL REFERENCES layer.version (id),
    input_version_id  text NOT NULL REFERENCES layer.version (id),
    PRIMARY KEY (output_version_id, input_version_id),
    CONSTRAINT nothing_derives_from_itself CHECK (output_version_id <> input_version_id)
);

CREATE INDEX lineage_by_input ON layer.lineage (input_version_id);
