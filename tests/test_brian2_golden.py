from __future__ import annotations

import copy
import json
import math
import threading
import urllib.request
from itertools import pairwise
from pathlib import Path
from typing import cast

import pytest

from flybrian_engine import brian2_backend
from flybrian_engine.cli import main
from flybrian_engine.results import validate_standardized_results
from flybrian_engine.runner import (
    CompatibilityError,
    create_server,
    default_registry,
    run_experiment,
)
from flybrian_engine.schema import ValidationError, validate_experiment_spec

FIXTURE = Path(__file__).parents[1] / "examples" / "brian2-golden-experiment.json"


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


def nearest_value(
    series: dict[str, object],
    checkpoint_seconds: float,
) -> tuple[float, float]:
    times = cast(list[float], series["times_seconds"])
    values = cast(list[float], series["values"])
    index = min(range(len(times)), key=lambda item: abs(times[item] - checkpoint_seconds))
    return times[index], values[index]


def test_golden_spec_round_trips_with_explicit_models_units_and_stimuli() -> None:
    value = load_fixture()
    spec = validate_experiment_spec(value)
    assert spec.value == value
    assert spec.model_families == ("compartmental", "lif", "rate")
    assert spec.requested_artifact_kinds == ("standardized_results",)


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda value: nested_object(value, "simulation", "time_step").update(
                unit="furlong"
            ),
            "simulation.time_step.unit",
        ),
        (
            lambda value: nested_object(value, "stimuli", 0, "target").update(
                neuron_id=999
            ),
            r"stimuli\[0\].target.neuron_id references unknown neuron 999",
        ),
        (
            lambda value: nested_object(
                value, "neuron_models", "lif_basic", "parameters", "tau_m"
            ).update(unit="mV"),
            "neuron_models.lif_basic.parameters.tau_m.unit",
        ),
        (
            lambda value: nested_object(
                value, "neurons", "rate_first_order", "2"
            ).update(record_spikes=True),
            "neurons.rate_first_order.2.record_spikes",
        ),
    ],
)
def test_golden_science_rejects_ambiguous_or_dimensionally_invalid_fields(
    mutate: object,
    message: str,
) -> None:
    value = copy.deepcopy(load_fixture())
    mutate(value)  # type: ignore[operator]
    with pytest.raises(ValidationError, match=message):
        validate_experiment_spec(value)


def test_brian2_backend_advertises_only_frozen_model_definitions() -> None:
    capabilities = default_registry().get("brian2").capabilities
    assert capabilities.scientific_execution is True
    assert capabilities.neuron_model_families == ("compartmental", "lif", "rate")
    assert capabilities.neuron_model_ids == (
        "compartmental.passive_two.v1",
        "lif.basic.v1",
        "rate.first_order.v1",
    )
    assert capabilities.artifact_kinds == ("standardized_results",)


def test_missing_brian_is_truthful_and_rejects_before_allocation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(brian2_backend, "_installed_brian_version", lambda: None)
    capabilities = default_registry().get("brian2").capabilities
    assert capabilities.availability == "not_installed"
    assert capabilities.unavailable_reason == (
        "Brian2 backend is not installed. Install flybrian-engine[brian2]."
    )
    with pytest.raises(CompatibilityError) as rejected:
        run_experiment(
            load_fixture(),
            tmp_path,
            backend_id="brian2",
            run_id="must_not_allocate",
        )
    assert ("backend_unavailable", "execution.backend_id") in {
        (issue.code, issue.path) for issue in rejected.value.issues
    }
    assert list(tmp_path.iterdir()) == []


def test_brian2_golden_run_matches_independent_analytic_oracle(tmp_path: Path) -> None:
    value = load_fixture()
    manifest = run_experiment(
        value,
        tmp_path,
        backend_id="brian2",
        run_id="brian_golden",
    )
    assert manifest["scientific_execution"] is True
    assert manifest["backend_id"] == "brian2"
    assert manifest["dispositions"] == [{
        "artifact_keys": ["standardized_results"],
        "kind": "standardized_results",
        "reason": None,
        "status": "available",
    }]
    artifact = cast(list[dict[str, object]], manifest["artifacts"])[0]
    results_path = tmp_path / "brian_golden" / cast(str, artifact["relative_path"])
    results = cast(dict[str, object], json.loads(results_path.read_text(encoding="utf-8")))
    assert validate_standardized_results(results).value == results

    assert results["schema_version"] == "1.0"
    assert results["run_id"] == "brian_golden"
    assert results["experiment_sha256"] == validate_experiment_spec(value).sha256()
    assert results["simulation"] == {
        "duration_seconds": 0.1,
        "random_seed": 6172,
        "time_step_seconds": 0.0001,
    }
    assert results["network"] == {"connections": 0, "neurons": 3}

    spikes = cast(list[dict[str, object]], results["spikes"])
    assert [spike["neuron_id"] for spike in spikes] == [1] * 6
    crossing = -0.020 * math.log(0.5)
    spike_times = [cast(float, spike["time_seconds"]) for spike in spikes]
    assert spike_times[0] == pytest.approx(crossing, abs=0.00011)
    assert [
        current - previous for previous, current in pairwise(spike_times)
    ] == pytest.approx([crossing + 0.002] * 5, abs=0.00011)

    series = cast(list[dict[str, object]], results["series"])
    by_identity = {
        (
            cast(int, item["neuron_id"]),
            cast(str | None, item["compartment_id"]),
            cast(str, item["variable"]),
        ): item
        for item in series
    }
    rate = by_identity[(2, None, "rate")]
    soma = by_identity[(3, "soma", "membrane_potential")]
    dendrite = by_identity[(3, "dendrite", "membrane_potential")]
    assert rate["unit"] == "Hz"
    assert soma["unit"] == "V"
    assert dendrite["unit"] == "V"

    checkpoints = (
        (0.010, 31.6060279414, -0.0640010589978, -0.0596777354139),
        (0.020, 43.2332358382, -0.0631308873190, -0.0582224655134),
        (0.050, 49.6631026500, -0.0625335762352, -0.0575338032348),
    )
    for checkpoint, expected_rate, expected_soma, expected_dendrite in checkpoints:
        rate_time, rate_value = nearest_value(rate, checkpoint)
        soma_time, soma_value = nearest_value(soma, checkpoint)
        dendrite_time, dendrite_value = nearest_value(dendrite, checkpoint)
        assert rate_time == pytest.approx(checkpoint, abs=0.00011)
        assert soma_time == pytest.approx(checkpoint, abs=0.00011)
        assert dendrite_time == pytest.approx(checkpoint, abs=0.00011)
        assert rate_value == pytest.approx(expected_rate, abs=0.0001, rel=0.00001)
        assert soma_value == pytest.approx(expected_soma, abs=1e-7, rel=0.00001)
        assert dendrite_value == pytest.approx(expected_dendrite, abs=1e-7, rel=0.00001)


def test_brian2_repeat_run_is_stable_for_fixed_release_and_seed(tmp_path: Path) -> None:
    value = load_fixture()
    first = run_experiment(value, tmp_path, backend_id="brian2", run_id="repeat_a")
    second = run_experiment(value, tmp_path, backend_id="brian2", run_id="repeat_b")
    first_artifact = cast(list[dict[str, object]], first["artifacts"])[0]
    second_artifact = cast(list[dict[str, object]], second["artifacts"])[0]
    first_result = json.loads(
        (tmp_path / "repeat_a" / cast(str, first_artifact["relative_path"])).read_text(
            encoding="utf-8"
        )
    )
    second_result = json.loads(
        (tmp_path / "repeat_b" / cast(str, second_artifact["relative_path"])).read_text(
            encoding="utf-8"
        )
    )
    first_result["run_id"] = "stable"
    second_result["run_id"] = "stable"
    assert first_result == second_result


def test_brian2_cli_and_loopback_protocol_use_the_same_public_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli_output = tmp_path / "cli"
    assert main([
        "run",
        str(FIXTURE),
        "--backend",
        "brian2",
        "--output",
        str(cli_output),
    ]) == 0
    cli_manifest = json.loads(capsys.readouterr().out.splitlines()[-1])
    assert cli_manifest["backend_id"] == "brian2"
    assert cli_manifest["scientific_execution"] is True

    http_output = tmp_path / "http"
    server = create_server(
        host="127.0.0.1",
        port=0,
        token="secret",
        output_dir=http_output,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        request = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/v1/runs",
            data=json.dumps({
                "backend_id": "brian2",
                "experiment": load_fixture(),
                "run_id": "brian_http",
            }).encode(),
            headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            http_manifest = json.load(response)
        assert http_manifest["backend_id"] == "brian2"
        assert http_manifest["scientific_execution"] is True
        assert http_manifest["experiment_sha256"] == cli_manifest["experiment_sha256"]
        assert http_manifest["dispositions"] == cli_manifest["dispositions"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
