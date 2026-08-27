"""FES 1.0 validation and canonical serialization."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any

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


def _validate_neurons(value: Any) -> None:
    families = _object(value, "neurons")
    if not families:
        raise ValidationError("neurons must contain at least one model family")
    seen_ids: set[int] = set()
    for family_name, family_value in families.items():
        _nonempty_string(family_name, "neurons family")
        family = _object(family_value, f"neurons.{family_name}")
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


def _validate_embodiment(value: Any) -> None:
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
    _validate_neurons(root.get("neurons"))
    if "embodied_config" in root:
        _validate_embodiment(root["embodied_config"])
    return ExperimentSpec(copy.deepcopy(root))
