from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path

import pytest

import flybrian_engine.acquisition as acquisition
from flybrian_engine.acquisition import (
    MANC_V121,
    AcquisitionCancelled,
    AcquisitionError,
    NeuprintPythonTransport,
    ProviderSnapshot,
    RetryableAcquisitionError,
    acquire_neuprint_release,
)
from flybrian_engine.datasets import DatasetManifest

TOKEN_SENTINEL = "TOP-SECRET-NEUPRINT-TOKEN"


def connection(pre_id: object, post_id: object, weight: object) -> dict[str, object]:
    return {
        "preId": pre_id,
        "preType": "pre-type",
        "preInstance": "pre-instance",
        "preNt": "acetylcholine",
        "postId": post_id,
        "postType": "post-type",
        "postInstance": "post-instance",
        "postNt": "glutamate",
        "total_weight": weight,
    }


def motor(body_id: object, nerve: str, target: str | None) -> dict[str, object]:
    return {
        "class": "motor neuron",
        "bodyid": body_id,
        "subclass": "hl",
        "systematic_type": "MNhl01",
        "exit_nerve": nerve,
        "target": target,
        "match_certainty(1-5)": None,
        "type": "motor type",
        "group": "group",
        "synonyms": None,
        "publication_match": None,
        "line_match": None,
        "match_notes": None,
    }


SNAPSHOT = ProviderSnapshot(
    server_url="https://neuprint.janelia.org",
    dataset="manc:v1.2.1",
    api_version="1.7.3",
    database_version="manc-v1.2.1-db",
    dataset_metadata_sha256="b" * 64,
)


class ScriptedTransport:
    def __init__(
        self,
        *,
        snapshots: tuple[ProviderSnapshot, ...] = (SNAPSHOT,),
        connection_pages: dict[tuple[int, int] | None, tuple[dict[str, object], ...]] | None = None,
        motor_pages: dict[int | None, tuple[dict[str, object], ...]] | None = None,
    ) -> None:
        self.snapshots = snapshots
        self.connection_pages = connection_pages or {
            None: (connection(1, 2, 3), connection(2, 3, 4)),
            (2, 3): (connection(3, 4, 5),),
            (3, 4): (),
        }
        self.motor_pages = motor_pages or {
            None: (motor(10347, "MetaLN_L", "Ti extensor"),),
            10347: (),
        }
        self.snapshot_calls = 0
        self.connection_calls: list[tuple[tuple[int, int] | None, int]] = []
        self.motor_calls: list[tuple[int | None, int]] = []
        self.token = TOKEN_SENTINEL

    def snapshot(self) -> ProviderSnapshot:
        value = self.snapshots[min(self.snapshot_calls, len(self.snapshots) - 1)]
        self.snapshot_calls += 1
        return value

    def fetch_connections(
        self, after: tuple[int, int] | None, limit: int
    ) -> tuple[dict[str, object], ...]:
        self.connection_calls.append((after, limit))
        return self.connection_pages[after]

    def fetch_motor_anatomy(self, after: int | None, limit: int) -> tuple[dict[str, object], ...]:
        self.motor_calls.append((after, limit))
        return self.motor_pages[after]


def test_acquisition_promotes_verified_manifest_receipt_and_is_idempotent(
    tmp_path: Path,
) -> None:
    transport = ScriptedTransport()
    staging = tmp_path / "acquisition"
    result = acquire_neuprint_release(MANC_V121, staging, transport, page_size=2)

    assert result.manifest.sha256() == result.receipt.manifest_sha256
    assert result.receipt.request_sha256
    assert result.receipt.initial_snapshot == SNAPSHOT
    assert result.receipt.final_snapshot == SNAPSHOT
    assert result.receipt.connection_rows == 3
    assert result.receipt.motor_anatomy_rows == 1
    assert result.manifest.license == "CC-BY-4.0"
    assert result.manifest.redistribution == "allowed"
    assert result.manifest.access == "token_required"
    assert [item.path for item in result.manifest.files] == [
        "connectivity.csv",
        "motor-anatomy.csv",
    ]
    assert result.manifest.verify(staging).manifest.sha256() == result.manifest.sha256()

    before_calls = (
        transport.snapshot_calls,
        list(transport.connection_calls),
        list(transport.motor_calls),
    )
    repeated = acquire_neuprint_release(MANC_V121, staging, transport, page_size=2)
    assert repeated.receipt.sha256() == result.receipt.sha256()
    assert (
        transport.snapshot_calls,
        transport.connection_calls,
        transport.motor_calls,
    ) == before_calls

    persisted = "\n".join(
        path.read_text(encoding="utf-8") for path in staging.iterdir() if path.is_file()
    )
    assert TOKEN_SENTINEL not in persisted


def test_resume_truncates_unjournaled_page_and_refetches_without_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    transport = ScriptedTransport()
    staging = tmp_path / "resume"
    original = acquisition._write_journal
    writes = 0

    def fail_second_write(path: Path, value: dict[str, object]) -> None:
        nonlocal writes
        writes += 1
        if writes == 2:
            raise OSError("injected journal replacement failure")
        original(path, value)

    monkeypatch.setattr(acquisition, "_write_journal", fail_second_write)
    with pytest.raises(OSError, match="injected journal replacement failure"):
        acquire_neuprint_release(MANC_V121, staging, transport, page_size=2)

    journal = json.loads((staging / ".flybrian-acquisition.json").read_text())
    header_offset = journal["streams"]["connectivity"]["committed_offset"]
    assert (staging / "connectivity.csv.part").stat().st_size > header_offset

    monkeypatch.setattr(acquisition, "_write_journal", original)
    result = acquire_neuprint_release(MANC_V121, staging, transport, page_size=2)
    with (staging / "connectivity.csv").open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert [(row["preId"], row["postId"]) for row in rows] == [
        ("1", "2"),
        ("2", "3"),
        ("3", "4"),
    ]
    assert transport.connection_calls.count((None, 2)) == 2
    assert result.receipt.connection_rows == 3


@pytest.mark.parametrize(
    ("pages", "message"),
    [
        ({None: (connection(1.5, 2, 3),)}, "must not be binary float"),
        (
            {None: (connection(2, 3, 1), connection(1, 4, 1))},
            "strictly increasing",
        ),
    ],
)
def test_invalid_provider_page_never_promotes(
    tmp_path: Path,
    pages: dict[tuple[int, int] | None, tuple[dict[str, object], ...]],
    message: str,
) -> None:
    transport = ScriptedTransport(connection_pages=pages)
    staging = tmp_path / "invalid"
    with pytest.raises(AcquisitionError, match=message):
        acquire_neuprint_release(MANC_V121, staging, transport, page_size=2)
    assert not (staging / "dataset-manifest.json").exists()
    assert not (staging / "acquisition-receipt.json").exists()
    assert not (staging / "connectivity.csv").exists()
    journal = json.loads((staging / ".flybrian-acquisition.json").read_text())
    assert journal["state"] == "FAILED_TERMINAL"


def test_changed_provider_snapshot_is_stale_and_never_promotes(tmp_path: Path) -> None:
    changed = replace(SNAPSHOT, database_version="changed-during-acquisition")
    transport = ScriptedTransport(snapshots=(SNAPSHOT, changed))
    staging = tmp_path / "stale"
    with pytest.raises(AcquisitionError, match="provider snapshot changed"):
        acquire_neuprint_release(MANC_V121, staging, transport, page_size=2)
    assert not (staging / "dataset-manifest.json").exists()
    assert not (staging / "acquisition-receipt.json").exists()
    assert (staging / "connectivity.csv.part").exists()
    assert (staging / "motor-anatomy.csv.part").exists()


def test_manifest_verification_failure_leaves_only_resumable_parts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    staging = tmp_path / "verify-failure"

    def fail_verification(self: DatasetManifest, root: Path) -> object:
        raise RuntimeError("injected manifest verification failure")

    monkeypatch.setattr(DatasetManifest, "verify", fail_verification)
    with pytest.raises(RuntimeError, match="injected manifest verification failure"):
        acquire_neuprint_release(MANC_V121, staging, ScriptedTransport(), page_size=2)

    assert (staging / "connectivity.csv.part").exists()
    assert (staging / "motor-anatomy.csv.part").exists()
    for name in (
        "connectivity.csv",
        "motor-anatomy.csv",
        "dataset-manifest.json",
        "acquisition-receipt.json",
    ):
        assert not (staging / name).exists()


def test_promoted_request_conflict_does_not_contact_provider_or_overwrite(
    tmp_path: Path,
) -> None:
    staging = tmp_path / "conflict"
    acquire_neuprint_release(MANC_V121, staging, ScriptedTransport(), page_size=2)
    before = {path.name: path.read_bytes() for path in staging.iterdir()}
    conflicting = ScriptedTransport()

    with pytest.raises(AcquisitionError, match="conflicts with requested release"):
        acquire_neuprint_release(MANC_V121, staging, conflicting, page_size=3)

    assert conflicting.snapshot_calls == 0
    assert conflicting.connection_calls == []
    assert conflicting.motor_calls == []
    assert {path.name: path.read_bytes() for path in staging.iterdir()} == before


class RetryOnceTransport(ScriptedTransport):
    def __init__(self) -> None:
        super().__init__()
        self.remaining_failures = 1

    def fetch_connections(
        self, after: tuple[int, int] | None, limit: int
    ) -> tuple[dict[str, object], ...]:
        if self.remaining_failures:
            self.remaining_failures -= 1
            raise RetryableAcquisitionError("scripted temporary failure")
        return super().fetch_connections(after, limit)


def test_retryable_failure_records_resume_state_and_continues_from_durable_cursor(
    tmp_path: Path,
) -> None:
    staging = tmp_path / "retryable"
    transport = RetryOnceTransport()
    with pytest.raises(RetryableAcquisitionError, match="temporary failure"):
        acquire_neuprint_release(MANC_V121, staging, transport, page_size=2)

    failed = json.loads((staging / ".flybrian-acquisition.json").read_text())
    assert failed["state"] == "FAILED_RETRYABLE"
    assert failed["resume_state"] == "SNAPSHOTTED"
    assert failed["failure_kind"] == "retryable"

    result = acquire_neuprint_release(MANC_V121, staging, transport, page_size=2)
    assert result.receipt.connection_rows == 3
    assert transport.connection_calls[0] == (None, 2)


def test_cancellation_is_observed_between_pages_and_remains_resumable(tmp_path: Path) -> None:
    staging = tmp_path / "cancelled"
    transport = ScriptedTransport()
    with pytest.raises(AcquisitionCancelled, match="durable page boundary"):
        acquire_neuprint_release(
            MANC_V121,
            staging,
            transport,
            page_size=2,
            cancelled=lambda: True,
        )
    failed = json.loads((staging / ".flybrian-acquisition.json").read_text())
    assert failed["state"] == "FAILED_RETRYABLE"
    assert failed["failure_kind"] == "cancelled"
    assert transport.connection_calls == []

    result = acquire_neuprint_release(
        MANC_V121,
        staging,
        transport,
        page_size=2,
        cancelled=lambda: False,
    )
    assert result.receipt.connection_rows == 3


class FakeNeuprintClient:
    def __init__(self, server: str, dataset: str, token: str, **kwargs: object) -> None:
        self.server = server
        self.dataset = dataset
        self.received_token = token
        self.kwargs = kwargs
        self.queries: list[str] = []
        self.fail_with_token = False
        self.failure: Exception | None = None

    def fetch_version(self) -> str:
        return "1.7.3"

    def fetch_db_version(self) -> str:
        return "db-v1"

    def fetch_datasets(self) -> dict[str, object]:
        return {"manc:v1.2.1": {"lastDatabaseEdit": "fixed"}}

    def fetch_custom(self, query: str, format: str) -> dict[str, object]:
        assert format == "json"
        self.queries.append(query)
        if self.failure is not None:
            raise self.failure
        if self.fail_with_token:
            raise RuntimeError(TOKEN_SENTINEL)
        if "ORDER BY bodyid" in query:
            return {
                "columns": [
                    "class",
                    "bodyid",
                    "subclass",
                    "systematic_type",
                    "exit_nerve",
                    "target",
                    "match_certainty(1-5)",
                    "type",
                    "group",
                    "synonyms",
                    "publication_match",
                    "line_match",
                    "match_notes",
                ],
                "data": [
                    [
                        "motor neuron",
                        10347,
                        "hl",
                        "MNhl01",
                        "MetaLN_L",
                        "Ti extensor",
                        None,
                        "motor type",
                        1,
                        None,
                        None,
                        None,
                        "reviewed",
                    ]
                ],
            }
        return {
            "columns": [
                "preId",
                "preType",
                "preInstance",
                "preNt",
                "postId",
                "postType",
                "postInstance",
                "postNt",
                "total_weight",
            ],
            "data": [[1, "a", "a1", "acetylcholine", 2, "b", "b1", "gaba", 3]],
        }


def test_optional_neuprint_adapter_uses_fixed_query_and_sanitizes_failures() -> None:
    clients: list[FakeNeuprintClient] = []

    def factory(server: str, dataset: str, token: str, **kwargs: object) -> FakeNeuprintClient:
        client = FakeNeuprintClient(server, dataset, token, **kwargs)
        clients.append(client)
        return client

    transport = NeuprintPythonTransport(MANC_V121, TOKEN_SENTINEL, client_factory=factory)
    assert transport.snapshot().dataset == "manc:v1.2.1"
    rows = transport.fetch_connections(None, 10)
    assert rows[0]["preId"] == 1
    assert "ORDER BY preId, postId" in clients[0].queries[0]
    assert TOKEN_SENTINEL not in clients[0].queries[0]
    assert TOKEN_SENTINEL not in repr(transport)
    assert "pre.predictedNt AS preNt" in clients[0].queries[0]

    motor_rows = transport.fetch_motor_anatomy(None, 10)
    assert motor_rows[0]["bodyid"] == 10347
    motor_query = clients[0].queries[1]
    assert "n.systematicType AS systematic_type" in motor_query
    assert "n.exitNerve AS exit_nerve" in motor_query
    assert "n.matchingNotes AS match_notes" in motor_query
    assert "n.systematic_type" not in motor_query

    clients[0].fail_with_token = True
    with pytest.raises(AcquisitionError) as failure:
        transport.fetch_connections(None, 10)
    assert TOKEN_SENTINEL not in str(failure.value)


def test_optional_neuprint_adapter_classifies_retryable_provider_status() -> None:
    class ProviderFailure(RuntimeError):
        status_code = 429

    clients: list[FakeNeuprintClient] = []

    def factory(server: str, dataset: str, token: str, **kwargs: object) -> FakeNeuprintClient:
        client = FakeNeuprintClient(server, dataset, token, **kwargs)
        clients.append(client)
        return client

    transport = NeuprintPythonTransport(MANC_V121, TOKEN_SENTINEL, client_factory=factory)
    clients[0].failure = ProviderFailure(TOKEN_SENTINEL)
    with pytest.raises(RetryableAcquisitionError) as failure:
        transport.fetch_connections(None, 10)
    assert TOKEN_SENTINEL not in str(failure.value)


def test_release_profile_rejects_unconfirmed_version_relabel() -> None:
    with pytest.raises(AcquisitionError, match="profile dataset identity"):
        replace(MANC_V121, dataset="manc:v1.0")

    manifest = DatasetManifest.from_dict(
        {
            "schema_version": "1.0",
            "dataset_id": "fixture:v1",
            "provider": "provider",
            "release": "v1",
            "source_url": "https://example.test",
            "citation": None,
            "license": "unknown",
            "redistribution": "unknown",
            "access": "restricted",
            "files": [
                {
                    "role": "extension",
                    "path": "fixture.csv",
                    "sha256": "0" * 64,
                    "size_bytes": 0,
                    "media_type": "text/csv",
                    "schema_id": "fixture.v1",
                    "data_rows": 0,
                }
            ],
        }
    )
    assert manifest.license == "unknown"
