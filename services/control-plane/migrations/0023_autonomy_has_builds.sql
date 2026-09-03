-- Autonomy has builds.
--
-- A stack's slug named exactly one image, and a second build of the same
-- controller had to be registered under another name — slug-v2, slug-v3 —
-- which is a version scheme nobody chose. The slug now names the controller
-- and each registration is a build of it: a new image digest, pinned as ever,
-- and the newest is what "the stack" means when a dive is asked for by name.
-- Dives pin a stack by id, so an old dive keeps the build it was defined with.

ALTER TABLE dive.autonomy_stack DROP CONSTRAINT IF EXISTS autonomy_stack_org_id_slug_key;
CREATE INDEX IF NOT EXISTS autonomy_stack_builds ON dive.autonomy_stack (org_id, slug, created_at DESC);
