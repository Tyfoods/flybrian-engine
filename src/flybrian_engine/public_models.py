"""Shared admission, parameter selection and artifacts for the public reference models."""

from pathlib import Path
from typing import Any, cast

from .artifacts import Artifact, ArtifactDisposition, ArtifactManifest, DatasetReference
from .backends import BackendCapabilities, CompatibilityIssue
from .results import validate_standardized_results
from .schema import ExperimentSpec
from .version import __version__


def _parameter_record(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, dict) or "value" not in value or "unit" not in value:
        raise ValueError(f"{path} must be a fixed unit-bearing parameter")
    return cast(dict[str, object], value)


def _model_parameters(
    spec: ExperimentSpec,
    group_id: str,
    neuron: dict[str, object],
) -> dict[str, object]:
    models = cast(dict[str, dict[str, object]], spec.value["neuron_models"])
    parameters = cast(dict[str, object], models[group_id]["parameters"]).copy()
    overrides = neuron.get("parameter_overrides")
    if isinstance(overrides, dict):
        parameters.update(overrides)
    return parameters


def _stimulus_for(
    spec: ExperimentSpec,
    neuron_id: int,
    variable: str,
    compartment_id: str | None = None,
) -> object | None:
    found: list[object] = []
    for raw_stimulus in cast(list[dict[str, object]], spec.value.get("stimuli", [])):
        target = cast(dict[str, object], raw_stimulus["target"])
        if (
            target["neuron_id"] == neuron_id
            and target["variable"] == variable
            and target.get("compartment_id") == compartment_id
        ):
            found.append(raw_stimulus["amplitude"])
    if len(found) > 1:
        raise ValueError(f"multiple stimuli target neuron {neuron_id} variable {variable!r}")
    return found[0] if found else None


_UNIT_SCALE = {
    "1": 1,
    "A": 1,
    "Hz": 1,
    "Mohm": 1e6,
    "V": 1,
    "ms": 1e-3,
    "mV": 1e-3,
    "nA": 1e-9,
    "nS": 1e-9,
    "pA": 1e-12,
    "pF": 1e-12,
    "s": 1,
    "uA": 1e-6,
    "us": 1e-6,
}


def parameter_si(value: object, path: str) -> float:
    parameter = _parameter_record(value, path)
    amount, unit = parameter["value"], parameter["unit"]
    if (
        not isinstance(amount, (int, float))
        or isinstance(amount, bool)
        or not isinstance(unit, str)
    ):
        raise ValueError(f"{path} must contain a numeric value and unit")
    return float(amount) * _UNIT_SCALE[unit]


def compatibility_issues(spec: ExperimentSpec) -> tuple[CompatibilityIssue, ...]:
    issues: list[CompatibilityIssue] = []
    models = spec.value.get("neuron_models")
    if not isinstance(models, dict):
        return (
            CompatibilityIssue(
                "missing_model_definitions",
                "neuron_models",
                "Choose an explicit supported public model definition.",
            ),
        )
    family_by_id = {}
    positive = {
        "tau_m",
        "tau",
        "capacitance_soma",
        "capacitance_dendrite",
        "leak_conductance_soma",
        "leak_conductance_dendrite",
    }
    nonnegative = {"coupling_conductance", "refractory_period"}
    for group_id, cells in spec.value["neurons"].items():
        for key, cell in cells.items():
            family_by_id[cell["neuron_id"]] = models[group_id]["family"]
            path = f"neurons.{group_id}.{key}"
            for name, value in _model_parameters(spec, group_id, cell).items():
                if name in positive | nonnegative:
                    numeric = parameter_si(value, f"{path}.parameter_overrides.{name}")
                    if numeric < 0 or (name in positive and numeric == 0):
                        issues.append(
                            CompatibilityIssue(
                                "unsupported_model_parameter",
                                path,
                                f"{name} must be "
                                f"{'positive' if name in positive else 'nonnegative'}.",
                            )
                        )
            for target in [cell, *cell.get("compartments", {}).values()]:
                if target.get("poisson_inputs") or target.get("external_currents"):
                    issues.append(
                        CompatibilityIssue(
                            "unsupported_legacy_drive",
                            path,
                            "Public reference models use explicit stimuli "
                            "rather than legacy drive fields.",
                        )
                    )
            if any(
                part.get("record_variables") != cell["record_variables"]
                or part.get("record_spikes")
                for part in cell.get("compartments", {}).values()
            ):
                issues.append(
                    CompatibilityIssue(
                        "unsupported_compartment_recording",
                        path,
                        "This public model release records both passive compartments together.",
                    )
                )
    for field in (
        "poisson_background_rate",
        "poisson_background_weight",
        "external_current_background_amplitude",
        "connectivity_modifications",
    ):
        if spec.value.get(field):
            issues.append(
                CompatibilityIssue(
                    "unsupported_legacy_drive",
                    field,
                    "Public reference models use explicit stimuli and connections.",
                )
            )
    simulation = spec.value.get("simulation")
    if not isinstance(simulation, dict):
        issues.append(
            CompatibilityIssue(
                code="missing_simulation_contract",
                path="simulation",
                message="Public model execution requires an explicit simulation contract",
            )
        )
    elif simulation.get("integration_method") != "exact":
        issues.append(
            CompatibilityIssue(
                code="unsupported_integration_method",
                path="simulation.integration_method",
                message="Public reference models require the exact integration method",
            )
        )
    connections = spec.value.get("connections")
    if connections not in (None, []):
        issues.append(
            CompatibilityIssue(
                code="unsupported_connections",
                path="connections",
                message="this public model release does not yet support "
                "public connection definitions",
            )
        )
    seen_targets: set[tuple[object, object, object]] = set()
    for index, raw_stimulus in enumerate(cast(list[object], spec.value.get("stimuli", []))):
        if not isinstance(raw_stimulus, dict):
            continue
        target = raw_stimulus.get("target")
        if not isinstance(target, dict):
            continue
        identity = (
            target.get("neuron_id"),
            target.get("compartment_id"),
            target.get("variable"),
        )
        family = family_by_id[target["neuron_id"]]
        expected = "input_rate" if family == "rate" else "external_current"
        if target["variable"] != expected or (
            family == "compartmental" and target.get("compartment_id") != "dendrite"
        ):
            issues.append(
                CompatibilityIssue(
                    "unsupported_stimulus_target",
                    f"stimuli[{index}].target",
                    "Choose LIF external current, rate input rate, "
                    "or passive dendrite external current.",
                )
            )
        if identity in seen_targets:
            issues.append(
                CompatibilityIssue(
                    code="overlapping_stimulus",
                    path=f"stimuli[{index}].target",
                    message="this public model release accepts one stimulus per target variable",
                )
            )
        seen_targets.add(identity)
        start = cast(dict[str, object], raw_stimulus["start_time"])
        end = cast(dict[str, object], raw_stimulus["end_time"])
        if start != {"unit": "ms", "value": 0} or end != {
            "unit": "ms",
            "value": spec.value["sim_time_ms"],
        }:
            issues.append(
                CompatibilityIssue(
                    code="unsupported_stimulus_window",
                    path=f"stimuli[{index}]",
                    message="this public model release accepts constant full-duration stimuli",
                )
            )
    return tuple(issues)


def write_result(
    spec: ExperimentSpec, result: dict[str, Any], run_dir: Path, capabilities: BackendCapabilities
) -> ArtifactManifest:
    run_id = run_dir.name
    result_path = run_dir / "standardized-results.json"
    validated_result = validate_standardized_results(result)
    result_path.write_text(validated_result.to_json(), encoding="utf-8")
    artifact = Artifact.from_file(
        key="standardized_results",
        kind="standardized_results",
        media_type="application/json",
        path=result_path,
        root=run_dir,
    )
    manifest = ArtifactManifest(
        run_id=run_id,
        engine_version=__version__,
        backend_id=capabilities.backend_id,
        backend_version=capabilities.backend_version,
        experiment_spec_version=str(spec.value["spec_version"]),
        experiment_sha256=spec.sha256(),
        random_seed=int(spec.value["random_seed"]),
        datasets=(DatasetReference(dataset_id=str(spec.value["dataset"])),),
        scientific_execution=True,
        deterministic_for_fixed_seed=True,
        artifacts=(artifact,),
        dispositions=(
            ArtifactDisposition(
                kind="standardized_results",
                status="available",
                artifact_keys=("standardized_results",),
            ),
        ),
    )
    manifest.write(run_dir / "manifest.json")
    return manifest
