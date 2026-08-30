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

## What it talks to

`@coral-city/api`, which is generated from the platform's contract. A route that
is renamed stops compiling here rather than failing in front of somebody.
