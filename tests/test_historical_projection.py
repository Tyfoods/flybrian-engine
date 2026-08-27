from __future__ import annotations

import builtins
import hashlib
import importlib
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Literal

import pytest

from flybrian_engine.historical_envelopes import (
    HistoricalExperimentEnvelope,
    HistoricalSourceAuthority,
)
from flybrian_engine.historical_estate import (
    HistoricalEstateInventory,
    HistoricalEstateRoot,
    inventory_historical_estate,
)
from flybrian_engine.historical_projection import (
    DEFAULT_MAX_HISTORICAL_PROJECTION_JSON_BYTES,
    HISTORICAL_ESTATE_PROJECTION_PROFILE_ID,
    HISTORICAL_ESTATE_PROJECTION_PROFILE_VERSION,
    HistoricalContributor,
    HistoricalEnvelopeReference,
    HistoricalEstateProjection,
    HistoricalEvidenceReference,
    HistoricalInventoryReference,
    HistoricalProjectedArtifact,
    HistoricalProjectedRun,
    HistoricalProjectionError,
    HistoricalProjectionReview,
    HistoricalVisibilityPolicy,
    load_historical_estate_projection_json,
    validate_historical_estate_projection,
)


def build_authorities(
    root: Path,
) -> tuple[
    tuple[HistoricalEstateInventory, HistoricalEstateInventory],
    HistoricalExperimentEnvelope,
]:
    source_root = root / "source"
    output_root = root / "output"
    source_root.mkdir(parents=True)
    (output_root / "run-1").mkdir(parents=True)
    source_bytes = b"# reviewed fixture\nseed = 42\n"
    (source_root / "walk.py").write_bytes(source_bytes)
    (output_root / "run-1" / "result.json").write_bytes(b'{"status":"complete"}\n')
    (output_root / "run-1" / "motor.npy").write_bytes(b"NUMPY-OPAQUE")
    (output_root / "run-1" / "replay.mp4").write_bytes(b"MP4-OPAQUE")

    source_inventory = inventory_historical_estate(
        HistoricalEstateRoot(
            root_id="org.flybrian.estate.experiments",
            revision="reviewed-revision-1",
            logical_root="experiments",
            license_id="MIT",
            access="public",
            redistribution="permitted",
            physical_root=source_root,
        )
    )
    output_inventory = inventory_historical_estate(
        HistoricalEstateRoot(
            root_id="org.flybrian.estate.output",
            revision="reviewed-revision-1",
            logical_root="output",
            license_id="MIT",
            access="public",
            redistribution="permitted",
            physical_root=output_root,
        )
    )
    envelope = HistoricalExperimentEnvelope(
        envelope_id="org.flybrian.experiment.walk",
        version="1.0",
        source=HistoricalSourceAuthority(
            repository="fixture-research",
            revision="reviewed-revision-1",
            logical_path="experiments/walk.py",
            byte_length=len(source_bytes),
            sha256=hashlib.sha256(source_bytes).hexdigest(),
            license_id="MIT",
            access="public",
            redistribution="permitted",
            extractor_id="org.flybrian.static-python-extractor",
            extractor_version="1.1",
        ),
        selector="reviewed-fixture",
        invocation=(),
        options=(),
        controller_profile=None,
        fes=None,
        expected_fes_sha256=None,
        source_artifacts=(),
        missing_requirements=("FES",),
        lineage=None,
    )
    return (source_inventory, output_inventory), envelope


def evidence(
    inventory: HistoricalEstateInventory,
    logical_path: str,
) -> HistoricalEvidenceReference:
    item = next(file for file in inventory.files if file.logical_path == logical_path)
    return HistoricalEvidenceReference(
        root_id=inventory.root.root_id,
        inventory_sha256=inventory.sha256(),
        logical_path=logical_path,
        byte_length=item.byte_length,
        file_sha256=item.sha256,
        candidate_role=item.candidate_role,
    )


def envelope_reference(envelope: HistoricalExperimentEnvelope) -> HistoricalEnvelopeReference:
    return HistoricalEnvelopeReference(
        envelope_id=envelope.envelope_id,
        version=envelope.version,
        envelope_sha256=envelope.sha256(),
        reproducibility_class=envelope.reproducibility_class,
        fes_sha256=envelope.expected_fes_sha256,
        missing_requirements=envelope.missing_requirements,
    )


def build_projection(
    inventories: tuple[HistoricalEstateInventory, HistoricalEstateInventory],
    envelope: HistoricalExperimentEnvelope,
    *,
    run_count: int = 1,
) -> HistoricalEstateProjection:
    source_inventory, output_inventory = inventories
    artifacts = (
        HistoricalProjectedArtifact(
            artifact_id="org.flybrian.artifact.motor-commands",
            kind="motor_commands",
            availability="available",
            evidence=evidence(output_inventory, "run-1/motor.npy"),
            reason=None,
        ),
        HistoricalProjectedArtifact(
            artifact_id="org.flybrian.artifact.result",
            kind="result",
            availability="available",
            evidence=evidence(output_inventory, "run-1/result.json"),
            reason=None,
        ),
        HistoricalProjectedArtifact(
            artifact_id="org.flybrian.artifact.video",
            kind="video",
            availability="available",
            evidence=evidence(output_inventory, "run-1/replay.mp4"),
            reason=None,
        ),
        HistoricalProjectedArtifact(
            artifact_id="org.flybrian.artifact.spike-table",
            kind="metrics",
            availability="unavailable",
            evidence=None,
            reason="The historical run did not preserve a separate spike table.",
        ),
    )
    runs = tuple(
        HistoricalProjectedRun(
            design_id=f"org.flybrian.design.walk-{index:05d}",
            design_version=1,
            run_id=f"org.flybrian.run.walk-{index:05d}",
            contributor_id="org.flybrian.contributor.pena-lab",
            visibility=HistoricalVisibilityPolicy("public", None),
            source=evidence(source_inventory, "walk.py"),
            source_repository_path="experiments/walk.py",
            envelope=envelope_reference(envelope),
            artifacts=artifacts if index == 0 else (),
        )
        for index in range(run_count)
    )
    return HistoricalEstateProjection(
        projection_id="org.flybrian.projection.reviewed-fixture",
        version="1.0",
        review=HistoricalProjectionReview(
            review_authority_id="org.flybrian.review.pena-lab",
            review_revision="review-decision-1",
            evidence="Fixture linkage reviewed against exact source and output receipts.",
        ),
        inventories=tuple(
            HistoricalInventoryReference(item.root.root_id, item.sha256())
            for item in inventories
        ),
        contributors=(
            HistoricalContributor(
                contributor_id="org.flybrian.contributor.pena-lab",
                display_name="Pena Lab",
                attribution="Historical FlyBrian research program",
            ),
        ),
        runs=runs,
    )


def test_exact_joint_inventory_envelope_and_artifact_projection(tmp_path: Path) -> None:
    inventories, envelope = build_authorities(tmp_path)
    projection = build_projection(inventories, envelope)

    assert HISTORICAL_ESTATE_PROJECTION_PROFILE_ID == (
        "org.flybrian.historical-estate-projection"
    )
    assert HISTORICAL_ESTATE_PROJECTION_PROFILE_VERSION == "1.0"
    assert validate_historical_estate_projection(
        projection, inventories=inventories, envelopes=(envelope,)
    ) is projection
    assert len(projection.sha256()) == 64
    assert len(projection.import_sha256()) == 64
    assert projection.runs[0].envelope.reproducibility_class == "PROVENANCE_ONLY"


def test_relocation_preserves_projection_and_import_identity(tmp_path: Path) -> None:
    left_authorities = build_authorities(tmp_path / "left")
    right_authorities = build_authorities(tmp_path / "right")
    left = build_projection(*left_authorities)
    right = build_projection(*right_authorities)

    assert left.canonical_bytes() == right.canonical_bytes()
    assert left.sha256() == right.sha256()
    assert left.import_sha256() == right.import_sha256()


@pytest.mark.parametrize(
    "mutation",
    ["drop", "reverse", "root", "inventory_hash"],
)
def test_exact_inventory_tuple_rejects_mutations(tmp_path: Path, mutation: str) -> None:
    inventories, envelope = build_authorities(tmp_path)
    projection = build_projection(inventories, envelope)
    supplied: tuple[HistoricalEstateInventory, ...] = inventories
    if mutation == "drop":
        supplied = inventories[:1]
    elif mutation == "reverse":
        supplied = tuple(reversed(inventories))
    elif mutation == "root":
        wrong = replace(
            inventories[0],
            root=replace(inventories[0].root, root_id="org.flybrian.estate.wrong"),
        )
        supplied = (wrong, inventories[1])
    else:
        refs = list(projection.inventories)
        refs[0] = replace(refs[0], inventory_sha256="0" * 64)
        projection = replace(projection, inventories=tuple(refs))
    with pytest.raises(HistoricalProjectionError):
        validate_historical_estate_projection(
            projection, inventories=supplied, envelopes=(envelope,)
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("root_id", "org.flybrian.estate.wrong"),
        ("logical_path", "missing.py"),
        ("byte_length", 999),
        ("file_sha256", "0" * 64),
        ("candidate_role", "result"),
    ],
)
def test_source_edge_must_match_inventory_exactly(
    tmp_path: Path, field: str, value: object
) -> None:
    inventories, envelope = build_authorities(tmp_path)
    projection = build_projection(inventories, envelope)
    run = projection.runs[0]
    if field == "root_id":
        changed_source = replace(run.source, root_id=str(value))
    elif field == "logical_path":
        changed_source = replace(run.source, logical_path=str(value))
    elif field == "byte_length":
        changed_source = replace(run.source, byte_length=int(str(value)))
    elif field == "file_sha256":
        changed_source = replace(run.source, file_sha256=str(value))
    else:
        changed_source = replace(run.source, candidate_role="result")
    projection = replace(projection, runs=(replace(run, source=changed_source),))
    with pytest.raises(HistoricalProjectionError):
        validate_historical_estate_projection(
            projection, inventories=inventories, envelopes=(envelope,)
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("envelope_id", "org.flybrian.experiment.wrong"),
        ("version", "2.0"),
        ("envelope_sha256", "0" * 64),
        ("reproducibility_class", "RUNNABLE_EMBODIED"),
        ("missing_requirements", ()),
    ],
)
def test_envelope_reference_cannot_invent_runnability(
    tmp_path: Path, field: str, value: object
) -> None:
    inventories, envelope = build_authorities(tmp_path)
    projection = build_projection(inventories, envelope)
    run = projection.runs[0]
    with pytest.raises(HistoricalProjectionError):
        if field == "envelope_id":
            changed_envelope = replace(run.envelope, envelope_id=str(value))
        elif field == "version":
            changed_envelope = replace(run.envelope, version=str(value))
        elif field == "envelope_sha256":
            changed_envelope = replace(run.envelope, envelope_sha256=str(value))
        elif field == "reproducibility_class":
            changed_envelope = replace(
                run.envelope,
                reproducibility_class="RUNNABLE_EMBODIED",
            )
        else:
            changed_envelope = replace(run.envelope, missing_requirements=())
        projection = replace(
            projection,
            runs=(replace(run, envelope=changed_envelope),),
        )
        validate_historical_estate_projection(
            projection, inventories=inventories, envelopes=(envelope,)
        )


def test_envelope_source_must_match_source_inventory(tmp_path: Path) -> None:
    inventories, envelope = build_authorities(tmp_path)
    projection = build_projection(inventories, envelope)
    wrong_envelope = replace(
        envelope,
        source=replace(envelope.source, revision="another-revision"),
    )
    wrong_ref = envelope_reference(wrong_envelope)
    projection = replace(
        projection,
        runs=(replace(projection.runs[0], envelope=wrong_ref),),
    )
    with pytest.raises(HistoricalProjectionError, match="source authority"):
        validate_historical_estate_projection(
            projection, inventories=inventories, envelopes=(wrong_envelope,)
        )


def test_repository_source_path_is_explicit_and_not_derived_from_logical_root(
    tmp_path: Path,
) -> None:
    inventories, envelope = build_authorities(tmp_path)
    projection = build_projection(inventories, envelope)
    run = replace(
        projection.runs[0],
        source_repository_path="another-root/walk.py",
    )
    with pytest.raises(HistoricalProjectionError, match="source authority"):
        validate_historical_estate_projection(
            replace(projection, runs=(run,)),
            inventories=inventories,
            envelopes=(envelope,),
        )


def test_provenance_only_envelope_may_express_fes_absence_without_missing_codes(
    tmp_path: Path,
) -> None:
    inventories, envelope = build_authorities(tmp_path)
    envelope = replace(envelope, missing_requirements=())
    assert envelope.reproducibility_class == "PROVENANCE_ONLY"
    projection = build_projection(inventories, envelope)
    assert validate_historical_estate_projection(
        projection,
        inventories=inventories,
        envelopes=(envelope,),
    ) is projection


@pytest.mark.parametrize(
    ("visibility", "scope", "valid"),
    [
        ("public", None, True),
        ("private", None, True),
        ("team", "org.flybrian.team.alpha", True),
        ("team", None, False),
        ("public", "org.flybrian.team.alpha", False),
        ("private", "org.flybrian.team.alpha", False),
    ],
)
def test_visibility_scope_matrix(
    visibility: Literal["public", "private", "team"],
    scope: str | None,
    valid: bool,
) -> None:
    if valid:
        assert HistoricalVisibilityPolicy(visibility, scope).visibility == visibility
    else:
        with pytest.raises(HistoricalProjectionError):
            HistoricalVisibilityPolicy(visibility, scope)


def test_artifact_disposition_and_role_are_fail_closed(tmp_path: Path) -> None:
    inventories, envelope = build_authorities(tmp_path)
    projection = build_projection(inventories, envelope)
    artifact = projection.runs[0].artifacts[0]

    with pytest.raises(HistoricalProjectionError):
        replace(artifact, availability="available", evidence=None)
    with pytest.raises(HistoricalProjectionError):
        replace(artifact, availability="unavailable", reason="missing")
    with pytest.raises(HistoricalProjectionError):
        replace(artifact, availability="failed", evidence=None, reason=None)

    mislabeled = replace(artifact, kind="video")
    run = replace(projection.runs[0], artifacts=(mislabeled,))
    with pytest.raises(HistoricalProjectionError, match="artifact role"):
        validate_historical_estate_projection(
            replace(projection, runs=(run,)),
            inventories=inventories,
            envelopes=(envelope,),
        )


def test_canonical_json_round_trip_and_strict_admission(tmp_path: Path) -> None:
    inventories, envelope = build_authorities(tmp_path)
    projection = build_projection(inventories, envelope)
    loaded = load_historical_estate_projection_json(
        projection.canonical_bytes(), inventories=inventories, envelopes=(envelope,)
    )
    assert loaded == projection
    assert loaded.import_sha256() == projection.import_sha256()
    assert len(projection.canonical_bytes()) <= DEFAULT_MAX_HISTORICAL_PROJECTION_JSON_BYTES


@pytest.mark.parametrize(
    "payload",
    [
        b'{"schema_version":"1.0","schema_version":"1.0"}',
        b'{"schema_version":1.0}',
        b'{"schema_version":NaN}',
        b'[]',
        b'\xff',
        b'{"schema_version":"1.0","unknown":true}',
    ],
)
def test_strict_json_rejects_duplicate_float_nonfinite_shape_utf8_and_unknown(
    tmp_path: Path, payload: bytes
) -> None:
    inventories, envelope = build_authorities(tmp_path)
    with pytest.raises(HistoricalProjectionError):
        load_historical_estate_projection_json(
            payload, inventories=inventories, envelopes=(envelope,)
        )


def test_json_byte_limit_is_positive_and_enforced(tmp_path: Path) -> None:
    inventories, envelope = build_authorities(tmp_path)
    projection = build_projection(inventories, envelope)
    payload = projection.canonical_bytes()
    with pytest.raises(HistoricalProjectionError, match="positive integer"):
        load_historical_estate_projection_json(
            payload, inventories=inventories, envelopes=(envelope,), max_bytes=True
        )
    with pytest.raises(HistoricalProjectionError, match="byte limit"):
        load_historical_estate_projection_json(
            payload,
            inventories=inventories,
            envelopes=(envelope,),
            max_bytes=len(payload) - 1,
        )


def test_order_uniqueness_and_contributor_references_are_validated(tmp_path: Path) -> None:
    inventories, envelope = build_authorities(tmp_path)
    projection = build_projection(inventories, envelope, run_count=2)
    with pytest.raises(HistoricalProjectionError, match="runs must be unique and sorted"):
        replace(projection, runs=tuple(reversed(projection.runs)))
    with pytest.raises(HistoricalProjectionError, match="contributor"):
        replace(
            projection,
            runs=(replace(projection.runs[0], contributor_id="org.flybrian.unknown.person"),),
        )


@pytest.mark.parametrize("run_count", [0, 1, 40, 6001])
def test_projection_scale_has_no_historical_count_cap(
    tmp_path: Path, run_count: int
) -> None:
    inventories, envelope = build_authorities(tmp_path)
    projection = build_projection(inventories, envelope, run_count=run_count)
    assert len(
        validate_historical_estate_projection(
            projection, inventories=inventories, envelopes=(envelope,)
        ).runs
    ) == run_count


def test_validation_does_not_reopen_or_execute_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    inventories, envelope = build_authorities(tmp_path)
    projection = build_projection(inventories, envelope)

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("projection validation crossed a forbidden boundary")

    monkeypatch.setattr(builtins, "open", forbidden)
    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(importlib, "import_module", forbidden)
    assert validate_historical_estate_projection(
        projection, inventories=inventories, envelopes=(envelope,)
    ) is projection


def test_identity_changes_with_review_contributor_edge_and_order(tmp_path: Path) -> None:
    inventories, envelope = build_authorities(tmp_path)
    base = build_projection(inventories, envelope)
    review_changed = replace(
        base,
        review=replace(base.review, review_revision="review-decision-2"),
    )
    contributor_changed = replace(
        base,
        contributors=(replace(base.contributors[0], display_name="Pena Laboratory"),),
    )
    edge = base.runs[0].artifacts[0]
    edge_changed = replace(
        base,
        runs=(
            replace(
                base.runs[0],
                artifacts=(replace(edge, artifact_id="org.flybrian.artifact.motor-state"),),
            ),
        ),
    )
    identities = {
        base.sha256(),
        review_changed.sha256(),
        contributor_changed.sha256(),
        edge_changed.sha256(),
    }
    assert len(identities) == 4
