# FlyBrian Engine Extraction and Local Runner — OA Implementation Contract

Status: **active; E0 boundary bootstrap verified, E1 rich-schema compatibility admission next**

Canonical stakeholder intent: `/Users/tyroachford/Projects/flybrian-web-p14/FLYBRIAN_LAUNCH_PRODUCT_SPEC.md`, especially invariants 8–12, sections 9–12, scenarios S5–S7, and acceptance A15–A19.

Quality authority: `/Users/tyroachford/Projects/agent-harness/OA_ENGINEERING_PROTOCOL.md`.

Mutation authority: this public repository and explicitly forecast private-consumer changes only. Maestro has no mutation authority. Historical source in `flybrian-serve` is read-only until an extraction phase names exact files, tests the public replacement, switches every consumer, and deletes the private duplicate in the same reviewed migration.

## 1. Correct-system outcome

A researcher can install `flybrian-engine` on a supported desktop, validate or reconstruct a versioned experiment without FlyBrian’s hosted product, execute every backend that the installation truthfully reports, and receive a versioned, checksummed artifact manifest. The FlyBrian local runner and proprietary cloud service consume the same public schema, scientific adapters, ingestion logic, embodiment mapping, and artifact contract. Unsupported model, embodiment, or backend combinations fail before allocation with structured reasons. No consumer silently drops unknown scientific extensions or substitutes the deterministic reference backend for a biological simulator.

## 2. Ownership invariant

```text
public flybrian-engine
  owns: FES schema + migrations + validation + compatibility reports
        Janelia/FlyWire acquisition and normalization where licensing permits
        scientific model registries and simulator adapters
        neuron→muscle→actuator/direct-actuator embodiment transforms
        standardized scientific results and artifact manifest
        loopback runner protocol and cross-platform CLI

private flybrian-serve
  owns: authentication + tenancy + hosted admission + durable queues
        autoscaling + quotas + billing + abuse/security controls
        hosted credentials + artifact storage + operational rendering isolation

proprietary flybrian-web
  owns: interface + account/team UX + AI harness + local/cloud selection UX
  consumes: public versioned JSON contracts through a runner or private service
```

`INV-ENG-OWN-1`: public code never imports private service or web code.

`INV-ENG-OWN-2`: after a capability is extracted, private consumers import the released public API; they do not retain a forked scientific implementation.

`INV-ENG-OWN-3`: a package-boundary change is incomplete until consumer tests prove the new direction and a reuse/deletion census proves no active duplicate remains.

## 3. Scientific and schema invariants

`INV-ENG-SCHEMA-1`: canonical serialization is deterministic and unknown namespaced extension data round-trips byte-semantically through validate/load/save.

`INV-ENG-SCHEMA-2`: known numeric data rejects booleans, non-finite values, invalid ranges, and implicit unit coercion. Units are explicit in the schema or in a versioned model-parameter declaration.

`INV-ENG-SCHEMA-3`: the neutral experiment contract can represent LIF, rate, and compartmental populations; per-population/per-neuron overrides; connectivity and stimuli; direct-neuron→actuator and neuron→muscle→actuator modes; flybody/environment/controller; backend/version constraints; recording/artifact requests; resource hints; and namespaced extensions.

`INV-ENG-COMPAT-1`: schema validity and backend compatibility are separate. A valid experiment may be unsupported by an installed backend, but it is never relabeled invalid and never executed after an incompatible field is discarded.

`INV-ENG-COMPAT-2`: every backend reports its accepted spec versions, model families/types, embodiment modes, artifact kinds, deterministic guarantees, and backend version. Admission returns structured unsupported paths/codes before a run directory or hosted job is allocated.

`INV-ENG-EQUIV-1`: local and cloud execution of the same canonical spec, input checksums, engine/backend versions, and seed use the same public adapter and artifact schema. Numerical equality/tolerance is declared per backend/model before equivalence can pass.

## 4. Runner state machine

States: `STOPPED`, `STARTING`, `HEALTHY`, `INCOMPATIBLE`, `DISCONNECTED`, `STOPPING`, `FAILED`.

Run states: `VALIDATING`, `QUEUED`, `STARTING`, `RUNNING`, `CANCELLING`, `CANCELLED`, `FAILED`, `COMPLETED`, `OUTCOME_UNKNOWN`.

```text
STOPPED + serve                    -> STARTING
STARTING + bound loopback/token    -> HEALTHY
STARTING + bind/config failure     -> FAILED
HEALTHY + protocol mismatch        -> INCOMPATIBLE
HEALTHY + shutdown                 -> STOPPING -> STOPPED

HEALTHY + submit                   -> VALIDATING
VALIDATING + invalid/incompatible  -> terminal rejection (no run allocation)
VALIDATING + accepted              -> QUEUED -> STARTING -> RUNNING
RUNNING + committed manifest       -> COMPLETED
RUNNING + confirmed cancellation   -> CANCELLING -> CANCELLED
transport ambiguity after allocate -> OUTCOME_UNKNOWN; reconnect by durable run id
```

The current synchronous alpha endpoint is E0 evidence only. It does not satisfy the durable local run state machine.

## 5. Security and lifecycle invariants

- Bind to loopback by default; any non-loopback bind requires explicit unsafe acknowledgement and a separate threat review.
- Capabilities and run operations require a bearer token; tokens never appear in manifests, experiment specs, browser URLs, committed fixtures, or ordinary logs.
- Request bodies, identifiers, paths, extension depth/size, artifact counts, and outputs are bounded. Run IDs cannot escape the configured output root or collide silently.
- CORS/origin access is deny-by-default until the FlyBrian connector pairing protocol is specified. A browser must not gain runner authority merely because it can reach localhost.
- Update/uninstall never deletes user experiments or outputs. Data removal is an explicit, separately targeted action.

## 6. Extraction inventory and deletion map

| Public destination | Current private authority | Extraction rule |
| --- | --- | --- |
| `schema`, migrations, serialization | `flybrian/spec/{v1,validate,serialize,compat}.py` | Establish strict public fixtures first; switch service admission/imports; delete private schema duplicates only after full service tests. |
| model metadata and parameters | `flybrian/spec/models.py`, configuration registries | Split simulator-neutral metadata from Brian-unit implementation; preserve provenance; reject unlicensed/private data. |
| Brian adapter + standardized result | `flybrian/adapters/*`, mixed-network execution helpers | Extract dependency-closed modules in measured slices; golden scientific tests travel with the code. |
| dataset ingestion/normalization | `flybrian/janelia/*` | Record source license, release/checksum, download/cache/offline behavior, and deterministic normalized outputs before moving. |
| embodiment mapping | `flybrian/digifly/{mapping,neural_motor,muscle_model,...}.py` | Separate scientific transform from hosted MuJoCo/render operations; preserve direct and muscle-mediated modes. |
| artifact manifest | service result/motor/video payloads plus engine alpha manifest | Version one public superset; private storage supplies URLs without changing scientific identity/checksums. |
| local protocol/client pairing | engine alpha `runner.py`; web `/api/connect/*` | Add durable identity/capability/reconnect/cancel and a connector-mediated origin-safe handshake. |

No bulk copy is accepted. Every row requires a source census, dependency graph, license/data review, pre-change golden or sensitivity oracle, public implementation, private-consumer cutover, duplicate deletion, and contract-to-diff review.

## 7. Segmented execution

### E0 — Boundary bootstrap (verified locally)

- Independent MIT package, typed API, backend registry, deterministic reference backend, artifact checksums, CLI, authenticated loopback endpoint, macOS wheel/sdist, and three-OS CI definition.
- The reference backend is labeled contract-only and does not count as biological execution.

### E1 — Rich schema and compatibility admission

- Define additive FES 1.0 neutral descriptors for model family, parameter values/units/distributions, embodiment drive graph, backend constraints, artifact requests, resource hints, and namespaced extensions.
- Add LIF, rate, compartmental, direct-actuator, and muscle-mediated round-trip fixtures.
- Produce structured compatibility issues and prevent unsupported reference-backend allocation.
- Preserve accepted existing snake_case FES payloads and canonical hashes.

### E2 — Public scientific result/artifact contract

- Reconcile standardized spikes/topology, motor commands, metrics/logs, video/render status, provenance, and checksums into a versioned manifest.
- Prove malformed paths/checksums/counts fail closed and cloud URL decoration cannot change scientific identity.

### E3 — Brian schema/adapter extraction

- Move public FES models/validation/serialization, neutral model registry, Brian adapter, and a minimal dependency-closed execution path.
- Move golden LIF/rate/compartmental tests and declare numerical tolerances before comparing.
- Make `flybrian-serve` import the public package; delete active private duplicates.

### E4 — Ingestion and embodiment extraction

- Move licensed/scripted Janelia/FlyWire acquisition and normalized manifests with checksums.
- Move direct-actuator and muscle-mediated transforms plus motor-command artifacts.
- Keep hosted renderer isolation/storage/queueing private; optional local rendering remains public only if dependency/licensing checks pass.

### E5 — Durable cross-platform runner

- Versioned health/capabilities, durable jobs, status/reconnect/cancel, artifact retrieval, bounded concurrency, clean shutdown, update, and uninstall-preserves-data behavior.
- Connector-mediated pairing and origin controls; no token in URL/localStorage.
- Clean evidence on macOS Apple Silicon and supported Intel path, Windows 11 x64, and mainstream Linux x64. CI emulation is not substituted for missing platform execution evidence.

### E6 — Local/cloud consumer equivalence and release

- Same deterministic fixture through local runner and private control plane using one released engine version.
- Publish source, signed/tagged package artifacts, release notes, installation/data licensing documentation, security policy, and reproducibility examples.
- Web selects local only after a compatible handshake and consumes the same artifact manifest used for DigiFly replay.

## 8. E1 forecast and test-trust plan

Forecast production files: `src/flybrian_engine/schema.py`, `src/flybrian_engine/backends.py`, `src/flybrian_engine/runner.py`, `src/flybrian_engine/reference.py`, and package exports only if needed.

Forecast fixtures/tests/docs: additive heterogeneous examples, `tests/test_schema.py`, `tests/test_runner.py`, README/architecture updates.

Pre-change RED oracles:

1. LIF/rate/compartmental and direct/muscle specimens round-trip with explicit scientific descriptors and unknown namespaced extensions.
2. Malformed units/distributions/mappings/extensions fail at exact paths.
3. Compatibility reports unsupported model family and embodiment mode separately from schema validity.
4. Reference-backend incompatibility allocates no run directory through Python, CLI, or HTTP.
5. Existing minimal fixture hash and run manifest remain stable unless a separately approved migration declares otherwise.

Mutation/sensitivity evidence must show that removing each new validation or admission guard makes its oracle fail. Closure requires pytest, Ruff, strict mypy, wheel/sdist, clean-wheel install/CLI smoke, contract-to-diff, and a clean worktree commit. E1 cannot claim Brian execution, service consumption, publication, or Windows/Linux runtime evidence.

## 9. Acceptance ledger

| ID | Oracle | Status |
| --- | --- | --- |
| ENG01 | Independent public package has license/docs/build/test/typed API | PASS — local E0 commit `2dd9a2b`; publication pending separately |
| ENG02 | Heterogeneous FES data round-trips losslessly | OPEN |
| ENG03 | Structured schema/backend compatibility with no silent loss | OPEN |
| ENG04 | Public artifact contract spans results/motor/video/provenance | OPEN |
| ENG05 | Public Brian adapter reproduces declared golden fixtures | OPEN |
| ENG06 | Public ingestion reconstructs declared dataset releases/checksums | OPEN |
| ENG07 | Direct and muscle-mediated embodiment transforms are public | OPEN |
| ENG08 | Private service consumes released engine and duplicates are deleted | OPEN |
| ENG09 | Durable origin-safe local runner lifecycle | OPEN |
| ENG10 | macOS/Windows/Linux clean install and uninstall-preserves-data | PARTIAL — macOS alpha smoke and CI definition only |
| ENG11 | Local/cloud scientific equivalence under declared tolerance | OPEN |
| ENG12 | Public release/tag/package/docs/security evidence | OPEN |

This child contract may advance but cannot close the parent FlyBrian launch goal by itself.
