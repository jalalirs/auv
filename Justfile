set dotenv-load := true
set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

compose := "deployments/local/compose.yaml"

# Show what can be run.
default:
    @just --list

# Install the pinned toolchains and locked dependencies.
setup:
    mise install
    pnpm install --frozen-lockfile

# Run every fast validation required before a commit.
check:
    git diff --check
    go -C services/control-plane vet ./...
    go -C services/worker vet ./...
    gofmt -l services/control-plane services/worker | (! grep .) || \
        (echo "the Go above is not formatted; run: just format" && exit 1)
    pnpm --recursive --if-present check
    just check-python

# Vet the Python: the simulation runtime, the SDK, and the tools.
#
# There was none of this until a `global` line was written above the variable
# it read, the runtime raised a NameError halfway through building the water,
# and a render sat at nought frames for a quarter of an hour with nothing in
# the log. Ruff finds that in a tenth of a second. The rules it runs are in
# ruff.toml and are the bug-shaped ones only; this codebase has its own voice
# and a linter is not going to improve it.
check-python:
    uvx ruff@0.14.0 check --config ruff.toml \
        services/sim-runtime packages/sdk-python tools apps

# Run every component's tests.
test:
    go -C services/control-plane test ./...
    go -C services/worker test ./...
    pnpm --recursive --if-present test

# Format the Go sources in place.
format:
    gofmt -w services/control-plane services/worker

# Build and start the whole local platform.
run:
    docker compose -f {{compose}} build control-plane worker
    docker compose -f {{compose}} up -d
    @echo
    @echo "Coral City is at http://localhost:${CORAL_CITY_WEB_PORT:-18090}"
    @echo "Sign in with ${CORAL_CITY_ADMIN_EMAIL:-admin@coral.local} / ${CORAL_CITY_ADMIN_SECRET:-development-secret}"

# Follow what the local platform is doing.
logs *services:
    docker compose -f {{compose}} logs -f {{services}}

# Stop the local platform, keeping the record and stored bytes.
stop:
    docker compose -f {{compose}} down

# Stop the local platform and discard everything it holds.
reset:
    docker compose -f {{compose}} down -v

# Check a running deployment end to end.
e2e:
    ./tools/e2e

# Commit and synchronize a reviewed change across Mac, GitHub, and the GPU host.
sync message:
    ./tools/gpu sync "{{ message }}"
