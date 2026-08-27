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

Dataset manifest 1.0 provides the corresponding input boundary. It verifies safe relative paths,
byte size, SHA-256, CSV row count, schema identity, access, citation, license, and redistribution
status before streaming normalized connection or motor-anatomy records. Historical MANC exports
that contain exact integral scientific IDs or `.0` connection counts are parsed with Decimal—not
binary float—and preserve their original lexemes in provenance. Missing muscle targets remain
explicitly unknown for later mapping dispositions; they are never guessed.

Verified connection sources can be promoted into canonical NDJSON with an explicit normalization
profile and receipt. The initial MANC profile retains and counts self-edges, repeated pre/post
pairs, and conflicting non-null neuron annotations while preserving every source row. It does not
silently sum weights or select one annotation. A strict caller can instead choose rejection. A
temporary on-disk identity index keeps retained Python memory bounded;
only `connections.ndjson` plus its receipt are promoted, and the receipt is written last.

```python
from pathlib import Path

from flybrian_engine import (
    MANC_CONNECTION_NORMALIZATION_V1,
    normalize_connection_dataset,
)

result = normalize_connection_dataset(
    verified_dataset,
    MANC_CONNECTION_NORMALIZATION_V1,
    Path("normalized-manc"),
)
print(result.receipt.output_sha256)
```

Versioned embodiment profiles then convert normalized motor anatomy into either direct
neuron-to-actuator links or explicit neuron-to-muscle-to-actuator graphs. Actuator and muscle
identities are stable strings rather than array positions; direction, exact rational weights,
confidence, unit-bearing muscle parameters, and source-row provenance remain explicit. Unknown or
generic anatomy produces structured dispositions instead of guessed links. Canonical graph and
receipt hashes bind the exact dataset manifest, profile, and catalog content.

The package also publishes the pinned 78-actuator FlyBody catalog, FlyBrian's historical
90-entry experiment-vector catalog, and a complete named crosswalk between them. The crosswalk
maps 78 controls, explicitly aliases the two historical antenna names, and returns the 12 legacy
`tarsus3`/`tarsus4` values as explained drops. It never truncates a vector or treats an index as
scientific identity.

```python
from flybrian_engine import (
    FLYBODY_78_ACTUATOR_CATALOG,
    FLYBRIAN_HISTORICAL_90_ACTUATOR_CATALOG,
    FLYBRIAN_HISTORICAL_90_TO_FLYBODY_78,
    apply_actuator_crosswalk,
)

replay = apply_actuator_crosswalk(
    FLYBRIAN_HISTORICAL_90_TO_FLYBODY_78,
    FLYBRIAN_HISTORICAL_90_ACTUATOR_CATALOG,
    FLYBODY_78_ACTUATOR_CATALOG,
    tuple(str(value) for value in historical_motor_command),
)
print(replay.target_values, replay.drops)
```

The package separately publishes two deliberately distinct muscle authorities: the exact 15
left-foreleg parameter records in the pinned FlyMimic OpenSim model, and FlyBrian's historical
six-leg Hill approximation used by earlier walking experiments. The latter includes the rounded
90-muscle catalog, explicit MANC target bridge, named muscle-to-DOF projections, spike-count drive
conversion, and pure activation/force state transitions. It is labeled historical experimental
behavior, not official FlyMimic validation.

Two Hill profiles prevent a migration shortcut from becoming invisible. The bug-compatible
profile advances a multi-DOF muscle once per projection, exactly reproducing the historical loop;
the corrected profile advances it once using its primary DOF and then projects the resulting
torque. Both require exact catalog and projection hashes. Recorded motor-command artifacts remain
the stricter replay authority when they exist.

```python
from flybrian_engine import (
    FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG,
    FLYBRIAN_HISTORICAL_HILL_CORRECTED_PROFILE,
    FLYBRIAN_HISTORICAL_MUSCLE_DOF_PROJECTIONS,
    initial_historical_leg_states,
    step_historical_hill_leg,
)

profile = FLYBRIAN_HISTORICAL_HILL_CORRECTED_PROFILE
catalog = FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG
states = initial_historical_leg_states(profile, catalog, "T1_left")
frame = step_historical_hill_leg(
    profile,
    catalog,
    FLYBRIAN_HISTORICAL_MUSCLE_DOF_PROJECTIONS,
    "T1_left",
    states,
    drives={},  # omitted declared muscles receive explicit zero drive
    joint_states={
        "coxa_abduct": ("-0.038", "0"),
        "coxa_twist": ("0", "0"),
        "coxa": ("-0.131", "0"),
        "femur_twist": ("0", "0"),
        "femur": ("0.6", "0"),
        "tibia": ("-0.5", "0"),
    },
    dt="0.002",
)
print(frame.torques, frame.sha256())
```

FlyBody-derived metadata is redistributed under Apache-2.0 with the bundled license and
third-party modification notice. The runtime catalog has no MuJoCo dependency; the pinned XML and
MuJoCo compilation are development/acceptance authorities.

Official MANC v1.2.1 acquisition is available through the optional `neuprint` extra. It uses a
release-pinned, fixed-query adapter; keyset-paginates into fsynced staging files; verifies that the
provider snapshot did not change; and promotes only a manifest-verified dataset with a canonical
receipt. A token enters only through the transport constructor or
`NEUPRINT_APPLICATION_CREDENTIALS`; it is never written into the profile, journal, manifest, or
receipt. API-extracted CSV is explicitly recorded as a modified representation under CC BY 4.0.

```python
from pathlib import Path

from flybrian_engine import MANC_V121, NeuprintPythonTransport, acquire_neuprint_release

transport = NeuprintPythonTransport(MANC_V121)  # reads NEUPRINT_APPLICATION_CREDENTIALS
result = acquire_neuprint_release(MANC_V121, Path("manc-v1.2.1"), transport)
print(result.receipt.manifest_sha256)
```

Install the adapter with `python -m pip install 'flybrian-engine[neuprint]'`. Interrupted downloads
resume from their last durable keyset cursor. Reusing a promoted staging directory verifies and
returns the existing result without contacting NeuPrint. Live MANC acceptance still requires an
authorized Janelia token; offline scripted-transport tests prove the durability and credential
boundaries without fabricating live-provider evidence.

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
