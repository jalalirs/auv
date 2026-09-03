# Coral City

The application. It runs on your machine, signs in to a platform, and dives.

Nothing heavy is here: no CUDA, no ROS, no world data. A place is hundreds of
megabytes and stays on the machine with the GPU; what crosses to a laptop is
pixels and the keys you are holding down. That is the whole reason for a thin
client, and the moment any of the rest creeps onto a laptop the platform has
stopped being one.

## Running it

    mise exec -- pnpm --filter @coral-city/client start

Sign in with the address of a platform — your box's, over Tailscale — and the
account you were granted things under.

## Looking at it in a browser while building it

    CORAL_CITY_UPSTREAM=http://100.76.65.1:18080 VITE_CORAL_CITY_PLATFORM=http://localhost:5173 \
      mise exec -- pnpm --filter @coral-city/client exec vite --config vite.renderer.config.mts

The dev server forwards `/api` to the platform named by `CORAL_CITY_UPSTREAM`,
because a browser will not let a page on one origin call a platform on
another. The page then signs in to its own address. Without a preload bridge
the sea is read from Aqualink directly; everything else is as in the
application. `.claude/launch.json` has this ready for the in-app browser.

## Packaging it

    APPLE_TEAM_ID=… APPLE_ID=… APPLE_ID_PASSWORD=… \
      mise exec -- pnpm --filter @coral-city/client dmg

electron-builder is deliberately not a dependency of this workspace. It pulls a
subdependency from a git repository, which this repository blocks — a sensible
default that protects every install, and not one worth turning off for the whole
tree so that one packaging tool can be convenient. It is fetched on demand
instead, only when somebody is actually building a release.

Signing needs the team's Developer ID in a keychain and the notarisation
credentials in the environment. Without them the build still produces a working
application; it just is not one anybody else can open without being warned.

## How it is put together

    src/main        the process that owns the window: the icon, the window, and
                    the few things the window may ask it for (ipc.ts)
    src/main/ocean  Aqualink, read from here because the page cannot read a
                    third-party API from a file, and the site list is worth
                    caching on disk for a day
    src/shared      the bridge between the two, typed once for both sides
    src/renderer    the page: screens/ for each page, parts/ for what pages
                    share, platform/ for reading the platform and its packages,
                    ocean/ for the sea at a place, physics/ for what a vehicle's
                    numbers mean, catalog/ for what exists in this repository
                    but not yet on a platform — environments, vehicles, tasks

A picture on a card is a file in the thing's own package, fetched through the
platform's short-lived URLs, or there is no picture. A place's position, depth
and reef come from the site record in its package; a vehicle's physics from its
dynamics. The platform records packages and does not read them, so reading them
is this application's job, in `platform/packages.ts`.

## What it talks to

`@coral-city/api`, which is generated from the platform's contract. A route that
is renamed stops compiling here rather than failing in front of somebody.
