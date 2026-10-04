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

**Phase 3 is done**, switched over on the box on 4 October with about a minute of downtime and no data moved:

- **Settings.** The Go services carry `CORAL_CITY_*` to `IOCEAN_*` at startup. The compose files, the box's `.env` (backed up as `.env.before-iocean-2026-10-04`) and the box tools say `IOCEAN_*`.
- **The platform.** It runs as the compose project `iocean` (containers `iocean-*`, images `iocean/*`), on the volumes it had (`coral-city_record`, `coral-city_registry`, `coral-city_credentials`), pinned by name.
- **The runtime.** The image is labelled `org.iocean.runtime`; the Kit app is `iocean.kit` and the extension `iocean.shell`, with Python package `iocean_shell`. Worker containers and networks are `iocean-*`.
- **Sign-in.** The session cookie is `iocean_session`, with `coral_session` still honoured; the auth realm is `iocean`.
- **Data folders.** `~/iocean` and `~/.config/iocean` on the Mac and on the box, each with a symlink from the old path.
- **The client.** It is named `iocean`, with appId `com.iocean.client`, and copies its settings across from the old "Coral City" folder once.
- **pip distributions.** `iocean`, `iocean-runtime` and `iocean-mcp`. The `coral-city` command still works.
- **The MCP server.** Its package is `iocean_mcp`, and it calls itself `iocean` at `https://jalalirs.tailedf721.ts.net/iocean/mcp`. `/coral` still answers beside it; nothing on the funnel was removed. `.mcp.json` names it `iocean`.
- **Brand files.** `iocean.*`. The loading picture says iocean and OCEAN ROBOTICS DIGITAL TWIN.

**Kept on purpose:**

- **The npm workspace scope `@coral-city/*`.** Renaming it means regenerating the lockfile with pnpm.
- **The client's saved-setting keys (`coral-city.place`, …).** Renaming them would forget your choices.
- **The format ids `coral-city/layout/v1` and `coral-city/mission/v1`.** They are written into stored records.
- **The Postgres role and database `coral`.**
- **`/var/lib/coral-city` on the box.** It is root's and unused, since the work folder is set in `.env`.
- **The `/coral` funnel path.** It stays so existing links keep working. It can go once nothing uses it, which needs `tailscale funnel --set-path /coral off` — your call, never `--https=443 off`.
