from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import cast

import pytest

from flybrian_engine.schema import ValidationError, validate_experiment_spec

FIXTURE = Path(__file__).parents[1] / "examples" / "minimal-experiment.json"


def load_fixture() -> dict[str, object]:
    return cast(dict[str, object], json.loads(FIXTURE.read_text(encoding="utf-8")))


def test_fixture_is_stable_and_unknown_extensions_round_trip() -> None:
    value = load_fixture()
    value["extensions"] = {"future_backend": {"preserved": True}}
    spec = validate_experiment_spec(value)
    assert spec.value == value
    assert len(spec.sha256()) == 64


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
