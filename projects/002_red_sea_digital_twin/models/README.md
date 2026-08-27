# Environmental model federation

Coral City integrates scientific models without embedding their source code or
internal data structures into Isaac Sim, ROS 2, or the web application.

Each model is represented by an adapter with the same lifecycle:

1. validate a versioned run request;
2. prepare model-native configuration and inputs;
3. execute in an isolated environment or submit to an external compute system;
4. preserve native outputs and logs;
5. translate selected results into a Coral City Environment Package; and
6. publish provenance, quality checks, uncertainty, and failure state.

## Stable boundary

Every adapter must eventually implement these operations:

- `describe`: model, version, license evidence, variables, grid, and limits;
- `prepare`: canonical request to model-native input files;
- `run`: local, container, HPC, or externally managed execution;
- `collect`: immutable native outputs, logs, and checksums;
- `normalize`: model output to the Environment Package contract; and
- `verify`: physical ranges, coordinates, time coverage, conservation checks,
  and comparison with available observations.

The shared Environment Package contains:

- site and scenario identifiers;
- issue time, valid time, calendar, and time zone;
- horizontal and vertical coordinate reference systems;
- gridded or trajectory variables with units;
- ensemble member and uncertainty metadata;
- spatial and temporal interpolation policy;
- source model, configuration, executable, and input checksums; and
- truth class: observed, derived, assimilated, forecast, synthetic, or
  experimental.

NetCDF or Zarr stores numerical fields. A small manifest stores lineage and
references those immutable arrays. Isaac Sim receives only sampled fields;
it never becomes the scientific archive.

## Directory shape

```text
models/
├── registry.yaml              # candidates, ownership, status, and licence review
├── README.md                  # federation rules and shared adapter contract
├── adapters/                  # one independently testable package per adopted model
│   ├── opendrift/
│   ├── swan/
│   └── ...
├── recipes/                   # pinned, reproducible build/run descriptions
├── fixtures/                  # tiny legal test inputs, never full data sets
└── validation/                # cross-model and observation comparison cases
```

Adapter directories are created only when a model is adopted. The upstream
solver remains external and pinned by version and checksum. Large inputs and
outputs remain in object storage, not Git.

## Adoption gate

A registry entry is not an installed dependency. A model becomes `adopted`
only after its licence has been independently verified, a reproducible build
exists, one tiny fixture passes, output normalization passes, and its scientific
role does not duplicate another adopted model without a documented reason.
