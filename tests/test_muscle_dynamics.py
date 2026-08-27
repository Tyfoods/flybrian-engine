from __future__ import annotations

import hashlib
import json
import math
from dataclasses import replace
from decimal import Decimal

import pytest

from flybrian_engine import (
    FLYBODY_78_ACTUATOR_CATALOG,
    FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG,
    FLYBRIAN_HISTORICAL_HILL_BUG_COMPATIBLE_PROFILE,
    FLYBRIAN_HISTORICAL_HILL_CORRECTED_PROFILE,
    FLYBRIAN_HISTORICAL_MANC_MUSCLE_PROFILE,
    FLYBRIAN_HISTORICAL_MANC_TARGET_BRIDGE,
    FLYBRIAN_HISTORICAL_MANC_TARGET_BRIDGE_SHA256,
    FLYBRIAN_HISTORICAL_MUSCLE_DOF_PROJECTIONS,
    FLYBRIAN_HISTORICAL_MUSCLE_DOF_PROJECTIONS_SHA256,
    FLYBRIAN_HISTORICAL_MUSCLE_DRIVE_PROFILE,
    FLYMIMIC_T1_MUSCLE_CATALOG,
    EmbodimentError,
    MuscleNeuronPool,
    initial_historical_leg_states,
    initial_muscle_activation_state,
    muscle_drives_from_spike_counts,
    step_historical_hill_leg,
    step_historical_hill_muscle,
)


def parameters(muscle_id: str, *, historical: bool = False) -> dict[str, Decimal]:
    catalog = (
        FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG
        if historical
        else FLYMIMIC_T1_MUSCLE_CATALOG
    )
    muscle = next(item for item in catalog.muscles if item.muscle_id == muscle_id)
    return {item.name: Decimal(str(item.value)) for item in muscle.parameters}


def test_official_flymimic_catalog_preserves_exact_source_parameters() -> None:
    catalog = FLYMIMIC_T1_MUSCLE_CATALOG
    assert catalog.catalog_id == "org.flybrian.muscles.flymimic-t1"
    assert catalog.version == "9ea1131"
    assert len(catalog.muscles) == 15
    assert catalog.muscles[0].muscle_id == "LFC_tergopleural_promotor_a"
    assert catalog.muscles[-1].muscle_id == "LFTibia_extensor_93932"

    first = parameters("LFC_tergopleural_promotor_a")
    assert first["max_isometric_force"] == Decimal("9.3186710000294823")
    assert first["optimal_fiber_length"] == Decimal("0.16525853534999999")
    assert first["tendon_slack_length"] == Decimal("0.0086978176499999948")
    assert first["max_contraction_velocity"] == Decimal("42.088141227468149")
    assert first["activation_time_constant"] == Decimal("0.0001")
    assert first["deactivation_time_constant"] == Decimal("0.00040000000000000002")
    assert first["ignore_tendon_compliance"] == Decimal("1")


def test_muscle_authorities_have_fixed_canonical_hashes() -> None:
    assert FLYMIMIC_T1_MUSCLE_CATALOG.sha256() == (
        "5e35c1343bcdc2f1744cc1acbe9e3e780a404d121af4cdb982917cb3bb483a53"
    )
    assert FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG.sha256() == (
        "985d57db75882bc541c42ff6b9426369e8c98666b63d53211e4e428c37c94f51"
    )
    assert FLYBRIAN_HISTORICAL_MUSCLE_DOF_PROJECTIONS_SHA256 == (
        "74cb6e0d5eca850f928dd186ab225e768e64eaa50a798848138388f641d3852a"
    )
    assert FLYBRIAN_HISTORICAL_MANC_TARGET_BRIDGE_SHA256 == (
        "46b914a7b48c414ec8c96258114434533a4a150efba091b39584b712355685d9"
    )
    assert FLYBRIAN_HISTORICAL_MANC_MUSCLE_PROFILE.sha256() == (
        "bf2530b1b1b1fbc9272e9095c48d330c82e9ae2895252a5385dc6712b4ba7ea4"
    )
    assert FLYBRIAN_HISTORICAL_MUSCLE_DRIVE_PROFILE.sha256() == (
        "0ff78dbcd8c18aec64d4f1c838f36f8df0b1512df9200d75deb133cecdc93d3a"
    )
    assert FLYBRIAN_HISTORICAL_HILL_BUG_COMPATIBLE_PROFILE.sha256() == (
        "bec0bbad29de3cd1dea8c7736ae1c831249da4e8b060d6f5e067a40cfd903e30"
    )
    assert FLYBRIAN_HISTORICAL_HILL_CORRECTED_PROFILE.sha256() == (
        "03c982feb92a1acf9058ce840977f912c3e363b193c91e63d7f8fd8daf922600"
    )


def test_historical_catalog_is_six_leg_rounded_and_explicitly_scaled() -> None:
    catalog = FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG
    assert catalog.catalog_id == "org.flybrian.muscles.historical-six-leg-hill"
    assert catalog.version == "1.0"
    assert len(catalog.muscles) == 90
    assert catalog.muscles[0].muscle_id == "T1L/LFC_tergopleural_promotor_a"
    assert catalog.muscles[15].muscle_id == "T1R/LFC_tergopleural_promotor_a"
    assert catalog.muscles[30].muscle_id == "T2L/LFC_tergopleural_promotor_a"
    assert catalog.muscles[60].muscle_id == "T3L/LFC_tergopleural_promotor_a"

    t1 = parameters("T1L/LFC_tergopleural_promotor_a", historical=True)
    t2 = parameters("T2L/LFC_tergopleural_promotor_a", historical=True)
    t3 = parameters("T3L/LFC_tergopleural_promotor_a", historical=True)
    assert t1["max_isometric_force"] == Decimal("9.32")
    assert t2["max_isometric_force"] == Decimal("11.184")
    assert t3["max_isometric_force"] == Decimal("13.048")
    assert t1["activation_time_constant"] == Decimal("0.01")
    assert t1["deactivation_time_constant"] == Decimal("0.04")
    assert t1["moment_arm"] == Decimal("0.53")
    assert t1["reference_angle"] == Decimal("0")

    tibia = parameters("T3R/LFTibia_flex_93434", historical=True)
    assert tibia["max_isometric_force"] == Decimal("58.142")
    assert tibia["moment_arm"] == Decimal("0.051")
    assert tibia["reference_angle"] == Decimal("-0.35")


def test_historical_bridge_and_dof_projections_are_complete_named_authorities() -> None:
    mapped = tuple(item for item in FLYBRIAN_HISTORICAL_MANC_TARGET_BRIDGE if item.muscle_names)
    no_equivalent = tuple(
        item for item in FLYBRIAN_HISTORICAL_MANC_TARGET_BRIDGE if not item.muscle_names
    )
    assert len(FLYBRIAN_HISTORICAL_MANC_TARGET_BRIDGE) == 19
    assert len(mapped) == 12
    assert len(no_equivalent) == 7
    assert {item.target_label for item in no_equivalent} == {
        "Sternotrochanter",
        "Tergotr.",
        "Ta depressor",
        "Ta levator",
        "ltm",
        "ltm1-tibia",
        "ltm2-femur",
    }
    assert len(FLYBRIAN_HISTORICAL_MUSCLE_DOF_PROJECTIONS) == 108
    assert {item.muscle_id for item in FLYBRIAN_HISTORICAL_MUSCLE_DOF_PROJECTIONS} == {
        item.muscle_id for item in FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG.muscles
    }
    assert {item.actuator_id for item in FLYBRIAN_HISTORICAL_MUSCLE_DOF_PROJECTIONS} <= {
        item.actuator_id for item in FLYBODY_78_ACTUATOR_CATALOG.actuators
    }

    profile = FLYBRIAN_HISTORICAL_MANC_MUSCLE_PROFILE
    assert len(profile.body_region_rules) == 14
    assert len(profile.target_rules) == 72
    assert len(profile.actuator_rules) == 108
    assert profile.generic_targets == ("front leg", "middle leg", "hind leg")
    assert profile.missing_certainty_confidence == Decimal("0.5")


def test_historical_drive_conversion_matches_default_and_dual_oracles() -> None:
    pool = (MuscleNeuronPool("LFTibia_flex_93434", (1, 2)),)
    default = muscle_drives_from_spike_counts(
        FLYBRIAN_HISTORICAL_MUSCLE_DRIVE_PROFILE,
        pool,
        {1: 0, 2: 3},
        "0.1",
    )
    assert default.drives[0].value == pytest.approx(0.13296424019782926, abs=1e-15)

    dual_profile = replace(
        FLYBRIAN_HISTORICAL_MUSCLE_DRIVE_PROFILE,
        extensor_rate_normalizer_hz="20",
        flexor_rate_normalizer_hz="40",
    )
    dual = muscle_drives_from_spike_counts(
        dual_profile,
        pool,
        {1: 0, 2: 3},
        "0.1",
    )
    assert dual.drives[0].value == pytest.approx(0.34864513533394575, abs=1e-15)


def test_isolated_historical_tibia_trace_matches_private_numeric_oracle() -> None:
    profile = FLYBRIAN_HISTORICAL_HILL_CORRECTED_PROFILE
    catalog = FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG
    state = initial_muscle_activation_state(
        profile,
        catalog,
        "T1L/LFTibia_flex_93434",
        "0",
    )
    expected = (
        (0.2, 0.7623194699459336),
        (0.36, 0.7620172383241075),
        (0.488, 1.8614016548196297),
        (0.5904, 1.2504165755533201),
        (0.56088, 2.1396389547880936),
        (0.532836, 1.1296793821374258),
        (0.5061942, 1.9313006243048767),
        (0.48088449, 1.0206533597846743),
    )
    for index, (activation, torque) in enumerate(expected):
        result = step_historical_hill_muscle(
            profile,
            catalog,
            state,
            neural_drive="1" if index < 4 else "0",
            joint_angle=str(-0.5 + 0.025 * index),
            joint_velocity="0.3" if index % 2 == 0 else "-0.2",
            dt="0.002",
        )
        assert result.next_state.activation == pytest.approx(activation, abs=1e-12)
        assert result.torque_mn_mm == pytest.approx(torque, rel=1e-12, abs=1e-12)
        state = result.next_state


def test_historical_hill_edges_match_independent_equation_oracle() -> None:
    profile = FLYBRIAN_HISTORICAL_HILL_CORRECTED_PROFILE
    catalog = FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG
    muscle_id = "T1L/LFTibia_flex_93434"
    state = initial_muscle_activation_state(profile, catalog, muscle_id, "0.4")
    values = {key: float(value) for key, value in parameters(muscle_id, historical=True).items()}

    def oracle(angle: float, velocity: float) -> tuple[float, ...]:
        sensitivity = min(values["moment_arm"] / values["optimal_fiber_length"], 1.0)
        length = min(
            max(1 + sensitivity * (angle - values["reference_angle"]), 0.5),
            1.5,
        )
        velocity_norm = min(
            max(sensitivity * velocity, -0.95 * values["max_contraction_velocity"]),
            5 * values["max_contraction_velocity"],
        )
        force_length = math.exp(-((length - 1) / 0.45) ** 2)
        if velocity_norm <= 0:
            force_velocity = (
                values["max_contraction_velocity"] + velocity_norm
            ) / (
                values["max_contraction_velocity"] - velocity_norm / 0.25
            )
        else:
            force_velocity = min(
                (
                    values["max_contraction_velocity"] * 1.8 + velocity_norm
                )
                / (values["max_contraction_velocity"] + velocity_norm),
                1.8,
            )
        active = (
            values["max_isometric_force"] * 0.4 * force_length * force_velocity
        )
        passive_multiplier = (
            0.0
            if length <= 1
            else (math.exp(4 * ((length - 1) / 0.6)) - 1)
            / (math.exp(4) - 1)
        )
        passive = min(
            values["max_isometric_force"] * passive_multiplier,
            values["max_isometric_force"] * 0.5,
        )
        total = active + passive
        torque = total * values["moment_arm"]
        return length, velocity_norm, active, passive, total, torque

    for angle, velocity in (
        (-0.5, -0.2),  # concentric at optimal length
        (-0.5, 0.0),  # isometric
        (-0.2, 0.3),  # eccentric with passive force
        (-100.0, -100000.0),  # lower length and shortening clamps
        (100.0, 100000.0),  # upper length, lengthening, and passive clamps
    ):
        result = step_historical_hill_muscle(
            profile,
            catalog,
            state,
            neural_drive="0.4",
            joint_angle=angle,
            joint_velocity=velocity,
            dt="0",
        )
        actual = (
            result.normalized_length,
            result.normalized_velocity,
            result.active_force_mn,
            result.passive_force_mn,
            result.total_force_mn,
            result.torque_mn_mm,
        )
        assert actual == pytest.approx(oracle(angle, velocity), rel=1e-12, abs=1e-12)


def test_bug_compatible_and_corrected_profiles_separate_multi_dof_state_advance() -> None:
    catalog = FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG
    drives = {"T1L/LFC_tergopleural_promotor_a": "1"}
    joints = {
        "coxa_abduct": ("-0.038", "0"),
        "coxa_twist": ("0", "0"),
        "coxa": ("-0.131", "0"),
        "femur_twist": ("0", "0"),
        "femur": ("0.6", "0"),
        "tibia": ("-0.5", "0"),
    }
    corrected_profile = FLYBRIAN_HISTORICAL_HILL_CORRECTED_PROFILE
    corrected = step_historical_hill_leg(
        corrected_profile,
        catalog,
        FLYBRIAN_HISTORICAL_MUSCLE_DOF_PROJECTIONS,
        "T1_left",
        initial_historical_leg_states(corrected_profile, catalog, "T1_left"),
        drives,
        joints,
        "0.002",
    )
    legacy_profile = FLYBRIAN_HISTORICAL_HILL_BUG_COMPATIBLE_PROFILE
    legacy = step_historical_hill_leg(
        legacy_profile,
        catalog,
        FLYBRIAN_HISTORICAL_MUSCLE_DOF_PROJECTIONS,
        "T1_left",
        initial_historical_leg_states(legacy_profile, catalog, "T1_left"),
        drives,
        joints,
        "0.002",
    )

    corrected_states = {item.muscle_id: item.activation for item in corrected.next_states}
    legacy_states = {item.muscle_id: item.activation for item in legacy.next_states}
    assert corrected_states["T1L/LFC_tergopleural_promotor_a"] == pytest.approx(0.2)
    assert legacy_states["T1L/LFC_tergopleural_promotor_a"] == pytest.approx(0.36)
    assert corrected.sha256() != legacy.sha256()


def test_equation_projection_bridge_and_tau_authorities_are_sensitive() -> None:
    profile = FLYBRIAN_HISTORICAL_HILL_CORRECTED_PROFILE
    catalog = FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG
    state = initial_muscle_activation_state(
        profile, catalog, "T1L/LFTibia_flex_93434", "0"
    )
    baseline = step_historical_hill_muscle(
        profile,
        catalog,
        state,
        neural_drive="1",
        joint_angle="-0.45",
        joint_velocity="0.3",
        dt="0.002",
    )
    changed_equation = replace(profile, force_length_width="0.46")
    assert changed_equation.sha256() != profile.sha256()
    changed_state = initial_muscle_activation_state(
        changed_equation, catalog, "T1L/LFTibia_flex_93434", "0"
    )
    changed_result = step_historical_hill_muscle(
        changed_equation,
        catalog,
        changed_state,
        neural_drive="1",
        joint_angle="-0.45",
        joint_velocity="0.3",
        dt="0.002",
    )
    assert changed_result.torque_mn_mm != baseline.torque_mn_mm

    changed_projection = replace(
        FLYBRIAN_HISTORICAL_MUSCLE_DOF_PROJECTIONS[0], direction="negative"
    )
    projections = (changed_projection, *FLYBRIAN_HISTORICAL_MUSCLE_DOF_PROJECTIONS[1:])
    with pytest.raises(EmbodimentError, match="projections do not match"):
        step_historical_hill_leg(
            profile,
            catalog,
            projections,
            "T1_left",
            initial_historical_leg_states(profile, catalog, "T1_left"),
            {},
            {
                "coxa_abduct": ("-0.038", "0"),
                "coxa_twist": ("0", "0"),
                "coxa": ("-0.131", "0"),
                "femur_twist": ("0", "0"),
                "femur": ("0.6", "0"),
                "tibia": ("-0.5", "0"),
            },
            "0.002",
        )

    changed_bridge = (
        replace(
            FLYBRIAN_HISTORICAL_MANC_TARGET_BRIDGE[0],
            confidence_class="medium",
        ),
        *FLYBRIAN_HISTORICAL_MANC_TARGET_BRIDGE[1:],
    )
    changed_bridge_bytes = json.dumps(
        [item.to_dict() for item in changed_bridge],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    assert hashlib.sha256(changed_bridge_bytes).hexdigest() != (
        FLYBRIAN_HISTORICAL_MANC_TARGET_BRIDGE_SHA256
    )

    muscle = catalog.muscles[0]
    parameters = tuple(
        replace(item, value="0.02")
        if item.name == "activation_time_constant"
        else item
        for item in muscle.parameters
    )
    changed_catalog = replace(
        catalog,
        muscles=(replace(muscle, parameters=parameters), *catalog.muscles[1:]),
    )
    with pytest.raises(EmbodimentError, match="catalog does not match"):
        initial_muscle_activation_state(
            profile, changed_catalog, muscle.muscle_id, "0"
        )


def test_muscle_dynamics_rejects_invalid_domains_and_identity() -> None:
    profile = FLYBRIAN_HISTORICAL_HILL_CORRECTED_PROFILE
    catalog = FLYBRIAN_HISTORICAL_6LEG_MUSCLE_CATALOG
    state = initial_muscle_activation_state(
        profile, catalog, "T1L/LFTibia_flex_93434", "0"
    )
    with pytest.raises(EmbodimentError):
        step_historical_hill_muscle(
            profile,
            catalog,
            state,
            neural_drive=float("nan"),
            joint_angle="0",
            joint_velocity="0",
            dt="0.001",
        )
    with pytest.raises(EmbodimentError, match="profile identity"):
        step_historical_hill_muscle(
            replace(profile, version="changed"),
            catalog,
            state,
            neural_drive="0",
            joint_angle="0",
            joint_velocity="0",
            dt="0.001",
        )
    with pytest.raises(EmbodimentError):
        muscle_drives_from_spike_counts(
            FLYBRIAN_HISTORICAL_MUSCLE_DRIVE_PROFILE,
            (MuscleNeuronPool("m", (1,)),),
            {1: 0},
            "0.1",
        )
    with pytest.raises(EmbodimentError):
        muscle_drives_from_spike_counts(
            FLYBRIAN_HISTORICAL_MUSCLE_DRIVE_PROFILE,
            (MuscleNeuronPool("LFTibia_flex_93434", (1,)),),
            {1: -1},
            "0.1",
        )
    with pytest.raises(EmbodimentError):
        replace(
            FLYBRIAN_HISTORICAL_MUSCLE_DRIVE_PROFILE,
            extensor_rate_normalizer_hz="20",
            flexor_rate_normalizer_hz=None,
        )
