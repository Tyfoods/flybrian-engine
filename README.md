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

Historical Python experiments enter the public boundary through static envelopes, not by importing
or executing their scripts. An envelope binds exact source bytes/revision, declared and effective
options, controller stages, FES projection, artifacts, missing requirements, and lineage. Its
reproducibility class is derived: incomplete records remain `PROVENANCE_ONLY`; only complete,
validated records become `RUNNABLE_CONNECTOME` or `RUNNABLE_EMBODIED`.

The bounded AST extractor reads literal `argparse` declarations and config tables without imports,
function calls, filesystem access, or subprocesses. Dynamic facts become dispositions for manual
review. Exact variations require the base envelope hash and before-value, apply a visible patch,
then recompute FES validity and completeness.

```python
from flybrian_engine import (
    HistoricalSourceAuthority,
    extract_static_python_experiment,
)

source_bytes = historical_script.read_bytes()
source = HistoricalSourceAuthority(
    repository="https://example.org/research/fly-history",
    revision="0123456789abcdef0123456789abcdef01234567",
    logical_path="experiments/example.py",
    byte_length=len(source_bytes),
    sha256=source_sha256,
    license_id="MIT",
    access="public",
    redistribution="allowed",
    extractor_id="org.flybrian.static-python-extractor",
    extractor_version="1.1",
)
draft = extract_static_python_experiment(source_bytes, source)
print(draft.receipt.option_count, draft.dispositions)
```

The first reviewed historical profile is C174. It publishes all 56 declared controls and all 16
selector rows as inspectable facts. Resolution is pure: omitting the historical index expands into
16 independent manifests, while selecting one row preserves requested values, effective values,
selector overrides, null fallbacks, and known historical discrepancies. The resulting records stay
`PROVENANCE_ONLY` until their private dataset/connectivity, neural, body, environment, controller
executor, unit, and result authorities are supplied; a complete option form alone is not a rerun
claim.

```python
from flybrian_engine import resolve_c174_batch, resolve_c174_experiment

manifest = resolve_c174_experiment(
    7,
    {"--force-gain": "9", "--anti-boost": "1.5"},
    invocation=("--index", "7", "--force-gain", "9", "--anti-boost", "1.5"),
)
force = next(
    option for option in manifest.options if option.option_id == "c174.feedback.force_gain"
)
print(force.requested_value, force.effective_value, force.application)
print(manifest.envelope.reproducibility_class, manifest.envelope.missing_requirements)

all_historical_rows = resolve_c174_batch({"--seed": 42})
assert len(all_historical_rows) == 16
```

The resolver does not import the private script or allocate Brian2/MuJoCo state. The script remains
private and is not packaged; only original public resolution code and reviewed factual metadata are
published.

Before the larger historical estate enters the catalog, the public inventory boundary can hash and
classify an explicitly authorized corpus root without executing scripts or parsing result payloads.
Its canonical receipt contains only logical relative paths, sizes, hashes, deterministic media/role
hints, collection summaries, and declared root provenance. Physical paths, timestamps, usernames,
and file contents are excluded. `.DS_Store`, `.pyc`, and `__pycache__` entries become fixed,
canonical non-scientific exclusions; all other hidden or secret-bearing paths, symlinks,
nonportable names, races, and bounded-size violations fail closed.

```python
from pathlib import Path

from flybrian_engine import HistoricalEstateRoot, inventory_historical_estate

inventory = inventory_historical_estate(
    HistoricalEstateRoot(
        root_id="org.example.fly-history.snapshot",
        revision="reviewed-snapshot-2026-08-27",
        logical_root="fly-history",
        license_id="UNKNOWN",
        access="private",
        redistribution="prohibited",
        physical_root=Path("/reviewed/local/fly-history"),
    )
)
print(inventory.total_file_count, inventory.total_bytes, inventory.sha256())
```

Inventory is not import or reproducibility. It does not guess how many experiments exist, link a
script to an artifact, parse filename parameters, or make a private byte redistributable. The
reviewed projection boundary must add stable run/design identity, visibility, lineage, FES
completeness, and source-to-artifact edges before the controlled catalog importer can expose a
historical record.

That next boundary is the reviewed historical-estate projection. A projection names every design,
run, contributor, visibility decision, semantic envelope, source edge, and artifact disposition,
then validates each available file against the exact ordered inventory receipts. Admission also
requires the exact `HistoricalExperimentEnvelope` objects, so projection text cannot promote an
incomplete record to runnable. The strict JSON loader is bounded, duplicate-key rejecting, rejects
binary floats and unknown fields, and never reopens or parses an estate file.

```python
from flybrian_engine import load_historical_estate_projection_json

projection = load_historical_estate_projection_json(
    reviewed_projection_bytes,
    inventories=(experiment_inventory, output_inventory),
    envelopes=(reviewed_envelope,),
)
print(projection.sha256(), projection.import_sha256())
```

The import identity binds both the ordered inventory hashes and projection hash, making repeat
admission idempotent while preserving changed evidence as a new review decision. Directory names,
JSON key signatures, and filename-encoded parameters may help a human prepare a candidate, but are
never accepted as linkage authority.

The package includes one engineering-reviewed launch cohort for twelve historical FlyBrian
champions. It is a source-only provenance package: all records remain `PROVENANCE_ONLY`, every
missing execution authority is named, and result/video/motor-command artifacts have explicit
`unavailable` or `failed` dispositions. The package redistributes no private source or result
bytes. Four historical command aliases are resolved to their exact regular-file targets for
Windows portability, while the unresolved C161 selector remains explicitly unresolved.

```python
from flybrian_engine import load_bundled_reviewed_champions_export

catalog_export = load_bundled_reviewed_champions_export()
assert catalog_export.record_count == 12
assert all(
    record.reproducibility_class == "PROVENANCE_ONLY"
    for record in catalog_export.records
)
print(catalog_export.import_sha256, catalog_export.sha256())
```

`load_bundled_reviewed_champions_export()` validates the packaged bytes against the exact public
engine inventory, envelopes, projection, metadata checksums, and pinned export hash. Consumers may
transport those facts into a catalog, but must not reclassify runnability, infer artifact links, or
turn a repository path into a download URL. A later complete reconstruction is a new immutable
engine package/version; it does not rewrite this historical record.

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

Install the reviewed public v0.1.4 release on macOS or Linux:

```text
python3 -m venv .venv
.venv/bin/python -m pip install "flybrian-engine[brian2] @ https://github.com/Tyfoods/flybrian-engine/archive/refs/tags/v0.1.4.zip"
.venv/bin/flybrian-engine health
```

On Windows PowerShell:

```text
py -m venv .venv
.venv\Scripts\python.exe -m pip install "flybrian-engine[brian2] @ https://github.com/Tyfoods/flybrian-engine/archive/refs/tags/v0.1.4.zip"
.venv\Scripts\flybrian-engine.exe health
```

v0.1.4 preserves the selected virtual-environment interpreter boundary for locked historical
recipes. v0.1.3 added the immutable C174 minimal-champion definition, its exact historical input closure,
and locked standalone, local, and hosted execution recipes. v0.1.2 was a backward-compatible
schema patch for hosted and local consumers: an explicit
`embodied_config.mapping_id: null` now means that no named mapping is selected and is preserved
in canonical FES bytes. Missing values and non-empty mapping IDs retain their existing behavior;
empty strings and non-string values still fail validation before execution allocation. It also
uses explicit runtime-validated type narrowing across the supported mypy toolchain range. The
immutable v0.1.1 tag contains the same runtime schema behavior but failed its public typing CI and
must not be used as a verified service coordinate.

For an editable source checkout, use:

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
