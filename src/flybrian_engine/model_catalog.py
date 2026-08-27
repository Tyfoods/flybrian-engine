"""Versioned simulator-neutral model definitions used by public adapters."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ParameterDefinition:
    dimension: str


@dataclass(frozen=True)
class ModelDefinition:
    model_id: str
    family: str
    parameters: dict[str, ParameterDefinition]
    compartment_ids: tuple[str, ...] = ()
    supports_spikes: bool = False


PUBLIC_MODEL_DEFINITIONS: dict[str, ModelDefinition] = {
    "lif.basic.v1": ModelDefinition(
        model_id="lif.basic.v1",
        family="lif",
        supports_spikes=True,
        parameters={
            "initial_v": ParameterDefinition("voltage"),
            "refractory_period": ParameterDefinition("time"),
            "resistance": ParameterDefinition("resistance"),
            "tau_m": ParameterDefinition("time"),
            "v_reset": ParameterDefinition("voltage"),
            "v_rest": ParameterDefinition("voltage"),
            "v_threshold": ParameterDefinition("voltage"),
        },
    ),
    "rate.first_order.v1": ModelDefinition(
        model_id="rate.first_order.v1",
        family="rate",
        parameters={
            "gain": ParameterDefinition("dimensionless"),
            "initial_rate": ParameterDefinition("rate"),
            "tau": ParameterDefinition("time"),
        },
    ),
    "compartmental.passive_two.v1": ModelDefinition(
        model_id="compartmental.passive_two.v1",
        family="compartmental",
        compartment_ids=("dendrite", "soma"),
        parameters={
            "capacitance_dendrite": ParameterDefinition("capacitance"),
            "capacitance_soma": ParameterDefinition("capacitance"),
            "coupling_conductance": ParameterDefinition("conductance"),
            "initial_v_dendrite": ParameterDefinition("voltage"),
            "initial_v_soma": ParameterDefinition("voltage"),
            "leak_conductance_dendrite": ParameterDefinition("conductance"),
            "leak_conductance_soma": ParameterDefinition("conductance"),
            "v_rest": ParameterDefinition("voltage"),
        },
    ),
}


UNIT_DIMENSIONS: dict[str, str] = {
    "1": "dimensionless",
    "A": "current",
    "Hz": "rate",
    "Mohm": "resistance",
    "V": "voltage",
    "ms": "time",
    "mV": "voltage",
    "nA": "current",
    "nS": "conductance",
    "pA": "current",
    "pF": "capacitance",
    "s": "time",
    "uA": "current",
    "us": "time",
}


def public_model_ids() -> tuple[str, ...]:
    return tuple(sorted(PUBLIC_MODEL_DEFINITIONS))
