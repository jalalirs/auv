"""The simulation runtime's own code: hydrodynamics, the dive, the controllers.

The modules import one another as top-level names, because inside the runtime
this directory is on the path. Anything importing them from outside should put
it there too — the SDK's tank does.
"""
