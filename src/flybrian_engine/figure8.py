"""Frozen Figure 8 model, verified network, and backend-neutral run data."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .artifacts import Artifact, ArtifactDisposition, ArtifactManifest, DatasetReference
from .backends import CompatibilityIssue
from .body_execution import attach_body_artifacts, execution_duration_ms, run_body
from .datasets import DatasetManifest
from .model_catalog import FIGURE8_MODEL, FIGURE8_PARAMETERS
from .result_summary import recorded_spike_ids
from .results import validate_standardized_results
from .schema import ExperimentSpec
from .version import __version__

MODEL_ID = FIGURE8_MODEL.model_id
GROUP = "lif_churgin_projection_neuron"
DATASET_ID = "manc:v1.2.1+flybrian-figure7-2025-12-05"
PARAMETERS = FIGURE8_PARAMETERS


def is_figure8(spec: ExperimentSpec) -> bool:
    return (
        spec.value.get("extensions", {}).get("org.flybrian.execution", {}).get("profile")
        == "figure8_fes_v1"
    )


def compatibility_issues(spec: ExperimentSpec) -> tuple[CompatibilityIssue, ...]:
    value = spec.value
    issues = []

    def require(condition: bool, path: str, message: str) -> None:
        if not condition:
            issues.append(CompatibilityIssue("unsupported_figure8_semantics", path, message))

    require(is_figure8(spec), "extensions", "This backend requires the figure8_fes_v1 profile.")
    require(
        value["dataset"] == DATASET_ID, "dataset", "Figure 8 requires its retained MANC release."
    )
    require(
        value.get("simulation")
        == {"integration_method": "euler", "time_step": {"value": 0.1, "unit": "ms"}},
        "simulation",
        "Figure 8 uses forward Euler at 0.1 ms.",
    )
    require(
        set(value["neurons"]) == {GROUP},
        "neurons",
        "Figure 8 supports the Churgin point model only.",
    )
    require(
        value.get("population_assignments") == {GROUP: {"selector": "dataset_all"}},
        "population_assignments",
        "Figure 8 simulates the complete dataset population.",
    )
    for field in (
        "poisson_background_rate",
        "poisson_background_weight",
        "external_current_background_amplitude",
    ):
        require(
            value.get(field, 0) == 0,
            field,
            "This Figure 8 implementation requires zero background drive.",
        )
    for field in ("connections", "connectivity_modifications", "stimuli"):
        require(
            not value.get(field),
            field,
            "Figure 8 uses the retained dataset connectivity and per-neuron currents.",
        )
    for key, neuron in value["neurons"].get(GROUP, {}).items():
        require(
            not neuron.get("compartments") and not neuron.get("poisson_inputs"),
            f"neurons.{GROUP}.{key}",
            "Figure 8 supports point cells with direct currents only.",
        )
        require(
            set(neuron.get("parameter_overrides", {})) <= {"R_m"},
            f"neurons.{GROUP}.{key}.parameter_overrides",
            "Only the membrane resistance override is supported.",
        )
    return tuple(issues)


@dataclass(frozen=True)
class Network:
    ids: np.ndarray
    sources: np.ndarray
    targets: np.ndarray
    transmitters: np.ndarray
    weights: np.ndarray
    manifest: DatasetManifest


@dataclass(frozen=True)
class ConductanceDrive:
    targets: tuple[int, ...]
    transmitter: str
    weight_ns: float
    times_ms: tuple[float, ...]


@dataclass(frozen=True)
class ChurginExecution:
    network: Network
    model_id: str
    parameters: dict[str, float]
    drives: tuple[ConductanceDrive, ...]


def prepare_execution(spec: ExperimentSpec) -> ChurginExecution:
    if is_figure8(spec):
        return ChurginExecution(load_network(), MODEL_ID, PARAMETERS, ())
    from .manc import prepare_execution as prepare_manc

    return prepare_manc(spec)


def load_network() -> Network:
    """Apply the retained cleaning policy to checksum-verified source rows."""
    root_value = os.environ.get("FLYBRIAN_FIGURE8_DATA_ROOT")
    if root_value is None:
        raise FileNotFoundError(
            "Set FLYBRIAN_FIGURE8_DATA_ROOT to the retained Figure 8 connectivity directory."
        )
    root = Path(root_value)
    manifest = DatasetManifest.from_dict(
        json.loads((Path(__file__).parent / "data/figure8-dataset.json").read_text())
    )
    frame = load_clean_connectivity(root, manifest)
    return network_from_frame(frame, np.union1d(frame.preId, frame.postId), manifest)


def load_clean_connectivity(root: Path, manifest: DatasetManifest) -> pd.DataFrame:
    """Read verified connectivity files with the shared missing/unknown-row policy."""
    verified = manifest.verify(root)
    columns = [
        "preId",
        "postId",
        "preType",
        "postType",
        "preInstance",
        "postInstance",
        "preNt",
        "postNt",
        "total_weight",
    ]
    frame = pd.concat(
        [
            pd.read_csv(root / item.path, usecols=columns)
            for item in verified.manifest.files
            if item.role == "connectivity"
        ],
        ignore_index=True,
    )
    frame = frame.dropna(subset=columns[:-1])
    for column in ("preNt", "postNt"):
        frame = frame[frame[column].str.lower().str.strip() != "unknown"]
    for column in ("preId", "postId"):
        frame[column] = pd.to_numeric(frame[column], errors="raise").astype("int64")
    return frame


def network_from_frame(frame: pd.DataFrame, ids: np.ndarray, manifest: DatasetManifest) -> Network:
    """Aggregate biological edges while retaining the caller's declared population."""
    edges = frame.groupby(
        ["preId", "postId", "preNt"], as_index=False, sort=True
    ).total_weight.sum()
    types = edges.preNt.str.lower().str.strip().map({"acetylcholine": 0, "gaba": 1, "glutamate": 2})
    if types.isna().any():
        raise ValueError("Retained connectivity contains an unsupported transmitter.")
    return Network(
        ids,
        np.searchsorted(ids, edges.preId),
        np.searchsorted(ids, edges.postId),
        types.to_numpy(dtype=np.int8),
        edges.total_weight.to_numpy(dtype=float),
        manifest,
    )


def current_schedule(current: dict[str, Any], duration: float) -> list[tuple[float, float, float]]:
    start, stop = float(current["start_time"]), min(float(current["end_time"]), duration)
    if stop <= start:
        return []
    frequency, width = float(current["frequency"]), float(current["duration"])
    if frequency <= 0 or width <= 0:
        return [(start, stop, float(current["amplitude"]))]
    period = 1000 / frequency
    return [
        (float(t), min(float(t) + width, stop), float(current["amplitude"]))
        for t in np.arange(start, stop, period)
    ]


def recording_ids(spec: ExperimentSpec, network: Network) -> list[int]:
    explicit = {
        int(key)
        for key, neuron in spec.value["neurons"][GROUP].items()
        if neuron["record_variables"]
    }
    count = max(
        len(explicit), int(len(network.ids) * spec.value.get("record_fraction_variables", 0))
    )
    remaining = np.array([int(nid) for nid in network.ids if int(nid) not in explicit])
    rng = np.random.RandomState(int(spec.value["random_seed"]))
    return sorted(
        explicit | set(map(int, rng.choice(remaining, count - len(explicit), replace=False)))
    )


def write_result(
    spec: ExperimentSpec,
    execution: ChurginExecution,
    run_dir: Path,
    backend_id: str,
    backend_version: str,
    spikes: list[dict[str, Any]],
    series: list[dict[str, Any]],
) -> ArtifactManifest:
    network = execution.network
    recorded = recorded_spike_ids(spec.value, network.ids)
    warnings = (
        []
        if len(recorded) == len(network.ids)
        else [
            f"Spike output covers {len(recorded)} of {len(network.ids)} simulated cells, "
            "selected by record_spikes."
        ]
    )
    duration = execution_duration_ms(spec)
    if duration != spec.value["sim_time_ms"]:
        warnings.append(
            "Closed-loop execution completes whole windows: "
            f"requested {spec.value['sim_time_ms']} ms, executed {duration:g} ms."
        )
    result = dict(
        schema_version="1.0",
        run_id=run_dir.name,
        backend_id=backend_id,
        backend_version=backend_version,
        engine_version=__version__,
        experiment_sha256=spec.sha256(),
        network=dict(neurons=len(network.ids), connections=len(network.sources)),
        neurons=[
            dict(neuron_id=int(nid), family="lif", model_id=execution.model_id)
            for nid in network.ids
        ],
        simulation=dict(
            duration_seconds=duration / 1000,
            random_seed=spec.value["random_seed"],
            time_step_seconds=0.0001,
        ),
        spikes=sorted(
            (spike for spike in spikes if spike["neuron_id"] in recorded),
            key=lambda x: (x["time_seconds"], x["neuron_id"]),
        ),
        series=sorted(
            series, key=lambda x: (x["neuron_id"], x["compartment_id"] or "", x["variable"])
        ),
        warnings=warnings,
    )
    path = run_dir / "standardized-results.json"
    validated = validate_standardized_results(result)
    # Compact serialization keeps fractional state recordings practical to transport lazily.
    with path.open("w") as out:
        json.dump(validated.value, out, separators=(",", ":"), allow_nan=False)
    artifact = Artifact.from_file(
        key="standardized_results",
        kind="standardized_results",
        media_type="application/json",
        path=path,
        root=run_dir,
    )
    artifacts = [artifact]
    if execution.drives:
        input_path = run_dir / "input-events.json"
        input_path.write_text(
            json.dumps(
                [
                    dict(
                        targets=drive.targets,
                        transmitter=drive.transmitter,
                        weight_ns=drive.weight_ns,
                        times_ms=drive.times_ms,
                    )
                    for drive in execution.drives
                ],
                separators=(",", ":"),
                allow_nan=False,
            )
        )
        artifacts.append(
            Artifact.from_file(
                key="input_events",
                kind="stimulus_events",
                media_type="application/json",
                path=input_path,
                root=run_dir,
            )
        )
    manifest = ArtifactManifest(
        run_id=run_dir.name,
        engine_version=__version__,
        backend_id=backend_id,
        backend_version=backend_version,
        experiment_spec_version="1.0",
        experiment_sha256=spec.sha256(),
        random_seed=spec.value["random_seed"],
        datasets=(
            DatasetReference(
                dataset_id=network.manifest.dataset_id, sha256=network.manifest.sha256()
            ),
        ),
        scientific_execution=True,
        deterministic_for_fixed_seed=True,
        artifacts=tuple(artifacts),
        dispositions=tuple(
            ArtifactDisposition(kind=item.kind, status="available", artifact_keys=(item.key,))
            for item in artifacts
        ),
    )
    manifest.write(run_dir / "manifest.json")
    return manifest


def run_brian2(spec: ExperimentSpec, output_dir: Path, run_id: str) -> ArtifactManifest:
    from importlib.metadata import version

    import brian2 as b

    execution = prepare_execution(spec)
    network = execution.network
    run_dir = output_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    b.start_scope()
    b.seed(int(spec.value["random_seed"]))
    b.prefs.codegen.target = "numpy"
    clock = b.Clock(dt=0.1 * b.ms)
    p = execution.parameters
    group = b.NeuronGroup(
        len(network.ids),
        "\n    dv/dt = (-(v-v_rest)/tau_m + "
        "(g_ace*(e_ace-v)+g_gab*(e_gab-v)+g_glu*(e_glu-v)+I_ext)/C_m) : volt (unless refractory)"
        """
    dg_ace/dt = -g_ace/tau_ace : siemens
    dg_gab/dt = -g_gab/tau_gab : siemens
    dg_glu/dt = -g_glu/tau_glu : siemens
    I_ext : amp
    tau_m : second
    """,
        threshold="v > v_threshold",
        reset="v = v_reset",
        refractory=p["refractory"] * b.ms,
        method="euler",
        clock=clock,
        namespace=dict(
            v_rest=p["v_rest"] * b.mV,
            v_reset=p["v_reset"] * b.mV,
            v_threshold=p["v_threshold"] * b.mV,
            e_ace=p["e_ace"] * b.mV,
            e_gab=p["e_gab"] * b.mV,
            e_glu=p["e_glu"] * b.mV,
            C_m=p["capacitance"] * b.pF,
            tau_ace=p["tau_ace"] * b.ms,
            tau_gab=p["tau_gab"] * b.ms,
            tau_glu=p["tau_glu"] * b.ms,
        ),
    )
    group.v = p["v_rest"] * b.mV
    group.tau_m = p["resistance"] * b.Mohm * p["capacitance"] * b.pF
    net = b.Network(group)
    schedules = []
    for key, neuron in spec.value["neurons"][GROUP].items():
        index = int(np.searchsorted(network.ids, int(key)))
        if index >= len(network.ids) or network.ids[index] != int(key):
            raise ValueError(f"Neuron {key} is absent from the retained network")
        group.tau_m[index] = (
            neuron.get("parameter_overrides", {}).get("R_m", p["resistance"])
            * b.Mohm
            * p["capacitance"]
            * b.pF
        )
        for current in neuron["external_currents"]:
            schedules.append((index, current_schedule(current, spec.value["sim_time_ms"])))
    feedback = np.zeros(len(network.ids))

    def update_current(t):
        time = float(t / b.ms)
        group.I_ext = feedback * b.nA
        for index, intervals in schedules:
            group.I_ext[index] += (
                sum(amp for start, stop, amp in intervals if start <= time < stop) * b.nA
            )

    net.add(b.NetworkOperation(update_current, clock=clock, when="start", order=-1))
    for code, name in enumerate(("ace", "gab", "glu")):
        mask = network.transmitters == code
        if not mask.any():
            continue
        syn = b.Synapses(
            group, group, model="weight : siemens", on_pre=f"g_{name}_post += weight", clock=clock
        )
        syn.connect(i=network.sources[mask], j=network.targets[mask])
        syn.weight = network.weights[mask] * p["j_" + name] * b.nS
        net.add(syn)
    if execution.drives:
        event_sources = [
            index for index, drive in enumerate(execution.drives) for _ in drive.times_ms
        ]
        event_times = [time for drive in execution.drives for time in drive.times_ms]
        source = b.SpikeGeneratorGroup(
            len(execution.drives),
            np.array(event_sources, dtype=int),
            np.array(event_times) * b.ms,
            clock=clock,
        )
        net.add(source)
        for name in ("ace", "gab", "glu"):
            links = [
                (index, int(np.searchsorted(network.ids, target)), drive.weight_ns)
                for index, drive in enumerate(execution.drives)
                if drive.transmitter == name
                for target in drive.targets
            ]
            if not links:
                continue
            source_ids, target_ids, weights = zip(*links, strict=True)
            syn = b.Synapses(
                source,
                group,
                model="weight : siemens",
                on_pre=f"g_{name}_post += weight",
                clock=clock,
            )
            syn.connect(i=np.array(source_ids), j=np.array(target_ids))
            syn.weight = np.array(weights) * b.nS
            net.add(syn)
    spike = b.SpikeMonitor(group)
    ids = recording_ids(spec, network)
    state = b.StateMonitor(
        group,
        ["v", "g_ace", "g_gab", "g_glu", "I_ext"],
        record=np.searchsorted(network.ids, ids),
        clock=clock,
    )
    net.add(spike, state)
    body = None
    if spec.embodiment_mode == "none":
        net.run(spec.value["sim_time_ms"] * b.ms)
    else:
        id_to_index = {int(nid): index for index, nid in enumerate(network.ids)}

        def advance(stop_ms):
            net.run((stop_ms - float(net.t / b.ms)) * b.ms)

        def window_spikes(start, stop):
            times = np.asarray(spike.t / b.second)
            indices = np.asarray(spike.i)
            selected = (times >= start) & (times < stop)
            output = {}
            for index, time in zip(indices[selected], times[selected], strict=True):
                output.setdefault(str(network.ids[index]), []).append(float(time))
            return output

        def set_currents(currents):
            feedback[:] = 0
            for nid, current in currents.items():
                index = id_to_index.get(nid)
                if index is not None:
                    feedback[index] = current

        body = run_body(spec, advance, window_spikes, set_currents)
    spikes = [
        dict(neuron_id=int(network.ids[i]), time_seconds=float(t))
        for i, t in zip(spike.i, spike.t / b.second, strict=True)
    ]
    series = []
    times = (state.t / b.second).tolist()
    for name, variable, unit, quantity in [
        ("v", "membrane_potential", "V", b.volt),
        ("g_ace", "g_ace", "S", b.siemens),
        ("g_gab", "g_gab", "S", b.siemens),
        ("g_glu", "g_glu", "S", b.siemens),
        ("I_ext", "external_current", "A", b.amp),
    ]:
        values = getattr(state, name) / quantity
        for row, nid in enumerate(ids):
            series.append(
                dict(
                    neuron_id=nid,
                    compartment_id=None,
                    variable=variable,
                    unit=unit,
                    times_seconds=times,
                    values=values[row].tolist(),
                )
            )
    manifest = write_result(spec, execution, run_dir, "brian2", version("brian2"), spikes, series)
    return manifest if body is None else attach_body_artifacts(spec, manifest, run_dir, body)
