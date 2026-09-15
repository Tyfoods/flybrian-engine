"""Public Brian2 adapter for the frozen E3-A scientific model definitions."""

from __future__ import annotations

import importlib
import importlib.metadata
from pathlib import Path
from typing import Any, cast

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from .artifacts import ArtifactManifest
from .backends import BackendCapabilities, CompatibilityIssue
from .model_catalog import MANC_MODEL, PUBLIC_MODEL_DEFINITIONS, public_model_ids
from .public_models import (
    _model_parameters,
    _parameter_record,
    _stimulus_for,
    parameter_si,
    write_result,
)
from .public_models import compatibility_issues as public_model_issues
from .schema import ExperimentSpec
from .version import __version__

_BRIAN_RANGE = SpecifierSet(">=2.7,<3")


def _installed_brian_version() -> str | None:
    try:
        return importlib.metadata.version("brian2")
    except importlib.metadata.PackageNotFoundError:
        return None


def _parameter_quantity(brian: Any, value: object, path: str) -> Any:
    parameter = _parameter_record(value, path)
    unit_name = cast(str, parameter["unit"])
    units = {
        "1": 1,
        "A": brian.amp,
        "Hz": brian.Hz,
        "Mohm": brian.Mohm,
        "V": brian.volt,
        "ms": brian.ms,
        "mV": brian.mV,
        "nA": brian.nA,
        "nS": brian.nS,
        "pA": brian.pA,
        "pF": brian.pF,
        "s": brian.second,
        "uA": brian.uA,
        "us": brian.us,
    }
    try:
        unit = units[unit_name]
    except KeyError as error:
        raise ValueError(f"{path}.unit is unsupported by the Brian2 adapter") from error
    return cast(float, parameter["value"]) * unit


def _seconds(brian: Any, values: Any) -> list[float]:
    return [float(value / brian.second) for value in values]


def _values(values: Any, unit: Any) -> list[float]:
    return [float(value / unit) for value in values]


class Brian2Backend:
    """Dependency-isolated Brian2 execution for the frozen public model catalog."""

    @property
    def capabilities(self) -> BackendCapabilities:
        version = _installed_brian_version()
        availability = "available"
        reason = None
        if version is None:
            version = "0"
            availability = "not_installed"
            reason = "Brian2 backend is not installed. Install flybrian-engine[brian2]."
        elif Version(version) not in _BRIAN_RANGE:
            availability = "incompatible_runtime"
            reason = "Installed Brian2 version is incompatible with this engine release."
        return BackendCapabilities(
            backend_id="brian2",
            backend_version=version,
            experiment_spec_versions=("1.0",),
            neuron_model_families=("compartmental", "lif", "rate", "lif_churgin_projection_neuron"),
            neuron_model_ids=(
                *public_model_ids(),
                "lif.churgin_projection.figure8.v1",
                MANC_MODEL.model_id,
            ),
            embodiment_modes=("none", "direct_actuator"),
            artifact_kinds=("standardized_results",),
            deterministic_for_fixed_seed=True,
            scientific_execution=True,
            availability=availability,
            unavailable_reason=reason,
        )

    def compatibility_issues(self, spec: ExperimentSpec) -> tuple[CompatibilityIssue, ...]:
        from .manc import compatibility_issues as manc_issues
        from .manc import is_manc

        if is_manc(spec):
            return manc_issues(spec)
        if spec.embodiment_mode != "none":
            return (
                CompatibilityIssue(
                    "unsupported_body_execution",
                    "embodied_config",
                    "Body execution is currently translated for the ordinary MANC walking profile.",
                ),
            )
        if (
            spec.value.get("extensions", {}).get("org.flybrian.execution", {}).get("profile")
            == "figure8_fes_v1"
        ):
            from .figure8 import compatibility_issues

            return compatibility_issues(spec)
        return public_model_issues(spec)

    def run(self, spec: ExperimentSpec, output_dir: Path, run_id: str) -> ArtifactManifest:
        from .manc import is_manc

        if (
            is_manc(spec)
            or spec.value.get("extensions", {}).get("org.flybrian.execution", {}).get("profile")
            == "figure8_fes_v1"
        ):
            from .figure8 import run_brian2

            return run_brian2(spec, output_dir, run_id)
        brian = importlib.import_module("brian2")
        capabilities = self.capabilities
        if capabilities.availability != "available":
            raise RuntimeError(capabilities.unavailable_reason)

        run_dir = output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        brian.start_scope()
        brian.seed(int(spec.value["random_seed"]))
        simulation = cast(dict[str, object], spec.value["simulation"])
        clock = brian.Clock(
            dt=_parameter_quantity(brian, simulation["time_step"], "simulation.time_step")
        )
        network = brian.Network()
        spike_monitors: list[tuple[int, Any]] = []
        series_monitors: list[tuple[int, str | None, str, str, Any, str]] = []
        neuron_records: list[dict[str, object]] = []

        models = cast(dict[str, dict[str, object]], spec.value["neuron_models"])
        neurons = cast(dict[str, dict[str, dict[str, object]]], spec.value["neurons"])
        for group_id in sorted(neurons):
            model = models[group_id]
            model_id = cast(str, model["model_id"])
            definition = PUBLIC_MODEL_DEFINITIONS[model_id]
            for neuron_key in sorted(neurons[group_id], key=int):
                neuron = neurons[group_id][neuron_key]
                neuron_id = cast(int, neuron["neuron_id"])
                parameters = _model_parameters(spec, group_id, neuron)
                neuron_records.append(
                    {
                        "family": definition.family,
                        "model_id": model_id,
                        "neuron_id": neuron_id,
                    }
                )
                if model_id == "lif.basic.v1":
                    group = self._build_lif(
                        brian,
                        clock,
                        parameters,
                        _stimulus_for(spec, neuron_id, "external_current"),
                        neuron_id,
                    )
                    network.add(group)
                    if neuron["record_spikes"]:
                        spike_monitor = brian.SpikeMonitor(group)
                        network.add(spike_monitor)
                        spike_monitors.append((neuron_id, spike_monitor))
                    if neuron["record_variables"]:
                        state_monitor = brian.StateMonitor(group, "v", record=True, clock=clock)
                        network.add(state_monitor)
                        series_monitors.append(
                            (
                                neuron_id,
                                None,
                                "membrane_potential",
                                "V",
                                state_monitor,
                                "v",
                            )
                        )
                elif model_id == "rate.first_order.v1":
                    group = self._build_rate(
                        brian,
                        clock,
                        parameters,
                        _stimulus_for(spec, neuron_id, "input_rate"),
                        neuron_id,
                    )
                    network.add(group)
                    if neuron["record_variables"]:
                        state_monitor = brian.StateMonitor(group, "r", record=True, clock=clock)
                        network.add(state_monitor)
                        series_monitors.append(
                            (
                                neuron_id,
                                None,
                                "rate",
                                "Hz",
                                state_monitor,
                                "r",
                            )
                        )
                elif model_id == "compartmental.passive_two.v1":
                    group = self._build_compartmental(
                        brian,
                        clock,
                        parameters,
                        _stimulus_for(
                            spec,
                            neuron_id,
                            "external_current",
                            "dendrite",
                        ),
                        neuron_id,
                    )
                    network.add(group)
                    if neuron["record_variables"]:
                        state_monitor = brian.StateMonitor(
                            group,
                            ("v_soma", "v_dendrite"),
                            record=True,
                            clock=clock,
                        )
                        network.add(state_monitor)
                        series_monitors.extend(
                            (
                                (
                                    neuron_id,
                                    "dendrite",
                                    "membrane_potential",
                                    "V",
                                    state_monitor,
                                    "v_dendrite",
                                ),
                                (
                                    neuron_id,
                                    "soma",
                                    "membrane_potential",
                                    "V",
                                    state_monitor,
                                    "v_soma",
                                ),
                            )
                        )
                else:
                    raise ValueError(f"unsupported public model definition {model_id!r}")

        network.run(float(spec.value["sim_time_ms"]) * brian.ms)
        result = self._standardized_results(
            brian,
            spec,
            run_id,
            capabilities.backend_version,
            neuron_records,
            spike_monitors,
            series_monitors,
            simulation,
        )
        return write_result(spec, result, run_dir, capabilities)

    @staticmethod
    def _build_lif(
        brian: Any,
        clock: Any,
        parameters: dict[str, object],
        stimulus: object | None,
        neuron_id: int,
    ) -> Any:
        group = brian.NeuronGroup(
            1,
            """
            dv/dt = (v_rest - v + resistance * external_current) / tau_m : volt (unless refractory)
            v_rest : volt (constant)
            v_reset : volt (constant)
            v_threshold : volt (constant)
            resistance : ohm (constant)
            tau_m : second (constant)
            refractory_period : second (constant)
            external_current : amp (constant)
            """,
            threshold="v >= v_threshold",
            reset="v = v_reset",
            refractory="refractory_period",
            method="exact",
            clock=clock,
            name=f"lif_{neuron_id}",
        )
        group.v = _parameter_quantity(brian, parameters["initial_v"], "initial_v")
        for name in (
            "v_rest",
            "v_reset",
            "v_threshold",
            "resistance",
            "tau_m",
            "refractory_period",
        ):
            setattr(group, name, _parameter_quantity(brian, parameters[name], name))
        group.external_current = (
            0 * brian.amp
            if stimulus is None
            else _parameter_quantity(brian, stimulus, "stimulus.amplitude")
        )
        return group

    @staticmethod
    def _build_rate(
        brian: Any,
        clock: Any,
        parameters: dict[str, object],
        stimulus: object | None,
        neuron_id: int,
    ) -> Any:
        group = brian.NeuronGroup(
            1,
            """
            dr/dt = (-r + gain * input_rate) / tau : Hz
            gain : 1 (constant)
            input_rate : Hz (constant)
            tau : second (constant)
            """,
            method="exact",
            clock=clock,
            name=f"rate_{neuron_id}",
        )
        group.r = _parameter_quantity(brian, parameters["initial_rate"], "initial_rate")
        group.gain = _parameter_quantity(brian, parameters["gain"], "gain")
        group.tau = _parameter_quantity(brian, parameters["tau"], "tau")
        group.input_rate = (
            0 * brian.Hz
            if stimulus is None
            else _parameter_quantity(brian, stimulus, "stimulus.amplitude")
        )
        return group

    @staticmethod
    def _build_compartmental(
        brian: Any,
        clock: Any,
        parameters: dict[str, object],
        stimulus: object | None,
        neuron_id: int,
    ) -> Any:
        equations = """
            dv_soma/dt = soma_current / capacitance_soma : volt
            dv_dendrite/dt = dendrite_total_current / capacitance_dendrite : volt
            soma_current = soma_leak + soma_coupling : amp
            dendrite_total_current = dendrite_leak + dendrite_coupling + dendrite_current : amp
            soma_leak = g_leak_soma * (v_rest - v_soma) : amp
            dendrite_leak = g_leak_dendrite * (v_rest - v_dendrite) : amp
            soma_coupling = g_couple * (v_dendrite - v_soma) : amp
            dendrite_coupling = g_couple * (v_soma - v_dendrite) : amp
            g_leak_soma : siemens (constant)
            g_leak_dendrite : siemens (constant)
            g_couple : siemens (constant)
            capacitance_soma : farad (constant)
            capacitance_dendrite : farad (constant)
            v_rest : volt (constant)
            dendrite_current : amp (constant)
            """
        if parameter_si(parameters["coupling_conductance"], "coupling_conductance") == 0:
            # Remove the absent coupling before symbolic integration, which otherwise
            # divides by a degenerate eigenvalue difference for equal compartments.
            equations = equations.replace("g_couple * (v_dendrite - v_soma)", "0 * amp")
            equations = equations.replace("g_couple * (v_soma - v_dendrite)", "0 * amp")
        group = brian.NeuronGroup(
            1,
            equations,
            method="exact",
            clock=clock,
            name=f"compartmental_{neuron_id}",
        )
        assignments = {
            "capacitance_dendrite": "capacitance_dendrite",
            "capacitance_soma": "capacitance_soma",
            "coupling_conductance": "g_couple",
            "leak_conductance_dendrite": "g_leak_dendrite",
            "leak_conductance_soma": "g_leak_soma",
            "v_rest": "v_rest",
        }
        for parameter_name, variable_name in assignments.items():
            setattr(
                group,
                variable_name,
                _parameter_quantity(brian, parameters[parameter_name], parameter_name),
            )
        group.v_soma = _parameter_quantity(brian, parameters["initial_v_soma"], "initial_v_soma")
        group.v_dendrite = _parameter_quantity(
            brian,
            parameters["initial_v_dendrite"],
            "initial_v_dendrite",
        )
        group.dendrite_current = (
            0 * brian.amp
            if stimulus is None
            else _parameter_quantity(brian, stimulus, "stimulus.amplitude")
        )
        return group

    @staticmethod
    def _standardized_results(
        brian: Any,
        spec: ExperimentSpec,
        run_id: str,
        backend_version: str,
        neurons: list[dict[str, object]],
        spike_monitors: list[tuple[int, Any]],
        series_monitors: list[tuple[int, str | None, str, str, Any, str]],
        simulation: dict[str, object],
    ) -> dict[str, object]:
        spikes = [
            {"neuron_id": neuron_id, "time_seconds": time}
            for neuron_id, monitor in spike_monitors
            for time in _seconds(brian, monitor.t)
        ]
        spikes.sort(key=lambda item: (item["time_seconds"], item["neuron_id"]))
        series: list[dict[str, object]] = []
        unit_objects = {"V": brian.volt, "Hz": brian.Hz}
        for neuron_id, compartment_id, variable, unit, monitor, monitor_variable in series_monitors:
            series.append(
                {
                    "compartment_id": compartment_id,
                    "neuron_id": neuron_id,
                    "times_seconds": _seconds(brian, monitor.t),
                    "unit": unit,
                    "values": _values(getattr(monitor, monitor_variable)[0], unit_objects[unit]),
                    "variable": variable,
                }
            )
        series.sort(
            key=lambda item: (
                cast(int, item["neuron_id"]),
                cast(str | None, item["compartment_id"]) or "",
                cast(str, item["variable"]),
            )
        )
        time_step = _parameter_quantity(brian, simulation["time_step"], "simulation.time_step")
        return {
            "backend_id": "brian2",
            "backend_version": backend_version,
            "engine_version": __version__,
            "experiment_sha256": spec.sha256(),
            "network": {"connections": 0, "neurons": len(neurons)},
            "neurons": sorted(neurons, key=lambda item: cast(int, item["neuron_id"])),
            "run_id": run_id,
            "schema_version": "1.0",
            "series": series,
            "simulation": {
                "duration_seconds": float(spec.value["sim_time_ms"]) / 1000,
                "random_seed": int(spec.value["random_seed"]),
                "time_step_seconds": float(time_step / brian.second),
            },
            "spikes": spikes,
            "warnings": [],
        }
