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
| E4-04 | Streaming connection and motor-anatomy normalization | PASS for the initial two schemas — bounded fixtures and the full private migration corpus stream with exact provenance; duplicate-edge policy remains E4-05 receipt work |
| E4-05 | Deterministic canonical normalized receipt | OPEN |
| E4-06 | Explicit direct actuator transform and dispositions | PASS — stable catalogs, exact target/direction/confidence/fan-out/normalization rules, canonical graph/receipt hashes, and unknown/ambiguous dispositions pass bounded and full-corpus direct oracles |
| E4-07 | Explicit muscle-mediated transform and dispositions | PASS for graph construction — unit-bearing versioned muscles, explicit weighted fan-out, complete actuator links, canonical graph/receipt hashes, and incomplete-profile rejection pass; muscle dynamics execution remains outside this transform acceptance |
| E4-08 | Historical corpus migration comparison | PARTIAL — all 396 private leg rows transform read-only into 692 corrected links plus 90 dispositions, removing 660 historical generic zero-sign links; historical muscle profile/catalog comparison remains open |
| E4-09 | Official provider acquisition/resume/credential boundary | OPEN |
| E4-10 | License/citation/redistribution evidence | OPEN |
| E4-11 | Ruff, strict mypy, pytest, build/clean-wheel and sensitivity | PASS for E4-A/E4-B — 81 tests, Ruff, strict mypy, wheel/sdist, clean-wheel embodiment smoke, eight E4 critical mutation receipts, and exact private read-only direct rehearsal pass; later E4 segments require their own gates |
| E4-12 | macOS/Windows/Linux canonical-byte agreement | OPEN |
| E4-13 | Released package consumed by private service | BLOCKED — publication coordinate absent |
| E4-14 | Bidirectional contract/diff closure | PASS for E4-A/E4-B checkpoints — maps below; acquisition, historical muscle/crosswalk, and consumer changes remain open |

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

Status: **implementation contract; production implementation not yet started**

### 15.1 Primary-source and current-authority record

Primary sources checked on 2026-08-27:

- Janelia's MANC page identifies the dataset as CC BY, names NeuPrint Python/R programmatic access,
  links a public flat-file bucket, and records the v1.2 release date:
  `https://www.janelia.org/node/68782`.
- Current neuprint-python documentation declares explicit server/dataset selection, token argument
  or `NEUPRINT_APPLICATION_CREDENTIALS`, and custom query support:
  `https://connectome-neuprint.github.io/neuprint-python/docs/client.html`.
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

The journal canonical-hashes the request and initial provider snapshot, and records per stream:
committed byte offset, data-row count, last keyset cursor, completion, and update time. For each
page the file is flushed and fsynced before an atomic journal replacement. Resume truncates each
`.part` file to its journaled offset before refetching, so a crash after bytes but before journal
commit cannot duplicate rows. Journal advancement before durable bytes is prohibited.

Finalization flushes files, obtains a second provider snapshot, and requires exact equality with
the first. It then constructs manifest 1.0 with computed SHA-256/size/row counts, verifies through
the E4-A owner, writes the canonical acquisition receipt and manifest atomically, and renames part
files without overwriting an existing final. No final artifact appears before all checks pass.

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
