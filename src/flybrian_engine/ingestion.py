"""Streaming normalization for versioned connectome and motor-anatomy CSV schemas."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal, cast

from .datasets import DatasetFile, DatasetVerificationError, VerifiedDataset
from .version import __version__

CONNECTION_SCHEMA = "org.janelia.neuprint.connection-summary.v1"
MOTOR_ANATOMY_SCHEMA = "org.flybrian.motor-anatomy.v1"
NORMALIZED_CONNECTION_SCHEMA = "org.flybrian.normalized-connections.ndjson.v1"

SelfEdgePolicy = Literal["retain", "reject"]
DuplicateEdgePolicy = Literal["record", "reject"]
AnnotationConflictPolicy = Literal["record", "reject"]

_NORMALIZED_CONNECTIONS = "connections.ndjson"
_NORMALIZATION_RECEIPT = "connection-normalization-receipt.json"
_NORMALIZATION_PART = "connections.ndjson.part"
_NORMALIZATION_RECEIPT_TMP = "connection-normalization-receipt.json.tmp"
_NORMALIZATION_INDEX = ".connection-normalization-index.sqlite3"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_CONNECTION_REQUIRED = {"preId", "postId", "total_weight"}
_CONNECTION_OPTIONAL = {
    "preType",
    "preInstance",
    "preNt",
    "postType",
    "postInstance",
    "postNt",
}
_MOTOR_REQUIRED = {"bodyid", "class", "subclass", "exit_nerve", "target"}
_MOTOR_OPTIONAL = {
    "systematic_type",
    "match_certainty(1-5)",
    "type",
    "group",
    "synonyms",
    "publication_match",
    "line_match",
    "match_notes",
}


@dataclass(frozen=True)
class SourceProvenance:
    dataset_id: str
    release: str
    logical_file: str
    data_row: int
    source_lexemes: dict[str, str]


@dataclass(frozen=True)
class ConnectionRecord:
    pre_neuron_id: int
    post_neuron_id: int
    weight: int
    pre_type: str | None
    pre_instance: str | None
    pre_transmitter: str | None
    post_type: str | None
    post_instance: str | None
    post_transmitter: str | None
    provenance: SourceProvenance
    source_extensions: dict[str, str]


@dataclass(frozen=True)
class MotorAnatomyRecord:
    neuron_id: int
    neuron_class: str
    subclass: str
    exit_nerves: tuple[str, ...]
    target_label: str | None
    systematic_type: str | None
    certainty: int | None
    provenance: SourceProvenance
    source_extensions: dict[str, str]


class ConnectionNormalizationError(DatasetVerificationError):
    """A connection stream cannot be promoted under its declared profile."""


def _normalization_text(value: object, path: str, *, maximum: int = 2048) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
    ):
        raise ConnectionNormalizationError(
            f"{path} must be a non-empty trimmed string of at most {maximum} characters"
        )
    return value


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True)
class ConnectionNormalizationProfile:
    profile_id: str
    profile_version: str
    source: str
    self_edge_policy: SelfEdgePolicy
    duplicate_edge_policy: DuplicateEdgePolicy
    annotation_conflict_policy: AnnotationConflictPolicy
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.schema_version != "1.0":
            raise ConnectionNormalizationError(
                "connection normalization profile schema_version must equal '1.0'"
            )
        _normalization_text(self.profile_id, "profile_id", maximum=255)
        _normalization_text(self.profile_version, "profile_version", maximum=255)
        _normalization_text(self.source, "source")
        if self.self_edge_policy not in {"retain", "reject"}:
            raise ConnectionNormalizationError("self_edge_policy is unsupported")
        if self.duplicate_edge_policy not in {"record", "reject"}:
            raise ConnectionNormalizationError("duplicate_edge_policy is unsupported")
        if self.annotation_conflict_policy not in {"record", "reject"}:
            raise ConnectionNormalizationError("annotation_conflict_policy is unsupported")

    def to_dict(self) -> dict[str, str]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "source": self.source,
            "self_edge_policy": self.self_edge_policy,
            "duplicate_edge_policy": self.duplicate_edge_policy,
            "annotation_conflict_policy": self.annotation_conflict_policy,
        }

    @classmethod
    def from_dict(cls, value: object) -> ConnectionNormalizationProfile:
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise ConnectionNormalizationError(
                "connection normalization profile must be an object"
            )
        record = cast(dict[str, Any], value)
        expected = {
            "schema_version",
            "profile_id",
            "profile_version",
            "source",
            "self_edge_policy",
            "duplicate_edge_policy",
            "annotation_conflict_policy",
        }
        missing = sorted(expected - set(record))
        unknown = sorted(set(record) - expected)
        if missing or unknown:
            raise ConnectionNormalizationError(
                f"connection normalization profile fields differ: "
                f"missing={missing}, unknown={unknown}"
            )
        return cls(
            schema_version=record["schema_version"],
            profile_id=record["profile_id"],
            profile_version=record["profile_version"],
            source=record["source"],
            self_edge_policy=record["self_edge_policy"],
            duplicate_edge_policy=record["duplicate_edge_policy"],
            annotation_conflict_policy=record["annotation_conflict_policy"],
        )

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


MANC_CONNECTION_NORMALIZATION_V1 = ConnectionNormalizationProfile(
    profile_id="org.flybrian.connection-normalization.manc.v1",
    profile_version="1.0",
    source="https://www.janelia.org/node/68782",
    self_edge_policy="retain",
    duplicate_edge_policy="record",
    annotation_conflict_policy="record",
)


@dataclass(frozen=True)
class ConnectionNormalizationReceipt:
    engine_version: str
    dataset_id: str
    release: str
    manifest_sha256: str
    profile_id: str
    profile_version: str
    profile_sha256: str
    self_edge_policy: SelfEdgePolicy
    duplicate_edge_policy: DuplicateEdgePolicy
    annotation_conflict_policy: AnnotationConflictPolicy
    input_record_count: int
    output_record_count: int
    self_edge_count: int
    duplicate_edge_count: int
    annotation_conflict_count: int
    output_size_bytes: int
    output_sha256: str
    output_schema: str = NORMALIZED_CONNECTION_SCHEMA
    output_path: str = _NORMALIZED_CONNECTIONS
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.schema_version != "1.0":
            raise ConnectionNormalizationError(
                "connection normalization receipt schema_version must equal '1.0'"
            )
        for name in (
            "engine_version",
            "dataset_id",
            "release",
            "profile_id",
            "profile_version",
        ):
            _normalization_text(getattr(self, name), f"receipt.{name}", maximum=255)
        for name in ("manifest_sha256", "profile_sha256", "output_sha256"):
            value = getattr(self, name)
            if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
                raise ConnectionNormalizationError(f"receipt.{name} must be lower-case SHA-256")
        if self.self_edge_policy not in {"retain", "reject"}:
            raise ConnectionNormalizationError("receipt.self_edge_policy is unsupported")
        if self.duplicate_edge_policy not in {"record", "reject"}:
            raise ConnectionNormalizationError("receipt.duplicate_edge_policy is unsupported")
        if self.annotation_conflict_policy not in {"record", "reject"}:
            raise ConnectionNormalizationError(
                "receipt.annotation_conflict_policy is unsupported"
            )
        for name in (
            "input_record_count",
            "output_record_count",
            "self_edge_count",
            "duplicate_edge_count",
            "annotation_conflict_count",
            "output_size_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ConnectionNormalizationError(
                    f"receipt.{name} must be a non-negative integer"
                )
        if self.input_record_count != self.output_record_count:
            raise ConnectionNormalizationError(
                "receipt input/output counts must match under profile 1.0"
            )
        if self.self_edge_count > self.output_record_count:
            raise ConnectionNormalizationError("receipt self_edge_count exceeds output count")
        if self.duplicate_edge_policy == "reject" and self.duplicate_edge_count != 0:
            raise ConnectionNormalizationError(
                "receipt reject policy cannot contain duplicate edges"
            )
        if self.annotation_conflict_policy == "reject" and self.annotation_conflict_count != 0:
            raise ConnectionNormalizationError(
                "receipt reject policy cannot contain annotation conflicts"
            )
        if self.output_schema != NORMALIZED_CONNECTION_SCHEMA:
            raise ConnectionNormalizationError("receipt.output_schema is unsupported")
        if self.output_path != _NORMALIZED_CONNECTIONS:
            raise ConnectionNormalizationError("receipt.output_path is unsupported")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "engine_version": self.engine_version,
            "dataset_id": self.dataset_id,
            "release": self.release,
            "manifest_sha256": self.manifest_sha256,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "profile_sha256": self.profile_sha256,
            "self_edge_policy": self.self_edge_policy,
            "duplicate_edge_policy": self.duplicate_edge_policy,
            "annotation_conflict_policy": self.annotation_conflict_policy,
            "input_record_count": self.input_record_count,
            "output_record_count": self.output_record_count,
            "self_edge_count": self.self_edge_count,
            "duplicate_edge_count": self.duplicate_edge_count,
            "annotation_conflict_count": self.annotation_conflict_count,
            "output_schema": self.output_schema,
            "output_path": self.output_path,
            "output_size_bytes": self.output_size_bytes,
            "output_sha256": self.output_sha256,
        }

    @classmethod
    def from_dict(cls, value: object) -> ConnectionNormalizationReceipt:
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise ConnectionNormalizationError("connection normalization receipt must be an object")
        record = cast(dict[str, Any], value)
        expected = {
            "schema_version",
            "engine_version",
            "dataset_id",
            "release",
            "manifest_sha256",
            "profile_id",
            "profile_version",
            "profile_sha256",
            "self_edge_policy",
            "duplicate_edge_policy",
            "annotation_conflict_policy",
            "input_record_count",
            "output_record_count",
            "self_edge_count",
            "duplicate_edge_count",
            "annotation_conflict_count",
            "output_schema",
            "output_path",
            "output_size_bytes",
            "output_sha256",
        }
        missing = sorted(expected - set(record))
        unknown = sorted(set(record) - expected)
        if missing or unknown:
            raise ConnectionNormalizationError(
                f"connection normalization receipt fields differ: "
                f"missing={missing}, unknown={unknown}"
            )
        return cls(
            schema_version=record["schema_version"],
            engine_version=record["engine_version"],
            dataset_id=record["dataset_id"],
            release=record["release"],
            manifest_sha256=record["manifest_sha256"],
            profile_id=record["profile_id"],
            profile_version=record["profile_version"],
            profile_sha256=record["profile_sha256"],
            self_edge_policy=record["self_edge_policy"],
            duplicate_edge_policy=record["duplicate_edge_policy"],
            annotation_conflict_policy=record["annotation_conflict_policy"],
            input_record_count=record["input_record_count"],
            output_record_count=record["output_record_count"],
            self_edge_count=record["self_edge_count"],
            duplicate_edge_count=record["duplicate_edge_count"],
            annotation_conflict_count=record["annotation_conflict_count"],
            output_schema=record["output_schema"],
            output_path=record["output_path"],
            output_size_bytes=record["output_size_bytes"],
            output_sha256=record["output_sha256"],
        )

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class ConnectionNormalizationResult:
    output_path: Path
    receipt: ConnectionNormalizationReceipt


def _header_map(
    header: tuple[str, ...],
    item: DatasetFile,
    required: set[str],
    optional: set[str],
) -> dict[str, int]:
    if len(header) != len(set(header)):
        raise DatasetVerificationError(f"{item.path} contains duplicate CSV columns")
    missing = sorted(required - set(header))
    unknown = sorted(
        name for name in header if name not in required | optional and not name.startswith("x_")
    )
    if missing or unknown:
        raise DatasetVerificationError(
            f"{item.path} columns differ: missing={missing}, unknown={unknown}"
        )
    return {name: index for index, name in enumerate(header)}


def _row_values(
    header: tuple[str, ...],
    row: tuple[str, ...],
    item: DatasetFile,
    row_number: int,
) -> dict[str, str]:
    if len(row) != len(header):
        raise DatasetVerificationError(
            f"{item.path} data row {row_number} has {len(row)} values for {len(header)} columns"
        )
    return dict(zip(header, row, strict=True))


def _nonempty(value: str, item: DatasetFile, row_number: int, field: str) -> str:
    if not value.strip():
        raise DatasetVerificationError(f"{item.path} data row {row_number} field {field} is empty")
    return value


def _nonnegative_int(
    value: str,
    item: DatasetFile,
    row_number: int,
    field: str,
    *,
    positive: bool = False,
) -> int:
    try:
        result = int(value)
    except ValueError as error:
        raise DatasetVerificationError(
            f"{item.path} data row {row_number} field {field} must be an integer"
        ) from error
    if result < (1 if positive else 0):
        qualifier = "positive" if positive else "non-negative"
        raise DatasetVerificationError(
            f"{item.path} data row {row_number} field {field} must be {qualifier}"
        )
    return result


_CANONICAL_INTEGER = re.compile(r"(?:0|[1-9][0-9]*)$")
_DECIMAL_INTEGER = re.compile(r"[0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?$")


def _exact_integral(
    value: str,
    item: DatasetFile,
    row_number: int,
    field: str,
    *,
    positive: bool = False,
    maximum_digits: int = 32,
) -> tuple[int, str | None]:
    if _CANONICAL_INTEGER.fullmatch(value) is not None:
        result = int(value)
        if positive and result == 0:
            raise DatasetVerificationError(
                f"{item.path} data row {row_number} field {field} must be positive"
            )
        return result, None
    if _DECIMAL_INTEGER.fullmatch(value) is None:
        raise DatasetVerificationError(
            f"{item.path} data row {row_number} field {field} must use decimal notation"
        )
    try:
        decimal = Decimal(value)
    except InvalidOperation as error:
        raise DatasetVerificationError(
            f"{item.path} data row {row_number} field {field} has invalid decimal notation"
        ) from error
    minimum = 1 if positive else 0
    if not decimal.is_finite() or decimal < minimum or decimal != decimal.to_integral_value():
        raise DatasetVerificationError(
            f"{item.path} data row {row_number} field {field} must resolve to an exact "
            f"{'positive' if positive else 'non-negative'} integer"
        )
    resolved = int(decimal)
    if len(str(resolved)) > maximum_digits:
        raise DatasetVerificationError(
            f"{item.path} data row {row_number} field {field} exceeds the "
            f"{maximum_digits}-digit bound"
        )
    return resolved, value


def _neuron_id(
    value: str,
    item: DatasetFile,
    row_number: int,
    field: str,
) -> tuple[int, str | None]:
    return _exact_integral(value, item, row_number, field)


def _optional(values: dict[str, str], key: str) -> str | None:
    value = values.get(key, "")
    return value if value else None


def _extensions(values: dict[str, str]) -> dict[str, str]:
    return {key: value for key, value in values.items() if key.startswith("x_")}


def _provenance(
    dataset: VerifiedDataset,
    item: DatasetFile,
    row_number: int,
    source_lexemes: dict[str, str] | None = None,
) -> SourceProvenance:
    return SourceProvenance(
        dataset_id=dataset.manifest.dataset_id,
        release=dataset.manifest.release,
        logical_file=item.path,
        data_row=row_number,
        source_lexemes=source_lexemes or {},
    )


def iter_connections(dataset: VerifiedDataset) -> Iterator[ConnectionRecord]:
    for item in dataset.files_for_schema(CONNECTION_SCHEMA):
        if item.role != "connectivity":
            raise DatasetVerificationError(
                f"{item.path} schema {CONNECTION_SCHEMA} requires role connectivity"
            )
        if item.data_rows == 0:
            _header_map(
                dataset.csv_header(item),
                item,
                _CONNECTION_REQUIRED,
                _CONNECTION_OPTIONAL,
            )
        header_map: dict[str, int] | None = None
        for header, row_number, row in dataset.csv_rows(item):
            if header_map is None:
                header_map = _header_map(header, item, _CONNECTION_REQUIRED, _CONNECTION_OPTIONAL)
            values = _row_values(header, row, item, row_number)
            pre_id, pre_lexeme = _neuron_id(values["preId"], item, row_number, "preId")
            post_id, post_lexeme = _neuron_id(values["postId"], item, row_number, "postId")
            weight, weight_lexeme = _exact_integral(
                values["total_weight"],
                item,
                row_number,
                "total_weight",
                positive=True,
            )
            source_lexemes = {
                field: lexeme
                for field, lexeme in (
                    ("preId", pre_lexeme),
                    ("postId", post_lexeme),
                    ("total_weight", weight_lexeme),
                )
                if lexeme is not None
            }
            yield ConnectionRecord(
                pre_neuron_id=pre_id,
                post_neuron_id=post_id,
                weight=weight,
                pre_type=_optional(values, "preType"),
                pre_instance=_optional(values, "preInstance"),
                pre_transmitter=_optional(values, "preNt"),
                post_type=_optional(values, "postType"),
                post_instance=_optional(values, "postInstance"),
                post_transmitter=_optional(values, "postNt"),
                provenance=_provenance(dataset, item, row_number, source_lexemes),
                source_extensions=_extensions(values),
            )


def iter_motor_anatomy(dataset: VerifiedDataset) -> Iterator[MotorAnatomyRecord]:
    for item in dataset.files_for_schema(MOTOR_ANATOMY_SCHEMA):
        if item.role != "motor_anatomy":
            raise DatasetVerificationError(
                f"{item.path} schema {MOTOR_ANATOMY_SCHEMA} requires role motor_anatomy"
            )
        if item.data_rows == 0:
            _header_map(
                dataset.csv_header(item),
                item,
                _MOTOR_REQUIRED,
                _MOTOR_OPTIONAL,
            )
        header_map: dict[str, int] | None = None
        for header, row_number, row in dataset.csv_rows(item):
            if header_map is None:
                header_map = _header_map(header, item, _MOTOR_REQUIRED, _MOTOR_OPTIONAL)
            values = _row_values(header, row, item, row_number)
            exit_nerves = tuple(
                part
                for part in _nonempty(values["exit_nerve"], item, row_number, "exit_nerve").split()
                if part
            )
            certainty_value = values.get("match_certainty(1-5)", "")
            certainty = None
            if certainty_value:
                certainty = _nonnegative_int(
                    certainty_value,
                    item,
                    row_number,
                    "match_certainty(1-5)",
                    positive=True,
                )
                if certainty > 5:
                    raise DatasetVerificationError(
                        f"{item.path} data row {row_number} certainty must be between 1 and 5"
                    )
            neuron_id, neuron_lexeme = _neuron_id(values["bodyid"], item, row_number, "bodyid")
            yield MotorAnatomyRecord(
                neuron_id=neuron_id,
                neuron_class=_nonempty(values["class"], item, row_number, "class"),
                subclass=_nonempty(values["subclass"], item, row_number, "subclass"),
                exit_nerves=exit_nerves,
                target_label=_optional(values, "target"),
                systematic_type=_optional(values, "systematic_type"),
                certainty=certainty,
                provenance=_provenance(
                    dataset,
                    item,
                    row_number,
                    {"bodyid": neuron_lexeme} if neuron_lexeme is not None else {},
                ),
                source_extensions=_extensions(values),
            )


def _provenance_to_dict(value: SourceProvenance) -> dict[str, object]:
    return {
        "dataset_id": value.dataset_id,
        "release": value.release,
        "logical_file": value.logical_file,
        "data_row": value.data_row,
        "source_lexemes": dict(value.source_lexemes),
    }


def _connection_to_dict(value: ConnectionRecord) -> dict[str, object]:
    return {
        "pre_neuron_id": value.pre_neuron_id,
        "post_neuron_id": value.post_neuron_id,
        "weight": value.weight,
        "pre_type": value.pre_type,
        "pre_instance": value.pre_instance,
        "pre_transmitter": value.pre_transmitter,
        "post_type": value.post_type,
        "post_instance": value.post_instance,
        "post_transmitter": value.post_transmitter,
        "provenance": _provenance_to_dict(value.provenance),
        "source_extensions": dict(value.source_extensions),
    }


def _source_location(file_name: str, data_row: int) -> str:
    return f"{file_name} data row {data_row}"


def _record_annotations(
    record: ConnectionRecord,
) -> tuple[tuple[int, str, str | None], ...]:
    return (
        (record.pre_neuron_id, "type", record.pre_type),
        (record.pre_neuron_id, "instance", record.pre_instance),
        (record.pre_neuron_id, "transmitter", record.pre_transmitter),
        (record.post_neuron_id, "type", record.post_type),
        (record.post_neuron_id, "instance", record.post_instance),
        (record.post_neuron_id, "transmitter", record.post_transmitter),
    )


def _create_normalization_index(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode = MEMORY")
    connection.execute("PRAGMA synchronous = OFF")
    connection.execute(
        """
        CREATE TABLE edges (
            pre_id TEXT NOT NULL,
            post_id TEXT NOT NULL,
            logical_file TEXT NOT NULL,
            data_row INTEGER NOT NULL,
            PRIMARY KEY (pre_id, post_id)
        ) WITHOUT ROWID
        """
    )
    connection.execute(
        """
        CREATE TABLE annotations (
            neuron_id TEXT NOT NULL,
            field TEXT NOT NULL,
            value TEXT NOT NULL,
            logical_file TEXT NOT NULL,
            data_row INTEGER NOT NULL,
            PRIMARY KEY (neuron_id, field)
        ) WITHOUT ROWID
        """
    )
    connection.execute(
        """
        CREATE TABLE edge_duplicates (
            pre_id TEXT NOT NULL,
            post_id TEXT NOT NULL,
            PRIMARY KEY (pre_id, post_id)
        ) WITHOUT ROWID
        """
    )
    connection.execute(
        """
        CREATE TABLE annotation_conflicts (
            neuron_id TEXT NOT NULL,
            field TEXT NOT NULL,
            PRIMARY KEY (neuron_id, field)
        ) WITHOUT ROWID
        """
    )
    return connection


def _admit_connection_identity(
    connection: sqlite3.Connection,
    record: ConnectionRecord,
    policy: DuplicateEdgePolicy,
) -> int:
    pre_id = str(record.pre_neuron_id)
    post_id = str(record.post_neuron_id)
    location = record.provenance
    try:
        connection.execute(
            "INSERT INTO edges VALUES (?, ?, ?, ?)",
            (pre_id, post_id, location.logical_file, location.data_row),
        )
        return 0
    except sqlite3.IntegrityError as error:
        first = connection.execute(
            "SELECT logical_file, data_row FROM edges WHERE pre_id = ? AND post_id = ?",
            (pre_id, post_id),
        ).fetchone()
        if first is None:
            raise ConnectionNormalizationError(
                f"cannot resolve duplicate connection pair ({pre_id}, {post_id})"
            ) from error
        if policy == "reject":
            raise ConnectionNormalizationError(
                f"duplicate connection pair ({pre_id}, {post_id}) first appears at "
                f"{_source_location(str(first[0]), int(first[1]))} and repeats at "
                f"{_source_location(location.logical_file, location.data_row)}"
            ) from error
        cursor = connection.execute(
            "INSERT OR IGNORE INTO edge_duplicates VALUES (?, ?)",
            (pre_id, post_id),
        )
        return cursor.rowcount


def _admit_annotations(
    connection: sqlite3.Connection,
    record: ConnectionRecord,
    policy: AnnotationConflictPolicy,
) -> int:
    location = record.provenance
    new_conflicts = 0
    for neuron_id, field, value in _record_annotations(record):
        if value is None:
            continue
        key = (str(neuron_id), field)
        first = connection.execute(
            """
            SELECT value, logical_file, data_row
            FROM annotations
            WHERE neuron_id = ? AND field = ?
            """,
            key,
        ).fetchone()
        if first is None:
            connection.execute(
                "INSERT INTO annotations VALUES (?, ?, ?, ?, ?)",
                (*key, value, location.logical_file, location.data_row),
            )
            continue
        if str(first[0]) != value:
            if policy == "reject":
                raise ConnectionNormalizationError(
                    f"neuron {neuron_id} {field} annotation conflicts between "
                    f"{_source_location(str(first[1]), int(first[2]))} and "
                    f"{_source_location(location.logical_file, location.data_row)}"
                )
            cursor = connection.execute(
                "INSERT OR IGNORE INTO annotation_conflicts VALUES (?, ?)",
                key,
            )
            new_conflicts += cursor.rowcount
    return new_conflicts


def _hash_and_count_lines(path: Path) -> tuple[int, str, int]:
    digest = hashlib.sha256()
    size = 0
    lines = 0
    try:
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
                lines += chunk.count(b"\n")
    except OSError as error:
        raise ConnectionNormalizationError(
            f"cannot verify normalized connection output {path.name}"
        ) from error
    return size, digest.hexdigest(), lines


def _unlink_owned(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as error:
        raise ConnectionNormalizationError(
            f"cannot remove incomplete normalization artifact {path.name}"
        ) from error


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _promote_connection_part(source: Path, destination: Path) -> None:
    source.replace(destination)


def _write_normalization_receipt(
    receipt: ConnectionNormalizationReceipt,
    temporary: Path,
    destination: Path,
) -> None:
    payload = receipt.canonical_bytes() + b"\n"
    try:
        with temporary.open("xb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(destination)
        _fsync_directory(destination.parent)
    except OSError as error:
        raise ConnectionNormalizationError(
            "cannot promote connection normalization receipt"
        ) from error


def _load_receipt(path: Path) -> ConnectionNormalizationReceipt:
    if path.is_symlink() or not path.is_file():
        raise ConnectionNormalizationError(
            "existing connection normalization receipt must be a regular file"
        )
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ConnectionNormalizationError(
            "cannot read existing connection normalization receipt"
        ) from error
    receipt = ConnectionNormalizationReceipt.from_dict(value)
    if payload != receipt.canonical_bytes() + b"\n":
        raise ConnectionNormalizationError(
            "existing connection normalization receipt is not canonical"
        )
    return receipt


def _existing_normalization(
    dataset: VerifiedDataset,
    profile: ConnectionNormalizationProfile,
    output_path: Path,
    receipt_path: Path,
) -> ConnectionNormalizationResult | None:
    if not receipt_path.exists():
        return None
    if not output_path.exists():
        raise ConnectionNormalizationError(
            "existing normalization receipt has no normalized connection output"
        )
    if output_path.is_symlink() or not output_path.is_file():
        raise ConnectionNormalizationError(
            "existing normalized connection output must be a regular file"
        )
    receipt = _load_receipt(receipt_path)
    manifest = dataset.manifest
    if (
        receipt.dataset_id != manifest.dataset_id
        or receipt.release != manifest.release
        or receipt.manifest_sha256 != manifest.sha256()
        or receipt.profile_id != profile.profile_id
        or receipt.profile_version != profile.profile_version
        or receipt.profile_sha256 != profile.sha256()
        or receipt.self_edge_policy != profile.self_edge_policy
        or receipt.duplicate_edge_policy != profile.duplicate_edge_policy
        or receipt.annotation_conflict_policy != profile.annotation_conflict_policy
    ):
        raise ConnectionNormalizationError(
            "requested normalization conflicts with existing normalized result"
        )
    size, digest, lines = _hash_and_count_lines(output_path)
    if (
        size != receipt.output_size_bytes
        or digest != receipt.output_sha256
        or lines != receipt.output_record_count
    ):
        raise ConnectionNormalizationError(
            "existing normalized connection output differs from its receipt"
        )
    return ConnectionNormalizationResult(output_path=output_path, receipt=receipt)


def normalize_connection_dataset(
    dataset: VerifiedDataset,
    profile: ConnectionNormalizationProfile,
    destination: Path,
) -> ConnectionNormalizationResult:
    """Promote canonical connection NDJSON and its receipt with bounded retained memory."""
    if not isinstance(profile, ConnectionNormalizationProfile):
        raise ConnectionNormalizationError(
            "profile must be a ConnectionNormalizationProfile"
        )
    if destination.is_symlink():
        raise ConnectionNormalizationError("normalization destination must not be a symbolic link")
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ConnectionNormalizationError("cannot create normalization destination") from error
    if not destination.is_dir():
        raise ConnectionNormalizationError("normalization destination must be a directory")

    output_path = destination / _NORMALIZED_CONNECTIONS
    receipt_path = destination / _NORMALIZATION_RECEIPT
    part_path = destination / _NORMALIZATION_PART
    receipt_tmp = destination / _NORMALIZATION_RECEIPT_TMP
    index_path = destination / _NORMALIZATION_INDEX

    existing = _existing_normalization(
        dataset, profile, output_path, receipt_path
    )
    if existing is not None:
        for temporary in (part_path, receipt_tmp, index_path):
            _unlink_owned(temporary)
        return existing

    if output_path.exists() or output_path.is_symlink():
        if not index_path.exists() or index_path.is_symlink():
            raise ConnectionNormalizationError(
                "unreceipted normalized connection output has no owned recovery marker; "
                "refusing overwrite"
            )
        _unlink_owned(output_path)
    for temporary in (part_path, receipt_tmp, index_path):
        _unlink_owned(temporary)

    connection: sqlite3.Connection | None = None
    promoted_output = False
    completed = False
    try:
        connection = _create_normalization_index(index_path)
        digest = hashlib.sha256()
        output_size = 0
        input_count = 0
        self_edge_count = 0
        duplicate_edge_count = 0
        annotation_conflict_count = 0
        try:
            with part_path.open("xb") as handle:
                for record in iter_connections(dataset):
                    input_count += 1
                    if record.pre_neuron_id == record.post_neuron_id:
                        if profile.self_edge_policy == "reject":
                            source = _source_location(
                                record.provenance.logical_file,
                                record.provenance.data_row,
                            )
                            raise ConnectionNormalizationError(
                                f"self-edge ({record.pre_neuron_id}, {record.post_neuron_id}) "
                                f"is rejected at {source}"
                            )
                        self_edge_count += 1
                    duplicate_edge_count += _admit_connection_identity(
                        connection,
                        record,
                        profile.duplicate_edge_policy,
                    )
                    annotation_conflict_count += _admit_annotations(
                        connection,
                        record,
                        profile.annotation_conflict_policy,
                    )
                    line = _canonical_bytes(_connection_to_dict(record)) + b"\n"
                    handle.write(line)
                    digest.update(line)
                    output_size += len(line)
                    if input_count % 10_000 == 0:
                        connection.commit()
                connection.commit()
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as error:
            raise ConnectionNormalizationError(
                "cannot write normalized connection output"
            ) from error

        verified_size, verified_digest, verified_lines = _hash_and_count_lines(part_path)
        if (
            verified_size != output_size
            or verified_digest != digest.hexdigest()
            or verified_lines != input_count
        ):
            raise ConnectionNormalizationError(
                "normalized connection part differs during pre-promotion verification"
            )
        receipt = ConnectionNormalizationReceipt(
            engine_version=__version__,
            dataset_id=dataset.manifest.dataset_id,
            release=dataset.manifest.release,
            manifest_sha256=dataset.manifest.sha256(),
            profile_id=profile.profile_id,
            profile_version=profile.profile_version,
            profile_sha256=profile.sha256(),
            self_edge_policy=profile.self_edge_policy,
            duplicate_edge_policy=profile.duplicate_edge_policy,
            annotation_conflict_policy=profile.annotation_conflict_policy,
            input_record_count=input_count,
            output_record_count=input_count,
            self_edge_count=self_edge_count,
            duplicate_edge_count=duplicate_edge_count,
            annotation_conflict_count=annotation_conflict_count,
            output_size_bytes=output_size,
            output_sha256=digest.hexdigest(),
        )
        try:
            _promote_connection_part(part_path, output_path)
        except OSError as error:
            raise ConnectionNormalizationError(
                "cannot promote normalized connections"
            ) from error
        promoted_output = True
        _fsync_directory(destination)
        _write_normalization_receipt(receipt, receipt_tmp, receipt_path)
        completed = True
        return ConnectionNormalizationResult(output_path=output_path, receipt=receipt)
    except sqlite3.Error as error:
        raise ConnectionNormalizationError("connection normalization index failed") from error
    finally:
        if connection is not None:
            connection.close()
        for temporary in (part_path, receipt_tmp, index_path):
            _unlink_owned(temporary)
        if promoted_output and not completed:
            _unlink_owned(output_path)
            _unlink_owned(receipt_path)
