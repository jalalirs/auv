# Packages

Versioned things that other areas depend on, and which depend on nothing.

| Package | What it is |
| --- | --- |
| `contracts/` | The API description. The source of truth for every shape. |
| `api/` | The TypeScript client generated from it, which the application uses. |
| `sdk-python/` | The controller SDK: write a controller for a catalogue vehicle, try it in a headless tank, deploy it as autonomy, fly it. |

The dependency direction is one way and enforced: applications, services, and
workers depend on the contract, and the contract depends on none of them.
A conformance test in the control plane fails the build if the contract and the
routes actually served disagree.
