# Tools

The human entry points. Each does one thing and says what it did.

| Tool | What it does |
| --- | --- |
| `gpu` | Runs a command on the GPU host, or forwards its ports here (`gpu web`) |
| `git-sync` | Commits and synchronises a change across this machine, GitHub, and the GPU host |
| `deploy-gpu` | Builds for the GPU host's architecture, streams the images, migrates, starts, and checks |
| `build-workflows` | Builds the workflow images and reports their content identities |
| `daily-loop` | Stands up the recurring ingestion against a running deployment |
| `e2e` | Checks a running deployment end to end |

Most are reached through `just`; run `just` with no arguments to see what it
offers.

## Why images are streamed rather than pushed

The GPU host cannot reliably reach a package registry. `deploy-gpu` builds for
its architecture here and streams the result over the SSH connection that
already exists, and workflow images are named by their content identity —
`sha256:…` — rather than by a registry digest, so that work can name exactly one
image without a registry existing at all.

## Why `gpu web` forwards two ports

The application is reached on the first. Stored bytes are read and written
directly on the second, because a presigned URL is signed over its host and so
cannot be proxied through the first.
