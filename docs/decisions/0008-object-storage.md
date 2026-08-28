# ADR-0008: Object storage and immutability

- Status: Accepted
- Date: 2026-08-28

## Context

Scientific bytes must outlive the software that produced them, must be
addressable by content rather than by location, and must never be silently
overwritten. Observations are evidence; corrections are new versions.

Storage must be portable across a development workstation, an institutional
store, and a cloud provider without changing the domain.

## Options considered

1. Filesystem storage with a naming convention.
2. A domain-specific scientific data repository product.
3. S3-compatible object storage, content-addressed, with per-bucket rules.

## Decision

- Storage is S3-compatible. Development uses a self-hosted implementation on a
  dedicated, size-capped volume; institutional or cloud storage may be
  substituted without domain changes.
- Three buckets with different rules:

  | Bucket | Rule |
  | --- | --- |
  | `evidence` | raw observations. Write-once, versioned, never deleted or overwritten. |
  | `derived` | job outputs. Immutable per version; collectable only when unreferenced and unpublished. |
  | `ephemeral` | session scratch, tiles, previews. Time-limited. |

- Every object carries `sha256`, size, and media type. **The server verifies the
  digest on ingest and rejects mismatches.** The client is never trusted to
  describe what it uploaded.
- Objects are addressed by content: `<bucket>/<sha256[0:2]>/<sha256>`. The
  database holds meaning; the store holds bytes.
- Uploads use short-lived presigned grants issued only after an access
  decision.
- Publication is a governed transition: `draft → in_review → published →
  superseded`, or `→ retracted`. Retraction hides a version from default views
  and never deletes it or its lineage.
- Promotion of a contributed layer to canonical changes policy only. The object
  key, the digest, and the version are unchanged.
- Git stores contracts, migrations, recipes, manifests, checksums, and fixtures
  under one megabyte. Continuous integration enforces an added-file size cap
  and rejects known scientific binary formats.

## Consequences

- Deduplication is a property of content addressing rather than a feature.
- A corrupted or tampered upload cannot enter the record.
- Provenance survives storage migration, because identity is the digest.
- Deletion is deliberately hard, and storage growth becomes an operational
  concern requiring a retention decision of its own.
