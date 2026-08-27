"""Streaming normalization for versioned connectome and motor-anatomy CSV schemas."""

from __future__ import annotations

import re
from collections.abc import Iterator
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from .datasets import DatasetFile, DatasetVerificationError, VerifiedDataset

CONNECTION_SCHEMA = "org.janelia.neuprint.connection-summary.v1"
MOTOR_ANATOMY_SCHEMA = "org.flybrian.motor-anatomy.v1"

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
