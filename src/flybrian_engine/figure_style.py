"""Canonical FlyBrian Figure Style Specification v0.1."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

FigurePanelKind = Literal["spike_raster", "membrane_potential", "external_current"]
FigureMarker = Literal["circle", "square", "diamond", "triangle_up", "triangle_down", "plus", "x"]


class FigureCanvas(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width_inches: float = Field(gt=0, le=100)
    height_inches: float = Field(gt=0, le=200)
    dpi: int = Field(gt=0, le=1200)


class FigureXAxis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    minimum: float
    maximum: float | None = None

    @model_validator(mode="after")
    def range_is_ordered(self):
        if self.maximum is not None and self.maximum <= self.minimum:
            raise ValueError("x_axis.maximum must be greater than x_axis.minimum")
        return self


class FigureYAxis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    mode: Literal["selected"]


class FigureLegend(BaseModel):
    model_config = ConfigDict(extra="forbid")

    visible: bool
    position: Literal["right"]


class FigureSeriesRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    neuron_ids: list[int] = Field(min_length=1)
    color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    marker: FigureMarker
    marker_size: float = Field(gt=0, le=500)
    opacity: float = Field(ge=0, le=1)


class FigurePanel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    kind: FigurePanelKind
    title: str
    canvas: FigureCanvas
    x_axis: FigureXAxis
    y_axis: FigureYAxis
    legend: FigureLegend
    series: list[FigureSeriesRule] = Field(min_length=1)

    @model_validator(mode="after")
    def neuron_rules_do_not_overlap(self):
        seen = set()
        for rule in self.series:
            overlap = seen.intersection(rule.neuron_ids)
            if overlap:
                raise ValueError(
                    f"neuron IDs may appear in only one series rule: {sorted(overlap)}"
                )
            seen.update(rule.neuron_ids)
        return self


class FigureStyleSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    spec_version: Literal["0.1"]
    name: str = Field(min_length=1)
    description: str = ""
    panels: list[FigurePanel] = Field(min_length=1)


class FigureRegenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    style: FigureStyleSpec
