"""Translate canonical figure intent into the existing FlyBrian spike renderer."""

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any

from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from .figure_style import FigurePanel, FigureStyleSpec

_MARKERS = {
    "circle": "o",
    "square": "s",
    "diamond": "D",
    "triangle_up": "^",
    "triangle_down": "v",
    "plus": "+",
    "x": "x",
}


def render_spike_raster_from_result(
    style: FigureStyleSpec,
    spike_times_seconds: dict[str, list[float]],
    sim_time_ms: float,
    output_dir: Path,
) -> dict[str, str]:
    """Render the supported raster panel from stored observations."""
    unsupported = [panel.kind for panel in style.panels if panel.kind != "spike_raster"]
    if unsupported:
        raise ValueError(
            "This result can regenerate spike_raster panels only; missing retained series for "
            + ", ".join(sorted(set(unsupported)))
        )
    if len(style.panels) != 1:
        raise ValueError(
            "Figure Style Specification 0.1 regeneration currently accepts one spike_raster panel"
        )

    panel = style.panels[0]
    neuron_ids = [neuron_id for rule in panel.series for neuron_id in rule.neuron_ids]
    figure = Figure(figsize=(panel.canvas.width_inches, panel.canvas.height_inches))
    FigureCanvasAgg(figure)
    axis = figure.subplots()
    id2idx = {neuron_id: index for index, neuron_id in enumerate(neuron_ids)}
    for rule in panel.series:
        times: list[float] = []
        rows: list[int] = []
        for neuron_id in rule.neuron_ids:
            values = spike_times_seconds.get(str(neuron_id), [])
            times.extend(float(value) * 1000 for value in values)
            rows.extend([id2idx[neuron_id]] * len(values))
        axis.scatter(
            times,
            rows,
            c=rule.color,
            marker=_MARKERS[rule.marker],
            s=rule.marker_size,
            alpha=rule.opacity,
            label=rule.label,
        )
    axis.set_title(panel.title)
    if panel.legend.visible:
        axis.legend()
    axis.set_xlabel(panel.x_axis.label)
    axis.set_ylabel(panel.y_axis.label)
    axis.set_xlim(
        panel.x_axis.minimum,
        sim_time_ms if panel.x_axis.maximum is None else panel.x_axis.maximum,
    )
    if neuron_ids:
        axis.set_ylim(-0.5, len(neuron_ids) - 0.5)
        axis.set_yticks(range(len(neuron_ids)))
        axis.set_yticklabels([str(neuron_id) for neuron_id in neuron_ids])

    output_dir.mkdir(parents=True, exist_ok=True)
    filename = _output_filename(style, panel)
    figure.savefig(output_dir / filename, dpi=panel.canvas.dpi, bbox_inches="tight")
    return {filename: f"/files/{output_dir.name}/{filename}"}


def renderer_options(style: FigureStyleSpec, id2idx: dict[int, int]) -> dict[str, Any]:
    """Convert a canonical raster style for monitors that already exist."""
    panel = next(
        (candidate for candidate in style.panels if candidate.kind == "spike_raster"), None
    )
    if panel is None:
        return {}
    neuron_ids = [
        neuron_id for rule in panel.series for neuron_id in rule.neuron_ids if neuron_id in id2idx
    ]
    return {
        "title": panel.title,
        "highlight_neuron_ids": neuron_ids,
        "manual_styles": _renderer_styles(panel, id2idx),
        "use_enhanced_styles": True,
        "show_neuron_legend": panel.legend.visible,
        "figsize": (panel.canvas.width_inches, panel.canvas.height_inches),
    }


def _renderer_styles(panel: FigurePanel, id2idx: dict[int, int]) -> dict[int, dict[str, object]]:
    return {
        id2idx[neuron_id]: {
            "color": rule.color,
            "marker": _MARKERS[rule.marker],
            "size": rule.marker_size,
            "alpha": rule.opacity,
            "fill_style": "full",
        }
        for rule in panel.series
        for neuron_id in rule.neuron_ids
        if neuron_id in id2idx
    }


def _output_filename(style: FigureStyleSpec, panel: FigurePanel) -> str:
    canonical = json.dumps(style.model_dump(), sort_keys=True, separators=(",", ":"))
    identity = sha256(canonical.encode("utf-8")).hexdigest()[:10]
    slug = re.sub(r"[^a-z0-9]+", "-", style.name.lower()).strip("-") or "figure-style"
    return f"{slug}--{panel.id}--{identity}.png"


def render_standardized_figures(
    spec: dict[str, Any], result: dict[str, Any], output_dir: Path
) -> dict[str, str]:
    """Use one plotting path for every scientific backend's stored observations."""
    extension = spec.get("extensions", {}).get("org.flybrian.figure_styles", {})
    preset = next(
        (
            item
            for item in extension.get("presets", [])
            if item["preset_id"] == extension.get("default_preset_id")
        ),
        None,
    )
    files = {}
    if preset is not None:
        spikes: dict[str, list[float]] = {}
        for spike in result["spikes"]:
            spikes.setdefault(str(spike["neuron_id"]), []).append(spike["time_seconds"])
        files.update(
            render_spike_raster_from_result(
                FigureStyleSpec.model_validate(preset["style"]),
                spikes,
                result["simulation"]["duration_seconds"] * 1000,
                output_dir,
            )
        )
    requested: set[tuple[int, str | None, str]] = set()
    for group_id, cells in spec["neurons"].items():
        model = spec.get("neuron_models", {}).get(group_id, {})
        variable = "rate" if model.get("family") == "rate" else "membrane_potential"
        for key, cell in cells.items():
            if cell.get("record_variables"):
                compartments = (
                    cell["compartments"] if model.get("family") == "compartmental" else [None]
                )
                requested.update((int(key), compartment, variable) for compartment in compartments)

    def identity(series: dict[str, Any]) -> tuple[int, str | None, str]:
        return series["neuron_id"], series["compartment_id"], series["variable"]

    traces = [series for series in result["series"] if identity(series) in requested]
    if {identity(series) for series in traces} != requested:
        raise ValueError("A requested state trace is missing from the standardized result")
    for variable, title, unit, scale, filename in [
        ("membrane_potential", "Membrane potential", "mV", 1000, "membrane-potential.png"),
        ("rate", "Firing rate", "Hz", 1, "firing-rate.png"),
    ]:
        selected = [series for series in traces if series["variable"] == variable]
        if not selected:
            continue
        figure = Figure(figsize=(8, 4))
        FigureCanvasAgg(figure)
        axis = figure.subplots()
        for series in selected:
            label = f"Neuron {series['neuron_id']}"
            if series["compartment_id"] is not None:
                label += f" · {series['compartment_id']}"
            axis.plot(
                [t * 1000 for t in series["times_seconds"]],
                [v * scale for v in series["values"]],
                label=label,
            )
        axis.set(xlabel="Time (ms)", ylabel=f"{title} ({unit})", title=title)
        axis.legend()
        figure.tight_layout()
        figure.savefig(output_dir / filename, dpi=150)
        files[filename] = f"/files/{output_dir.name}/{filename}"
    return files
