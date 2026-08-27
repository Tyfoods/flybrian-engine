"""Reviewed, non-executing selection profile for the historical C174 experiment."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation

from .historical_envelopes import (
    ControllerStageKind,
    HistoricalControllerPhase,
    HistoricalControllerProfile,
    HistoricalControllerStage,
    HistoricalExperimentEnvelope,
    HistoricalLineage,
    HistoricalOptionResolution,
    HistoricalParameter,
    HistoricalSourceAuthority,
    HistoricalVariationPatch,
    OptionApplication,
    OptionOrigin,
    OptionValueKind,
)


class C174ResolutionError(ValueError):
    """The requested C174 selector or option set is not statically resolvable."""


def _canonical_value(value: object) -> object:
    if isinstance(value, Decimal):
        normalized = value.normalize()
        if normalized == 0:
            return "0"
        text = format(normalized, "f")
        return text.rstrip("0").rstrip(".") if "." in text else text
    if isinstance(value, tuple | list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, Mapping):
        return {key: _canonical_value(item) for key, item in value.items()}
    return value


def _sha256(value: object) -> str:
    payload = json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(payload).hexdigest()


def _decimal(value: object, path: str) -> Decimal:
    if isinstance(value, (bool, float)) or not isinstance(value, (Decimal, int, str)):
        raise C174ResolutionError(f"{path} must be an exact finite decimal")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise C174ResolutionError(f"{path} must be an exact finite decimal") from error
    if not result.is_finite():
        raise C174ResolutionError(f"{path} must be finite")
    return result


@dataclass(frozen=True)
class C174OptionDefinition:
    option_id: str
    legacy_name: str
    value_kind: OptionValueKind
    unit: str | None
    default_value: object
    source_line: int
    target: str
    resolution_rule: str
    choices: tuple[str, ...] = ()
    arity: int | None = None

    def __post_init__(self) -> None:
        if not self.option_id.startswith(("c174.", "simulation.")):
            raise C174ResolutionError("C174 option ID must be namespaced")
        if not self.legacy_name.startswith("--"):
            raise C174ResolutionError("C174 legacy option must start with --")
        if self.source_line <= 0:
            raise C174ResolutionError("C174 source line must be positive")
        if not self.target.startswith("/"):
            raise C174ResolutionError("C174 option target must be a JSON pointer")
        if self.arity is not None and self.arity <= 0:
            raise C174ResolutionError("C174 option arity must be positive")
        _coerce_value(self, self.default_value, "default", allow_null=True)

    def to_dict(self) -> dict[str, object]:
        return {
            "option_id": self.option_id,
            "legacy_name": self.legacy_name,
            "value_kind": self.value_kind,
            "unit": self.unit,
            "default_value": _canonical_value(self.default_value),
            "source_line": self.source_line,
            "target": self.target,
            "resolution_rule": self.resolution_rule,
            "choices": list(self.choices),
            "arity": self.arity,
        }


@dataclass(frozen=True)
class C174ConfigSelector:
    selector: int
    mode: str
    coxa_active: bool
    label: str
    force_gain_override: Decimal | None
    angle_gain_override: Decimal | None

    def __post_init__(self) -> None:
        if isinstance(self.selector, bool) or not isinstance(self.selector, int):
            raise C174ResolutionError("C174 selector must be integer")
        if not self.mode or not self.label:
            raise C174ResolutionError("C174 selector mode and label must be non-empty")
        for name in ("force_gain_override", "angle_gain_override"):
            value = getattr(self, name)
            if value is not None and not isinstance(value, Decimal):
                raise C174ResolutionError(f"C174 selector {name} must be Decimal")

    def to_dict(self) -> dict[str, object]:
        return {
            "selector": self.selector,
            "mode": self.mode,
            "coxa_active": self.coxa_active,
            "label": self.label,
            "force_gain_override": _canonical_value(self.force_gain_override),
            "angle_gain_override": _canonical_value(self.angle_gain_override),
        }


def _coerce_value(
    definition: C174OptionDefinition,
    value: object,
    path: str,
    *,
    allow_null: bool,
) -> object:
    if value is None:
        if allow_null:
            return None
        raise C174ResolutionError(f"{path} must not be null")
    kind = definition.value_kind
    if kind == "boolean":
        if not isinstance(value, bool):
            raise C174ResolutionError(f"{path} must be boolean")
        result: object = value
    elif kind == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise C174ResolutionError(f"{path} must be integer")
        result = value
    elif kind == "decimal":
        result = _decimal(value, path)
    elif kind == "text":
        if not isinstance(value, str) or not value:
            raise C174ResolutionError(f"{path} must be text")
        result = value
    elif kind in {"decimal_list", "text_list"}:
        if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
            raise C174ResolutionError(f"{path} must be a list")
        if definition.arity is not None and len(value) != definition.arity:
            raise C174ResolutionError(f"{path} has invalid arity")
        if kind == "decimal_list":
            result = tuple(_decimal(item, f"{path} item") for item in value)
        else:
            if not all(isinstance(item, str) and item for item in value):
                raise C174ResolutionError(f"{path} must contain text segments")
            result = tuple(value)
            if definition.legacy_name == "--zero-coxa-segs" and not result:
                raise C174ResolutionError(f"{path} must contain at least one segment")
    elif kind == "null":
        raise C174ResolutionError(f"{path} must be null")
    else:
        raise C174ResolutionError(f"{path} has unsupported value kind")
    if definition.choices:
        values = result if isinstance(result, tuple) else (result,)
        if any(item not in definition.choices for item in values):
            noun = "segment" if definition.legacy_name == "--zero-coxa-segs" else "choice"
            raise C174ResolutionError(f"{path} contains invalid {noun}")
    return result


def _definition(
    option_id: str,
    legacy_name: str,
    value_kind: OptionValueKind,
    unit: str | None,
    default_value: object,
    source_line: int,
    target: str,
    resolution_rule: str = "c174.declared-default.v1",
    *,
    choices: tuple[str, ...] = (),
    arity: int | None = None,
) -> C174OptionDefinition:
    return C174OptionDefinition(
        option_id,
        legacy_name,
        value_kind,
        unit,
        default_value,
        source_line,
        target,
        resolution_rule,
        choices,
        arity,
    )


D = Decimal
C174_SOURCE_AUTHORITY = HistoricalSourceAuthority(
    repository="flybrian-serve",
    revision="d08d4a8cd20b44d54a583515ccb39586d505215d",
    logical_path="experiments/c174_phase1_per_muscle.py",
    byte_length=144_532,
    sha256="35b2cf1e2e18fe0ef512a567dc474c279a02c0f6f8cb08adbd990eb9c89f4038",
    license_id="proprietary-unpublished",
    access="private",
    redistribution="not-allowed",
    extractor_id="org.flybrian.static-python-extractor",
    extractor_version="1.1",
)

C174_OPTION_PROFILE = (
    _definition(
        "c174.selection.index",
        "--index",
        "integer",
        "1",
        None,
        2390,
        "/selector",
        "c174.selector.v1",
    ),
    _definition("simulation.seed", "--seed", "integer", "1", 42, 2391, "/random_seed"),
    _definition(
        "c174.neural.gaba_conductance",
        "--j-gab",
        "decimal",
        "nS",
        D("0.04"),
        2392,
        "/extensions/org.flybrian.c174/neural/j_gab_nS",
    ),
    _definition("simulation.duration", "--sim-ms", "integer", "ms", 5000, 2393, "/sim_time_ms"),
    _definition(
        "c174.body.femur_tibia_stiffness",
        "--ft-stiff",
        "decimal",
        "historical_mujoco_stiffness",
        D("0.03"),
        2394,
        "/extensions/org.flybrian.c174/body/ft_stiffness",
    ),
    _definition(
        "c174.body.coxa_stiffness",
        "--coxa-stiff",
        "decimal",
        "historical_mujoco_stiffness",
        None,
        2395,
        "/extensions/org.flybrian.c174/body/coxa_stiffness",
        "c174.coxa-stiffness-fallback.v1",
    ),
    _definition(
        "c174.body.velocity_damping",
        "--vd",
        "decimal",
        "historical_mujoco_damping",
        D("-0.01"),
        2396,
        "/extensions/org.flybrian.c174/body/velocity_damping",
    ),
    _definition(
        "c174.drive.minimum",
        "--boost-min",
        "decimal",
        "1",
        D("0.5"),
        2397,
        "/extensions/org.flybrian.c174/drive/minimum",
    ),
    _definition(
        "c174.feedback.force_gain",
        "--force-gain",
        "decimal",
        "nA/N",
        D("0"),
        2398,
        "/extensions/org.flybrian.c174/feedback/force_gain",
        "c174.selector-force-override.v1",
    ),
    _definition(
        "c174.neural.antigravity_vrest",
        "--vrest-anti",
        "decimal",
        "mV",
        D("-48"),
        2399,
        "/extensions/org.flybrian.c174/neural/antigravity_vrest",
    ),
    _definition(
        "c174.feedback.angle_gain",
        "--angle-gain",
        "decimal",
        "nA/rad",
        D("0"),
        2400,
        "/extensions/org.flybrian.c174/feedback/angle_gain",
        "c174.selector-angle-override.v1",
    ),
    _definition(
        "c174.transform.torque_multiplier",
        "--ts-mult",
        "decimal",
        "1",
        D("1"),
        2401,
        "/extensions/org.flybrian.c174/transform/torque_multiplier",
    ),
    _definition(
        "c174.drive.poisson_count",
        "--poisson-n",
        "integer",
        "1",
        3,
        2402,
        "/extensions/org.flybrian.c174/drive/poisson_count",
    ),
    _definition(
        "c174.drive.exclude_motor_neurons",
        "--no-poisson-mn",
        "boolean",
        None,
        False,
        2403,
        "/extensions/org.flybrian.c174/drive/exclude_motor_neurons",
    ),
    _definition(
        "c174.drive.anti_boost",
        "--anti-boost",
        "decimal",
        "nA",
        D("0"),
        2404,
        "/extensions/org.flybrian.c174/drive/anti_boost",
    ),
    _definition(
        "c174.drive.pro_suppress_fraction",
        "--pro-suppress",
        "decimal",
        "1",
        D("1"),
        2405,
        "/extensions/org.flybrian.c174/drive/pro_suppress_fraction",
    ),
    _definition(
        "c174.drive.t1_anti_boost",
        "--t1-ab",
        "decimal",
        "nA",
        None,
        2406,
        "/extensions/org.flybrian.c174/drive/t1_anti_boost",
        "c174.tier-anti-boost-fallback.v1",
    ),
    _definition(
        "c174.drive.t2_anti_boost",
        "--t2-ab",
        "decimal",
        "nA",
        None,
        2407,
        "/extensions/org.flybrian.c174/drive/t2_anti_boost",
        "c174.tier-anti-boost-fallback.v1",
    ),
    _definition(
        "c174.drive.t3_anti_boost",
        "--t3-ab",
        "decimal",
        "nA",
        None,
        2408,
        "/extensions/org.flybrian.c174/drive/t3_anti_boost",
        "c174.tier-anti-boost-fallback.v1",
    ),
    _definition(
        "c174.drive.warmup",
        "--warmup",
        "decimal_list",
        "nA",
        None,
        2409,
        "/extensions/org.flybrian.c174/drive/warmup",
        arity=3,
    ),
    _definition(
        "c174.initialization.pre_settle",
        "--pre-settle-ms",
        "integer",
        "ms",
        0,
        2413,
        "/extensions/org.flybrian.c174/initialization/pre_settle_ms",
    ),
    _definition(
        "c174.body.abduction_bias",
        "--abduct-bias",
        "decimal",
        "rad",
        D("0"),
        2418,
        "/extensions/org.flybrian.c174/body/abduction_bias",
    ),
    _definition(
        "c174.body.abduction_stiffness",
        "--abduct-stiff",
        "decimal",
        "historical_mujoco_stiffness",
        D("0"),
        2421,
        "/extensions/org.flybrian.c174/body/abduction_stiffness",
    ),
    _definition(
        "c174.transform.t1_torque_multiplier",
        "--t1-ts",
        "decimal",
        "1",
        None,
        2423,
        "/extensions/org.flybrian.c174/transform/t1_torque_multiplier",
        "c174.tier-torque-fallback.v1",
    ),
    _definition(
        "c174.transform.t2_torque_multiplier",
        "--t2-ts",
        "decimal",
        "1",
        None,
        2425,
        "/extensions/org.flybrian.c174/transform/t2_torque_multiplier",
        "c174.tier-torque-fallback.v1",
    ),
    _definition(
        "c174.transform.t3_torque_multiplier",
        "--t3-ts",
        "decimal",
        "1",
        None,
        2427,
        "/extensions/org.flybrian.c174/transform/t3_torque_multiplier",
        "c174.tier-torque-fallback.v1",
    ),
    _definition(
        "c174.transform.zero_coxa_segments",
        "--zero-coxa-segs",
        "text_list",
        None,
        None,
        2429,
        "/extensions/org.flybrian.c174/transform/zero_coxa_segments",
        choices=("T1", "T2", "T3"),
    ),
    _definition(
        "c174.transform.coxa_scale",
        "--coxa-scale",
        "decimal",
        "1",
        D("1"),
        2432,
        "/extensions/org.flybrian.c174/transform/coxa_scale",
    ),
    _definition(
        "c174.transform.t1_coxa_scale",
        "--t1-cxs",
        "decimal",
        "1",
        None,
        2435,
        "/extensions/org.flybrian.c174/transform/t1_coxa_scale",
        "c174.tier-coxa-scale-fallback.v1",
    ),
    _definition(
        "c174.transform.t2_coxa_scale",
        "--t2-cxs",
        "decimal",
        "1",
        None,
        2437,
        "/extensions/org.flybrian.c174/transform/t2_coxa_scale",
        "c174.tier-coxa-scale-fallback.v1",
    ),
    _definition(
        "c174.transform.t3_coxa_scale",
        "--t3-cxs",
        "decimal",
        "1",
        None,
        2439,
        "/extensions/org.flybrian.c174/transform/t3_coxa_scale",
        "c174.tier-coxa-scale-fallback.v1",
    ),
    _definition(
        "c174.transform.femur_scale",
        "--femur-scale",
        "decimal",
        "1",
        D("1"),
        2441,
        "/extensions/org.flybrian.c174/transform/femur_scale",
    ),
    _definition(
        "c174.transform.tibia_scale",
        "--tibia-scale",
        "decimal",
        "1",
        D("1"),
        2444,
        "/extensions/org.flybrian.c174/transform/tibia_scale",
    ),
    _definition(
        "c174.neural.true_adex",
        "--true-adex",
        "boolean",
        None,
        False,
        2447,
        "/extensions/org.flybrian.c174/neural/true_adex",
    ),
    _definition(
        "c174.feedback.pitch_gain",
        "--pitch-K",
        "decimal",
        "nA/rad",
        D("0"),
        2453,
        "/extensions/org.flybrian.c174/feedback/pitch_gain",
    ),
    _definition(
        "c174.feedback.pitch_tau",
        "--pitch-tau",
        "decimal",
        "ms",
        D("100"),
        2456,
        "/extensions/org.flybrian.c174/feedback/pitch_tau",
    ),
    _definition(
        "c174.feedback.pitch_target",
        "--pitch-target",
        "decimal",
        "deg",
        D("-35"),
        2459,
        "/extensions/org.flybrian.c174/feedback/pitch_target",
    ),
    _definition(
        "c174.feedback.height_gain",
        "--height-K",
        "decimal",
        "nA/cm",
        D("0"),
        2462,
        "/extensions/org.flybrian.c174/feedback/height_gain",
    ),
    _definition(
        "c174.feedback.height_tau",
        "--height-tau",
        "decimal",
        "ms",
        D("100"),
        2465,
        "/extensions/org.flybrian.c174/feedback/height_tau",
    ),
    _definition(
        "c174.feedback.height_target",
        "--height-target",
        "decimal",
        "cm",
        D("0.037"),
        2468,
        "/extensions/org.flybrian.c174/feedback/height_target",
    ),
    _definition(
        "c174.feedback.height_dof",
        "--height-dof",
        "text",
        None,
        "femur_tibia",
        2471,
        "/extensions/org.flybrian.c174/feedback/height_dof",
        choices=("all", "femur", "femur_tibia"),
    ),
    _definition(
        "c174.transform.symmetrize_lr",
        "--symmetrize-lr",
        "boolean",
        None,
        False,
        2475,
        "/extensions/org.flybrian.c174/transform/symmetrize_lr",
    ),
    _definition(
        "c174.drive.left_extensor_boost",
        "--l-ext-boost",
        "decimal",
        "nA",
        D("0"),
        2479,
        "/extensions/org.flybrian.c174/drive/left_extensor_boost",
    ),
    _definition(
        "c174.body.tarsus_friction",
        "--tarsus-friction",
        "decimal",
        "1",
        None,
        2483,
        "/extensions/org.flybrian.c174/body/tarsus_friction",
    ),
    _definition(
        "c174.initialization.body_height",
        "--init-z",
        "decimal",
        "historical_body_length",
        None,
        2488,
        "/extensions/org.flybrian.c174/initialization/body_height",
        "c174.initial-height-fallback.v1",
    ),
    _definition(
        "c174.drive.trochanter_boost",
        "--troch-boost",
        "decimal",
        "nA",
        D("0"),
        2492,
        "/extensions/org.flybrian.c174/drive/trochanter_boost",
    ),
    _definition(
        "c174.drive.t1_trochanter_boost",
        "--t1-tb",
        "decimal",
        "nA",
        None,
        2496,
        "/extensions/org.flybrian.c174/drive/t1_trochanter_boost",
        "c174.tier-trochanter-fallback.v1",
    ),
    _definition(
        "c174.drive.t2_trochanter_boost",
        "--t2-tb",
        "decimal",
        "nA",
        None,
        2498,
        "/extensions/org.flybrian.c174/drive/t2_trochanter_boost",
        "c174.tier-trochanter-fallback.v1",
    ),
    _definition(
        "c174.drive.t3_trochanter_boost",
        "--t3-tb",
        "decimal",
        "nA",
        None,
        2500,
        "/extensions/org.flybrian.c174/drive/t3_trochanter_boost",
        "c174.tier-trochanter-fallback.v1",
    ),
    _definition(
        "c174.body.joint_damping_multiplier",
        "--jdamp-mult",
        "decimal",
        "1",
        D("1"),
        2502,
        "/extensions/org.flybrian.c174/body/joint_damping_multiplier",
    ),
    _definition(
        "c174.feedback.campaniform_gain",
        "--cs-gain",
        "decimal",
        "nA/historical_force_unit",
        D("0"),
        2505,
        "/extensions/org.flybrian.c174/feedback/campaniform_gain",
    ),
    _definition(
        "c174.body.coxa_abduction_k",
        "--coxa-abd-K",
        "decimal",
        "historical_mujoco_stiffness",
        D("0"),
        2510,
        "/extensions/org.flybrian.c174/body/coxa_abduction_k",
    ),
    _definition(
        "c174.body.t1_coxa_abduction_k",
        "--coxa-abd-K-t1",
        "decimal",
        "historical_mujoco_stiffness",
        None,
        2512,
        "/extensions/org.flybrian.c174/body/t1_coxa_abduction_k",
        "c174.tier-coxa-abduction-global-gate.v1",
    ),
    _definition(
        "c174.body.t2_coxa_abduction_k",
        "--coxa-abd-K-t2",
        "decimal",
        "historical_mujoco_stiffness",
        None,
        2514,
        "/extensions/org.flybrian.c174/body/t2_coxa_abduction_k",
        "c174.tier-coxa-abduction-global-gate.v1",
    ),
    _definition(
        "c174.neural.progravity_vrest",
        "--pro-vrest",
        "decimal",
        "mV",
        D("-68"),
        2516,
        "/extensions/org.flybrian.c174/neural/progravity_vrest",
    ),
    _definition(
        "c174.feedback.campaniform_tau",
        "--cs-tau",
        "decimal",
        "ms",
        D("100"),
        2519,
        "/extensions/org.flybrian.c174/feedback/campaniform_tau",
    ),
)

C174_SELECTORS = (
    C174ConfigSelector(0, "lumped", False, "baseline", None, None),
    C174ConfigSelector(1, "per_muscle", False, "pm_coxaOFF", None, None),
    C174ConfigSelector(2, "per_muscle", True, "pm_coxaON", None, None),
    C174ConfigSelector(3, "per_muscle_vrest", False, "pmVr_coxaOFF", None, None),
    C174ConfigSelector(4, "per_muscle_vrest", True, "pmVr_coxaON", None, None),
    C174ConfigSelector(5, "per_muscle_silence", False, "pmSil_coxaOFF", None, None),
    C174ConfigSelector(6, "per_muscle_silence", True, "pmSil_coxaON", None, None),
    C174ConfigSelector(7, "per_muscle_vrest", True, "p3_snta1", D("1"), None),
    C174ConfigSelector(8, "per_muscle_vrest", True, "p3_snta5", D("5"), None),
    C174ConfigSelector(9, "per_muscle", True, "p3_signchk", D("5"), None),
    C174ConfigSelector(10, "per_muscle_vrest", True, "p4a_init", None, None),
    C174ConfigSelector(11, "per_muscle_vrest_cxneutral", True, "p4b_cxneutral", None, None),
    C174ConfigSelector(12, "per_muscle_vrest_direct", True, "p4c_direct", None, None),
    C174ConfigSelector(13, "per_muscle_vrest_cxneutral", True, "p4_snpp2", None, D("2")),
    C174ConfigSelector(14, "per_muscle_vrest_cxneutral", True, "p4_snpp5", None, D("5")),
    C174ConfigSelector(15, "per_muscle", True, "p4_snpp_ctrl", None, D("2")),
)

_C174_CONTROLLER_STAGE_IDS = (
    "neural_initialization",
    "open_loop_schedule",
    "angle_force_feedback",
    "pitch_feedback",
    "height_feedback",
    "campaniform_feedback",
    "muscle_drive",
    "joint_torque_transform",
    "body_property_override",
    "coxa_abduction_correction",
    "initial_condition",
    "artifact_capture",
)
_PROFILE_FACTS = {
    "schema_version": "1.0",
    "source": C174_SOURCE_AUTHORITY.to_dict(),
    "options": [item.to_dict() for item in C174_OPTION_PROFILE],
    "selectors": [item.to_dict() for item in C174_SELECTORS],
    "controller_stage_ids": list(_C174_CONTROLLER_STAGE_IDS),
    "mode_profiles": sorted({item.mode for item in C174_SELECTORS}),
    "source_constants": {
        "window_ms": 32,
        "initial_body_height": "0.10",
        "tonic_iext_nA": "0",
        "t1_vrest": None,
        "t2_vrest": None,
        "t3_vrest": None,
    },
    "discrepancies": [
        "STALE_INDEX_HELP_RANGE",
        "GLOBAL_GATE_SUPPRESSES_TIER_OVERRIDE",
        "DISPLAY_TRUTHINESS_DIFFERS_FROM_EXECUTION_NULL_FALLBACK",
    ],
}
C174_PROFILE_SHA256 = _sha256(_PROFILE_FACTS)


def _option_map(
    requested_values: Mapping[str, object],
) -> tuple[dict[str, object], set[str]]:
    aliases: dict[str, C174OptionDefinition] = {}
    for definition in C174_OPTION_PROFILE:
        aliases[definition.option_id] = definition
        aliases[definition.legacy_name] = definition
        aliases[definition.legacy_name[2:]] = definition
    values = {item.option_id: item.default_value for item in C174_OPTION_PROFILE}
    supplied: set[str] = set()
    for key, value in requested_values.items():
        if not isinstance(key, str) or key not in aliases:
            raise C174ResolutionError(f"unknown C174 option {key!r}")
        definition = aliases[key]
        if definition.option_id in supplied:
            raise C174ResolutionError(f"duplicate aliases supplied for {definition.option_id}")
        values[definition.option_id] = _coerce_value(
            definition,
            value,
            definition.legacy_name,
            allow_null=definition.default_value is None,
        )
        supplied.add(definition.option_id)
    zero_segments = values["c174.transform.zero_coxa_segments"]
    if isinstance(zero_segments, tuple):
        values["c174.transform.zero_coxa_segments"] = tuple(sorted(set(zero_segments)))
    return values, supplied


def _validate_structural_values(values: Mapping[str, object]) -> None:
    positive_integers = (
        "simulation.duration",
        "c174.drive.poisson_count",
    )
    for option_id in positive_integers:
        value = values[option_id]
        assert isinstance(value, int)
        if value <= 0:
            raise C174ResolutionError(f"{option_id} must be positive")
    pre_settle = values["c174.initialization.pre_settle"]
    assert isinstance(pre_settle, int)
    if pre_settle < 0:
        raise C174ResolutionError("pre-settle must be non-negative")
    for option_id in (
        "c174.feedback.pitch_tau",
        "c174.feedback.height_tau",
        "c174.feedback.campaniform_tau",
    ):
        value = values[option_id]
        assert isinstance(value, Decimal)
        if value <= 0:
            raise C174ResolutionError(f"{option_id} must be positive")


def _parameter(name: str, value: object, unit: str) -> HistoricalParameter:
    if isinstance(value, bool):
        value = int(value)
    assert isinstance(value, (Decimal, int, str))
    return HistoricalParameter(name, value, unit)


def _stage_hash(stage_id: str, mode: str) -> str:
    return _sha256(
        {
            "schema_version": "1.0",
            "profile": "org.flybrian.c174.reviewed-stage",
            "stage_id": stage_id,
            "mode": mode,
            "source_sha256": C174_SOURCE_AUTHORITY.sha256,
        }
    )


def _controller_profile(
    selector: C174ConfigSelector,
    effective: Mapping[str, object],
) -> HistoricalControllerProfile:
    sim_ms = effective["simulation.duration"]
    assert isinstance(sim_ms, int)
    warmup = effective["c174.drive.warmup"]
    phases: list[HistoricalControllerPhase] = []
    if isinstance(warmup, tuple):
        starts = (0, 200, 400)
        ends = (min(200, sim_ms), min(400, sim_ms), sim_ms)
        for start, end, value in zip(starts, ends, warmup, strict=True):
            if end > start:
                phases.append(
                    HistoricalControllerPhase(
                        start,
                        end,
                        (_parameter("anti_boost", value, "nA"),),
                    )
                )

    force_gain = effective["c174.feedback.force_gain"]
    angle_gain = effective["c174.feedback.angle_gain"]
    pitch_gain = effective["c174.feedback.pitch_gain"]
    height_gain = effective["c174.feedback.height_gain"]
    campaniform_gain = effective["c174.feedback.campaniform_gain"]
    assert isinstance(force_gain, Decimal)
    assert isinstance(angle_gain, Decimal)
    assert isinstance(pitch_gain, Decimal)
    assert isinstance(height_gain, Decimal)
    assert isinstance(campaniform_gain, Decimal)
    stages: list[HistoricalControllerStage] = []

    def add_stage(
        stage_id: str,
        kind: ControllerStageKind,
        inputs: tuple[str, ...],
        outputs: tuple[str, ...],
        parameters: tuple[HistoricalParameter, ...],
        active: bool,
        stage_phases: tuple[HistoricalControllerPhase, ...] = (),
    ) -> None:
        stages.append(
            HistoricalControllerStage(
                stage_id=stage_id,
                kind=kind,
                profile_id=f"org.flybrian.c174.{stage_id.replace('_', '-')}",
                profile_version="1.0",
                profile_sha256=_stage_hash(stage_id, selector.mode),
                inputs=inputs,
                outputs=outputs,
                parameters=parameters,
                activation_condition=active,
                phases=stage_phases,
            )
        )

    add_stage(
        "neural_initialization",
        "neural_initialization",
        ("neural_state",),
        ("initialized_neural_state",),
        (
            _parameter("j_gab", effective["c174.neural.gaba_conductance"], "nS"),
            _parameter("antigravity_vrest", effective["c174.neural.antigravity_vrest"], "mV"),
            _parameter("progravity_vrest", effective["c174.neural.progravity_vrest"], "mV"),
            _parameter("true_adex", effective["c174.neural.true_adex"], "1"),
            _parameter("poisson_count", effective["c174.drive.poisson_count"], "1"),
            _parameter(
                "exclude_motor_neurons",
                effective["c174.drive.exclude_motor_neurons"],
                "1",
            ),
        ),
        True,
    )
    add_stage(
        "open_loop_schedule",
        "open_loop_schedule",
        ("initialized_neural_state",),
        ("commanded_neural_state",),
        (
            _parameter("t1_anti_boost", effective["c174.drive.t1_anti_boost"], "nA"),
            _parameter("t2_anti_boost", effective["c174.drive.t2_anti_boost"], "nA"),
            _parameter("t3_anti_boost", effective["c174.drive.t3_anti_boost"], "nA"),
            _parameter("pro_suppress_fraction", effective["c174.drive.pro_suppress_fraction"], "1"),
            _parameter(
                "left_extensor_boost",
                effective["c174.drive.left_extensor_boost"],
                "nA",
            ),
            _parameter(
                "t1_trochanter_boost",
                effective["c174.drive.t1_trochanter_boost"],
                "nA",
            ),
            _parameter(
                "t2_trochanter_boost",
                effective["c174.drive.t2_trochanter_boost"],
                "nA",
            ),
            _parameter(
                "t3_trochanter_boost",
                effective["c174.drive.t3_trochanter_boost"],
                "nA",
            ),
        ),
        any(
            effective[item] != Decimal("0")
            for item in (
                "c174.drive.t1_anti_boost",
                "c174.drive.t2_anti_boost",
                "c174.drive.t3_anti_boost",
                "c174.drive.left_extensor_boost",
                "c174.drive.t1_trochanter_boost",
                "c174.drive.t2_trochanter_boost",
                "c174.drive.t3_trochanter_boost",
            )
        )
        or bool(phases),
        tuple(phases),
    )
    add_stage(
        "angle_force_feedback",
        "sensor_feedback",
        ("contact_force", "joint_angle"),
        ("angle_force_current",),
        (
            _parameter("force_gain", force_gain, "nA/N"),
            _parameter("angle_gain", angle_gain, "nA/rad"),
        ),
        force_gain > 0 or angle_gain != 0,
    )
    add_stage(
        "pitch_feedback",
        "sensor_feedback",
        ("body_pose", "angle_force_current"),
        ("pitch_feedback_current",),
        (
            _parameter("gain", pitch_gain, "nA/rad"),
            _parameter("tau", effective["c174.feedback.pitch_tau"], "ms"),
            _parameter("target", effective["c174.feedback.pitch_target"], "deg"),
        ),
        pitch_gain > 0,
    )
    height_dof = effective["c174.feedback.height_dof"]
    assert isinstance(height_dof, str)
    add_stage(
        "height_feedback",
        "sensor_feedback",
        ("body_pose", "pitch_feedback_current"),
        ("height_feedback_current",),
        (
            _parameter("gain", height_gain, "nA/cm"),
            _parameter("tau", effective["c174.feedback.height_tau"], "ms"),
            _parameter("target", effective["c174.feedback.height_target"], "cm"),
            _parameter("dof_all", int(height_dof == "all"), "1"),
            _parameter("dof_femur", int(height_dof == "femur"), "1"),
            _parameter("dof_femur_tibia", int(height_dof == "femur_tibia"), "1"),
        ),
        height_gain > 0,
    )
    add_stage(
        "campaniform_feedback",
        "sensor_feedback",
        ("contact_force", "height_feedback_current"),
        ("feedback_current",),
        (
            _parameter("gain", campaniform_gain, "nA/historical_force_unit"),
            _parameter("tau", effective["c174.feedback.campaniform_tau"], "ms"),
        ),
        campaniform_gain > 0,
    )
    direct = selector.mode == "per_muscle_vrest_direct"
    torque_inputs: tuple[str, ...]
    if not direct:
        add_stage(
            "muscle_drive",
            "muscle_drive",
            ("spike_counts", "feedback_current"),
            ("muscle_drive",),
            (_parameter("minimum_drive", effective["c174.drive.minimum"], "1"),),
            True,
        )
        torque_inputs = ("muscle_drive",)
    else:
        torque_inputs = ("spike_counts", "feedback_current")
    zero_segments = effective["c174.transform.zero_coxa_segments"]
    assert zero_segments is None or isinstance(zero_segments, tuple)
    add_stage(
        "joint_torque_transform",
        "joint_torque_transform",
        torque_inputs,
        ("motor_command",),
        (
            _parameter("t1_multiplier", effective["c174.transform.t1_torque_multiplier"], "1"),
            _parameter("t2_multiplier", effective["c174.transform.t2_torque_multiplier"], "1"),
            _parameter("t3_multiplier", effective["c174.transform.t3_torque_multiplier"], "1"),
            _parameter("t1_coxa_scale", effective["c174.transform.t1_coxa_scale"], "1"),
            _parameter("t2_coxa_scale", effective["c174.transform.t2_coxa_scale"], "1"),
            _parameter("t3_coxa_scale", effective["c174.transform.t3_coxa_scale"], "1"),
            _parameter("femur_scale", effective["c174.transform.femur_scale"], "1"),
            _parameter("tibia_scale", effective["c174.transform.tibia_scale"], "1"),
            _parameter("coxa_active", selector.coxa_active, "1"),
            _parameter("zero_t1_coxa", zero_segments is not None and "T1" in zero_segments, "1"),
            _parameter("zero_t2_coxa", zero_segments is not None and "T2" in zero_segments, "1"),
            _parameter("zero_t3_coxa", zero_segments is not None and "T3" in zero_segments, "1"),
            _parameter("symmetrize_lr", effective["c174.transform.symmetrize_lr"], "1"),
        ),
        True,
    )
    tarsus_friction = effective["c174.body.tarsus_friction"]
    assert tarsus_friction is None or isinstance(tarsus_friction, Decimal)
    add_stage(
        "body_property_override",
        "body_property_override",
        ("body_pose",),
        ("configured_body_pose",),
        (
            _parameter(
                "ft_stiffness",
                effective["c174.body.femur_tibia_stiffness"],
                "historical_mujoco_stiffness",
            ),
            _parameter(
                "coxa_stiffness",
                effective["c174.body.coxa_stiffness"],
                "historical_mujoco_stiffness",
            ),
            _parameter(
                "velocity_damping",
                effective["c174.body.velocity_damping"],
                "historical_mujoco_damping",
            ),
            _parameter(
                "joint_damping_multiplier", effective["c174.body.joint_damping_multiplier"], "1"
            ),
            _parameter("abduction_bias", effective["c174.body.abduction_bias"], "rad"),
            _parameter(
                "abduction_stiffness",
                effective["c174.body.abduction_stiffness"],
                "historical_mujoco_stiffness",
            ),
            _parameter("tarsus_friction_present", tarsus_friction is not None, "1"),
            _parameter(
                "tarsus_friction",
                Decimal("0") if tarsus_friction is None else tarsus_friction,
                "1",
            ),
        ),
        True,
    )
    global_coxa_k = effective["c174.body.coxa_abduction_k"]
    assert isinstance(global_coxa_k, Decimal)
    add_stage(
        "coxa_abduction_correction",
        "body_property_override",
        ("configured_body_pose",),
        ("corrected_body_pose",),
        (
            _parameter(
                "t1_k",
                effective["c174.body.t1_coxa_abduction_k"],
                "historical_mujoco_stiffness",
            ),
            _parameter(
                "t2_k",
                effective["c174.body.t2_coxa_abduction_k"],
                "historical_mujoco_stiffness",
            ),
            _parameter("t3_k", global_coxa_k, "historical_mujoco_stiffness"),
        ),
        global_coxa_k > 0,
    )
    add_stage(
        "initial_condition",
        "initial_condition",
        ("corrected_body_pose",),
        ("initial_body_pose",),
        (
            _parameter("pre_settle", effective["c174.initialization.pre_settle"], "ms"),
            _parameter(
                "body_height",
                effective["c174.initialization.body_height"],
                "historical_body_length",
            ),
        ),
        True,
    )
    add_stage(
        "artifact_capture",
        "artifact_capture",
        ("motor_command", "body_pose"),
        ("artifact_manifest",),
        (),
        True,
    )
    return HistoricalControllerProfile(
        profile_id=f"org.flybrian.c174.controller.selector-{selector.selector}",
        version="1.0",
        source=f"Reviewed C174 selector {selector.selector}: {selector.mode}",
        stages=tuple(stages),
    )


@dataclass(frozen=True)
class C174ResolvedExperiment:
    selector: C174ConfigSelector
    options: tuple[HistoricalOptionResolution, ...]
    controller_profile: HistoricalControllerProfile
    discrepancies: tuple[str, ...]
    profile_sha256: str
    envelope: HistoricalExperimentEnvelope

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "selector": self.selector.to_dict(),
            "options": [item.to_dict() for item in self.options],
            "controller_profile": self.controller_profile.to_dict(),
            "discrepancies": list(self.discrepancies),
            "profile_sha256": self.profile_sha256,
            "envelope_sha256": self.envelope.sha256(),
        }

    def sha256(self) -> str:
        return _sha256(self.to_dict())


_FALLBACKS = {
    "c174.body.coxa_stiffness": "c174.body.femur_tibia_stiffness",
    "c174.drive.t1_anti_boost": "c174.drive.anti_boost",
    "c174.drive.t2_anti_boost": "c174.drive.anti_boost",
    "c174.drive.t3_anti_boost": "c174.drive.anti_boost",
    "c174.transform.t1_torque_multiplier": "c174.transform.torque_multiplier",
    "c174.transform.t2_torque_multiplier": "c174.transform.torque_multiplier",
    "c174.transform.t3_torque_multiplier": "c174.transform.torque_multiplier",
    "c174.transform.t1_coxa_scale": "c174.transform.coxa_scale",
    "c174.transform.t2_coxa_scale": "c174.transform.coxa_scale",
    "c174.transform.t3_coxa_scale": "c174.transform.coxa_scale",
    "c174.drive.t1_trochanter_boost": "c174.drive.trochanter_boost",
    "c174.drive.t2_trochanter_boost": "c174.drive.trochanter_boost",
    "c174.drive.t3_trochanter_boost": "c174.drive.trochanter_boost",
}


def resolve_c174_experiment(
    selector: object,
    requested_values: Mapping[str, object],
    *,
    invocation: Sequence[str] = (),
) -> C174ResolvedExperiment:
    """Resolve one selector without importing or executing the historical source."""
    if isinstance(selector, bool) or not isinstance(selector, int) or not 0 <= selector < 16:
        raise C174ResolutionError("C174 selector must be integer from 0 through 15")
    selected = C174_SELECTORS[selector]
    values, supplied = _option_map(requested_values)
    _validate_structural_values(values)
    if "c174.selection.index" in supplied:
        requested_selector = values["c174.selection.index"]
        if requested_selector != selector:
            raise C174ResolutionError("requested index does not match C174 selector")
    values["c174.selection.index"] = selector
    supplied.add("c174.selection.index")
    requested_by_id = dict(values)

    for target, fallback in _FALLBACKS.items():
        if values[target] is None:
            values[target] = values[fallback]
    if values["c174.initialization.body_height"] is None:
        values["c174.initialization.body_height"] = Decimal("0.10")
    if selected.force_gain_override is not None:
        values["c174.feedback.force_gain"] = selected.force_gain_override
    if selected.angle_gain_override is not None:
        values["c174.feedback.angle_gain"] = selected.angle_gain_override

    discrepancies = ["STALE_INDEX_HELP_RANGE"]
    if selected.force_gain_override is not None:
        discrepancies.append("SELECTOR_FORCE_OVERRIDE")
    if selected.angle_gain_override is not None:
        discrepancies.append("SELECTOR_ANGLE_OVERRIDE")
    display_fallbacks = {
        "c174.drive.t1_anti_boost": "c174.drive.anti_boost",
        "c174.drive.t2_anti_boost": "c174.drive.anti_boost",
        "c174.drive.t3_anti_boost": "c174.drive.anti_boost",
        "c174.transform.t1_torque_multiplier": "c174.transform.torque_multiplier",
        "c174.transform.t2_torque_multiplier": "c174.transform.torque_multiplier",
        "c174.transform.t3_torque_multiplier": "c174.transform.torque_multiplier",
        "c174.drive.t1_trochanter_boost": "c174.drive.trochanter_boost",
        "c174.drive.t2_trochanter_boost": "c174.drive.trochanter_boost",
        "c174.drive.t3_trochanter_boost": "c174.drive.trochanter_boost",
    }
    if any(
        target in supplied
        and requested_by_id[target] == Decimal("0")
        and requested_by_id[fallback] != Decimal("0")
        for target, fallback in display_fallbacks.items()
    ):
        discrepancies.append("DISPLAY_TRUTHINESS_DIFFERS_FROM_EXECUTION_NULL_FALLBACK")
    global_k = values["c174.body.coxa_abduction_k"]
    assert isinstance(global_k, Decimal)
    for target in (
        "c174.body.t1_coxa_abduction_k",
        "c174.body.t2_coxa_abduction_k",
    ):
        requested = values[target]
        if requested is None:
            values[target] = global_k
        elif global_k <= 0 and requested != 0:
            values[target] = Decimal("0")
            if "GLOBAL_GATE_SUPPRESSES_TIER_OVERRIDE" not in discrepancies:
                discrepancies.append("GLOBAL_GATE_SUPPRESSES_TIER_OVERRIDE")

    options: list[HistoricalOptionResolution] = []
    for definition in C174_OPTION_PROFILE:
        option_id = definition.option_id
        requested = requested_by_id[option_id] if option_id in supplied else None
        origin: OptionOrigin = "invocation" if option_id in supplied else "default"
        application: OptionApplication = "applied"
        notes = f"Reviewed from source line {definition.source_line}."
        derived = definition.default_value is None and values[option_id] is not None
        selector_override = (
            option_id == "c174.feedback.force_gain" and selected.force_gain_override is not None
        ) or (option_id == "c174.feedback.angle_gain" and selected.angle_gain_override is not None)
        global_gate = (
            option_id
            in {
                "c174.body.t1_coxa_abduction_k",
                "c174.body.t2_coxa_abduction_k",
            }
            and requested_by_id[option_id] not in (None, Decimal("0"))
            and global_k <= 0
        )
        if derived or selector_override or global_gate:
            origin = "derived"
        if selector_override and option_id in supplied:
            application = "ignored"
            notes += " Selector row overrides the requested CLI value."
        if global_gate:
            application = "ignored"
            notes += " Global zero gate suppresses the tier override."
        options.append(
            HistoricalOptionResolution(
                option_id=option_id,
                legacy_names=(definition.legacy_name,),
                value_kind=definition.value_kind,
                unit=definition.unit,
                default_value=definition.default_value,
                requested_value=requested,
                effective_value=values[option_id],
                origin=origin,
                application=application,
                resolution_rule=definition.resolution_rule,
                target=None,
                notes=notes,
            )
        )

    controller = _controller_profile(selected, values)
    missing = tuple(
        sorted(
            {
                "BODY_MODEL",
                "CONNECTIVITY",
                "CONTROLLER_EXECUTOR",
                "DATASET",
                "ENVIRONMENT",
                "NEURAL_PROFILE",
                "NEURON_SELECTION",
                "RESULT_EVIDENCE",
                "UNIT_AUTHORITY",
            }
        )
    )
    envelope = HistoricalExperimentEnvelope(
        envelope_id=f"org.flybrian.history.c174.selector-{selector}",
        version="1.0",
        source=C174_SOURCE_AUTHORITY,
        selector=str(selector),
        invocation=tuple(invocation),
        options=tuple(options),
        controller_profile=controller,
        fes=None,
        expected_fes_sha256=None,
        source_artifacts=(),
        missing_requirements=missing,
        lineage=None,
    )
    return C174ResolvedExperiment(
        selected,
        tuple(options),
        controller,
        tuple(discrepancies),
        C174_PROFILE_SHA256,
        envelope,
    )


def resolve_c174_batch(
    requested_values: Mapping[str, object],
    *,
    invocation: Sequence[str] = (),
) -> tuple[C174ResolvedExperiment, ...]:
    """Expand the historical no-index behavior into 16 independent manifests."""
    if any(key in {"--index", "index", "c174.selection.index"} for key in requested_values):
        raise C174ResolutionError("batch resolution must not include selector option")
    return tuple(
        resolve_c174_experiment(
            selector.selector,
            requested_values,
            invocation=invocation,
        )
        for selector in C174_SELECTORS
    )


def apply_c174_variations(
    base: C174ResolvedExperiment,
    patches: Sequence[HistoricalVariationPatch],
    *,
    new_version: str,
    invocation: Sequence[str] | None = None,
) -> C174ResolvedExperiment:
    """Apply option patches and recompute the reviewed C174 controller and envelope."""
    if not isinstance(new_version, str) or not new_version.strip():
        raise C174ResolutionError("C174 variation version must be non-empty")
    if new_version == base.envelope.version:
        raise C174ResolutionError("C174 variation version must change")
    if not patches:
        raise C174ResolutionError("C174 variation patches must not be empty")
    base_sha256 = base.envelope.sha256()
    options_by_id = {item.option_id: item for item in base.options}
    requested: dict[str, object] = {
        item.option_id: item.requested_value
        for item in base.options
        if item.option_id != "c174.selection.index" and item.requested_value is not None
    }
    targets: set[str] = set()
    for patch in patches:
        if patch.base_envelope_sha256 != base_sha256:
            raise C174ResolutionError("C174 variation base envelope hash does not match")
        if patch.target_kind != "option":
            raise C174ResolutionError("C174 variation must target a reviewed option")
        if patch.target == "c174.selection.index":
            raise C174ResolutionError("C174 selector changes require selecting another manifest")
        if patch.target in targets:
            raise C174ResolutionError("C174 variation option targets must be unique")
        targets.add(patch.target)
        current = options_by_id.get(patch.target)
        if current is None:
            raise C174ResolutionError(f"unknown C174 variation option {patch.target!r}")
        if _canonical_value(current.effective_value) != _canonical_value(
            patch.before_canonical_value
        ):
            raise C174ResolutionError("C174 variation before value does not match")
        requested[patch.target] = patch.after_canonical_value
    resolved = resolve_c174_experiment(
        base.selector.selector,
        requested,
        invocation=(base.envelope.invocation if invocation is None else invocation),
    )
    resolved_by_id = {item.option_id: item for item in resolved.options}
    definitions_by_id = {item.option_id: item for item in C174_OPTION_PROFILE}
    for patch in patches:
        effective = resolved_by_id[patch.target].effective_value
        clears_nullable_override = (
            patch.after_canonical_value is None
            and definitions_by_id[patch.target].default_value is None
        )
        if not clears_nullable_override and _canonical_value(effective) != _canonical_value(
            patch.after_canonical_value
        ):
            raise C174ResolutionError(
                "C174 variation is suppressed by a reviewed selector or source rule"
            )
    envelope = replace(
        resolved.envelope,
        version=new_version,
        lineage=HistoricalLineage(
            base.envelope.envelope_id,
            base.envelope.version,
            base_sha256,
            "variation",
        ),
        variation_patches=tuple(patches),
    )
    return replace(resolved, envelope=envelope)
