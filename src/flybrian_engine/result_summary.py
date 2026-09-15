"""One scientific summary projection for local and hosted results."""

from collections import Counter
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .artifacts import ArtifactManifest
from .schema import ExperimentSpec


def recorded_spike_ids(spec: dict[str, Any], neuron_ids: Iterable[int]) -> set[int]:
    if (
        spec.get("extensions", {}).get("org.flybrian.execution", {}).get("profile")
        == "figure8_fes_v1"
    ):
        return set(map(int, neuron_ids))
    return {
        int(key)
        for group in spec["neurons"].values()
        for key, cell in group.items()
        if cell.get("record_spikes")
    }


def summarize_result(spec: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    counts = Counter(str(spike["neuron_id"]) for spike in result["spikes"])
    neurons = result["network"]["neurons"]
    duration = result["simulation"]["duration_seconds"]
    recorded = recorded_spike_ids(spec, (cell["neuron_id"] for cell in result["neurons"]))
    return {
        "total_spikes": len(result["spikes"]),
        "recorded_neuron_spikes": {
            str(key): counts[str(key)]
            for group in spec["neurons"].values()
            for key, cell in group.items()
            if cell.get("record_spikes")
        },
        "active_neurons": len(counts),
        "activity_fraction": len(counts) / len(recorded) if recorded else None,
        "avg_firing_rate_hz": len(result["spikes"]) / len(recorded) / duration
        if recorded
        else None,
        "num_recorded_neurons": len(recorded),
        "num_neurons": neurons,
        "num_synapses": result["network"]["connections"],
    }


def present_result(
    spec: ExperimentSpec, manifest: ArtifactManifest, run_root: Path
) -> ArtifactManifest:
    """Attach the common plots and summary to every scientific backend's manifest."""
    if not manifest.scientific_execution:
        return manifest
    import json
    from dataclasses import replace

    from .artifacts import Artifact, ArtifactDisposition
    from .figure_rendering import render_standardized_figures
    from .results import validate_standardized_results

    source = next(item for item in manifest.artifacts if item.kind == "standardized_results")
    result = validate_standardized_results(
        json.loads((run_root / source.relative_path).read_text())
    ).value
    files = render_standardized_figures(spec.value, result, run_root)
    summary_path = run_root / "run-summary.json"
    summary = summarize_result(spec.value, result)
    body_artifact = next(
        (item for item in manifest.artifacts if item.kind == "body_execution"), None
    )
    if body_artifact is not None:
        body = json.loads((run_root / body_artifact.relative_path).read_text())
        summary.update(
            qpos_frame_interval_ms=body["qpos_frame_interval_ms"],
            requested_duration_ms=body["requested_duration_ms"],
            executed_duration_ms=body["executed_duration_ms"],
            embodiment=body,
        )
    summary_path.write_text(json.dumps(summary, allow_nan=False))
    presentation = [
        Artifact.from_file(
            key="run_summary",
            kind="summary",
            media_type="application/json",
            path=summary_path,
            root=run_root,
        )
    ]
    for name in files:
        presentation.append(
            Artifact.from_file(
                key=name, kind="plot", media_type="image/png", path=run_root / name, root=run_root
            )
        )
    dispositions = tuple(
        ArtifactDisposition(
            kind=kind,
            status="available",
            artifact_keys=tuple(item.key for item in presentation if item.kind == kind),
        )
        for kind in dict.fromkeys(item.kind for item in presentation)
    )
    completed = replace(
        manifest,
        artifacts=(*manifest.artifacts, *presentation),
        dispositions=(*manifest.dispositions, *dispositions),
    )
    completed.write(run_root / "manifest.json")
    return completed
