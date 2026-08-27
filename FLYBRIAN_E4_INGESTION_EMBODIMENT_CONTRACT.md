# FlyBrian E4 Public Ingestion and Embodiment Contract

Status: **specified; offline manifest/normalization implementation next**

Date: 2026-08-27

Parent authorities: `FLYBRIAN_ENGINE_EXTRACTION_CONTRACT.md` E4, ENG06–ENG07; FlyBrian launch
A15, A17–A19. Historical private sources are read-only discovery evidence, not code authority.

## 1. Outcome

A researcher can acquire a declared public connectome release, verify every input byte against a
portable dataset manifest, normalize the release into deterministic simulator-neutral neuron and
connection records, join motor-neuron anatomy to an explicit embodiment catalog, and reproduce
either neuron→actuator or neuron→muscle→actuator transforms locally. Every derived record retains
source release, source row identity, transformation version, and confidence/provenance. Missing or
ambiguous anatomy becomes a structured disposition; it never silently defaults to an extensor,
actuator, neurotransmitter, or model family.

This open boundary is the scrutable scientific logic. Hosted credentials, tenant storage, queues,
billing, private dataset mirrors, and FlyBrian UI remain outside it.

## 2. Discovery baseline

Read-only census of the historical private repository found:

- `manc:v1.2.1` connectivity split across three CSV files with 1,209,528 data rows;
- one 838-data-row motor-neuron/muscle table;
- historical NeuPrint fetchers and export pipelines;
- a private biological-prior generator that expands exit nerve + muscle target into Flybody
  actuator links, including a scientifically unsafe unknown-muscle positive-sign default;
- both direct firing-rate→actuator and experimental Hill muscle-mediated paths;
- public-engine FES already representing direct and muscle-mediated graphs.

These counts/checksums are migration evidence only. Dataset distribution and licensing must be
verified before any source bytes are bundled in the public repository or package.

## 3. Protected boundaries and non-goals

- No private dataset bytes, credentials, unpublished mappings, RL policy/template, MuJoCo asset,
  or cloud code are copied without explicit license and provenance approval.
- E4 does not claim that the connectome alone produces walking or that a mapping is biological
  truth merely because it is deterministic.
- E4 does not implement the Flybody renderer, hosted video, account sharing, or cloud execution.
- E4 does not infer unknown neurotransmitter sign, muscle action, left/right identity, or actuator
  direction. Unknown and conflicting source values remain explicit.
- Live NeuPrint acquisition is a separate adapter over the same manifest/normalization contract;
  offline verified fixtures land first.

## 4. Invariants

`INV-E4-RELEASE-1`: a dataset is identified by provider, dataset ID, release/version, and a
manifest hash. A label such as `manc:v1.2.1` without verified files is insufficient for execution.

`INV-E4-BYTES-1`: every admitted source file declares logical role, relative path, byte size,
SHA-256, media type, schema ID, and expected data-row count. Verification finishes before parsing.

`INV-E4-PATH-1`: manifest paths are normalized POSIX relatives; absolute, backslash, dot segment,
escape, symlink, duplicate path, and case-colliding entries are rejected.

`INV-E4-SCHEMA-1`: parsers require the exact versioned required-column set, reject duplicate
columns, preserve allowed additive columns in namespaced source metadata, and report row/file/field
for malformed values. Required values are never coerced from empty or non-finite input.

`INV-E4-STREAM-1`: large connectivity sources are streamed in deterministic manifest/file/row
order. Correctness does not require loading the 1.2-million-edge corpus into memory.

`INV-E4-IDENTITY-1`: normalized neuron IDs are non-negative provider identities represented as
integers; source row identity is `(logical_file, one-based data_row)`. Duplicate scientific keys
are rejected or resolved only by an explicit declared aggregation policy.

`INV-E4-CONNECTION-1`: normalized connections declare pre/post neuron IDs, non-negative integer
weight/count, source and target annotations where present, and source row provenance. Zero-weight,
self-edge, duplicate-edge, and neurotransmitter-conflict policies are explicit manifest/profile
choices rather than hidden parser behavior.

`INV-E4-PROVENANCE-1`: normalized output declares input manifest SHA-256, transformation profile
ID/version, engine version, record counts, dispositions, and output SHA-256. A consumer can prove
which exact source bytes and rules produced it.

`INV-E4-LICENSE-1`: acquisition/manifest metadata records source URL, citation/DOI where known,
license or `unknown`, access requirements, and redistribution permission separately. `unknown`
never permits bundling.

`INV-E4-MAPPING-1`: anatomy normalization and embodiment mapping are separate stages. A source
muscle label is not an actuator ID; an explicit versioned rule/catalog mediates the conversion.

`INV-E4-DIRECT-1`: a direct link declares neuron ID, actuator ID, finite weight, direction/sign,
confidence, and provenance. A neuron may drive multiple actuators and an actuator may receive
multiple neurons; duplicate pairs are rejected.

`INV-E4-MUSCLE-1`: muscle-mediated graphs declare muscle definitions independently, then explicit
neuron→muscle and muscle→actuator links. Muscle dynamics/model parameters are versioned and
unit-bearing; direct links cannot masquerade as muscles.

`INV-E4-UNKNOWN-1`: unknown exit nerve, target muscle, body segment, actuator, sign, or confidence
produces `unmapped`, `ambiguous`, or `conflicting` disposition with source provenance. It is never
assigned a default positive sign or a generic all-joint expansion without an explicit rule.

`INV-E4-CATALOG-1`: actuator catalogs have stable string IDs independent of array position. Any
90→78 or future actuator-space conversion is an explicit total/partial crosswalk with dropped-ID
dispositions, not positional arithmetic hidden in simulation code.

`INV-E4-DETERMINISM-1`: identical manifest bytes, source bytes, profile, and options yield bytewise
identical canonical normalized/mapping output across supported platforms.

`INV-E4-PORTABLE-1`: public logic uses portable paths and standard data contracts. Provider SDKs,
NumPy, Brian, NEURON, or MuJoCo are optional adapters, not requirements for manifest verification
or CSV normalization.

## 5. Dataset manifest 1.0

Required top-level fields:

```text
schema_version = "1.0"
dataset_id, provider, release, source_url
citation (nullable), license, redistribution
access = public | token_required | restricted
files[]
```

Each file declares:

```text
role = connectivity | neurons | motor_anatomy | morphology | crosswalk | extension
path, sha256, size_bytes, media_type, schema_id, data_rows
```

Files are ordered and that order controls streamed normalization. `manifest_sha256` is the SHA-256
of canonical JSON excluding any self-hash field. Credentials and local absolute paths are forbidden.

Initial schema IDs:

- `org.janelia.neuprint.connection-summary.v1`: required
  `preId,postId,total_weight`; optional source/target type, instance, transmitter fields;
- `org.flybrian.motor-anatomy.v1`: required `bodyid,class,subclass,exit_nerve,target`;
  optional systematic type, certainty, citations, synonyms, notes;
- future morphology/synapse schemas require separate profiles rather than unbounded CSV acceptance.

## 6. Normalized public records

Connection record:

```text
pre_neuron_id, post_neuron_id, weight
pre_type?, pre_instance?, pre_transmitter?
post_type?, post_instance?, post_transmitter?
provenance { dataset_id, release, logical_file, data_row }
source_extensions {}
```

Motor anatomy record:

```text
neuron_id, neuron_class, subclass, exit_nerves[], target_label
systematic_type?, certainty? (integer 1..5)
provenance {...}
source_extensions {}
```

Canonical serialization sorts object keys but preserves manifest file/row record order. Numeric IDs
remain numeric. Source strings preserve Unicode exactly after strict UTF-8 decoding.

## 7. Transformation profiles

A profile has stable ID/version, compatible dataset/schema IDs, a source citation, and explicit:

- exit-nerve→body-region rules;
- target-label→muscle or joint rules;
- muscle-action/direction rules;
- certainty→confidence rules;
- actuator catalog and optional crosswalk;
- fan-out and weight aggregation/normalization policy;
- unknown/conflict disposition policy.

The historical `biological_prior` behavior becomes a named migration profile only after every
default is made explicit and its known scientific limitations are documented. Corrected profiles
receive new versions; they do not mutate old output.

### 7.1 Direct transform

`motor anatomy + direct profile + actuator catalog -> direct mapping + dispositions`

Weights may be normalized per actuator only if the profile names the normalization. Sign must be
declared by the matched rule. Generic leg targets can fan out only under an explicitly named rule
and must retain lower confidence/ambiguity rather than presenting as exact anatomy.

### 7.2 Muscle-mediated transform

`motor anatomy + muscle catalog + muscle profile + actuator catalog -> muscles + two link sets + dispositions`

Muscle parameters and units come from a cited catalog release. A source target label may map to
multiple muscles only when the profile declares that fan-out. Muscle force/dynamics execution is a
separate backend capability; building the graph does not claim successful biomechanics.

## 8. Acquisition and credentials

- Provider adapters read credentials from explicit environment/keychain inputs; credentials never
  enter manifests, command history generated by the tool, logs, URLs, cache filenames, or output.
- Acquisition writes to an exact user-selected staging directory, then computes a candidate
  manifest. Verification and normalization are separate commands.
- Resume uses provider-stable page/cursor identity and content checks; it does not append blindly.
- Rate limit, authorization, provider error, partial page, schema drift, and checksum mismatch are
  distinct failures. Partial acquisition is never promoted to a verified release.
- Offline users can supply already-downloaded files plus a manifest without installing a provider
  SDK or disclosing a token.

## 9. Failure and edge matrix

| Edge | Required result |
| --- | --- |
| unknown/unsupported manifest or schema version | fail closed before file access |
| missing/extra duplicate/case-colliding manifest path | fail with exact entry |
| checksum/size/row mismatch | fail before normalized output promotion |
| invalid UTF-8 or duplicate CSV header | fail with file/header evidence |
| missing required column or empty/non-integer ID/weight | fail with data row and field |
| negative/overflow/non-finite weight | fail; never clamp |
| duplicate connection pair | reject or apply exact declared aggregation policy |
| conflicting repeated neuron annotation/transmitter | disposition or reject per profile |
| unknown exit nerve/muscle/actuator/sign | unmapped/ambiguous disposition; no guessed link |
| generic leg target | disposition unless profile explicitly declares fan-out |
| zero mapping links | valid report but not executable embodiment |
| source file changed after verification | parse through verified open handle or reverify before promotion |
| interrupted normalization | no final output/receipt; temporary data recoverable/removable by exact target |
| two platforms | canonical bytes and SHA-256 match |

## 10. Implementation segmentation

1. **E4-A manifest + offline readers:** typed manifest, path/checksum/size/row verification,
   streaming connection/motor-anatomy parsers, canonical receipt, bounded fixtures.
2. **E4-B explicit embodiment profiles:** stable actuator catalog, direct and muscle-mediated
   transforms, dispositions, historical-profile reproduction/correction comparison.
3. **E4-C provider acquisition:** NeuPrint release adapter, credential boundary, pagination/resume,
   candidate manifest, recorded official-source evidence.
4. **E4-D consumer cutover:** service uses released package; duplicate private authorities removed
   only after exact corpus/fixture parity and production-shaped rehearsal.

Each segment amends this contract before deviating from its forecast.

## 11. Forecast

Expected engine production: `datasets.py`, `ingestion.py`, `embodiment.py`, optional provider module,
and stable exports only when consumer-ready. Expected fixtures/tests: tiny connection and motor
anatomy CSVs, manifests generated with fixed checksums, malformed/path/tamper/unknown mapping cases,
and a migration comparison that reads private source data without copying it.

## 12. OA evidence and acceptance ledger

| ID | Acceptance | Status |
| --- | --- | --- |
| E4-01 | Detailed release/manifest/normalization/transformation contract | PASS — this document |
| E4-02 | Portable manifest validation and canonical identity | OPEN |
| E4-03 | Checksum/size/path/symlink/row verification | OPEN |
| E4-04 | Streaming connection and motor-anatomy normalization | OPEN |
| E4-05 | Deterministic canonical normalized receipt | OPEN |
| E4-06 | Explicit direct actuator transform and dispositions | OPEN |
| E4-07 | Explicit muscle-mediated transform and dispositions | OPEN |
| E4-08 | Historical corpus migration comparison | OPEN |
| E4-09 | Official provider acquisition/resume/credential boundary | OPEN |
| E4-10 | License/citation/redistribution evidence | OPEN |
| E4-11 | Ruff, strict mypy, pytest, build/clean-wheel and sensitivity | OPEN |
| E4-12 | macOS/Windows/Linux canonical-byte agreement | OPEN |
| E4-13 | Released package consumed by private service | BLOCKED — publication coordinate absent |
| E4-14 | Bidirectional contract/diff closure | OPEN |

No open or blocked row is completion. E4 cannot close local/cloud equivalence, production rehearsal,
or the overall FlyBrian launch.

## 13. Contract-change procedure

When real source data contradicts a field/rule assumption: stop, preserve the exact offending row,
amend the schema/profile/disposition rule here, add a pre-change failing fixture, then resume. Git
history records superseded behavior; old profile IDs remain reproducible.
