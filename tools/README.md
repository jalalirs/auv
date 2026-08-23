# Tools

These scripts are the supported human interface to the local/remote workflow.

| Command | Purpose |
| --- | --- |
| `gpu` | Run a GPU command, open a shell, or perform a verified Git sync |
| `doctor` | Check required local tools and remote capacity |
| `assets` | Verify and transfer external simulation assets over Tailscale |
| `git-sync` | Implementation used by `gpu sync`; GitHub + GPU mirror + checkout |
| `sync` | Compatibility alias for `gpu sync` |
| `sim` | Build and manage the remote Compose service |
| `view` | Manage the SSH tunnel used by Foxglove |
| `reef` | Build, run, view, and keyboard-drive the Stonefish Living Reef |

Configuration comes from environment variables documented in `.env.example`.
Synchronization never rewrites history or replaces an existing non-Git folder.
