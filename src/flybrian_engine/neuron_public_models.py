"""Run the explicit public reference models through native NEURON mechanisms."""

import math
from pathlib import Path
from typing import Any, TypedDict

from .artifacts import ArtifactManifest
from .backends import BackendCapabilities
from .model_catalog import PUBLIC_MODEL_DEFINITIONS
from .public_models import _model_parameters, _stimulus_for, parameter_si, write_result
from .schema import ExperimentSpec
from .version import __version__


class RecordedSeries(TypedDict):
    neuron_id: int
    compartment_id: str | None
    variable: str
    unit: str
    times_seconds: list[float]
    values: list[float]


_MECHANISMS = {
    "lif.basic.v1": "FlyBrianBasicLIF",
    "rate.first_order.v1": "FlyBrianFirstOrderRate",
    "compartmental.passive_two.v1": "FlyBrianPassiveTwo",
}
_NATIVE_SCALE = {
    "voltage": 1000,
    "time": 1000,
    "resistance": 1e-6,
    "conductance": 1e9,
    "capacitance": 1e12,
    "rate": 1,
    "dimensionless": 1,
}


def run_public_models(
    spec: ExperimentSpec, output_dir: Path, run_id: str, capabilities: BackendCapabilities
) -> ArtifactManifest:
    from neuron import h

    h.load_file("stdrun.hoc")
    h.cvode_active(0)
    dt_seconds = parameter_si(spec.value["simulation"]["time_step"], "simulation.time_step")
    h.dt = dt_seconds * 1000
    duration_seconds = spec.value["sim_time_ms"] / 1000
    nearest = round(duration_seconds / dt_seconds)
    # Brian2 Clock._calc_timestep treats targets within 0.01% of dt as on-grid.
    steps = (
        nearest
        if abs(nearest * dt_seconds - duration_seconds) / dt_seconds <= 1e-4
        else math.ceil(duration_seconds / dt_seconds)
    )
    times = [index * dt_seconds for index in range(steps)]
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    sections, points, neurons, spiking = [], [], [], []
    recordings: list[tuple[Any, str, float, RecordedSeries]] = []
    for group_id, cells in sorted(spec.value["neurons"].items()):
        model_id = spec.value["neuron_models"][group_id]["model_id"]
        definition = PUBLIC_MODEL_DEFINITIONS[model_id]
        for key, cell in sorted(cells.items(), key=lambda item: int(item[0])):
            neuron_id = int(key)
            section = h.Section(name=f"public_{neuron_id}")
            point = getattr(h, _MECHANISMS[model_id])(section(0.5))
            sections.append(section)
            points.append(point)
            for name, value in _model_parameters(spec, group_id, cell).items():
                scale = _NATIVE_SCALE[definition.parameters[name].dimension]
                setattr(point, name, parameter_si(value, name) * scale)
            drive_scale: float
            observed: list[tuple[str | None, str, str, str, float]]
            if definition.family == "rate":
                drive_variable, compartment, native_variable, drive_scale = (
                    "input_rate",
                    None,
                    "input_rate",
                    1,
                )
                observed = [(None, "rate", "rate", "Hz", 1)]
            elif definition.family == "lif":
                drive_variable, compartment, native_variable, drive_scale = (
                    "external_current",
                    None,
                    "external_current",
                    1e9,
                )
                observed = [(None, "vm", "membrane_potential", "V", 0.001)]
            else:
                drive_variable, compartment, native_variable, drive_scale = (
                    "external_current",
                    "dendrite",
                    "dendrite_current",
                    1e9,
                )
                observed = [
                    ("dendrite", "v_dendrite", "membrane_potential", "V", 0.001),
                    ("soma", "v_soma", "membrane_potential", "V", 0.001),
                ]
            stimulus = _stimulus_for(spec, neuron_id, drive_variable, compartment)
            setattr(
                point,
                native_variable,
                0
                if stimulus is None
                else parameter_si(stimulus, "stimulus.amplitude") * drive_scale,
            )
            neurons.append(dict(neuron_id=neuron_id, family=definition.family, model_id=model_id))
            if cell["record_spikes"]:
                spiking.append((neuron_id, point))
            if cell["record_variables"]:
                for compartment, native_variable, variable, unit, scale in observed:
                    series: RecordedSeries = dict(
                        neuron_id=neuron_id,
                        compartment_id=compartment,
                        variable=variable,
                        unit=unit,
                        times_seconds=times,
                        values=[],
                    )
                    recordings.append((point, native_variable, scale, series))
    h.finitialize(-65)
    spikes = []
    for time in times:
        # Both adapters observe the state at the beginning of this integration tick.
        for point, variable, scale, series in recordings:
            series["values"].append(float(getattr(point, variable)) * scale)
        h.fadvance()
        # NEURON advances to the end of the tick; FES labels its threshold event
        # by the tick's beginning, as the retained Brian2 implementation does.
        for neuron_id, point in spiking:
            if point.spike_out > 0.5:
                spikes.append(dict(neuron_id=neuron_id, time_seconds=time))
    result_series = [record[3] for record in recordings]
    result_series.sort(
        key=lambda item: (item["neuron_id"], item["compartment_id"] or "", item["variable"])
    )
    result = dict(
        schema_version="1.0",
        run_id=run_id,
        backend_id="neuron",
        backend_version=capabilities.backend_version,
        engine_version=__version__,
        experiment_sha256=spec.sha256(),
        network=dict(neurons=len(neurons), connections=0),
        neurons=sorted(neurons, key=lambda item: item["neuron_id"]),
        simulation=dict(
            duration_seconds=duration_seconds,
            time_step_seconds=dt_seconds,
            random_seed=spec.value["random_seed"],
        ),
        spikes=spikes,
        series=result_series,
        warnings=[],
    )
    return write_result(spec, result, run_dir, capabilities)
