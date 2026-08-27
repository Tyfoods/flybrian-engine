from __future__ import annotations

import copy
from collections.abc import Callable

import pytest

from flybrian_engine.results import ResultsValidationError, validate_standardized_results


def valid_results() -> dict[str, object]:
    return {
        "backend_id": "brian2",
        "backend_version": "2.10.1",
        "engine_version": "0.1.0",
        "experiment_sha256": "a" * 64,
        "network": {"connections": 0, "neurons": 1},
        "neurons": [{"family": "lif", "model_id": "lif.basic.v1", "neuron_id": 1}],
        "run_id": "run_fixture",
        "schema_version": "1.0",
        "series": [{
            "compartment_id": None,
            "neuron_id": 1,
            "times_seconds": [0.0, 0.001],
            "unit": "V",
            "values": [-0.065, -0.064],
            "variable": "membrane_potential",
        }],
        "simulation": {
            "duration_seconds": 0.01,
            "random_seed": 42,
            "time_step_seconds": 0.001,
        },
        "spikes": [{"neuron_id": 1, "time_seconds": 0.005}],
        "warnings": [],
    }


def test_standardized_results_round_trip_deterministically() -> None:
    value = valid_results()
    validated = validate_standardized_results(value)
    assert validated.value == value
    assert validate_standardized_results(validated.value).to_json() == validated.to_json()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: value["spikes"][0].update(neuron_id=9),
            r"spikes\[0\].neuron_id is unknown",
        ),
        (
            lambda value: value["series"][0]["values"].append(float("nan")),
            "finite number",
        ),
        (
            lambda value: value["series"][0].update(values=[]),
            "non-empty and equal length",
        ),
        (
            lambda value: value["network"].update(neurons=2),
            "network.neurons must equal",
        ),
        (
            lambda value: value.update(experiment_sha256="not-a-hash"),
            "lower-case SHA-256",
        ),
    ],
)
def test_standardized_results_fail_closed_at_ambiguous_fields(
    mutate: Callable[[dict[str, object]], None],
    message: str,
) -> None:
    value = copy.deepcopy(valid_results())
    mutate(value)
    with pytest.raises(ResultsValidationError, match=message):
        validate_standardized_results(value)
