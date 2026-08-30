-- The catalogue of measurements is retired.
--
-- It described layers, versions, lineage and truth class: a real thing to want,
-- and not this platform. Nothing read it, nothing wrote to it, and no code
-- refers to it any longer. Keeping an unused schema alive would leave a second
-- account of what a place is, and the next person would have to work out which
-- one meant anything.
--
-- Dropped in dependency order rather than with a blanket CASCADE, so that
-- anything still holding a reference fails here — loudly, in a migration —
-- instead of being silently cut loose.

-- A job could declare that its result would become a layer version. Layers are
-- gone, so the declaration has nothing to name. The equivalent for a city or a
-- vehicle package will be built when something produces one.
DROP TABLE IF EXISTS exec.schedule_publication;
DROP TABLE IF EXISTS exec.publication;

-- Layer versions reference stored objects and the cities that contained them,
-- so they come out before either.
DROP TABLE IF EXISTS layer.lineage;
DROP TABLE IF EXISTS layer.version_object;
DROP TABLE IF EXISTS layer.version;
DROP TABLE IF EXISTS layer.layer;

DROP TABLE IF EXISTS city.city;

-- The triggers that protected the tables, and the types the columns were
-- declared with. Named one at a time rather than dropped with a blanket
-- CASCADE, so that anything unexpected still fails here instead of being
-- quietly swept away with them.
DROP FUNCTION IF EXISTS layer.protect_published_version();
DROP FUNCTION IF EXISTS layer.protect_manifest();
DROP FUNCTION IF EXISTS layer.enforce_truth_class_propagation();
DROP FUNCTION IF EXISTS layer.protect_lineage();

DROP TYPE IF EXISTS layer.uncertainty_kind;
DROP TYPE IF EXISTS layer.visibility;
DROP TYPE IF EXISTS layer.state;
DROP TYPE IF EXISTS layer.truth_class;
DROP TYPE IF EXISTS layer.kind;
DROP TYPE IF EXISTS layer.scope_kind;

DROP TYPE IF EXISTS city.discoverability;

DROP SCHEMA IF EXISTS layer;
DROP SCHEMA IF EXISTS city;

-- policy.scope_kind keeps its 'city' value: it now means a city in the
-- catalogue, and the bindings that use it are still the bindings that grant a
-- place. Postgres cannot remove one value from an enum in any case, and the
-- name was never wrong — only what it pointed at.
