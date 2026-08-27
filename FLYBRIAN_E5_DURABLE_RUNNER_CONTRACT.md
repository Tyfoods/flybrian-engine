# FlyBrian E5 Durable Local Runner Contract

Status: **durable public checkpoint implemented; connector, publication, and cross-platform evidence open**

Date: 2026-08-27

Parent authorities: `FLYBRIAN_ENGINE_EXTRACTION_CONTRACT.md` E5 and ENG09–ENG11;
FlyBrian launch A16–A20. This child narrows those requirements without weakening them.

## 1. Outcome

A researcher can install the public `flybrian-engine` package on a supported desktop, start
one loopback runner, submit a validated experiment, disconnect, reconnect by durable run ID,
observe an honest lifecycle, cancel work where cancellation is enforceable, and retrieve the
same checksummed public artifact manifest used by FlyBrian cloud execution. A browser never
receives runner authority merely because localhost is reachable. Runner replacement or package
uninstall never removes experiment specifications, status records, manifests, or artifacts.

The initial E5 implementation is a public execution daemon and protocol, not the proprietary
FlyBrian interface, account system, cloud scheduler, AI harness, billing layer, or renderer.

## 2. Protected boundaries and non-goals

- `flybrian-engine` owns neutral validation, backend admission, local job persistence, process
  isolation, cancellation, and authorized artifact retrieval.
- `flybrian-serve` remains the proprietary cloud control plane. E5 does not edit or vendor it.
- FlyBrian web may consume E5 only through a same-origin server connector or a separately
  specified desktop connector. Direct cross-origin browser access is denied.
- E5 does not publish the package, claim Windows/Linux execution evidence, invent MANC/FlyWire
  ingestion, implement billing, or claim local/cloud numerical equivalence.
- The existing synchronous `POST /v1/runs` alpha remains compatible during E5 migration. New
  durable clients use `/v1/jobs`; removal requires a future protocol version and migration.

## 3. Terms and authorities

- **job ID / run ID**: one opaque identifier, 1–64 characters, already constrained by
  `_validated_identifier`. E5 does not create two identities for one attempt.
- **runner root**: user-selected durable directory. It contains scientific run outputs and a
  hidden `.runner-v1` control directory. The package installation directory is never a data
  root.
- **attempt**: one admitted execution of one canonical experiment/backend pair.
- **accepted**: schema and backend compatibility passed and the durable request/status record
  was atomically committed. HTTP receipt alone is not acceptance.
- **terminal state**: `succeeded`, `failed`, `cancelled`, or `outcome_unknown`.
- **manifest authority**: manifest 1.1 validated by the public artifact contract; runner status
  may point to it but cannot rewrite scientific provenance.

## 4. Invariants

`INV-E5-DURABLE-1`: acceptance atomically persists canonical input and a `queued` status before
the response reports success. A process crash after the response cannot erase the job identity.

`INV-E5-IDENTITY-1`: a job ID is immutable and non-reusable. Repeating a submission with an
existing ID returns conflict and never overwrites prior input, status, logs, or artifacts.

`INV-E5-ADMISSION-1`: FES validation, backend existence/availability, compatibility, body size,
and identifier checks finish before scientific output allocation or worker launch.

`INV-E5-STATE-1`: status revisions increase by exactly one for every committed transition.
Terminal states never transition. Timestamps are UTC RFC 3339 values and never move backward.

`INV-E5-TRUTH-1`: restart never relabels an interrupted `running` job as failed or cancelled.
Without a terminal worker receipt it becomes `outcome_unknown`; the user may inspect preserved
files and explicitly submit a new run ID.

`INV-E5-CANCEL-1`: cancelling `queued` work produces `cancelled` without worker allocation.
Cancelling `running` work first records `cancellation_requested`, then terminates the isolated
worker. Only observed worker termination permits `cancelled`; uncertain termination produces
`outcome_unknown`. Cancellation never deletes partial output.

`INV-E5-BOUND-1`: the runner launches no more than the configured worker limit. Admission can
persist additional queued jobs up to a configured queue bound; overflow returns 429 without a
job record.

`INV-E5-ARTIFACT-1`: artifact downloads resolve only manifest-declared relative paths beneath
the exact run directory, reject symlinks/path traversal, preserve media type, report immutable
size/checksum headers, and require authorization.

`INV-E5-AUTH-1`: every endpoint except minimal health requires a bearer token compared in
constant time. Tokens never appear in URLs, status files, logs, artifact manifests, or default
browser storage.

`INV-E5-ORIGIN-1`: requests carrying `Origin`, `Access-Control-Request-*`, or browser preflight
headers are denied unless a future pairing contract explicitly authorizes that exact origin.
No permissive CORS header is emitted. A valid bearer token does not override this rule.

`INV-E5-LOOPBACK-1`: the public CLI binds only `127.0.0.1` or `::1`. Library callers cannot use
the E5 server factory to bind a wildcard or non-loopback address by mistake.

`INV-E5-INPUT-1`: the worker consumes the accepted immutable request snapshot, not a mutable
caller file or subsequent UI draft. Retry is a new job ID unless the prior attempt was never
accepted.

`INV-E5-ATOMIC-1`: request/status/result receipts use same-directory temporary files followed by
atomic replacement. Readers either see the prior complete revision or the next complete one.

`INV-E5-DATA-1`: update, shutdown, or uninstall does not recursively remove the runner root.
Cleanup, if later offered, requires an explicit exact job/run target and reports recoverability.

`INV-E5-PORTABLE-1`: paths in persisted JSON and public responses are relative identifiers or
URLs, never host-specific absolute paths. Process launch uses the active Python interpreter and
argument arrays, not shell command strings.

## 5. Lifecycle state machine

States:

```text
queued -> running -> succeeded
                 -> failed
                 -> cancellation_requested -> cancelled
                                           -> outcome_unknown
queued -> cancelled
cancellation_requested -> succeeded  # a valid terminal receipt proves completion won the race
running + runner recovery -> outcome_unknown
```

Invalid transitions return conflict and do not increment the revision.

| Current | Event | Next | Required durable evidence |
| --- | --- | --- | --- |
| absent | valid admission | queued | immutable request + status revision 1 |
| queued | worker slot acquired | running | PID, start time, revision +1 |
| queued | cancel | cancelled | cancellation time, no PID/output allocation |
| running | valid manifest receipt and worker exit 0 | succeeded | manifest relative path + exit time |
| running | structured worker failure and observed exit | failed | sanitized code/message + exit time |
| running | cancel | cancellation_requested | request time before terminate signal |
| cancellation_requested | worker termination observed | cancelled | exit observation; partial files retained |
| cancellation_requested | valid manifest receipt and worker exit 0 | succeeded | completion won the cancellation race |
| running/cancellation_requested | recovery cannot prove outcome | outcome_unknown | recovery reason + prior PID |

`failed` means the runner observed a definitive execution failure. `outcome_unknown` means it
cannot prove whether execution completed. These labels are never interchangeable.

## 6. Durable layout and records

```text
<runner-root>/
  .runner-v1/
    jobs/<run-id>/
      request.json
      status.json
      worker-result.json        # written only by isolated worker
      stdout.log
      stderr.log
  <run-id>/
    manifest.json
    ... declared scientific artifacts ...
```

`request.json` fields: protocol version, run ID, backend ID, accepted UTC timestamp, canonical
experiment object, experiment SHA-256, and engine version. It contains no credential.

`status.json` fields: protocol version, run ID, state, revision, submitted/started/finished UTC
timestamps, backend ID, engine version, worker PID while relevant, cancellation time, manifest
relative path after success, and a structured sanitized error/outcome reason where applicable.
Unknown additive fields are preserved by readers; unknown state/protocol versions fail closed.

The runner creates private control directories/files with owner-only permissions where the OS
supports POSIX modes. Correctness cannot depend on POSIX-only locking or signals.

## 7. HTTP protocol 1

All JSON responses include `protocol_version: "1"`. Errors use `{error, code}` and optional
structured `issues`; they do not expose tracebacks or absolute host paths.

| Method/path | Success | Semantics |
| --- | --- | --- |
| `GET /v1/health` | 200 | minimal status/protocol only; no backends, paths, or jobs |
| `GET /v1/capabilities` | 200 | authorized backend and runner limits |
| `POST /v1/jobs` | 202 | validate, preflight, persist, enqueue; return durable status |
| `GET /v1/jobs/{id}` | 200 | reconnect to current durable status |
| `POST /v1/jobs/{id}/cancel` | 200 | idempotent for cancelled; conflict for other terminal states |
| `GET /v1/jobs/{id}/manifest` | 200 | succeeded job's validated manifest; 409 before success |
| `GET /v1/jobs/{id}/artifacts/{key}` | 200 | stream a manifest-declared artifact by key |
| `POST /v1/runs` | 201 | compatibility-only synchronous alpha retained temporarily |

Job submission accepts exactly `experiment`, optional `backend_id`, and optional `run_id`.
Unknown top-level keys are rejected so misspelled execution choices cannot be ignored.

Cache rules: health/capabilities/status use `Cache-Control: no-store`; immutable succeeded
manifest/artifacts may use `private, immutable` plus ETag derived from the recorded SHA-256.
Responses set `X-Content-Type-Options: nosniff` and do not advertise CORS.

## 8. Worker isolation and scheduler

- One scheduler owns the in-memory queue and process table; HTTP threads only admit/query/cancel.
- Each accepted job launches `sys.executable -m flybrian_engine.worker` with exact file arguments.
- Experiment content travels through the immutable request file, never command-line JSON.
- The worker writes one atomic, structured result receipt and exits. The scheduler alone commits
  the public status transition.
- Captured stdout/stderr are bounded or rotated; user-controlled experiment content is not
  interpolated into control logs.
- Startup scans all records. `queued` jobs are re-enqueued in submission order; `running` and
  `cancellation_requested` jobs become `outcome_unknown`; terminal jobs remain unchanged.
- Graceful shutdown stops admission, drains no new queued work, asks active workers to terminate,
  records observed outcomes, and closes the HTTP listener. Queued records remain reconnectable.

## 9. Install, update, connect, and uninstall

E5 package commands remain normal cross-platform Python console scripts. `serve` accepts runner
root, port, token source, worker/queue bounds, and emits one machine-readable connection record
to stdout. Generated tokens are process credentials and must be handed to a trusted connector;
the CLI does not write them into the data root.

Health and a deterministic reference job are the clean-install smoke. Updating replaces package
code but reuses compatible protocol-1 records. An unknown future control schema stops startup
with an actionable error rather than rewriting it. Uninstall removes package code only; the
user-selected runner root and results remain readable JSON/files.

Real macOS, Windows 11 x64, and Linux x64 evidence is required. CI definitions are useful but do
not substitute for runtime evidence on the named targets.

## 10. Failure and edge matrix

| Edge | Required result |
| --- | --- |
| malformed/oversized/unknown-key submission | 400/413; no durable job or scientific output |
| unsupported backend/science/dependency | 422 structured issues; no durable job |
| duplicate run ID, including terminal job | 409; original bytes unchanged |
| queue full | 429 with retry guidance; no durable job |
| missing/invalid bearer | 401 with no sensitive detail |
| any browser Origin/preflight header | 403; no CORS allow header |
| worker exits without receipt | failed only if definitive local exit is observed; otherwise unknown |
| malformed worker receipt | failed with stable internal-receipt code; receipt retained |
| restart with queued/running/terminal records | queue resumes; running becomes unknown; terminal unchanged |
| cancel queued/running/terminal/unknown ID | cancelled/requested/conflict/404 respectively |
| manifest before success | 409 |
| missing, altered, symlinked, traversing artifact | 409/404; never serve unverified bytes |
| client disconnect after admission | job continues and reconnects by ID |
| client disconnect before atomic admission | no success may be inferred; retry with chosen ID resolves ambiguity |
| disk/write failure during admission | 507 or 500; no accepted status is reported |
| shutdown during active worker termination uncertainty | outcome_unknown; files retained |

## 11. Implementation forecast

Expected production surfaces:

- `src/flybrian_engine/durable.py`: records, state transitions, scheduler, recovery;
- `src/flybrian_engine/worker.py`: isolated execution receipt;
- `src/flybrian_engine/runner.py`: authorized/origin-safe protocol adapter;
- `src/flybrian_engine/cli.py`: durable serve bounds and root options;
- exports only where they are a stable public API.

Expected tests/docs:

- `tests/test_durable_runner.py` for persistence, transitions, recovery, cancel, bounds, artifacts;
- `tests/test_runner.py` for HTTP auth/origin/request/response behavior and alpha compatibility;
- README and architecture updates; parent ledger promotion only to evidence actually obtained.

Any materially different production surface or state semantics amend this forecast first.

## 12. Required oracles

1. Record unit tests: atomic acceptance, duplicate immutability, transition/revision rules,
   recovery, unknown versions/states, and path/permission boundaries.
2. Scheduler integration: bounded workers, queue overflow, queued/running cancellation, worker
   success/failure/no-receipt, disconnect/reconnect, and clean shutdown.
3. HTTP integration: auth, Origin/preflight denial even with a valid token, size/shape/status
   codes, duplicate IDs, reconnect, manifest and verified artifact download.
4. Artifact negatives: traversal, symlink, undeclared key, checksum/size mismatch, pre-success.
5. Packaging: Ruff, strict mypy, full pytest, wheel/sdist, clean wheel install, CLI health,
   deterministic durable job, reinstall/update, uninstall-preserves-data.
6. Runtime evidence on macOS, Windows, and Linux; absence remains explicitly partial.
7. Consumer evidence: FlyBrian trusted connector submits/reconnects/cancels/retrieves without
   browser-held authority; private service uses the same released engine version and manifest.
8. Sensitivity: disabling duplicate protection, Origin denial, terminal immutability, recovery
   uncertainty, captured manifest checksum, or worker bound makes its focused oracle fail.

## 13. OA gates and acceptance ledger

| ID | Acceptance | Status |
| --- | --- | --- |
| E5-01 | Detailed state, persistence, security, portability, and failure contract | PASS — this document |
| E5-02 | Atomic durable record store and legal transition enforcement | PASS — immutable request/status admission, duplicate preservation, revisions, and terminal rejection are tested |
| E5-03 | Bounded isolated worker scheduler and restart recovery | PARTIAL — subprocess worker, queue bound, queued recovery, interrupted-running uncertainty, and reconnect pass; injected missing/malformed worker receipts and multi-worker stress remain open |
| E5-04 | Queued/running cancellation with truthful uncertain outcome | PARTIAL — queued cancellation allocates no output; real running cancellation records the request and reaches cancelled or a receipt-proven successful race; forced termination uncertainty remains open |
| E5-05 | Authorized reconnect, manifest, and verified artifact HTTP protocol | PASS — submit/status/manifest/artifact and negative auth/shape/duplicate/tamper paths pass on the local protocol |
| E5-06 | Browser-origin denial and loopback-only binding | PASS — valid-token Origin and preflight requests are denied without CORS; wildcard bind is rejected and IPv4/available IPv6 loopback construction passes |
| E5-07 | Clean shutdown/update/uninstall-preserves-data behavior | PARTIAL — queued work survives manager shutdown/restart and clean-wheel uninstall preserves a completed manifest; active-worker shutdown uncertainty and future-schema update rejection remain open |
| E5-08 | Ruff, strict mypy, full pytest, build/clean-install and mutation receipts | PARTIAL — 69 tests, Ruff, strict mypy, wheel/sdist, clean-wheel durable smoke, and three critical sensitivity receipts pass; Brian clean-wheel and real cross-platform gates remain parent evidence |
| E5-09 | Real macOS runtime | PARTIAL — macOS ARM source and clean base-wheel durable reference execution/uninstall pass; signed installer/desktop connector and optional Brian E5 path remain open |
| E5-10 | Real Windows 11 x64 runtime | OPEN |
| E5-11 | Real Linux x64 runtime | OPEN |
| E5-12 | Trusted FlyBrian connector consumer | OPEN |
| E5-13 | Released package and private-service same-version consumer | BLOCKED — no publication coordinate or authenticated registry |
| E5-14 | Local/cloud deterministic equivalence | OPEN |
| E5-15 | Contract-to-diff and diff-to-contract closure | PASS for this checkpoint — the map below accounts for every changed surface; later consumer/release work remains unmapped until it exists |

No `OPEN`, `PARTIAL`, or `BLOCKED` row may be described as complete. E5 cannot close the parent
launch until consumer, publication, cross-platform, and production-rehearsal evidence exists.

### 13.1 Evidence journal — 2026-08-27

- `RED`: the new durable test module failed collection because `flybrian_engine.durable` did not
  exist; HTTP oracles then failed with 404 and accepted browser Origin requests before routing and
  origin guards were implemented.
- `TEST`: the restored full source environment passes 69 tests, including the existing Brian2
  biological suite. Ruff reports no findings and strict mypy reports no issues across 19 files.
- `PACKAGE`: wheel and sdist build in a disposable output directory and include this contract,
  `durable.py`, and `worker.py`. A separate base-wheel environment reported truthful health,
  completed `wheel_durable`, retrieved its verified summary, then uninstalled the package while
  `<runner-root>/wheel_durable/manifest.json` remained.
- `SENSITIVITY — duplicate identity`: changing the exclusive job-directory creation to
  `exist_ok=True` made the duplicate oracle fail because no `DuplicateJobError` was raised; the
  exclusive creation guard was restored.
- `SENSITIVITY — Origin isolation`: forcing `_browser_request` false made the valid-token Origin
  oracle fail because capabilities became reachable; exact header detection was restored.
- `SENSITIVITY — artifact integrity`: disabling only the leaf checksum stayed green because the
  manifest-level verification independently caught tampering. Disabling both retrieval integrity
  layers made the tamper oracle fail; both checks were restored. This receipt documents deliberate
  defense in depth rather than counting the first non-sensitive mutation as success.
- `HOST`: all test jobs used pytest or exact disposable roots. No source/service/Maestro data was
  removed or rewritten.

### 13.2 Current checkpoint contract-to-diff map

| Changed surface | Contract authority |
| --- | --- |
| `durable.py` | E5 §§4–6, 8: records, transitions, recovery, bounds, cancellation, verified retrieval |
| `worker.py` | E5 §§4, 8: immutable request execution and structured atomic receipt |
| `runner.py` | E5 §§4, 7: loopback, bearer/Origin boundary, durable endpoints, compatibility path |
| `cli.py` | E5 §9: explicit worker/queue bounds and machine-readable connection record |
| durable/runner tests | E5 §§10–12: executable lifecycle, security, failure, portability, and sensitivity oracles |
| README, architecture, manifest, parent contract | E5 §§1–3, 9, 13: user boundary, packaging, honest status promotion |

No implementation change in this checkpoint belongs to ingestion, embodiment transforms, the
private service, FlyBrian web, publication, or cloud equivalence; those rows remain unchanged.

## 14. Contract-change procedure

When an implementation fact contradicts this contract: stop that edit, record the discovery,
amend the controlling invariant/state/failure row, add a pre-change failing oracle, then resume.
Git history is the record of superseded behavior; status rows are never silently promoted.
