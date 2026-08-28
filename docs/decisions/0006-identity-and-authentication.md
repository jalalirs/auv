# ADR-0006: Identity and authentication

- Status: Accepted
- Date: 2026-08-28

## Context

The platform serves institutions, their members, and non-human principals:
workers, edge stations, and vehicles. Institutional single sign-on will
eventually be required, but committing to a provider before the domain exists
would couple the product to a vendor prematurely.

Whether unauthenticated visitors may read the open world is difficult to change
later, because it determines whether authentication sits in front of or beside
the read path.

## Options considered

1. Adopt an external identity provider immediately.
2. Build a local credential system with no migration path.
3. Build a local provider behind an adapter boundary shaped for OIDC, and
   require authentication on every route.

## Decision

- Identity distinguishes **people**, **organisations**, and **service
  principals**. Workers, edge stations, and vehicles authenticate as service
  principals with their own credentials and role bindings.
- The first implementation is a local credential provider, isolated behind an
  adapter boundary shaped so that an OIDC provider can be introduced without
  changing the domain.
- **There is no anonymous read.** Authentication sits in front of every route,
  including the globe and the catalogue. There is no public rendering path.
- Sessions are short-lived and revocable. Service-principal credentials are
  scoped and independently revocable.
- Authentication establishes who is calling. It never decides what they may do;
  that is ADR-0005.

## Consequences

- No dual public and private read paths, no divergent caching, and no
  catalogue leak surface.
- Outreach or public-citation access, if wanted later, becomes a deliberate
  decision with its own record rather than an accident of the read path.
- Institutional single sign-on is a later adapter, not a rewrite.
- Every automated actor is identifiable in the audit record, because nothing
  acts without a principal.
