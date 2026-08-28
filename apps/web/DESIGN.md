# Web foundation design

- **Outcome:** let a user identify Coral City, understand the four product
  areas, and see whether the real control plane is connected.
- **Location:** `apps/web`.
- **Owned contract:** browser presentation and interaction state.
- **May call:** public control-plane HTTP APIs through same-origin paths.
- **Forbidden direct calls:** object storage, databases, containers, GPU hosts,
  robots, simulators, and scientific solvers.
- **Technology:** React and TypeScript built by Vite. They provide a small,
  browser-native application without a server-rendering platform dependency.
- **Data changed:** none. This foundation is read-only.
- **Deployment:** static assets served beside or in front of the control plane.
- **Evidence:** component tests for connected and disconnected states, a
  production build, and an end-to-end browser check in checkpoint 5.
- **Replacement:** platform calls and area definitions are isolated from visual
  components so a later application shell can evolve without changing APIs.

## Truthfulness rule

Until a product area has a real data contract and runtime, its screen explains
what will live there and explicitly reports that no source is connected. The UI
must not display invented reef records, user counts, forecasts, missions, or GPU
capacity.
