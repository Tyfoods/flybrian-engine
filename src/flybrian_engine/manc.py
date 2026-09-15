"""Verified ordinary MANC circuit input, preserving the hosted population policy."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .backends import CompatibilityIssue
from .body_execution import compatibility_issues as body_issues
from .body_execution import execution_duration_ms
from .datasets import DatasetManifest
from .figure8 import (
    GROUP,
    ChurginExecution,
    ConductanceDrive,
    Network,
    load_clean_connectivity,
    network_from_frame,
)
from .model_catalog import MANC_MODEL, MANC_PARAMETERS
from .schema import ExperimentSpec

MODEL_ID = MANC_MODEL.model_id
PARAMETERS = MANC_PARAMETERS
TRANSMITTERS = {
    "ace": "ace",
    "acetylcholine": "ace",
    "gaba": "gab",
    "glu": "glu",
    "glutamate": "glu",
}


def is_manc(spec: ExperimentSpec) -> bool:
    return (
        "neuron_models" not in spec.value
        and spec.value["dataset"] == "manc:v1.2.1"
        and set(spec.value["neurons"]) == {GROUP}
        and spec.value.get("extensions", {}).get("org.flybrian.execution", {}).get("profile")
        in (None, "detailed_v1")
    )


def compatibility_issues(spec: ExperimentSpec) -> tuple[CompatibilityIssue, ...]:
    value = spec.value
    issues = []

    def require(condition: bool, path: str, message: str) -> None:
        if not condition:
            issues.append(CompatibilityIssue("unsupported_manc_semantics", path, message))

    require(
        is_manc(spec), "dataset", "This adapter requires the ordinary MANC Churgin point circuit."
    )
    require(
        value.get("simulation")
        in (None, {"integration_method": "euler", "time_step": {"value": 0.1, "unit": "ms"}}),
        "simulation",
        "Ordinary Churgin execution uses forward Euler at 0.1 ms.",
    )
    require(
        not value.get("population_assignments"),
        "population_assignments",
        "This adapter uses explicitly configured cells.",
    )
    for field in ("poisson_background_rate", "poisson_background_weight"):
        number = value.get(field, 0)
        require(
            isinstance(number, (int, float))
            and not isinstance(number, bool)
            and math.isfinite(number)
            and number >= 0,
            field,
            "Background rate and weight must be finite nonnegative numbers.",
        )
    rate = value.get("poisson_background_rate", 0)
    require(
        isinstance(rate, (int, float)) and not isinstance(rate, bool) and rate <= 10000,
        "poisson_background_rate",
        "Independent background input permits at most one event per 0.1 ms step.",
    )
    exclusions = value.get("poisson_background_exclude_ids", [])
    require(
        isinstance(exclusions, list)
        and all(isinstance(nid, int) and not isinstance(nid, bool) for nid in exclusions),
        "poisson_background_exclude_ids",
        "Background exclusions must be neuron IDs.",
    )
    require(
        value.get("external_current_background_amplitude", 0) == 0,
        "external_current_background_amplitude",
        "Background current migration is still pending.",
    )
    for field in ("connections", "connectivity_modifications", "stimuli"):
        require(
            not value.get(field),
            field,
            "This adapter uses dataset connectivity and per-cell inputs.",
        )
    issues.extend(body_issues(spec))
    require(
        value.get("record_fraction_spikes", 0) == 0,
        "record_fraction_spikes",
        "Ordinary MANC spike recording currently requires explicit per-cell flags.",
    )
    for key, cell in value["neurons"].get(GROUP, {}).items():
        require(
            not cell.get("compartments"),
            f"neurons.{GROUP}.{key}",
            "This adapter supports point cells.",
        )
        require(
            set(cell.get("parameter_overrides", {})) <= {"R_m"},
            f"neurons.{GROUP}.{key}.parameter_overrides",
            "Only membrane resistance overrides are supported.",
        )
        for index, stimulus in enumerate(cell.get("poisson_inputs", [])):
            valid = all(
                isinstance(stimulus.get(field), (int, float))
                and not isinstance(stimulus.get(field), bool)
                and math.isfinite(stimulus[field])
                and stimulus[field] >= 0
                for field in ("rate", "weight")
            )
            require(
                valid and str(stimulus.get("nt_type", "")).lower() in TRANSMITTERS,
                f"neurons.{GROUP}.{key}.poisson_inputs[{index}]",
                "Poisson inputs require a finite nonnegative rate/weight and known transmitter.",
            )
    return tuple(issues)


def prepare_execution(spec: ExperimentSpec) -> ChurginExecution:
    issues = compatibility_issues(spec)
    if issues:
        raise ValueError("; ".join(issue.message for issue in issues))
    root = os.environ.get("FLYBRIAN_MANC_DATA_ROOT")
    if root is None:
        raise FileNotFoundError(
            "Set FLYBRIAN_MANC_DATA_ROOT to the three-part MANC dataset "
            "and correction file directory."
        )
    grouped: dict[tuple[float, float, str], list[int]] = {}
    for key, cell in spec.value["neurons"][GROUP].items():
        for stimulus in cell.get("poisson_inputs", []):
            signature = (
                float(stimulus["rate"]),
                float(stimulus["weight"]),
                str(stimulus["nt_type"]).lower(),
            )
            grouped.setdefault(signature, []).append(int(key))
    network = load_manc_network(spec, Path(root))
    drives = realize_conductance_drives(spec, network.ids, grouped)
    return ChurginExecution(network, MODEL_ID, PARAMETERS, drives)


def realize_conductance_drives(
    spec: ExperimentSpec, ids: np.ndarray, grouped: dict[tuple[float, float, str], list[int]]
) -> tuple[ConductanceDrive, ...]:
    sources = [
        (rate, weight, TRANSMITTERS[nt], tuple(targets))
        for (rate, weight, nt), targets in grouped.items()
    ]
    rate = spec.value.get("poisson_background_rate", 0)
    weight = spec.value.get("poisson_background_weight", 0)
    excluded = set(spec.value.get("poisson_background_exclude_ids", [])) & set(ids.tolist())
    independent = rate > 0 and not excluded
    if rate > 0 and excluded:
        included = tuple(int(nid) for nid in ids if nid not in excluded)
        if included:
            sources.append((rate, weight, "ace", included))
    events: list[list[float]] = [[] for _ in sources]
    background_events: list[list[float]] = [[] for _ in ids] if independent else []
    # Brian2 schedules the thresholder objects by name, then PoissonInput
    # draws one independent binomial sample per cell in the synapses slot.
    order = sorted(
        range(len(sources)),
        key=lambda index: (
            (f"poissongroup_{index}" if index else "poissongroup") + "_spike_thresholder"
        ),
    )
    rng = np.random.RandomState(int(spec.value["random_seed"]))
    for step in range(math.ceil(execution_duration_ms(spec) / 0.1)):
        time = float(step) * 0.1
        for draw, index in zip(rng.random_sample(len(sources)), order, strict=True):
            if draw < sources[index][0] * 0.0001:
                events[index].append(time)
        if independent:
            for index in np.flatnonzero(rng.binomial(1, rate * 0.0001, len(ids))):
                background_events[index].append(time)
    drives = [
        ConductanceDrive(targets, nt, weight, tuple(times))
        for (_, weight, nt, targets), times in zip(sources, events, strict=True)
    ]
    drives.extend(
        ConductanceDrive((int(nid),), "ace", weight, tuple(times))
        for nid, times in zip(ids, background_events, strict=False)
    )
    return tuple(drives)


def load_manc_network(spec: ExperimentSpec, root: Path) -> Network:
    if spec.value["dataset"] != "manc:v1.2.1" or set(spec.value["neurons"]) != {GROUP}:
        raise ValueError("Ordinary MANC input requires a MANC Churgin circuit.")
    manifest = DatasetManifest.from_dict(
        json.loads((Path(__file__).parent / "data/manc-dataset.json").read_text())
    )
    frame = load_clean_connectivity(root, manifest)
    corrections = json.loads((root / "nt_corrections.json").read_text())
    for key, entry in corrections.items():
        for endpoint in ("pre", "post"):
            frame.loc[frame[f"{endpoint}Id"] == int(key), f"{endpoint}Nt"] = entry["corrected_nt"]
    ids = np.array(sorted(int(key) for key in spec.value["neurons"][GROUP]), dtype=np.int64)
    selected = frame[frame.preId.isin(ids) & frame.postId.isin(ids)]
    isolated = np.setdiff1d(ids, np.union1d(selected.preId, selected.postId))
    # The hosted builder uses zero-weight self-edges to keep isolated configured
    # cells. Preserve them for both simulation population and connection counts.
    placeholders = pd.DataFrame(
        {"preId": isolated, "postId": isolated, "preNt": "acetylcholine", "total_weight": 0.0}
    )
    return network_from_frame(pd.concat([selected, placeholders], ignore_index=True), ids, manifest)
