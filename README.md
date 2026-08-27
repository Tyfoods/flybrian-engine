# flybrian-engine

`flybrian-engine` is the open scientific boundary of FlyBrian. It owns the versioned
experiment contract, validation/canonicalization, simulator adapter interface, artifact
manifest, and cross-platform local-runner protocol. It deliberately excludes FlyBrian's
hosted UI, AI harness, accounts, tenancy, queues, autoscaling, billing, and abuse controls.

This alpha establishes the package and protocol boundary. Its built-in `reference` backend
is deterministic contract verification, not a biological simulator. Brian2/NEURON adapters
must register through the same interface and declare their scientific/version provenance.

## Install and verify

```text
python -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/flybrian-engine health
.venv/bin/flybrian-engine validate examples/minimal-experiment.json
.venv/bin/flybrian-engine run examples/minimal-experiment.json --output flybrian-runs
```

On Windows, use `.venv\Scripts\python.exe` and `.venv\Scripts\flybrian-engine.exe`.

Start the loopback runner with `flybrian-engine serve`. The command prints a bearer token
when one is not supplied. `GET /v1/health` is public; `/v1/capabilities` and `POST /v1/runs`
require that token. The default bind is `127.0.0.1`, never a public interface.

See [architecture](docs/architecture.md) for dependency and compatibility rules.
