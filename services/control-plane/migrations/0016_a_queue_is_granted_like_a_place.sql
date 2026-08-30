-- A queue is granted the way a city and a vehicle are.
--
-- The existing 'work' scope is the execution machinery as a whole — it is what
-- an agent holds authority over, and it names nothing, because there is only
-- one of it. A queue is not like that: there are many, each holds particular
-- hardware, and access to one says nothing about access to another. So it needs
-- a scope that carries an identifier.
--
-- The alternative was to reuse 'work' and filter afterwards, which would have
-- meant the decision point returning "yes" for hardware the caller cannot
-- actually use, and something further down having to disagree with it. One
-- place decides; this is what that costs when a new kind of thing appears.

ALTER TYPE policy.scope_kind ADD VALUE 'queue';
