# Packages

Versioned things that other areas depend on, and which depend on nothing.

| Package | What it is |
| --- | --- |
| `contracts/` | The API description. The source of truth for every shape. |
| `client-ts/` | The client generated from it. |

The dependency direction is one way and enforced: applications, services, and
workers depend on the contract, and the contract depends on none of them.
A conformance test in the control plane fails the build if the contract and the
routes actually served disagree.
