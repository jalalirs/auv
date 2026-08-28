# Control plane

The future control plane owns identity and authorization, site and twin state,
missions and scenarios, workflow state, job state, simulator sessions,
publication state, and provenance.

It begins as a Go modular monolith with explicit internal boundaries. API style,
persistence technology, and production deployment have not been selected.
