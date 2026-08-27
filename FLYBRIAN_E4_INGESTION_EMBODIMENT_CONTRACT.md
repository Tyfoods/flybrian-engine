# FlyBrian E4 Public Ingestion and Embodiment Contract

Status: **E4-A and E4-B verified checkpoints; E4-C–E4-D open**

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

- `manc:v1.2.1` connectivity split across three CSV files with 1,208,689 data rows;
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
SHA-256, media type, schema ID, and expected data-row count. A schema reader admits only its
declared logical role. Verification finishes before parsing.

`INV-E4-PATH-1`: manifest paths are normalized POSIX relatives; absolute, backslash, dot segment,
escape, symlink, duplicate path, and case-colliding entries are rejected.

`INV-E4-SCHEMA-1`: parsers require the exact versioned required-column set, reject duplicate
columns, preserve allowed additive columns in namespaced source metadata, and report row/file/field
for malformed values. Required values are never coerced from empty or non-finite input.

`INV-E4-STREAM-1`: large connectivity sources are streamed in deterministic manifest/file/row
order. Correctness does not require loading the 1.2-million-edge corpus into memory.

`INV-E4-IDENTITY-1`: normalized neuron IDs are non-negative provider identities represented as
integers; source row identity is `(logical_file, one-based data_row)`. A source schema may declare
exact integral decimal scientific notation because the historical MANC CSV contains 153 such ID
cells (for example `8.4137E+11`). Conversion uses decimal lexical arithmetic, never binary float;
requires finite, non-negative, integral output within the declared digit bound; and preserves the
original non-canonical lexeme in provenance. Fractional, signed-negative, non-finite, or excessive
identities fail. Duplicate scientific keys are rejected or resolved only by an explicit declared
aggregation policy.

`INV-E4-CONNECTION-1`: normalized connections declare pre/post neuron IDs, non-negative integer
weight/count, source and target annotations where present, and source row provenance. Zero-weight,
self-edge, duplicate-edge, and neurotransmitter-conflict policies are explicit manifest/profile
choices rather than hidden parser behavior.

`INV-E4-NUMERIC-1`: source schemas may declare exact integral Decimal notation for integer domains.
The historical corpus serializes all 21,427 part-3 weights with a `.0` suffix. Decimal/scientific
lexemes are accepted only when finite, non-negative, mathematically integral, within field bounds,
and retained in provenance. Binary floating-point conversion and fractional-count rounding are
forbidden.

`INV-E4-PROVENANCE-1`: normalized output declares input manifest SHA-256, transformation profile
ID/version, engine version, record counts, dispositions, and output SHA-256. A consumer can prove
which exact source bytes and rules produced it.

`INV-E4-LICENSE-1`: acquisition/manifest metadata records source URL, citation/DOI where known,
license or `unknown`, access requirements, and redistribution permission separately. `unknown`
never permits bundling. Source URLs are absolute HTTP(S) locations without embedded credentials
or fragments.

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
provenance { dataset_id, release, logical_file, data_row, source_lexemes? }
source_extensions {}
```

Motor anatomy record:

```text
neuron_id, neuron_class, subclass, exit_nerves[], target_label?
systematic_type?, certainty? (integer 1..5)
provenance {...}
source_extensions {}
```

Canonical serialization sorts object keys but preserves manifest file/row record order. Numeric IDs
remain numeric. Source strings preserve Unicode exactly after strict UTF-8 decoding.

The motor-anatomy column `target` is structurally required but its value is nullable: 84 of the 838
historical rows explicitly lack a characterized muscle target. They normalize as `target_label =
null` with provenance and later produce an unmapped disposition; they are not malformed rows.

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
| unknown/unsupported manifest or schema version, role/schema mismatch | fail closed before record parsing |
| missing/extra duplicate/case-colliding manifest path | fail with exact entry |
| checksum/size/row mismatch | fail before normalized output promotion |
| invalid UTF-8, duplicate/missing CSV header, including a header-only source | fail with file/header evidence |
| missing required column or empty/invalid ID/weight | fail with data row and field; profile-declared exact integral scientific IDs use Decimal and retain their lexeme |
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
| E4-02 | Portable manifest validation and canonical identity | PASS — strict manifest 1.0 round-trip/canonical hash and unknown/version/domain rejection pass |
| E4-03 | Checksum/size/path/symlink/row verification | PASS — safe relative paths, duplicate/case collision, regular-file/symlink, size/hash, strict CSV, row count, and mid-stream mutation oracles pass |
| E4-04 | Streaming connection and motor-anatomy normalization | PASS for the initial two schemas — bounded fixtures and the full private migration corpus stream with exact provenance |
| E4-05 | Deterministic canonical normalized receipt | PASS — §16 profile/receipt owner preserves every source row, records 21,296 repeated pair identities plus one annotation conflict in the 1,208,689-row migration corpus, retains 15 self-edges, rejects under strict policies, and passes canonical/promotion/idempotence/scale/sensitivity oracles |
| E4-06 | Explicit direct actuator transform and dispositions | PASS — stable catalogs, exact target/direction/confidence/fan-out/normalization rules, canonical graph/receipt hashes, and unknown/ambiguous dispositions pass bounded and full-corpus direct oracles |
| E4-07 | Explicit muscle-mediated transform and dispositions | PASS for graph construction — unit-bearing versioned muscles, explicit weighted fan-out, complete actuator links, canonical graph/receipt hashes, and incomplete-profile rejection pass; muscle dynamics execution remains outside this transform acceptance |
| E4-08 | Historical corpus migration comparison | PARTIAL — all 396 private leg rows transform read-only into 692 corrected links plus 90 dispositions, removing 660 historical generic zero-sign links; the 90-entry actuator catalog and all 90 crosswalk dispositions match read-only historical evidence exactly; historical muscle profile/catalog comparison remains open |
| E4-09 | Official provider acquisition/resume/credential boundary | PARTIAL — the release-pinned adapter, exact paging, retry/terminal/cancellation states, crash-safe resume, snapshot guard, receipt-last promotion, idempotence/conflict, and credential-sentinel oracles pass offline; authorized live MANC v1.2.1 rehearsal is `BLOCKED-LIVE` because this host has no token |
| E4-10 | License/citation/redistribution evidence | PASS for the initial MANC v1.2.1 and FlyBody actuator authorities — official Janelia, neuPrint, CC BY 4.0, pinned FlyBody, and Apache-2.0 evidence are recorded; dataset receipts bind DOI/license/redistribution/query/modified-representation status, while wheel/sdist bundle the exact FlyBody license and modification notice |
| E4-11 | Ruff, strict mypy, pytest, build/clean-wheel and sensitivity | PASS for E4-A/E4-B/E4-C offline — 114 tests, Ruff, strict mypy, wheel/sdist, clean-wheel public acquisition/crosswalk smoke, E4 critical mutation receipts, exact private read-only direct/catalog/crosswalk rehearsals, and E4-C base-install tests pass; live provider rehearsal remains separate |
| E4-12 | macOS/Windows/Linux canonical-byte agreement | OPEN |
| E4-13 | Released package consumed by private service | BLOCKED — publication coordinate absent |
| E4-14 | Bidirectional contract/diff closure | PASS for E4-A/E4-B and the E4-C offline checkpoint — maps below; live provider acceptance, historical muscle behavior, and consumer changes remain open |

No open or blocked row is completion. E4 cannot close local/cloud equivalence, production rehearsal,
or the overall FlyBrian launch.

### 12.1 E4-A evidence journal — 2026-08-27

- `RED`: focused tests initially failed because `datasets.py`/`ingestion.py` did not exist.
- `DISCOVERY`: the first full-corpus parse stopped at part 1 data row 6,109 because `postId`
  contained `8.4137E+11`. Census proved 153 exact integral scientific ID cells and no invalid or
  fractional IDs. The contract and red fixture were amended before Decimal conversion landed.
- `DISCOVERY`: the next pass stopped at part 3 data row 1 because `total_weight` contained `609.0`.
  Census proved all 21,427 part-3 weights are exact integral Decimal values, with no fractions; the
  numeric invariant and red fixture were amended before conversion landed.
- `DISCOVERY`: the next pass stopped at motor-anatomy row 51 because target is empty. Census proved
  exactly 84 of 838 rows have an unknown target and no other structurally required field is empty;
  the nullable-target/unmapped rule and red fixture were amended before normalization resumed.
- `MIGRATION-READONLY`: manifest `418408d839b103cf1bd8060d13b71e128ebd4efbf3124916d208e307c6d1725f`
  verified and streamed 1,208,689 edges, weight sum 23,577,375, 21,580 retained numeric lexemes,
  838 motor-anatomy rows, and 84 unknown targets. Private source paths were read only; no bytes were
  copied, normalized into the private tree, or modified.
- `TEST`: bounded fixtures cover canonical manifest identity, path/case/tamper/symlink/row checks,
  strict headers/weights, provenance, source mutation, exact Decimal IDs/counts, and nullable target.
- `PACKAGE`: wheel and sdist include both E4 contracts/modules; a clean base-wheel environment
  verified the bounded manifest, preserved the exact `9007199254740993` ID beyond binary-float
  precision, streamed four edges and three anatomy rows, and retained one unknown target.
- `SENSITIVITY — checksum`: removing SHA-256 comparison made a same-size byte mutation pass
  verification and the tamper oracle fail; size+hash comparison was restored.
- `SENSITIVITY — exact Decimal`: routing a large scientific ID through binary float changed
  `9007199254740993` to `9007199254740992` and failed the normalization oracle; direct Decimal
  lexical conversion was restored.
- `SENSITIVITY — source stability`: removing the post-stream fingerprint made an appended row
  escape mutation detection; the completion fingerprint was restored.
- `SENSITIVITY — role/schema admission`: removing the connection schema's role check admitted an
  `extension` file as connectivity and failed the role oracle; role enforcement was restored.
- `SENSITIVITY — header-only schema`: skipping validation for a declared zero-row CSV admitted a
  header missing `postId` and failed the header oracle; verified header validation was restored.

### 12.2 E4-A contract-to-diff map

| Changed surface | Authority |
| --- | --- |
| `datasets.py` | §§4–5, 8–9: manifest domains, canonical hash, path/file/row verification, stable streaming handle |
| `ingestion.py` | §§4, 6, 9: typed connection/motor records, provenance, exact Decimal conversion, strict columns |
| bounded CSV fixtures and `test_ingestion.py` | §§9, 12: positive and negative executable oracles plus source-mutation detection |
| this contract | discovery-driven source-domain amendments and honest E4-A ledger promotion |

No E4-A production edit implements actuator mapping, muscles, provider acquisition, dataset
redistribution, service cutover, or cloud policy.

## 13. Contract-change procedure

When real source data contradicts a field/rule assumption: stop, preserve the exact offending row,
amend the schema/profile/disposition rule here, add a pre-change failing fixture, then resume. Git
history records superseded behavior; old profile IDs remain reproducible.

## 14. E4-B explicit embodiment implementation contract

Status: **verified checkpoint; E4 parent remains open**

This slice turns normalized motor anatomy into one of two simulator-neutral, versioned graphs. It
does not execute muscle dynamics, calculate motor commands, copy the private Flybody catalog, or
claim that a bounded profile is the final biological mapping.

### 14.1 Current authority and reuse record

| Fact | Current authority/evidence | E4-B decision |
| --- | --- | --- |
| normalized motor anatomy | public `ingestion.py` `MotorAnatomyRecord` at E4-A `fefeead` | reuse as the sole transform input |
| experiment graph shape | public FES 1.0 validation in `schema.py`; direct and muscle specimens | produce data that can be projected into this shape; do not create a second experiment schema |
| historical 90-actuator catalog/direct mapper | private read-only `flybrian/digifly/mapping.py` | migration evidence only until source/license/version are explicit |
| historical muscle bridge/dynamics | private read-only `flybrian/digifly/muscle_model.py` | migration evidence only; no implicit import or copy |
| transformation owner after E4-B | absent | one public engine embodiment module owns profile validation and deterministic graph construction |

Semantic searches covered actuator, muscle, embodiment, mapping, disposition, motor command,
exit-nerve, target-label, crosswalk, and Hill-model concepts across public engine and private
service. Existing FES validation checks graph references but does not derive graphs from anatomy.
The artifact disposition type describes output-file availability and is intentionally not reused
for scientific mapping dispositions.

Read-only historical census on 2026-08-27 found 838 motor-anatomy rows, 396 leg rows, 1,352 direct
links over 60 actuators, and no duplicate neuron/actuator pairs. Of those links, 660 are generic-leg
fan-out links with zero sign. The corrected public profile must represent those source rows as
`ambiguous`; zero is not an actuator direction. The historical behavior may later be preserved
under an explicitly unsafe migration profile, but it cannot be the corrected default.

### 14.2 Intended authority and deletion map

- Intended owner: the public engine's versioned actuator catalog, muscle catalog, mapping profiles,
  transform result, and canonical receipt.
- E4-B adds no private compatibility reader, hidden default profile, positional actuator lookup, or
  mutable global mapping.
- No public authority is displaced in this slice, so there is no public deletion target.
- Private direct/muscle authorities remain until E4-D has a released-package consumer and exact
  corpus parity. They are read-only here and are not wrapped as a second runtime authority.
- Retirement gate: after public profile license/provenance approval, full-corpus comparison, service
  cutover, and production rehearsal, E4-D must delete the duplicate private transformation paths.

### 14.3 Behavioral state machine

States: `PROFILE_INVALID`, `READY`, `TRANSFORMING`, `GRAPH_WITH_LINKS`, `GRAPH_WITHOUT_LINKS`,
`TRANSFORM_REJECTED`.

```text
catalog/profile construction + invalid reference/domain      -> PROFILE_INVALID (no transform)
catalog/profile construction + complete explicit rules       -> READY
READY + verified ordered anatomy records                     -> TRANSFORMING
TRANSFORMING + one or more valid derived links                -> GRAPH_WITH_LINKS
TRANSFORMING + only scientific dispositions                   -> GRAPH_WITHOUT_LINKS
TRANSFORMING + duplicate neuron identity/conflicting source  -> TRANSFORM_REJECTED
```

Both graph outcomes contain a canonical receipt. `GRAPH_WITHOUT_LINKS` is valid for inspection but
derives `executable = false`. Profile validation and source-identity rejection happen before a
result is promoted; partial graphs are never returned after rejection.

### 14.4 Catalog and profile contract

Every actuator has a stable string ID, body region, joint/function, control range with unit, and
source reference. Catalog ID plus version identifies the ordered set; array position is not an
identity. Duplicate/case-colliding IDs, non-finite or reversed ranges, and blank source are
rejected. Multiple actuator IDs may deliberately share a body-region/joint identity only when the
consuming profile explicitly permits that fan-out.

Every muscle has a stable string ID, body region, model ID/version, source reference, and an
ordered unit-bearing parameter set. Parameters use exact decimal lexical values; duplicate names,
unknown units, non-finite values, or duplicate/case-colliding muscle IDs are rejected.

A direct profile declares:

- profile ID/version/source and compatible dataset identities;
- exact exit-nerve→body-region rules;
- exact target-label→joint plus positive/negative direction rules;
- exact certainty→confidence rules;
- an optional, explicit missing-certainty confidence for releases whose declared source field is
  blank; absence of this profile field means no fallback;
- whether multiple body regions and multiple same-joint actuators may fan out; and
- weight policy `none` or `per_actuator_equal_share`.

A muscle profile declares the same identity/compatibility/body-region/confidence facts plus exact
`(body_region, target_label)` rules. Each rule names muscles and exact neuron→muscle weights; each
muscle names one or more explicit muscle→actuator links with weight and direction. Fan-out is
therefore data, not inference.

Missing certainty has no implicit default confidence. A profile may declare the exact confidence
used for a missing source value; that declaration is canonical-hashed and versioned. Without it,
missing confidence cannot create a link. Missing/unknown target, exit nerve, actuator, muscle, or
direction cannot create a link. A generic leg label has no direct target rule in the corrected
profile and becomes `ambiguous_target`, not a zero-sign fan-out.

### 14.5 Result, provenance, and derived state

Direct links contain neuron ID, stable actuator ID, exact positive rational weight, direction,
confidence,
and original row provenance. Muscle graphs contain selected muscle definitions, neuron→muscle
links, and muscle→actuator links with the same explicit identity/weight/direction provenance.

Every disposition contains `unmapped`, `ambiguous`, or `conflicting`; a stable reason code; neuron
ID where applicable; source row provenance; affected field; and original value when available.
Disposition order follows input record order and then rule/catalog order.

`DERIVED: executable`

- direct graph: true only when at least one direct link exists;
- muscle graph: true only when at least one neuron→muscle link exists and every selected muscle has
  at least one explicit actuator link;
- missing, empty, or disposition-only output: false.

The canonical receipt binds engine version, input dataset ID/release/manifest hash, profile
ID/version/canonical SHA-256, catalog IDs/versions/canonical SHA-256 values, mode, input count,
link/muscle/disposition counts, canonical graph SHA-256, and receipt SHA-256. The graph also embeds
those authority hashes, so changing catalog bounds, sources, parameters, or profile rules changes
the graph identity even when a caller incorrectly reuses a version label. Canonical JSON sorts
object keys and preserves declared/input order. Exact decimal values serialize as normalized
strings and exact rational weights as reduced `p/q` strings to avoid platform float differences.

### 14.6 Edge and lifecycle resolutions

| Edge/lifecycle | Required resolution |
| --- | --- |
| create profile/catalog | validate the complete immutable object before use |
| read/replay old result | bind exact profile/catalog versions and hashes; do not resolve `latest` |
| update rules | publish a new version; old graph/receipt bytes remain reproducible |
| delete profile/catalog | external distribution may retire discovery, but a referenced version cannot silently disappear from reproducibility storage |
| unknown dataset/profile compatibility | reject before transforming |
| duplicate neuron source identity | reject the transform; no last-row-wins behavior |
| two nerves resolve to one region | deduplicate the region without duplicating a link |
| nerves resolve to multiple regions | `ambiguous` unless the profile explicitly permits fan-out |
| no target or no rule | `unmapped`; generic target uses `ambiguous` |
| multiple matching actuators | `ambiguous` unless same-joint fan-out is explicit |
| certainty absent/outside profile | `unmapped` confidence disposition |
| selected muscle lacks actuator link | invalid profile before source transformation |
| direct/muscle duplicate derived pair | invalid profile or rejected transform; never silently sum |
| no links | valid non-executable graph plus receipt |
| interrupted transform | no promoted result or receipt; immutable inputs remain untouched |

### 14.7 Scale and horizon

The scaling input is `M` motor-anatomy records and `L` emitted links. Transform work is
`O(M + L)` plus bounded catalog lookup; retained state is `O(M + L)` because duplicate scientific
identity detection and the returned graph require those identities. No row-count cap becomes
product capacity. A profile that deliberately fans one row to many outputs pays for those declared
links; an unknown row pays for one disposition. The first real constraint is memory for the graph
that the caller requested, not an unrelated hard-coded neuron count.

The historical migration oracle uses all 396 leg rows. A separate bounded fixture varies fan-out,
unknown rows, and duplicate identity. Corpus size is evidence, not a production maximum.

Discovery census found that all 396 historical leg rows leave `match_certainty(1-5)` blank even
though non-leg rows use the field. The migration profile must therefore declare its historical
`0.5` confidence explicitly; treating `0.5` as an engine default remains prohibited.

### 14.8 Forecast and test-trust gate

Expected production: one new public embodiment module and stable exports only. Expected tests: one
new test module using E4-A records and small synthetic catalogs/profiles. Expected documentation:
this contract, extraction ledger, and README. No service/web/Maestro file belongs to E4-B.

| Invariant | Existing test evidence | Pre-change result | Decisive oracle/sensitivity | Disposition |
| --- | --- | --- | --- | --- |
| direct explicit mapping | FES validates hand-authored links only | absent | anatomy→direct graph exact bytes; removing target/direction admission fails | add |
| muscle explicit mapping | FES validates hand-authored graph only | absent | anatomy→muscle graph with explicit fan-out and links; removing actuator completeness fails | add |
| unknown/ambiguous truth | private tests assert link count/leg coverage, not dispositions | unsafe generic links admitted privately | missing/generic/unknown records produce exact dispositions and no links | replace in public boundary |
| stable identity/cross-platform bytes | schema round-trip covers experiment JSON, not derived graph receipt | absent | equivalent construction yields identical canonical bytes/hash; float conversion mutation fails | add |
| duplicate/conflict rejection | no public transform | absent | repeated neuron ID rejects before result | add |
| scale ownership | private test asserts `>500` links | insensitive to growth owner | full 396-row read-only migration plus bounded fan-out fixture; no fixed count in production | add |

Tests are written and demonstrated red because the embodiment owner does not yet exist. At least one
critical rule is then mutated after implementation to prove the oracle rejects the harmful
alternative. Discovery that requires a second authority, guessed sign, hidden aggregation, or a
private-file runtime dependency returns this slice to contract state before further production
editing.

### 14.9 Confirmed behavioral scenarios

1. A `MetaLN_L` neuron targeting `Ti extensor` with certainty 5 maps through explicit rules to the
   declared left T3 tibia actuator with positive direction and confidence 1.
2. A `ProLN_R` neuron targeting `Ti flexor` maps to the declared right T1 tibia actuator with
   negative direction; changing only the target changes the direction oracle.
3. A neuron with no target yields `unmapped/missing_target` and no direct or muscle link.
4. A generic `hind leg` record yields `ambiguous/ambiguous_target`, never ten zero-sign links.
5. A muscle rule may explicitly fan one anatomy target into two named muscles with declared
   weights; both muscles must have explicit actuator links and unit-bearing model parameters.
6. Reordering dictionary construction without changing declared catalog/rule/input order leaves
   canonical bytes unchanged; changing a declared rule or source row changes the graph hash.

### 14.10 E4-B evidence journal — 2026-08-27

- `RED — owner`: the behavioral suite failed collection because the public embodiment module did
  not exist.
- `RED — authority identity`: source-reference and canonical authority-hash assertions failed
  against the first implementation; individual actuator sources and profile/catalog hashes were
  added before closure.
- `DISCOVERY — certainty`: all 396 historical leg rows leave the declared certainty field blank.
  The contract was amended before adding an explicit profile-level missing-certainty confidence;
  profiles without that field still emit `missing_confidence`.
- `MIGRATION-READONLY — direct`: the public transform consumed all 396 normalized private leg rows
  in memory without copying or modifying private bytes. Historical code emits 1,352 links,
  including 660 generic zero-sign links. The corrected transform emits 692 explicit signed links,
  66 `ambiguous_target` dispositions, and 24 `unknown_target` dispositions. Its read-only migration
  graph SHA-256 is `670f90de3e191b82d226418c5ed3296c4f219a99925988fea7c1330a6cd2e30d` and
  receipt SHA-256 is `6b75c0334c9e1725a5f7b65d755e4be527e223a02ba27da31eb60a850502360c`.
- `SENSITIVITY — direction`: forcing every direct link positive changed the flexor result and
  failed the exact direction oracle; rule-derived direction was restored.
- `SENSITIVITY — muscle completeness`: skipping the complete muscle→actuator requirement admitted
  a neuron→muscle graph with no actuator path and failed the profile oracle; rejection was restored.
- `SENSITIVITY — authority hash`: replacing the embedded profile hash with a constant made two
  different profile sources share a graph hash and failed the identity oracle; content binding was
  restored.
- `QUALITY`: the final E4-B revision passes the complete 81-test suite, Ruff, strict mypy, wheel and
  sdist construction, and a clean-wheel direct transform through the public package exports.
- `PACKAGE`: clean-wheel smoke produced one negative-direction direct link and verified that the
  receipt's profile and graph hashes exactly match the installed public authorities.

### 14.11 E4-B contract-to-diff map

| Changed surface | Contract authority |
| --- | --- |
| `embodiment.py` catalogs/profiles | §§4, 7, 14.4: stable IDs, explicit rules, exact numeric and source authorities |
| `embodiment.py` transforms/results | §§4, 7, 14.3–14.6: direct/muscle graphs, dispositions, executable derivation, canonical receipts |
| public package exports | §14.1 intended public owner and §14.8 stable export forecast |
| `test_embodiment.py` | §§14.6–14.9 behavioral, edge, scale, canonical identity, and sensitivity oracles |
| README/extraction/E4 contracts | public behavior, ledger promotion, discovery amendments, and remaining limits |

No E4-B edit implements muscle dynamics, a licensed historical catalog distribution, provider
acquisition, positional 90→78 crosswalk, private service cutover, web form behavior, or DigiFly
rendering. Those remain governed by open E4/parent rows rather than implied by graph construction.

## 15. E4-C official NeuPrint acquisition implementation contract

Status: **implemented and verified offline; authorized live-provider acceptance is `BLOCKED-LIVE`**

### 15.1 Primary-source and current-authority record

Primary sources checked on 2026-08-27:

- Janelia's MANC page identifies the dataset as CC BY, names NeuPrint Python/R programmatic access,
  links a public flat-file bucket, and records the v1.2 release date:
  `https://www.janelia.org/node/68782`.
- Current neuprint-python documentation declares explicit server/dataset selection, token argument
  or `NEUPRINT_APPLICATION_CREDENTIALS`, and custom query support:
  `https://connectome-neuprint.github.io/neuprint-python/docs/client.html`.
- Current official neuprint-python source identifies the cross-dataset neuron properties used by
  the fixed MANC query as `predictedNt`, `systematicType`, `exitNerve`, `matchingNotes`, and
  `target`; provider-absent historical review columns are emitted as explicit nulls, not guessed:
  `https://github.com/connectome-neuprint/neuprint-python/blob/master/neuprint/queries/neuroncriteria.py`.
- The official neuPrintHTTP repository documents the custom JSON endpoint and Bearer-token header:
  `https://github.com/connectome-neuprint/neuPrintHTTP`.
- CC BY 4.0 permits sharing/adaptation with attribution, license link, and change indication:
  `https://creativecommons.org/licenses/by/4.0/`.

The public Google bucket currently exposes MANC v1.0 exports, not a confirmed v1.2.1 flat
connection/motor pair matching FlyBrian's historical normalized sources. E4-C therefore uses the
version-selected NeuPrint API for the initial v1.2.1 candidate and records the public bucket as a
future direct-download adapter. It does not relabel v1.0 bytes as v1.2.1.

The private fetcher is read-only evidence. It constructs a global neuprint-python client, sets a
900-second session timeout, logs broad exceptions, and contains a dataset-specific placeholder; it
does not provide page identity, exact resume, byte manifests, credential-log oracles, or promotion
atomicity. It is not reused as a public authority.

### 15.2 Intended owner and non-goals

One public acquisition module owns release profiles, provider snapshots, fixed queries, page
validation, resumable staging, candidate manifest/receipt construction, and atomic promotion. It
depends on an injected transport contract; the optional neuprint-python transport is one adapter,
not the scientific data model.

E4-C does not bundle a token, run an unaudited arbitrary Cypher string, download multi-gigabyte
synapse/morphology assets, install pandas in the base package, mutate private data, or claim live
MANC acceptance without credentials. Provider SDK and network access remain optional extras; all
manifest verification/normalization stays dependency-free and offline.

### 15.3 Acquisition state machine

States: `NEW`, `SNAPSHOTTED`, `CONNECTIONS`, `MOTOR_ANATOMY`, `VERIFYING`, `PROMOTED`, `STALE`,
`FAILED_RETRYABLE`, `FAILED_TERMINAL`.

```text
NEW + compatible provider snapshot                  -> SNAPSHOTTED
SNAPSHOTTED + first committed connection page       -> CONNECTIONS
CONNECTIONS + next valid page                        -> CONNECTIONS
CONNECTIONS + empty terminal page                    -> MOTOR_ANATOMY
MOTOR_ANATOMY + next valid page                      -> MOTOR_ANATOMY
MOTOR_ANATOMY + empty terminal page                  -> VERIFYING
VERIFYING + unchanged snapshot + verified files     -> PROMOTED
any active state + retryable transport failure       -> FAILED_RETRYABLE
FAILED_RETRYABLE + matching request/snapshot resume  -> prior active state
any active state + changed provider snapshot         -> STALE (never promoted)
any state + schema/order/auth/request conflict       -> FAILED_TERMINAL
```

`PROMOTED` is idempotent: rerunning the identical request verifies and returns the existing
manifest/receipt. A different request or provider snapshot never appends to the existing staging
estate.

### 15.4 Release profile and fixed provider rows

The initial profile is exactly `manc:v1.2.1`, provider `Janelia Research Campus`, server
`https://neuprint.janelia.org`, CC BY 4.0, redistribution allowed, and citation DOI
`10.7554/eLife.97769.1`. The profile records that API-extracted CSV is a transformed representation
and retains the query/profile version. A later corrected citation or release produces a new profile
version; it does not mutate old receipts.

Connection pages are ordered by `(preId, postId)` and contain exactly the initial E4-A connection
schema fields. Motor-anatomy pages are ordered by `bodyid` and contain exactly the initial E4-A
motor schema fields. Provider results must be objects with exact known keys; boolean, binary-float,
negative, missing, out-of-order, repeated cursor, or duplicate identity values fail the page.
Large identifiers are admitted only as exact integers or exact integral decimal strings and are
written without binary-float conversion.

Pagination is keyset-based. Page size controls one request/commit unit, not total dataset capacity.
The default target is 10,000 rows; 1–50,000 is the transport containment range. A full page is not
terminal; an empty page after the last cursor is the only completion signal.

### 15.5 Durable resume and atomic promotion

The caller supplies an exact staging directory. The acquisition owner creates only these names:

```text
.flybrian-acquisition.json
connectivity.csv.part
motor-anatomy.csv.part
connectivity.csv                 (promotion only)
motor-anatomy.csv                (promotion only)
dataset-manifest.json            (promotion only)
acquisition-receipt.json         (promotion only)
```

Atomic JSON replacement may create the corresponding exact `<name>.tmp` sibling transiently; it
is fsynced and replaced or removed, never treated as evidence or left as an alternate authority.

The journal canonical-hashes the request and initial provider snapshot, and records per stream:
committed byte offset, data-row count, last keyset cursor, completion, and update time. For each
page the file is flushed and fsynced before an atomic journal replacement. Resume truncates each
`.part` file to its journaled offset before refetching, so a crash after bytes but before journal
commit cannot duplicate rows. Journal advancement before durable bytes is prohibited.

Finalization flushes files, obtains a second provider snapshot, and requires exact equality with
the first. It constructs a candidate manifest over the part files with computed
SHA-256/size/row counts and verifies it through the E4-A owner. It then derives the identical
final-path manifest, renames parts without overwriting an existing final, verifies the final-path
manifest, writes that manifest atomically, and writes the canonical receipt last. Because a
filesystem cannot atomically rename the full set, the receipt is the sole promotion marker; final
filenames that exist without it are recoverable staging, not a promoted dataset. On restart before
that marker, an owned final file is moved back to its `.part` name and the candidate manifest is
removed before verification resumes; source rows and journal offsets remain authoritative and no
provider page is lost or duplicated.

### 15.6 Credential and failure contract

- The token enters only the optional transport constructor, explicitly or from
  `NEUPRINT_APPLICATION_CREDENTIALS`; it is never stored on request/profile/journal/receipt objects.
- Exceptions, request summaries, URLs, file names, and repr strings must not contain the token or
  Authorization header. Tests use a sentinel and search all persisted/output text.
- TLS verification defaults on and cannot be disabled by the release profile.
- `401/403` are terminal authorization failures; `404`/unknown dataset/schema are terminal release
  failures; timeout/429/5xx are retryable without journal advancement.
- Backoff is owned by the caller/CLI and honors provider retry metadata; acquisition state itself
  stores no secret-bearing raw response.
- A short/invalid/out-of-order page, cursor non-advance, changed snapshot, checksum mismatch, or
  staging escape fails closed with exact stream/page/cursor evidence.

### 15.7 Scale and responsiveness

For `N` source rows and page size `P`, requests are `O(N/P)`, work is `O(N)`, and retained memory is
`O(P)` plus small journal state. Output disk is `O(N)` and is the first intended resource
constraint. There is no total-row maximum. Each network call and page commit is independently
bounded; a transport implementation must not accumulate prior pages. Cancellation is observed
between pages and leaves the exact resume point durable.

### 15.8 Forecast, red oracles, and acceptance

Expected production: one acquisition module, an optional `neuprint` dependency group, stable
exports, README installation/acquisition text. Expected tests: one filesystem integration module
with scripted transport pages/failures. No web/service/Maestro file belongs to E4-C.

| Invariant | Pre-change result | Decisive oracle and sensitivity |
| --- | --- | --- |
| fixed ordered page admission | owner absent | valid two-page acquisition; duplicate/out-of-order/float page rejects |
| crash-safe resume | owner absent | inject failure after durable page bytes and before journal replacement; resume truncates/refetches without duplication |
| immutable snapshot | owner absent | start/end snapshot mismatch produces no final files |
| credential isolation | private client accepts/logs broad exceptions | sentinel token absent from every persisted file, exception, and captured log |
| atomic manifest promotion | owner absent | verified final manifest/receipt only after both streams; mutation of pre-promotion verify blocks all finals |
| idempotence/conflict | owner absent | identical promoted request returns same hashes; changed request fails without overwrite |
| optional real adapter | private-only dependency | fixed Cypher/JSON adapter tests; live token-backed MANC rehearsal remains `BLOCKED-LIVE` on this host |

Implementation begins with failing tests because the acquisition owner is absent. At least one
journal-order or snapshot guard is temporarily removed after implementation to prove the
filesystem oracle detects duplicate or stale promotion. Official live acceptance cannot become
PASS until an authorized token is available and no secret appears in evidence.

### 15.9 E4-C implementation evidence — 2026-08-27

- `RED`: with `PYTHONPATH=src`, collection failed because
  `flybrian_engine.acquisition` did not exist.
- `PRODUCTION`: `acquisition.py` now owns the immutable `manc:v1.2.1` release profile,
  provider snapshots, fixed queries, optional neuprint-python adapter, exact row admission,
  keyset pagination, fsynced part files, atomic journal replacement, retryable/terminal/cancelled
  states, crash recovery, candidate/final manifest verification, and receipt-last promotion.
- `CREDENTIAL`: a sentinel token is absent from transport repr, fixed queries, sanitized terminal
  and retryable exceptions, and every persisted staging artifact. TLS verification is fixed on.
- `DURABILITY`: fault injection after durable page bytes and before the second journal replacement
  leaves the earlier offset authoritative; resume truncates and refetches without duplicate rows.
- `PROMOTION`: injected E4-A manifest verification failure leaves both resumable parts and no
  finals, manifest, or receipt. An identical promoted request returns without provider access; a
  changed page-size request neither contacts the provider nor changes any byte.
- `SENSITIVITY`: temporarily disabling the final provider-snapshot equality guard made
  `test_changed_provider_snapshot_is_stale_and_never_promotes` fail because no exception was
  raised. Restoring the guard returned the test to PASS.
- `QUALITY`: all 93 tests pass in the existing scientific environment; all 12 E4-C tests pass in
  the base-only environment; Ruff and strict mypy pass; sdist/wheel build and fresh-wheel public
  API import pass.
- `BLOCKED-LIVE`: `NEUPRINT_APPLICATION_CREDENTIALS` is absent on this host, and unauthenticated
  NeuPrint access returns 401. No live row-count, receipt, or MANC v1.2.1 provider claim is made.

## 16. E4-A2 deterministic connection normalization and receipt contract

Status: **implemented and verified locally; cross-platform CI execution remains E4-12**

### 16.1 Intended outcome and single owner

A researcher can turn one verified dataset into an immutable, portable normalized connection
stream plus a receipt that proves the exact source manifest, policy, engine version, record bytes,
and scientific edge decisions. `ingestion.py` is the sole public owner. The raw
`iter_connections()` reader remains a lossless source-schema reader; the new normalization owner
wraps it rather than changing parser behavior beneath existing consumers.

The owner accepts an exact destination directory and produces only:

```text
connections.ndjson
connection-normalization-receipt.json
```

During work it may create the exact owned siblings `connections.ndjson.part`,
`connection-normalization-receipt.json.tmp`, and `.connection-normalization-index.sqlite3`.
Temporary files are never evidence and are removed after success or handled failure. The receipt
is written last and is the sole promotion marker. A final connection file without its receipt is
recoverable incomplete work, never an executable normalized dataset.

### 16.2 Versioned normalization profile

Connection normalization profile 1.0 contains only trimmed, bounded strings and these exact
fields:

```text
schema_version = "1.0"
profile_id, profile_version, source
self_edge_policy = retain | reject
duplicate_edge_policy = record | reject
annotation_conflict_policy = record | reject
```

The initial public MANC profile is
`org.flybrian.connection-normalization.manc.v1@1.0`: self-edges are retained and counted because
the historical corpus contains 15; duplicate pairs and conflicting non-null neuron annotations
are retained per source row and recorded. A read-only full-corpus rehearsal found 21,296 distinct
repeated pre/post identities, including `(13316, 841370000000)` twice with different positive
weights, while a separate annotation census found one
conflicting neuron/field identity (`841370000000`, `transmitter`) with four source values and 52
post-establishment conflict occurrences. Rejecting the whole release would prevent historical
reproduction, while selecting one transmitter would fabricate authority. Version 1.0 deliberately
does not offer duplicate-edge summation. The historical simulator explicitly groups by
`(preId, postId, preNt)` and sums weights later; that execution policy is not silently promoted to
source-normalization truth. Adding an aggregation choice requires a new profile schema
that specifies weight arithmetic, provenance cardinality, annotation compatibility, overflow
bounds, and canonical source ordering before production code changes.

This is an explicit scientific choice, not an assertion that self-connections are universally
meaningful. A consumer that requires their removal must use a later cited profile rather than
silently filtering the normalized bytes.

### 16.3 Canonical record stream and conflict identity

Each output line is one UTF-8 canonical JSON object followed by exactly LF. Object keys are sorted,
JSON is compact and non-ASCII text is preserved. Lines remain in verified manifest/file/data-row
order. Every field of `ConnectionRecord`, including source extensions and source lexemes, is
serialized; no local absolute path or credential is admitted.

Connection identity is `(pre_neuron_id, post_neuron_id)` across every declared connectivity file,
not within one file. Under `record`, repeated rows remain unchanged and the receipt counts each
unique repeated pair once; under `reject`, any repeated identity fails with both source locations
and produces no receipt or final output. Neither branch sums weights or chooses one row. A self-edge
has equal pre/post IDs; `retain` writes it unchanged and increments `self_edge_count`, while
`reject` fails with source evidence.

For each neuron ID, each non-null `type`, `instance`, and `transmitter` value independently
establishes an annotation. Later null values do not erase it and the identical non-null value is
compatible. A different non-null value for the same field is a conflict. Under `record`, every
row remains unchanged and the receipt counts each unique conflicting `(neuron_id, field)` once;
under `reject`, normalization fails with neuron, field, first source, and conflicting source
evidence. Pre- and post-side annotations participate in the same identity table. Source text is
compared exactly; this owner does not case-fold, guess synonyms, or select a winning value.

### 16.4 Receipt 1.0 and deterministic identity

The receipt contains exactly:

```text
schema_version = "1.0"
engine_version
dataset_id, release, manifest_sha256
profile_id, profile_version, profile_sha256
self_edge_policy, duplicate_edge_policy, annotation_conflict_policy
input_record_count, output_record_count, self_edge_count
duplicate_edge_count, annotation_conflict_count
output_schema = "org.flybrian.normalized-connections.ndjson.v1"
output_path = "connections.ndjson"
output_size_bytes, output_sha256
```

`profile_sha256` hashes canonical profile JSON. `output_sha256` hashes the exact NDJSON bytes.
The receipt SHA-256 hashes its canonical JSON and is available through the API but is not embedded
as a self-hash. Counts are non-negative JSON integers. Profile 1.0 is source-lossless, so successful
input/output row counts match even when repeated identities are recorded. `duplicate_edge_count`
is the number of distinct repeated pre/post keys; it is zero under a successful duplicate `reject`
profile and may be non-zero under `record`. `annotation_conflict_count` is the number of distinct
conflicting neuron/field keys; it is zero under a successful annotation `reject` profile and may
be non-zero under `record`.

Reordering dictionary construction cannot change bytes. Reordering source files or rows changes
the manifest or output hash. Changing a policy changes the profile and receipt hashes even when
the bounded fixture happens not to contain the affected edge.

### 16.5 State machine, atomicity, and idempotence

```text
ABSENT + verified manifest/profile                  -> NORMALIZING
NORMALIZING + all records admitted/indexed/written  -> VERIFYING
VERIFYING + part size/hash/count recheck            -> CONNECTION_PROMOTED
CONNECTION_PROMOTED + canonical receipt write       -> PROMOTED
any active state + rejected-duplicate/self/conflict or tamper -> REJECTED
PROMOTED + identical manifest/profile/output        -> PROMOTED (idempotent)
PROMOTED + different manifest/profile/output        -> CONFLICT (no overwrite)
```

The SQLite index is an implementation detail used to prove global identity with bounded memory;
it is not an authority, package artifact, or returned result. Transactions are bounded. Output is
flushed and fsynced before rename; the destination directory is fsynced where supported. A caught
failure removes only the exact files created by that invocation. Existing complete output is
verified byte-for-byte before idempotent return. Existing unknown files are untouched. Incomplete
output is recovered only when the receipt is absent and the exact owned SQLite marker remains from
an interrupted invocation. An unreceipted connection file without that marker is preserved and
rejected as ambiguous, not assumed disposable. A complete conflicting result is never overwritten.

### 16.6 Scale, portability, and resource bounds

For `N` records, parsing and hashing are `O(N)` and the on-disk identity index is `O(N)`; retained
Python memory is `O(1)` apart from bounded CSV/SQLite buffers. No production row cap is introduced.
The algorithm uses standard-library paths, JSON, hashing, CSV, and SQLite so the same public API
runs on macOS, Windows, and Linux. Canonical content contains POSIX logical paths from the manifest,
never OS-native destination paths. A caller must provision space for output plus the temporary
index; disk exhaustion fails without a receipt.

### 16.7 Failure matrix

| Edge | Required result |
| --- | --- |
| duplicate pair in one file or across files with `record` | retain every source row; count the pair once; never aggregate |
| duplicate pair with `reject` | reject with both source rows; no final/receipt |
| duplicate pair with identical metadata | follow declared policy; still no implicit aggregation |
| self-edge with `retain` | exact record retained and counted |
| self-edge with `reject` | reject with source row; no final/receipt |
| null followed by known annotation | compatible; establish known value |
| two different non-null annotations/transmitters with `record` | retain both source rows; count the neuron/field conflict once |
| two different non-null annotations/transmitters with `reject` | reject with neuron/field/both sources |
| source mutation during stream | verified reader rejects; no final/receipt |
| output/index write or fsync failure | no receipt; exact owned temporary files removable |
| crash after connection rename, before receipt, with owned index marker | incomplete owned output; never executable; next call recovers |
| unreceipted output without owned recovery marker | preserve and reject; never assume researcher data is disposable |
| complete identical rerun | reverify and return identical receipt without rewriting |
| complete different profile/manifest | conflict; preserve every existing byte |
| unknown destination file | preserve it; normalization does not broaden cleanup |

### 16.8 Forecast and decisive acceptance

Expected diff: `ingestion.py`, public exports, focused ingestion tests, README, and this contract.
No service, web, Maestro, historical catalog, provider acquisition, or simulation-backend file
belongs to E4-A2.

| Oracle | Required evidence |
| --- | --- |
| canonical happy path | fixture output bytes/count/hash and receipt/profile round-trip are exact |
| duplicate policy | `record` retains/counts same/cross-file duplicates once; `reject` fails with both provenance locations |
| annotation policy | null enrichment passes; `record` retains/counts conflict once; `reject` fails for type/instance/transmitter |
| self-edge policy | retained/count and rejected/no-promotion branches both pass |
| promotion | injected writer/verification failure and marked-orphan recovery never expose a receipt early; unmarked output is preserved |
| idempotence | identical rerun preserves mtimes/bytes; changed policy conflicts without overwrite |
| portability | fixed fixture output/receipt hashes match on supported CI operating systems |
| scale | synthetic multi-file stream exceeds bounded SQLite transaction size without memory growth owner |
| sensitivity | disabling the global uniqueness insert must make the cross-file duplicate oracle fail |
| quality | full pytest, Ruff, strict mypy, sdist/wheel, and clean-wheel import/smoke pass |

Implementation starts with red tests for the absent profile/result/normalization API. E4-05 moves
to PASS only after every local oracle above is evidenced. The historical 1,208,689-row corpus is
an additional read-only migration rehearsal, not a substitute for bounded behavioral tests and
not authorization to copy its bytes into this repository.

### 16.9 E4-A2 implementation evidence — 2026-08-27

- `RED`: focused test collection failed because the public profile, receipt, result, and
  normalization API did not exist.
- `DISCOVERY — annotation`: the first proposed MANC profile rejected non-null annotation
  disagreement. A read-only corpus census found exactly one conflicting neuron/field key,
  `(841370000000, transmitter)`, four declared source values, and 52 post-establishment conflict
  occurrences. The contract was amended to lossless `record` before production behavior changed.
- `DISCOVERY — duplicate`: the first full normalization failed at part 1 rows 212,734/212,740 for
  repeated pair `(13316, 841370000000)` with weights 12/11. Historical execution separately sums
  `(preId, postId, preNt)` groups. The normalization contract was amended to preserve/count source
  rows and keep aggregation outside normalization before the profile changed.
- `MIGRATION-READONLY`: all three private connection files were verified and streamed without
  modification. Manifest `3e8c4d3caeccec80f73ffa8bf5b2a0f6430ac6d349d0a1007f4fb224dea161dc`
  produced 1,208,689 rows, 15 retained self-edges, 21,296 distinct repeated pair identities, and
  one annotation-conflict identity. Output SHA-256 was
  `7bd2bb474b2316d66747bd9505d2690734cb24b13cff8ee201cf417354344594`
  over 522,803,133 bytes; receipt SHA-256 was
  `1ad35623b0d1f8ffd7d49d095640087b43baae479d36d65c03cbd21a5e7521e8`.
  The exact 510,556-KiB disposable output was removed immediately; no private bytes were copied
  into the public repository or package.
- `PRODUCTION`: standard-library SQLite globally indexes pair and neuron/field identities with
  bounded Python memory. Canonical NDJSON preserves manifest/file/row order and all provenance;
  the receipt binds manifest, profile, engine, policies, counts, output bytes, and hashes.
  Promotion is fsynced and receipt-last; idempotent complete output is reverified; strict profile
  conflicts, unmarked unreceipted output, and unrelated destination files are preserved.
- `SENSITIVITY`: temporarily returning from the SQLite uniqueness conflict path made the strict
  cross-file duplicate oracle fail because no exception was raised. Restoring the global policy
  guard returned the oracle to PASS.
- `QUALITY`: all 104 engine tests, Ruff, strict mypy, sdist/wheel build, and fresh-wheel public
  normalization/profile-round-trip smoke pass locally. The existing six-entry
  macOS/Ubuntu/Windows ×
  Python 3.10/3.12 CI matrix carries the fixed canonical hashes; remote matrix execution remains
  E4-12 rather than being inferred from this macOS run.

## 17. E4-B2 licensed FlyBody actuator catalogs and explicit 90→78 crosswalk

Status: **implemented and verified locally; supported-platform CI execution remains E4-12**

### 17.1 Intended outcome and user-visible promise

A FlyBrian experiment can bind a stable, inspectable actuator authority instead of an anonymous
array length. Historical 90-value motor-command artifacts can be replayed against the current
FlyBody 78-actuator model without positional guessing: every source identity is either mapped to
one named target identity or returned as one named, explained drop. The same public engine API is
the authority for local execution, cloud execution, the experiment catalog, and DigiFly playback.

The public package owns two immutable catalogs and one immutable crosswalk:

- `org.flybrian.actuators.flybody@d015e9b`: the exact 78-actuator order and resolved control ranges
  compiled from pinned upstream FlyBody XML;
- `org.flybrian.actuators.historical-90@1.0`: FlyBrian's explicitly modified historical 90-entry
  experiment-vector authority; and
- `org.flybrian.crosswalk.historical-90-to-flybody-78@1.0`: 78 named mappings and 12 named drops.

Catalog order remains the declared external vector order, but array position is never identity.
The crosswalk operates only on stable actuator IDs and validates both catalog IDs, versions, and
canonical hashes before transforming a vector.

### 17.2 Primary-source, license, and modification record

The upstream authority is `TuragaLab/flybody` commit
`d015e9bfe441bd90ae431bac24c55cb74bdbce26` (also the currently installed FlyBody 0.1.0 direct-url
commit on the acceptance host):

- repository: `https://github.com/TuragaLab/flybody`;
- exact XML:
  `https://raw.githubusercontent.com/TuragaLab/flybody/d015e9bfe441bd90ae431bac24c55cb74bdbce26/flybody/fruitfly/assets/fruitfly.xml`;
- XML byte size: 65,787; SHA-256:
  `d14946fd0311025ecca70c8eeb5de80e1fe18700d3072be37ecbb18d33d80fd8`;
- exact Apache-2.0 license:
  `https://raw.githubusercontent.com/TuragaLab/flybody/d015e9bfe441bd90ae431bac24c55cb74bdbce26/LICENSE`;
- license byte size: 11,357; SHA-256:
  `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`.

MuJoCo compilation of that exact XML resolves `nu = 78`. The 78-entry public catalog is a
modified representation extracted from those Apache-2.0 source bytes: it preserves compiled
actuator order, exact names, and exact resolved `ctrlrange` decimal values while adding FlyBrian
stable catalog metadata, body-region/joint labels, and explicit control-domain labels. The source
XML itself is not bundled.

The historical 90-entry catalog is FlyBrian-authored migration data informed by that upstream
model. It changes the antenna IDs `antenna_left/right` to historical
`antenna_extend_left/right`, inserts `tarsus3` and `tarsus4` after each leg's `tarsus2`, and then
places the eight adhesion controls at positions 82–89. It must be described as modified historical
FlyBrian behavior, never as an upstream FlyBody 90-actuator claim. The 12 added tarsal entries use
the historical generic `[-1, 1]` range and have no direct upstream actuator.

The distribution keeps the engine under MIT and bundles the unmodified Apache-2.0 license plus a
third-party attribution/modification notice in source and wheel artifacts. Package tests must
inspect both archives; a repository-only notice is insufficient.

### 17.3 Exact catalog semantics

An actuator retains the existing stable fields: ID, body region, joint/function, increasing exact
decimal control range, control unit/domain, and source. Catalog construction rejects blanks,
duplicates, case-collisions, non-finite/reversed bounds, and unsupported authority identity.

The upstream 78 catalog uses the compiled XML actuator name as `actuator_id`. The 48 leg controls
use six explicit regions (`T1_left` through `T3_right`). The eight `adhere_*` controls use the
`normalized_activation` domain and exact `[0, 1]` range. Other controls use the
`mujoco_control` domain; this contract does not overclaim that every general actuator is a torque,
angle, or SI quantity merely because its range resembles a joint limit. Exact XML source and
compiled behavior remain the semantics.

The historical 90 catalog preserves its exact legacy names and vector order. It is not selected
by a hidden default and does not make the current model accept 90 controls directly. Consumers
must bind the exact catalog identity/hash carried by an experiment artifact.

### 17.4 Crosswalk, result, and canonical identity

Each crosswalk entry contains exactly:

```text
source_actuator_id
status = mapped | dropped
target_actuator_id = stable ID when mapped, null when dropped
reason_code
source
```

Mapped entries require a target ID and reason `same_control` or `renamed_control`; dropped entries
forbid a target and use `no_upstream_actuator`. Every source catalog ID appears exactly once.
Every target catalog ID appears exactly once in this 90→78 profile. Duplicate source entries,
duplicate mapped targets, unknown IDs, missing source coverage, non-surjective target coverage,
bad disposition/target combinations, or source/target catalog hash mismatch reject construction
or application before returning a result.

The first 22 controls map by name except the explicit aliases
`antenna_extend_left → antenna_left` and
`antenna_extend_right → antenna_right`. For every one of the six leg regions, `coxa_abduct`,
`coxa_twist`, `coxa`, `femur_twist`, `femur`, `tibia`, `tarsus`, and `tarsus2` map by the complete
stable ID. That region's `tarsus3` and `tarsus4` are dropped individually. All eight adhesion
controls map by stable name. Positional arithmetic may be used only by a caller to pair a vector
with its already-bound source catalog; it may not select crosswalk identity or disposition.

Applying the crosswalk to a complete source vector returns:

- the 78 target values in declared target-catalog order;
- 12 drop records containing source ID, exact source value, and reason;
- source/target catalog IDs, versions, and hashes;
- crosswalk ID, version, and hash; and
- a canonical result SHA-256 over all authority metadata, values, and drops.

Values are exact decimal lexemes; binary floats, booleans, NaN, and infinity are rejected. Vector
length mismatch rejects without a partial result. Applying an already-78 vector is not a
crosswalk operation and must not silently pass through this profile.

### 17.5 State machine and lifecycle edges

```text
catalog/crosswalk invalid                              -> AUTHORITY_INVALID
exact catalogs + complete validated crosswalk          -> READY
READY + bound 90-value exact vector                    -> TRANSFORMING
TRANSFORMING + 78 mappings + 12 recorded drops         -> COMPLETE
TRANSFORMING + length/hash/identity/value mismatch      -> REJECTED
COMPLETE + same authorities and source values           -> COMPLETE (identical bytes/hash)
```

| Edge/lifecycle | Required resolution |
| --- | --- |
| upstream XML changes under a reused URL | pinned commit and XML SHA detect it; publish a new catalog version |
| actuator reorder with unchanged names | catalog hash changes; old artifacts retain their exact authority |
| renamed antenna controls | only the two explicit `renamed_control` entries map them |
| virtual tarsal values are non-zero | preserve each exact value in a drop record; never merge into `tarsus2` |
| unknown legacy actuator | invalid/incomplete crosswalk; never drop by fallback |
| target appears twice | reject crosswalk; never last-value-wins |
| input has 89/91 values | reject before transformation |
| binary float or non-finite input | reject; caller must supply exact decimals |
| package lacks Apache license/notice | build acceptance fails |
| old result replay | resolve exact catalog/crosswalk hashes; never `latest` |

### 17.6 Scale, portability, and ownership boundary

For source catalog size `S` and target size `T`, validation and application are `O(S + T)` time
and retained state. No hard-coded 90/78 check belongs in the generic types; the named constants
carry those cardinalities. Implementation uses immutable Python data and exact decimals only, so
it has no MuJoCo runtime dependency and behaves the same on macOS, Linux, and Windows. MuJoCo is a
development oracle for the pinned XML, not a package dependency or import-time authority.

This slice does not implement motor-neuron mapping, muscle dynamics, simulation execution,
DigiFly rendering, service cutover, or a general catalog registry. It does not edit or wrap the
private service table. Read-only comparison is acceptance evidence only; the public owner is
derived from the cited upstream source and the user-authorized FlyBrian migration semantics.

### 17.7 Test-trust and acceptance gate

Implementation begins with red tests for absent public catalog/crosswalk/result authorities.

| Oracle | Required evidence |
| --- | --- |
| upstream authority | exact 78 order/names/resolved ranges match compilation of pinned XML; fixed catalog hash |
| historical authority | exact 90 order/names/ranges match read-only historical evidence; fixed catalog hash |
| complete mapping | 90 entries, 78 mapped, 12 dropped; every source once and every target once |
| aliases/drops | exact two antenna renames; exact six-region `tarsus3/tarsus4` drop set |
| application | distinctive exact values land on named targets; drops preserve IDs/values/reasons |
| rejection | malformed catalogs/crosswalks, hash/length mismatch, floats, non-finite values all fail |
| canonical identity | construction-order variation preserves bytes; source/range/value/disposition mutation changes hash |
| sensitivity | replacing named lookup with the historical positional shortcut makes the distinctive-value oracle fail |
| packaging | sdist and wheel contain Apache-2.0 license and third-party notice; clean-wheel public smoke passes |
| quality | full pytest, Ruff, strict mypy, build, and supported-platform CI matrix pass |

E4-B2 becomes verified only after the full local gate and read-only 90-table comparison pass.
Remote supported-platform execution remains E4-12 and may not be inferred from one macOS run.

### 17.8 Forecast and contract-to-diff map

Expected production diff: the public embodiment module (or one narrowly named catalog module),
stable exports, license/notice assets, focused tests, README, package metadata, and this contract.
No web, service, Maestro, acquisition, or simulation-backend file belongs to this slice.

| Changed surface | Contract authority |
| --- | --- |
| public catalog constants | §17.2–17.3 pinned source, stable IDs, ranges, order, and source claims |
| crosswalk/result types and apply function | §17.4–17.5 complete named dispositions and exact canonical result |
| package license/notice metadata | §17.2 and §17.7 archive-level compliance |
| focused actuator tests | §17.5–17.7 lifecycle, rejection, sensitivity, and authority oracles |
| README/public exports | §17.1 user-visible promise and single public owner |

Any source mismatch, unresolved unit claim, missing disposition, license ambiguity, or need for a
private runtime dependency returns this slice to specification state before production changes.

### 17.9 E4-B2 implementation evidence — 2026-08-27

- `RED`: focused test collection failed because the public catalog constants, crosswalk types,
  result, and apply function did not exist.
- `UPSTREAM-READONLY`: MuJoCo compiled the locally installed XML whose 65,787 bytes match the
  pinned upstream SHA-256. All 78 public catalog names, declared order, and exact resolved control
  ranges matched `MjModel` actuator output. MuJoCo remains absent from runtime dependencies.
- `MIGRATION-READONLY`: all 90 public historical catalog names, body regions, joint labels, and
  exact ranges matched the private historical table. All 90 named public dispositions matched the
  private index oracle: 78 mapped targets and 12 dropped tarsal controls. No private source byte
  was modified, copied, imported at runtime, or included in either distribution artifact.
- `IDENTITY`: public catalog SHA-256 is
  `8469956cd66465f4191e6597d823c3bd6cb08635ab1e041a94631383a971ab92`; historical catalog
  SHA-256 is `8f24d150b6efdd3e98d5710d901ad375bf48470f7a8a7387802ac167ed192300`;
  crosswalk SHA-256 is `08f112f8fd8d37d2bbcfc97bdfede601dd0613c7719850e250ee4828b7ac65ee`.
  The distinctive `0..89` source vector produces result SHA-256
  `a9935d1e014f8db697fdcb834bfec01ee3ef6af1878c19c331620f6163b3edfc`.
- `SENSITIVITY`: temporarily replacing named target assembly with `source_values[:78]` made the
  distinctive-vector oracle fail at `coxa_abduct_T1_right` (`30` observed instead of the named
  source value `32`). Named assembly was restored and the focused suite returned to PASS.
- `LICENSE`: the bundled upstream Apache-2.0 file is exactly 11,357 bytes with SHA-256
  `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`. Wheel and sdist
  inspection verified that exact file plus `THIRD_PARTY_NOTICES.md`; the notice identifies the
  pinned source, upstream project/authors, and FlyBrian modifications.
- `QUALITY`: all 114 tests pass in the scientific Python 3.12 environment; Ruff and strict mypy
  pass; sdist/wheel build passes; clean-wheel import and 90→78 application smoke pass through only
  public exports. Remote macOS/Ubuntu/Windows × Python 3.10/3.12 execution remains E4-12 and is not
  inferred from this host.

## 18. E4-B3 licensed muscle authorities and historical Hill execution profile

Status: **implemented and host-accepted; supported-platform CI remains E4-12**

### 18.1 Outcome and truth boundary

A historical muscle-mediated FlyBrian experiment can bind explicit muscle parameters, mapping
rules, drive conversion, dynamic equations, integration behavior, and state instead of relying on
an unversioned private module. A user can inspect and run the same bounded historical Hill
approximation locally through the public engine, while separately inspecting the exact official
FlyMimic foreleg parameters from which part of that approximation was derived.

Two authorities must remain visibly distinct:

1. **Official FlyMimic T1 authority:** 15 left-foreleg muscles and exact source parameters from the
   pinned OpenSim model. This is cited, Apache-2.0 source data. It is not a six-leg model.
2. **FlyBrian historical six-leg approximation:** the rounded 15-muscle table copied across six
   legs, FlyBrian-calibrated moment arms and standing reference angles, T2/T3 strength scales,
   MANC target bridge, spike-rate sigmoid, and FlyBrian-authored Hill approximation. This is a
   migration/reproduction profile, not an assertion that FlyMimic validated those choices.

The default public discovery surface labels the second authority `historical_experimental`.
Callers must opt into it by exact profile ID/version/hash. No API named merely `muscle` or `latest`
may silently choose it.

### 18.2 Primary sources, license, and pinned bytes

Primary authorities checked on 2026-08-27:

- FlyMimic repository: `https://github.com/gizemozd/FlyMimic`, Apache-2.0, commit
  `9ea1131626cd76f7203b74076ef8f0e9cab30bef`;
- exact OpenSim source:
  `flymimic/assets/models/opensim/best_combined.osim`, 483,413 bytes, SHA-256
  `091a173b9cfb26a64228935c6f6ebfc93c26a9425a0b5e5c1bb463c644cb89de`;
- converted MuJoCo source:
  `flymimic/assets/models/best_combined_arm_cvt3.xml`, 49,643 bytes, SHA-256
  `59d7db31eb756c61661065c16cfbbb1e3400da1a9df8b1f02fe79dc87bd48724`;
- exact FlyMimic license: 11,357 bytes, SHA-256
  `c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4`;
- paper: Özdil et al., *Musculoskeletal simulation of limb movement biomechanics in Drosophila
  melanogaster*, ICLR 2026, arXiv `2509.06426`, OpenReview `6lEjX1getx`.

The Apache license is byte-identical to the license already bundled for FlyBody. B3 adds FlyMimic
source/citation/modification attribution to `THIRD_PARTY_NOTICES.md` and verifies that the shared
license plus updated notice occur in both source and wheel archives. Neither the 483-KiB OpenSim
model nor the MuJoCo XML is bundled by this slice.

The pinned OpenSim file declares exactly 15 `Millard2012EquilibriumMuscle` entries, all with rigid
tendon (`ignore_tendon_compliance=true`), exact full-precision maximum isometric force, optimal
fiber length, tendon slack length, zero optimal pennation, maximum contraction velocity, and
activation/deactivation constants `0.0001`/`0.00040000000000000002` seconds. The converted MuJoCo
file likewise has exactly 15 muscle actuators. The official project and paper describe the
muscle-driven left foreleg; its ground example supports the remaining legs through direct torque.
The private historical 90-muscle extrapolation therefore cannot be relabeled as official.

### 18.3 Discovery census and historical deviations

Read-only comparison found that the private 15-muscle values are rounded derivatives of the
pinned OpenSim values. Maximum absolute rounding differences are:

```text
F_max:   0.004758622609079 mN
L_opt:   0.000049243987291333 mm
L_slack: 0.00004783390114995 mm
V_max:   0.045275132706327 L_opt/s
pennation: 0 rad
```

The historical six-leg builder creates 90 muscles by repeating those rounded T1 values with
strength scales `T1=1`, `T2=1.2`, `T3=1.4`. It uses 10/40 ms activation/deactivation constants,
not FlyMimic's 0.1/0.4 ms source constants. It adds 15 calibrated/placeholder moment arms, six
per-leg standing-angle tables, a length-sensitivity cap, fiber-length/velocity clamps, a passive
force cap, and output torque scaling. Those additions are FlyBrian historical choices.

The historical builder's documentation advertises `t2_f_max_scale`, `t3_f_max_scale`,
`tau_act`, and `tau_deact`, while production behavior reads `t2_scale`/`t3_scale` and ignores the
tau overrides. Public historical import records the actually effective values and emits ignored
legacy-option evidence; it does not silently pretend the advertised overrides took effect. A
corrected caller-selected profile may vary tau/scales, but its canonical identity must change.

For the 396 historical leg motor-anatomy rows, the private bridge classifies 242 as mapped, 88 as
known targets with no FlyMimic equivalent, and 66 as generic leg targets. It emits 312
neuron→muscle links. Per-leg mapped-neuron counts are `T1L=49`, `T1R=49`, `T2L=38`, `T2R=37`,
`T3L=34`, `T3R=35`. Both T1 legs drive all 15 reference muscle identities; T2/T3 drive 12 because
the three promotor identities have no MANC neurons in those segments. Unknown, no-equivalent, and
generic rows must become dispositions; none may gain baseline torque through an inferred target.

### 18.4 Public owners and immutable authorities

One new narrowly named public module owns:

- `FLYMIMIC_T1_MUSCLE_CATALOG`: exact 15-entry full-precision source catalog;
- `FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG`: exact 90-entry historical effective catalog;
- `FLYBRIAN_HISTORICAL_MANC_MUSCLE_PROFILE`: the target/body/muscle/actuator bridge with explicit
  confidence and no-equivalent/generic dispositions;
- `FLYBRIAN_HISTORICAL_HILL_BUG_COMPATIBLE_PROFILE`: equations, constants, clamps, scaling,
  integration, and the historical per-projection state-advance defect;
- `FLYBRIAN_HISTORICAL_HILL_CORRECTED_PROFILE`: the same declared approximation with one state
  advance per muscle and first-declared/primary-DOF kinematics;
- `MuscleActivationState`, step input/result records, and pure state-transition functions; and
- an explicit spike-count→drive profile/function.

Stable muscle IDs include leg identity; repeating the raw T1 muscle name is not sufficient for a
90-entry catalog. Catalog array position is never muscle identity. Every parameter is unit-bearing
and represented by an exact decimal lexeme in canonical authority JSON. Catalog/profile hashes
change if any source value, historical rounding, moment arm, standing angle, sign, clamp, scale,
normalizer, or equation version changes.

The public module must not import private FlyBrian code, pandas, NumPy, MuJoCo, OpenSim, or a
network client at runtime. The pinned files are acceptance oracles, not runtime dependencies.

### 18.5 Historical spike-count to drive contract

Input is one exact counting window plus a declared muscle→ordered-neuron pool:

```text
non-negative integer spike count per neuron
positive finite window_duration_s
positive finite rate_normalizer_hz and sigmoid_k_hz
optional positive extensor/flexor normalizers supplied together or neither
```

For each pool, missing neuron counts are zero. Mean firing rate is the arithmetic mean of each
neuron's `count / window_duration_s`. Stable pool order and `math.fsum` define aggregation.
Historical drive is:

```text
drive = 1 / (1 + exp(-(mean_rate_hz - selected_normalizer_hz) / sigmoid_k_hz))
```

Flexor classification requires `flexor` in the source muscle name; extensor requires `extensor` or
the historical coxa keywords `sternal`, `pleural`, `remotor`, or `promotor`; remaining identities
use the extensor normalizer only when dual mode is explicitly selected. Empty pools produce exact
zero. A populated pool with zero spikes retains the historical non-zero sigmoid baseline (about
0.02298 under 30/8); it must not be described as spontaneous biological activation.

Negative/non-integral counts, zero/negative duration, one-sided dual normalizer configuration,
unknown muscle IDs, duplicate neuron IDs in one pool, booleans, and non-finite numbers reject.

### 18.6 Historical Hill state transition

The state is only activation `a` plus exact profile/catalog identities. State is passed in and a
new immutable state/result is returned; there is no mutable global or hidden object history.

For neural drive `u`, time step `dt`, angle `q`, velocity `v`, and one historical muscle:

```text
u_c = clamp(u, 0, 1)
tau = tau_act if u_c > a else tau_deact
a_next = clamp(a + ((u_c - a) / tau) * dt, 0, 1)       # explicit Euler

sensitivity = min(moment_arm_mm / L_opt_mm, 1)
L_norm = clamp(1 + sensitivity * (q - ref_angle), 0.5, 1.5)
V_norm = clamp(sensitivity * v, -0.95 * V_max, 5 * V_max)
f_L = exp(-((L_norm - 1) / 0.45)^2)

if V_norm <= 0:
    f_V = (V_max + V_norm) / (V_max - V_norm / 0.25)
else:
    f_V = min((V_max * 1.8 + V_norm) / (V_max + V_norm), 1.8)

if L_norm <= 1:
    f_passive = 0
else:
    f_passive = (exp(4 * ((L_norm - 1) / 0.6)) - 1) / (exp(4) - 1)

F_active = F_max_mN * a_next * f_L * f_V
F_passive = min(F_max_mN * f_passive, F_max_mN * 0.5)
F_total = F_active + F_passive
torque_mN_mm = F_total * moment_arm_mm * cos(pennation_rad)
```

The per-muscle result exposes activation, normalized length/velocity, active/passive/total force,
and torque. Under the corrected profile, a leg step computes one transition using the muscle's
first declared (primary) DOF kinematics, then contributes that torque to every explicit DOF/sign
entry. Contributions are accumulated in declared muscle order with `math.fsum`. The historical
private loop instead advances a multi-DOF muscle once per DOF and uses each projection's kinematics;
the separately named bug-compatible profile reproduces that defect for exact experiment reruns.
It is never selected as corrected behavior. Recorded motor commands remain the authority for
strict artifact replay without a dynamics rerun.

### 18.7 Numeric, determinism, and result identity

Authority/config values serialize as exact decimal strings. Execution uses validated IEEE-754
binary64 and Python `math`; booleans, NaN, infinities, negative `dt`, invalid state, non-positive
physical constants, and incomplete joint state reject before transition. A zero time step is
permitted only for read-only force inspection and leaves activation unchanged.

Isolated force/drive/activation comparisons use absolute and relative tolerance `1e-12` against
the historical Python oracle. Bounded multi-muscle traces use `1e-10`. The result's canonical
scientific identity includes profile/catalog/bridge hashes, ordered input/state lexemes, output
binary64 hexadecimal representations, and declared tolerance; formatted decimal display is not
the authority. Supported-platform CI must compare those canonical result bytes for the fixed
oracle and separately apply the declared numerical tolerance to any platform math variation.

A state/result may be checkpointed and resumed only with exact matching profile, muscle catalog,
muscle ID set/order, and prior-state hash. Reusing activation state under changed tau, timestep,
muscle parameters, or body mapping rejects.

### 18.8 Adapter and artifact boundary

B3 produces named joint torques and state traces. It does not write directly into a 78-value
MuJoCo array. A separate embodiment adapter must bind each named DOF to the pinned actuator
catalog, declare the historical `0.01` mN·mm→model-control scaling, validate target control ranges,
and emit the existing motor-command artifact schema with catalog/profile hashes. Non-leg and
adhesion controls are explicit adapter inputs; they are never silently passed from an undeclared
global vector.

The current official FlyMimic model has its own 15 spatial tendons, attachment sites, body rig,
passive joint properties, and actuator dynamics. A FlyBody torque adapter is not equivalent to
running that model. UI labels and artifact provenance must distinguish:

- `flymimic_official_left_foreleg`;
- `flybrian_historical_hill_flybody_adapter`; and
- future corrected/validated muscle-body profiles.

### 18.9 State/lifecycle and failure matrix

```text
invalid catalog/profile/bridge                         -> AUTHORITY_INVALID
valid exact authorities + initial activation state     -> READY
READY + one validated drive/joint/dt frame              -> STEPPING
STEPPING + all named transitions/accumulations          -> FRAME_COMPLETE
FRAME_COMPLETE + checkpoint                             -> READY (next frame)
any state + identity/non-finite/domain mismatch          -> REJECTED (prior state unchanged)
recorded motor artifact + exact actuator catalog         -> REPLAYABLE (no dynamics rerun needed)
```

| Edge | Required resolution |
| --- | --- |
| official 15 catalog requested as six-leg | reject; no extrapolation |
| historical tau option was present but ineffective | preserve requested/effective distinction in import evidence |
| known MANC target has no muscle equivalent | disposition; never zero-drive pseudo-muscle |
| generic leg target | ambiguous disposition; never fan out |
| mapped pool has no spikes | historical sigmoid baseline, explicitly reported |
| muscle acts on two DOFs | one activation transition, two signed torque projections |
| missing drive for a declared muscle | explicit zero drive; no hidden `0.02` experiment-script fallback |
| missing joint state | reject frame unless the selected profile explicitly declares a fixed-state fallback |
| timestep exceeds activation constant | explicit Euler/clamp behavior remains profile data; validation may warn but not silently change solver |
| force/velocity exponential overflow | reject non-finite frame; no partial state promotion |
| target torque exceeds actuator range | adapter disposition/reject per explicit policy; never silent clip |
| interrupted trace | last complete checkpoint is durable; partial frame has no receipt |

### 18.10 Scale, non-goals, and retirement map

For `M` muscles, `D` declared muscle→DOF projections, and `N` spike-pool memberships, a frame is
`O(M + D + N)` time and `O(M + D)` state/result memory. No corpus-count or 90-muscle constant is a
generic engine capacity limit.

B3 does not claim walking, validate the historical approximations biologically, port every C-series
experiment script, bundle FlyMimic meshes/models, implement MuJoCo physics, or close local/cloud
equivalence. It does not hide experiment-script overrides such as anti-gravity boosts, per-muscle
resting-potential changes, reflex controllers, or default `0.02` drives inside the core Hill
profile. Those become separate structured controller/profile inputs when each historical family is
converted.

Intended deletion after E4-D consumer cutover: private duplicate parameter tables, MANC bridge,
drive conversion, and Hill equations. Historical experiment scripts remain provenance/migration
oracles until their configs/results are imported; they are not bulk-deleted by B3. Private
MuJoCo/body/render code remains until the separate physical adapter and DigiFly acceptance prove
replacement.

### 18.11 Test-trust and acceptance gate

Implementation starts with red tests for absent official/historical catalogs, profiles, mapping,
state, and pure transition APIs.

| Oracle | Required evidence |
| --- | --- |
| official catalog | parse pinned OpenSim read-only; exact 15 names/full-precision parameters/tau/rigid-tendon values and fixed hash |
| historical catalog | exact 90 IDs, rounded parameters, scales, moment arms, references, and fixed hash match private evidence read-only |
| MANC bridge | all 396 rows reproduce the 242/88/66 classification, 312 links, per-leg counts, and explicit dispositions |
| isolated dynamics | activation, force components, and torque match independently calculated fixtures at concentric/isometric/eccentric/passive/clamp edges |
| bounded trace | historical tibia eight-step oracle matches within `1e-12`; result/checkpoint hashes are fixed |
| drive conversion | empty/zero/mixed pools and default/dual sigmoid fixtures match historical values; invalid domains reject |
| multi-DOF state | one state advance per frame; sensitivity mutation advancing per projection must fail |
| authority identity | any parameter/sign/clamp/source/state mutation changes canonical hashes or rejects resume |
| packaging | shared Apache license and updated FlyMimic notice appear byte-correct in sdist/wheel |
| quality | full pytest, Ruff, strict mypy, build, clean-wheel public smoke, and supported-platform CI pass |

Historical private numerical comparison is migration evidence, not a runtime dependency. At least
one equation, one tau/config trap, one bridge disposition, and the multi-DOF state-advance rule are
mutated during sensitivity review. Any mismatch returns this slice to specification before the
implementation or parent ledger is promoted.

### 18.12 Forecast and contract-to-diff map

Expected diff: one public muscle-dynamics module, stable exports, focused tests, README, updated
third-party notice/package archive evidence, and this contract. Reuse the existing `Muscle`,
`MuscleCatalog`, `MuscleProfile`, mapping result, actuator catalog, and artifact schemas; do not
create parallel graph/artifact authorities. No service, web, Maestro, cloud, or renderer file
belongs to B3.

| Changed surface | Contract authority |
| --- | --- |
| official/historical catalog constants | §18.2–18.4 source truth, modifications, exact units/identity |
| drive/bridge profiles | §18.3–18.5 source classification, sigmoid, explicit dispositions |
| pure Hill state/step/leg result | §18.6–18.9 equations, state, numeric identity, failure behavior |
| focused tests | §18.9–18.11 behavioral, migration, sensitivity, and portability oracles |
| notice/README/exports | §18.1–18.2 public promise, license, and truthful labeling |

Any production edit not explained by this map, or contract requirement without implementation or
explicit open disposition, blocks B3 closure.

### 18.13 Implementation and acceptance evidence (2026-08-27)

Implemented by `src/flybrian_engine/muscle_dynamics.py` and public package exports without a
runtime dependency on FlyMimic, the private FlyBrian service, NumPy, pandas, OpenSim, or MuJoCo.
README and third-party notices preserve the official-versus-historical truth boundary. Fixed
authorities are:

```text
official FlyMimic 15 catalog:      5e35c1343bcdc2f1744cc1acbe9e3e780a404d121af4cdb982917cb3bb483a53
historical FlyBrian 90 catalog:    985d57db75882bc541c42ff6b9426369e8c98666b63d53211e4e428c37c94f51
historical DOF projections:        74cb6e0d5eca850f928dd186ab225e768e64eaa50a798848138388f641d3852a
historical MANC target bridge:     46b914a7b48c414ec8c96258114434533a4a150efba091b39584b712355685d9
MANC muscle mapping profile:       bf2530b1b1b1fbc9272e9095c48d330c82e9ae2895252a5385dc6712b4ba7ea4
historical drive profile:          0ff78dbcd8c18aec64d4f1c838f36f8df0b1512df9200d75deb133cecdc93d3a
bug-compatible Hill profile:       bec0bbad29de3cd1dea8c7736ae1c831249da4e8b060d6f5e067a40cfd903e30
corrected Hill profile:            03c982feb92a1acf9058ce840977f912c3e363b193c91e63d7f8fd8daf922600
```

Read-only acceptance against pinned upstream and private migration authorities proved:

- downloaded OpenSim bytes were exactly 483,413 bytes with the §18.2 SHA-256; XML parsing found
  exactly 15 muscles, and every public parameter/tau/rigid-tendon value matched its source decimal;
- all 90 effective historical definitions and all 108 projection rows matched the untouched
  private builders; the largest Decimal-to-private-binary64 parameter difference was
  `2.842170943040401e-14` from historical float scaling;
- the 396 leg rows emitted 312 neuron→muscle links, 78 selected muscle definitions, 88
  muscle→actuator links, 88 `unknown_muscle_target` dispositions for known no-equivalent targets,
  and 66 `ambiguous_target` dispositions for generic targets; and
- a complete deterministic T1L bug-compatible frame matched private joint torques with maximum
  absolute difference `4.440892098500626e-16`.

The permanent focused suite covers official/historical hashes, the eight-step tibia trace,
default/dual drive oracles, invalid domains, corrected-versus-legacy state advancement, and
independent concentric/isometric/eccentric/passive/clamp equations. Sensitivity cases prove that
equation-width, projection-sign, bridge-confidence, tau, and state-advance mutations change an
authority/result identity or reject reuse.

Host OA gates passed from the accepted source tree: 124 pytest tests; Ruff; strict mypy over 30
source files; isolated sdist/wheel build; byte-identical 11,357-byte Apache license and 3,042-byte
notice in both archives; and clean-wheel public import plus 15-state/6-torque step. Remote
macOS/Ubuntu/Windows × Python 3.10/3.12 execution remains E4-12 and is not inferred from this host.
