# FlyBrian E2 Scientific Artifact Manifest — OA Implementation Contract

Status: **active implementation contract**

Parent authority: `FLYBRIAN_ENGINE_EXTRACTION_CONTRACT.md` E2 and
`/Users/tyroachford/Projects/flybrian-web-p14/FLYBRIAN_LAUNCH_PRODUCT_SPEC.md`
invariants 8–10, run/artifact section 10, and acceptance A11–A12/A16–A17.

## Correct-system outcome

Every completed local or cloud attempt produces one versioned scientific manifest whose run,
engine, backend, experiment, dataset, and seed identity cannot be confused with another
attempt. Available artifacts carry relative paths, byte sizes, MIME types, and SHA-256.
Requested-but-unavailable or failed artifact kinds are explicit outcomes with reasons. The
web/service may attach authorized download URLs, storage providers, retention, and tenancy,
but those decorations cannot change the public scientific identity or availability ledger.

## Reconciled current shapes

| Current producer/consumer | Existing shape | E2 treatment |
| --- | --- | --- |
| Public engine | `ArtifactManifest` with available files only | Upgrade to manifest 1.1 identity + dispositions; retain available-file fields. |
| `flybrian-serve` | result `files`, `summary`, `spike_times`, optional `video_url`, separate motor endpoint/error | Future E3/E4 adapter emits the public manifest first; hosted response decorates its records with URLs. |
| FlyBrian web durable ledger | inferred `json/plot/motorCommands/video` rows from endpoints | Future consumer ingests manifest dispositions; it does not infer MP4/motor availability from an embodied flag or URL convention. |

## Invariants

`INV-E2-ID-1`: `run_id`, engine version, backend ID/version, FES version/hash, random seed,
dataset references/checksums, scientific-execution flag, and deterministic guarantee are
manifest fields, not log prose.

`INV-E2-FILE-1`: an available artifact path is relative to the run root, cannot traverse it
lexically or through symlinks, and has a verified size and lower-case SHA-256 of its bytes.

`INV-E2-AVAIL-1`: each disposition is exactly one of `available`, `unavailable`, or `failed`.
`available` references exactly one same-kind manifest artifact and has no reason. The other
states reference no artifact and require a bounded human-readable reason. Duplicate artifact
keys or disposition kinds are invalid.

`INV-E2-TRUTH-1`: absence of a manifest/disposition is `unknown`, not `unavailable`. A
requested video that cannot render is `unavailable` or `failed`; it is never represented by a
guessed URL. Motor commands may be available while video failed.

`INV-E2-PORT-1`: the manifest contains no absolute paths, storage credentials, presigned URLs,
private account/workspace IDs, or host-specific path syntax. JSON arrays/objects serialize
identically on supported platforms.

`INV-E2-WRITE-1`: manifest persistence is replace-atomic within the run directory; readers do
not observe a partially written JSON document.

## Manifest 1.1 outcome schema

- Immutable identity: manifest schema, run ID, engine/backend/spec versions, canonical FES
  SHA-256, seed, dataset references, `scientific_execution`, and
  `deterministic_for_fixed_seed`.
- Available artifacts: unique key/kind, media type, safe relative path, byte size, checksum.
- Dispositions: unique kind, status, optional available-artifact key, optional failure reason.
- Dataset reference: public dataset ID plus optional verified SHA-256. A source release without
  a content checksum remains truthful by leaving checksum null.

Disposition kinds use public snake_case names (`standardized_results`, `motor_commands`,
`video`, `plot`, `raw_data`, `csv`, `json`, `notebook`, `log`, `summary`, `provenance`). Private
consumers may map presentation labels such as `motorCommands`; the public manifest remains
canonical.

## Forecast and deletion map

Production: `src/flybrian_engine/artifacts.py`, `reference.py`, runner serialization only if
required, and public exports. Tests: `tests/test_artifacts.py`, companion runner expectations.
Docs: README/architecture and both engine contracts.

No private code changes belong in E2. Later E3/E4 must replace server result/file inference
with public manifest production; later web work must replace `resultArtifacts()` inference
with manifest ingestion. Those deletions are not claimed by this slice.

## Test-trust plan

Pre-change RED oracles:

1. Reference manifest exposes the complete immutable identity and an available `summary`
   disposition.
2. A motor-command artifact may be available while video has a failed disposition, and the
   distinction survives JSON round-trip.
3. Traversal, symlink escape, wrong checksum/size, duplicate keys/kinds, dangling or
   cross-kind disposition references, invalid statuses/reasons, and malformed identity fail.
4. Removing a disposition relationship guard makes its targeted oracle fail.
5. Manifest write/read never exposes partial JSON and serialization is deterministic.

Closure requires all tests, Ruff, strict mypy, wheel/sdist, clean-wheel smoke, mutation
sensitivity, contract-to-diff, and a clean commit. E2 does not claim server/web consumption,
biological execution, cloud/local numerical equivalence, or package publication.

## Acceptance ledger

| ID | Oracle | Status |
| --- | --- | --- |
| E2-01 | Manifest 1.1 immutable identity | OPEN |
| E2-02 | Safe checksummed available files | OPEN |
| E2-03 | Explicit available/unavailable/failed dispositions | OPEN |
| E2-04 | Deterministic JSON + atomic persistence | OPEN |
| E2-05 | Clean package and sensitivity gates | OPEN |
| E2-06 | Private service emits public manifest | DEFERRED E3/E4 |
| E2-07 | Web ingests manifest without URL inference | DEFERRED consumer slice |
