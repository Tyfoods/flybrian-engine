"""Licensed muscle catalogs and explicit historical FlyBrian Hill dynamics."""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal, TypeAlias

from .actuator_catalogs import FLYBODY_78_ACTUATOR_CATALOG
from .embodiment import (
    BodyRegionRule,
    ConfidenceRule,
    EmbodimentError,
    Muscle,
    MuscleActuatorRule,
    MuscleCatalog,
    MuscleParameter,
    MuscleProfile,
    MuscleTarget,
    MuscleTargetRule,
)

StateAdvancePolicy = Literal["once_per_muscle_primary_dof", "per_projection_legacy"]
ProjectionDirection = Literal["positive", "negative"]
BridgeConfidence = Literal["high", "medium", "no_equivalent"]
ExactDecimal: TypeAlias = Decimal | int | str

_FLYMIMIC_COMMIT = "9ea1131626cd76f7203b74076ef8f0e9cab30bef"
_FLYMIMIC_OSIM = (
    "https://raw.githubusercontent.com/gizemozd/FlyMimic/"
    f"{_FLYMIMIC_COMMIT}/flymimic/assets/models/opensim/best_combined.osim"
)
_HISTORICAL_SOURCE = (
    "FlyBrian historical six-leg Hill approximation 1.0; rounded/extrapolated from "
    f"FlyMimic {_FLYMIMIC_COMMIT} with FlyBrian-authored calibration and dynamics"
)


def _text(value: object, path: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EmbodimentError(f"{path} must be a non-empty trimmed string")
    if len(value) > maximum:
        raise EmbodimentError(f"{path} must contain at most {maximum} characters")
    return value


def _decimal(value: object, path: str) -> Decimal:
    if isinstance(value, (bool, float)):
        raise EmbodimentError(f"{path} must be an exact decimal, not bool or binary float")
    if not isinstance(value, (Decimal, int, str)):
        raise EmbodimentError(f"{path} must be an exact decimal")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise EmbodimentError(f"{path} must be an exact decimal") from error
    if not result.is_finite():
        raise EmbodimentError(f"{path} must be finite")
    return result


def _binary64(value: object, path: str) -> float:
    if isinstance(value, bool):
        raise EmbodimentError(f"{path} must not be boolean")
    if not isinstance(value, (Decimal, float, int, str)):
        raise EmbodimentError(f"{path} must be numeric")
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise EmbodimentError(f"{path} must be binary64-compatible") from error
    if not math.isfinite(result):
        raise EmbodimentError(f"{path} must be finite")
    return result


def _positive_decimal(value: object, path: str) -> Decimal:
    result = _decimal(value, path)
    if result <= 0:
        raise EmbodimentError(f"{path} must be positive")
    return result


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _float_hex(value: float) -> str:
    if not math.isfinite(value):
        raise EmbodimentError("canonical binary64 value must be finite")
    return value.hex()


_OFFICIAL_PARAMETERS = (
    (
        "LFC_tergopleural_promotor_a",
        "9.3186710000294823",
        "0.16525853534999999",
        "0.0086978176499999948",
        "42.088141227468149",
    ),
    (
        "LFC_tergopleural_promotor_b",
        "46.199225232013418",
        "0.27555787858985969",
        "0.02774111841014032",
        "29.582563314795539",
    ),
    (
        "LFC_pleural_remotor_and_abductor",
        "16.073374433046375",
        "0.17504030464423312",
        "0.064697052355766865",
        "62.172012057329532",
    ),
    (
        "LFC_pleural_promotor",
        "16.321853483864867",
        "0.086046779310720481",
        "0.033540009689279518",
        "24.810626354483187",
    ),
    (
        "LFC_sternal_anterior_rotator",
        "50.190420560282327",
        "0.063550756012708667",
        "0.15499443398729135",
        "48.707602129050898",
    ),
    (
        "LFC_sternal_posterior_rotator",
        "98.165524324481822",
        "0.10659815486394372",
        "0.014682512136056286",
        "19.063244896117165",
    ),
    (
        "LFC_sternal_adductor",
        "9.0799731937055537",
        "0.14616210238408217",
        "0.056366907615917811",
        "13.622140336693155",
    ),
    (
        "LFF_trochanter_flexor_b",
        "66.94011845253408",
        "0.1959653237129548",
        "0.17190187853202057",
        "8.5146205857090536",
    ),
    (
        "LFF_sterno-tergo-trochanter_extensor_a",
        "92.625241377390921",
        "0.200869504270694",
        "0.091434136357565143",
        "49.187316064636818",
    ),
    (
        "LFF_sterno-tergo-trochanter_extensor_b",
        "70.475356564380618",
        "0.18581314004810731",
        "0.10732787472296393",
        "12.245275132706327",
    ),
    (
        "LFF_accesory_trochanter_flexor",
        "15.180767121910684",
        "0.073564374747315378",
        "0.16314783390114995",
        "56.506122005620988",
    ),
    (
        "LFF_trochanter_extensor",
        "25.781693285517122",
        "0.10140696206987981",
        "0.017732469331603176",
        "71.736960038810921",
    ),
    (
        "LFF_trochanter_flexor_a",
        "27.448956960049777",
        "0.34947384213272659",
        "0.018393360112248791",
        "92.21973488214941",
    ),
    (
        "LFTibia_flex_93434",
        "41.531495075195743",
        "0.40006233168917504",
        "0.059464497310824926",
        "75.644104930211938",
    ),
    (
        "LFTibia_extensor_93932",
        "154.06374241726678",
        "0.42355333916453586",
        "0.14097306883546412",
        "24.794348625868036",
    ),
)

_HISTORICAL_PARAMETERS = (
    ("LFC_tergopleural_promotor_a", "9.32", "0.1653", "0.0087", "42.1"),
    ("LFC_tergopleural_promotor_b", "46.20", "0.2756", "0.0277", "29.6"),
    ("LFC_pleural_remotor_and_abductor", "16.07", "0.1750", "0.0647", "62.2"),
    ("LFC_pleural_promotor", "16.32", "0.0860", "0.0335", "24.8"),
    ("LFC_sternal_anterior_rotator", "50.19", "0.0636", "0.1550", "48.7"),
    ("LFC_sternal_posterior_rotator", "98.17", "0.1066", "0.0147", "19.1"),
    ("LFC_sternal_adductor", "9.08", "0.1462", "0.0564", "13.6"),
    ("LFF_trochanter_flexor_b", "66.94", "0.1960", "0.1719", "8.5"),
    ("LFF_sterno-tergo-trochanter_extensor_a", "92.63", "0.2009", "0.0914", "49.2"),
    ("LFF_sterno-tergo-trochanter_extensor_b", "70.48", "0.1858", "0.1073", "12.2"),
    ("LFF_accesory_trochanter_flexor", "15.18", "0.0736", "0.1631", "56.5"),
    ("LFF_trochanter_extensor", "25.78", "0.1014", "0.0177", "71.7"),
    ("LFF_trochanter_flexor_a", "27.45", "0.3495", "0.0184", "92.2"),
    ("LFTibia_flex_93434", "41.53", "0.4001", "0.0595", "75.6"),
    ("LFTibia_extensor_93932", "154.06", "0.4236", "0.1410", "24.8"),
)

_MOMENT_ARMS_MM = {
    "LFC_tergopleural_promotor_a": "0.53",
    "LFC_tergopleural_promotor_b": "0.45",
    "LFC_pleural_remotor_and_abductor": "0.45",
    "LFC_pleural_promotor": "0.53",
    "LFC_sternal_anterior_rotator": "0.36",
    "LFC_sternal_posterior_rotator": "0.36",
    "LFC_sternal_adductor": "0.36",
    "LFF_trochanter_flexor_b": "0.18",
    "LFF_sterno-tergo-trochanter_extensor_a": "0.18",
    "LFF_sterno-tergo-trochanter_extensor_b": "0.18",
    "LFF_accesory_trochanter_flexor": "0.16",
    "LFF_trochanter_extensor": "0.16",
    "LFF_trochanter_flexor_a": "0.18",
    "LFTibia_flex_93434": "0.051",
    "LFTibia_extensor_93932": "0.051",
}

_DOF_MAP: dict[str, tuple[tuple[str, ProjectionDirection], ...]] = {
    "LFC_tergopleural_promotor_a": (("coxa_twist", "positive"), ("coxa", "positive")),
    "LFC_tergopleural_promotor_b": (("coxa", "positive"), ("coxa_abduct", "negative")),
    "LFC_pleural_remotor_and_abductor": (
        ("coxa", "negative"),
        ("coxa_abduct", "positive"),
    ),
    "LFC_pleural_promotor": (("coxa", "positive"),),
    "LFC_sternal_anterior_rotator": (("coxa_abduct", "positive"),),
    "LFC_sternal_posterior_rotator": (("coxa_abduct", "negative"),),
    "LFC_sternal_adductor": (("coxa_abduct", "negative"),),
    "LFF_trochanter_flexor_b": (("femur", "positive"),),
    "LFF_sterno-tergo-trochanter_extensor_a": (("femur", "negative"),),
    "LFF_sterno-tergo-trochanter_extensor_b": (("femur", "negative"),),
    "LFF_accesory_trochanter_flexor": (("femur_twist", "positive"),),
    "LFF_trochanter_extensor": (("femur_twist", "negative"),),
    "LFF_trochanter_flexor_a": (("femur", "positive"),),
    "LFTibia_flex_93434": (("tibia", "negative"),),
    "LFTibia_extensor_93932": (("tibia", "positive"),),
}

_LEG_LAYOUT = (
    ("T1L", "T1_left", "1"),
    ("T1R", "T1_right", "1"),
    ("T2L", "T2_left", "1.2"),
    ("T2R", "T2_right", "1.2"),
    ("T3L", "T3_left", "1.4"),
    ("T3R", "T3_right", "1.4"),
)

_STANDING_ANGLES = {
    "T1L": {
        "coxa_abduct": "-0.038",
        "coxa_twist": "0",
        "coxa": "-0.131",
        "femur_twist": "0",
        "femur": "0.6",
        "tibia": "-0.5",
        "tarsus": "0",
        "tarsus2": "0",
    },
    "T1R": {
        "coxa_abduct": "-0.066",
        "coxa_twist": "0",
        "coxa": "-0.122",
        "femur_twist": "0",
        "femur": "0.6",
        "tibia": "-0.5",
        "tarsus": "0",
        "tarsus2": "0",
    },
    "T2L": {
        "coxa_abduct": "-0.014",
        "coxa_twist": "0",
        "coxa": "-0.059",
        "femur_twist": "0",
        "femur": "0.3",
        "tibia": "-0.4",
        "tarsus": "0",
        "tarsus2": "0",
    },
    "T2R": {
        "coxa_abduct": "-0.014",
        "coxa_twist": "0",
        "coxa": "-0.096",
        "femur_twist": "0",
        "femur": "0.3",
        "tibia": "-0.4",
        "tarsus": "0",
        "tarsus2": "0",
    },
    "T3L": {
        "coxa_abduct": "0.052",
        "coxa_twist": "0",
        "coxa": "0.047",
        "femur_twist": "0",
        "femur": "0.1",
        "tibia": "-0.35",
        "tarsus": "0",
        "tarsus2": "0",
    },
    "T3R": {
        "coxa_abduct": "0.030",
        "coxa_twist": "0",
        "coxa": "0.035",
        "femur_twist": "0",
        "femur": "0.1",
        "tibia": "-0.35",
        "tarsus": "0",
        "tarsus2": "0",
    },
}


def _parameters(
    f_max: str,
    l_opt: str,
    l_slack: str,
    v_max: str,
    *,
    tau_act: str,
    tau_deact: str,
    scale: str | None = None,
    moment_arm: str | None = None,
    reference_angle: str | None = None,
) -> tuple[MuscleParameter, ...]:
    values = [
        MuscleParameter("max_isometric_force", f_max, "mN"),
        MuscleParameter("optimal_fiber_length", l_opt, "mm"),
        MuscleParameter("tendon_slack_length", l_slack, "mm"),
        MuscleParameter("pennation_angle_at_optimal", "0", "rad"),
        MuscleParameter(
            "max_contraction_velocity", v_max, "optimal_fiber_lengths_per_second"
        ),
        MuscleParameter("activation_time_constant", tau_act, "s"),
        MuscleParameter("deactivation_time_constant", tau_deact, "s"),
        MuscleParameter("ignore_tendon_compliance", "1", "boolean"),
    ]
    if scale is not None:
        values.append(MuscleParameter("source_f_max_scale", scale, "dimensionless"))
    if moment_arm is not None:
        values.append(MuscleParameter("moment_arm", moment_arm, "mm"))
    if reference_angle is not None:
        values.append(MuscleParameter("reference_angle", reference_angle, "rad"))
    return tuple(values)


def _official_catalog() -> MuscleCatalog:
    return MuscleCatalog(
        catalog_id="org.flybrian.muscles.flymimic-t1",
        version="9ea1131",
        source=(
            f"FlyMimic {_FLYMIMIC_COMMIT}, Apache-2.0; exact "
            f"Millard2012EquilibriumMuscle parameters from {_FLYMIMIC_OSIM} "
            "(SHA-256 091a173b9cfb26a64228935c6f6ebfc93c26a9425a0b5e5c1bb463c644cb89de)"
        ),
        muscles=tuple(
            Muscle(
                muscle_id=name,
                body_region="T1_left",
                model_id="org.flymimic.millard2012-equilibrium-muscle",
                model_version="9ea1131",
                source=f"{_FLYMIMIC_OSIM}#Millard2012EquilibriumMuscle={name}",
                parameters=_parameters(
                    f_max,
                    l_opt,
                    l_slack,
                    v_max,
                    tau_act="0.0001",
                    tau_deact="0.00040000000000000002",
                ),
            )
            for name, f_max, l_opt, l_slack, v_max in _OFFICIAL_PARAMETERS
        ),
    )


def _historical_catalog() -> MuscleCatalog:
    muscles = []
    for leg_id, body_region, scale in _LEG_LAYOUT:
        for name, f_max, l_opt, l_slack, v_max in _HISTORICAL_PARAMETERS:
            primary_dof = _DOF_MAP[name][0][0]
            scaled_force = Decimal(f_max) * Decimal(scale)
            muscles.append(
                Muscle(
                    muscle_id=f"{leg_id}/{name}",
                    body_region=body_region,
                    model_id="org.flybrian.hill.historical-experimental",
                    model_version="1.0",
                    source=_HISTORICAL_SOURCE,
                    parameters=_parameters(
                        str(scaled_force),
                        l_opt,
                        l_slack,
                        v_max,
                        tau_act="0.01",
                        tau_deact="0.04",
                        scale=scale,
                        moment_arm=_MOMENT_ARMS_MM[name],
                        reference_angle=_STANDING_ANGLES[leg_id][primary_dof],
                    ),
                )
            )
    return MuscleCatalog(
        catalog_id="org.flybrian.muscles.historical-six-leg-hill",
        version="1.0",
        source=_HISTORICAL_SOURCE,
        muscles=tuple(muscles),
    )


FLYMIMIC_T1_MUSCLE_CATALOG = _official_catalog()
FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG = _historical_catalog()


@dataclass(frozen=True)
class MuscleDofProjection:
    muscle_id: str
    dof_name: str
    actuator_id: str
    direction: ProjectionDirection
    source: str

    def __post_init__(self) -> None:
        _text(self.muscle_id, "muscle_projection.muscle_id", maximum=255)
        _text(self.dof_name, "muscle_projection.dof_name", maximum=255)
        _text(self.actuator_id, "muscle_projection.actuator_id", maximum=255)
        _text(self.source, "muscle_projection.source")
        if self.direction not in ("positive", "negative"):
            raise EmbodimentError("muscle_projection.direction is unsupported")

    def to_dict(self) -> dict[str, object]:
        return {
            "muscle_id": self.muscle_id,
            "dof_name": self.dof_name,
            "actuator_id": self.actuator_id,
            "direction": self.direction,
            "source": self.source,
        }


def _projections() -> tuple[MuscleDofProjection, ...]:
    items = []
    actuator_ids = {
        actuator.actuator_id for actuator in FLYBODY_78_ACTUATOR_CATALOG.actuators
    }
    for leg_id, body_region, _ in _LEG_LAYOUT:
        for source_name, *_ in _HISTORICAL_PARAMETERS:
            muscle_id = f"{leg_id}/{source_name}"
            for dof_name, direction in _DOF_MAP[source_name]:
                actuator_id = f"{dof_name}_{body_region}"
                if actuator_id not in actuator_ids:
                    raise EmbodimentError(
                        f"historical muscle projection references {actuator_id!r}"
                    )
                items.append(
                    MuscleDofProjection(
                        muscle_id,
                        dof_name,
                        actuator_id,
                        direction,
                        _HISTORICAL_SOURCE,
                    )
                )
    return tuple(items)


FLYBRIAN_HISTORICAL_MUSCLE_DOF_PROJECTIONS = _projections()
FLYBRIAN_HISTORICAL_MUSCLE_DOF_PROJECTIONS_SHA256 = _sha256(
    [item.to_dict() for item in FLYBRIAN_HISTORICAL_MUSCLE_DOF_PROJECTIONS]
)


@dataclass(frozen=True)
class MuscleTargetBridgeEntry:
    target_label: str
    muscle_names: tuple[str, ...]
    confidence_class: BridgeConfidence
    source: str

    def __post_init__(self) -> None:
        _text(self.target_label, "muscle_bridge.target_label", maximum=255)
        if self.confidence_class not in ("high", "medium", "no_equivalent"):
            raise EmbodimentError("muscle_bridge.confidence_class is unsupported")
        _text(self.source, "muscle_bridge.source")
        if len(self.muscle_names) != len(set(self.muscle_names)):
            raise EmbodimentError("muscle_bridge muscle names must be unique")
        for name in self.muscle_names:
            _text(name, "muscle_bridge.muscle_name", maximum=255)

    def to_dict(self) -> dict[str, object]:
        return {
            "target_label": self.target_label,
            "muscle_names": list(self.muscle_names),
            "confidence_class": self.confidence_class,
            "source": self.source,
        }


FLYBRIAN_HISTORICAL_MANC_TARGET_BRIDGE = (
    MuscleTargetBridgeEntry("Ti extensor", ("LFTibia_extensor_93932",), "high", _HISTORICAL_SOURCE),
    MuscleTargetBridgeEntry("Ti flexor", ("LFTibia_flex_93434",), "high", _HISTORICAL_SOURCE),
    MuscleTargetBridgeEntry(
        "Acc. ti flexor", ("LFTibia_flex_93434",), "high", _HISTORICAL_SOURCE
    ),
    MuscleTargetBridgeEntry(
        "Pleural remotor/abductor",
        ("LFC_pleural_remotor_and_abductor",),
        "high",
        _HISTORICAL_SOURCE,
    ),
    MuscleTargetBridgeEntry(
        "Sternal anterior rotator",
        ("LFC_sternal_anterior_rotator",),
        "high",
        _HISTORICAL_SOURCE,
    ),
    MuscleTargetBridgeEntry(
        "Sternal posterior rotator",
        ("LFC_sternal_posterior_rotator",),
        "high",
        _HISTORICAL_SOURCE,
    ),
    MuscleTargetBridgeEntry(
        "Sternal adductor", ("LFC_sternal_adductor",), "high", _HISTORICAL_SOURCE
    ),
    MuscleTargetBridgeEntry(
        "Acc. tr flexor",
        ("LFF_accesory_trochanter_flexor",),
        "high",
        _HISTORICAL_SOURCE,
    ),
    MuscleTargetBridgeEntry(
        "Fe reductor", ("LFF_trochanter_extensor",), "high", _HISTORICAL_SOURCE
    ),
    MuscleTargetBridgeEntry(
        "Tr flexor",
        ("LFF_trochanter_flexor_a", "LFF_trochanter_flexor_b"),
        "medium",
        _HISTORICAL_SOURCE,
    ),
    MuscleTargetBridgeEntry(
        "Tr extensor",
        (
            "LFF_sterno-tergo-trochanter_extensor_a",
            "LFF_sterno-tergo-trochanter_extensor_b",
        ),
        "medium",
        _HISTORICAL_SOURCE,
    ),
    MuscleTargetBridgeEntry(
        "Tergopleural/Pleural promotor",
        (
            "LFC_tergopleural_promotor_a",
            "LFC_tergopleural_promotor_b",
            "LFC_pleural_promotor",
        ),
        "medium",
        _HISTORICAL_SOURCE,
    ),
    *(
        MuscleTargetBridgeEntry(label, (), "no_equivalent", _HISTORICAL_SOURCE)
        for label in (
            "Sternotrochanter",
            "Tergotr.",
            "Ta depressor",
            "Ta levator",
            "ltm",
            "ltm1-tibia",
            "ltm2-femur",
        )
    ),
)
FLYBRIAN_HISTORICAL_MANC_TARGET_BRIDGE_SHA256 = _sha256(
    [item.to_dict() for item in FLYBRIAN_HISTORICAL_MANC_TARGET_BRIDGE]
)


def _manc_muscle_profile() -> MuscleProfile:
    leg_by_region = {body_region: leg_id for leg_id, body_region, _ in _LEG_LAYOUT}
    target_rules = []
    for body_region, leg_id in leg_by_region.items():
        for bridge in FLYBRIAN_HISTORICAL_MANC_TARGET_BRIDGE:
            if not bridge.muscle_names:
                continue
            target_rules.append(
                MuscleTargetRule(
                    body_region,
                    bridge.target_label,
                    tuple(
                        MuscleTarget(f"{leg_id}/{name}", "1")
                        for name in bridge.muscle_names
                    ),
                )
            )
    body_rules = tuple(
        BodyRegionRule(nerve, region)
        for nerve, region in (
            ("DProN_L", "T1_left"),
            ("ProAN_L", "T1_left"),
            ("ProLN_L", "T1_left"),
            ("VProN_L", "T1_left"),
            ("DProN_R", "T1_right"),
            ("ProAN_R", "T1_right"),
            ("ProLN_R", "T1_right"),
            ("VProN_R", "T1_right"),
            ("MesoLN_L", "T2_left"),
            ("MesoLN_R", "T2_right"),
            ("AbN1_L", "T3_left"),
            ("MetaLN_L", "T3_left"),
            ("AbN1_R", "T3_right"),
            ("MetaLN_R", "T3_right"),
        )
    )
    return MuscleProfile(
        profile_id="org.flybrian.mapping.manc-to-historical-six-leg-muscle",
        version="1.0",
        source=(
            f"{_HISTORICAL_SOURCE}; target_bridge_sha256="
            f"{FLYBRIAN_HISTORICAL_MANC_TARGET_BRIDGE_SHA256}"
        ),
        compatible_dataset_ids=("manc:v1.2.1",),
        body_region_rules=body_rules,
        target_rules=tuple(target_rules),
        actuator_rules=tuple(
            MuscleActuatorRule(
                item.muscle_id,
                item.actuator_id,
                "1",
                item.direction,
            )
            for item in FLYBRIAN_HISTORICAL_MUSCLE_DOF_PROJECTIONS
        ),
        confidence_rules=tuple(
            ConfidenceRule(certainty, str(Decimal(certainty) / Decimal(5)))
            for certainty in range(1, 6)
        ),
        missing_certainty_confidence="0.5",
        generic_targets=("front leg", "middle leg", "hind leg"),
        allow_multiple_body_regions=False,
    )


FLYBRIAN_HISTORICAL_MANC_MUSCLE_PROFILE = _manc_muscle_profile()


@dataclass(frozen=True)
class HistoricalHillProfile:
    profile_id: str
    version: str
    source: str
    muscle_catalog_id: str
    muscle_catalog_version: str
    muscle_catalog_sha256: str
    muscle_projection_sha256: str
    state_advance_policy: StateAdvancePolicy
    force_length_width: ExactDecimal = "0.45"
    concentric_shape_factor: ExactDecimal = "0.25"
    eccentric_force_factor: ExactDecimal = "1.8"
    passive_shape_factor: ExactDecimal = "4"
    passive_strain_at_max: ExactDecimal = "0.6"
    passive_force_cap_ratio: ExactDecimal = "0.5"
    length_sensitivity_cap: ExactDecimal = "1"
    length_norm_min: ExactDecimal = "0.5"
    length_norm_max: ExactDecimal = "1.5"
    shortening_velocity_limit_ratio: ExactDecimal = "0.95"
    lengthening_velocity_limit_ratio: ExactDecimal = "5"

    def __post_init__(self) -> None:
        for path, value in (
            ("profile_id", self.profile_id),
            ("version", self.version),
            ("source", self.source),
            ("muscle_catalog_id", self.muscle_catalog_id),
            ("muscle_catalog_version", self.muscle_catalog_version),
        ):
            _text(value, f"hill_profile.{path}")
        for path, digest in (
            ("muscle_catalog_sha256", self.muscle_catalog_sha256),
            ("muscle_projection_sha256", self.muscle_projection_sha256),
        ):
            if len(digest) != 64 or any(
                character not in "0123456789abcdef" for character in digest
            ):
                raise EmbodimentError(f"hill_profile.{path} must be lowercase SHA-256")
        if self.state_advance_policy not in (
            "once_per_muscle_primary_dof",
            "per_projection_legacy",
        ):
            raise EmbodimentError("hill_profile.state_advance_policy is unsupported")
        exact_fields = (
            "force_length_width",
            "concentric_shape_factor",
            "eccentric_force_factor",
            "passive_shape_factor",
            "passive_strain_at_max",
            "passive_force_cap_ratio",
            "length_sensitivity_cap",
            "length_norm_min",
            "length_norm_max",
            "shortening_velocity_limit_ratio",
            "lengthening_velocity_limit_ratio",
        )
        for field_name in exact_fields:
            decimal_value = _positive_decimal(
                getattr(self, field_name), f"hill_profile.{field_name}"
            )
            object.__setattr__(self, field_name, decimal_value)
        if _decimal(self.length_norm_min, "hill_profile.length_norm_min") >= _decimal(
            self.length_norm_max, "hill_profile.length_norm_max"
        ):
            raise EmbodimentError("hill_profile length range must be increasing")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "profile_id": self.profile_id,
            "version": self.version,
            "source": self.source,
            "muscle_catalog_id": self.muscle_catalog_id,
            "muscle_catalog_version": self.muscle_catalog_version,
            "muscle_catalog_sha256": self.muscle_catalog_sha256,
            "muscle_projection_sha256": self.muscle_projection_sha256,
            "state_advance_policy": self.state_advance_policy,
            "force_length_width": str(self.force_length_width),
            "concentric_shape_factor": str(self.concentric_shape_factor),
            "eccentric_force_factor": str(self.eccentric_force_factor),
            "passive_shape_factor": str(self.passive_shape_factor),
            "passive_strain_at_max": str(self.passive_strain_at_max),
            "passive_force_cap_ratio": str(self.passive_force_cap_ratio),
            "length_sensitivity_cap": str(self.length_sensitivity_cap),
            "length_norm_min": str(self.length_norm_min),
            "length_norm_max": str(self.length_norm_max),
            "shortening_velocity_limit_ratio": str(
                self.shortening_velocity_limit_ratio
            ),
            "lengthening_velocity_limit_ratio": str(
                self.lengthening_velocity_limit_ratio
            ),
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def _hill_profile(profile_id: str, policy: StateAdvancePolicy) -> HistoricalHillProfile:
    return HistoricalHillProfile(
        profile_id=profile_id,
        version="1.0",
        source=_HISTORICAL_SOURCE,
        muscle_catalog_id=FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG.catalog_id,
        muscle_catalog_version=FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG.version,
        muscle_catalog_sha256=FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG.sha256(),
        muscle_projection_sha256=(
            FLYBRIAN_HISTORICAL_MUSCLE_DOF_PROJECTIONS_SHA256
        ),
        state_advance_policy=policy,
    )


FLYBRIAN_HISTORICAL_HILL_BUG_COMPATIBLE_PROFILE = _hill_profile(
    "org.flybrian.hill.historical-multi-advance", "per_projection_legacy"
)
FLYBRIAN_HISTORICAL_HILL_CORRECTED_PROFILE = _hill_profile(
    "org.flybrian.hill.historical-single-advance", "once_per_muscle_primary_dof"
)


@dataclass(frozen=True)
class MuscleDriveProfile:
    profile_id: str
    version: str
    source: str
    muscle_catalog_id: str
    muscle_catalog_version: str
    muscle_catalog_sha256: str
    rate_normalizer_hz: ExactDecimal
    sigmoid_k_hz: ExactDecimal
    extensor_rate_normalizer_hz: ExactDecimal | None = None
    flexor_rate_normalizer_hz: ExactDecimal | None = None

    def __post_init__(self) -> None:
        _text(self.profile_id, "muscle_drive_profile.profile_id", maximum=255)
        _text(self.version, "muscle_drive_profile.version", maximum=255)
        _text(self.source, "muscle_drive_profile.source")
        _text(
            self.muscle_catalog_id,
            "muscle_drive_profile.muscle_catalog_id",
            maximum=255,
        )
        _text(
            self.muscle_catalog_version,
            "muscle_drive_profile.muscle_catalog_version",
            maximum=255,
        )
        if len(self.muscle_catalog_sha256) != 64 or any(
            character not in "0123456789abcdef"
            for character in self.muscle_catalog_sha256
        ):
            raise EmbodimentError(
                "muscle_drive_profile.muscle_catalog_sha256 must be lowercase SHA-256"
            )
        object.__setattr__(
            self,
            "rate_normalizer_hz",
            _positive_decimal(self.rate_normalizer_hz, "rate_normalizer_hz"),
        )
        object.__setattr__(
            self,
            "sigmoid_k_hz",
            _positive_decimal(self.sigmoid_k_hz, "sigmoid_k_hz"),
        )
        dual = (
            self.extensor_rate_normalizer_hz is not None,
            self.flexor_rate_normalizer_hz is not None,
        )
        if dual[0] != dual[1]:
            raise EmbodimentError("dual muscle drive normalizers must be supplied together")
        if dual[0]:
            object.__setattr__(
                self,
                "extensor_rate_normalizer_hz",
                _positive_decimal(
                    self.extensor_rate_normalizer_hz,
                    "extensor_rate_normalizer_hz",
                ),
            )
            object.__setattr__(
                self,
                "flexor_rate_normalizer_hz",
                _positive_decimal(
                    self.flexor_rate_normalizer_hz,
                    "flexor_rate_normalizer_hz",
                ),
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "profile_id": self.profile_id,
            "version": self.version,
            "source": self.source,
            "muscle_catalog_id": self.muscle_catalog_id,
            "muscle_catalog_version": self.muscle_catalog_version,
            "muscle_catalog_sha256": self.muscle_catalog_sha256,
            "rate_normalizer_hz": str(self.rate_normalizer_hz),
            "sigmoid_k_hz": str(self.sigmoid_k_hz),
            "extensor_rate_normalizer_hz": (
                None
                if self.extensor_rate_normalizer_hz is None
                else str(self.extensor_rate_normalizer_hz)
            ),
            "flexor_rate_normalizer_hz": (
                None
                if self.flexor_rate_normalizer_hz is None
                else str(self.flexor_rate_normalizer_hz)
            ),
        }

    def sha256(self) -> str:
        return _sha256(self.to_dict())


FLYBRIAN_HISTORICAL_MUSCLE_DRIVE_PROFILE = MuscleDriveProfile(
    profile_id="org.flybrian.muscle-drive.historical-sigmoid",
    version="1.0",
    source=_HISTORICAL_SOURCE,
    muscle_catalog_id=FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG.catalog_id,
    muscle_catalog_version=FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG.version,
    muscle_catalog_sha256=FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG.sha256(),
    rate_normalizer_hz="30",
    sigmoid_k_hz="8",
)


@dataclass(frozen=True)
class MuscleNeuronPool:
    muscle_id: str
    neuron_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        _text(self.muscle_id, "muscle_neuron_pool.muscle_id", maximum=255)
        if len(self.neuron_ids) != len(set(self.neuron_ids)):
            raise EmbodimentError("muscle_neuron_pool neuron IDs must be unique")
        for neuron_id in self.neuron_ids:
            if isinstance(neuron_id, bool) or not isinstance(neuron_id, int) or neuron_id < 0:
                raise EmbodimentError("muscle_neuron_pool neuron IDs must be non-negative integers")


@dataclass(frozen=True)
class MuscleDrive:
    muscle_id: str
    value: float
    mean_rate_hz: float
    neuron_count: int

    def __post_init__(self) -> None:
        _text(self.muscle_id, "muscle_drive.muscle_id", maximum=255)
        value = _binary64(self.value, "muscle_drive.value")
        rate = _binary64(self.mean_rate_hz, "muscle_drive.mean_rate_hz")
        if value < 0 or value > 1:
            raise EmbodimentError("muscle_drive.value must be between zero and one")
        if rate < 0:
            raise EmbodimentError("muscle_drive.mean_rate_hz must be non-negative")
        if (
            isinstance(self.neuron_count, bool)
            or not isinstance(self.neuron_count, int)
            or self.neuron_count < 0
        ):
            raise EmbodimentError("muscle_drive.neuron_count must be non-negative integer")
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "mean_rate_hz", rate)

    def to_dict(self) -> dict[str, object]:
        return {
            "muscle_id": self.muscle_id,
            "value_binary64": _float_hex(self.value),
            "mean_rate_hz_binary64": _float_hex(self.mean_rate_hz),
            "neuron_count": self.neuron_count,
        }


@dataclass(frozen=True)
class MuscleDriveResult:
    profile_id: str
    profile_version: str
    profile_sha256: str
    window_duration_s: float
    drives: tuple[MuscleDrive, ...]

    def __post_init__(self) -> None:
        _text(self.profile_id, "muscle_drive_result.profile_id", maximum=255)
        _text(self.profile_version, "muscle_drive_result.profile_version", maximum=255)
        if len(self.profile_sha256) != 64 or any(
            char not in "0123456789abcdef" for char in self.profile_sha256
        ):
            raise EmbodimentError("muscle_drive_result.profile_sha256 must be lowercase SHA-256")
        duration = _binary64(
            self.window_duration_s, "muscle_drive_result.window_duration_s"
        )
        if duration <= 0:
            raise EmbodimentError("muscle_drive_result.window_duration_s must be positive")
        muscle_ids = tuple(item.muscle_id for item in self.drives)
        if len(muscle_ids) != len(set(muscle_ids)):
            raise EmbodimentError("muscle_drive_result drives must have unique muscle IDs")
        object.__setattr__(self, "window_duration_s", duration)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "profile_sha256": self.profile_sha256,
            "window_duration_s_binary64": _float_hex(self.window_duration_s),
            "drives": [item.to_dict() for item in self.drives],
        }

    def sha256(self) -> str:
        return _sha256(self.to_dict())


def _muscle_class(muscle_id: str) -> str:
    lowered = muscle_id.lower()
    if "flexor" in lowered:
        return "flex"
    if "extensor" in lowered:
        return "ext"
    if any(key in lowered for key in ("sternal", "pleural", "remotor", "promotor")):
        return "ext"
    return "unknown"


def _logistic(value: float) -> float:
    if value >= 0:
        return 1.0 / (1.0 + math.exp(-value))
    exponent = math.exp(value)
    return exponent / (1.0 + exponent)


def muscle_drives_from_spike_counts(
    profile: MuscleDriveProfile,
    pools: Sequence[MuscleNeuronPool],
    spike_counts: Mapping[int, int],
    window_duration_s: object,
    catalog: MuscleCatalog = FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG,
) -> MuscleDriveResult:
    if (
        catalog.catalog_id != profile.muscle_catalog_id
        or catalog.version != profile.muscle_catalog_version
        or catalog.sha256() != profile.muscle_catalog_sha256
    ):
        raise EmbodimentError("muscle drive catalog does not match profile authority")
    duration = _binary64(window_duration_s, "window_duration_s")
    if duration <= 0:
        raise EmbodimentError("window_duration_s must be positive")
    pool_ids = tuple(item.muscle_id for item in pools)
    if len(pool_ids) != len(set(pool_ids)):
        raise EmbodimentError("muscle drive pools must have unique muscle IDs")
    catalog_ids = {item.muscle_id for item in catalog.muscles}
    source_names = {
        muscle_id.split("/", 1)[1]
        for muscle_id in catalog_ids
        if "/" in muscle_id
    }
    unknown_muscles = set(pool_ids) - catalog_ids - source_names
    if unknown_muscles:
        raise EmbodimentError(
            f"muscle drive pool references unknown muscle {sorted(unknown_muscles)[0]!r}"
        )
    for neuron_id, count in spike_counts.items():
        if isinstance(neuron_id, bool) or not isinstance(neuron_id, int) or neuron_id < 0:
            raise EmbodimentError("spike count neuron IDs must be non-negative integers")
        if isinstance(count, bool) or not isinstance(count, int) or count < 0:
            raise EmbodimentError("spike counts must be non-negative integers")

    default_normalizer = float(profile.rate_normalizer_hz)
    sigmoid_k = float(profile.sigmoid_k_hz)
    drives = []
    for pool in pools:
        if not pool.neuron_ids:
            mean_rate = 0.0
            drive = 0.0
        else:
            rates = tuple(spike_counts.get(item, 0) / duration for item in pool.neuron_ids)
            mean_rate = math.fsum(rates) / len(rates)
            normalizer = default_normalizer
            if profile.extensor_rate_normalizer_hz is not None:
                if _muscle_class(pool.muscle_id) == "flex":
                    assert profile.flexor_rate_normalizer_hz is not None
                    normalizer = float(profile.flexor_rate_normalizer_hz)
                else:
                    normalizer = float(profile.extensor_rate_normalizer_hz)
            drive = _logistic((mean_rate - normalizer) / sigmoid_k)
        drives.append(MuscleDrive(pool.muscle_id, drive, mean_rate, len(pool.neuron_ids)))
    return MuscleDriveResult(
        profile.profile_id,
        profile.version,
        profile.sha256(),
        duration,
        tuple(drives),
    )


@dataclass(frozen=True)
class MuscleActivationState:
    profile_id: str
    profile_version: str
    profile_sha256: str
    muscle_catalog_id: str
    muscle_catalog_version: str
    muscle_catalog_sha256: str
    muscle_id: str
    activation: float

    def __post_init__(self) -> None:
        activation = _binary64(self.activation, "muscle_state.activation")
        if activation < 0 or activation > 1:
            raise EmbodimentError("muscle_state.activation must be between zero and one")
        object.__setattr__(self, "activation", activation)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "profile_sha256": self.profile_sha256,
            "muscle_catalog_id": self.muscle_catalog_id,
            "muscle_catalog_version": self.muscle_catalog_version,
            "muscle_catalog_sha256": self.muscle_catalog_sha256,
            "muscle_id": self.muscle_id,
            "activation_binary64": _float_hex(self.activation),
        }

    def sha256(self) -> str:
        return _sha256(self.to_dict())


@dataclass(frozen=True)
class HistoricalMuscleStepResult:
    prior_state: MuscleActivationState
    next_state: MuscleActivationState
    neural_drive: float
    joint_angle: float
    joint_velocity: float
    dt: float
    normalized_length: float
    normalized_velocity: float
    active_force_mn: float
    passive_force_mn: float
    total_force_mn: float
    torque_mn_mm: float

    def to_dict(self) -> dict[str, object]:
        values = {
            "neural_drive": self.neural_drive,
            "joint_angle": self.joint_angle,
            "joint_velocity": self.joint_velocity,
            "dt": self.dt,
            "normalized_length": self.normalized_length,
            "normalized_velocity": self.normalized_velocity,
            "active_force_mn": self.active_force_mn,
            "passive_force_mn": self.passive_force_mn,
            "total_force_mn": self.total_force_mn,
            "torque_mn_mm": self.torque_mn_mm,
        }
        return {
            "schema_version": "1.0",
            "prior_state": self.prior_state.to_dict(),
            "next_state": self.next_state.to_dict(),
            **{f"{key}_binary64": _float_hex(value) for key, value in values.items()},
        }

    def sha256(self) -> str:
        return _sha256(self.to_dict())


def _assert_profile_catalog(
    profile: HistoricalHillProfile,
    catalog: MuscleCatalog,
) -> None:
    if (
        catalog.catalog_id != profile.muscle_catalog_id
        or catalog.version != profile.muscle_catalog_version
        or catalog.sha256() != profile.muscle_catalog_sha256
    ):
        raise EmbodimentError("muscle catalog does not match Hill profile authority")


def _muscle(catalog: MuscleCatalog, muscle_id: str) -> Muscle:
    for muscle in catalog.muscles:
        if muscle.muscle_id == muscle_id:
            return muscle
    raise EmbodimentError(f"unknown muscle {muscle_id!r}")


def _muscle_parameters(muscle: Muscle) -> dict[str, float]:
    return {item.name: float(item.value) for item in muscle.parameters}


def initial_muscle_activation_state(
    profile: HistoricalHillProfile,
    catalog: MuscleCatalog,
    muscle_id: str,
    activation: object = "0",
) -> MuscleActivationState:
    _assert_profile_catalog(profile, catalog)
    _muscle(catalog, muscle_id)
    return MuscleActivationState(
        profile.profile_id,
        profile.version,
        profile.sha256(),
        catalog.catalog_id,
        catalog.version,
        catalog.sha256(),
        muscle_id,
        _binary64(activation, "activation"),
    )


def _assert_state_identity(
    profile: HistoricalHillProfile,
    catalog: MuscleCatalog,
    state: MuscleActivationState,
) -> None:
    if (
        state.profile_id != profile.profile_id
        or state.profile_version != profile.version
        or state.profile_sha256 != profile.sha256()
    ):
        raise EmbodimentError("muscle state profile identity does not match")
    if (
        state.muscle_catalog_id != catalog.catalog_id
        or state.muscle_catalog_version != catalog.version
        or state.muscle_catalog_sha256 != catalog.sha256()
    ):
        raise EmbodimentError("muscle state catalog identity does not match")


def step_historical_hill_muscle(
    profile: HistoricalHillProfile,
    catalog: MuscleCatalog,
    state: MuscleActivationState,
    *,
    neural_drive: object,
    joint_angle: object,
    joint_velocity: object,
    dt: object,
) -> HistoricalMuscleStepResult:
    _assert_profile_catalog(profile, catalog)
    _assert_state_identity(profile, catalog, state)
    muscle = _muscle(catalog, state.muscle_id)
    parameters = _muscle_parameters(muscle)
    required = {
        "max_isometric_force",
        "optimal_fiber_length",
        "pennation_angle_at_optimal",
        "max_contraction_velocity",
        "activation_time_constant",
        "deactivation_time_constant",
        "moment_arm",
        "reference_angle",
    }
    if not required <= set(parameters):
        raise EmbodimentError("muscle lacks historical Hill parameters")

    drive = _binary64(neural_drive, "neural_drive")
    angle = _binary64(joint_angle, "joint_angle")
    velocity = _binary64(joint_velocity, "joint_velocity")
    step_seconds = _binary64(dt, "dt")
    if step_seconds < 0:
        raise EmbodimentError("dt must be non-negative")
    drive_clamped = min(max(drive, 0.0), 1.0)
    prior_activation = state.activation
    tau = (
        parameters["activation_time_constant"]
        if drive_clamped > prior_activation
        else parameters["deactivation_time_constant"]
    )
    if tau <= 0:
        raise EmbodimentError("muscle activation time constant must be positive")
    activation = min(
        max(prior_activation + ((drive_clamped - prior_activation) / tau) * step_seconds, 0.0),
        1.0,
    )

    f_max = parameters["max_isometric_force"]
    l_opt = parameters["optimal_fiber_length"]
    v_max = parameters["max_contraction_velocity"]
    moment_arm = parameters["moment_arm"]
    if f_max <= 0 or l_opt <= 0 or v_max <= 0 or moment_arm <= 0:
        raise EmbodimentError("historical Hill physical constants must be positive")
    sensitivity = min(moment_arm / l_opt, float(profile.length_sensitivity_cap))
    normalized_length = min(
        max(
            1.0 + sensitivity * (angle - parameters["reference_angle"]),
            float(profile.length_norm_min),
        ),
        float(profile.length_norm_max),
    )
    normalized_velocity = min(
        max(
            sensitivity * velocity,
            -v_max * float(profile.shortening_velocity_limit_ratio),
        ),
        v_max * float(profile.lengthening_velocity_limit_ratio),
    )
    force_length = math.exp(
        -((normalized_length - 1.0) / float(profile.force_length_width)) ** 2
    )
    if normalized_velocity <= 0:
        denominator = v_max - normalized_velocity / float(profile.concentric_shape_factor)
        force_velocity = (
            0.0
            if denominator <= 0
            else (v_max + normalized_velocity) / denominator
        )
    else:
        eccentric = float(profile.eccentric_force_factor)
        force_velocity = min(
            (v_max * eccentric + normalized_velocity) / (v_max + normalized_velocity),
            eccentric,
        )
    active_force = f_max * activation * force_length * force_velocity
    if normalized_length <= 1.0:
        passive_multiplier = 0.0
    else:
        strain = (normalized_length - 1.0) / float(profile.passive_strain_at_max)
        passive_shape = float(profile.passive_shape_factor)
        passive_multiplier = (math.exp(passive_shape * strain) - 1.0) / (
            math.exp(passive_shape) - 1.0
        )
    passive_force = min(
        f_max * passive_multiplier,
        f_max * float(profile.passive_force_cap_ratio),
    )
    total_force = active_force + passive_force
    torque = total_force * moment_arm * math.cos(
        parameters["pennation_angle_at_optimal"]
    )
    outputs = (
        normalized_length,
        normalized_velocity,
        active_force,
        passive_force,
        total_force,
        torque,
    )
    if not all(math.isfinite(value) for value in outputs):
        raise EmbodimentError("historical Hill transition produced non-finite output")
    next_state = MuscleActivationState(
        state.profile_id,
        state.profile_version,
        state.profile_sha256,
        state.muscle_catalog_id,
        state.muscle_catalog_version,
        state.muscle_catalog_sha256,
        state.muscle_id,
        activation,
    )
    return HistoricalMuscleStepResult(
        state,
        next_state,
        drive,
        angle,
        velocity,
        step_seconds,
        normalized_length,
        normalized_velocity,
        active_force,
        passive_force,
        total_force,
        torque,
    )


@dataclass(frozen=True)
class NamedJointTorque:
    dof_name: str
    value_mn_mm: float

    def __post_init__(self) -> None:
        _text(self.dof_name, "named_joint_torque.dof_name", maximum=255)
        object.__setattr__(
            self,
            "value_mn_mm",
            _binary64(self.value_mn_mm, "named_joint_torque.value_mn_mm"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "dof_name": self.dof_name,
            "value_mn_mm_binary64": _float_hex(self.value_mn_mm),
        }


@dataclass(frozen=True)
class HistoricalLegStepResult:
    profile_id: str
    profile_version: str
    profile_sha256: str
    muscle_catalog_id: str
    muscle_catalog_version: str
    muscle_catalog_sha256: str
    muscle_projection_sha256: str
    body_region: str
    next_states: tuple[MuscleActivationState, ...]
    torques: tuple[NamedJointTorque, ...]
    muscle_steps: tuple[HistoricalMuscleStepResult, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "profile_sha256": self.profile_sha256,
            "muscle_catalog_id": self.muscle_catalog_id,
            "muscle_catalog_version": self.muscle_catalog_version,
            "muscle_catalog_sha256": self.muscle_catalog_sha256,
            "muscle_projection_sha256": self.muscle_projection_sha256,
            "body_region": self.body_region,
            "next_states": [item.to_dict() for item in self.next_states],
            "torques": [item.to_dict() for item in self.torques],
            "muscle_steps": [item.to_dict() for item in self.muscle_steps],
        }

    def sha256(self) -> str:
        return _sha256(self.to_dict())


def initial_historical_leg_states(
    profile: HistoricalHillProfile,
    catalog: MuscleCatalog,
    body_region: str,
) -> tuple[MuscleActivationState, ...]:
    muscles = tuple(item for item in catalog.muscles if item.body_region == body_region)
    if not muscles:
        raise EmbodimentError(f"unknown historical muscle body region {body_region!r}")
    return tuple(
        initial_muscle_activation_state(profile, catalog, item.muscle_id)
        for item in muscles
    )


def step_historical_hill_leg(
    profile: HistoricalHillProfile,
    catalog: MuscleCatalog,
    projections: Sequence[MuscleDofProjection],
    body_region: str,
    states: Sequence[MuscleActivationState],
    drives: Mapping[str, object],
    joint_states: Mapping[str, tuple[object, object]],
    dt: object,
) -> HistoricalLegStepResult:
    _assert_profile_catalog(profile, catalog)
    projection_sha256 = _sha256([item.to_dict() for item in projections])
    if projection_sha256 != profile.muscle_projection_sha256:
        raise EmbodimentError("muscle projections do not match Hill profile authority")
    muscles = tuple(item for item in catalog.muscles if item.body_region == body_region)
    if not muscles:
        raise EmbodimentError(f"unknown historical muscle body region {body_region!r}")
    muscle_ids = tuple(item.muscle_id for item in muscles)
    state_by_muscle = {item.muscle_id: item for item in states}
    if set(state_by_muscle) != set(muscle_ids) or len(state_by_muscle) != len(muscle_ids):
        raise EmbodimentError("leg states must cover every muscle exactly once")
    unknown_drives = set(drives) - set(muscle_ids)
    if unknown_drives:
        raise EmbodimentError(f"drive references unknown leg muscle {sorted(unknown_drives)[0]!r}")
    projection_by_muscle: dict[str, list[MuscleDofProjection]] = {}
    seen_projection: set[tuple[str, str]] = set()
    for projection in projections:
        if projection.muscle_id not in muscle_ids:
            continue
        key = (projection.muscle_id, projection.dof_name)
        if key in seen_projection:
            raise EmbodimentError("leg muscle projections must be unique")
        seen_projection.add(key)
        projection_by_muscle.setdefault(projection.muscle_id, []).append(projection)
    if set(projection_by_muscle) != set(muscle_ids):
        raise EmbodimentError("leg projections must cover every muscle")
    required_dofs = {
        projection.dof_name
        for values in projection_by_muscle.values()
        for projection in values
    }
    if not required_dofs <= set(joint_states):
        missing = sorted(required_dofs - set(joint_states))
        raise EmbodimentError(f"joint state is missing {missing[0]!r}")
    if set(joint_states) - required_dofs:
        unknown = sorted(set(joint_states) - required_dofs)
        raise EmbodimentError(f"joint state contains unknown DOF {unknown[0]!r}")

    contributions: dict[str, list[float]] = {dof: [] for dof in sorted(required_dofs)}
    next_states = []
    step_results = []
    for muscle in muscles:
        current = state_by_muscle[muscle.muscle_id]
        _assert_state_identity(profile, catalog, current)
        muscle_projections = projection_by_muscle[muscle.muscle_id]
        drive = drives.get(muscle.muscle_id, "0")
        if profile.state_advance_policy == "once_per_muscle_primary_dof":
            primary = muscle_projections[0]
            angle, velocity = joint_states[primary.dof_name]
            result = step_historical_hill_muscle(
                profile,
                catalog,
                current,
                neural_drive=drive,
                joint_angle=angle,
                joint_velocity=velocity,
                dt=dt,
            )
            step_results.append(result)
            current = result.next_state
            for projection in muscle_projections:
                sign = 1.0 if projection.direction == "positive" else -1.0
                contributions[projection.dof_name].append(sign * result.torque_mn_mm)
        else:
            for projection in muscle_projections:
                angle, velocity = joint_states[projection.dof_name]
                result = step_historical_hill_muscle(
                    profile,
                    catalog,
                    current,
                    neural_drive=drive,
                    joint_angle=angle,
                    joint_velocity=velocity,
                    dt=dt,
                )
                step_results.append(result)
                current = result.next_state
                sign = 1.0 if projection.direction == "positive" else -1.0
                contributions[projection.dof_name].append(sign * result.torque_mn_mm)
        next_states.append(current)

    torques = tuple(
        NamedJointTorque(dof_name, math.fsum(contributions[dof_name]))
        for dof_name in sorted(required_dofs)
    )
    return HistoricalLegStepResult(
        profile.profile_id,
        profile.version,
        profile.sha256(),
        catalog.catalog_id,
        catalog.version,
        catalog.sha256(),
        projection_sha256,
        body_region,
        tuple(next_states),
        torques,
        tuple(step_results),
    )
