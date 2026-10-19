-- A source holds several controllers.
--
-- A repository may list its controllers in an iocean.toml, or keep each in a
-- folder of its own, and one build now makes every one of them: each that
-- passes its tank check is registered, each that does not says why. So a
-- build registers a list of stacks, not one: [{slug, stackId}] for each
-- registered, [{slug, failure}] for one that passed and could not be.

ALTER TABLE catalog.controller_build ADD COLUMN stacks jsonb;
ALTER TABLE catalog.controller_build DROP COLUMN stack_id;
