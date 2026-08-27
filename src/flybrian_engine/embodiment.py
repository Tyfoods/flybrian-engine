"""Explicit, versioned motor-anatomy to embodiment transformations."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Hashable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Literal, TypeAlias, TypeVar

from .ingestion import MotorAnatomyRecord, SourceProvenance
from .version import __version__

ExactDecimal: TypeAlias = Decimal | int | str
ExactRational: TypeAlias = Fraction | Decimal | int | str
Direction = Literal["positive", "negative"]
DispositionStatus = Literal["unmapped", "ambiguous", "conflicting"]
WeightPolicy = Literal["none", "per_actuator_equal_share"]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_T = TypeVar("_T")


class EmbodimentError(ValueError):
    """An embodiment catalog, profile, or transformation is invalid."""


def _text(value: object, path: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EmbodimentError(f"{path} must be a non-empty trimmed string")
    if len(value) > maximum:
        raise EmbodimentError(f"{path} must contain at most {maximum} characters")
    return value


def _exact_decimal(value: ExactDecimal, path: str) -> Decimal:
    if isinstance(value, (bool, float)):
        raise EmbodimentError(f"{path} must not be binary float")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise EmbodimentError(f"{path} must be an exact decimal") from error
    if not result.is_finite():
        raise EmbodimentError(f"{path} must be finite")
    return result


def _positive_rational(value: ExactRational, path: str) -> Fraction:
    if isinstance(value, (bool, float)):
        raise EmbodimentError(f"{path} must not be binary float")
    try:
        if isinstance(value, Fraction):
            result = value
        elif isinstance(value, (Decimal, int)):
            result = Fraction(value)
        else:
            result = Fraction(value)
    except (ValueError, ZeroDivisionError) as error:
        raise EmbodimentError(f"{path} must be an exact rational") from error
    if result <= 0:
        raise EmbodimentError(f"{path} must be positive")
    return result


def _confidence(value: ExactDecimal, path: str) -> Decimal:
    result = _exact_decimal(value, path)
    if result < 0 or result > 1:
        raise EmbodimentError(f"{path} must be between 0 and 1")
    return result


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return str(normalized).replace("E+", "E")


def _fraction_text(value: Fraction) -> str:
    if value.denominator == 1:
        return str(value.numerator)
    return f"{value.numerator}/{value.denominator}"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _unique_text(values: tuple[str, ...], path: str) -> None:
    if not values:
        raise EmbodimentError(f"{path} must not be empty")
    checked = tuple(_text(value, f"{path} item") for value in values)
    if len(checked) != len(set(checked)):
        raise EmbodimentError(f"{path} must be unique")
    if len(checked) != len({value.casefold() for value in checked}):
        raise EmbodimentError(f"{path} must not be case-colliding")


def _unique_key(
    values: tuple[_T, ...], key: Callable[[_T], Hashable], path: str
) -> None:
    keys = [key(item) for item in values]
    if len(keys) != len(set(keys)):
        raise EmbodimentError(f"{path} must be unique")


def _provenance_dict(value: SourceProvenance) -> dict[str, object]:
    return {
        "dataset_id": value.dataset_id,
        "release": value.release,
        "logical_file": value.logical_file,
        "data_row": value.data_row,
        "source_lexemes": dict(value.source_lexemes),
    }


@dataclass(frozen=True)
class Actuator:
    actuator_id: str
    body_region: str
    joint: str
    control_min: ExactDecimal
    control_max: ExactDecimal
    control_unit: str
    source: str

    def __post_init__(self) -> None:
        _text(self.actuator_id, "actuator.actuator_id", maximum=255)
        _text(self.body_region, "actuator.body_region", maximum=255)
        _text(self.joint, "actuator.joint", maximum=255)
        minimum = _exact_decimal(self.control_min, "actuator.control_min")
        maximum = _exact_decimal(self.control_max, "actuator.control_max")
        if minimum >= maximum:
            raise EmbodimentError("actuator control range must be increasing")
        _text(self.control_unit, "actuator.control_unit", maximum=64)
        _text(self.source, "actuator.source")
        object.__setattr__(self, "control_min", minimum)
        object.__setattr__(self, "control_max", maximum)

    def to_dict(self) -> dict[str, object]:
        return {
            "actuator_id": self.actuator_id,
            "body_region": self.body_region,
            "joint": self.joint,
            "control_min": _decimal_text(_exact_decimal(self.control_min, "control_min")),
            "control_max": _decimal_text(_exact_decimal(self.control_max, "control_max")),
            "control_unit": self.control_unit,
            "source": self.source,
        }


@dataclass(frozen=True)
class ActuatorCatalog:
    catalog_id: str
    version: str
    source: str
    actuators: tuple[Actuator, ...]

    def __post_init__(self) -> None:
        _text(self.catalog_id, "actuator_catalog.catalog_id", maximum=255)
        _text(self.version, "actuator_catalog.version", maximum=255)
        _text(self.source, "actuator_catalog.source")
        if not self.actuators:
            raise EmbodimentError("actuator_catalog.actuators must not be empty")
        ids = tuple(item.actuator_id for item in self.actuators)
        _unique_text(ids, "actuator_catalog actuator IDs")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "catalog_id": self.catalog_id,
            "version": self.version,
            "source": self.source,
            "actuators": [item.to_dict() for item in self.actuators],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class MuscleParameter:
    name: str
    value: ExactDecimal
    unit: str

    def __post_init__(self) -> None:
        _text(self.name, "muscle_parameter.name", maximum=255)
        numeric = _exact_decimal(self.value, f"muscle_parameter.{self.name}.value")
        _text(self.unit, f"muscle_parameter.{self.name}.unit", maximum=64)
        object.__setattr__(self, "value", numeric)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "value": _decimal_text(_exact_decimal(self.value, f"parameter.{self.name}")),
            "unit": self.unit,
        }


@dataclass(frozen=True)
class Muscle:
    muscle_id: str
    body_region: str
    model_id: str
    model_version: str
    source: str
    parameters: tuple[MuscleParameter, ...]

    def __post_init__(self) -> None:
        _text(self.muscle_id, "muscle.muscle_id", maximum=255)
        _text(self.body_region, "muscle.body_region", maximum=255)
        _text(self.model_id, "muscle.model_id", maximum=255)
        _text(self.model_version, "muscle.model_version", maximum=255)
        _text(self.source, "muscle.source")
        if not self.parameters:
            raise EmbodimentError(f"muscle {self.muscle_id!r} parameters must not be empty")
        _unique_text(
            tuple(item.name for item in self.parameters),
            f"muscle {self.muscle_id} parameter names",
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "muscle_id": self.muscle_id,
            "body_region": self.body_region,
            "model_id": self.model_id,
            "model_version": self.model_version,
            "source": self.source,
            "parameters": [item.to_dict() for item in self.parameters],
        }


@dataclass(frozen=True)
class MuscleCatalog:
    catalog_id: str
    version: str
    source: str
    muscles: tuple[Muscle, ...]

    def __post_init__(self) -> None:
        _text(self.catalog_id, "muscle_catalog.catalog_id", maximum=255)
        _text(self.version, "muscle_catalog.version", maximum=255)
        _text(self.source, "muscle_catalog.source")
        if not self.muscles:
            raise EmbodimentError("muscle_catalog.muscles must not be empty")
        ids = tuple(item.muscle_id for item in self.muscles)
        _unique_text(ids, "muscle_catalog muscle IDs")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "catalog_id": self.catalog_id,
            "version": self.version,
            "source": self.source,
            "muscles": [item.to_dict() for item in self.muscles],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class BodyRegionRule:
    exit_nerve: str
    body_region: str

    def __post_init__(self) -> None:
        _text(self.exit_nerve, "body_region_rule.exit_nerve", maximum=255)
        _text(self.body_region, "body_region_rule.body_region", maximum=255)


@dataclass(frozen=True)
class ConfidenceRule:
    certainty: int
    confidence: ExactDecimal

    def __post_init__(self) -> None:
        if isinstance(self.certainty, bool) or not isinstance(self.certainty, int):
            raise EmbodimentError("confidence_rule.certainty must be an integer")
        if self.certainty < 1 or self.certainty > 5:
            raise EmbodimentError("confidence_rule.certainty must be between 1 and 5")
        value = _confidence(self.confidence, "confidence_rule.confidence")
        object.__setattr__(self, "confidence", value)


@dataclass(frozen=True)
class DirectTargetRule:
    target_label: str
    joint: str
    direction: Direction

    def __post_init__(self) -> None:
        _text(self.target_label, "direct_target_rule.target_label", maximum=255)
        _text(self.joint, "direct_target_rule.joint", maximum=255)
        if self.direction not in {"positive", "negative"}:
            raise EmbodimentError("direct_target_rule.direction is unsupported")


@dataclass(frozen=True)
class DirectProfile:
    profile_id: str
    version: str
    source: str
    compatible_dataset_ids: tuple[str, ...]
    body_region_rules: tuple[BodyRegionRule, ...]
    target_rules: tuple[DirectTargetRule, ...]
    confidence_rules: tuple[ConfidenceRule, ...]
    missing_certainty_confidence: ExactDecimal | None
    generic_targets: tuple[str, ...]
    allow_multiple_body_regions: bool
    allow_joint_fanout: bool
    weight_policy: WeightPolicy

    def __post_init__(self) -> None:
        _profile_identity(self.profile_id, self.version, self.source, self.compatible_dataset_ids)
        if not self.body_region_rules:
            raise EmbodimentError("direct_profile body-region rules must not be empty")
        if not self.target_rules:
            raise EmbodimentError("direct_profile target rules must not be empty")
        if not self.confidence_rules and self.missing_certainty_confidence is None:
            raise EmbodimentError("direct_profile confidence authority must not be empty")
        _unique_key(
            self.body_region_rules,
            lambda item: item.exit_nerve,
            "direct_profile exit-nerve rules",
        )
        _unique_key(
            self.target_rules,
            lambda item: item.target_label,
            "direct_profile target rules",
        )
        _unique_key(
            self.confidence_rules,
            lambda item: item.certainty,
            "direct_profile confidence rules",
        )
        _validate_generic_targets(
            self.generic_targets,
            {item.target_label for item in self.target_rules},
        )
        if self.missing_certainty_confidence is not None:
            object.__setattr__(
                self,
                "missing_certainty_confidence",
                _confidence(
                    self.missing_certainty_confidence,
                    "direct_profile.missing_certainty_confidence",
                ),
            )
        if not isinstance(self.allow_multiple_body_regions, bool):
            raise EmbodimentError("allow_multiple_body_regions must be a boolean")
        if not isinstance(self.allow_joint_fanout, bool):
            raise EmbodimentError("allow_joint_fanout must be a boolean")
        if self.weight_policy not in {"none", "per_actuator_equal_share"}:
            raise EmbodimentError("direct_profile.weight_policy is unsupported")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "mode": "direct_actuator",
            "profile_id": self.profile_id,
            "version": self.version,
            "source": self.source,
            "compatible_dataset_ids": list(self.compatible_dataset_ids),
            "body_region_rules": [
                {"exit_nerve": item.exit_nerve, "body_region": item.body_region}
                for item in self.body_region_rules
            ],
            "target_rules": [
                {
                    "target_label": item.target_label,
                    "joint": item.joint,
                    "direction": item.direction,
                }
                for item in self.target_rules
            ],
            "confidence_rules": [
                {
                    "certainty": item.certainty,
                    "confidence": _decimal_text(
                        _confidence(item.confidence, "confidence")
                    ),
                }
                for item in self.confidence_rules
            ],
            "missing_certainty_confidence": (
                None
                if self.missing_certainty_confidence is None
                else _decimal_text(
                    _confidence(
                        self.missing_certainty_confidence,
                        "missing certainty confidence",
                    )
                )
            ),
            "generic_targets": list(self.generic_targets),
            "allow_multiple_body_regions": self.allow_multiple_body_regions,
            "allow_joint_fanout": self.allow_joint_fanout,
            "weight_policy": self.weight_policy,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class MuscleTarget:
    muscle_id: str
    weight: ExactRational

    def __post_init__(self) -> None:
        _text(self.muscle_id, "muscle_target.muscle_id", maximum=255)
        object.__setattr__(self, "weight", _positive_rational(self.weight, "muscle_target.weight"))


@dataclass(frozen=True)
class MuscleTargetRule:
    body_region: str
    target_label: str
    muscles: tuple[MuscleTarget, ...]

    def __post_init__(self) -> None:
        _text(self.body_region, "muscle_target_rule.body_region", maximum=255)
        _text(self.target_label, "muscle_target_rule.target_label", maximum=255)
        if not self.muscles:
            raise EmbodimentError("muscle_target_rule.muscles must not be empty")
        _unique_key(
            self.muscles,
            lambda item: item.muscle_id,
            "muscle_target_rule muscle IDs",
        )


@dataclass(frozen=True)
class MuscleActuatorRule:
    muscle_id: str
    actuator_id: str
    weight: ExactRational
    direction: Direction

    def __post_init__(self) -> None:
        _text(self.muscle_id, "muscle_actuator_rule.muscle_id", maximum=255)
        _text(self.actuator_id, "muscle_actuator_rule.actuator_id", maximum=255)
        object.__setattr__(
            self,
            "weight",
            _positive_rational(self.weight, "muscle_actuator_rule.weight"),
        )
        if self.direction not in {"positive", "negative"}:
            raise EmbodimentError("muscle_actuator_rule.direction is unsupported")


@dataclass(frozen=True)
class MuscleProfile:
    profile_id: str
    version: str
    source: str
    compatible_dataset_ids: tuple[str, ...]
    body_region_rules: tuple[BodyRegionRule, ...]
    target_rules: tuple[MuscleTargetRule, ...]
    actuator_rules: tuple[MuscleActuatorRule, ...]
    confidence_rules: tuple[ConfidenceRule, ...]
    missing_certainty_confidence: ExactDecimal | None
    generic_targets: tuple[str, ...]
    allow_multiple_body_regions: bool

    def __post_init__(self) -> None:
        _profile_identity(self.profile_id, self.version, self.source, self.compatible_dataset_ids)
        if not self.body_region_rules:
            raise EmbodimentError("muscle_profile body-region rules must not be empty")
        if not self.target_rules:
            raise EmbodimentError("muscle_profile target rules must not be empty")
        if not self.actuator_rules:
            raise EmbodimentError("muscle_profile actuator rules must not be empty")
        if not self.confidence_rules and self.missing_certainty_confidence is None:
            raise EmbodimentError("muscle_profile confidence authority must not be empty")
        _unique_key(
            self.body_region_rules,
            lambda item: item.exit_nerve,
            "muscle_profile exit-nerve rules",
        )
        _unique_key(
            self.target_rules,
            lambda item: (item.body_region, item.target_label),
            "muscle_profile target rules",
        )
        _unique_key(
            self.actuator_rules,
            lambda item: (item.muscle_id, item.actuator_id),
            "muscle_profile actuator rules",
        )
        _unique_key(
            self.confidence_rules,
            lambda item: item.certainty,
            "muscle_profile confidence rules",
        )
        _validate_generic_targets(
            self.generic_targets,
            {item.target_label for item in self.target_rules},
        )
        if self.missing_certainty_confidence is not None:
            object.__setattr__(
                self,
                "missing_certainty_confidence",
                _confidence(
                    self.missing_certainty_confidence,
                    "muscle_profile.missing_certainty_confidence",
                ),
            )
        if not isinstance(self.allow_multiple_body_regions, bool):
            raise EmbodimentError("allow_multiple_body_regions must be a boolean")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "mode": "muscle_mediated",
            "profile_id": self.profile_id,
            "version": self.version,
            "source": self.source,
            "compatible_dataset_ids": list(self.compatible_dataset_ids),
            "body_region_rules": [
                {"exit_nerve": item.exit_nerve, "body_region": item.body_region}
                for item in self.body_region_rules
            ],
            "target_rules": [
                {
                    "body_region": item.body_region,
                    "target_label": item.target_label,
                    "muscles": [
                        {
                            "muscle_id": target.muscle_id,
                            "weight": _fraction_text(
                                _positive_rational(target.weight, "muscle target weight")
                            ),
                        }
                        for target in item.muscles
                    ],
                }
                for item in self.target_rules
            ],
            "actuator_rules": [
                {
                    "muscle_id": item.muscle_id,
                    "actuator_id": item.actuator_id,
                    "weight": _fraction_text(
                        _positive_rational(item.weight, "muscle actuator weight")
                    ),
                    "direction": item.direction,
                }
                for item in self.actuator_rules
            ],
            "confidence_rules": [
                {
                    "certainty": item.certainty,
                    "confidence": _decimal_text(
                        _confidence(item.confidence, "confidence")
                    ),
                }
                for item in self.confidence_rules
            ],
            "missing_certainty_confidence": (
                None
                if self.missing_certainty_confidence is None
                else _decimal_text(
                    _confidence(
                        self.missing_certainty_confidence,
                        "missing certainty confidence",
                    )
                )
            ),
            "generic_targets": list(self.generic_targets),
            "allow_multiple_body_regions": self.allow_multiple_body_regions,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def _profile_identity(
    profile_id: str,
    version: str,
    source: str,
    compatible_dataset_ids: tuple[str, ...],
) -> None:
    _text(profile_id, "profile.profile_id", maximum=255)
    _text(version, "profile.version", maximum=255)
    _text(source, "profile.source")
    _unique_text(compatible_dataset_ids, "profile.compatible_dataset_ids")


def _validate_generic_targets(generic_targets: tuple[str, ...], exact_targets: set[str]) -> None:
    _unique_text(generic_targets, "profile.generic_targets")
    overlap = sorted(set(generic_targets) & exact_targets)
    if overlap:
        raise EmbodimentError(f"generic and exact targets overlap: {overlap}")


@dataclass(frozen=True)
class MappingDisposition:
    status: DispositionStatus
    code: str
    neuron_id: int
    provenance: SourceProvenance
    field: str
    value: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "code": self.code,
            "neuron_id": self.neuron_id,
            "provenance": _provenance_dict(self.provenance),
            "field": self.field,
            "value": self.value,
        }


@dataclass(frozen=True)
class DirectLink:
    neuron_id: int
    actuator_id: str
    weight: Fraction
    direction: Direction
    confidence: Decimal
    provenance: SourceProvenance

    def to_dict(self) -> dict[str, object]:
        return {
            "neuron_id": self.neuron_id,
            "actuator_id": self.actuator_id,
            "weight": _fraction_text(self.weight),
            "direction": self.direction,
            "confidence": _decimal_text(self.confidence),
            "provenance": _provenance_dict(self.provenance),
        }


@dataclass(frozen=True)
class NeuronMuscleLink:
    neuron_id: int
    muscle_id: str
    weight: Fraction
    confidence: Decimal
    provenance: SourceProvenance

    def to_dict(self) -> dict[str, object]:
        return {
            "neuron_id": self.neuron_id,
            "muscle_id": self.muscle_id,
            "weight": _fraction_text(self.weight),
            "confidence": _decimal_text(self.confidence),
            "provenance": _provenance_dict(self.provenance),
        }


@dataclass(frozen=True)
class MuscleActuatorLink:
    muscle_id: str
    actuator_id: str
    weight: Fraction
    direction: Direction

    def to_dict(self) -> dict[str, object]:
        return {
            "muscle_id": self.muscle_id,
            "actuator_id": self.actuator_id,
            "weight": _fraction_text(self.weight),
            "direction": self.direction,
        }


@dataclass(frozen=True)
class MappingReceipt:
    engine_version: str
    dataset_id: str
    release: str
    manifest_sha256: str
    profile_id: str
    profile_version: str
    profile_sha256: str
    actuator_catalog_id: str
    actuator_catalog_version: str
    actuator_catalog_sha256: str
    muscle_catalog_id: str | None
    muscle_catalog_version: str | None
    muscle_catalog_sha256: str | None
    mode: Literal["direct_actuator", "muscle_mediated"]
    input_record_count: int
    link_count: int
    muscle_count: int
    disposition_count: int
    graph_sha256: str

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "engine_version": self.engine_version,
            "dataset_id": self.dataset_id,
            "release": self.release,
            "manifest_sha256": self.manifest_sha256,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "profile_sha256": self.profile_sha256,
            "actuator_catalog_id": self.actuator_catalog_id,
            "actuator_catalog_version": self.actuator_catalog_version,
            "actuator_catalog_sha256": self.actuator_catalog_sha256,
            "muscle_catalog_id": self.muscle_catalog_id,
            "muscle_catalog_version": self.muscle_catalog_version,
            "muscle_catalog_sha256": self.muscle_catalog_sha256,
            "mode": self.mode,
            "input_record_count": self.input_record_count,
            "link_count": self.link_count,
            "muscle_count": self.muscle_count,
            "disposition_count": self.disposition_count,
            "graph_sha256": self.graph_sha256,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class DirectMapping:
    dataset_id: str
    release: str
    manifest_sha256: str
    profile_id: str
    profile_version: str
    profile_sha256: str
    actuator_catalog_id: str
    actuator_catalog_version: str
    actuator_catalog_sha256: str
    input_record_count: int
    links: tuple[DirectLink, ...]
    dispositions: tuple[MappingDisposition, ...]
    receipt: MappingReceipt

    @property
    def executable(self) -> bool:
        return bool(self.links)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "mode": "direct_actuator",
            "dataset": {
                "dataset_id": self.dataset_id,
                "release": self.release,
                "manifest_sha256": self.manifest_sha256,
            },
            "profile": {
                "profile_id": self.profile_id,
                "version": self.profile_version,
                "sha256": self.profile_sha256,
            },
            "actuator_catalog": {
                "catalog_id": self.actuator_catalog_id,
                "version": self.actuator_catalog_version,
                "sha256": self.actuator_catalog_sha256,
            },
            "input_record_count": self.input_record_count,
            "executable": self.executable,
            "links": [item.to_dict() for item in self.links],
            "dispositions": [item.to_dict() for item in self.dispositions],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class MuscleMapping:
    dataset_id: str
    release: str
    manifest_sha256: str
    profile_id: str
    profile_version: str
    profile_sha256: str
    actuator_catalog_id: str
    actuator_catalog_version: str
    actuator_catalog_sha256: str
    muscle_catalog_id: str
    muscle_catalog_version: str
    muscle_catalog_sha256: str
    input_record_count: int
    muscles: tuple[Muscle, ...]
    neuron_to_muscle: tuple[NeuronMuscleLink, ...]
    muscle_to_actuator: tuple[MuscleActuatorLink, ...]
    dispositions: tuple[MappingDisposition, ...]
    receipt: MappingReceipt

    @property
    def executable(self) -> bool:
        return bool(self.neuron_to_muscle) and bool(self.muscle_to_actuator)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "mode": "muscle_mediated",
            "dataset": {
                "dataset_id": self.dataset_id,
                "release": self.release,
                "manifest_sha256": self.manifest_sha256,
            },
            "profile": {
                "profile_id": self.profile_id,
                "version": self.profile_version,
                "sha256": self.profile_sha256,
            },
            "actuator_catalog": {
                "catalog_id": self.actuator_catalog_id,
                "version": self.actuator_catalog_version,
                "sha256": self.actuator_catalog_sha256,
            },
            "muscle_catalog": {
                "catalog_id": self.muscle_catalog_id,
                "version": self.muscle_catalog_version,
                "sha256": self.muscle_catalog_sha256,
            },
            "input_record_count": self.input_record_count,
            "executable": self.executable,
            "muscles": [item.to_dict() for item in self.muscles],
            "neuron_to_muscle": [item.to_dict() for item in self.neuron_to_muscle],
            "muscle_to_actuator": [item.to_dict() for item in self.muscle_to_actuator],
            "dispositions": [item.to_dict() for item in self.dispositions],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def _transform_identity(
    records: tuple[MotorAnatomyRecord, ...],
    manifest_sha256: str,
    compatible_dataset_ids: tuple[str, ...],
) -> tuple[str, str]:
    if _SHA256.fullmatch(manifest_sha256) is None:
        raise EmbodimentError("manifest_sha256 must be a lower-case SHA-256")
    if not records:
        raise EmbodimentError("motor anatomy records must not be empty")
    dataset_id = records[0].provenance.dataset_id
    release = records[0].provenance.release
    if dataset_id not in compatible_dataset_ids:
        raise EmbodimentError(f"dataset {dataset_id!r} is not compatible with this profile")
    seen: set[int] = set()
    for record in records:
        if (
            record.provenance.dataset_id != dataset_id
            or record.provenance.release != release
        ):
            raise EmbodimentError("motor anatomy records must share dataset identity and release")
        if record.neuron_id in seen:
            raise EmbodimentError(f"duplicate neuron identity {record.neuron_id}")
        seen.add(record.neuron_id)
    return dataset_id, release


def _body_regions(
    record: MotorAnatomyRecord,
    body_lookup: dict[str, str],
    allow_multiple: bool,
) -> tuple[tuple[str, ...] | None, MappingDisposition | None]:
    if not record.exit_nerves:
        return None, _disposition(record, "unmapped", "missing_exit_nerve", "exit_nerves", None)
    unknown = [value for value in record.exit_nerves if value not in body_lookup]
    if unknown:
        return None, _disposition(
            record,
            "unmapped",
            "unknown_exit_nerve",
            "exit_nerves",
            " ".join(unknown),
        )
    regions = tuple(dict.fromkeys(body_lookup[value] for value in record.exit_nerves))
    if len(regions) > 1 and not allow_multiple:
        return None, _disposition(
            record,
            "ambiguous",
            "ambiguous_body_region",
            "exit_nerves",
            " ".join(record.exit_nerves),
        )
    return regions, None


def _disposition(
    record: MotorAnatomyRecord,
    status: DispositionStatus,
    code: str,
    field: str,
    value: str | None,
) -> MappingDisposition:
    return MappingDisposition(status, code, record.neuron_id, record.provenance, field, value)


def _common_source_rules(
    record: MotorAnatomyRecord,
    body_lookup: dict[str, str],
    confidence_lookup: dict[int, Decimal],
    missing_certainty_confidence: ExactDecimal | None,
    generic_targets: set[str],
    allow_multiple: bool,
) -> tuple[tuple[str, ...] | None, Decimal | None, MappingDisposition | None]:
    regions, issue = _body_regions(record, body_lookup, allow_multiple)
    if issue is not None:
        return None, None, issue
    if record.target_label is None:
        return None, None, _disposition(
            record, "unmapped", "missing_target", "target_label", None
        )
    if record.target_label in generic_targets:
        return None, None, _disposition(
            record,
            "ambiguous",
            "ambiguous_target",
            "target_label",
            record.target_label,
        )
    if record.certainty is None:
        if missing_certainty_confidence is not None:
            return (
                regions,
                _confidence(missing_certainty_confidence, "missing certainty confidence"),
                None,
            )
        value = None
    elif record.certainty not in confidence_lookup:
        value = str(record.certainty)
    else:
        return regions, confidence_lookup[record.certainty], None
    return None, None, _disposition(
        record,
        "unmapped",
        "missing_confidence",
        "certainty",
        value,
    )


def transform_direct(
    records: tuple[MotorAnatomyRecord, ...],
    manifest_sha256: str,
    profile: DirectProfile,
    actuator_catalog: ActuatorCatalog,
) -> DirectMapping:
    """Build a deterministic direct neuron-to-actuator graph."""
    dataset_id, release = _transform_identity(
        records, manifest_sha256, profile.compatible_dataset_ids
    )
    profile_sha256 = profile.sha256()
    actuator_catalog_sha256 = actuator_catalog.sha256()
    body_lookup = {item.exit_nerve: item.body_region for item in profile.body_region_rules}
    target_lookup = {item.target_label: item for item in profile.target_rules}
    confidence_lookup = {
        item.certainty: _confidence(item.confidence, "confidence")
        for item in profile.confidence_rules
    }
    actuators_by_region_joint: dict[tuple[str, str], list[Actuator]] = {}
    for actuator in actuator_catalog.actuators:
        actuators_by_region_joint.setdefault((actuator.body_region, actuator.joint), []).append(
            actuator
        )

    raw: list[tuple[MotorAnatomyRecord, Actuator, DirectTargetRule, Decimal]] = []
    dispositions: list[MappingDisposition] = []
    for record in records:
        regions, confidence, issue = _common_source_rules(
            record,
            body_lookup,
            confidence_lookup,
            profile.missing_certainty_confidence,
            set(profile.generic_targets),
            profile.allow_multiple_body_regions,
        )
        if issue is not None:
            dispositions.append(issue)
            continue
        assert regions is not None and confidence is not None and record.target_label is not None
        target_rule = target_lookup.get(record.target_label)
        if target_rule is None:
            dispositions.append(
                _disposition(
                    record,
                    "unmapped",
                    "unknown_target",
                    "target_label",
                    record.target_label,
                )
            )
            continue
        record_candidates: list[Actuator] = []
        missing_regions: list[str] = []
        for region in regions:
            matches = actuators_by_region_joint.get((region, target_rule.joint), [])
            if not matches:
                missing_regions.append(region)
            else:
                record_candidates.extend(matches)
        if missing_regions:
            dispositions.append(
                _disposition(
                    record,
                    "unmapped",
                    "unknown_actuator",
                    "body_region/joint",
                    ",".join(f"{region}/{target_rule.joint}" for region in missing_regions),
                )
            )
            continue
        if len(record_candidates) > len(regions) and not profile.allow_joint_fanout:
            dispositions.append(
                _disposition(
                    record,
                    "ambiguous",
                    "ambiguous_actuator",
                    "body_region/joint",
                    ",".join(f"{region}/{target_rule.joint}" for region in regions),
                )
            )
            continue
        for actuator in record_candidates:
            raw.append((record, actuator, target_rule, confidence))

    counts: dict[str, int] = {}
    for _, actuator, _, _ in raw:
        counts[actuator.actuator_id] = counts.get(actuator.actuator_id, 0) + 1
    links = tuple(
        DirectLink(
            neuron_id=record.neuron_id,
            actuator_id=actuator.actuator_id,
            weight=(
                Fraction(1, counts[actuator.actuator_id])
                if profile.weight_policy == "per_actuator_equal_share"
                else Fraction(1)
            ),
            direction=target_rule.direction,
            confidence=confidence,
            provenance=record.provenance,
        )
        for record, actuator, target_rule, confidence in raw
    )
    _reject_duplicate_pairs(
        tuple((item.neuron_id, item.actuator_id) for item in links),
        "direct neuron/actuator",
    )
    temporary = DirectMapping(
        dataset_id=dataset_id,
        release=release,
        manifest_sha256=manifest_sha256,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        profile_sha256=profile_sha256,
        actuator_catalog_id=actuator_catalog.catalog_id,
        actuator_catalog_version=actuator_catalog.version,
        actuator_catalog_sha256=actuator_catalog_sha256,
        input_record_count=len(records),
        links=links,
        dispositions=tuple(dispositions),
        receipt=_placeholder_receipt(
            dataset_id,
            release,
            manifest_sha256,
            profile,
            actuator_catalog,
            "direct_actuator",
        ),
    )
    receipt = _receipt(
        temporary.sha256(),
        dataset_id,
        release,
        manifest_sha256,
        profile,
        actuator_catalog,
        None,
        "direct_actuator",
        len(records),
        len(links),
        0,
        len(dispositions),
    )
    return DirectMapping(
        dataset_id=dataset_id,
        release=release,
        manifest_sha256=manifest_sha256,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        profile_sha256=profile_sha256,
        actuator_catalog_id=actuator_catalog.catalog_id,
        actuator_catalog_version=actuator_catalog.version,
        actuator_catalog_sha256=actuator_catalog_sha256,
        input_record_count=len(records),
        links=links,
        dispositions=tuple(dispositions),
        receipt=receipt,
    )


def transform_muscle_mediated(
    records: tuple[MotorAnatomyRecord, ...],
    manifest_sha256: str,
    profile: MuscleProfile,
    muscle_catalog: MuscleCatalog,
    actuator_catalog: ActuatorCatalog,
) -> MuscleMapping:
    """Build a deterministic neuron-to-muscle-to-actuator graph."""
    dataset_id, release = _transform_identity(
        records, manifest_sha256, profile.compatible_dataset_ids
    )
    profile_sha256 = profile.sha256()
    actuator_catalog_sha256 = actuator_catalog.sha256()
    muscle_catalog_sha256 = muscle_catalog.sha256()
    muscles_by_id = {item.muscle_id: item for item in muscle_catalog.muscles}
    actuators_by_id = {item.actuator_id: item for item in actuator_catalog.actuators}
    _validate_muscle_profile(profile, muscles_by_id, actuators_by_id)
    body_lookup = {item.exit_nerve: item.body_region for item in profile.body_region_rules}
    target_lookup = {
        (item.body_region, item.target_label): item for item in profile.target_rules
    }
    confidence_lookup = {
        item.certainty: _confidence(item.confidence, "confidence")
        for item in profile.confidence_rules
    }

    neuron_links: list[NeuronMuscleLink] = []
    dispositions: list[MappingDisposition] = []
    selected_muscles: list[str] = []
    for record in records:
        regions, confidence, issue = _common_source_rules(
            record,
            body_lookup,
            confidence_lookup,
            profile.missing_certainty_confidence,
            set(profile.generic_targets),
            profile.allow_multiple_body_regions,
        )
        if issue is not None:
            dispositions.append(issue)
            continue
        assert regions is not None and confidence is not None and record.target_label is not None
        rules: list[MuscleTargetRule] = []
        missing_regions: list[str] = []
        for region in regions:
            target_rule = target_lookup.get((region, record.target_label))
            if target_rule is None:
                missing_regions.append(region)
            else:
                rules.append(target_rule)
        if missing_regions:
            dispositions.append(
                _disposition(
                    record,
                    "unmapped",
                    "unknown_muscle_target",
                    "body_region/target_label",
                    ",".join(f"{region}/{record.target_label}" for region in missing_regions),
                )
            )
            continue
        for target_rule in rules:
            for target in target_rule.muscles:
                weight = _positive_rational(target.weight, "muscle target weight")
                neuron_links.append(
                    NeuronMuscleLink(
                        record.neuron_id,
                        target.muscle_id,
                        weight,
                        confidence,
                        record.provenance,
                    )
                )
                if target.muscle_id not in selected_muscles:
                    selected_muscles.append(target.muscle_id)

    _reject_duplicate_pairs(
        tuple((item.neuron_id, item.muscle_id) for item in neuron_links),
        "neuron/muscle",
    )
    selected_set = set(selected_muscles)
    actuator_links = tuple(
        MuscleActuatorLink(
            item.muscle_id,
            item.actuator_id,
            _positive_rational(item.weight, "muscle actuator weight"),
            item.direction,
        )
        for item in profile.actuator_rules
        if item.muscle_id in selected_set
    )
    selected_definitions = tuple(muscles_by_id[item] for item in selected_muscles)
    temporary = MuscleMapping(
        dataset_id=dataset_id,
        release=release,
        manifest_sha256=manifest_sha256,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        profile_sha256=profile_sha256,
        actuator_catalog_id=actuator_catalog.catalog_id,
        actuator_catalog_version=actuator_catalog.version,
        actuator_catalog_sha256=actuator_catalog_sha256,
        muscle_catalog_id=muscle_catalog.catalog_id,
        muscle_catalog_version=muscle_catalog.version,
        muscle_catalog_sha256=muscle_catalog_sha256,
        input_record_count=len(records),
        muscles=selected_definitions,
        neuron_to_muscle=tuple(neuron_links),
        muscle_to_actuator=actuator_links,
        dispositions=tuple(dispositions),
        receipt=_placeholder_receipt(
            dataset_id,
            release,
            manifest_sha256,
            profile,
            actuator_catalog,
            "muscle_mediated",
            muscle_catalog,
        ),
    )
    link_count = len(neuron_links) + len(actuator_links)
    receipt = _receipt(
        temporary.sha256(),
        dataset_id,
        release,
        manifest_sha256,
        profile,
        actuator_catalog,
        muscle_catalog,
        "muscle_mediated",
        len(records),
        link_count,
        len(selected_definitions),
        len(dispositions),
    )
    return MuscleMapping(
        dataset_id=dataset_id,
        release=release,
        manifest_sha256=manifest_sha256,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        profile_sha256=profile_sha256,
        actuator_catalog_id=actuator_catalog.catalog_id,
        actuator_catalog_version=actuator_catalog.version,
        actuator_catalog_sha256=actuator_catalog_sha256,
        muscle_catalog_id=muscle_catalog.catalog_id,
        muscle_catalog_version=muscle_catalog.version,
        muscle_catalog_sha256=muscle_catalog_sha256,
        input_record_count=len(records),
        muscles=selected_definitions,
        neuron_to_muscle=tuple(neuron_links),
        muscle_to_actuator=actuator_links,
        dispositions=tuple(dispositions),
        receipt=receipt,
    )


def _validate_muscle_profile(
    profile: MuscleProfile,
    muscles: dict[str, Muscle],
    actuators: dict[str, Actuator],
) -> None:
    referenced: set[str] = set()
    for target_rule in profile.target_rules:
        for target in target_rule.muscles:
            muscle = muscles.get(target.muscle_id)
            if muscle is None:
                raise EmbodimentError(f"profile references unknown muscle {target.muscle_id!r}")
            if muscle.body_region != target_rule.body_region:
                raise EmbodimentError(
                    f"muscle {muscle.muscle_id!r} body region differs from its target rule"
                )
            referenced.add(target.muscle_id)
    actuator_muscles: set[str] = set()
    for actuator_rule in profile.actuator_rules:
        muscle = muscles.get(actuator_rule.muscle_id)
        if muscle is None:
            raise EmbodimentError(
                f"actuator rule references unknown muscle {actuator_rule.muscle_id!r}"
            )
        actuator = actuators.get(actuator_rule.actuator_id)
        if actuator is None:
            raise EmbodimentError(
                f"actuator rule references unknown actuator {actuator_rule.actuator_id!r}"
            )
        if muscle.body_region != actuator.body_region:
            raise EmbodimentError(
                f"muscle {muscle.muscle_id!r} and actuator {actuator.actuator_id!r} "
                "have different body regions"
            )
        actuator_muscles.add(actuator_rule.muscle_id)
    missing = sorted(referenced - actuator_muscles)
    if missing:
        raise EmbodimentError(f"muscle {missing[0]!r} has no actuator rule")


def _reject_duplicate_pairs(values: tuple[tuple[object, object], ...], path: str) -> None:
    if len(values) != len(set(values)):
        raise EmbodimentError(f"derived {path} pairs must be unique")


def _receipt(
    graph_sha256: str,
    dataset_id: str,
    release: str,
    manifest_sha256: str,
    profile: DirectProfile | MuscleProfile,
    actuator_catalog: ActuatorCatalog,
    muscle_catalog: MuscleCatalog | None,
    mode: Literal["direct_actuator", "muscle_mediated"],
    input_count: int,
    link_count: int,
    muscle_count: int,
    disposition_count: int,
) -> MappingReceipt:
    return MappingReceipt(
        engine_version=__version__,
        dataset_id=dataset_id,
        release=release,
        manifest_sha256=manifest_sha256,
        profile_id=profile.profile_id,
        profile_version=profile.version,
        profile_sha256=profile.sha256(),
        actuator_catalog_id=actuator_catalog.catalog_id,
        actuator_catalog_version=actuator_catalog.version,
        actuator_catalog_sha256=actuator_catalog.sha256(),
        muscle_catalog_id=None if muscle_catalog is None else muscle_catalog.catalog_id,
        muscle_catalog_version=None if muscle_catalog is None else muscle_catalog.version,
        muscle_catalog_sha256=None if muscle_catalog is None else muscle_catalog.sha256(),
        mode=mode,
        input_record_count=input_count,
        link_count=link_count,
        muscle_count=muscle_count,
        disposition_count=disposition_count,
        graph_sha256=graph_sha256,
    )


def _placeholder_receipt(
    dataset_id: str,
    release: str,
    manifest_sha256: str,
    profile: DirectProfile | MuscleProfile,
    actuator_catalog: ActuatorCatalog,
    mode: Literal["direct_actuator", "muscle_mediated"],
    muscle_catalog: MuscleCatalog | None = None,
) -> MappingReceipt:
    return _receipt(
        "0" * 64,
        dataset_id,
        release,
        manifest_sha256,
        profile,
        actuator_catalog,
        muscle_catalog,
        mode,
        0,
        0,
        0,
        0,
    )
