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

Start the durable loopback runner with `flybrian-engine serve`. The command prints one
machine-readable connection record containing a process bearer token when one is not supplied.
The default bind is `127.0.0.1`; the only other accepted bind is IPv6 loopback `::1`.

`GET /v1/health` is the only unauthenticated endpoint. Authorized clients submit durable work
with `POST /v1/jobs`, reconnect with `GET /v1/jobs/{run_id}`, cancel with
`POST /v1/jobs/{run_id}/cancel`, and retrieve the validated manifest or a manifest-declared
artifact below that job. `--workers` and `--max-queued` provide explicit bounded concurrency.
The original synchronous `POST /v1/runs` remains temporarily available for protocol-1 alpha
compatibility.

Direct browser-origin and preflight requests are denied even when they carry a valid token.
FlyBrian must connect through a trusted same-origin server or a separately paired desktop
connector; a website cannot acquire local execution authority merely by reaching localhost.
Job records and outputs live under the user-selected `--output` directory, not the package
installation, so package update or uninstall preserves research data.

See [architecture](docs/architecture.md) for dependency and compatibility rules.
The staged extraction and cross-platform acceptance contract is recorded in
[`FLYBRIAN_ENGINE_EXTRACTION_CONTRACT.md`](FLYBRIAN_ENGINE_EXTRACTION_CONTRACT.md).
The public biological execution and private-consumer cutover behavior is specified in
[`FLYBRIAN_E3_BRIAN_ADAPTER_CONTRACT.md`](FLYBRIAN_E3_BRIAN_ADAPTER_CONTRACT.md).
The release-verified dataset normalization and explicit embodiment transformation behavior is
specified in
[`FLYBRIAN_E4_INGESTION_EMBODIMENT_CONTRACT.md`](FLYBRIAN_E4_INGESTION_EMBODIMENT_CONTRACT.md).
The durable lifecycle, security, portability, and cross-platform acceptance behavior is specified
in [`FLYBRIAN_E5_DURABLE_RUNNER_CONTRACT.md`](FLYBRIAN_E5_DURABLE_RUNNER_CONTRACT.md).
