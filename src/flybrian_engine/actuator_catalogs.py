"""Licensed FlyBody actuator authorities and explicit historical crosswalks."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal

from .embodiment import Actuator, ActuatorCatalog, EmbodimentError

CrosswalkStatus = Literal["mapped", "dropped"]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_UPSTREAM_COMMIT = "d015e9bfe441bd90ae431bac24c55cb74bdbce26"
_UPSTREAM_XML = (
    "https://raw.githubusercontent.com/TuragaLab/flybody/"
    f"{_UPSTREAM_COMMIT}/flybody/fruitfly/assets/fruitfly.xml"
)
_HISTORICAL_SOURCE = (
    "FlyBrian historical actuator-vector profile 1.0; modified from FlyBody "
    f"{_UPSTREAM_COMMIT}"
)


def _text(value: object, path: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise EmbodimentError(f"{path} must be a non-empty trimmed string")
    if len(value) > maximum:
        raise EmbodimentError(f"{path} must contain at most {maximum} characters")
    return value


def _exact_decimal(value: object, path: str) -> Decimal:
    if isinstance(value, (bool, float)):
        raise EmbodimentError(f"{path} must not be bool or binary float")
    if not isinstance(value, (Decimal, int, str)):
        raise EmbodimentError(f"{path} must be an exact decimal")
    try:
        result = value if isinstance(value, Decimal) else Decimal(value)
    except (InvalidOperation, ValueError) as error:
        raise EmbodimentError(f"{path} must be an exact decimal") from error
    if not result.is_finite():
        raise EmbodimentError(f"{path} must be finite")
    return result


def _decimal_text(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == 0:
        return "0"
    return str(normalized).replace("E+", "E")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()


def _require_sha256(value: object, path: str) -> str:
    checked = _text(value, path, maximum=64)
    if not _SHA256.fullmatch(checked):
        raise EmbodimentError(f"{path} must be lowercase SHA-256")
    return checked


@dataclass(frozen=True)
class ActuatorCrosswalkEntry:
    """One named mapping or explained drop in an actuator crosswalk."""

    source_actuator_id: str
    status: CrosswalkStatus
    target_actuator_id: str | None
    reason_code: str
    source: str

    def __post_init__(self) -> None:
        _text(self.source_actuator_id, "crosswalk_entry.source_actuator_id", maximum=255)
        _text(self.reason_code, "crosswalk_entry.reason_code", maximum=255)
        _text(self.source, "crosswalk_entry.source")
        if self.status not in ("mapped", "dropped"):
            raise EmbodimentError("crosswalk_entry.status must be mapped or dropped")
        if self.status == "mapped":
            if self.target_actuator_id is None:
                raise EmbodimentError("mapped crosswalk entry requires target_actuator_id")
            _text(self.target_actuator_id, "crosswalk_entry.target_actuator_id", maximum=255)
            if self.reason_code not in ("same_control", "renamed_control"):
                raise EmbodimentError("mapped crosswalk entry has invalid reason_code")
        else:
            if self.target_actuator_id is not None:
                raise EmbodimentError("dropped crosswalk entry forbids target_actuator_id")
            if self.reason_code != "no_upstream_actuator":
                raise EmbodimentError("dropped crosswalk entry has invalid reason_code")

    def to_dict(self) -> dict[str, object]:
        return {
            "source_actuator_id": self.source_actuator_id,
            "status": self.status,
            "target_actuator_id": self.target_actuator_id,
            "reason_code": self.reason_code,
            "source": self.source,
        }


@dataclass(frozen=True)
class ActuatorCrosswalk:
    """Immutable authority binding two exact catalogs through named entries."""

    crosswalk_id: str
    version: str
    source: str
    source_catalog_id: str
    source_catalog_version: str
    source_catalog_sha256: str
    target_catalog_id: str
    target_catalog_version: str
    target_catalog_sha256: str
    entries: tuple[ActuatorCrosswalkEntry, ...]

    def __post_init__(self) -> None:
        _text(self.crosswalk_id, "crosswalk.crosswalk_id", maximum=255)
        _text(self.version, "crosswalk.version", maximum=255)
        _text(self.source, "crosswalk.source")
        _text(self.source_catalog_id, "crosswalk.source_catalog_id", maximum=255)
        _text(self.source_catalog_version, "crosswalk.source_catalog_version", maximum=255)
        _require_sha256(self.source_catalog_sha256, "crosswalk.source_catalog_sha256")
        _text(self.target_catalog_id, "crosswalk.target_catalog_id", maximum=255)
        _text(self.target_catalog_version, "crosswalk.target_catalog_version", maximum=255)
        _require_sha256(self.target_catalog_sha256, "crosswalk.target_catalog_sha256")
        if not self.entries:
            raise EmbodimentError("crosswalk.entries must not be empty")
        source_ids = tuple(item.source_actuator_id for item in self.entries)
        if len(source_ids) != len(set(source_ids)):
            raise EmbodimentError("crosswalk source actuator IDs must be unique")
        if len(source_ids) != len({item.casefold() for item in source_ids}):
            raise EmbodimentError("crosswalk source actuator IDs must not case-collide")
        target_ids = tuple(
            item.target_actuator_id
            for item in self.entries
            if item.target_actuator_id is not None
        )
        if len(target_ids) != len(set(target_ids)):
            raise EmbodimentError("crosswalk mapped target actuator IDs must be unique")
        if len(target_ids) != len({item.casefold() for item in target_ids}):
            raise EmbodimentError("crosswalk mapped target actuator IDs must not case-collide")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "crosswalk_id": self.crosswalk_id,
            "version": self.version,
            "source": self.source,
            "source_catalog_id": self.source_catalog_id,
            "source_catalog_version": self.source_catalog_version,
            "source_catalog_sha256": self.source_catalog_sha256,
            "target_catalog_id": self.target_catalog_id,
            "target_catalog_version": self.target_catalog_version,
            "target_catalog_sha256": self.target_catalog_sha256,
            "entries": [item.to_dict() for item in self.entries],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class ActuatorCrosswalkDrop:
    """A preserved source value with no actuator in the target catalog."""

    source_actuator_id: str
    value: Decimal
    reason_code: str

    def __post_init__(self) -> None:
        _text(self.source_actuator_id, "crosswalk_drop.source_actuator_id", maximum=255)
        value = _exact_decimal(self.value, "crosswalk_drop.value")
        _text(self.reason_code, "crosswalk_drop.reason_code", maximum=255)
        if self.reason_code != "no_upstream_actuator":
            raise EmbodimentError("crosswalk_drop.reason_code is invalid")
        object.__setattr__(self, "value", value)

    def to_dict(self) -> dict[str, object]:
        return {
            "source_actuator_id": self.source_actuator_id,
            "value": _decimal_text(self.value),
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class ActuatorCrosswalkResult:
    """Canonical named result of applying one exact actuator crosswalk."""

    source_catalog_id: str
    source_catalog_version: str
    source_catalog_sha256: str
    target_catalog_id: str
    target_catalog_version: str
    target_catalog_sha256: str
    crosswalk_id: str
    crosswalk_version: str
    crosswalk_sha256: str
    target_actuator_ids: tuple[str, ...]
    target_values: tuple[Decimal, ...]
    drops: tuple[ActuatorCrosswalkDrop, ...]

    def __post_init__(self) -> None:
        if len(self.target_actuator_ids) != len(self.target_values):
            raise EmbodimentError("crosswalk result target IDs and values must align")
        if len(self.target_actuator_ids) != len(set(self.target_actuator_ids)):
            raise EmbodimentError("crosswalk result target actuator IDs must be unique")
        if len(self.target_actuator_ids) != len(
            {item.casefold() for item in self.target_actuator_ids}
        ):
            raise EmbodimentError("crosswalk result target actuator IDs must not case-collide")
        for target_id in self.target_actuator_ids:
            _text(target_id, "crosswalk_result.target_actuator_id", maximum=255)
        for path, value in (
            ("source_catalog_sha256", self.source_catalog_sha256),
            ("target_catalog_sha256", self.target_catalog_sha256),
            ("crosswalk_sha256", self.crosswalk_sha256),
        ):
            _require_sha256(value, f"crosswalk_result.{path}")
        for path, value in (
            ("source_catalog_id", self.source_catalog_id),
            ("source_catalog_version", self.source_catalog_version),
            ("target_catalog_id", self.target_catalog_id),
            ("target_catalog_version", self.target_catalog_version),
            ("crosswalk_id", self.crosswalk_id),
            ("crosswalk_version", self.crosswalk_version),
        ):
            _text(value, f"crosswalk_result.{path}", maximum=255)
        exact_values = tuple(
            _exact_decimal(target_value, f"crosswalk_result.target_values[{index}]")
            for index, target_value in enumerate(self.target_values)
        )
        object.__setattr__(self, "target_values", exact_values)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "1.0",
            "source_catalog_id": self.source_catalog_id,
            "source_catalog_version": self.source_catalog_version,
            "source_catalog_sha256": self.source_catalog_sha256,
            "target_catalog_id": self.target_catalog_id,
            "target_catalog_version": self.target_catalog_version,
            "target_catalog_sha256": self.target_catalog_sha256,
            "crosswalk_id": self.crosswalk_id,
            "crosswalk_version": self.crosswalk_version,
            "crosswalk_sha256": self.crosswalk_sha256,
            "target_actuator_ids": list(self.target_actuator_ids),
            "target_values": [_decimal_text(value) for value in self.target_values],
            "drops": [item.to_dict() for item in self.drops],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


def _actuator(
    actuator_id: str,
    body_region: str,
    joint: str,
    control_min: str,
    control_max: str,
    *,
    source: str,
    control_unit: str = "mujoco_control",
) -> Actuator:
    return Actuator(
        actuator_id=actuator_id,
        body_region=body_region,
        joint=joint,
        control_min=control_min,
        control_max=control_max,
        control_unit=control_unit,
        source=source,
    )


_BASE_22 = (
    ("head_abduct", "head", "head", "-0.2", "0.2"),
    ("head_twist", "head", "head", "-3", "3"),
    ("head", "head", "head", "-0.5", "0.3"),
    ("rostrum", "head", "mouth", "-1.24", "0.183"),
    ("haustellum_abduct", "mouth", "mouth", "-0.0873", "0.0873"),
    ("haustellum", "mouth", "mouth", "-1.59", "0.7"),
    ("labrum_left", "mouth", "mouth", "-0.00524", "1.05"),
    ("labrum_right", "mouth", "mouth", "-0.00524", "1.05"),
    ("antenna_abduct_left", "antennae", "antenna", "-0.4", "0.8"),
    ("antenna_twist_left", "antennae", "antenna", "-0.1", "0.09"),
    ("antenna_left", "antennae", "antenna", "-0.2", "0.5"),
    ("antenna_abduct_right", "antennae", "antenna", "-0.4", "0.8"),
    ("antenna_twist_right", "antennae", "antenna", "-0.1", "0.09"),
    ("antenna_right", "antennae", "antenna", "-0.2", "0.5"),
    ("wing_yaw_left", "wings", "wing", "-1", "1"),
    ("wing_roll_left", "wings", "wing", "-1", "1"),
    ("wing_pitch_left", "wings", "wing", "-1", "1"),
    ("wing_yaw_right", "wings", "wing", "-1", "1"),
    ("wing_roll_right", "wings", "wing", "-1", "1"),
    ("wing_pitch_right", "wings", "wing", "-1", "1"),
    ("abdomen_abduct", "abdomen", "abdomen", "-0.7", "0.7"),
    ("abdomen", "abdomen", "abdomen", "-1.05", "0.7"),
)

_LEG_RANGES = {
    "T1": (
        ("coxa_abduct", "coxa", "-1", "0.7"),
        ("coxa_twist", "coxa", "-0.8", "0.8"),
        ("coxa", "coxa", "-0.2", "1.7"),
        ("femur_twist", "femur", "-1", "1"),
        ("femur", "femur", "-0.15", "2"),
        ("tibia", "tibia", "-1.35", "1.3"),
        ("tarsus", "tarsus", "-0.7", "1.2"),
        ("tarsus2", "tarsus", "-0.9", "0.9"),
    ),
    "T2": (
        ("coxa_abduct", "coxa", "-0.5", "0.3"),
        ("coxa_twist", "coxa", "-0.75", "0.8"),
        ("coxa", "coxa", "-0.2", "0.9"),
        ("femur_twist", "femur", "-1", "1"),
        ("femur", "femur", "-0.15", "2"),
        ("tibia", "tibia", "-1.35", "1.3"),
        ("tarsus", "tarsus", "-1", "1.8"),
        ("tarsus2", "tarsus", "-0.9", "0.9"),
    ),
    "T3": (
        ("coxa_abduct", "coxa", "-0.9", "0.25"),
        ("coxa_twist", "coxa", "-0.15", "0.8"),
        ("coxa", "coxa", "-0.3", "1.3"),
        ("femur_twist", "femur", "-1", "1"),
        ("femur", "femur", "-0.7", "1.5"),
        ("tibia", "tibia", "-1.35", "1.3"),
        ("tarsus", "tarsus", "-0.8", "1.2"),
        ("tarsus2", "tarsus", "-0.9", "0.9"),
    ),
}

_ADHESION_IDS = (
    "adhere_labrum_left",
    "adhere_labrum_right",
    "adhere_claw_T1_left",
    "adhere_claw_T1_right",
    "adhere_claw_T2_left",
    "adhere_claw_T2_right",
    "adhere_claw_T3_left",
    "adhere_claw_T3_right",
)


def _upstream_actuators() -> tuple[Actuator, ...]:
    actuators = [
        _actuator(*spec, source=f"{_UPSTREAM_XML}#actuator={spec[0]}")
        for spec in _BASE_22
    ]
    for region in ("T1", "T2", "T3"):
        for side in ("left", "right"):
            body_region = f"{region}_{side}"
            for stem, joint, minimum, maximum in _LEG_RANGES[region]:
                actuator_id = f"{stem}_{body_region}"
                actuators.append(
                    _actuator(
                        actuator_id,
                        body_region,
                        joint,
                        minimum,
                        maximum,
                        source=f"{_UPSTREAM_XML}#actuator={actuator_id}",
                    )
                )
    actuators.extend(
        _actuator(
            actuator_id,
            "adhesion",
            "adhesion",
            "0",
            "1",
            source=f"{_UPSTREAM_XML}#actuator={actuator_id}",
            control_unit="normalized_activation",
        )
        for actuator_id in _ADHESION_IDS
    )
    return tuple(actuators)


def _historical_actuators() -> tuple[Actuator, ...]:
    overrides = {
        "haustellum_abduct": ("haustellum_abduct", "-0.087", "0.087"),
        "labrum_left": ("labrum_left", "-0.005", "1.05"),
        "labrum_right": ("labrum_right", "-0.005", "1.05"),
        "antenna_left": ("antenna_extend_left", "-0.2", "0.5"),
        "antenna_right": ("antenna_extend_right", "-0.2", "0.5"),
    }
    actuators: list[Actuator] = []
    for actuator_id, body_region, joint, minimum, maximum in _BASE_22:
        historical_id, historical_min, historical_max = overrides.get(
            actuator_id, (actuator_id, minimum, maximum)
        )
        actuators.append(
            _actuator(
                historical_id,
                body_region,
                joint,
                historical_min,
                historical_max,
                source=_HISTORICAL_SOURCE,
                control_unit="historical_model_control",
            )
        )
    for region in ("T1", "T2", "T3"):
        for side in ("left", "right"):
            body_region = f"{region}_{side}"
            for stem, joint, minimum, maximum in _LEG_RANGES[region]:
                actuators.append(
                    _actuator(
                        f"{stem}_{body_region}",
                        body_region,
                        joint,
                        minimum,
                        maximum,
                        source=_HISTORICAL_SOURCE,
                        control_unit="historical_model_control",
                    )
                )
            for stem in ("tarsus3", "tarsus4"):
                actuators.append(
                    _actuator(
                        f"{stem}_{body_region}",
                        body_region,
                        "tarsus",
                        "-1",
                        "1",
                        source=_HISTORICAL_SOURCE,
                        control_unit="historical_model_control",
                    )
                )
    actuators.extend(
        _actuator(
            actuator_id,
            "adhesion",
            "adhesion",
            "0",
            "1",
            source=_HISTORICAL_SOURCE,
            control_unit="normalized_activation",
        )
        for actuator_id in _ADHESION_IDS
    )
    return tuple(actuators)


FLYBODY_78_ACTUATOR_CATALOG = ActuatorCatalog(
    catalog_id="org.flybrian.actuators.flybody",
    version="d015e9b",
    source=(
        f"FlyBody {_UPSTREAM_COMMIT}, Apache-2.0; compiled actuator names and ctrlrange from "
        f"{_UPSTREAM_XML} (SHA-256 "
        "d14946fd0311025ecca70c8eeb5de80e1fe18700d3072be37ecbb18d33d80fd8)"
    ),
    actuators=_upstream_actuators(),
)

FLYBRIAN_HISTORICAL_90_ACTUATOR_CATALOG = ActuatorCatalog(
    catalog_id="org.flybrian.actuators.historical-90",
    version="1.0",
    source=_HISTORICAL_SOURCE,
    actuators=_historical_actuators(),
)


def _historical_crosswalk_entries() -> tuple[ActuatorCrosswalkEntry, ...]:
    aliases = {
        "antenna_extend_left": "antenna_left",
        "antenna_extend_right": "antenna_right",
    }
    target_ids = {
        item.actuator_id for item in FLYBODY_78_ACTUATOR_CATALOG.actuators
    }
    entries = []
    for actuator in FLYBRIAN_HISTORICAL_90_ACTUATOR_CATALOG.actuators:
        source_id = actuator.actuator_id
        if source_id.startswith(("tarsus3_", "tarsus4_")):
            entries.append(
                ActuatorCrosswalkEntry(
                    source_actuator_id=source_id,
                    status="dropped",
                    target_actuator_id=None,
                    reason_code="no_upstream_actuator",
                    source=_HISTORICAL_SOURCE,
                )
            )
            continue
        target_id = aliases.get(source_id, source_id)
        if target_id not in target_ids:
            raise EmbodimentError(f"historical actuator {source_id!r} has no disposition")
        entries.append(
            ActuatorCrosswalkEntry(
                source_actuator_id=source_id,
                status="mapped",
                target_actuator_id=target_id,
                reason_code="renamed_control" if source_id in aliases else "same_control",
                source=_HISTORICAL_SOURCE,
            )
        )
    return tuple(entries)


FLYBRIAN_HISTORICAL_90_TO_FLYBODY_78 = ActuatorCrosswalk(
    crosswalk_id="org.flybrian.crosswalk.historical-90-to-flybody-78",
    version="1.0",
    source=(
        "FlyBrian named migration profile 1.0; upstream target "
        f"FlyBody {_UPSTREAM_COMMIT}"
    ),
    source_catalog_id=FLYBRIAN_HISTORICAL_90_ACTUATOR_CATALOG.catalog_id,
    source_catalog_version=FLYBRIAN_HISTORICAL_90_ACTUATOR_CATALOG.version,
    source_catalog_sha256=FLYBRIAN_HISTORICAL_90_ACTUATOR_CATALOG.sha256(),
    target_catalog_id=FLYBODY_78_ACTUATOR_CATALOG.catalog_id,
    target_catalog_version=FLYBODY_78_ACTUATOR_CATALOG.version,
    target_catalog_sha256=FLYBODY_78_ACTUATOR_CATALOG.sha256(),
    entries=_historical_crosswalk_entries(),
)


def _assert_catalog_authority(
    catalog: ActuatorCatalog,
    *,
    expected_id: str,
    expected_version: str,
    expected_sha256: str,
    role: str,
) -> None:
    if (
        catalog.catalog_id != expected_id
        or catalog.version != expected_version
        or catalog.sha256() != expected_sha256
    ):
        raise EmbodimentError(f"{role} catalog does not match crosswalk authority")


def apply_actuator_crosswalk(
    crosswalk: ActuatorCrosswalk,
    source_catalog: ActuatorCatalog,
    target_catalog: ActuatorCatalog,
    source_values: Sequence[object],
) -> ActuatorCrosswalkResult:
    """Apply a total named crosswalk to one exact catalog-bound value vector."""

    _assert_catalog_authority(
        source_catalog,
        expected_id=crosswalk.source_catalog_id,
        expected_version=crosswalk.source_catalog_version,
        expected_sha256=crosswalk.source_catalog_sha256,
        role="source",
    )
    _assert_catalog_authority(
        target_catalog,
        expected_id=crosswalk.target_catalog_id,
        expected_version=crosswalk.target_catalog_version,
        expected_sha256=crosswalk.target_catalog_sha256,
        role="target",
    )
    if isinstance(source_values, (str, bytes)):
        raise EmbodimentError("source vector must be an exact-value sequence")
    if len(source_values) != len(source_catalog.actuators):
        raise EmbodimentError("source vector length must match source catalog")

    source_ids = tuple(item.actuator_id for item in source_catalog.actuators)
    entry_by_source = {item.source_actuator_id: item for item in crosswalk.entries}
    if set(entry_by_source) != set(source_ids) or len(entry_by_source) != len(source_ids):
        raise EmbodimentError("crosswalk entries must cover every source actuator exactly once")

    target_ids = tuple(item.actuator_id for item in target_catalog.actuators)
    mapped_target_ids = tuple(
        item.target_actuator_id
        for item in crosswalk.entries
        if item.status == "mapped"
    )
    if set(mapped_target_ids) != set(target_ids) or len(mapped_target_ids) != len(target_ids):
        raise EmbodimentError("crosswalk must cover every target actuator exactly once")

    exact_values = tuple(
        _exact_decimal(value, f"source_values[{index}]")
        for index, value in enumerate(source_values)
    )
    mapped_values: dict[str, Decimal] = {}
    drops = []
    for source_id, value in zip(source_ids, exact_values, strict=True):
        entry = entry_by_source[source_id]
        if entry.status == "dropped":
            drops.append(
                ActuatorCrosswalkDrop(
                    source_actuator_id=source_id,
                    value=value,
                    reason_code=entry.reason_code,
                )
            )
        else:
            if entry.target_actuator_id is None:
                raise EmbodimentError("mapped crosswalk entry is missing target")
            mapped_values[entry.target_actuator_id] = value

    return ActuatorCrosswalkResult(
        source_catalog_id=source_catalog.catalog_id,
        source_catalog_version=source_catalog.version,
        source_catalog_sha256=source_catalog.sha256(),
        target_catalog_id=target_catalog.catalog_id,
        target_catalog_version=target_catalog.version,
        target_catalog_sha256=target_catalog.sha256(),
        crosswalk_id=crosswalk.crosswalk_id,
        crosswalk_version=crosswalk.version,
        crosswalk_sha256=crosswalk.sha256(),
        target_actuator_ids=target_ids,
        target_values=tuple(mapped_values[item] for item in target_ids),
        drops=tuple(drops),
    )
