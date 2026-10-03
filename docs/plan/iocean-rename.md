# Renaming Coral City to iocean: scope, for approval

You said on 3 October 2026 that iocean replaces Coral City everywhere. The old name is in about 1,300 lines across about 300 files, and some of them are names other things depend on. So the rename goes in three phases, from no risk to real risk. Each phase is a separate yes.

| form | files | lines |
|---|---|---|
| `Coral City` (prose, UI) | 77 | 117 |
| `coral-city` (MCP server, paths, slugs) | 114 | 241 |
| `coral_city` (the Python SDK package) | 92 | 531 |
| `CORAL_CITY_*` (environment switches) | 66 | 462 |
| `coral.city` (the Kit extension) | 7 | 7 |

## Phase 1: what people read. No risk.

These are names only people see, and nothing depends on them:

- Prose and titles in docs and READMEs.
- The client and console apps' visible text.
- The MCP tools' descriptions and server instructions (but not the server's name).
- Place and vehicle summaries on the platform.

## Phase 2: names code uses, kept working under the old ones. Low risk.

- **The SDK.** `coral_city` becomes `iocean`, and a `coral_city` shim re-exports it, so controllers already written keep importing. The shim goes in a later release.
- **The `CORAL_CITY_*` switches.** They become `IOCEAN_*`. The runtime reads the new name first and the old one after, so existing tools and scripts keep working.
- **`tools/mcp-call` and the repo's own scripts** move to the new names.

## Phase 3: names outside the repository. Touches running systems; needs you.

- **The MCP server's name.** `coral-city` to `iocean`. Your Claude configuration names the server, so you would change one line there.
- **The Kit app and extension.** `coral_city.kit` and `coral.city.shell` become `iocean.kit` and `iocean.shell`, which means a runtime image rebuild.
- **Container and image names.** `coral-sim-run_*` and `sim-runtime:r1` on the box.
- **Data directories.** `~/coral-city/places`, `~/.config/coral-city`, and the box's equivalents become `~/iocean/...`, with a symlink from the old path so nothing breaks mid-move.
- **The public path.** The `/coral` path behind the Tailscale Funnel. This is not touched without an explicit yes, because the funnel's config must not be replaced.

## Not renamed

- **Git history and old commit messages.**
- **The repository name `auv`.**
- **Published package versions.** They are immutable; new versions carry the new name.

**Recommendation:** phase 1 now; phase 2 with the next runtime deploy; phase 3 when you choose a quiet hour, with you at the keyboard for the Claude configuration line and the funnel.
