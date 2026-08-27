"""Static, non-executing envelopes for historical FlyBrian experiments."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from typing import Literal, TypeAlias

from .schema import validate_experiment_spec

ExactDecimal: TypeAlias = Decimal | int | str
OptionValueKind = Literal[
    "boolean",
    "integer",
    "decimal",
    "text",
    "decimal_list",
    "text_list",
    "null",
]
OptionOrigin = Literal[
    "default", "config_table", "invocation", "derived", "source_constant"
]
OptionApplication = Literal["applied", "ignored", "unresolved", "not_applicable"]
ControllerStageKind = Literal[
    "neural_initialization",
    "open_loop_schedule",
    "sensor_feedback",
    "muscle_drive",
    "joint_torque_transform",
    "body_property_override",
    "initial_condition",
    "artifact_capture",
]
VariationTargetKind = Literal["option", "fes", "controller"]
ReproducibilityClass = Literal[
    "PROVENANCE_ONLY", "RUNNABLE_CONNECTOME", "RUNNABLE_EMBODIED"
]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NAMESPACE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]*(?:[.:][A-Za-z0-9][A-Za-z0-9_.:-]*)+$"
)
_ALLOWED_EXTERNAL_SIGNALS = {
    "actuator_state",
    "body_pose",
    "contact_force",
    "joint_angle",
    "joint_velocity",
    "motor_command",
    "muscle_state",
    "neural_state",
    "simulation_clock",
    "spike_counts",
}
_EXECUTABLE_PARAMETER_NAMES = {
    "callback",
    "callable",
    "code",
    "command",
    "expression",
    "import",
    "lambda",
    "module",
    "pickle",
    "script",
    "source_code",
}
STATIC_PYTHON_EXTRACTOR_ID = "org.flybrian.static-python-extractor"
STATIC_PYTHON_EXTRACTOR_VERSION = "1.1"


class HistoricalEnvelopeError(ValueError):
    """A historical source, envelope, controller, or variation is invalid."""


def _text(value: object, path: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise HistoricalEnvelopeError(f"{path} must be a non-empty trimmed string")
    if len(value) > maximum:
        raise HistoricalEnvelopeError(f"{path} must contain at most {maximum} characters")
    return value


def _namespaced(value: str, path: str) -> str:
    checked = _text(value, path, maximum=255)
    if _NAMESPACE.fullmatch(checked) is None:
        raise HistoricalEnvelopeError(f"{path} must be namespaced")
    return checked


def _digest(value: str, path: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise HistoricalEnvelopeError(f"{path} must be lowercase SHA-256")
    return value


def _non_negative_integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HistoricalEnvelopeError(f"{path} must be a non-negative integer")
    return value


def _exact_decimal(value: object, path: str) -> Decimal:
    if isinstance(value, (bool, float)):
        raise HistoricalEnvelopeError(f"{path} must be exact decimal, not binary float")
    if not isinstance(value, (Decimal, int, str)):
        raise HistoricalEnvelopeError(f"{path} must be exact decimal")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise HistoricalEnvelopeError(f"{path} must be exact decimal") from error
    if not result.is_finite():
        raise HistoricalEnvelopeError(f"{path} must be finite")
    return result


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    text = format(normalized, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _unique_text(values: Sequence[str], path: str, *, allow_empty: bool = True) -> None:
    if not allow_empty and not values:
        raise HistoricalEnvelopeError(f"{path} must not be empty")
    checked = tuple(_text(value, f"{path} item", maximum=255) for value in values)
    if len(checked) != len(set(checked)):
        raise HistoricalEnvelopeError(f"{path} must be unique")
    if len(checked) != len({value.casefold() for value in checked}):
        raise HistoricalEnvelopeError(f"{path} must not case-collide")


def _canonical_option_value(value: object, kind: OptionValueKind, path: str) -> object:
    if value is None:
        return None
    if kind == "null":
        raise HistoricalEnvelopeError(f"{path} must be null")
    if kind == "boolean":
        if not isinstance(value, bool):
            raise HistoricalEnvelopeError(f"{path} must be boolean")
        return value
    if kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise HistoricalEnvelopeError(f"{path} must be integer")
        return value
    if kind == "decimal":
        return _exact_decimal(value, path)
    if kind == "text":
        return _text(value, path)
    if kind == "decimal_list":
        if not isinstance(value, (list, tuple)):
            raise HistoricalEnvelopeError(f"{path} must be decimal list")
        return tuple(_exact_decimal(item, f"{path} item") for item in value)
    if kind == "text_list":
        if not isinstance(value, (list, tuple)):
            raise HistoricalEnvelopeError(f"{path} must be text list")
        items = tuple(_text(item, f"{path} item") for item in value)
        return items
    raise HistoricalEnvelopeError(f"{path} has unsupported value kind")


def _option_value_dict(value: object, kind: OptionValueKind) -> object:
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if kind == "decimal_list" and isinstance(value, tuple):
        return [_decimal_text(item) for item in value if isinstance(item, Decimal)]
    if isinstance(value, tuple):
        return list(value)
    return value


def _canonical_general_value(value: object, path: str = "value") -> object:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, float):
        raise HistoricalEnvelopeError(f"{path} must not contain binary float")
    if isinstance(value, tuple | list):
        return [
            _canonical_general_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise HistoricalEnvelopeError(f"{path} object keys must be strings")
        return {
            key: _canonical_general_value(item, f"{path}.{key}")
            for key, item in value.items()
        }
    raise HistoricalEnvelopeError(f"{path} contains unsupported value")


@dataclass(frozen=True)
class HistoricalSourceAuthority:
    repository: str
    revision: str
    logical_path: str
    byte_length: int
    sha256: str
    license_id: str
    access: str
    redistribution: str
    extractor_id: str
    extractor_version: str

    def __post_init__(self) -> None:
        _text(self.repository, "historical_source.repository")
        _text(self.revision, "historical_source.revision", maximum=255)
        logical_path = _text(
            self.logical_path, "historical_source.logical_path", maximum=1024
        )
        if logical_path.startswith(("/", "\\")) or ".." in logical_path.split("/"):
            raise HistoricalEnvelopeError(
                "historical_source.logical_path must be safe relative path"
            )
        _non_negative_integer(self.byte_length, "historical_source.byte_length")
        _digest(self.sha256, "historical_source.sha256")
        for name, value in (
            ("license_id", self.license_id),
            ("access", self.access),
            ("redistribution", self.redistribution),
            ("extractor_version", self.extractor_version),
        ):
            _text(value, f"historical_source.{name}", maximum=255)
        _namespaced(self.extractor_id, "historical_source.extractor_id")

    def to_dict(self) -> dict[str, object]:
        return {
            "repository": self.repository,
            "revision": self.revision,
            "logical_path": self.logical_path,
            "byte_length": self.byte_length,
            "sha256": self.sha256,
            "license_id": self.license_id,
            "access": self.access,
            "redistribution": self.redistribution,
            "extractor_id": self.extractor_id,
            "extractor_version": self.extractor_version,
        }


@dataclass(frozen=True)
class HistoricalOptionResolution:
    option_id: str
    legacy_names: tuple[str, ...]
    value_kind: OptionValueKind
    unit: str | None
    default_value: object
    requested_value: object
    effective_value: object
    origin: OptionOrigin
    application: OptionApplication
    resolution_rule: str
    target: str | None
    notes: str

    def __post_init__(self) -> None:
        _namespaced(self.option_id, "historical_option.option_id")
        _unique_text(self.legacy_names, "historical_option.legacy_names", allow_empty=False)
        if self.value_kind not in (
            "boolean",
            "integer",
            "decimal",
            "text",
            "decimal_list",
            "text_list",
            "null",
        ):
            raise HistoricalEnvelopeError("historical_option.value_kind is unsupported")
        numeric = self.value_kind in {"integer", "decimal", "decimal_list"}
        if numeric:
            _text(self.unit, "historical_option.unit", maximum=64)
        elif self.unit is not None:
            raise HistoricalEnvelopeError(
                "historical_option.unit is only valid for numeric kinds"
            )
        for field_name in ("default_value", "requested_value", "effective_value"):
            object.__setattr__(
                self,
                field_name,
                _canonical_option_value(
                    getattr(self, field_name),
                    self.value_kind,
                    f"historical_option.{field_name}",
                ),
            )
        if self.origin not in (
            "default",
            "config_table",
            "invocation",
            "derived",
            "source_constant",
        ):
            raise HistoricalEnvelopeError("historical_option.origin is unsupported")
        if self.application not in (
            "applied",
            "ignored",
            "unresolved",
            "not_applicable",
        ):
            raise HistoricalEnvelopeError("historical_option.application is unsupported")
        _namespaced(self.resolution_rule, "historical_option.resolution_rule")
        if self.target is not None:
            _text(self.target, "historical_option.target", maximum=1024)
            if not self.target.startswith("/"):
                raise HistoricalEnvelopeError(
                    "historical_option.target must be RFC 6901 JSON pointer"
                )
        _text(self.notes, "historical_option.notes")

    def to_dict(self) -> dict[str, object]:
        return {
            "option_id": self.option_id,
            "legacy_names": list(self.legacy_names),
            "value_kind": self.value_kind,
            "unit": self.unit,
            "default_value": _option_value_dict(self.default_value, self.value_kind),
            "requested_value": _option_value_dict(
                self.requested_value, self.value_kind
            ),
            "effective_value": _option_value_dict(
                self.effective_value, self.value_kind
            ),
            "origin": self.origin,
            "application": self.application,
            "resolution_rule": self.resolution_rule,
            "target": self.target,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class HistoricalParameter:
    name: str
    value: ExactDecimal
    unit: str

    def __post_init__(self) -> None:
        name = _text(self.name, "historical_parameter.name", maximum=255)
        if name.casefold() in _EXECUTABLE_PARAMETER_NAMES or self.unit == "code":
            raise HistoricalEnvelopeError(
                "historical controller parameter must not contain executable behavior"
            )
        object.__setattr__(
            self,
            "value",
            _exact_decimal(self.value, f"historical_parameter.{name}.value"),
        )
        _text(self.unit, f"historical_parameter.{name}.unit", maximum=64)

    def to_dict(self) -> dict[str, str]:
        value = self.value
        assert isinstance(value, Decimal)
        return {"name": self.name, "value": _decimal_text(value), "unit": self.unit}


@dataclass(frozen=True)
class HistoricalControllerPhase:
    start_ms: ExactDecimal
    end_ms: ExactDecimal
    parameters: tuple[HistoricalParameter, ...]

    def __post_init__(self) -> None:
        start = _exact_decimal(self.start_ms, "historical_phase.start_ms")
        end = _exact_decimal(self.end_ms, "historical_phase.end_ms")
        if start < 0 or end <= start:
            raise HistoricalEnvelopeError(
                "historical controller phase intervals must be positive and increasing"
            )
        object.__setattr__(self, "start_ms", start)
        object.__setattr__(self, "end_ms", end)
        names = tuple(item.name for item in self.parameters)
        _unique_text(names, "historical_phase parameter names")

    def to_dict(self) -> dict[str, object]:
        assert isinstance(self.start_ms, Decimal)
        assert isinstance(self.end_ms, Decimal)
        return {
            "start_ms": _decimal_text(self.start_ms),
            "end_ms": _decimal_text(self.end_ms),
            "parameters": [item.to_dict() for item in self.parameters],
        }


@dataclass(frozen=True)
class HistoricalControllerStage:
    stage_id: str
    kind: ControllerStageKind
    profile_id: str
    profile_version: str
    profile_sha256: str
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    parameters: tuple[HistoricalParameter, ...]
    activation_condition: bool
    phases: tuple[HistoricalControllerPhase, ...]

    def __post_init__(self) -> None:
        _text(self.stage_id, "historical_stage.stage_id", maximum=255)
        if self.kind not in (
            "neural_initialization",
            "open_loop_schedule",
            "sensor_feedback",
            "muscle_drive",
            "joint_torque_transform",
            "body_property_override",
            "initial_condition",
            "artifact_capture",
        ):
            raise HistoricalEnvelopeError("historical_stage.kind is unsupported")
        _namespaced(self.profile_id, "historical_stage.profile_id")
        _text(self.profile_version, "historical_stage.profile_version", maximum=255)
        _digest(self.profile_sha256, "historical_stage.profile_sha256")
        _unique_text(self.inputs, "historical_stage.inputs")
        _unique_text(self.outputs, "historical_stage.outputs", allow_empty=False)
        names = tuple(item.name for item in self.parameters)
        _unique_text(names, "historical_stage parameter names")
        if not isinstance(self.activation_condition, bool):
            raise HistoricalEnvelopeError(
                "historical_stage.activation_condition must be boolean"
            )
        prior_end: Decimal | None = None
        for phase in self.phases:
            assert isinstance(phase.start_ms, Decimal)
            assert isinstance(phase.end_ms, Decimal)
            if prior_end is not None and phase.start_ms < prior_end:
                raise HistoricalEnvelopeError(
                    "historical controller phase intervals must not overlap"
                )
            prior_end = phase.end_ms

    def to_dict(self) -> dict[str, object]:
        return {
            "stage_id": self.stage_id,
            "kind": self.kind,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "profile_sha256": self.profile_sha256,
            "inputs": list(self.inputs),
            "outputs": list(self.outputs),
            "parameters": [item.to_dict() for item in self.parameters],
            "activation_condition": self.activation_condition,
            "phases": [item.to_dict() for item in self.phases],
        }


@dataclass(frozen=True)
class HistoricalControllerProfile:
    profile_id: str
    version: str
    source: str
    stages: tuple[HistoricalControllerStage, ...]

    def __post_init__(self) -> None:
        _namespaced(self.profile_id, "historical_controller.profile_id")
        _text(self.version, "historical_controller.version", maximum=255)
        _text(self.source, "historical_controller.source")
        if not self.stages:
            raise HistoricalEnvelopeError("historical controller stages must not be empty")
        stage_ids = tuple(item.stage_id for item in self.stages)
        _unique_text(stage_ids, "historical controller stage IDs", allow_empty=False)
        produced = set(_ALLOWED_EXTERNAL_SIGNALS)
        output_owners: dict[str, str] = {}
        for stage in self.stages:
            missing = tuple(item for item in stage.inputs if item not in produced)
            if missing:
                raise HistoricalEnvelopeError(
                    f"historical controller input {missing[0]!r} must come from an earlier stage"
                )
            for output in stage.outputs:
                if output in output_owners:
                    raise HistoricalEnvelopeError(
                        f"historical controller output {output!r} has multiple producers"
                    )
                output_owners[output] = stage.stage_id
                produced.add(output)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "profile_id": self.profile_id,
            "version": self.version,
            "source": self.source,
            "stages": [item.to_dict() for item in self.stages],
        }

    def sha256(self) -> str:
        return _sha256(self.to_dict())


@dataclass(frozen=True)
class HistoricalSourceArtifact:
    artifact_id: str
    kind: str
    logical_path: str
    byte_length: int
    sha256: str

    def __post_init__(self) -> None:
        _namespaced(self.artifact_id, "historical_artifact.artifact_id")
        _text(self.kind, "historical_artifact.kind", maximum=255)
        path = _text(self.logical_path, "historical_artifact.logical_path", maximum=1024)
        if path.startswith(("/", "\\")) or ".." in path.split("/"):
            raise HistoricalEnvelopeError(
                "historical_artifact.logical_path must be safe relative path"
            )
        _non_negative_integer(self.byte_length, "historical_artifact.byte_length")
        _digest(self.sha256, "historical_artifact.sha256")

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "logical_path": self.logical_path,
            "byte_length": self.byte_length,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class HistoricalLineage:
    parent_envelope_id: str
    parent_version: str
    parent_sha256: str
    relation: Literal["import", "fork", "variation"]

    def __post_init__(self) -> None:
        _namespaced(self.parent_envelope_id, "historical_lineage.parent_envelope_id")
        _text(self.parent_version, "historical_lineage.parent_version", maximum=255)
        _digest(self.parent_sha256, "historical_lineage.parent_sha256")
        if self.relation not in ("import", "fork", "variation"):
            raise HistoricalEnvelopeError("historical_lineage.relation is unsupported")

    def to_dict(self) -> dict[str, str]:
        return {
            "parent_envelope_id": self.parent_envelope_id,
            "parent_version": self.parent_version,
            "parent_sha256": self.parent_sha256,
            "relation": self.relation,
        }


@dataclass(frozen=True)
class HistoricalVariationPatch:
    base_envelope_sha256: str
    patch_id: str
    target_kind: VariationTargetKind
    target: str
    before_canonical_value: object
    after_canonical_value: object
    reason: str

    def __post_init__(self) -> None:
        _digest(self.base_envelope_sha256, "historical_patch.base_envelope_sha256")
        _text(self.patch_id, "historical_patch.patch_id", maximum=255)
        if self.target_kind not in ("option", "fes", "controller"):
            raise HistoricalEnvelopeError("historical_patch.target_kind is unsupported")
        _text(self.target, "historical_patch.target", maximum=1024)
        if self.target_kind != "option" and not self.target.startswith("/"):
            raise HistoricalEnvelopeError(
                "historical_patch JSON target must be RFC 6901 pointer"
            )
        object.__setattr__(
            self,
            "before_canonical_value",
            _canonical_general_value(
                self.before_canonical_value, "historical_patch.before_canonical_value"
            ),
        )
        object.__setattr__(
            self,
            "after_canonical_value",
            _canonical_general_value(
                self.after_canonical_value, "historical_patch.after_canonical_value"
            ),
        )
        _text(self.reason, "historical_patch.reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "base_envelope_sha256": self.base_envelope_sha256,
            "patch_id": self.patch_id,
            "target_kind": self.target_kind,
            "target": self.target,
            "before_canonical_value": self.before_canonical_value,
            "after_canonical_value": self.after_canonical_value,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class HistoricalExperimentEnvelope:
    envelope_id: str
    version: str
    source: HistoricalSourceAuthority
    selector: str | None
    invocation: tuple[str, ...]
    options: tuple[HistoricalOptionResolution, ...]
    controller_profile: HistoricalControllerProfile | None
    fes: dict[str, object] | None
    expected_fes_sha256: str | None
    source_artifacts: tuple[HistoricalSourceArtifact, ...]
    missing_requirements: tuple[str, ...]
    lineage: HistoricalLineage | None
    variation_patches: tuple[HistoricalVariationPatch, ...] = ()

    def __post_init__(self) -> None:
        _namespaced(self.envelope_id, "historical_envelope.envelope_id")
        _text(self.version, "historical_envelope.version", maximum=255)
        if self.selector is not None:
            _text(self.selector, "historical_envelope.selector", maximum=255)
        for index, value in enumerate(self.invocation):
            _text(value, f"historical_envelope.invocation[{index}]", maximum=4096)
        option_ids = tuple(item.option_id for item in self.options)
        _unique_text(option_ids, "historical envelope option IDs")
        aliases: dict[str, str] = {}
        for item in self.options:
            for alias in item.legacy_names:
                owner = aliases.get(alias.casefold())
                if owner is not None and owner != item.option_id:
                    raise HistoricalEnvelopeError(
                        f"historical option alias {alias!r} targets multiple option IDs"
                    )
                aliases[alias.casefold()] = item.option_id
        artifact_ids = tuple(item.artifact_id for item in self.source_artifacts)
        _unique_text(artifact_ids, "historical envelope artifact IDs")
        if len(self.missing_requirements) != len(set(self.missing_requirements)):
            raise HistoricalEnvelopeError(
                "historical_envelope.missing_requirements must be unique"
            )
        for requirement in self.missing_requirements:
            _text(
                requirement,
                "historical_envelope.missing_requirements item",
                maximum=255,
            )
            if requirement != requirement.upper():
                raise HistoricalEnvelopeError(
                    "historical_envelope.missing_requirements must be uppercase codes"
                )
        if tuple(sorted(self.missing_requirements)) != self.missing_requirements:
            raise HistoricalEnvelopeError(
                "historical_envelope.missing_requirements must be sorted"
            )
        derived_missing: set[str] = set(self.missing_requirements)
        if self.source.revision.casefold() in {"unknown", "uncommitted"}:
            derived_missing.add("SOURCE_REVISION")
        if any(item.application == "unresolved" for item in self.options):
            derived_missing.add("OPTION_RESOLUTION")
        if self.fes is None:
            if self.expected_fes_sha256 is not None:
                raise HistoricalEnvelopeError(
                    "historical_envelope.expected_fes_sha256 requires FES"
                )
        else:
            validated = validate_experiment_spec(self.fes)
            expected = validated.sha256()
            if self.expected_fes_sha256 != expected:
                raise HistoricalEnvelopeError(
                    "historical_envelope.expected_fes_sha256 does not match FES"
                )
            object.__setattr__(self, "fes", copy.deepcopy(validated.value))
            if "neuron_models" not in validated.value:
                derived_missing.add("NEURON_MODELS")
            if "simulation" not in validated.value:
                derived_missing.add("SIMULATION_TIMING")
            if "execution" not in validated.value:
                derived_missing.add("BACKEND_PROFILE")
            embodiment = validated.embodiment_mode
            if embodiment != "none":
                embodied_config = validated.value.get("embodied_config")
                assert isinstance(embodied_config, dict)
                flybody = embodied_config.get("flybody")
                if not isinstance(flybody, dict) or not all(
                    isinstance(flybody.get(key), str) and flybody.get(key)
                    for key in ("id", "version")
                ):
                    derived_missing.add("BODY_MODEL")
                environment = embodied_config.get("environment")
                if not isinstance(environment, dict) or not all(
                    isinstance(environment.get(key), str) and environment.get(key)
                    for key in ("id", "version")
                ):
                    derived_missing.add("ENVIRONMENT")
                elif not isinstance(environment.get("initial_conditions"), dict):
                    derived_missing.add("INITIAL_STATE")
                if self.controller_profile is None:
                    derived_missing.add("CONTROLLER_PROFILE")
                else:
                    sim_time = Decimal(str(validated.value["sim_time_ms"]))
                    for stage in self.controller_profile.stages:
                        for phase in stage.phases:
                            assert isinstance(phase.end_ms, Decimal)
                            if phase.end_ms > sim_time:
                                raise HistoricalEnvelopeError(
                                    "historical controller phase exceeds FES simulation time"
                                )
                requests = validated.value.get("artifact_requests")
                if not isinstance(requests, list) or "motor_commands" not in requests:
                    derived_missing.add("ARTIFACT_CONTRACT")
        if self.source.license_id.casefold() == "unknown" or (
            self.source.access.casefold() == "unknown"
            or self.source.redistribution.casefold() == "unknown"
        ):
            derived_missing.add("LICENSE_ACCESS")
        object.__setattr__(self, "missing_requirements", tuple(sorted(derived_missing)))
        patch_ids = tuple(item.patch_id for item in self.variation_patches)
        _unique_text(patch_ids, "historical envelope variation patch IDs")

    @property
    def reproducibility_class(self) -> ReproducibilityClass:
        if self.missing_requirements or self.fes is None:
            return "PROVENANCE_ONLY"
        validated = validate_experiment_spec(self.fes)
        if validated.embodiment_mode == "none":
            return "RUNNABLE_CONNECTOME"
        assert self.controller_profile is not None
        return "RUNNABLE_EMBODIED"

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "envelope_id": self.envelope_id,
            "version": self.version,
            "source": self.source.to_dict(),
            "selector": self.selector,
            "invocation": list(self.invocation),
            "options": [item.to_dict() for item in self.options],
            "controller_profile": (
                None
                if self.controller_profile is None
                else self.controller_profile.to_dict()
            ),
            "fes": self.fes,
            "expected_fes_sha256": self.expected_fes_sha256,
            "source_artifacts": [item.to_dict() for item in self.source_artifacts],
            "missing_requirements": list(self.missing_requirements),
            "reproducibility_class": self.reproducibility_class,
            "lineage": None if self.lineage is None else self.lineage.to_dict(),
            "variation_patches": [item.to_dict() for item in self.variation_patches],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def _pointer_tokens(pointer: str) -> tuple[str, ...]:
    if not pointer.startswith("/"):
        raise HistoricalEnvelopeError("variation target must be RFC 6901 JSON pointer")
    return tuple(
        token.replace("~1", "/").replace("~0", "~")
        for token in pointer[1:].split("/")
    )


def _pointer_get(value: object, pointer: str) -> object:
    current = value
    for token in _pointer_tokens(pointer):
        if isinstance(current, dict):
            if token not in current:
                raise HistoricalEnvelopeError(f"variation target {pointer!r} is unknown")
            current = current[token]
        elif isinstance(current, list):
            raise HistoricalEnvelopeError(
                "variation must not use positional array identity for scientific entities"
            )
        else:
            raise HistoricalEnvelopeError(f"variation target {pointer!r} is unknown")
    return current


def _pointer_set(value: dict[str, object], pointer: str, replacement: object) -> None:
    tokens = _pointer_tokens(pointer)
    if not tokens:
        raise HistoricalEnvelopeError("variation cannot replace FES root")
    current: object = value
    for token in tokens[:-1]:
        if not isinstance(current, dict) or token not in current:
            raise HistoricalEnvelopeError(f"variation target {pointer!r} is unknown")
        current = current[token]
    if not isinstance(current, dict) or tokens[-1] not in current:
        raise HistoricalEnvelopeError(f"variation target {pointer!r} is unknown")
    current[tokens[-1]] = copy.deepcopy(replacement)


def _canonical_equal(left: object, right: object) -> bool:
    return _canonical_bytes(_canonical_general_value(left)) == _canonical_bytes(
        _canonical_general_value(right)
    )


def _canonical_fes_value(value: object, path: str = "fes") -> object:
    if isinstance(value, float):
        return _decimal_text(Decimal(str(value)))
    if isinstance(value, list):
        return [
            _canonical_fes_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        return {
            key: _canonical_fes_value(item, f"{path}.{key}")
            for key, item in value.items()
        }
    return _canonical_general_value(value, path)


def _canonical_fes_equal(left: object, right: object) -> bool:
    return _canonical_bytes(_canonical_fes_value(left)) == _canonical_bytes(
        _canonical_fes_value(right)
    )


def _fes_replacement(current: object, replacement: object, path: str) -> object:
    if isinstance(current, float):
        exact = _exact_decimal(replacement, f"historical_patch.{path}")
        converted = float(exact)
        if not converted == converted or Decimal(str(converted)) != exact:
            raise HistoricalEnvelopeError(
                f"historical_patch.{path} is not exactly representable by FES numeric storage"
            )
        return converted
    if isinstance(current, dict) and isinstance(replacement, dict):
        if current.keys() != replacement.keys():
            return copy.deepcopy(replacement)
        return {
            key: _fes_replacement(current[key], replacement[key], f"{path}.{key}")
            for key in current
        }
    if isinstance(current, list) and isinstance(replacement, list):
        if len(current) != len(replacement):
            return copy.deepcopy(replacement)
        return [
            _fes_replacement(left, right, f"{path}[{index}]")
            for index, (left, right) in enumerate(zip(current, replacement, strict=True))
        ]
    return copy.deepcopy(replacement)


def _register_variation_path(
    occupied: list[tuple[str, tuple[str, ...]]],
    domain: str,
    pointer: str,
) -> None:
    tokens = _pointer_tokens(pointer)
    for prior_domain, prior_tokens in occupied:
        shared = min(len(tokens), len(prior_tokens))
        if prior_domain == domain and tokens[:shared] == prior_tokens[:shared]:
            raise HistoricalEnvelopeError(
                "variation targets must not overlap by parent/child path"
            )
    occupied.append((domain, tokens))


def _patch_controller(
    profile: HistoricalControllerProfile,
    pointer: str,
    before: object,
    after: object,
) -> HistoricalControllerProfile:
    tokens = _pointer_tokens(pointer)
    if len(tokens) != 4 or tokens[0] != "stages" or tokens[2] != "parameters":
        raise HistoricalEnvelopeError(
            "controller variation target must be /stages/{stage_id}/parameters/{name}"
        )
    stage_id, parameter_name = tokens[1], tokens[3]
    found = False
    stages = []
    for stage in profile.stages:
        if stage.stage_id != stage_id:
            stages.append(stage)
            continue
        parameters = []
        for parameter in stage.parameters:
            if parameter.name != parameter_name:
                parameters.append(parameter)
                continue
            value = parameter.to_dict()["value"]
            if not _canonical_equal(value, before):
                raise HistoricalEnvelopeError("variation before value does not match")
            if isinstance(after, (bool, float)) or not isinstance(
                after, (Decimal, int, str)
            ):
                raise HistoricalEnvelopeError(
                    "controller parameter variation must be an exact scalar"
                )
            parameters.append(replace(parameter, value=after))
            found = True
        stages.append(replace(stage, parameters=tuple(parameters)))
    if not found:
        raise HistoricalEnvelopeError(f"variation target {pointer!r} is unknown")
    return replace(profile, stages=tuple(stages))


def apply_historical_variations(
    envelope: HistoricalExperimentEnvelope,
    patches: Sequence[HistoricalVariationPatch],
    *,
    new_version: str,
) -> HistoricalExperimentEnvelope:
    """Apply exact hash/before-value patches and return a new immutable envelope."""
    _text(new_version, "historical variation new_version", maximum=255)
    if new_version == envelope.version:
        raise HistoricalEnvelopeError("historical variation version must change")
    if not patches:
        raise HistoricalEnvelopeError("historical variation patches must not be empty")
    base_sha256 = envelope.sha256()
    targets: set[tuple[str, str]] = set()
    occupied_paths: list[tuple[str, tuple[str, ...]]] = []
    options = list(envelope.options)
    fes = None if envelope.fes is None else copy.deepcopy(envelope.fes)
    controller = envelope.controller_profile
    for patch in patches:
        if patch.base_envelope_sha256 != base_sha256:
            raise HistoricalEnvelopeError("variation base envelope hash does not match")
        key = (patch.target_kind, patch.target)
        if key in targets:
            raise HistoricalEnvelopeError("variation targets must be unique")
        targets.add(key)
        if patch.target_kind == "option":
            index = next(
                (i for i, item in enumerate(options) if item.option_id == patch.target),
                None,
            )
            if index is None:
                raise HistoricalEnvelopeError(
                    f"variation target option {patch.target!r} is unknown"
                )
            current = options[index]
            if current.target is not None:
                _register_variation_path(occupied_paths, "fes", current.target)
            current_value = _option_value_dict(
                current.effective_value, current.value_kind
            )
            if not _canonical_equal(current_value, patch.before_canonical_value):
                raise HistoricalEnvelopeError("variation before value does not match")
            options[index] = replace(
                current,
                requested_value=patch.after_canonical_value,
                effective_value=patch.after_canonical_value,
                origin="invocation",
                application="applied",
            )
            if current.target is not None:
                if fes is None:
                    raise HistoricalEnvelopeError(
                        "option variation targets FES but envelope has no FES"
                    )
                before_fes = _pointer_get(fes, current.target)
                if not _canonical_fes_equal(before_fes, patch.before_canonical_value):
                    raise HistoricalEnvelopeError(
                        "variation before value does not match FES target"
                    )
                _pointer_set(
                    fes,
                    current.target,
                    _fes_replacement(
                        before_fes,
                        patch.after_canonical_value,
                        current.target,
                    ),
                )
        elif patch.target_kind == "fes":
            _register_variation_path(occupied_paths, "fes", patch.target)
            if fes is None:
                raise HistoricalEnvelopeError("FES variation requires existing FES")
            current_value = _pointer_get(fes, patch.target)
            if not _canonical_fes_equal(current_value, patch.before_canonical_value):
                raise HistoricalEnvelopeError("variation before value does not match")
            _pointer_set(
                fes,
                patch.target,
                _fes_replacement(
                    current_value,
                    patch.after_canonical_value,
                    patch.target,
                ),
            )
        else:
            _register_variation_path(occupied_paths, "controller", patch.target)
            if controller is None:
                raise HistoricalEnvelopeError(
                    "controller variation requires controller profile"
                )
            controller = _patch_controller(
                controller,
                patch.target,
                patch.before_canonical_value,
                patch.after_canonical_value,
            )
    expected_fes_sha256 = None if fes is None else validate_experiment_spec(fes).sha256()
    return HistoricalExperimentEnvelope(
        envelope_id=envelope.envelope_id,
        version=new_version,
        source=envelope.source,
        selector=envelope.selector,
        invocation=envelope.invocation,
        options=tuple(options),
        controller_profile=controller,
        fes=fes,
        expected_fes_sha256=expected_fes_sha256,
        source_artifacts=envelope.source_artifacts,
        missing_requirements=envelope.missing_requirements,
        lineage=HistoricalLineage(
            envelope.envelope_id, envelope.version, base_sha256, "variation"
        ),
        variation_patches=tuple(patches),
    )


@dataclass(frozen=True)
class StaticExtractionLimits:
    max_source_bytes: int = 2_000_000
    max_ast_nodes: int = 200_000
    max_ast_depth: int = 256
    max_options: int = 1_000
    max_config_entries: int = 20_000
    max_dispositions: int = 5_000
    max_string_length: int = 65_536

    def __post_init__(self) -> None:
        for name in (
            "max_source_bytes",
            "max_ast_nodes",
            "max_ast_depth",
            "max_options",
            "max_config_entries",
            "max_dispositions",
            "max_string_length",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise HistoricalEnvelopeError(
                    f"static extraction {name} must be positive integer"
                )


_DEFAULT_EXTRACTION_LIMITS = StaticExtractionLimits()


@dataclass(frozen=True)
class StaticExtractionDisposition:
    code: str
    line: int
    column: int
    detail: str

    def __post_init__(self) -> None:
        _text(self.code, "static disposition code", maximum=255)
        _non_negative_integer(self.line, "static disposition line")
        _non_negative_integer(self.column, "static disposition column")
        _text(self.detail, "static disposition detail")

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "line": self.line,
            "column": self.column,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class StaticOptionDeclaration:
    legacy_name: str
    type_name: str | None
    action: str | None
    nargs: int | str | None
    default_value: object
    choices: tuple[object, ...]
    line: int

    def __post_init__(self) -> None:
        name = _text(self.legacy_name, "static option legacy_name", maximum=255)
        if not name.startswith("-"):
            raise HistoricalEnvelopeError("static option name must start with dash")
        if self.type_name is not None:
            _text(self.type_name, "static option type_name", maximum=64)
        if self.action is not None:
            _text(self.action, "static option action", maximum=64)
        if self.nargs is not None and not isinstance(self.nargs, (int, str)):
            raise HistoricalEnvelopeError("static option nargs is invalid")
        object.__setattr__(
            self,
            "default_value",
            _canonical_general_value(self.default_value, "static option default"),
        )
        object.__setattr__(
            self,
            "choices",
            tuple(
                _canonical_general_value(item, "static option choice")
                for item in self.choices
            ),
        )
        _non_negative_integer(self.line, "static option line")

    def to_dict(self) -> dict[str, object]:
        return {
            "legacy_name": self.legacy_name,
            "type_name": self.type_name,
            "action": self.action,
            "nargs": self.nargs,
            "default_value": _canonical_general_value(self.default_value),
            "choices": [
                _canonical_general_value(item) for item in self.choices
            ],
            "line": self.line,
        }


@dataclass(frozen=True)
class StaticConfigTable:
    name: str
    entry_count: int
    value_sha256: str
    line: int

    def __post_init__(self) -> None:
        _text(self.name, "static config table name", maximum=255)
        _non_negative_integer(self.entry_count, "static config table entry_count")
        _digest(self.value_sha256, "static config table value_sha256")
        _non_negative_integer(self.line, "static config table line")

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "entry_count": self.entry_count,
            "value_sha256": self.value_sha256,
            "line": self.line,
        }


@dataclass(frozen=True)
class StaticExtractionReceipt:
    extractor_id: str
    extractor_version: str
    source_sha256: str
    source_byte_length: int
    ast_node_count: int
    option_count: int
    config_table_count: int
    config_entry_count: int
    disposition_count: int
    graph_sha256: str

    def __post_init__(self) -> None:
        _namespaced(self.extractor_id, "static receipt extractor_id")
        _text(self.extractor_version, "static receipt extractor_version", maximum=255)
        _digest(self.source_sha256, "static receipt source_sha256")
        _digest(self.graph_sha256, "static receipt graph_sha256")
        for name in (
            "source_byte_length",
            "ast_node_count",
            "option_count",
            "config_table_count",
            "config_entry_count",
            "disposition_count",
        ):
            _non_negative_integer(getattr(self, name), f"static receipt {name}")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "extractor_id": self.extractor_id,
            "extractor_version": self.extractor_version,
            "source_sha256": self.source_sha256,
            "source_byte_length": self.source_byte_length,
            "ast_node_count": self.ast_node_count,
            "option_count": self.option_count,
            "config_table_count": self.config_table_count,
            "config_entry_count": self.config_entry_count,
            "disposition_count": self.disposition_count,
            "graph_sha256": self.graph_sha256,
        }


@dataclass(frozen=True)
class StaticExtractionResult:
    options: tuple[StaticOptionDeclaration, ...]
    config_tables: tuple[StaticConfigTable, ...]
    dispositions: tuple[StaticExtractionDisposition, ...]
    receipt: StaticExtractionReceipt


def _ast_depth(node: ast.AST) -> int:
    maximum = 0
    pending: list[tuple[ast.AST, int]] = [(node, 1)]
    while pending:
        current, depth = pending.pop()
        maximum = max(maximum, depth)
        pending.extend((child, depth + 1) for child in ast.iter_child_nodes(current))
    return maximum


def _literal(
    node: ast.AST,
    limits: StaticExtractionLimits,
    source_text: str,
    *,
    depth: int = 0,
) -> object:
    if depth > limits.max_ast_depth:
        raise HistoricalEnvelopeError("static literal exceeds maximum nesting depth")
    if isinstance(node, ast.Constant):
        value = node.value
        if value is None or isinstance(value, (bool, int, str)):
            if isinstance(value, str) and len(value) > limits.max_string_length:
                raise HistoricalEnvelopeError("static literal exceeds maximum string length")
            return value
        if isinstance(value, float):
            lexeme = ast.get_source_segment(source_text, node)
            if lexeme is None:
                raise HistoricalEnvelopeError("static decimal source lexeme is unavailable")
            return _exact_decimal(lexeme.replace("_", ""), "static decimal literal")
        raise HistoricalEnvelopeError("static literal contains unsupported constant")
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        operand = _literal(node.operand, limits, source_text, depth=depth + 1)
        if isinstance(operand, bool) or not isinstance(operand, (int, Decimal)):
            raise HistoricalEnvelopeError("static unary literal must be numeric")
        if isinstance(node.op, ast.USub):
            return -operand
        return operand
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        if len(node.elts) > limits.max_config_entries:
            raise HistoricalEnvelopeError("static literal exceeds maximum collection length")
        return [
            _literal(item, limits, source_text, depth=depth + 1)
            for item in node.elts
        ]
    if isinstance(node, ast.Dict):
        if len(node.keys) > limits.max_config_entries:
            raise HistoricalEnvelopeError("static literal exceeds maximum collection length")
        result: dict[str, object] = {}
        for raw_key, raw_value in zip(node.keys, node.values, strict=True):
            if raw_key is None:
                raise HistoricalEnvelopeError("static config dictionary unpack is unsupported")
            key = _literal(raw_key, limits, source_text, depth=depth + 1)
            if not isinstance(key, str):
                raise HistoricalEnvelopeError("static config object keys must be strings")
            result[key] = _literal(
                raw_value, limits, source_text, depth=depth + 1
            )
        return result
    raise ValueError("node is not a bounded static literal")


def _keyword(call: ast.Call, name: str) -> ast.AST | None:
    return next((item.value for item in call.keywords if item.arg == name), None)


def _name(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    return None


def extract_static_python_experiment(
    source_bytes: bytes,
    source: HistoricalSourceAuthority,
    limits: StaticExtractionLimits = _DEFAULT_EXTRACTION_LIMITS,
) -> StaticExtractionResult:
    """Extract bounded literal declarations without importing or executing source."""
    if not isinstance(source_bytes, bytes):
        raise HistoricalEnvelopeError("historical source bytes must be bytes")
    if (
        source.extractor_id != STATIC_PYTHON_EXTRACTOR_ID
        or source.extractor_version != STATIC_PYTHON_EXTRACTOR_VERSION
    ):
        raise HistoricalEnvelopeError("historical source extractor profile is unsupported")
    if len(source_bytes) > limits.max_source_bytes:
        raise HistoricalEnvelopeError("historical source exceeds maximum source bytes")
    if len(source_bytes) != source.byte_length or (
        hashlib.sha256(source_bytes).hexdigest() != source.sha256
    ):
        raise HistoricalEnvelopeError("historical source bytes do not match authority")
    try:
        source_text = source_bytes.decode("utf-8")
    except UnicodeDecodeError as error:
        raise HistoricalEnvelopeError("historical source must be UTF-8") from error
    try:
        tree = ast.parse(source_text, filename=source.logical_path)
    except SyntaxError as error:
        raise HistoricalEnvelopeError("historical source is invalid Python syntax") from error
    nodes = tuple(ast.walk(tree))
    if len(nodes) > limits.max_ast_nodes:
        raise HistoricalEnvelopeError("historical source exceeds maximum AST nodes")
    if _ast_depth(tree) > limits.max_ast_depth:
        raise HistoricalEnvelopeError("historical source exceeds maximum AST depth")

    options: list[StaticOptionDeclaration] = []
    dispositions: list[StaticExtractionDisposition] = []
    for node in nodes:
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "add_argument"
            and node.args
        ):
            continue
        if len(options) >= limits.max_options:
            raise HistoricalEnvelopeError("historical source exceeds maximum options")
        try:
            legacy_name = _literal(node.args[0], limits, source_text)
        except (ValueError, HistoricalEnvelopeError):
            dispositions.append(
                StaticExtractionDisposition(
                    "DYNAMIC_OPTION_NAME",
                    node.lineno,
                    node.col_offset,
                    "add_argument option name is not static literal",
                )
            )
            continue
        if not isinstance(legacy_name, str):
            dispositions.append(
                StaticExtractionDisposition(
                    "INVALID_OPTION_NAME",
                    node.lineno,
                    node.col_offset,
                    "add_argument option name is not text",
                )
            )
            continue
        default_node = _keyword(node, "default")
        default: object = None
        if default_node is not None:
            try:
                default = _literal(default_node, limits, source_text)
            except (ValueError, HistoricalEnvelopeError):
                dispositions.append(
                    StaticExtractionDisposition(
                        "DYNAMIC_OPTION_DEFAULT",
                        getattr(default_node, "lineno", 0),
                        getattr(default_node, "col_offset", 0),
                        f"default for {legacy_name} is not static literal",
                    )
                )
        choices_node = _keyword(node, "choices")
        choices: tuple[object, ...] = ()
        if choices_node is not None:
            try:
                raw_choices = _literal(choices_node, limits, source_text)
                if not isinstance(raw_choices, list):
                    raise HistoricalEnvelopeError("option choices must be literal collection")
                choices = tuple(raw_choices)
            except (ValueError, HistoricalEnvelopeError):
                dispositions.append(
                    StaticExtractionDisposition(
                        "DYNAMIC_OPTION_CHOICES",
                        getattr(choices_node, "lineno", 0),
                        getattr(choices_node, "col_offset", 0),
                        f"choices for {legacy_name} are not static literals",
                    )
                )
        action_node = _keyword(node, "action")
        action = None
        if action_node is not None:
            try:
                raw_action = _literal(action_node, limits, source_text)
                action = raw_action if isinstance(raw_action, str) else None
            except (ValueError, HistoricalEnvelopeError):
                dispositions.append(
                    StaticExtractionDisposition(
                        "DYNAMIC_OPTION_ACTION",
                        getattr(action_node, "lineno", 0),
                        getattr(action_node, "col_offset", 0),
                        f"action for {legacy_name} is not static literal",
                    )
                )
        if default_node is None and action == "store_true":
            default = False
        elif default_node is None and action == "store_false":
            default = True
        nargs_node = _keyword(node, "nargs")
        nargs: int | str | None = None
        if nargs_node is not None:
            try:
                raw_nargs = _literal(nargs_node, limits, source_text)
                nargs = raw_nargs if isinstance(raw_nargs, (int, str)) else None
            except (ValueError, HistoricalEnvelopeError):
                dispositions.append(
                    StaticExtractionDisposition(
                        "DYNAMIC_OPTION_NARGS",
                        getattr(nargs_node, "lineno", 0),
                        getattr(nargs_node, "col_offset", 0),
                        f"nargs for {legacy_name} is not static literal",
                    )
                )
        options.append(
            StaticOptionDeclaration(
                legacy_name=legacy_name,
                type_name=_name(_keyword(node, "type")),
                action=action,
                nargs=nargs,
                default_value=default,
                choices=choices,
                line=node.lineno,
            )
        )

    config_tables: list[StaticConfigTable] = []
    config_entries = 0
    for statement in tree.body:
        if not isinstance(statement, (ast.Assign, ast.AnnAssign)):
            continue
        targets = statement.targets if isinstance(statement, ast.Assign) else [statement.target]
        value_node = statement.value
        if value_node is None:
            continue
        for target in targets:
            if not isinstance(target, ast.Name) or "CONFIG" not in target.id.upper():
                continue
            try:
                value = _literal(value_node, limits, source_text)
            except (ValueError, HistoricalEnvelopeError):
                dispositions.append(
                    StaticExtractionDisposition(
                        "DYNAMIC_CONFIG_TABLE",
                        statement.lineno,
                        statement.col_offset,
                        f"config table {target.id} is not static literal",
                    )
                )
                continue
            if not isinstance(value, (list, dict)):
                continue
            count = len(value)
            config_entries += count
            if config_entries > limits.max_config_entries:
                raise HistoricalEnvelopeError(
                    "historical source exceeds maximum config entries"
                )
            config_tables.append(
                StaticConfigTable(
                    target.id,
                    count,
                    _sha256(_canonical_general_value(value)),
                    statement.lineno,
                )
            )

    if len(dispositions) > limits.max_dispositions:
        raise HistoricalEnvelopeError(
            "historical source exceeds maximum extraction dispositions"
        )

    graph = {
        "options": [item.to_dict() for item in options],
        "config_tables": [item.to_dict() for item in config_tables],
        "dispositions": [item.to_dict() for item in dispositions],
    }
    receipt = StaticExtractionReceipt(
        source.extractor_id,
        source.extractor_version,
        source.sha256,
        len(source_bytes),
        len(nodes),
        len(options),
        len(config_tables),
        config_entries,
        len(dispositions),
        _sha256(graph),
    )
    return StaticExtractionResult(
        tuple(options), tuple(config_tables), tuple(dispositions), receipt
    )
