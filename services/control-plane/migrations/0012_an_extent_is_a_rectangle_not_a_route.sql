-- An extent is a rectangle on a map, not a path across a sphere.
--
-- Extents were stored as `geography`, which measures on the ellipsoid and so
-- has to decide which way round the world an edge goes. For an edge spanning
-- exactly 180 degrees of longitude — which is what the extent of a global layer
-- is — the two great-circle paths are the same length, and PostGIS rightly
-- refuses to guess: "Antipodal (180 degrees long) edge detected".
--
-- That refusal is correct, and the type was wrong. An extent says which
-- rectangle of latitude and longitude something covers. It is used to index and
-- to draw, never to measure a distance or an area, and as a planar geometry in
-- EPSG:4326 it represents the whole world exactly and unambiguously. Anything
-- that later needs a geodesic answer casts to geography deliberately, at the
-- point where the question is actually geodesic.

ALTER TABLE city.city
    ALTER COLUMN extent TYPE geometry(Polygon, 4326) USING extent::geometry;

ALTER TABLE layer.version
    ALTER COLUMN extent TYPE geometry(Polygon, 4326) USING extent::geometry;

-- The spatial indexes are rebuilt against the new type.
DROP INDEX IF EXISTS city.city_by_extent;
CREATE INDEX city_by_extent ON city.city USING gist (extent);

DROP INDEX IF EXISTS layer.version_by_extent;
CREATE INDEX version_by_extent ON layer.version USING gist (extent);
