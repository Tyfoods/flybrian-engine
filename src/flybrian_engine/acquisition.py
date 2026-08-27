"""Release-pinned, resumable NeuPrint acquisition for public FlyBrian datasets."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, cast

from .datasets import DatasetFile, DatasetManifest
from .ingestion import CONNECTION_SCHEMA, MOTOR_ANATOMY_SCHEMA

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_PROFILE_ID = "janelia-manc-v1.2.1-neuprint-v1"
_JOURNAL = ".flybrian-acquisition.json"
_MANIFEST = "dataset-manifest.json"
_RECEIPT = "acquisition-receipt.json"
_CONNECTION_PART = "connectivity.csv.part"
_MOTOR_PART = "motor-anatomy.csv.part"
_CONNECTION_FINAL = "connectivity.csv"
_MOTOR_FINAL = "motor-anatomy.csv"
_OWNED_NAMES = {
    _JOURNAL,
    _MANIFEST,
    _RECEIPT,
    _CONNECTION_PART,
    _MOTOR_PART,
    _CONNECTION_FINAL,
    _MOTOR_FINAL,
}

CONNECTION_FIELDS = (
    "preId",
    "preType",
    "preInstance",
    "preNt",
    "postId",
    "postType",
    "postInstance",
    "postNt",
    "total_weight",
)
MOTOR_ANATOMY_FIELDS = (
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
)


class AcquisitionError(ValueError):
    """Acquisition cannot safely continue or promote its staged data."""


class RetryableAcquisitionError(AcquisitionError):
    """Provider failure may be retried from the last durable journal cursor."""


class AcquisitionCancelled(RetryableAcquisitionError):
    """Caller requested a resumable stop between bounded provider pages."""


@dataclass(frozen=True)
class NeuprintReleaseProfile:
    """Immutable provider, release, query, attribution, and access authority."""

    profile_id: str
    provider: str
    server_url: str
    dataset: str
    release: str
    source_url: str
    citation: str
    license: str
    redistribution: str
    access: str
    query_profile_version: str
    modified_representation: bool

    def __post_init__(self) -> None:
        if self.profile_id == _PROFILE_ID:
            expected = {
                "provider": "Janelia Research Campus",
                "server_url": "https://neuprint.janelia.org",
                "dataset": "manc:v1.2.1",
                "release": "v1.2.1",
                "source_url": "https://neuprint.janelia.org",
                "citation": "10.7554/eLife.97769.1",
                "license": "CC-BY-4.0",
                "redistribution": "allowed",
                "access": "token_required",
                "query_profile_version": "manc-v1.2.1-neuprint-v1",
                "modified_representation": True,
            }
            actual = {name: getattr(self, name) for name in expected}
            if actual != expected:
                raise AcquisitionError("release profile dataset identity is immutable")
        if not self.profile_id or not self.dataset or not self.query_profile_version:
            raise AcquisitionError("release profile identity fields must be non-empty")

    def to_dict(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "provider": self.provider,
            "server_url": self.server_url,
            "dataset": self.dataset,
            "release": self.release,
            "source_url": self.source_url,
            "citation": self.citation,
            "license": self.license,
            "redistribution": self.redistribution,
            "access": self.access,
            "query_profile_version": self.query_profile_version,
            "modified_representation": self.modified_representation,
        }

    def sha256(self) -> str:
        return _sha256_json(self.to_dict())


MANC_V121 = NeuprintReleaseProfile(
    profile_id=_PROFILE_ID,
    provider="Janelia Research Campus",
    server_url="https://neuprint.janelia.org",
    dataset="manc:v1.2.1",
    release="v1.2.1",
    source_url="https://neuprint.janelia.org",
    citation="10.7554/eLife.97769.1",
    license="CC-BY-4.0",
    redistribution="allowed",
    access="token_required",
    query_profile_version="manc-v1.2.1-neuprint-v1",
    modified_representation=True,
)


@dataclass(frozen=True)
class ProviderSnapshot:
    """Provider identity observed before and after a complete acquisition."""

    server_url: str
    dataset: str
    api_version: str
    database_version: str
    dataset_metadata_sha256: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value
            for value in (self.server_url, self.dataset, self.api_version, self.database_version)
        ):
            raise AcquisitionError("provider snapshot identity fields must be non-empty strings")
        if _SHA256.fullmatch(self.dataset_metadata_sha256) is None:
            raise AcquisitionError("provider snapshot metadata hash must be lower-case SHA-256")

    def to_dict(self) -> dict[str, str]:
        return {
            "server_url": self.server_url,
            "dataset": self.dataset,
            "api_version": self.api_version,
            "database_version": self.database_version,
            "dataset_metadata_sha256": self.dataset_metadata_sha256,
        }

    @classmethod
    def from_dict(cls, value: object) -> ProviderSnapshot:
        record = _exact_object(
            value,
            {
                "server_url",
                "dataset",
                "api_version",
                "database_version",
                "dataset_metadata_sha256",
            },
            "provider snapshot",
        )
        return cls(**{name: _required_string(record[name], name) for name in record})

    def sha256(self) -> str:
        return _sha256_json(self.to_dict())


class NeuprintTransport(Protocol):
    """Bounded provider operations needed by the acquisition state machine."""

    def snapshot(self) -> ProviderSnapshot: ...

    def fetch_connections(
        self, after: tuple[int, int] | None, limit: int
    ) -> Sequence[Mapping[str, object]]: ...

    def fetch_motor_anatomy(
        self, after: int | None, limit: int
    ) -> Sequence[Mapping[str, object]]: ...


class _NeuprintClient(Protocol):
    def fetch_version(self) -> object: ...

    def fetch_db_version(self) -> object: ...

    def fetch_datasets(self) -> object: ...

    def fetch_custom(self, query: str, *, format: str) -> object: ...


ClientFactory = Callable[..., _NeuprintClient]


class NeuprintPythonTransport:
    """Optional neuprint-python adapter with fixed, release-scoped Cypher queries."""

    def __init__(
        self,
        profile: NeuprintReleaseProfile,
        token: str | None = None,
        *,
        client_factory: ClientFactory | None = None,
    ) -> None:
        credential = (
            token if token is not None else os.environ.get("NEUPRINT_APPLICATION_CREDENTIALS")
        )
        if not credential:
            raise AcquisitionError(
                "NeuPrint token is required via constructor or NEUPRINT_APPLICATION_CREDENTIALS"
            )
        if client_factory is None:
            try:
                client = vars(import_module("neuprint"))["Client"]
            except (ImportError, KeyError) as error:
                raise AcquisitionError(
                    "neuprint-python is not installed; install flybrian-engine[neuprint]"
                ) from error
            client_factory = cast(ClientFactory, client)
        try:
            self._client = client_factory(
                profile.server_url,
                dataset=profile.dataset,
                token=credential,
                verify=True,
                progress=False,
            )
        except Exception as error:
            raise _provider_error(error, "NeuPrint client initialization") from None
        self._profile = profile

    def __repr__(self) -> str:
        return (
            "NeuprintPythonTransport("
            f"profile_id={self._profile.profile_id!r}, dataset={self._profile.dataset!r})"
        )

    def snapshot(self) -> ProviderSnapshot:
        try:
            api_version = str(self._client.fetch_version())
            database_version = str(self._client.fetch_db_version())
            datasets = self._client.fetch_datasets()
            if not isinstance(datasets, dict) or self._profile.dataset not in datasets:
                raise AcquisitionError("configured NeuPrint dataset is not advertised")
            metadata_hash = _sha256_json(_json_value(datasets[self._profile.dataset]))
            return ProviderSnapshot(
                server_url=self._profile.server_url,
                dataset=self._profile.dataset,
                api_version=api_version,
                database_version=database_version,
                dataset_metadata_sha256=metadata_hash,
            )
        except AcquisitionError:
            raise
        except Exception as error:
            raise _provider_error(error, "NeuPrint snapshot request") from None

    def fetch_connections(
        self, after: tuple[int, int] | None, limit: int
    ) -> tuple[dict[str, object], ...]:
        where = ""
        if after is not None:
            where = (
                "WHERE pre.bodyId > "
                f"{after[0]} OR (pre.bodyId = {after[0]} AND post.bodyId > {after[1]})\n"
            )
        query = (
            "MATCH (pre:Neuron)-[edge:ConnectsTo]->(post:Neuron)\n"
            f"{where}"
            "WITH pre, post, sum(edge.weight) AS total_weight\n"
            "RETURN pre.bodyId AS preId, pre.type AS preType, pre.instance AS preInstance, "
            "pre.predictedNt AS preNt, post.bodyId AS postId, post.type AS postType, "
            "post.instance AS postInstance, post.predictedNt AS postNt, total_weight\n"
            f"ORDER BY preId, postId LIMIT {limit}"
        )
        return self._fetch_json(query, CONNECTION_FIELDS)

    def fetch_motor_anatomy(self, after: int | None, limit: int) -> tuple[dict[str, object], ...]:
        cursor = "" if after is None else f" AND n.bodyId > {after}"
        query = (
            "MATCH (n:Neuron)\n"
            f"WHERE n.class = 'motor neuron'{cursor}\n"
            "RETURN n.class AS class, n.bodyId AS bodyid, n.subclass AS subclass, "
            "n.systematicType AS systematic_type, n.exitNerve AS exit_nerve, "
            "n.target AS target, null AS `match_certainty(1-5)`, "
            "n.type AS type, n.group AS group, n.synonyms AS synonyms, "
            "null AS publication_match, null AS line_match, n.matchingNotes AS match_notes\n"
            f"ORDER BY bodyid LIMIT {limit}"
        )
        return self._fetch_json(query, MOTOR_ANATOMY_FIELDS)

    def _fetch_json(
        self, query: str, expected_fields: tuple[str, ...]
    ) -> tuple[dict[str, object], ...]:
        try:
            response = self._client.fetch_custom(query, format="json")
            record = _exact_object(response, {"columns", "data"}, "NeuPrint response")
            columns = record["columns"]
            data = record["data"]
            if not isinstance(columns, list) or tuple(columns) != expected_fields:
                raise AcquisitionError("NeuPrint response columns differ from fixed query schema")
            if not isinstance(data, list):
                raise AcquisitionError("NeuPrint response data must be an array")
            rows: list[dict[str, object]] = []
            for index, raw in enumerate(data):
                if not isinstance(raw, list) or len(raw) != len(columns):
                    raise AcquisitionError(f"NeuPrint response row {index} width differs")
                rows.append(dict(zip(expected_fields, raw, strict=True)))
            return tuple(rows)
        except AcquisitionError:
            raise
        except Exception as error:
            raise _provider_error(error, "NeuPrint request") from None


@dataclass(frozen=True)
class AcquisitionReceipt:
    request_sha256: str
    profile_sha256: str
    query_profile_version: str
    modified_representation: bool
    initial_snapshot: ProviderSnapshot
    final_snapshot: ProviderSnapshot
    manifest_sha256: str
    connection_rows: int
    motor_anatomy_rows: int
    license: str
    schema_version: str = "1.0"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "request_sha256": self.request_sha256,
            "profile_sha256": self.profile_sha256,
            "query_profile_version": self.query_profile_version,
            "modified_representation": self.modified_representation,
            "initial_snapshot": self.initial_snapshot.to_dict(),
            "final_snapshot": self.final_snapshot.to_dict(),
            "manifest_sha256": self.manifest_sha256,
            "connection_rows": self.connection_rows,
            "motor_anatomy_rows": self.motor_anatomy_rows,
            "license": self.license,
        }

    @classmethod
    def from_dict(cls, value: object) -> AcquisitionReceipt:
        fields = {
            "schema_version",
            "request_sha256",
            "profile_sha256",
            "query_profile_version",
            "modified_representation",
            "initial_snapshot",
            "final_snapshot",
            "manifest_sha256",
            "connection_rows",
            "motor_anatomy_rows",
            "license",
        }
        record = _exact_object(value, fields, "acquisition receipt")
        if record["schema_version"] != "1.0":
            raise AcquisitionError("acquisition receipt schema_version must equal '1.0'")
        for name in ("request_sha256", "profile_sha256", "manifest_sha256"):
            if not isinstance(record[name], str) or _SHA256.fullmatch(record[name]) is None:
                raise AcquisitionError(f"acquisition receipt {name} must be lower-case SHA-256")
        modified = record["modified_representation"]
        if not isinstance(modified, bool):
            raise AcquisitionError("acquisition receipt modified_representation must be boolean")
        return cls(
            request_sha256=cast(str, record["request_sha256"]),
            profile_sha256=cast(str, record["profile_sha256"]),
            query_profile_version=_required_string(
                record["query_profile_version"], "query_profile_version"
            ),
            modified_representation=modified,
            initial_snapshot=ProviderSnapshot.from_dict(record["initial_snapshot"]),
            final_snapshot=ProviderSnapshot.from_dict(record["final_snapshot"]),
            manifest_sha256=cast(str, record["manifest_sha256"]),
            connection_rows=_nonnegative_int(record["connection_rows"], "connection_rows"),
            motor_anatomy_rows=_nonnegative_int(record["motor_anatomy_rows"], "motor_anatomy_rows"),
            license=_required_string(record["license"], "license"),
        )

    def sha256(self) -> str:
        return _sha256_json(self.to_dict())


@dataclass(frozen=True)
class AcquisitionResult:
    manifest: DatasetManifest
    receipt: AcquisitionReceipt


def acquire_neuprint_release(
    profile: NeuprintReleaseProfile,
    staging: Path,
    transport: NeuprintTransport,
    *,
    page_size: int = 10_000,
    cancelled: Callable[[], bool] | None = None,
) -> AcquisitionResult:
    """Acquire one immutable release with keyset pages and receipt-last promotion."""
    if (
        isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or not 1 <= page_size <= 50_000
    ):
        raise AcquisitionError("page_size must be an integer between 1 and 50000")
    root = _prepare_staging(staging)
    request_sha256 = _sha256_json(
        {
            "profile_sha256": profile.sha256(),
            "query_profile_version": profile.query_profile_version,
            "page_size": page_size,
        }
    )
    promoted = _load_promoted(root, profile, request_sha256)
    if promoted is not None:
        return promoted

    _recover_partial_promotion(root)
    journal_path = root / _JOURNAL
    if journal_path.exists():
        journal = _load_json(journal_path, "acquisition journal")
        _validate_journal(journal, profile, request_sha256, page_size)
        initial_snapshot = ProviderSnapshot.from_dict(journal["initial_snapshot"])
        try:
            current_snapshot = _transport_snapshot(transport)
        except AcquisitionError as error:
            _record_failure(journal_path, journal, error)
            raise
        if current_snapshot != initial_snapshot:
            journal["state"] = "STALE"
            _write_journal(journal_path, journal)
            raise AcquisitionError("provider snapshot changed before acquisition resume")
        if journal["state"] == "FAILED_RETRYABLE":
            resume_state = journal.pop("resume_state", None)
            if resume_state not in {
                "SNAPSHOTTED",
                "CONNECTIONS",
                "MOTOR_ANATOMY",
                "VERIFYING",
            }:
                raise AcquisitionError("retryable journal has no valid resume state")
            journal["state"] = resume_state
            journal.pop("failure_kind", None)
            journal["updated_at"] = _now()
            _write_journal(journal_path, journal)
    else:
        initial_snapshot = _transport_snapshot(transport)
        _validate_snapshot(profile, initial_snapshot)
        offsets = {
            "connectivity": _create_part(root / _CONNECTION_PART, CONNECTION_FIELDS),
            "motor_anatomy": _create_part(root / _MOTOR_PART, MOTOR_ANATOMY_FIELDS),
        }
        journal = {
            "schema_version": "1.0",
            "request_sha256": request_sha256,
            "profile_sha256": profile.sha256(),
            "page_size": page_size,
            "state": "SNAPSHOTTED",
            "initial_snapshot": initial_snapshot.to_dict(),
            "streams": {
                "connectivity": _new_stream(offsets["connectivity"]),
                "motor_anatomy": _new_stream(offsets["motor_anatomy"]),
            },
            "updated_at": _now(),
        }
        _write_journal(journal_path, journal)

    _truncate_to_journal(root, journal)
    if not _stream(journal, "connectivity")["complete"]:
        _acquire_connections(root, journal_path, journal, transport, page_size, cancelled)
    if not _stream(journal, "motor_anatomy")["complete"]:
        _acquire_motor_anatomy(root, journal_path, journal, transport, page_size, cancelled)

    journal["state"] = "VERIFYING"
    journal["updated_at"] = _now()
    _write_journal(journal_path, journal)
    try:
        _check_cancelled(cancelled)
        final_snapshot = _transport_snapshot(transport)
    except AcquisitionError as error:
        _record_failure(journal_path, journal, error)
        raise
    if final_snapshot != initial_snapshot:
        journal["state"] = "STALE"
        journal["updated_at"] = _now()
        _write_journal(journal_path, journal)
        raise AcquisitionError("provider snapshot changed during acquisition")

    result = _promote(
        root,
        profile,
        request_sha256,
        initial_snapshot,
        final_snapshot,
        journal,
    )
    journal["state"] = "PROMOTED"
    journal["updated_at"] = _now()
    _write_journal(journal_path, journal)
    return result


def _transport_snapshot(transport: NeuprintTransport) -> ProviderSnapshot:
    try:
        snapshot = transport.snapshot()
    except AcquisitionError:
        raise
    except Exception:
        raise AcquisitionError("provider snapshot request failed") from None
    if not isinstance(snapshot, ProviderSnapshot):
        raise AcquisitionError("transport returned an invalid provider snapshot")
    return snapshot


def _provider_error(error: Exception, operation: str) -> AcquisitionError:
    response = _attribute(error, "response")
    status = _attribute(error, "status_code")
    if status is None and response is not None:
        status = _attribute(response, "status_code")
    if status == 429 or (isinstance(status, int) and status >= 500):
        return RetryableAcquisitionError(f"{operation} is temporarily unavailable")
    if (
        isinstance(error, (TimeoutError, ConnectionError))
        or "timeout" in type(error).__name__.lower()
    ):
        return RetryableAcquisitionError(f"{operation} timed out")
    if status in {401, 403}:
        return AcquisitionError(f"{operation} authorization failed")
    if status == 404:
        return AcquisitionError(f"{operation} release was not found")
    return AcquisitionError(f"{operation} failed")


def _attribute(value: object, name: str) -> object:
    return getattr(value, name, None)


def _check_cancelled(cancelled: Callable[[], bool] | None) -> None:
    if cancelled is not None and cancelled():
        raise AcquisitionCancelled("acquisition cancelled at durable page boundary")


def _record_failure(journal_path: Path, journal: dict[str, Any], error: AcquisitionError) -> None:
    state = journal.get("state")
    if isinstance(error, RetryableAcquisitionError):
        if state != "FAILED_RETRYABLE":
            journal["resume_state"] = state
        journal["state"] = "FAILED_RETRYABLE"
        journal["failure_kind"] = (
            "cancelled" if isinstance(error, AcquisitionCancelled) else "retryable"
        )
    else:
        journal.pop("resume_state", None)
        journal["state"] = "FAILED_TERMINAL"
        journal["failure_kind"] = "terminal"
    journal["updated_at"] = _now()
    _write_journal(journal_path, journal)


def _validate_snapshot(profile: NeuprintReleaseProfile, snapshot: ProviderSnapshot) -> None:
    if snapshot.server_url != profile.server_url or snapshot.dataset != profile.dataset:
        raise AcquisitionError("provider snapshot does not match release profile")


def _prepare_staging(staging: Path) -> Path:
    if not isinstance(staging, Path):
        raise AcquisitionError("staging must be a pathlib.Path")
    if staging.is_symlink():
        raise AcquisitionError("staging directory must not be a symbolic link")
    try:
        staging.mkdir(parents=True, exist_ok=True)
        root = staging.resolve(strict=True)
    except OSError as error:
        raise AcquisitionError("cannot create acquisition staging directory") from error
    if not root.is_dir():
        raise AcquisitionError("acquisition staging path must be a directory")
    for item in root.iterdir():
        if item.is_symlink():
            raise AcquisitionError(
                f"owned acquisition path {item.name} must not be a symbolic link"
            )
        if item.name.endswith(".tmp") and item.name.removesuffix(".tmp") in _OWNED_NAMES:
            if not item.is_file():
                raise AcquisitionError(f"temporary acquisition path {item.name} must be a file")
            item.unlink()
        elif item.name not in _OWNED_NAMES:
            raise AcquisitionError(f"staging directory contains unowned path {item.name}")
        elif not item.is_file():
            raise AcquisitionError(f"owned acquisition path {item.name} must be a regular file")
    return root


def _load_promoted(
    root: Path, profile: NeuprintReleaseProfile, request_sha256: str
) -> AcquisitionResult | None:
    receipt_path = root / _RECEIPT
    if not receipt_path.exists():
        return None
    receipt = AcquisitionReceipt.from_dict(_load_json(receipt_path, "acquisition receipt"))
    if receipt.request_sha256 != request_sha256 or receipt.profile_sha256 != profile.sha256():
        raise AcquisitionError("promoted acquisition conflicts with requested release")
    if (
        receipt.query_profile_version != profile.query_profile_version
        or receipt.modified_representation != profile.modified_representation
        or receipt.license != profile.license
        or receipt.initial_snapshot != receipt.final_snapshot
    ):
        raise AcquisitionError("promoted acquisition receipt differs from release profile")
    _validate_snapshot(profile, receipt.initial_snapshot)
    manifest_path = root / _MANIFEST
    if not manifest_path.exists():
        raise AcquisitionError("promoted acquisition is missing its manifest")
    manifest = DatasetManifest.from_dict(_load_json(manifest_path, "dataset manifest"))
    if manifest.sha256() != receipt.manifest_sha256:
        raise AcquisitionError("promoted acquisition manifest hash differs from receipt")
    manifest.verify(root)
    return AcquisitionResult(manifest, receipt)


def _recover_partial_promotion(root: Path) -> None:
    if (root / _RECEIPT).exists():
        return
    for final_name, part_name in (
        (_CONNECTION_FINAL, _CONNECTION_PART),
        (_MOTOR_FINAL, _MOTOR_PART),
    ):
        final = root / final_name
        part = root / part_name
        if final.exists():
            if part.exists():
                raise AcquisitionError(
                    f"partial promotion contains both {final_name} and {part_name}"
                )
            final.replace(part)
    manifest = root / _MANIFEST
    if manifest.exists():
        manifest.unlink()


def _create_part(path: Path, fields: tuple[str, ...]) -> int:
    if path.exists():
        raise AcquisitionError(f"new acquisition unexpectedly found {path.name}")
    payload = _csv_payload(fields, ())
    try:
        with path.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except OSError as error:
        raise AcquisitionError(f"cannot create acquisition file {path.name}") from error
    return len(payload)


def _new_stream(offset: int) -> dict[str, object]:
    return {
        "committed_offset": offset,
        "rows": 0,
        "cursor": None,
        "complete": False,
    }


def _validate_journal(
    journal: dict[str, Any],
    profile: NeuprintReleaseProfile,
    request_sha256: str,
    page_size: int,
) -> None:
    if journal.get("schema_version") != "1.0":
        raise AcquisitionError("acquisition journal schema version is unsupported")
    if journal.get("request_sha256") != request_sha256:
        raise AcquisitionError("staged acquisition conflicts with requested release")
    if journal.get("profile_sha256") != profile.sha256() or journal.get("page_size") != page_size:
        raise AcquisitionError("staged acquisition profile or page size differs")
    state = journal.get("state")
    allowed_states = {
        "SNAPSHOTTED",
        "CONNECTIONS",
        "MOTOR_ANATOMY",
        "VERIFYING",
        "PROMOTED",
        "STALE",
        "FAILED_RETRYABLE",
        "FAILED_TERMINAL",
    }
    if state not in allowed_states:
        raise AcquisitionError("acquisition journal state is unsupported")
    if state in {"STALE", "FAILED_TERMINAL"}:
        raise AcquisitionError(f"staged acquisition is terminal: {journal['state']}")
    if state == "FAILED_RETRYABLE" and journal.get("resume_state") not in {
        "SNAPSHOTTED",
        "CONNECTIONS",
        "MOTOR_ANATOMY",
        "VERIFYING",
    }:
        raise AcquisitionError("retryable journal has no valid resume state")
    ProviderSnapshot.from_dict(journal.get("initial_snapshot"))
    for name in ("connectivity", "motor_anatomy"):
        stream = _stream(journal, name)
        _nonnegative_int(stream.get("committed_offset"), f"{name}.committed_offset")
        _nonnegative_int(stream.get("rows"), f"{name}.rows")
        if not isinstance(stream.get("complete"), bool):
            raise AcquisitionError(f"journal stream {name}.complete must be boolean")


def _stream(journal: dict[str, Any], name: str) -> dict[str, Any]:
    streams = journal.get("streams")
    if not isinstance(streams, dict) or set(streams) != {"connectivity", "motor_anatomy"}:
        raise AcquisitionError("acquisition journal streams differ")
    stream = streams.get(name)
    if not isinstance(stream, dict):
        raise AcquisitionError(f"acquisition journal stream {name} is invalid")
    return stream


def _truncate_to_journal(root: Path, journal: dict[str, Any]) -> None:
    for name, filename in (
        ("connectivity", _CONNECTION_PART),
        ("motor_anatomy", _MOTOR_PART),
    ):
        stream = _stream(journal, name)
        offset = _nonnegative_int(stream["committed_offset"], f"{name}.committed_offset")
        path = root / filename
        if not path.exists() or path.is_symlink():
            raise AcquisitionError(f"journaled acquisition file {filename} is missing or unsafe")
        size = path.stat().st_size
        if size < offset:
            raise AcquisitionError(f"journal for {filename} advances beyond durable bytes")
        if size != offset:
            with path.open("r+b") as handle:
                handle.truncate(offset)
                handle.flush()
                os.fsync(handle.fileno())


def _acquire_connections(
    root: Path,
    journal_path: Path,
    journal: dict[str, Any],
    transport: NeuprintTransport,
    page_size: int,
    cancelled: Callable[[], bool] | None,
) -> None:
    stream = _stream(journal, "connectivity")
    cursor = _connection_cursor(stream.get("cursor"))
    while True:
        try:
            _check_cancelled(cancelled)
            raw_page = transport.fetch_connections(cursor, page_size)
        except AcquisitionError as error:
            _record_failure(journal_path, journal, error)
            raise
        except Exception:
            failure = AcquisitionError("connection page request failed")
            _record_failure(journal_path, journal, failure)
            raise failure from None
        try:
            if len(raw_page) > page_size:
                raise AcquisitionError("connection provider page exceeds requested page size")
            rows, next_cursor = _connection_page(raw_page, cursor)
        except AcquisitionError as error:
            _record_failure(journal_path, journal, error)
            raise
        if not rows:
            stream["complete"] = True
            journal["state"] = "MOTOR_ANATOMY"
            journal["updated_at"] = _now()
            _write_journal(journal_path, journal)
            return
        offset = _append_page(root / _CONNECTION_PART, CONNECTION_FIELDS, rows)
        stream["committed_offset"] = offset
        stream["rows"] = _nonnegative_int(stream["rows"], "connectivity.rows") + len(rows)
        stream["cursor"] = list(next_cursor)
        journal["state"] = "CONNECTIONS"
        journal["updated_at"] = _now()
        _write_journal(journal_path, journal)
        cursor = next_cursor


def _acquire_motor_anatomy(
    root: Path,
    journal_path: Path,
    journal: dict[str, Any],
    transport: NeuprintTransport,
    page_size: int,
    cancelled: Callable[[], bool] | None,
) -> None:
    stream = _stream(journal, "motor_anatomy")
    cursor = _motor_cursor(stream.get("cursor"))
    while True:
        try:
            _check_cancelled(cancelled)
            raw_page = transport.fetch_motor_anatomy(cursor, page_size)
        except AcquisitionError as error:
            _record_failure(journal_path, journal, error)
            raise
        except Exception:
            failure = AcquisitionError("motor-anatomy page request failed")
            _record_failure(journal_path, journal, failure)
            raise failure from None
        try:
            if len(raw_page) > page_size:
                raise AcquisitionError("motor-anatomy provider page exceeds requested page size")
            rows, next_cursor = _motor_page(raw_page, cursor)
        except AcquisitionError as error:
            _record_failure(journal_path, journal, error)
            raise
        if not rows:
            stream["complete"] = True
            journal["state"] = "VERIFYING"
            journal["updated_at"] = _now()
            _write_journal(journal_path, journal)
            return
        offset = _append_page(root / _MOTOR_PART, MOTOR_ANATOMY_FIELDS, rows)
        stream["committed_offset"] = offset
        stream["rows"] = _nonnegative_int(stream["rows"], "motor_anatomy.rows") + len(rows)
        stream["cursor"] = next_cursor
        journal["state"] = "MOTOR_ANATOMY"
        journal["updated_at"] = _now()
        _write_journal(journal_path, journal)
        cursor = next_cursor


def _connection_page(
    page: Sequence[Mapping[str, object]], previous: tuple[int, int] | None
) -> tuple[tuple[tuple[str, ...], ...], tuple[int, int]]:
    if isinstance(page, (str, bytes)) or not isinstance(page, Sequence):
        raise AcquisitionError("connection provider page must be a bounded sequence")
    output: list[tuple[str, ...]] = []
    cursor = previous
    for index, raw in enumerate(page):
        record = _exact_mapping(raw, set(CONNECTION_FIELDS), f"connection page row {index}")
        pre_id, pre_text = _exact_integer(record["preId"], f"connection row {index} preId")
        post_id, post_text = _exact_integer(record["postId"], f"connection row {index} postId")
        _, weight_text = _exact_integer(
            record["total_weight"], f"connection row {index} total_weight", positive=True
        )
        current = (pre_id, post_id)
        if cursor is not None and current <= cursor:
            raise AcquisitionError("connection page cursors must be strictly increasing")
        cursor = current
        output.append(
            (
                pre_text,
                _cell(record["preType"]),
                _cell(record["preInstance"]),
                _cell(record["preNt"]),
                post_text,
                _cell(record["postType"]),
                _cell(record["postInstance"]),
                _cell(record["postNt"]),
                weight_text,
            )
        )
    return tuple(output), cursor if cursor is not None else (-1, -1)


def _motor_page(
    page: Sequence[Mapping[str, object]], previous: int | None
) -> tuple[tuple[tuple[str, ...], ...], int]:
    if isinstance(page, (str, bytes)) or not isinstance(page, Sequence):
        raise AcquisitionError("motor-anatomy provider page must be a bounded sequence")
    output: list[tuple[str, ...]] = []
    cursor = previous
    for index, raw in enumerate(page):
        record = _exact_mapping(raw, set(MOTOR_ANATOMY_FIELDS), f"motor page row {index}")
        body_id, body_text = _exact_integer(record["bodyid"], f"motor row {index} bodyid")
        if cursor is not None and body_id <= cursor:
            raise AcquisitionError("motor-anatomy page cursors must be strictly increasing")
        cursor = body_id
        row: list[str] = []
        for name in MOTOR_ANATOMY_FIELDS:
            row.append(body_text if name == "bodyid" else _cell(record[name]))
        output.append(tuple(row))
    return tuple(output), cursor if cursor is not None else -1


def _exact_integer(value: object, path: str, *, positive: bool = False) -> tuple[int, str]:
    if isinstance(value, float):
        raise AcquisitionError(f"{path} must not be binary float")
    if isinstance(value, bool) or not isinstance(value, (int, str, Decimal)):
        raise AcquisitionError(f"{path} must be an exact integral number")
    text = str(value).strip()
    try:
        decimal = Decimal(text)
    except InvalidOperation as error:
        raise AcquisitionError(f"{path} must be an exact integral number") from error
    if not decimal.is_finite() or decimal != decimal.to_integral_value():
        raise AcquisitionError(f"{path} must be an exact integral number")
    integer = int(decimal)
    if integer < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise AcquisitionError(f"{path} must be {qualifier}")
    return integer, text


def _cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, Decimal)) and not isinstance(value, bool):
        return str(value)
    raise AcquisitionError("provider text fields must be strings, exact numbers, or null")


def _connection_cursor(value: object) -> tuple[int, int] | None:
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != 2:
        raise AcquisitionError("connection journal cursor must be a two-item array")
    return (
        _nonnegative_int(value[0], "connection cursor preId"),
        _nonnegative_int(value[1], "connection cursor postId"),
    )


def _motor_cursor(value: object) -> int | None:
    return None if value is None else _nonnegative_int(value, "motor cursor bodyid")


def _append_page(path: Path, fields: tuple[str, ...], rows: Sequence[Sequence[str]]) -> int:
    payload = _csv_payload(fields, rows, include_header=False)
    try:
        with path.open("ab") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
            return handle.tell()
    except OSError as error:
        raise AcquisitionError(f"cannot commit acquisition page to {path.name}") from error


def _csv_payload(
    fields: tuple[str, ...],
    rows: Sequence[Sequence[str]],
    *,
    include_header: bool = True,
) -> bytes:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    if include_header:
        writer.writerow(fields)
    writer.writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _promote(
    root: Path,
    profile: NeuprintReleaseProfile,
    request_sha256: str,
    initial_snapshot: ProviderSnapshot,
    final_snapshot: ProviderSnapshot,
    journal: dict[str, Any],
) -> AcquisitionResult:
    connection_rows = _nonnegative_int(
        _stream(journal, "connectivity")["rows"], "connectivity.rows"
    )
    motor_rows = _nonnegative_int(_stream(journal, "motor_anatomy")["rows"], "motor_anatomy.rows")
    connection_file = _dataset_file(
        root / _CONNECTION_PART,
        role="connectivity",
        manifest_path=_CONNECTION_PART,
        schema_id=CONNECTION_SCHEMA,
        rows=connection_rows,
    )
    motor_file = _dataset_file(
        root / _MOTOR_PART,
        role="motor_anatomy",
        manifest_path=_MOTOR_PART,
        schema_id=MOTOR_ANATOMY_SCHEMA,
        rows=motor_rows,
    )
    candidate = _manifest(profile, (connection_file, motor_file))
    candidate.verify(root)

    final_manifest = _manifest(
        profile,
        (
            _renamed_dataset_file(connection_file, _CONNECTION_FINAL),
            _renamed_dataset_file(motor_file, _MOTOR_FINAL),
        ),
    )
    connection_part = root / _CONNECTION_PART
    motor_part = root / _MOTOR_PART
    connection_final = root / _CONNECTION_FINAL
    motor_final = root / _MOTOR_FINAL
    if connection_final.exists() or motor_final.exists():
        raise AcquisitionError("promotion refuses to overwrite existing final dataset files")
    try:
        connection_part.replace(connection_final)
        motor_part.replace(motor_final)
        final_manifest.verify(root)
        receipt = AcquisitionReceipt(
            request_sha256=request_sha256,
            profile_sha256=profile.sha256(),
            query_profile_version=profile.query_profile_version,
            modified_representation=profile.modified_representation,
            initial_snapshot=initial_snapshot,
            final_snapshot=final_snapshot,
            manifest_sha256=final_manifest.sha256(),
            connection_rows=connection_rows,
            motor_anatomy_rows=motor_rows,
            license=profile.license,
        )
        _write_json(root / _MANIFEST, final_manifest.to_dict())
        _write_json(root / _RECEIPT, receipt.to_dict())
    except Exception:
        if not (root / _RECEIPT).exists():
            if motor_final.exists() and not motor_part.exists():
                motor_final.replace(motor_part)
            if connection_final.exists() and not connection_part.exists():
                connection_final.replace(connection_part)
            if (root / _MANIFEST).exists():
                (root / _MANIFEST).unlink()
        raise
    return AcquisitionResult(final_manifest, receipt)


def _manifest(
    profile: NeuprintReleaseProfile, files: tuple[DatasetFile, DatasetFile]
) -> DatasetManifest:
    return DatasetManifest.from_dict(
        {
            "schema_version": "1.0",
            "dataset_id": profile.dataset,
            "provider": profile.provider,
            "release": profile.release,
            "source_url": profile.source_url,
            "citation": profile.citation,
            "license": profile.license,
            "redistribution": profile.redistribution,
            "access": profile.access,
            "files": [item.to_dict() for item in files],
        }
    )


def _dataset_file(
    path: Path,
    *,
    role: str,
    manifest_path: str,
    schema_id: str,
    rows: int,
) -> DatasetFile:
    digest = hashlib.sha256()
    size = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
    except OSError as error:
        raise AcquisitionError(f"cannot fingerprint acquisition file {path.name}") from error
    return DatasetFile.from_dict(
        {
            "role": role,
            "path": manifest_path,
            "sha256": digest.hexdigest(),
            "size_bytes": size,
            "media_type": "text/csv",
            "schema_id": schema_id,
            "data_rows": rows,
        },
        0,
    )


def _renamed_dataset_file(item: DatasetFile, path: str) -> DatasetFile:
    value = item.to_dict()
    value["path"] = path
    return DatasetFile.from_dict(value, 0)


def _write_journal(path: Path, value: dict[str, object]) -> None:
    """Write the durable cursor authority (a public seam for fault injection tests)."""
    _write_json(path, value)


def _write_json(path: Path, value: object) -> None:
    payload = _canonical_bytes(value) + b"\n"
    temporary = path.with_name(f"{path.name}.tmp")
    try:
        with temporary.open("wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    except OSError:
        if temporary.exists():
            temporary.unlink()
        raise


def _load_json(path: Path, description: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AcquisitionError(f"cannot read canonical {description}") from error
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise AcquisitionError(f"{description} must be an object with string keys")
    return value


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _exact_object(value: object, fields: set[str], path: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise AcquisitionError(f"{path} must be an object with string keys")
    if set(value) != fields:
        raise AcquisitionError(
            f"{path} fields differ: missing={sorted(fields - set(value))}, "
            f"unknown={sorted(set(value) - fields)}"
        )
    return value


def _exact_mapping(value: object, fields: set[str], path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise AcquisitionError(f"{path} must be an object with string keys")
    if set(value) != fields:
        raise AcquisitionError(
            f"{path} fields differ: missing={sorted(fields - set(value))}, "
            f"unknown={sorted(set(value) - fields)}"
        )
    return cast(Mapping[str, object], value)


def _required_string(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise AcquisitionError(f"{path} must be a non-empty string")
    return value


def _nonnegative_int(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise AcquisitionError(f"{path} must be a non-negative integer")
    return value


def _json_value(value: object) -> object:
    try:
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise AcquisitionError("provider metadata must be canonical JSON") from error
    return value


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _sha256_json(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
