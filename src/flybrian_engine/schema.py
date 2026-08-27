"""FES 1.0 validation and canonical serialization."""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from dataclasses import dataclass
from typing import Any

from packaging.specifiers import InvalidSpecifier, SpecifierSet

JsonObject = dict[str, Any]


class ValidationError(ValueError):
    """One or more experiment fields violate the public contract."""


def _object(value: Any, path: str) -> JsonObject:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValidationError(f"{path} must be an object with string keys")
    return value


def _nonempty_string(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{path} must be a non-empty string")
    return value


def _finite_number(value: Any, path: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ValidationError(f"{path} must be a finite number")
    numeric = float(value)
    if positive and numeric <= 0:
        raise ValidationError(f"{path} must be greater than zero")
    return numeric


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValidationError(f"{path} must be an array")
    return value


def _validate_parameter(value: Any, path: str, *, allow_scalar: bool = False) -> None:
    if allow_scalar and isinstance(value, int | float) and not isinstance(value, bool):
        _finite_number(value, path)
        return
    parameter = _object(value, path)
    _nonempty_string(parameter.get("unit"), f"{path}.unit")
    has_value = "value" in parameter
    has_distribution = "distribution" in parameter
    if has_value == has_distribution:
        raise ValidationError(f"{path} must define exactly one of value or distribution")
    if has_value:
        _finite_number(parameter["value"], f"{path}.value")
        return
    distribution = _object(parameter["distribution"], f"{path}.distribution")
    kind = _nonempty_string(distribution.get("kind"), f"{path}.distribution.kind")
    if kind == "normal":
        _finite_number(distribution.get("mean"), f"{path}.distribution.mean")
        deviation = _finite_number(
            distribution.get("standard_deviation"),
            f"{path}.distribution.standard_deviation",
        )
        if deviation < 0:
            raise ValidationError(
                f"{path}.distribution.standard_deviation must be non-negative"
            )
    elif kind in {"uniform", "log_uniform"}:
        minimum = _finite_number(distribution.get("minimum"), f"{path}.distribution.minimum")
        maximum = _finite_number(distribution.get("maximum"), f"{path}.distribution.maximum")
        if maximum < minimum:
            raise ValidationError(f"{path}.distribution.maximum must be at least minimum")
        if kind == "log_uniform" and minimum <= 0:
            raise ValidationError(f"{path}.distribution.minimum must be greater than zero")
    else:
        raise ValidationError(f"{path}.distribution.kind is unsupported")


def _validate_parameter_map(value: Any, path: str, *, allow_scalar: bool = False) -> None:
    parameters = _object(value, path)
    for name, parameter in parameters.items():
        _nonempty_string(name, f"{path} key")
        _validate_parameter(parameter, f"{path}.{name}", allow_scalar=allow_scalar)


def _validate_neurons(value: Any) -> set[int]:
    families = _object(value, "neurons")
    if not families:
        raise ValidationError("neurons must contain at least one model family")
    seen_ids: set[int] = set()
    for family_name, family_value in families.items():
        _nonempty_string(family_name, "neurons family")
        family = _object(family_value, f"neurons.{family_name}")
        if not family:
            raise ValidationError(f"neurons.{family_name} must not be empty")
        for key, raw_neuron in family.items():
            neuron = _object(raw_neuron, f"neurons.{family_name}.{key}")
            neuron_id = neuron.get("neuron_id")
            if isinstance(neuron_id, bool) or not isinstance(neuron_id, int) or neuron_id < 0:
                raise ValidationError(
                    f"neurons.{family_name}.{key}.neuron_id must be a non-negative integer"
                )
            if str(neuron_id) != key:
                raise ValidationError(f"neurons.{family_name}.{key}.neuron_id must match its key")
            if neuron_id in seen_ids:
                raise ValidationError(f"neuron_id {neuron_id} occurs in more than one model family")
            seen_ids.add(neuron_id)
            if neuron.get("model_type") != family_name:
                raise ValidationError(
                    f"neurons.{family_name}.{key}.model_type must match its family"
                )
            for field in ("poisson_inputs", "external_currents"):
                _array(neuron.get(field), f"neurons.{family_name}.{key}.{field}")
            for field in ("record_spikes", "record_variables"):
                if not isinstance(neuron.get(field), bool):
                    raise ValidationError(
                        f"neurons.{family_name}.{key}.{field} must be a boolean"
                    )
            if "parameter_overrides" in neuron:
                _validate_parameter_map(
                    neuron["parameter_overrides"],
                    f"neurons.{family_name}.{key}.parameter_overrides",
                    allow_scalar=True,
                )
            if "compartments" in neuron:
                compartments = _object(
                    neuron["compartments"],
                    f"neurons.{family_name}.{key}.compartments",
                )
                for compartment_key, raw_compartment in compartments.items():
                    if not compartment_key.isdigit():
                        raise ValidationError(
                            f"neurons.{family_name}.{key}.compartments keys must be integers"
                        )
                    compartment = _object(
                        raw_compartment,
                        f"neurons.{family_name}.{key}.compartments.{compartment_key}",
                    )
                    for field in ("poisson_inputs", "external_currents"):
                        if field in compartment:
                            _array(
                                compartment[field],
                                f"neurons.{family_name}.{key}.compartments.{compartment_key}.{field}",
                            )
                    for field in ("record_spikes", "record_variables"):
                        if field in compartment and not isinstance(compartment[field], bool):
                            raise ValidationError(
                                f"neurons.{family_name}.{key}.compartments."
                                f"{compartment_key}.{field} must be a boolean"
                            )
    return seen_ids


def _validate_neuron_models(value: Any, neuron_groups: JsonObject) -> None:
    models = _object(value, "neuron_models")
    if set(models) != set(neuron_groups):
        raise ValidationError("neuron_models keys must exactly match neurons model groups")
    for model_id, raw_model in models.items():
        model = _object(raw_model, f"neuron_models.{model_id}")
        family = _nonempty_string(model.get("family"), f"neuron_models.{model_id}.family")
        _validate_parameter_map(model.get("parameters", {}), f"neuron_models.{model_id}.parameters")
        if family == "compartmental":
            neurons = _object(neuron_groups[model_id], f"neurons.{model_id}")
            for neuron_id, raw_neuron in neurons.items():
                neuron = _object(raw_neuron, f"neurons.{model_id}.{neuron_id}")
                compartments = _object(
                    neuron.get("compartments"),
                    f"neurons.{model_id}.{neuron_id}.compartments",
                )
                if not compartments:
                    raise ValidationError(
                        f"neurons.{model_id}.{neuron_id}.compartments must not be empty "
                        "for a compartmental model"
                    )


def _validate_weighted_links(
    value: Any,
    path: str,
    *,
    source_key: str,
    target_key: str,
    neuron_ids: set[int] | None = None,
    muscle_ids: set[str] | None = None,
) -> None:
    links = _array(value, path)
    if not links:
        raise ValidationError(f"{path} must not be empty")
    for index, raw_link in enumerate(links):
        link_path = f"{path}[{index}]"
        link = _object(raw_link, link_path)
        source = link.get(source_key)
        target = link.get(target_key)
        if source_key == "neuron_id":
            invalid_neuron = (
                isinstance(source, bool)
                or not isinstance(source, int)
                or source not in (neuron_ids or set())
            )
            if invalid_neuron:
                raise ValidationError(
                    f"{link_path}.{source_key} references unknown neuron {source!r}"
                )
        else:
            _nonempty_string(source, f"{link_path}.{source_key}")
            if muscle_ids is not None and source not in muscle_ids:
                raise ValidationError(f"{link_path} references unknown muscle {source!r}")
        _nonempty_string(target, f"{link_path}.{target_key}")
        if target_key == "muscle_id" and target not in (muscle_ids or set()):
            raise ValidationError(f"{link_path} references unknown muscle {target!r}")
        _finite_number(link.get("weight"), f"{link_path}.weight")


def _validate_embodiment(value: Any, neuron_ids: set[int]) -> None:
    config = _object(value, "embodied_config")
    if "enabled" in config and not isinstance(config["enabled"], bool):
        raise ValidationError("embodied_config.enabled must be a boolean")
    if "mapping_id" in config:
        _nonempty_string(config["mapping_id"], "embodied_config.mapping_id")
    if "firing_rate_window_ms" in config:
        _finite_number(
            config["firing_rate_window_ms"],
            "embodied_config.firing_rate_window_ms",
            positive=True,
        )
    mode = config.get("drive_mode")
    if mode is None:
        return
    if mode not in {"none", "direct_actuator", "muscle_mediated"}:
        raise ValidationError("embodied_config.drive_mode is unsupported")
    if config.get("enabled") is not True and mode != "none":
        raise ValidationError("embodied_config.enabled must be true when drive_mode is active")
    if mode == "direct_actuator":
        direct = _object(config.get("direct_actuator"), "embodied_config.direct_actuator")
        _validate_weighted_links(
            direct.get("links"),
            "embodied_config.direct_actuator.links",
            source_key="neuron_id",
            target_key="actuator_id",
            neuron_ids=neuron_ids,
        )
    if mode == "muscle_mediated":
        mediated = _object(
            config.get("muscle_mediated"),
            "embodied_config.muscle_mediated",
        )
        muscles = _object(
            mediated.get("muscles"),
            "embodied_config.muscle_mediated.muscles",
        )
        if not muscles:
            raise ValidationError("embodied_config.muscle_mediated.muscles must not be empty")
        muscle_ids = set(muscles)
        for muscle_id, raw_muscle in muscles.items():
            _nonempty_string(muscle_id, "embodied_config.muscle_mediated.muscles key")
            muscle = _object(
                raw_muscle,
                f"embodied_config.muscle_mediated.muscles.{muscle_id}",
            )
            _nonempty_string(
                muscle.get("model"),
                f"embodied_config.muscle_mediated.muscles.{muscle_id}.model",
            )
            _validate_parameter_map(
                muscle.get("parameters", {}),
                f"embodied_config.muscle_mediated.muscles.{muscle_id}.parameters",
            )
        _validate_weighted_links(
            mediated.get("neuron_to_muscle"),
            "embodied_config.muscle_mediated.neuron_to_muscle",
            source_key="neuron_id",
            target_key="muscle_id",
            neuron_ids=neuron_ids,
            muscle_ids=muscle_ids,
        )
        _validate_weighted_links(
            mediated.get("muscle_to_actuator"),
            "embodied_config.muscle_mediated.muscle_to_actuator",
            source_key="muscle_id",
            target_key="actuator_id",
            muscle_ids=muscle_ids,
        )


def _validate_execution(value: Any) -> None:
    execution = _object(value, "execution")
    _nonempty_string(execution.get("backend_id"), "execution.backend_id")
    for key in ("backend_version", "engine_version"):
        if key not in execution:
            continue
        constraint = _nonempty_string(execution[key], f"execution.{key}")
        try:
            SpecifierSet(constraint)
        except InvalidSpecifier as error:
            raise ValidationError(f"execution.{key} must be a valid version constraint") from error


def _validate_extensions(value: Any) -> None:
    extensions = _object(value, "extensions")
    namespace = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*(?:[.:][A-Za-z0-9][A-Za-z0-9_.:-]*)+$")
    for owner in extensions:
        if namespace.fullmatch(owner) is None:
            raise ValidationError(f"extensions.{owner} must use a namespaced owner")


def _validate_artifact_requests(value: Any) -> None:
    requests = _array(value, "artifact_requests")
    normalized = [_nonempty_string(item, "artifact_requests item") for item in requests]
    if len(normalized) != len(set(normalized)):
        raise ValidationError("artifact_requests must not contain duplicates")


def _validate_resource_hints(value: Any) -> None:
    hints = _object(value, "resource_hints")
    for key in ("cpu_cores", "memory_gib"):
        if key in hints:
            _finite_number(hints[key], f"resource_hints.{key}", positive=True)
    if "gpu_count" in hints:
        gpu_count = hints["gpu_count"]
        if isinstance(gpu_count, bool) or not isinstance(gpu_count, int) or gpu_count < 0:
            raise ValidationError("resource_hints.gpu_count must be a non-negative integer")


@dataclass(frozen=True)
class ExperimentSpec:
    """Validated immutable view of a JSON-compatible FES document."""

    value: JsonObject

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @property
    def model_families(self) -> tuple[str, ...]:
        models = self.value.get("neuron_models")
        if isinstance(models, dict):
            return tuple(sorted({str(model["family"]) for model in models.values()}))
        return tuple(sorted(self.value["neurons"]))

    @property
    def embodiment_mode(self) -> str:
        config = self.value.get("embodied_config")
        if not isinstance(config, dict) or config.get("enabled") is not True:
            return "none"
        return str(config.get("drive_mode", "direct_actuator"))

    @property
    def requested_artifact_kinds(self) -> tuple[str, ...]:
        value = self.value.get("artifact_requests", [])
        return tuple(sorted(str(item) for item in value))


def validate_experiment_spec(value: Any) -> ExperimentSpec:
    root = _object(value, "experiment")
    if root.get("spec_version") != "1.0":
        raise ValidationError("spec_version must equal '1.0'")
    metadata = _object(root.get("metadata"), "metadata")
    _nonempty_string(metadata.get("name"), "metadata.name")
    _nonempty_string(root.get("dataset"), "dataset")
    _finite_number(root.get("sim_time_ms"), "sim_time_ms", positive=True)
    seed = root.get("random_seed")
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValidationError("random_seed must be a non-negative integer")
    neuron_ids = _validate_neurons(root.get("neurons"))
    if "neuron_models" in root:
        neurons = _object(root["neurons"], "neurons")
        _validate_neuron_models(root["neuron_models"], neurons)
    if "embodied_config" in root:
        _validate_embodiment(root["embodied_config"], neuron_ids)
    if "execution" in root:
        _validate_execution(root["execution"])
    if "artifact_requests" in root:
        _validate_artifact_requests(root["artifact_requests"])
    if "resource_hints" in root:
        _validate_resource_hints(root["resource_hints"])
    if "extensions" in root:
        _validate_extensions(root["extensions"])
    return ExperimentSpec(copy.deepcopy(root))
