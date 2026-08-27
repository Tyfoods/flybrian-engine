# flybrian-engine

`flybrian-engine` is the open scientific boundary of FlyBrian. It owns the versioned
experiment contract, validation/canonicalization, simulator adapter interface, artifact
manifest, and cross-platform local-runner protocol. It deliberately excludes FlyBrian's
hosted UI, AI harness, accounts, tenancy, queues, autoscaling, billing, and abuse controls.

This alpha establishes the package and protocol boundary. Its built-in `reference` backend
is deterministic contract verification, not a biological simulator. Brian2/NEURON adapters
must register through the same interface and declare their scientific/version provenance.

The optional `brian2` backend is the first real biological adapter. Its frozen offline oracle
covers public `lif.basic.v1`, `rate.first_order.v1`, and
`compartmental.passive_two.v1` definitions and emits standardized scientific results. It does
not yet claim public inter-model connections, MANC ingestion, or historical private-model
equivalence.

FES 1.0 accepts additive simulator-neutral descriptors for heterogeneous neuron models,
unit-bearing values or distributions, direct or muscle-mediated embodiment, backend/version
constraints, requested artifacts, resource hints, and namespaced extensions. See
`examples/heterogeneous-experiment.json` and `examples/direct-actuator-experiment.json`.
Validation proves that a document is well formed. Execution is a separate compatibility
decision: every backend reports its supported model families, embodiment modes, artifacts,
determinism, and whether it performs scientific execution. Unsupported combinations return
structured issues before allocating output.

Completed runs emit scientific artifact manifest 1.1. The manifest binds run/engine/backend,
canonical experiment hash, seed, and dataset identity to checksummed relative files. A
per-kind disposition distinguishes `available`, `unavailable`, and `failed`, so motor commands
can remain replayable when video rendering fails without inventing an MP4 URL.

## Install and verify

```text
python -m venv .venv
.venv/bin/python -m pip install -e '.[brian2]'
.venv/bin/flybrian-engine health
.venv/bin/flybrian-engine validate examples/minimal-experiment.json
.venv/bin/flybrian-engine run examples/minimal-experiment.json --output flybrian-runs
.venv/bin/flybrian-engine run examples/brian2-golden-experiment.json --backend brian2 --output flybrian-runs
```

On Windows, use `.venv\Scripts\python.exe` and `.venv\Scripts\flybrian-engine.exe`.
The base install remains useful without the optional extra: schema validation and the
`reference` backend continue working, while health reports `brian2` as `not_installed` with
the exact installation remedy instead of failing import or substituting reference output.

Start the loopback runner with `flybrian-engine serve`. The command prints a bearer token
when one is not supplied. `GET /v1/health` is public; `/v1/capabilities` and `POST /v1/runs`
require that token. The default bind is `127.0.0.1`, never a public interface.

See [architecture](docs/architecture.md) for dependency and compatibility rules.
The staged extraction and cross-platform acceptance contract is recorded in
[`FLYBRIAN_ENGINE_EXTRACTION_CONTRACT.md`](FLYBRIAN_ENGINE_EXTRACTION_CONTRACT.md).
The public biological execution and private-consumer cutover behavior is specified in
[`FLYBRIAN_E3_BRIAN_ADAPTER_CONTRACT.md`](FLYBRIAN_E3_BRIAN_ADAPTER_CONTRACT.md).
