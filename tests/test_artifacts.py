from __future__ import annotations

import json
import os
from dataclasses import replace
from pathlib import Path

import pytest

from flybrian_engine.artifacts import (
    Artifact,
    ArtifactDisposition,
    ArtifactManifest,
    DatasetReference,
)


def artifact_manifest(root: Path) -> ArtifactManifest:
    motor_path = root / "motor_commands.json"
    motor_path.write_text('{"commands": [[0.0, 1.0]]}\n', encoding="utf-8")
    motor = Artifact.from_file(
        key="motor_commands",
        kind="motor_commands",
        media_type="application/json",
        path=motor_path,
        root=root,
    )
    return ArtifactManifest(
        run_id="run_fixture",
        engine_version="0.1.0",
        backend_id="brian2",
        backend_version="2.8.0",
        experiment_spec_version="1.0",
        experiment_sha256="a" * 64,
        random_seed=42,
        datasets=(DatasetReference(dataset_id="manc:v1.2.1", sha256="b" * 64),),
        scientific_execution=True,
        deterministic_for_fixed_seed=True,
        artifacts=(motor,),
        dispositions=(
            ArtifactDisposition(
                kind="motor_commands",
                status="available",
                artifact_keys=("motor_commands",),
            ),
            ArtifactDisposition(
                kind="video",
                status="failed",
                reason="Renderer terminated after scientific results committed.",
            ),
        ),
    )


def test_motor_commands_available_while_video_failed_survives_json_round_trip(
    tmp_path: Path,
) -> None:
    manifest = artifact_manifest(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    manifest.write(manifest_path)
    restored = ArtifactManifest.read(manifest_path)

    assert restored == manifest
    assert restored.schema_version == "1.1"
    assert restored.disposition("motor_commands").status == "available"
    assert restored.disposition("video").status == "failed"
    assert restored.disposition("video").reason is not None
    restored.verify_files(tmp_path)
    assert manifest.to_json() == restored.to_json()


def test_file_verification_detects_size_or_checksum_change(tmp_path: Path) -> None:
    manifest = artifact_manifest(tmp_path)
    (tmp_path / "motor_commands.json").write_text("tampered\n", encoding="utf-8")
    with pytest.raises(ValueError, match="size or SHA-256"):
        manifest.verify_files(tmp_path)


def test_artifact_rejects_lexical_and_symlink_escape(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="safe relative path"):
        Artifact(
            key="escape",
            kind="log",
            media_type="text/plain",
            relative_path="../secret.txt",
            size_bytes=1,
            sha256="a" * 64,
        )

    outside = tmp_path.parent / "outside-artifact.txt"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("platform does not permit symlink creation")
    with pytest.raises(ValueError, match="escapes the run root"):
        Artifact.from_file(
            key="escape",
            kind="log",
            media_type="text/plain",
            path=link,
            root=tmp_path,
        )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("duplicate-artifact", "artifact keys must be unique"),
        ("duplicate-disposition", "disposition kinds must be unique"),
        ("dangling", "references missing artifact"),
        ("cross-kind", "must reference an artifact of the same kind"),
        ("missing-reason", "requires a reason"),
        ("missing-dataset", "at least one dataset"),
        ("invalid-hash", "experiment_sha256"),
    ],
)
def test_manifest_rejects_ambiguous_identity_or_availability(
    tmp_path: Path,
    change: str,
    message: str,
) -> None:
    manifest = artifact_manifest(tmp_path)
    with pytest.raises(ValueError, match=message):
        if change == "duplicate-artifact":
            replace(manifest, artifacts=manifest.artifacts + manifest.artifacts)
        elif change == "duplicate-disposition":
            replace(
                manifest,
                dispositions=(*manifest.dispositions, manifest.dispositions[0]),
            )
        elif change == "dangling":
            replace(manifest, dispositions=(
                ArtifactDisposition(kind="video", status="available", artifact_keys=("missing",)),
            ))
        elif change == "cross-kind":
            replace(manifest, dispositions=(
                ArtifactDisposition(
                    kind="video",
                    status="available",
                    artifact_keys=("motor_commands",),
                ),
            ))
        elif change == "missing-reason":
            disposition = ArtifactDisposition(
                kind="video",
                status="failed",
                reason="renderer failed",
            )
            object.__setattr__(disposition, "reason", None)
            replace(manifest, dispositions=(disposition,))
        elif change == "missing-dataset":
            replace(manifest, datasets=())
        else:
            replace(manifest, experiment_sha256="not-a-hash")


def test_failed_atomic_replace_preserves_previous_manifest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    destination = tmp_path / "manifest.json"
    destination.write_text('{"previous": true}\n', encoding="utf-8")
    manifest = artifact_manifest(tmp_path)

    def fail_replace(
        _source: str | bytes | os.PathLike[str] | os.PathLike[bytes],
        _destination: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    ) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(os, "replace", fail_replace)
    with pytest.raises(OSError, match="injected replace failure"):
        manifest.write(destination)
    assert json.loads(destination.read_text(encoding="utf-8")) == {"previous": True}
    assert not (tmp_path / ".manifest.json.tmp").exists()
