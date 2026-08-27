# FlyBrian E3 Public Brian Scientific Adapter — OA Behavioral Specification

Status: **public v0.1.0 released; v0.1.1 compatibility patch in verification; mixed connections and private-consumer cutover open**

Parent authorities:

- `FLYBRIAN_ENGINE_EXTRACTION_CONTRACT.md`, segment E3 and acceptance ENG05/ENG08.
- The product-boundary, specification-design, and quality requirements restated in this document;
  proprietary planning documents are not required to interpret or verify the public contract.

Mutation authority is limited to this public repository until segment E3-D explicitly starts.
The private service is read-only source/provenance evidence before that segment. Maestro and
unrelated Reviewer/Implementor work have no mutation authority.

## 1. Correct-system outcome

A researcher installs the public Brian extra, selects the `brian2` backend, and executes a
supported FES document without FlyBrian's web product or cloud service. Backend discovery
truthfully distinguishes an unavailable optional dependency, an available but incompatible
experiment, and an accepted scientific run. An accepted run translates every supported
neutral scientific field into Brian units and dynamics, uses the declared seed and time step,
and emits a checksummed public artifact manifest containing standardized scientific results.

By E3 closure, one public adapter covers the declared LIF, rate, and compartmental golden
fixtures. The private service imports that released public schema/adapter/result authority,
and the corresponding active private duplicates are deleted in the same consumer migration.
Reference-backend output is never substituted for scientific output.

E3 is not complete when only a class exists, only one family runs, package tests pass without
the private consumer, or private code is copied but still authoritative.

## 2. Invariants

`INV-E3-PUBLIC-1`: public scientific execution imports no private service, web, account,
queue, billing, hosted storage, or hosted-rendering module.

`INV-E3-TRUTH-1`: `scientific_execution` is true only when Brian actually integrates the
accepted model. Missing Brian is `UNAVAILABLE`, unsupported science is `INCOMPATIBLE`, and a
runtime error is `FAILED`; none of these produce a completed scientific manifest.

`INV-E3-LOSSLESS-1`: every supported FES field is either applied, recorded as provenance, or
rejected before allocation. Unknown core scientific fields never disappear during adapter
translation. Namespaced extensions round-trip but cannot silently alter execution.

`INV-E3-UNITS-1`: neutral values become simulator quantities only through a declared unit
registry. Unknown units, dimension mismatches, booleans, non-finite values, or unsupported
distributions fail at their exact FES path before network construction.

`INV-E3-SEED-1`: canonical FES bytes, dataset checksum, engine/backend versions, seed, and
declared integration time step are sufficient to identify a deterministic attempt. Random
draw order is stable for a fixed accepted document and backend release.

`INV-E3-RESULT-1`: standardized results use global neuron identifiers, seconds for spike
times, explicit units for continuous series, deterministic ordering, and the manifest 1.1
identity/disposition contract. Simulator objects never cross the public JSON boundary.

`INV-E3-FAMILY-1`: LIF, rate, and compartmental are independently advertised capabilities.
Supporting one family does not authorize another, and a mixed document is accepted only when
every referenced model, connection, stimulus, recording, and artifact is supported together.

`INV-E3-DATASET-1`: a dataset ID without locally verified content is not sufficient to run a
dataset-backed experiment. Fixture networks may be fully embedded; external connectomes need
the checksum-bound ingestion contract delivered in E4.

`INV-E3-CUTOVER-1`: private-consumer migration is atomic at the capability boundary: consumer
tests use the public API, deployment packages the public distribution, and active duplicate
schema/adapter/result authority is removed. A local path dependency or vendored second copy is
not a released dependency and does not close E3.

`INV-E3-PLATFORM-1`: unmarked behavior is identical on supported macOS, Windows, and Linux.
Dependency absence and unsupported architecture are explicit capability states, not import
crashes.

## 3. Backend and run state machines

Backend states: `NOT_INSTALLED`, `LOADING`, `AVAILABLE`, `INCOMPATIBLE_RUNTIME`, `BROKEN`.

```text
engine discovery + Brian extra absent          -> NOT_INSTALLED
engine discovery + Brian extra present         -> LOADING
LOADING + version/platform accepted             -> AVAILABLE
LOADING + unsupported Brian/Python/platform     -> INCOMPATIBLE_RUNTIME
LOADING + import/self-check failure             -> BROKEN
NOT_INSTALLED + another backend selected        -> other backend flow (engine remains usable)
```

Scientific attempt states: `VALIDATING`, `COMPATIBILITY_CHECK`, `BUILDING`, `RUNNING`,
`SERIALIZING`, `COMPLETED`, `REJECTED`, `FAILED`.

```text
submit                              -> VALIDATING
VALIDATING + malformed FES          -> REJECTED (no run directory)
VALIDATING + valid FES              -> COMPATIBILITY_CHECK
COMPATIBILITY_CHECK + unsupported   -> REJECTED (structured paths; no run directory)
COMPATIBILITY_CHECK + supported     -> BUILDING (run identity allocated once)
BUILDING + translation/build error  -> FAILED (failure record; never completed manifest)
BUILDING + success                  -> RUNNING
RUNNING + integration error         -> FAILED
RUNNING + success                   -> SERIALIZING
SERIALIZING + verified artifacts    -> COMPLETED (manifest committed last)
SERIALIZING + artifact failure      -> FAILED (partial files remain non-completed evidence)
```

Completion is derived only from a committed, verified manifest. Directory presence, a zero
exit code without a manifest, or a service job label is not completion.

## 4. Neutral model behavior

### 4.1 Common behavior

- Each model definition has a stable ID, family, equation/provenance identifier, supported
  parameters with dimensions and defaults, integration method, and recording capabilities.
- Model-level parameters apply to every member. Per-neuron overrides replace only named
  supported parameters. A distribution is sampled once at the declared scope in canonical
  neuron-ID order.
- Inputs and connections reference global IDs. Missing, duplicated, cross-family-confused, or
  self-inconsistent identifiers are rejected before allocation.
- Simulation duration and time step use explicit time units. A final partial step is either
  rejected or represented by a declared policy; it is never silently rounded differently by
  platform.

### 4.2 LIF family

The public LIF fixture specifies membrane time constant, rest/reset/threshold potentials,
refractory duration, initial potential, and supported current or Poisson input. Threshold
crossings emit spikes, apply the declared reset/refractory behavior, and can record membrane
potential. Defaults are versioned model metadata, not implicit Brian defaults.

### 4.3 Rate family

The public rate fixture specifies state variable, time constant, transfer function, initial
value, and supported input. Continuous output is recorded with explicit time/value units.
`record_spikes` is rejected for a non-spiking rate model unless the selected model explicitly
defines an event conversion.

### 4.4 Compartmental family

The public compartmental fixture names every compartment and coupling edge, distinguishes the
spike-generating/recording site, and supplies morphology-independent electrical parameters.
Compartment inputs and recordings apply to the addressed compartment only. An absent or empty
compartment set, disconnected required compartment, invalid coupling, or unknown compartment
reference is rejected before allocation.

Dataset-derived morphology remains E4; E3's golden compartmental network is fully embedded and
small enough to run offline.

### 4.5 Mixed-family behavior

A mixed accepted fixture may connect supported family outputs to compatible family inputs.
Connection semantics, delay, weight dimension, and sign are explicit. The adapter rejects a
mixed network if any connection requires an undeclared conversion (for example, rate value to
spike event) rather than guessing one.

## 5. Derived state declarations

`DERIVED: brianBackendAvailability`

- Source: optional package presence, imported Brian version, Python/platform compatibility,
  and startup self-check.
- Missing package: `NOT_INSTALLED` with install guidance.
- Import returns `null`/missing version: `BROKEN`, not available.
- Installed but version outside the declared range: `INCOMPATIBLE_RUNTIME`.
- Only a successful self-check becomes `AVAILABLE`.

`DERIVED: supportedModelFamilies`

- Source: adapter release registry entries that have passing scientific golden tests.
- An absent entry is unsupported. An empty registry advertises no scientific families.
- A placeholder, private-only model key, or namespaced extension does not add a family.

`DERIVED: runDeterminism`

- Source: model/integrator capability, fixed seed, deterministic input corpus, and backend
  guarantee.
- Missing seed, unverified external dataset checksum, or nondeterministic implementation makes
  the value false. It is never inferred from a successful repeated sample alone.

`DERIVED: standardizedResultsAvailable`

- True only after the result file exists, matches its manifest size/checksum, parses against
  the public result schema, and has an `available` disposition.
- Missing/undefined manifest means unknown. A failed disposition means failed. An unavailable
  disposition means intentionally unavailable. These values do not collapse to false.

## 6. Scientific result contract

The standardized-results artifact contains:

- schema version and the same immutable run/FES/backend identity as the manifest;
- exact simulated duration, integration time step, seed, and dataset references;
- global neuron and model identity;
- spike events sorted by `(time_seconds, neuron_id)`;
- recorded continuous series with variable name, source neuron/compartment, unit, sample times,
  and finite values;
- network counts and bounded scientific warnings;
- provenance for model definitions and integrator.

Empty spikes are a valid available result. Missing requested recordings are not represented as
empty arrays: they reject admission, fail serialization, or receive an explicit non-available
disposition according to whether the request was unsupported or execution failed.

Raw Brian monitor/network objects are optional in-process diagnostics only and are not pickled
as a portable public artifact.

## 7. Entity lifecycle and conversion rules

### Backend registration

- Create/install: installing the Brian extra makes discovery eligible after self-check.
- Read: health/capabilities report availability, version, families, artifacts, determinism, and
  scientific-execution truth.
- Update: changing Brian or engine version re-runs compatibility/self-check before admission.
- Delete/uninstall: removing the extra removes capability but never deletes experiments/runs.
- Publish: a package release advertises only families with current golden evidence.
- Unpublish: yanking a release does not mutate prior manifests; version constraints prevent new
  selection where configured.

### Scientific attempt

- Create: allocate only after validation and compatibility pass.
- Read: result and manifest are immutable completion evidence.
- Update: attempts are immutable; a changed parameter or backend creates a new attempt.
- Delete: removing an output is explicit and never deletes the source experiment.
- Publish/share: hosted visibility is private-platform metadata and cannot alter checksums.
- Unpublish/private: visibility changes do not alter scientific identity.

### Conversion

- Legacy scalar parameters convert only through a named compatibility rule whose assumed unit
  is versioned and visible. Ambiguous scalars reject; the adapter does not infer from magnitude.
- A point LIF model does not become a compartmental model by adding a `compartments` object; the
  model family and complete required parameters must change together.
- Rate-to-spike and spike-to-rate connections require explicit versioned conversion semantics.
- Switching from private legacy execution to the public adapter creates the same FES identity
  and a new attempt with public engine/backend provenance; historical result bytes are not
  relabeled as public-engine output.

## 8. Edge-case resolution

| Category | Required behavior |
| --- | --- |
| Ownership/permissions | Public engine has no account authority; filesystem permissions fail without privilege escalation or path escape. Hosted ACL stays private. |
| Empty network | Reject before allocation; a zero-spike nonempty network is valid. |
| Missing optional dependency | Engine schema/CLI/reference backend remain usable; Brian capability reports install guidance. |
| Version conflict | Reject with installed and required versions; do not auto-downgrade or select another backend. |
| Unknown model/parameter/unit | Structured incompatibility/validation at the exact path; no ignored dictionary entries. |
| Unsupported recording | Reject before allocation; do not emit a plausible empty recording. |
| External dataset missing | Reject with dataset ID and expected checksum; never substitute fixture/default data. |
| Partial output/disk full | Attempt fails; no completed manifest. Existing verified artifacts may be retained as failed-attempt evidence. |
| Duplicate run ID | Reject without overwriting. |
| Concurrent runs | No global Brian clock/seed/device state may leak between attempts; until isolation is proven, bounded concurrency is one scientific run per process. |
| Cancellation | Durable cancellation is E5; a synchronous E3 process interruption cannot claim `CANCELLED` unless termination is confirmed. |
| Deletion | Uninstall/update preserves output roots; explicit run deletion targets one validated run ID. |
| Platform divergence | Same fixture ordering/schema/hash everywhere; unsupported native dependency is named, not hidden behind reference output. |

## 9. User-facing and protocol text

The public CLI/protocol uses these stable primary messages:

- Missing extra: `Brian2 backend is not installed. Install flybrian-engine[brian2].`
- Version mismatch: `Installed Brian2 version is incompatible with this engine release.`
- Unsupported science: `Experiment is incompatible with the selected backend.`
- External corpus missing: `Required dataset is not installed or its checksum is unverified.`
- Successful terminal state: `completed` only after manifest commit.

Structured codes and paths accompany text. Private UI may present friendlier copy while retaining
the code/path and may not turn a rejection into a runnable state.

## 10. Stakeholder-confirmed scenarios

These scenarios derive directly from the confirmed parent scenarios S5 and S7 and the approved
open-scientific-core boundary.

### E3-S1 — Offline scientific fixture

1. Researcher installs the public engine with the Brian extra on a supported computer.
2. Health reports a real `brian2` backend and supported family list.
3. Researcher validates and runs a fully embedded deterministic fixture while offline.
4. A manifest and standardized results are produced with scientific execution true.
5. Repeating the attempt with the same versions/seed matches the declared golden oracle.

### E3-S2 — Heterogeneous supported execution

1. Researcher selects a document containing LIF, rate, and compartmental models.
2. Compatibility inspects every family, connection, stimulus, recording, and requested artifact.
3. If the full combination is supported, Brian runs it and standardized results retain all
   identities and units.
4. If any conversion is not declared, the entire attempt rejects before allocation.

### E3-S3 — Truthful unsupported environment

1. Researcher installs the base package without Brian, or on an unsupported dependency version.
2. Schema validation and the reference contract backend continue to work.
3. Brian health explains the exact unavailable state and install/version remedy.
4. Submitting to `brian2` creates no scientific run directory and never executes `reference`.

### E3-S4 — Private service cutover

1. Hosted admission validates with the released public engine.
2. A supported cloud attempt invokes the same public adapter used locally.
3. Hosted storage decorates but does not rewrite the public manifest identity/checksums.
4. The source census shows the superseded private schema/adapter/result authority deleted.
5. Existing compatibility routes continue through explicit public conversion rules.

## 11. Source census and deletion forecast

The paths below are provenance/constraint records, not an instruction to bulk-copy.

| Current private source | Present role | E3 treatment |
| --- | --- | --- |
| `flybrian/spec/v1.py`, `serialize.py`, `validate.py` | legacy FES dataclasses/defaulting/validation | Freeze compatibility specimens; public neutral schema remains canonical; move only necessary explicit conversion rules, then delete active private admission authority in E3-D. |
| `flybrian/spec/models.py` | metadata mixed with Brian equation/profile imports | Extract licensed simulator-neutral provenance and parameter declarations; Brian equations/units live behind the public optional adapter. |
| `flybrian/spec/compat.py` | legacy enhanced/web conversions | Inventory every field and fail on lossy conversion; retain a thin private web DTO adapter only if it contains no scientific defaults. |
| `flybrian/adapters/base.py` | legacy adapter/result interface | Replace consumers with public backend and standardized artifact contracts. |
| `flybrian/adapters/brian2_adapter.py` | wrapper over private mixed network path | Establish independent public golden path; do not copy its private dependency closure blindly. |
| `flybrian/helpers/mixed_network_utils/*` | active heterogeneous construction/execution | Extract in measured LIF/rate/compartmental slices with dependency/license census and sensitivity tests; E3 closes only when the declared golden path is public. |
| `flybrian/janelia/*` | dataset acquisition/morphology | Read-only dependency boundary in E3; move under E4 with dataset/license/checksum contract. |
| `flybrian/digifly/*` | scientific mapping mixed with physics/rendering | Read-only dependency boundary in E3; move transforms under E4, keep hosted renderer private. |
| `flybrian/server/api.py`, `jobs.py`, `simulation_interface.py` | private HTTP/queue/control plane | Remain private; switch scientific imports and manifest handling in E3-D without moving tenancy/operations. |

Before E3-D mutation, a fresh import/reference census must name every live consumer and all
unrelated dirty files. Deletion is limited to proven superseded authority; historical scripts
and provenance are not deleted merely to make the census smaller.

## 12. Segmented execution and acceptance

### E3-A — Frozen scientific oracle and adapter boundary

- Freeze fully embedded LIF, rate, compartmental, and mixed specimens plus expected normalized
  results from an independently reviewed authority.
- Record model equations/provenance, parameter/unit table, integration method/time step, Brian
  version range, deterministic claim, and per-output numerical tolerance before implementation.
- Define optional-dependency discovery so base-package import remains clean without Brian.

Acceptance: pre-change tests fail because `brian2` is absent; malformed units/model fields and
missing dependency reject without allocation. No biological execution is claimed.

### E3-B — Public biological execution

- Deliver LIF first, then rate, then compartmental, then their declared mixed connection path.
- Each family is advertised only after its own golden and sensitivity evidence passes.
- Emit standardized results and manifest dispositions; prove repeatability and unsupported-field
  rejection through Python, CLI, and loopback HTTP.

Acceptance: exact discrete identities/counts; time events within one declared integration step;
continuous values within a predeclared absolute/relative tolerance. Any performance target is
set after baseline with target/soft/hard bands (hard limit no tighter than 20% above target).

### E3-C — Package and platform evidence

- Package Brian as an optional extra with compatible version bounds and truthful metadata.
- Base wheel and Brian wheel environments both pass clean installs; uninstall preserves a
  separately targeted output root.
- Run source/lint/strict typing/tests/build/clean-wheel/sensitivity gates. CI covers the three OS
  definitions, while real platform runtime evidence remains required by E5/E6.

### E3-D — Released private-consumer migration

- Requires an actual publication coordinate or approved immutable package source; no local path
  fiction and no vendored duplicate.
- Add private-service integration tests for accepted, invalid, incompatible, execution-failed,
  and completed-manifest paths.
- Switch every named scientific consumer, prove hosted packaging, then delete superseded active
  duplicates in the same reviewed migration.

E3-D is externally blocked until the public repository/package publication authority exists.
That blocker does not authorize a fake dependency and does not block E3-A through E3-C source
work.

## 13. Acceptance ledger

| ID | Oracle | Status |
| --- | --- | --- |
| E3-01 | Specification describes behavior, invariants, states, derivations, lifecycle, edge cases, scenarios, parity, and segmented gates | PASS — this document |
| E3-02 | Golden equations/fixtures/tolerances frozen before adapter implementation | PASS — independent analytic oracle and per-output tolerances |
| E3-03 | Base install remains usable and reports missing Brian truthfully | PASS — clean base wheel health/reference run and pre-allocation rejection |
| E3-04 | Public LIF execution and standardized result golden | PASS — six events under per-cycle quantization oracle |
| E3-05 | Public rate execution and standardized result golden | PASS — analytic 10/20/50 ms checkpoints |
| E3-06 | Public compartmental execution and standardized result golden | PASS — analytic soma/dendrite 10/20/50 ms checkpoints |
| E3-07 | Declared mixed-family connection path | OPEN |
| E3-08 | Python/CLI/HTTP pre-allocation incompatibility and runtime failure behavior | PARTIAL — accepted Python/CLI/HTTP and missing-dependency rejection pass; injected runtime failure/partial-output oracle remains open |
| E3-09 | Manifest 1.1 standardized-results identity/checksum/disposition | PASS — public result validator plus verified artifact/disposition |
| E3-10 | Base/Brian package, lint, typing, test, build, clean-install, and mutation gates | PARTIAL — macOS and three-OS CI definition pass; real Windows/Linux runtime remains E5/E6 |
| E3-11 | Released public package consumed by private service | PARTIAL — immutable v0.1.0 tag exists; v0.1.1 service pin and production-consumer evidence remain open |
| E3-12 | Superseded private authority removed after consumer proof | OPEN — deletion requires verified v0.1.1 consumer migration |
| E3-13 | Optional embodiment mapping has an explicit absent/null/nonempty/invalid value-domain contract | PASS in 0.1.1 source candidate — isolated v0.1.0 negative control rejects null; preservation and six invalid-domain cases pass in the 271-test suite |
| E3-14 | Strict typing passes on the current supported mypy release without hiding failures behind a checker cap | PASS in 0.1.1 source candidate — mypy 1.20.2 checks all 41 source/test files with no issues; focused runtime guard oracles remain green |

## 14. Principles compliance review

| Principle | Application |
| --- | --- |
| Behavioral over defect list | Sections 1–10 specify the correct public scientific system. |
| State machines | Section 3 defines backend and attempt states/transitions. |
| Scenario co-creation | Section 10 concretizes already confirmed parent scenarios; new scientific choices update this spec first. |
| Invariants first | Section 2 constrains every segment. |
| Platform parity | Invariant and edge table make cross-platform behavior the default. |
| Derived state/full domains | Section 5 distinguishes missing, null/broken, empty, unavailable, failed, and available. |
| Edge enumeration | Section 8 covers permission, empty, dependency, version, data, disk, concurrency, cancellation, deletion, and platform cases. |
| Conversion completeness | Section 7 specifies scalar/model/connection/private-public conversions. |
| Navigation | No graphical navigation exists; CLI/protocol terminal destinations are specified by the attempt state machine. |
| User-facing text | Section 9 freezes primary public messages. |
| What over how | Code paths appear only as provenance/deletion constraints; outcomes remain implementation-independent. |
| Quantitative tolerance | Section 12 requires predeclared scientific tolerances and target/soft/hard performance bands. |
| CRUD lifecycle | Section 7 covers backend registration and attempt lifecycles. |
| Element-level parity | Capability fields and standardized-result elements are enumerated rather than called “equivalent.” |
| Integration gates | E3-B requires Python/CLI/HTTP; E3-D requires private-service happy/error/completion tests. |
| Context-bounded segmentation | Four sequenced segments, each below 20 phases. |

## 15. Change control

- A stakeholder correction updates this specification first and reopens affected ledger rows.
- A scientific assumption lacking source/evidence is marked open; it is not encoded as a default.
- Each segment receives a pre-change oracle, production forecast, mutation/sensitivity check,
  contract-to-diff review, clean commit, and honest non-claims.
- E3 completion cannot close parent launch acceptance A17–A20; local/cloud equivalence, durable
  runner lifecycle, cross-platform runtime, and production rehearsal remain later segments.

## 16. E3-A / first E3-B quality evidence — 2026-08-26

- Pre-change focused tests failed because named compartments, explicit simulation/stimulus
  dimensions, registered Brian capabilities, and biological execution did not exist.
- `docs/brian2-golden-models.md` freezes equations, units, integration settings, analytic
  checkpoints, and tolerance bands independently of adapter output. The one implementation
  discovery—per-cycle event quantization—updated the oracle to constrain first-event and every
  inter-spike interval rather than allowing accumulated absolute-phase error.
- One offline FES attempt executes LIF, rate, and passive two-compartment models through real
  Brian 2.10.1. It emits six LIF spikes, the analytic rate/voltage checkpoints, and a validated
  standardized-results artifact under manifest 1.1 with `scientific_execution: true`.
- Base-package discovery imports no Brian, reports exact `not_installed` guidance, keeps schema
  and reference execution usable, and rejects a Brian submission before output allocation.
- Python, CLI, and authenticated loopback HTTP produce the same experiment identity and public
  disposition. Fixed release/seed repeats produce equal normalized result content after run ID
  normalization.
- 54 tests pass. Ruff and strict mypy pass across 16 source/test files. Wheel/sdist build; the
  source distribution contains this contract, the oracle, and the fixture. Clean base and Brian
  wheel installs pass; uninstall leaves the completed run manifest in place.
- Mutation evidence: skipping only the `tau_m` dimension guard makes exactly the targeted
  malformed-unit oracle fail while the other three boundary cases remain green.
- Not claimed: public connection semantics, MANC/FlyWire ingestion, historical private-model
  numerical equivalence, runtime failure/partial-output normalization, private service cutover,
  package publication, Windows/Linux runtime evidence, or local/cloud equivalence.

## 17. v0.1.1 hosted-embodiment compatibility and current-toolchain addendum

This addendum is an implementation contract for a backward-compatible public patch discovered
while wiring the released package into the private service. It does not authorize private service
workarounds and does not expand the public engine into hosted account, queue, or rendering logic.

### Behavioral and derived-state contract

`DERIVED: selectedEmbodimentMapping`

- Source: the optional `embodied_config.mapping_id` FES member.
- Missing member: no named mapping is selected; preserve the missing representation.
- Explicit `null`: no named mapping is selected; preserve explicit `null` in canonical bytes.
- Non-empty string: select that named mapping and preserve the string exactly.
- Empty string, whitespace-only string, boolean, number, array, or object: reject at
  `embodied_config.mapping_id` before compatibility checking or output allocation.
- The value does not select a backend. Backend selection remains the execution constraint's
  responsibility.

The state transition is deliberately small:

```text
FES input -> schema validation
missing/null/nonempty mapping_id -> VALIDATED (representation preserved)
invalid mapping_id               -> REJECTED (no run/output allocation)
```

The canonical private constructor currently emits `mapping_id: null`; therefore rejecting null
prevents an otherwise valid hosted FES from reaching either the explicit public or named legacy
backend. Converting null to omission in the private service would create a second canonicalization
authority and is prohibited.

### Test-trust and sensitivity record

| Invariant | Decisive oracle | Pre-change result | Sensitivity/negative control | Acceptance |
| --- | --- | --- | --- | --- |
| Null mapping is valid and preserved | `tests/test_schema.py::test_legacy_hosted_embodiment_preserves_null_mapping_selection` through public validation/canonical value | RED on v0.1.0 at `embodied_config.mapping_id` | Reverting the one validator condition reproduces the rejection | Focused and full source suite green on 0.1.1 source |
| Invalid mapping values still fail closed | Existing schema malformed-field parameterization plus empty-string companion | Preservation baseline green | Empty string/type mutations must remain rejected | Focused schema suite and full suite |
| Current strict typing accepts runtime-validated literals | `python -m mypy --no-incremental --cache-dir=/dev/null` over `src` and `tests` | RED on mypy 1.20.2: eight return-type failures in four existing deserializers | Existing invalid disposition/visibility/role/reproducibility tests fail if their runtime guards are removed | Current mypy, focused invalid-input tests, and full suite green |

### Intended authority, reuse, and change forecast

- Public schema validation remains the sole mapping value-domain authority; no service-side
  normalization, default, fallback, or duplicate validator is permitted.
- Existing deserializer runtime guards remain the literal-domain authorities. The typing slice
  only carries their already-validated values into declared `Literal` result types; it does not
  widen accepted values or add a second validator.
- Expected public production edits: `src/flybrian_engine/schema.py`, version metadata, and the
  four current-toolchain typing sites in `results.py`, `artifacts.py`,
  `historical_projection.py`, and `historical_corpus.py`.
- Expected test edits: the null-domain schema oracle and version/hash expectations caused solely
  by the 0.1.1 package identity. Existing invalid-input tests are retained as negative controls.
- Expected documentation edits: this contract, the parent extraction ledger, and README release
  coordinates. No scientific equations, backend compatibility claims, dataset authorities,
  runner lifecycle, or private code enter this patch.
- Release acceptance requires source tests, current Ruff, current strict mypy, package build,
  clean-wheel import/validation, real Brian golden smoke, immutable tag/archive checksum, and
  public CI. Service consumption remains a separate E3-D/SC ledger.

### Source-candidate verification receipt — 2026-08-27

- An isolated worktree at public v0.1.0 commit `4022fa3` rejects the canonical hosted specimen
  with `embodied_config.mapping_id must be a non-empty string`; this is the decisive RED control.
- The 0.1.1 source candidate passes 271 tests with pytest bytecode/cache writes disabled. The
  matrix includes missing, null, non-empty, empty, whitespace, boolean, numeric, array, and object
  mapping values.
- Ruff 0.16.4 passes `src` and `tests` with its cache disabled. Strict mypy 1.20.2 reports no
  issues across 41 files with incremental/cache output disabled.
- Wheel and source distribution build without dependency downloads. The isolated wheel import
  resolves from the disposable install root, reports engine 0.1.1, preserves explicit null, and
  reports the real Brian2 2.10.1 adapter.
- The wheel executes the public Brian golden FES, produces a scientific manifest and standardized
  results at engine 0.1.1, and emits exactly six spikes. The 174,421-byte wheel and 305,101-byte
  source distribution were removed after verification.
- Still open for release acceptance: immutable v0.1.1 tag/archive checksum and the public
  macOS/Windows/Linux CI result on that exact commit. Private service consumption remains open.
