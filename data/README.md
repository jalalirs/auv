# Data boundary

This directory documents the local data layout; its heavy contents are ignored.
On the GPU box it is backed by `/home/jalalirs/auv-data` and mounted into the
container at `/data`.

Never rely on an unrecorded manual change inside a dataset. Store provenance,
checksums, generation commands, and schemas alongside experiments or manifests.
