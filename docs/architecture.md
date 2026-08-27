# Architecture and compatibility

The dependency arrow points one way:

```text
flybrian-engine <- flybrian-serve (private control plane)
flybrian-engine <- local runner / desktop connector
```

The engine never imports either consumer. A backend registers a stable ID, version,
capabilities, and execution function. Every run hashes canonical input and emits an artifact
manifest. Local and cloud consumers therefore exchange the same schema and output envelope.

FES `1.0` remains compatible with FlyBrian's accepted snake_case experiment payload. Unknown
scientific fields are preserved verbatim; validation rejects invalid known fields without
silently coercing them. Future incompatible changes require a new spec version and explicit
migration. Extension data must remain JSON-compatible and bounded by the invoking consumer.

Schema validity is intentionally not backend compatibility. A valid FES document exposes
its neutral model-family, embodiment, artifact, and version requirements. The selected
backend is assessed against those requirements before it can create a run directory. The
`reference` backend reports `scientific_execution: false`: it is useful for deterministic
contract and packaging verification, but it never stands in for Brian2, NEURON, or another
scientific adapter.

The optional Brian2 adapter imports Brian only at execution time, so the base package and
reference backend remain usable without scientific extras. Discovery reports `available`,
`not_installed`, or `incompatible_runtime` independently from model compatibility. The first
public release accepts three checksumable offline model definitions—LIF, first-order rate, and
passive two-compartment—and rejects all unadvertised model IDs and connection semantics before
allocation. Equations, analytic checkpoints, and tolerance bands are frozen in
[`brian2-golden-models.md`](brian2-golden-models.md).

The corresponding standardized-results schema is validated independently of the manifest file
checksum. It requires immutable engine/backend/experiment identity, ordered global neuron and
spike identities, finite unit-bearing continuous series, duration bounds, and exact network
counts. Brian monitor objects never cross this JSON boundary.

Artifact manifest 1.1 is the portable completion envelope. It contains no hosted URLs or
credentials. Consumers may decorate its checksummed artifact records with authorized storage
locations, while explicit dispositions preserve the difference between unavailable, failed,
and unknown output. Manifest writes use same-directory atomic replacement.

The alpha local server is intentionally synchronous and loopback-only. Durable scheduling,
tenancy, billing, and autoscaling belong to private `flybrian-serve`; a future desktop daemon
may add durable local jobs behind the versioned `/v1` protocol without changing engine
execution semantics.
