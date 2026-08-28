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
    just contracts-current

# Run every component's tests.
test:
    go -C services/control-plane test ./...
    go -C services/worker test ./...
    pnpm --recursive --if-present test

# Format the Go sources in place.
format:
    gofmt -w services/control-plane services/worker

# Regenerate the client from the contract.
contracts:
    pnpm --filter @coral-city/client run generate

# Fail if the generated client has drifted from the contract.
contracts-current:
    #!/usr/bin/env bash
    set -euo pipefail
    before=$(shasum -a 256 packages/client-ts/src/schema.d.ts | cut -d' ' -f1)
    pnpm --filter @coral-city/client run generate >/dev/null
    after=$(shasum -a 256 packages/client-ts/src/schema.d.ts | cut -d' ' -f1)
    if [ "$before" != "$after" ]; then
        echo "the generated client is out of date; commit the result of: just contracts"
        exit 1
    fi

# Build and start the whole local platform.
run:
    docker compose -f {{compose}} build control-plane web worker
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

# Stand up the platform's daily loop against a running deployment.
daily-loop:
    ./tools/daily-loop

# Build the platform's workflow images.
workflows:
    ./tools/build-workflows

# Check a running deployment end to end.
e2e:
    ./tools/e2e

# Deploy to the GPU host and check it.
deploy-gpu:
    ./tools/deploy-gpu

# Commit and synchronize a reviewed change across Mac, GitHub, and the GPU host.
sync message:
    ./tools/gpu sync "{{ message }}"
