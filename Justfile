set dotenv-load := true
set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# Install the pinned repository toolchains and JavaScript dependencies.
setup:
    mise install
    pnpm install --frozen-lockfile

# Run every fast validation required before a commit.
check:
    git diff --check
    go -C services/control-plane vet ./...
    pnpm --recursive --if-present check

# Run all component test suites.
test:
    go -C services/control-plane test ./...
    pnpm --recursive --if-present test

# Build and start the complete local product runtime.
run:
    docker compose -f deployments/local/compose.yaml up --build

# Commit and synchronize a reviewed change across Mac, GitHub, and the GPU box.
sync message:
    ./tools/gpu sync "{{ message }}"
