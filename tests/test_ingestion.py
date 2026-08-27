from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import pytest

from flybrian_engine.datasets import DatasetManifest, DatasetVerificationError
from flybrian_engine.ingestion import iter_connections, iter_motor_anatomy

FIXTURES = Path(__file__).parent / "fixtures" / "ingestion"


def file_entry(path: Path, role: str, schema_id: str, rows: int) -> dict[str, object]:
    data = path.read_bytes()
    return {
        "role": role,
        "path": path.name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size_bytes": len(data),
        "media_type": "text/csv",
        "schema_id": schema_id,
        "data_rows": rows,
    }


def manifest_value(root: Path) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "dataset_id": "manc:v1.2.1-fixture",
        "provider": "Janelia Research Campus",
        "release": "v1.2.1-fixture",
        "source_url": "https://neuprint.janelia.org",
        "citation": None,
        "license": "unknown",
        "redistribution": "unknown",
        "access": "token_required",
        "files": [
            file_entry(
                root / "connectivity.csv",
                "connectivity",
                "org.janelia.neuprint.connection-summary.v1",
                4,
            ),
            file_entry(
                root / "motor-anatomy.csv",
                "motor_anatomy",
                "org.flybrian.motor-anatomy.v1",
                3,
            ),
        ],
    }


@pytest.fixture
def dataset_root(tmp_path: Path) -> Path:
    root = tmp_path / "dataset"
    shutil.copytree(FIXTURES, root)
    return root


def test_manifest_identity_and_verified_streaming_normalization(dataset_root: Path) -> None:
    manifest = DatasetManifest.from_dict(manifest_value(dataset_root))
    reparsed = DatasetManifest.from_dict(manifest.to_dict())
    assert reparsed.canonical_bytes() == manifest.canonical_bytes()
    assert reparsed.sha256() == manifest.sha256()

    verified = manifest.verify(dataset_root)
    connections = list(iter_connections(verified))
    assert [(item.pre_neuron_id, item.post_neuron_id, item.weight) for item in connections] == [
        (10000, 10110, 146),
        (10110, 10200, 8),
        (10200, 841370000000, 11),
        (10201, 9007199254740993, 1),
    ]
    assert connections[0].provenance.data_row == 1
    assert connections[2].provenance.source_lexemes == {
        "postId": "8.4137E+11",
        "total_weight": "11.0",
    }
    assert connections[3].provenance.source_lexemes == {
        "postId": "9.007199254740993E+15"
    }
    anatomy = list(iter_motor_anatomy(verified))
    assert anatomy[0].exit_nerves == ("MetaLN_L",)
    assert anatomy[0].certainty == 5
    assert anatomy[0].source_extensions == {"x_source_note": "curated"}
    assert anatomy[2].target_label is None
    assert anatomy[2].source_extensions == {"x_source_note": "uncharacterized"}


def test_manifest_rejects_escape_duplicate_case_and_unknown_fields(
    dataset_root: Path,
) -> None:
    value = manifest_value(dataset_root)
    files = value["files"]
    assert isinstance(files, list)
    first = files[0]
    assert isinstance(first, dict)
    first["path"] = "../connectivity.csv"
    with pytest.raises(ValueError, match="safe relative POSIX path"):
        DatasetManifest.from_dict(value)

    value = manifest_value(dataset_root)
    files = value["files"]
    assert isinstance(files, list)
    duplicate = dict(files[0])
    duplicate["path"] = "CONNECTIVITY.csv"
    files.append(duplicate)
    with pytest.raises(ValueError, match="case-colliding"):
        DatasetManifest.from_dict(value)

    value = manifest_value(dataset_root)
    value["unexpected"] = True
    with pytest.raises(ValueError, match=r"unknown=\['unexpected'\]"):
        DatasetManifest.from_dict(value)

    value = manifest_value(dataset_root)
    value["source_url"] = "https://user:secret@example.test/release#token"
    with pytest.raises(ValueError, match=r"HTTP\(S\) URL without credentials or fragment"):
        DatasetManifest.from_dict(value)

    value = manifest_value(dataset_root)
    value["source_url"] = "https://example.test:not-a-port/release"
    with pytest.raises(ValueError, match=r"HTTP\(S\) URL without credentials or fragment"):
        DatasetManifest.from_dict(value)


def test_verification_rejects_tamper_and_symlink(dataset_root: Path, tmp_path: Path) -> None:
    manifest = DatasetManifest.from_dict(manifest_value(dataset_root))
    path = dataset_root / "connectivity.csv"
    original = path.read_bytes()
    replacement = bytes([original[0] ^ 1]) + original[1:]
    assert len(replacement) == len(original)
    path.write_bytes(replacement)
    with pytest.raises(DatasetVerificationError, match="size or SHA-256"):
        manifest.verify(dataset_root)

    dataset_root = tmp_path / "linked"
    dataset_root.mkdir()
    target = FIXTURES / "connectivity.csv"
    (dataset_root / "connectivity.csv").symlink_to(target)
    shutil.copy(FIXTURES / "motor-anatomy.csv", dataset_root / "motor-anatomy.csv")
    value = manifest_value(FIXTURES)
    with pytest.raises(DatasetVerificationError, match="symbolic link"):
        DatasetManifest.from_dict(value).verify(dataset_root)


def test_stream_detects_source_mutation_before_completion(dataset_root: Path) -> None:
    manifest = DatasetManifest.from_dict(manifest_value(dataset_root))
    verified = manifest.verify(dataset_root)
    stream = iter_connections(verified)
    assert next(stream).weight == 146
    with (dataset_root / "connectivity.csv").open("a", encoding="utf-8") as handle:
        handle.write("100,Type,a,acetylcholine,200,Type,b,glutamate,1\n")
    with pytest.raises(DatasetVerificationError, match="changed during parsing"):
        list(stream)


def test_parser_rejects_duplicate_columns_and_non_positive_weight(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    root.mkdir()
    connectivity = root / "connectivity.csv"
    connectivity.write_text(
        "preId,preId,postId,total_weight\n1,1,2,1\n",
        encoding="utf-8",
    )
    shutil.copy(FIXTURES / "motor-anatomy.csv", root / "motor-anatomy.csv")
    value = manifest_value(root)
    files = value["files"]
    assert isinstance(files, list) and isinstance(files[0], dict)
    files[0]["data_rows"] = 1
    with pytest.raises(DatasetVerificationError, match="duplicate CSV columns"):
        list(iter_connections(DatasetManifest.from_dict(value).verify(root)))

    connectivity.write_text(
        "preId,postId,total_weight\n1,2,0\n",
        encoding="utf-8",
    )
    value = manifest_value(root)
    files = value["files"]
    assert isinstance(files, list) and isinstance(files[0], dict)
    files[0]["data_rows"] = 1
    with pytest.raises(DatasetVerificationError, match="total_weight must be positive"):
        list(iter_connections(DatasetManifest.from_dict(value).verify(root)))


def test_parser_validates_declared_role_and_header_only_sources(tmp_path: Path) -> None:
    root = tmp_path / "dataset"
    root.mkdir()
    connectivity = root / "connectivity.csv"
    connectivity.write_text("preId,postId,total_weight\n", encoding="utf-8")
    shutil.copy(FIXTURES / "motor-anatomy.csv", root / "motor-anatomy.csv")

    value = manifest_value(root)
    files = value["files"]
    assert isinstance(files, list) and isinstance(files[0], dict)
    files[0]["data_rows"] = 0
    verified = DatasetManifest.from_dict(value).verify(root)
    assert list(iter_connections(verified)) == []

    connectivity.write_text("preId,total_weight\n", encoding="utf-8")
    value = manifest_value(root)
    files = value["files"]
    assert isinstance(files, list) and isinstance(files[0], dict)
    files[0]["data_rows"] = 0
    with pytest.raises(DatasetVerificationError, match=r"missing=\['postId'\]"):
        list(iter_connections(DatasetManifest.from_dict(value).verify(root)))

    connectivity.write_text("preId,postId,total_weight\n", encoding="utf-8")
    value = manifest_value(root)
    files = value["files"]
    assert isinstance(files, list) and isinstance(files[0], dict)
    files[0]["data_rows"] = 0
    files[0]["role"] = "extension"
    with pytest.raises(DatasetVerificationError, match="requires role connectivity"):
        list(iter_connections(DatasetManifest.from_dict(value).verify(root)))

    shutil.copy(FIXTURES / "connectivity.csv", connectivity)
    value = manifest_value(root)
    files = value["files"]
    assert isinstance(files, list) and isinstance(files[1], dict)
    files[1]["role"] = "extension"
    with pytest.raises(DatasetVerificationError, match="requires role motor_anatomy"):
        list(iter_motor_anatomy(DatasetManifest.from_dict(value).verify(root)))
