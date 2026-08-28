-- A city is a bounded, curated, navigable place. It exists at the platform.
-- An organisation is granted access to a city; it never contains one, so the
-- record of a place survives the institution that funded the survey.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA city;

-- Discoverability and access are separate. Discoverability decides what a
-- principal with no binding may learn; access is decided by bindings.
CREATE TYPE city.discoverability AS ENUM ('listed_open', 'listed_locked', 'unlisted');

CREATE TABLE city.city (
    id               text PRIMARY KEY,
    slug             text NOT NULL UNIQUE,
    name             text NOT NULL,
    summary          text NOT NULL,
    extent           geography(Polygon, 4326) NOT NULL,
    crs_epsg         integer NOT NULL,
    vertical_datum   text NOT NULL,
    discoverability  city.discoverability NOT NULL DEFAULT 'unlisted',
    created_at       timestamptz NOT NULL DEFAULT now(),
    created_by       text NOT NULL REFERENCES identity.principal (id),
    CONSTRAINT city_slug_is_a_label CHECK (slug ~ '^[a-z][a-z0-9-]{0,61}[a-z0-9]$'),
    CONSTRAINT a_city_states_its_vertical_datum CHECK (vertical_datum <> ''),
    CONSTRAINT a_city_states_a_real_projection CHECK (crs_epsg > 0)
);

CREATE INDEX city_by_extent ON city.city USING gist (extent);
CREATE INDEX city_by_discoverability ON city.city (discoverability);
