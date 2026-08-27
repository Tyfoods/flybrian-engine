from __future__ import annotations

from dataclasses import replace
from decimal import Decimal

import pytest

from flybrian_engine import (
    FLYBODY_78_ACTUATOR_CATALOG,
    FLYBRIAN_HISTORICAL_90_ACTUATOR_CATALOG,
    FLYBRIAN_HISTORICAL_90_TO_FLYBODY_78,
    ActuatorCrosswalk,
    ActuatorCrosswalkEntry,
    EmbodimentError,
    apply_actuator_crosswalk,
)


def test_catalog_authorities_have_exact_cardinality_and_identity() -> None:
    current = FLYBODY_78_ACTUATOR_CATALOG
    historical = FLYBRIAN_HISTORICAL_90_ACTUATOR_CATALOG

    assert current.catalog_id == "org.flybrian.actuators.flybody"
    assert current.version == "d015e9b"
    assert len(current.actuators) == 78
    assert current.actuators[0].actuator_id == "head_abduct"
    assert current.actuators[10].actuator_id == "antenna_left"
    assert current.actuators[13].actuator_id == "antenna_right"
    assert current.actuators[29].actuator_id == "tarsus2_T1_left"
    assert current.actuators[30].actuator_id == "coxa_abduct_T1_right"
    assert current.actuators[70].actuator_id == "adhere_labrum_left"
    assert current.actuators[-1].actuator_id == "adhere_claw_T3_right"
    assert current.actuators[4].control_min == Decimal("-0.0873")
    assert current.actuators[6].control_min == Decimal("-0.00524")
    assert current.actuators[70].control_unit == "normalized_activation"
    assert current.actuators[0].control_unit == "mujoco_control"
    assert current.sha256() == "8469956cd66465f4191e6597d823c3bd6cb08635ab1e041a94631383a971ab92"

    assert historical.catalog_id == "org.flybrian.actuators.historical-90"
    assert historical.version == "1.0"
    assert len(historical.actuators) == 90
    assert historical.actuators[10].actuator_id == "antenna_extend_left"
    assert historical.actuators[13].actuator_id == "antenna_extend_right"
    assert historical.actuators[30].actuator_id == "tarsus3_T1_left"
    assert historical.actuators[31].actuator_id == "tarsus4_T1_left"
    assert historical.actuators[82].actuator_id == "adhere_labrum_left"
    assert historical.actuators[4].control_min == Decimal("-0.087")
    assert historical.actuators[6].control_min == Decimal("-0.005")
    assert historical.sha256() == (
        "8f24d150b6efdd3e98d5710d901ad375bf48470f7a8a7387802ac167ed192300"
    )


def test_crosswalk_is_total_named_and_surjective() -> None:
    crosswalk = FLYBRIAN_HISTORICAL_90_TO_FLYBODY_78
    mapped = tuple(item for item in crosswalk.entries if item.status == "mapped")
    dropped = tuple(item for item in crosswalk.entries if item.status == "dropped")

    assert len(crosswalk.entries) == 90
    assert len(mapped) == 78
    assert len(dropped) == 12
    assert {item.target_actuator_id for item in mapped} == {
        item.actuator_id for item in FLYBODY_78_ACTUATOR_CATALOG.actuators
    }
    assert {
        item.source_actuator_id for item in dropped
    } == {
        f"tarsus{segment}_{region}_{side}"
        for region in ("T1", "T2", "T3")
        for side in ("left", "right")
        for segment in (3, 4)
    }
    aliases = {
        item.source_actuator_id: item.target_actuator_id
        for item in mapped
        if item.reason_code == "renamed_control"
    }
    assert aliases == {
        "antenna_extend_left": "antenna_left",
        "antenna_extend_right": "antenna_right",
    }
    assert all(item.reason_code == "no_upstream_actuator" for item in dropped)
    assert crosswalk.sha256() == (
        "08f112f8fd8d37d2bbcfc97bdfede601dd0613c7719850e250ee4828b7ac65ee"
    )


def test_crosswalk_application_uses_names_and_preserves_dropped_values() -> None:
    source_values = tuple(str(index) for index in range(90))
    result = apply_actuator_crosswalk(
        FLYBRIAN_HISTORICAL_90_TO_FLYBODY_78,
        FLYBRIAN_HISTORICAL_90_ACTUATOR_CATALOG,
        FLYBODY_78_ACTUATOR_CATALOG,
        source_values,
    )

    by_target = dict(zip(result.target_actuator_ids, result.target_values, strict=True))
    assert by_target["head_abduct"] == Decimal("0")
    assert by_target["antenna_left"] == Decimal("10")
    assert by_target["coxa_abduct_T1_right"] == Decimal("32")
    assert by_target["adhere_labrum_left"] == Decimal("82")
    assert by_target["adhere_claw_T3_right"] == Decimal("89")
    assert tuple((item.source_actuator_id, item.value) for item in result.drops) == (
        ("tarsus3_T1_left", Decimal("30")),
        ("tarsus4_T1_left", Decimal("31")),
        ("tarsus3_T1_right", Decimal("40")),
        ("tarsus4_T1_right", Decimal("41")),
        ("tarsus3_T2_left", Decimal("50")),
        ("tarsus4_T2_left", Decimal("51")),
        ("tarsus3_T2_right", Decimal("60")),
        ("tarsus4_T2_right", Decimal("61")),
        ("tarsus3_T3_left", Decimal("70")),
        ("tarsus4_T3_left", Decimal("71")),
        ("tarsus3_T3_right", Decimal("80")),
        ("tarsus4_T3_right", Decimal("81")),
    )
    assert result == apply_actuator_crosswalk(
        FLYBRIAN_HISTORICAL_90_TO_FLYBODY_78,
        FLYBRIAN_HISTORICAL_90_ACTUATOR_CATALOG,
        FLYBODY_78_ACTUATOR_CATALOG,
        source_values,
    )
    assert result.sha256() == "a9935d1e014f8db697fdcb834bfec01ee3ef6af1878c19c331620f6163b3edfc"


@pytest.mark.parametrize(
    "values",
    [
        tuple("0" for _ in range(89)),
        tuple("0" for _ in range(91)),
        tuple([0.0] + ["0"] * 89),
        tuple(["NaN"] + ["0"] * 89),
        tuple([True] + ["0"] * 89),
    ],
)
def test_crosswalk_application_rejects_bad_vectors(values: tuple[object, ...]) -> None:
    with pytest.raises(EmbodimentError):
        apply_actuator_crosswalk(
            FLYBRIAN_HISTORICAL_90_TO_FLYBODY_78,
            FLYBRIAN_HISTORICAL_90_ACTUATOR_CATALOG,
            FLYBODY_78_ACTUATOR_CATALOG,
            values,
        )


def test_crosswalk_rejects_incomplete_duplicate_and_wrong_authority() -> None:
    good = FLYBRIAN_HISTORICAL_90_TO_FLYBODY_78

    incomplete = replace(good, entries=good.entries[:-1])
    with pytest.raises(EmbodimentError, match="cover every source"):
        apply_actuator_crosswalk(
            incomplete,
            FLYBRIAN_HISTORICAL_90_ACTUATOR_CATALOG,
            FLYBODY_78_ACTUATOR_CATALOG,
            tuple("0" for _ in range(90)),
        )

    duplicate = replace(good.entries[1], source_actuator_id=good.entries[0].source_actuator_id)
    with pytest.raises(EmbodimentError, match="source actuator IDs"):
        replace(good, entries=(good.entries[0], duplicate, *good.entries[2:]))

    with pytest.raises(EmbodimentError, match="source catalog"):
        apply_actuator_crosswalk(
            good,
            replace(FLYBRIAN_HISTORICAL_90_ACTUATOR_CATALOG, version="wrong"),
            FLYBODY_78_ACTUATOR_CATALOG,
            tuple("0" for _ in range(90)),
        )


def test_crosswalk_entry_disposition_is_strict() -> None:
    with pytest.raises(EmbodimentError):
        ActuatorCrosswalkEntry(
            source_actuator_id="source",
            status="mapped",
            target_actuator_id=None,
            reason_code="same_control",
            source="test",
        )
    with pytest.raises(EmbodimentError):
        ActuatorCrosswalkEntry(
            source_actuator_id="source",
            status="dropped",
            target_actuator_id="target",
            reason_code="no_upstream_actuator",
            source="test",
        )
    with pytest.raises(EmbodimentError):
        ActuatorCrosswalk(
            crosswalk_id="test",
            version="1",
            source="test",
            source_catalog_id="source",
            source_catalog_version="1",
            source_catalog_sha256="0" * 64,
            target_catalog_id="target",
            target_catalog_version="1",
            target_catalog_sha256="1" * 64,
            entries=(),
        )
