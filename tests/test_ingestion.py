from __future__ import annotations

import hashlib
import shutil
from dataclasses import replace
from pathlib import Path

import pytest

from flybrian_engine.datasets import (
    DatasetManifest,
    DatasetVerificationError,
    VerifiedDataset,
)
from flybrian_engine.ingestion import (
    MANC_CONNECTION_NORMALIZATION_V1,
    ConnectionNormalizationError,
    ConnectionNormalizationProfile,
    ConnectionNormalizationReceipt,
    iter_connections,
    iter_motor_anatomy,
    normalize_connection_dataset,
)

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


def _connection_dataset(tmp_path: Path, files: dict[str, str]) -> VerifiedDataset:
    root = tmp_path / "source"
    root.mkdir()
    entries: list[dict[str, object]] = []
    for name, content in files.items():
        path = root / name
        # Preserve the fixture's exact LF bytes on Windows so the source
        # manifest and its receipt identity are platform-neutral.
        path.write_bytes(content.encode("utf-8"))
        entries.append(
            file_entry(
                path,
                "connectivity",
                "org.janelia.neuprint.connection-summary.v1",
                content.count("\n") - 1,
            )
        )
    manifest = DatasetManifest.from_dict(
        {
            "schema_version": "1.0",
            "dataset_id": "fixture:normalization",
            "provider": "FlyBrian tests",
            "release": "1",
            "source_url": "https://example.test/fixture",
            "citation": None,
            "license": "CC0-1.0",
            "redistribution": "allowed",
            "access": "public",
            "files": entries,
        }
    )
    return manifest.verify(root)


_CONNECTION_HEADER = (
    "preId,preType,preInstance,preNt,postId,postType,postInstance,postNt,total_weight\n"
)


def test_connection_normalization_canonical_receipt_and_idempotence(tmp_path: Path) -> None:
    dataset = _connection_dataset(
        tmp_path,
        {
            "connections.csv": _CONNECTION_HEADER
            + "1,TypeA,A_L,acetylcholine,2,TypeB,B_R,gaba,3\n"
            + "2,TypeB,B_R,gaba,3,,,,4.0\n"
        },
    )
    destination = tmp_path / "normalized"
    unknown = destination / "researcher-note.txt"
    destination.mkdir()
    unknown.write_text("preserve me", encoding="utf-8")

    result = normalize_connection_dataset(
        dataset, MANC_CONNECTION_NORMALIZATION_V1, destination
    )
    output = destination / "connections.ndjson"
    receipt_path = destination / "connection-normalization-receipt.json"
    assert result.output_path == output
    assert output.read_bytes().endswith(b"\n")
    assert result.receipt.output_record_count == 2
    assert result.receipt.input_record_count == 2
    assert result.receipt.self_edge_count == 0
    assert result.receipt.output_sha256 == hashlib.sha256(output.read_bytes()).hexdigest()
    assert result.receipt.profile_sha256 == MANC_CONNECTION_NORMALIZATION_V1.sha256()
    assert result.receipt.duplicate_edge_count == 0
    assert result.receipt.annotation_conflict_count == 0
    assert result.receipt.output_sha256 == (
        "92123fdbf30851dbc3ff6f175fbbc000911b18429b5a2ccc3b0f2a4e6a51f2dc"
    )
    assert result.receipt.sha256() == (
        "f86ab27f6b5f7524ab0d38c92166061719a18c3666f8942df74b1c019bb372fb"
    )
    assert MANC_CONNECTION_NORMALIZATION_V1.sha256() == (
        "648aa3bd382a5bcd7e09d778f154c1a6ca209d521f6ff0399ad048768f2a020d"
    )
    assert (
        ConnectionNormalizationProfile.from_dict(
            MANC_CONNECTION_NORMALIZATION_V1.to_dict()
        )
        == MANC_CONNECTION_NORMALIZATION_V1
    )
    assert ConnectionNormalizationReceipt.from_dict(result.receipt.to_dict()) == result.receipt
    assert receipt_path.read_bytes() == result.receipt.canonical_bytes() + b"\n"
    assert unknown.read_text(encoding="utf-8") == "preserve me"
    output_stat = output.stat()
    receipt_stat = receipt_path.stat()

    repeated = normalize_connection_dataset(
        dataset, MANC_CONNECTION_NORMALIZATION_V1, destination
    )
    assert repeated.receipt.sha256() == result.receipt.sha256()
    assert output.stat().st_mtime_ns == output_stat.st_mtime_ns
    assert receipt_path.stat().st_mtime_ns == receipt_stat.st_mtime_ns

    changed = replace(MANC_CONNECTION_NORMALIZATION_V1, self_edge_policy="reject")
    with pytest.raises(ConnectionNormalizationError, match="conflicts with existing normalized"):
        normalize_connection_dataset(dataset, changed, destination)
    assert output.stat().st_mtime_ns == output_stat.st_mtime_ns
    assert receipt_path.stat().st_mtime_ns == receipt_stat.st_mtime_ns


def test_connection_normalization_rejects_cross_file_duplicate_with_provenance(
    tmp_path: Path,
) -> None:
    dataset = _connection_dataset(
        tmp_path,
        {
            "a.csv": _CONNECTION_HEADER + "1,A,a,acetylcholine,2,B,b,gaba,3\n",
            "b.csv": _CONNECTION_HEADER + "1,A,a,acetylcholine,2,B,b,gaba,3\n",
        },
    )
    destination = tmp_path / "normalized"
    rejecting = replace(
        MANC_CONNECTION_NORMALIZATION_V1,
        duplicate_edge_policy="reject",
    )
    with pytest.raises(ConnectionNormalizationError) as caught:
        normalize_connection_dataset(dataset, rejecting, destination)
    message = str(caught.value)
    assert "duplicate connection pair (1, 2)" in message
    assert "a.csv data row 1" in message
    assert "b.csv data row 1" in message
    assert not (destination / "connections.ndjson").exists()
    assert not (destination / "connection-normalization-receipt.json").exists()
    assert not (destination / ".connection-normalization-index.sqlite3").exists()


def test_connection_normalization_records_each_duplicate_pair_once(tmp_path: Path) -> None:
    row = "1,A,a,acetylcholine,2,B,b,gaba,3\n"
    dataset = _connection_dataset(
        tmp_path,
        {
            "a.csv": _CONNECTION_HEADER + row + row,
            "b.csv": _CONNECTION_HEADER + row,
        },
    )
    result = normalize_connection_dataset(
        dataset,
        MANC_CONNECTION_NORMALIZATION_V1,
        tmp_path / "normalized",
    )
    assert result.receipt.input_record_count == 3
    assert result.receipt.output_record_count == 3
    assert result.receipt.duplicate_edge_count == 1
    assert result.output_path.read_text(encoding="utf-8").count("\n") == 3


@pytest.mark.parametrize("field,column", [("type", 1), ("instance", 2), ("transmitter", 3)])
def test_connection_normalization_rejects_annotation_conflicts(
    tmp_path: Path, field: str, column: int
) -> None:
    first = ["1", "TypeA", "A_L", "acetylcholine", "2", "TypeB", "B_R", "gaba", "3"]
    second = ["1", "TypeA", "A_L", "acetylcholine", "3", "", "", "", "4"]
    second[column] = "conflicting"
    dataset = _connection_dataset(
        tmp_path,
        {"connections.csv": _CONNECTION_HEADER + ",".join(first) + "\n" + ",".join(second) + "\n"},
    )
    rejecting = replace(
        MANC_CONNECTION_NORMALIZATION_V1,
        annotation_conflict_policy="reject",
    )
    with pytest.raises(
        ConnectionNormalizationError,
        match=rf"neuron 1 {field} annotation conflicts.*data row 1.*data row 2",
    ):
        normalize_connection_dataset(dataset, rejecting, tmp_path / "normalized")


def test_connection_normalization_records_each_annotation_conflict_once(
    tmp_path: Path,
) -> None:
    dataset = _connection_dataset(
        tmp_path,
        {
            "connections.csv": _CONNECTION_HEADER
            + "1,A,a,acetylcholine,2,B,b,gaba,3\n"
            + "1,A,a,gaba,3,C,c,gaba,4\n"
            + "1,A,a,glutamate,4,D,d,gaba,5\n"
        },
    )
    result = normalize_connection_dataset(
        dataset,
        MANC_CONNECTION_NORMALIZATION_V1,
        tmp_path / "normalized",
    )
    assert result.receipt.annotation_conflict_count == 1
    assert result.receipt.output_record_count == 3
    output = result.output_path.read_text(encoding="utf-8")
    assert '"pre_transmitter":"acetylcholine"' in output
    assert '"pre_transmitter":"gaba"' in output
    assert '"pre_transmitter":"glutamate"' in output


def test_connection_normalization_allows_null_enrichment_and_controls_self_edges(
    tmp_path: Path,
) -> None:
    dataset = _connection_dataset(
        tmp_path,
        {
            "connections.csv": _CONNECTION_HEADER
            + "1,,,,2,,,,3\n"
            + "2,TypeB,B_R,gaba,2,TypeB,B_R,gaba,4\n"
        },
    )
    kept = normalize_connection_dataset(
        dataset, MANC_CONNECTION_NORMALIZATION_V1, tmp_path / "kept"
    )
    assert kept.receipt.self_edge_count == 1
    assert kept.receipt.duplicate_edge_count == 0
    assert kept.receipt.annotation_conflict_count == 0
    assert kept.receipt.output_record_count == 2

    rejecting = replace(MANC_CONNECTION_NORMALIZATION_V1, self_edge_policy="reject")
    with pytest.raises(ConnectionNormalizationError, match=r"self-edge \(2, 2\).*data row 2"):
        normalize_connection_dataset(dataset, rejecting, tmp_path / "rejected")
    assert not (tmp_path / "rejected" / "connections.ndjson").exists()


def test_connection_normalization_recovers_orphan_and_never_promotes_receipt_early(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dataset = _connection_dataset(
        tmp_path,
        {"connections.csv": _CONNECTION_HEADER + "1,A,a,acetylcholine,2,B,b,gaba,3\n"},
    )
    destination = tmp_path / "normalized"
    destination.mkdir()
    orphan = destination / "connections.ndjson"
    orphan.write_text("incomplete\n", encoding="utf-8")
    (destination / ".connection-normalization-index.sqlite3").write_text(
        "owned interrupted marker",
        encoding="utf-8",
    )

    import flybrian_engine.ingestion as ingestion

    def fail_promotion(_source: Path, _destination: Path) -> None:
        raise OSError("injected promotion failure")

    monkeypatch.setattr(ingestion, "_promote_connection_part", fail_promotion)
    with pytest.raises(ConnectionNormalizationError, match="cannot promote normalized connections"):
        normalize_connection_dataset(dataset, MANC_CONNECTION_NORMALIZATION_V1, destination)
    assert not orphan.exists()
    assert not (destination / "connection-normalization-receipt.json").exists()
    assert not (destination / "connections.ndjson.part").exists()
    assert not (destination / ".connection-normalization-index.sqlite3").exists()


def test_connection_normalization_preserves_unowned_unreceipted_output(
    tmp_path: Path,
) -> None:
    dataset = _connection_dataset(
        tmp_path,
        {"connections.csv": _CONNECTION_HEADER + "1,A,a,acetylcholine,2,B,b,gaba,3\n"},
    )
    destination = tmp_path / "normalized"
    destination.mkdir()
    unowned = destination / "connections.ndjson"
    unowned.write_text("researcher data\n", encoding="utf-8")

    with pytest.raises(
        ConnectionNormalizationError,
        match="has no owned recovery marker; refusing overwrite",
    ):
        normalize_connection_dataset(
            dataset,
            MANC_CONNECTION_NORMALIZATION_V1,
            destination,
        )
    assert unowned.read_text(encoding="utf-8") == "researcher data\n"
    assert not (destination / "connection-normalization-receipt.json").exists()


def test_connection_profile_rejects_unknown_policy_and_scale_streams(tmp_path: Path) -> None:
    with pytest.raises(ConnectionNormalizationError, match="duplicate_edge_policy"):
        ConnectionNormalizationProfile(
            profile_id="fixture",
            profile_version="1",
            source="https://example.test/profile",
            self_edge_policy="retain",
            duplicate_edge_policy="sum",  # type: ignore[arg-type]
            annotation_conflict_policy="reject",
        )
    invalid_profile = MANC_CONNECTION_NORMALIZATION_V1.to_dict()
    invalid_profile["unexpected"] = "value"
    with pytest.raises(ConnectionNormalizationError, match=r"unknown=\['unexpected'\]"):
        ConnectionNormalizationProfile.from_dict(invalid_profile)

    rows = [f"{index},,,,10000,,,,1\n" for index in range(1, 2501)]
    dataset = _connection_dataset(
        tmp_path,
        {
            "a.csv": _CONNECTION_HEADER + "".join(rows[:1250]),
            "b.csv": _CONNECTION_HEADER + "".join(rows[1250:]),
        },
    )
    result = normalize_connection_dataset(
        dataset, MANC_CONNECTION_NORMALIZATION_V1, tmp_path / "normalized"
    )
    assert result.receipt.output_record_count == 2500
