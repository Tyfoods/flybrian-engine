from __future__ import annotations

from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from typing import Any

import pytest

import flybrian_engine
from flybrian_engine.embodiment import (
    Actuator,
    ActuatorCatalog,
    BodyRegionRule,
    ConfidenceRule,
    DirectProfile,
    DirectTargetRule,
    EmbodimentError,
    Muscle,
    MuscleActuatorRule,
    MuscleCatalog,
    MuscleParameter,
    MuscleProfile,
    MuscleTarget,
    MuscleTargetRule,
    transform_direct,
    transform_muscle_mediated,
)
from flybrian_engine.ingestion import MotorAnatomyRecord, SourceProvenance

MANIFEST_SHA = "a" * 64
DATASET_ID = "manc:v1.2.1-fixture"


def provenance(row: int, lexemes: dict[str, str] | None = None) -> SourceProvenance:
    return SourceProvenance(
        dataset_id=DATASET_ID,
        release="v1.2.1-fixture",
        logical_file="motor-anatomy.csv",
        data_row=row,
        source_lexemes=lexemes or {},
    )


def anatomy(
    neuron_id: int,
    row: int,
    nerve: str,
    target: str | None,
    certainty: int | None,
) -> MotorAnatomyRecord:
    return MotorAnatomyRecord(
        neuron_id=neuron_id,
        neuron_class="motor neuron",
        subclass="hl" if nerve.startswith("Meta") else "fl",
        exit_nerves=tuple(nerve.split()),
        target_label=target,
        systematic_type=None,
        certainty=certainty,
        provenance=provenance(row),
        source_extensions={},
    )


def actuator_catalog() -> ActuatorCatalog:
    return ActuatorCatalog(
        catalog_id="fixture-actuators",
        version="1",
        source="fixture://Flybody-compatible actuator identities",
        actuators=(
            Actuator(
                "tibia_T3_left", "T3_left", "tibia", "-1.35", "1.3", "rad", "fixture://a/1"
            ),
            Actuator(
                "tibia_T1_right", "T1_right", "tibia", "-1.35", "1.3", "rad", "fixture://a/2"
            ),
            Actuator(
                "coxa_T3_left", "T3_left", "coxa", "-0.3", "1.3", "rad", "fixture://a/3"
            ),
            Actuator(
                "coxa_twist_T3_left",
                "T3_left",
                "coxa",
                "-0.15",
                "0.8",
                "rad",
                "fixture://a/4",
            ),
        ),
    )


def confidence_rules() -> tuple[ConfidenceRule, ...]:
    return (ConfidenceRule(3, "0.6"), ConfidenceRule(5, "1"))


def body_rules() -> tuple[BodyRegionRule, ...]:
    return (
        BodyRegionRule("MetaLN_L", "T3_left"),
        BodyRegionRule("MetaLN_R", "T3_right"),
        BodyRegionRule("ProLN_R", "T1_right"),
    )


def direct_profile(**overrides: object) -> DirectProfile:
    values: dict[str, object] = {
        "profile_id": "fixture-direct",
        "version": "1",
        "source": "fixture://explicit corrected direct mapping",
        "compatible_dataset_ids": (DATASET_ID,),
        "body_region_rules": body_rules(),
        "target_rules": (
            DirectTargetRule("Ti extensor", "tibia", "positive"),
            DirectTargetRule("Ti flexor", "tibia", "negative"),
            DirectTargetRule("Coxa rotator", "coxa", "positive"),
        ),
        "confidence_rules": confidence_rules(),
        "missing_certainty_confidence": None,
        "generic_targets": ("front leg", "middle leg", "hind leg"),
        "allow_multiple_body_regions": False,
        "allow_joint_fanout": False,
        "weight_policy": "per_actuator_equal_share",
    }
    values.update(overrides)
    return DirectProfile(**values)  # type: ignore[arg-type]


def muscle_catalog() -> MuscleCatalog:
    return MuscleCatalog(
        catalog_id="fixture-muscles",
        version="1",
        source="fixture://unit-bearing muscle catalog",
        muscles=(
            Muscle(
                "T3_left:tibia_extensor",
                "T3_left",
                "hill",
                "1",
                "fixture://muscle/extensor",
                (MuscleParameter("activation_tau", "20", "ms"),),
            ),
            Muscle(
                "T1_right:tibia_flexor_fast",
                "T1_right",
                "hill",
                "1",
                "fixture://muscle/flexor-fast",
                (MuscleParameter("activation_tau", "10", "ms"),),
            ),
            Muscle(
                "T1_right:tibia_flexor_slow",
                "T1_right",
                "hill",
                "1",
                "fixture://muscle/flexor-slow",
                (MuscleParameter("activation_tau", "30", "ms"),),
            ),
        ),
    )


def muscle_profile(**overrides: object) -> MuscleProfile:
    values: dict[str, object] = {
        "profile_id": "fixture-muscle",
        "version": "1",
        "source": "fixture://explicit muscle mapping",
        "compatible_dataset_ids": (DATASET_ID,),
        "body_region_rules": body_rules(),
        "target_rules": (
            MuscleTargetRule(
                "T3_left",
                "Ti extensor",
                (MuscleTarget("T3_left:tibia_extensor", "1"),),
            ),
            MuscleTargetRule(
                "T1_right",
                "Ti flexor",
                (
                    MuscleTarget("T1_right:tibia_flexor_fast", "1/4"),
                    MuscleTarget("T1_right:tibia_flexor_slow", "3/4"),
                ),
            ),
        ),
        "actuator_rules": (
            MuscleActuatorRule(
                "T3_left:tibia_extensor", "tibia_T3_left", "1", "positive"
            ),
            MuscleActuatorRule(
                "T1_right:tibia_flexor_fast", "tibia_T1_right", "1", "negative"
            ),
            MuscleActuatorRule(
                "T1_right:tibia_flexor_slow", "tibia_T1_right", "1", "negative"
            ),
        ),
        "confidence_rules": confidence_rules(),
        "missing_certainty_confidence": None,
        "generic_targets": ("front leg", "middle leg", "hind leg"),
        "allow_multiple_body_regions": False,
    }
    values.update(overrides)
    return MuscleProfile(**values)  # type: ignore[arg-type]


def test_direct_transform_is_explicit_truthful_and_canonical() -> None:
    assert flybrian_engine.transform_direct is transform_direct
    records = (
        anatomy(10347, 1, "MetaLN_L", "Ti extensor", 5),
        anatomy(10462, 2, "ProLN_R", "Ti flexor", 3),
        anatomy(12009, 3, "MetaLN_L", None, None),
        anatomy(12010, 4, "MetaLN_L", "hind leg", 5),
    )
    result = transform_direct(records, MANIFEST_SHA, direct_profile(), actuator_catalog())

    assert result.executable is True
    assert [
        (link.neuron_id, link.actuator_id, link.weight, link.direction, link.confidence)
        for link in result.links
    ] == [
        (10347, "tibia_T3_left", Fraction(1), "positive", Decimal("1")),
        (10462, "tibia_T1_right", Fraction(1), "negative", Decimal("0.6")),
    ]
    assert [(item.status, item.code, item.neuron_id) for item in result.dispositions] == [
        ("unmapped", "missing_target", 12009),
        ("ambiguous", "ambiguous_target", 12010),
    ]
    assert result.receipt.input_record_count == 4
    assert result.receipt.link_count == 2
    assert result.receipt.disposition_count == 2
    assert result.receipt.graph_sha256 == result.sha256()
    assert result.receipt.profile_sha256 == direct_profile().sha256()
    assert result.receipt.actuator_catalog_sha256 == actuator_catalog().sha256()

    reordered_lexemes = replace(
        records[0],
        provenance=provenance(1, {"z": "last", "a": "first"}),
    )
    reverse_inserted = replace(
        records[0],
        provenance=provenance(1, {"a": "first", "z": "last"}),
    )
    first = transform_direct(
        (reordered_lexemes,), MANIFEST_SHA, direct_profile(), actuator_catalog()
    )
    second = transform_direct(
        (reverse_inserted,), MANIFEST_SHA, direct_profile(), actuator_catalog()
    )
    assert first.canonical_bytes() == second.canonical_bytes()
    assert first.receipt.canonical_bytes() == second.receipt.canonical_bytes()

    changed_profile = replace(direct_profile(), source="fixture://changed-profile-authority")
    changed = transform_direct(
        (records[0],), MANIFEST_SHA, changed_profile, actuator_catalog()
    )
    baseline = transform_direct(
        (records[0],), MANIFEST_SHA, direct_profile(), actuator_catalog()
    )
    assert changed.profile_sha256 != baseline.profile_sha256
    assert changed.sha256() != baseline.sha256()


def test_direct_equal_share_fanout_and_direction_are_declared() -> None:
    records = (
        anatomy(1, 1, "MetaLN_L", "Ti extensor", 5),
        anatomy(2, 2, "MetaLN_L", "Ti extensor", 5),
    )
    result = transform_direct(records, MANIFEST_SHA, direct_profile(), actuator_catalog())
    assert [link.weight for link in result.links] == [Fraction(1, 2), Fraction(1, 2)]

    missing_confidence = anatomy(9, 9, "MetaLN_L", "Ti extensor", None)
    unresolved = transform_direct(
        (missing_confidence,), MANIFEST_SHA, direct_profile(), actuator_catalog()
    )
    assert unresolved.dispositions[0].code == "missing_confidence"
    explicit = transform_direct(
        (missing_confidence,),
        MANIFEST_SHA,
        direct_profile(missing_certainty_confidence="0.5"),
        actuator_catalog(),
    )
    assert explicit.links[0].confidence == Decimal("0.5")

    coxa_record = (anatomy(3, 3, "MetaLN_L", "Coxa rotator", 5),)
    ambiguous = transform_direct(
        coxa_record, MANIFEST_SHA, direct_profile(), actuator_catalog()
    )
    assert ambiguous.links == ()
    assert ambiguous.dispositions[0].code == "ambiguous_actuator"

    fanout = transform_direct(
        coxa_record,
        MANIFEST_SHA,
        direct_profile(allow_joint_fanout=True, weight_policy="none"),
        actuator_catalog(),
    )
    assert [link.actuator_id for link in fanout.links] == [
        "coxa_T3_left",
        "coxa_twist_T3_left",
    ]


def test_direct_rejects_duplicate_identity_multiple_regions_and_incompatibility() -> None:
    record = anatomy(1, 1, "MetaLN_L MetaLN_R", "Ti extensor", 5)
    result = transform_direct((record,), MANIFEST_SHA, direct_profile(), actuator_catalog())
    assert result.links == ()
    assert result.dispositions[0].code == "ambiguous_body_region"

    duplicate = anatomy(1, 2, "MetaLN_L", "Ti extensor", 5)
    with pytest.raises(EmbodimentError, match="duplicate neuron identity 1"):
        transform_direct((record, duplicate), MANIFEST_SHA, direct_profile(), actuator_catalog())

    incompatible = replace(direct_profile(), compatible_dataset_ids=("other:v1",))
    with pytest.raises(EmbodimentError, match="is not compatible"):
        transform_direct((duplicate,), MANIFEST_SHA, incompatible, actuator_catalog())


def test_muscle_transform_has_explicit_fanout_models_and_actuators() -> None:
    records = (
        anatomy(10347, 1, "MetaLN_L", "Ti extensor", 5),
        anatomy(10462, 2, "ProLN_R", "Ti flexor", 3),
        anatomy(12009, 3, "MetaLN_L", None, None),
    )
    result = transform_muscle_mediated(
        records,
        MANIFEST_SHA,
        muscle_profile(),
        muscle_catalog(),
        actuator_catalog(),
    )

    assert result.executable is True
    assert [item.muscle_id for item in result.muscles] == [
        "T3_left:tibia_extensor",
        "T1_right:tibia_flexor_fast",
        "T1_right:tibia_flexor_slow",
    ]
    assert [link.weight for link in result.neuron_to_muscle] == [
        Fraction(1),
        Fraction(1, 4),
        Fraction(3, 4),
    ]
    assert [link.direction for link in result.muscle_to_actuator] == [
        "positive",
        "negative",
        "negative",
    ]
    assert result.dispositions[0].code == "missing_target"
    assert result.receipt.link_count == 6
    assert result.receipt.muscle_count == 3


def test_profiles_reject_float_duplicate_and_incomplete_scientific_authority() -> None:
    binary_float: Any = -1.0
    with pytest.raises(EmbodimentError, match="must not be binary float"):
        Actuator(
            "bad", "T1_left", "tibia", binary_float, "1", "rad", "fixture://bad"
        )

    with pytest.raises(EmbodimentError, match="case-colliding"):
        ActuatorCatalog(
            "bad",
            "1",
            "fixture://bad",
            (
                Actuator(
                    "Tibia", "T1_left", "tibia", "-1", "1", "rad", "fixture://bad/1"
                ),
                Actuator(
                    "tibia", "T1_right", "tibia", "-1", "1", "rad", "fixture://bad/2"
                ),
            ),
        )

    with pytest.raises(EmbodimentError, match=r"actuator\.source"):
        Actuator("bad", "T1_left", "tibia", "-1", "1", "rad", "")

    with pytest.raises(EmbodimentError, match="body-region rules must not be empty"):
        replace(direct_profile(), body_region_rules=())

    with pytest.raises(EmbodimentError, match="target rules must not be empty"):
        replace(muscle_profile(), target_rules=())

    incomplete = replace(
        muscle_profile(),
        actuator_rules=muscle_profile().actuator_rules[:1],
    )
    with pytest.raises(EmbodimentError, match="has no actuator rule"):
        transform_muscle_mediated(
            (anatomy(10462, 2, "ProLN_R", "Ti flexor", 3),),
            MANIFEST_SHA,
            incomplete,
            muscle_catalog(),
            actuator_catalog(),
        )


def test_disposition_only_graph_is_valid_but_not_executable() -> None:
    result = transform_direct(
        (anatomy(12009, 3, "MetaLN_L", None, None),),
        MANIFEST_SHA,
        direct_profile(),
        actuator_catalog(),
    )
    assert result.executable is False
    assert result.links == ()
    assert result.receipt.link_count == 0
    assert result.receipt.disposition_count == 1
