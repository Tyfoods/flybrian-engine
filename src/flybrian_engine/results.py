"""Validation for portable standardized scientific results."""

from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import dataclass
from typing import Any

JsonObject = dict[str, Any]
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class ResultsValidationError(ValueError):
    """A standardized-results document violates the public schema."""


def _object(value: Any, path: str) -> JsonObject:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ResultsValidationError(f"{path} must be an object with string keys")
    return value


def _array(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise ResultsValidationError(f"{path} must be an array")
    return value


def _string(value: Any, path: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ResultsValidationError(
            f"{path} must be a non-empty string of at most {maximum} characters"
        )
    return value


def _identifier(value: Any, path: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ResultsValidationError(f"{path} must be a safe identifier")
    return value


def _number(value: Any, path: str, *, non_negative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise ResultsValidationError(f"{path} must be a finite number")
    numeric = float(value)
    if non_negative and numeric < 0:
        raise ResultsValidationError(f"{path} must be non-negative")
    return numeric


def _integer(value: Any, path: str, *, non_negative: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ResultsValidationError(f"{path} must be an integer")
    if non_negative and value < 0:
        raise ResultsValidationError(f"{path} must be non-negative")
    return value


@dataclass(frozen=True)
class StandardizedResults:
    """Validated immutable view of standardized-results schema 1.0."""

    value: JsonObject

    def to_json(self) -> str:
        return json.dumps(
            self.value,
            indent=2,
            sort_keys=True,
            allow_nan=False,
        ) + "\n"


def validate_standardized_results(value: Any) -> StandardizedResults:
    root = _object(value, "results")
    if root.get("schema_version") != "1.0":
        raise ResultsValidationError("schema_version must equal '1.0'")
    _identifier(root.get("run_id"), "run_id")
    for key in ("engine_version", "backend_id", "backend_version"):
        _string(root.get(key), key, maximum=128)
    experiment_sha256 = root.get("experiment_sha256")
    if not isinstance(experiment_sha256, str) or _SHA256.fullmatch(experiment_sha256) is None:
        raise ResultsValidationError("experiment_sha256 must be a lower-case SHA-256")

    simulation = _object(root.get("simulation"), "simulation")
    duration = _number(
        simulation.get("duration_seconds"),
        "simulation.duration_seconds",
        non_negative=True,
    )
    time_step = _number(
        simulation.get("time_step_seconds"),
        "simulation.time_step_seconds",
        non_negative=True,
    )
    if duration <= 0 or time_step <= 0 or time_step > duration:
        raise ResultsValidationError(
            "simulation duration/time step must be positive and time step must not exceed duration"
        )
    _integer(simulation.get("random_seed"), "simulation.random_seed", non_negative=True)

    raw_neurons = _array(root.get("neurons"), "neurons")
    neurons: list[JsonObject] = []
    neuron_ids: set[int] = set()
    for index, raw_neuron in enumerate(raw_neurons):
        neuron = _object(raw_neuron, f"neurons[{index}]")
        neuron_id = _integer(neuron.get("neuron_id"), f"neurons[{index}].neuron_id")
        if neuron_id in neuron_ids:
            raise ResultsValidationError("neurons must have unique neuron IDs")
        neuron_ids.add(neuron_id)
        _identifier(neuron.get("model_id"), f"neurons[{index}].model_id")
        _identifier(neuron.get("family"), f"neurons[{index}].family")
        neurons.append(neuron)
    if [neuron["neuron_id"] for neuron in neurons] != sorted(neuron_ids):
        raise ResultsValidationError("neurons must be ordered by neuron_id")

    network = _object(root.get("network"), "network")
    declared_neurons = _integer(network.get("neurons"), "network.neurons", non_negative=True)
    _integer(network.get("connections"), "network.connections", non_negative=True)
    if declared_neurons != len(neuron_ids):
        raise ResultsValidationError("network.neurons must equal the neuron record count")

    raw_spikes = _array(root.get("spikes"), "spikes")
    spike_identity: list[tuple[float, int]] = []
    for index, raw_spike in enumerate(raw_spikes):
        spike = _object(raw_spike, f"spikes[{index}]")
        neuron_id = _integer(spike.get("neuron_id"), f"spikes[{index}].neuron_id")
        if neuron_id not in neuron_ids:
            raise ResultsValidationError(f"spikes[{index}].neuron_id is unknown")
        time = _number(
            spike.get("time_seconds"),
            f"spikes[{index}].time_seconds",
            non_negative=True,
        )
        if time > duration:
            raise ResultsValidationError(f"spikes[{index}].time_seconds exceeds duration")
        spike_identity.append((time, neuron_id))
    if spike_identity != sorted(spike_identity):
        raise ResultsValidationError("spikes must be ordered by time_seconds then neuron_id")

    raw_series = _array(root.get("series"), "series")
    series_identity: list[tuple[int, str, str]] = []
    for index, raw_item in enumerate(raw_series):
        item = _object(raw_item, f"series[{index}]")
        neuron_id = _integer(item.get("neuron_id"), f"series[{index}].neuron_id")
        if neuron_id not in neuron_ids:
            raise ResultsValidationError(f"series[{index}].neuron_id is unknown")
        compartment = item.get("compartment_id")
        if compartment is not None:
            compartment = _identifier(compartment, f"series[{index}].compartment_id")
        variable = _identifier(item.get("variable"), f"series[{index}].variable")
        _string(item.get("unit"), f"series[{index}].unit", maximum=64)
        times = [
            _number(sample, f"series[{index}].times_seconds sample", non_negative=True)
            for sample in _array(item.get("times_seconds"), f"series[{index}].times_seconds")
        ]
        values = [
            _number(sample, f"series[{index}].values sample")
            for sample in _array(item.get("values"), f"series[{index}].values")
        ]
        if not times or len(times) != len(values):
            raise ResultsValidationError(
                f"series[{index}] times and values must be non-empty and equal length"
            )
        if times != sorted(times) or times[-1] > duration:
            raise ResultsValidationError(
                f"series[{index}].times_seconds must be ordered within duration"
            )
        series_identity.append((neuron_id, compartment or "", variable))
    if len(series_identity) != len(set(series_identity)):
        raise ResultsValidationError("series identities must be unique")
    if series_identity != sorted(series_identity):
        raise ResultsValidationError("series must be ordered by neuron, compartment, variable")

    for index, warning in enumerate(_array(root.get("warnings"), "warnings")):
        _string(warning, f"warnings[{index}]")
    return StandardizedResults(copy.deepcopy(root))
