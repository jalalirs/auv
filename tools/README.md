# Tools

Human entry points for repository operations live here.

Currently preserved:

- `gpu`: connect to the GPU box and invoke synchronization;
- `git-sync`: commit, push to GitHub and the GPU mirror, and fast-forward the
  GPU checkout.

New commands require an approved workflow and must remain thin wrappers around
documented system behaviour.
