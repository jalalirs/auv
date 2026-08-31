-- A host says what physics it can run.
--
-- A run is required to record the runtime that produced it, because a physics
-- fix changes results and comparing across one has to be refused rather than
-- done quietly. That requirement was sound and half-built: the platform
-- insisted on the value and had no idea what the acceptable values were, so
-- whoever asked for a dive had to invent a string and hope it matched what the
-- host would actually run. An application cannot invent that, and should not:
-- it is a fact about a machine in a rack, not about the person diving.
--
-- So the machine says it. An agent already asks for work by naming the host it
-- speaks for; now it names what that host can run in the same breath, every
-- time, which means the answer cannot go stale while the host is alive.
--
-- Empty by default and empty is meaningful: a host that has never asked for
-- work has told us nothing about itself, and a queue of such hosts offers
-- nothing to run on. That is better than a default that is probably wrong.

ALTER TABLE exec.target
    ADD COLUMN runtimes text[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN exec.target.runtimes IS
    'What this host can simulate in, as it last reported when asking for work.';
