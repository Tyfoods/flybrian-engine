from __future__ import annotations

import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from flybrian_engine.schema import ValidationError, validate_experiment_spec

FIXTURE = Path(__file__).parents[1] / "examples" / "minimal-experiment.json"
HETEROGENEOUS_FIXTURE = Path(__file__).parents[1] / "examples" / "heterogeneous-experiment.json"
DIRECT_FIXTURE = Path(__file__).parents[1] / "examples" / "direct-actuator-experiment.json"


def load_fixture() -> dict[str, object]:
    return cast(dict[str, object], json.loads(FIXTURE.read_text(encoding="utf-8")))


def nested_object(value: object, *path: str | int) -> dict[str, object]:
    current = value
    for segment in path:
        if isinstance(segment, int):
            current = cast(list[object], current)[segment]
        else:
            current = cast(dict[str, object], current)[segment]
    return cast(dict[str, object], current)


def test_fixture_is_stable_and_unknown_extensions_round_trip() -> None:
    value = load_fixture()
    value["extensions"] = {"org.example.future-backend": {"preserved": True}}
    spec = validate_experiment_spec(value)
    assert spec.value == value
    assert len(spec.sha256()) == 64


def test_minimal_fixture_canonical_hash_is_stable() -> None:
    assert validate_experiment_spec(load_fixture()).sha256() == (
        "243c9724d250eaeca11e884d091d7b236e1255646c64a88bc4f90f0f6f8af625"
    )


def test_heterogeneous_spec_round_trips_and_reports_neutral_requirements() -> None:
    value = cast(dict[str, object], json.loads(HETEROGENEOUS_FIXTURE.read_text(encoding="utf-8")))
    spec = validate_experiment_spec(value)
    assert spec.value == value
    assert spec.model_families == ("compartmental", "lif", "rate")
    assert spec.embodiment_mode == "muscle_mediated"
    assert spec.requested_artifact_kinds == ("motor_commands", "standardized_results", "video")


def test_direct_actuator_spec_is_distinct_from_muscle_mediated_drive() -> None:
    value = cast(dict[str, object], json.loads(DIRECT_FIXTURE.read_text(encoding="utf-8")))
    spec = validate_experiment_spec(value)
    assert spec.value == value
    assert spec.model_families == ("lif",)
    assert spec.embodiment_mode == "direct_actuator"


def test_legacy_hosted_embodiment_preserves_null_mapping_selection() -> None:
    value = load_fixture()
    value["embodied_config"] = {
        "enabled": True,
        "mapping_id": None,
        "firing_rate_window_ms": 32.0,
    }

    spec = validate_experiment_spec(value)

    assert spec.value == value
    assert spec.embodiment_mode == "direct_actuator"


@pytest.mark.parametrize("mapping_id", ["", " ", True, 1, [], {}])
def test_embodiment_mapping_selection_rejects_invalid_values(mapping_id: object) -> None:
    value = load_fixture()
    value["embodied_config"] = {
        "enabled": True,
        "mapping_id": mapping_id,
        "firing_rate_window_ms": 32.0,
    }

    with pytest.raises(ValidationError, match=r"embodied_config\.mapping_id"):
        validate_experiment_spec(value)


def test_direct_actuator_links_must_reference_selected_neurons() -> None:
    value = cast(dict[str, object], json.loads(DIRECT_FIXTURE.read_text(encoding="utf-8")))
    nested_object(value, "embodied_config", "direct_actuator", "links", 0).update(
        neuron_id=999
    )
    with pytest.raises(ValidationError, match="references unknown neuron 999"):
        validate_experiment_spec(value)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: nested_object(
                value, "neuron_models", "lif_interneuron", "parameters", "tau_m"
            ).update(unit=""),
            "neuron_models.lif_interneuron.parameters.tau_m.unit",
        ),
        (
            lambda value: nested_object(
                value,
                "neuron_models",
                "rate_controller",
                "parameters",
                "gain",
                "distribution",
            ).update(standard_deviation=-1),
            "standard_deviation must be non-negative",
        ),
        (
            lambda value: nested_object(
                value,
                "embodied_config",
                "muscle_mediated",
                "neuron_to_muscle",
                0,
            ).update(muscle_id="missing"),
            "references unknown muscle 'missing'",
        ),
        (
            lambda value: value.update(extensions={"unnamespaced": {"preserved": True}}),
            "extensions.unnamespaced must use a namespaced owner",
        ),
        (
            lambda value: nested_object(
                value, "neurons", "rate_controller", "2"
            ).update(record_spikes="yes"),
            "neurons.rate_controller.2.record_spikes must be a boolean",
        ),
        (
            lambda value: nested_object(
                value, "neurons", "compartmental_motor", "3"
            ).update(compartments={}),
            "compartments must not be empty for a compartmental model",
        ),
    ],
)
def test_malformed_rich_scientific_fields_fail_at_their_contract_path(
    mutate: Callable[[dict[str, object]], None],
    message: str,
) -> None:
    value = cast(dict[str, object], json.loads(HETEROGENEOUS_FIXTURE.read_text(encoding="utf-8")))
    mutate(value)
    with pytest.raises(ValidationError, match=message):
        validate_experiment_spec(value)


@pytest.mark.parametrize("mutation", [
    lambda value: value.update(spec_version="2.0"),
    lambda value: value.update(sim_time_ms=float("nan")),
    lambda value: value.update(random_seed=-1),
    lambda value: value.update(neurons={}),
])
def test_invalid_known_fields_are_not_coerced(mutation: object) -> None:
    value = copy.deepcopy(load_fixture())
    mutation(value)  # type: ignore[operator]
    with pytest.raises(ValidationError):
        validate_experiment_spec(value)


def test_model_family_and_neuron_identity_must_agree() -> None:
    value = load_fixture()
    value["neurons"]["lif"]["1"]["model_type"] = "rate"  # type: ignore[index]
    with pytest.raises(ValidationError, match="model_type"):
        validate_experiment_spec(value)
