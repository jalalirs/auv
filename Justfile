set dotenv-load := true
set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

# Install the pinned repository toolchains and JavaScript dependencies.
setup:
    mise install
    pnpm install --frozen-lockfile

# Run every fast validation required before a commit.
check:
    git diff --check
    pnpm --recursive --if-present check

# Run all component test suites.
test:
    pnpm --recursive --if-present test

# Start the local product once a runtime exists.
run:
    @echo "Coral City has no runtime yet; the control plane arrives in checkpoint 3."

# Commit and synchronize a reviewed change across Mac, GitHub, and the GPU box.
sync message:
    ./tools/gpu sync "{{ message }}"
