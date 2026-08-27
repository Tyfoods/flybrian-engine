from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import flybrian_engine.historical_estate as estate_module
from flybrian_engine.historical_estate import (
    HISTORICAL_ESTATE_INVENTORY_PROFILE_ID,
    HISTORICAL_ESTATE_INVENTORY_PROFILE_VERSION,
    HistoricalEstateError,
    HistoricalEstateFile,
    HistoricalEstateInventory,
    HistoricalEstateLimits,
    HistoricalEstateRoot,
    classify_historical_estate_file,
    inventory_historical_estate,
)


def write_fixture(root: Path) -> None:
    (root / "experiments").mkdir(parents=True)
    (root / "output" / "run-a").mkdir(parents=True)
    # These exact-byte fixtures back portable identity assertions; text-mode
    # writes would translate LF to CRLF on Windows.
    (root / "experiments" / "walk.py").write_bytes(b"seed = 42\n")
    (root / "output" / "run-a" / "result.json").write_bytes(b'{"status":"complete"}\n')
    (root / "output" / "run-a" / "motor.npy").write_bytes(b"NUMPY-FIXTURE")
    (root / "README.md").write_bytes(b"# Estate\n")


def authority(root: Path, **overrides: object) -> HistoricalEstateRoot:
    values: dict[str, object] = {
        "root_id": "org.flybrian.historical-estate.fixture",
        "revision": "fixture-revision-1",
        "logical_root": "flybrian-research",
        "license_id": "UNKNOWN",
        "access": "private",
        "redistribution": "prohibited",
        "physical_root": root,
    }
    values.update(overrides)
    return HistoricalEstateRoot(**values)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("path", "media_kind", "role", "disposition"),
    [
        ("experiment.py", "text/x-python", "source", "source_candidate"),
        ("result.json", "application/json", "result", "artifact_candidate"),
        ("table.csv", "text/csv", "result", "artifact_candidate"),
        ("state.npy", "application/x-npy", "array", "artifact_candidate"),
        ("state.npz", "application/x-npz", "array", "artifact_candidate"),
        ("replay.mp4", "video/mp4", "video", "artifact_candidate"),
        ("frame.png", "image/png", "image", "artifact_candidate"),
        ("frame.jpg", "image/jpeg", "image", "artifact_candidate"),
        ("frame.jpeg", "image/jpeg", "image", "artifact_candidate"),
        ("notes.md", "text/markdown", "narrative", "review_required"),
        ("notes.txt", "text/plain", "narrative", "review_required"),
        ("run.log", "text/plain", "narrative", "review_required"),
        ("bundle.tar.gz", "application/gzip", "archive", "review_required"),
        ("bundle.tgz", "application/gzip", "archive", "review_required"),
        ("bundle.zip", "application/zip", "archive", "review_required"),
        ("score.standing_report.json", "application/json", "result", "artifact_candidate"),
        ("artifact.bin", "application/octet-stream", "unknown", "review_required"),
    ],
)
def test_classification_is_extension_only(
    path: str, media_kind: str, role: str, disposition: str
) -> None:
    assert classify_historical_estate_file(path) == (media_kind, role, disposition)


def test_exact_inventory_and_collection_summary(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    inventory = inventory_historical_estate(authority(tmp_path))

    assert HISTORICAL_ESTATE_INVENTORY_PROFILE_ID == "org.flybrian.historical-estate-inventory"
    assert HISTORICAL_ESTATE_INVENTORY_PROFILE_VERSION == "1.0"
    assert [item.logical_path for item in inventory.files] == [
        "README.md",
        "experiments/walk.py",
        "output/run-a/motor.npy",
        "output/run-a/result.json",
    ]
    assert inventory.total_file_count == 4
    assert inventory.total_bytes == sum(item.byte_length for item in inventory.files)
    assert inventory.files[1].sha256 == hashlib.sha256(b"seed = 42\n").hexdigest()
    assert [(item.collection_id, item.file_count) for item in inventory.collections] == [
        ("experiments", 1),
        ("output", 2),
    ]
    assert inventory.collections[1].role_counts == (("array", 1), ("result", 1))
    assert inventory.to_dict()["root"] == {
        "root_id": "org.flybrian.historical-estate.fixture",
        "revision": "fixture-revision-1",
        "logical_root": "flybrian-research",
        "license_id": "UNKNOWN",
        "access": "private",
        "redistribution": "prohibited",
    }
    assert str(tmp_path) not in inventory.canonical_bytes().decode("utf-8")
    assert inventory.sha256() == "cb9aee688ebe4bd6bb804f8eec7e40a983864c90a0509cb1cd2be82269eac404"


def test_relocation_preserves_identity(tmp_path: Path) -> None:
    first = tmp_path / "one"
    second = tmp_path / "two"
    first.mkdir()
    second.mkdir()
    write_fixture(first)
    write_fixture(second)

    left = inventory_historical_estate(authority(first))
    right = inventory_historical_estate(authority(second))
    assert left.canonical_bytes() == right.canonical_bytes()
    assert left.sha256() == right.sha256()


def test_content_path_and_authority_are_identity_sensitive(tmp_path: Path) -> None:
    write_fixture(tmp_path)
    base = inventory_historical_estate(authority(tmp_path))
    (tmp_path / "output" / "run-a" / "motor.npy").write_bytes(b"CHANGED")
    content_changed = inventory_historical_estate(authority(tmp_path))
    (tmp_path / "output" / "run-a" / "motor.npy").rename(
        tmp_path / "output" / "run-a" / "renamed.npy"
    )
    path_changed = inventory_historical_estate(authority(tmp_path))
    authority_changed = inventory_historical_estate(
        authority(tmp_path, revision="fixture-revision-2")
    )

    assert len({
        base.sha256(),
        content_changed.sha256(),
        path_changed.sha256(),
        authority_changed.sha256(),
    }) == 4


@pytest.mark.parametrize(
    "path",
    [
        "/absolute.json",
        "../escape.json",
        "a/../escape.json",
        "a\\windows.json",
        "a//empty.json",
        "a/control\n.json",
        "decomposed-e\u0301.json",
        "C:/drive.json",
        "a/trailing-space .json",
        "a/CON.json",
    ],
)
def test_unsafe_or_nonportable_logical_paths_reject(path: str) -> None:
    with pytest.raises(HistoricalEstateError):
        classify_historical_estate_file(path)


@pytest.mark.parametrize(
    "overrides",
    [
        {"root_id": "not-namespaced"},
        {"revision": ""},
        {"logical_root": "/absolute"},
        {"logical_root": "../escape"},
        {"license_id": ""},
        {"access": "public-ish"},
        {"redistribution": "maybe"},
    ],
)
def test_root_authority_validation(tmp_path: Path, overrides: dict[str, object]) -> None:
    with pytest.raises(HistoricalEstateError):
        authority(tmp_path, **overrides)


@pytest.mark.parametrize(
    "overrides",
    [
        {"max_files": 0},
        {"max_files": True},
        {"max_file_bytes": -1},
        {"max_total_bytes": 0},
        {"max_depth": 0},
        {"max_path_chars": 0},
    ],
)
def test_limits_must_be_positive_integers(overrides: dict[str, object]) -> None:
    with pytest.raises(HistoricalEstateError):
        HistoricalEstateLimits(**overrides)  # type: ignore[arg-type]


def test_file_count_file_size_and_aggregate_limits(tmp_path: Path) -> None:
    (tmp_path / "a.json").write_bytes(b"1234")
    (tmp_path / "b.json").write_bytes(b"5678")
    with pytest.raises(HistoricalEstateError, match="file count"):
        inventory_historical_estate(authority(tmp_path), HistoricalEstateLimits(max_files=1))
    with pytest.raises(HistoricalEstateError, match="per-file"):
        inventory_historical_estate(
            authority(tmp_path), HistoricalEstateLimits(max_file_bytes=3)
        )
    with pytest.raises(HistoricalEstateError, match="aggregate"):
        inventory_historical_estate(
            authority(tmp_path), HistoricalEstateLimits(max_total_bytes=7)
        )


@pytest.mark.parametrize(
    "relative_path",
    [
        ".env",
        "keys/private.pem",
        "credentials.json",
        "nested/api-token.txt",
        ".hidden/result.json",
    ],
)
def test_sensitive_and_hidden_paths_fail_closed(tmp_path: Path, relative_path: str) -> None:
    path = tmp_path.joinpath(*relative_path.split("/"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("must-not-enter-inventory", encoding="utf-8")
    with pytest.raises(HistoricalEstateError):
        inventory_historical_estate(authority(tmp_path))


def test_gitkeep_is_explicit_unknown_file(tmp_path: Path) -> None:
    (tmp_path / ".gitkeep").write_bytes(b"")
    inventory = inventory_historical_estate(authority(tmp_path))
    assert inventory.files[0].logical_path == ".gitkeep"
    assert inventory.files[0].candidate_role == "unknown"
    assert inventory.files[0].import_disposition == "review_required"


def test_only_fixed_platform_and_bytecode_entries_are_recorded_exclusions(
    tmp_path: Path,
) -> None:
    (tmp_path / ".DS_Store").write_bytes(b"platform metadata")
    (tmp_path / "loose.pyc").write_bytes(b"bytecode")
    cache = tmp_path / "pkg" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "module.cpython-312.pyc").write_bytes(b"cached bytecode")
    (tmp_path / "result.json").write_text("{}", encoding="utf-8")

    inventory = inventory_historical_estate(authority(tmp_path))
    assert inventory.total_file_count == 1
    assert inventory.excluded_entry_count == 3
    assert [item.to_dict() for item in inventory.exclusions] == [
        {
            "logical_path": ".DS_Store",
            "entry_kind": "file",
            "reason": "platform_metadata",
        },
        {
            "logical_path": "loose.pyc",
            "entry_kind": "file",
            "reason": "python_bytecode_cache",
        },
        {
            "logical_path": "pkg/__pycache__",
            "entry_kind": "directory",
            "reason": "python_bytecode_cache",
        },
    ]


def test_excluded_name_does_not_hide_a_symlink(tmp_path: Path) -> None:
    target = tmp_path / "target"
    target.write_text("not metadata", encoding="utf-8")
    link = tmp_path / ".DS_Store"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")
    with pytest.raises(HistoricalEstateError, match="symlink"):
        inventory_historical_estate(authority(tmp_path))


def test_casefold_collision_rejects(tmp_path: Path) -> None:
    digest = hashlib.sha256(b"{}").hexdigest()
    first = HistoricalEstateFile(
        "Run.json", 2, digest, "application/json", "result", "artifact_candidate", None
    )
    second = HistoricalEstateFile(
        "run.JSON", 2, digest, "application/json", "result", "artifact_candidate", None
    )
    with pytest.raises(HistoricalEstateError, match="case-fold"):
        HistoricalEstateInventory(
            root=authority(tmp_path),
            files=(first, second),
            exclusions=(),
            collections=(),
            total_file_count=2,
            excluded_entry_count=0,
            total_bytes=4,
        )


def test_symlink_rejects_without_following(tmp_path: Path) -> None:
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "linked.json"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation is unavailable on this host")
    with pytest.raises(HistoricalEstateError, match="symlink"):
        inventory_historical_estate(authority(tmp_path))


def test_mutation_during_hash_rejects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "result.json"
    source.write_bytes(b"a" * (1024 * 1024 + 1))
    original_read = estate_module._read_chunk
    mutated = False

    def mutate_after_first_read(descriptor: int, length: int) -> bytes:
        nonlocal mutated
        value = original_read(descriptor, length)
        if not mutated:
            mutated = True
            with source.open("ab") as stream:
                stream.write(b"changed")
        return value

    monkeypatch.setattr(estate_module, "_read_chunk", mutate_after_first_read)
    with pytest.raises(HistoricalEstateError, match="changed while being inventoried"):
        inventory_historical_estate(authority(tmp_path))


def test_scanner_never_parses_or_executes_payloads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "experiment.py").write_text("raise RuntimeError('executed')\n", encoding="utf-8")
    (tmp_path / "result.json").write_text("not-json", encoding="utf-8")
    (tmp_path / "array.npy").write_bytes(b"not-numpy")
    (tmp_path / "archive.zip").write_bytes(b"not-zip")

    def forbidden(*_args: object, **_kwargs: object) -> object:
        raise AssertionError("payload parser or executor was called")

    monkeypatch.setattr(json, "load", forbidden)
    monkeypatch.setattr(json, "loads", forbidden)
    inventory = inventory_historical_estate(authority(tmp_path))
    assert inventory.total_file_count == 4


def test_directory_depth_and_path_length_limits(tmp_path: Path) -> None:
    deep = tmp_path / "one" / "two"
    deep.mkdir(parents=True)
    (deep / "result.json").write_text("{}", encoding="utf-8")
    with pytest.raises(HistoricalEstateError, match="depth"):
        inventory_historical_estate(authority(tmp_path), HistoricalEstateLimits(max_depth=2))
    with pytest.raises(HistoricalEstateError, match="at most 10"):
        inventory_historical_estate(
            authority(tmp_path), HistoricalEstateLimits(max_path_chars=10)
        )


def test_large_metadata_cohort_is_complete_and_ordered(tmp_path: Path) -> None:
    count = 10_001
    for index in range(count):
        (tmp_path / f"result-{index:05d}.json").write_bytes(b"")
    inventory = inventory_historical_estate(
        authority(tmp_path), HistoricalEstateLimits(max_files=count)
    )
    assert inventory.total_file_count == count
    assert inventory.total_bytes == 0
    assert inventory.files[0].logical_path == "result-00000.json"
    assert inventory.files[-1].logical_path == "result-10000.json"
    assert len({item.logical_path for item in inventory.files}) == count
