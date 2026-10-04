# Renaming Coral City to iocean

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

## Where it stands, 4 October 2026

**Phase 1 is done.** Every name people read says iocean, with three things kept back on purpose:

- the Electron app's `setName`, which names the folder its settings live in;
- the dated result write-ups in `docs/results`;
- generated place outputs.

**Phase 2 is done.**
- **The SDK.** It is `iocean`. `coral_city` is a shim whose import hook answers every `coral_city.X` with the module `iocean.X` itself, so old controllers get the same classes, not copies. Both commands, `iocean` and `coral-city`, work.
- **The switches.** The runtime, the Kit extension, the SDK, the MCP server, `tools/look`, `fly-over`, `count-bias`, `mcp-call`, `publish` and `e2e` read `IOCEAN_*`. Each entry point gives any `CORAL_CITY_*` it is handed to the `IOCEAN_*` name, unless that is set, so the new name wins and the old one works.
- **The client.** Its dev settings read `VITE_IOCEAN_*` and `IOCEAN_UPSTREAM`, falling back to the old names.

**Phase 3, still to do, with you at the keyboard:**

- **The MCP server's name.** `coral-city` becomes `iocean`, in your Claude configuration, and the MCP Python package `coral_city_mcp` with it.
- **The box's deployment settings.** The `CORAL_CITY_*` names in `deployments/*/compose.yaml`, the box's `.env`, `tools/box`, `tools/uav`, `tools/matrix` and `tools/clear-check-data`, and the Go services' config readers. The worker still hands the runtime `CORAL_CITY_SEED`, `CORAL_CITY_BRIEF` and the model settings; the runtime carries them.
- **The image.** The `CORAL_CITY_RUNTIME` build argument and the `org.coralcity.runtime` label.
- **The Kit app and extension.** `coral_city.kit` and `coral.city.shell`.
- **Container names.** `coral-sim-run_*` and `coral-look`.
- **Data directories.** `~/coral-city/...` and `~/.config/coral-city`, with a symlink from each old path.
- **The client's data folder.** The Electron `setName`, with its settings moved across.
- **The pip distribution names.** `coral-city`, `coral-city-runtime` and `coral-city-mcp`.
- **The public path.** `/coral` behind the Tailscale Funnel; the funnel's config is never replaced.
- **File names.** `coral-city.svg` and `coral_city.png`.
