"""Reviewed, non-inferencing projections over historical estate inventories."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, NoReturn, TypeGuard, cast

from .historical_envelopes import HistoricalExperimentEnvelope, ReproducibilityClass
from .historical_estate import (
    EstateCandidateRole,
    HistoricalEstateFile,
    HistoricalEstateInventory,
    classify_historical_estate_file,
)

HISTORICAL_ESTATE_PROJECTION_PROFILE_ID = (
    "org.flybrian.historical-estate-projection"
)
HISTORICAL_ESTATE_PROJECTION_PROFILE_VERSION = "1.0"
DEFAULT_MAX_HISTORICAL_PROJECTION_JSON_BYTES = 64 * 1024 * 1024

ProjectionVisibility = Literal["public", "private", "team"]
ProjectedArtifactAvailability = Literal["available", "unavailable", "failed"]
ProjectedArtifactKind = Literal[
    "result",
    "metrics",
    "motor_commands",
    "state",
    "video",
    "image",
    "narrative",
    "log",
    "archive",
    "other",
]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NAMESPACE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]*(?:[.:][A-Za-z0-9][A-Za-z0-9_.:-]*)+$"
)
_ARTIFACT_ROLE_COMPATIBILITY: dict[ProjectedArtifactKind, frozenset[str]] = {
    "result": frozenset({"result"}),
    "metrics": frozenset({"result", "array"}),
    "motor_commands": frozenset({"array", "result"}),
    "state": frozenset({"array", "result"}),
    "video": frozenset({"video"}),
    "image": frozenset({"image"}),
    "narrative": frozenset({"narrative"}),
    "log": frozenset({"narrative"}),
    "archive": frozenset({"archive"}),
    "other": frozenset(
        {"source", "result", "array", "video", "image", "narrative", "archive", "unknown"}
    ),
}


def _is_estate_candidate_role(value: object) -> TypeGuard[EstateCandidateRole]:
    return value in (
        "source",
        "result",
        "array",
        "video",
        "image",
        "narrative",
        "archive",
        "unknown",
    )


def _is_reproducibility_class(value: object) -> TypeGuard[ReproducibilityClass]:
    return value in (
        "PROVENANCE_ONLY",
        "RUNNABLE_CONNECTOME",
        "RUNNABLE_EMBODIED",
    )


def _is_projection_visibility(value: object) -> TypeGuard[ProjectionVisibility]:
    return value == "public" or value == "private" or value == "team"


def _is_projected_artifact_availability(
    value: object,
) -> TypeGuard[ProjectedArtifactAvailability]:
    return value == "available" or value == "unavailable" or value == "failed"


class HistoricalProjectionError(ValueError):
    """A reviewed projection is invalid or differs from its authorities."""


def _text(value: object, path: str, *, maximum: int = 4096) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise HistoricalProjectionError(f"{path} must be a non-empty trimmed string")
    if len(value) > maximum:
        raise HistoricalProjectionError(
            f"{path} must contain at most {maximum} characters"
        )
    if unicodedata.normalize("NFC", value) != value:
        raise HistoricalProjectionError(f"{path} must use NFC Unicode normalization")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise HistoricalProjectionError(f"{path} must not contain control characters")
    return value


def _namespaced(value: object, path: str) -> str:
    checked = _text(value, path, maximum=255)
    if _NAMESPACE.fullmatch(checked) is None:
        raise HistoricalProjectionError(f"{path} must be namespaced")
    return checked


def _sha256(value: object, path: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise HistoricalProjectionError(f"{path} must be lowercase SHA-256")
    return value


def _non_negative_integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HistoricalProjectionError(f"{path} must be a non-negative integer")
    return value


def _positive_integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalProjectionError(f"{path} must be a positive integer")
    return value


def _safe_logical_path(value: object, path: str) -> str:
    checked = _text(value, path, maximum=2048)
    try:
        classify_historical_estate_file(checked)
    except ValueError as error:
        raise HistoricalProjectionError(f"{path} must be a safe logical path") from error
    return checked


def _mapping(
    value: object,
    path: str,
    fields: frozenset[str],
) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise HistoricalProjectionError(f"{path} must be an object")
    actual = frozenset(value)
    if actual != fields:
        missing = ", ".join(sorted(fields - actual)) or "none"
        unknown = ", ".join(sorted(actual - fields)) or "none"
        raise HistoricalProjectionError(
            f"{path} fields differ (missing: {missing}; unknown: {unknown})"
        )
    return cast(Mapping[str, object], value)


def _array(value: object, path: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise HistoricalProjectionError(f"{path} must be an array")
    return cast(Sequence[object], value)


def _optional_text(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _text(value, path)


def _optional_sha256(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _sha256(value, path)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True)
class HistoricalInventoryReference:
    root_id: str
    inventory_sha256: str

    def __post_init__(self) -> None:
        _namespaced(self.root_id, "inventory_reference.root_id")
        _sha256(
            self.inventory_sha256,
            "inventory_reference.inventory_sha256",
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "root_id": self.root_id,
            "inventory_sha256": self.inventory_sha256,
        }

    @classmethod
    def from_dict(cls, value: object) -> HistoricalInventoryReference:
        record = _mapping(
            value,
            "inventory_reference",
            frozenset({"root_id", "inventory_sha256"}),
        )
        return cls(
            root_id=_namespaced(record["root_id"], "inventory_reference.root_id"),
            inventory_sha256=_sha256(
                record["inventory_sha256"],
                "inventory_reference.inventory_sha256",
            ),
        )


@dataclass(frozen=True)
class HistoricalEvidenceReference:
    root_id: str
    inventory_sha256: str
    logical_path: str
    byte_length: int
    file_sha256: str
    candidate_role: EstateCandidateRole

    def __post_init__(self) -> None:
        _namespaced(self.root_id, "evidence.root_id")
        _sha256(self.inventory_sha256, "evidence.inventory_sha256")
        _safe_logical_path(self.logical_path, "evidence.logical_path")
        _non_negative_integer(self.byte_length, "evidence.byte_length")
        _sha256(self.file_sha256, "evidence.file_sha256")
        if self.candidate_role not in {
            "source",
            "result",
            "array",
            "video",
            "image",
            "narrative",
            "archive",
            "unknown",
        }:
            raise HistoricalProjectionError("evidence.candidate_role is unsupported")

    def to_dict(self) -> dict[str, object]:
        return {
            "root_id": self.root_id,
            "inventory_sha256": self.inventory_sha256,
            "logical_path": self.logical_path,
            "byte_length": self.byte_length,
            "file_sha256": self.file_sha256,
            "candidate_role": self.candidate_role,
        }

    @classmethod
    def from_dict(cls, value: object) -> HistoricalEvidenceReference:
        record = _mapping(
            value,
            "evidence",
            frozenset(
                {
                    "root_id",
                    "inventory_sha256",
                    "logical_path",
                    "byte_length",
                    "file_sha256",
                    "candidate_role",
                }
            ),
        )
        role = record["candidate_role"]
        if not _is_estate_candidate_role(role):
            raise HistoricalProjectionError("evidence.candidate_role is unsupported")
        return cls(
            root_id=_namespaced(record["root_id"], "evidence.root_id"),
            inventory_sha256=_sha256(
                record["inventory_sha256"], "evidence.inventory_sha256"
            ),
            logical_path=_safe_logical_path(
                record["logical_path"], "evidence.logical_path"
            ),
            byte_length=_non_negative_integer(
                record["byte_length"], "evidence.byte_length"
            ),
            file_sha256=_sha256(record["file_sha256"], "evidence.file_sha256"),
            candidate_role=role,
        )


@dataclass(frozen=True)
class HistoricalEnvelopeReference:
    envelope_id: str
    version: str
    envelope_sha256: str
    reproducibility_class: ReproducibilityClass
    fes_sha256: str | None
    missing_requirements: tuple[str, ...]

    def __post_init__(self) -> None:
        _namespaced(self.envelope_id, "envelope_reference.envelope_id")
        _text(self.version, "envelope_reference.version", maximum=255)
        _sha256(self.envelope_sha256, "envelope_reference.envelope_sha256")
        if self.reproducibility_class not in {
            "PROVENANCE_ONLY",
            "RUNNABLE_CONNECTOME",
            "RUNNABLE_EMBODIED",
        }:
            raise HistoricalProjectionError(
                "envelope_reference.reproducibility_class is unsupported"
            )
        _optional_sha256(self.fes_sha256, "envelope_reference.fes_sha256")
        if (
            tuple(sorted(self.missing_requirements)) != self.missing_requirements
            or len(set(self.missing_requirements)) != len(self.missing_requirements)
        ):
            raise HistoricalProjectionError(
                "envelope_reference.missing_requirements must be unique and sorted"
            )
        for requirement in self.missing_requirements:
            _text(
                requirement,
                "envelope_reference.missing_requirements item",
                maximum=255,
            )
            if requirement != requirement.upper():
                raise HistoricalProjectionError(
                    "envelope_reference.missing_requirements must be uppercase codes"
                )
        if self.reproducibility_class != "PROVENANCE_ONLY" and self.missing_requirements:
            raise HistoricalProjectionError(
                "runnable envelope reference must not contain missing requirements"
            )
        if self.reproducibility_class != "PROVENANCE_ONLY" and self.fes_sha256 is None:
            raise HistoricalProjectionError(
                "runnable envelope reference requires an exact FES SHA-256"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "envelope_id": self.envelope_id,
            "version": self.version,
            "envelope_sha256": self.envelope_sha256,
            "reproducibility_class": self.reproducibility_class,
            "fes_sha256": self.fes_sha256,
            "missing_requirements": list(self.missing_requirements),
        }

    @classmethod
    def from_dict(cls, value: object) -> HistoricalEnvelopeReference:
        record = _mapping(
            value,
            "envelope_reference",
            frozenset(
                {
                    "envelope_id",
                    "version",
                    "envelope_sha256",
                    "reproducibility_class",
                    "fes_sha256",
                    "missing_requirements",
                }
            ),
        )
        reproducibility = record["reproducibility_class"]
        if not _is_reproducibility_class(reproducibility):
            raise HistoricalProjectionError(
                "envelope_reference.reproducibility_class is unsupported"
            )
        requirements = tuple(
            _text(item, "envelope_reference.missing_requirements item", maximum=255)
            for item in _array(
                record["missing_requirements"],
                "envelope_reference.missing_requirements",
            )
        )
        return cls(
            envelope_id=_namespaced(
                record["envelope_id"], "envelope_reference.envelope_id"
            ),
            version=_text(record["version"], "envelope_reference.version", maximum=255),
            envelope_sha256=_sha256(
                record["envelope_sha256"], "envelope_reference.envelope_sha256"
            ),
            reproducibility_class=reproducibility,
            fes_sha256=_optional_sha256(
                record["fes_sha256"], "envelope_reference.fes_sha256"
            ),
            missing_requirements=requirements,
        )


@dataclass(frozen=True)
class HistoricalContributor:
    contributor_id: str
    display_name: str
    attribution: str

    def __post_init__(self) -> None:
        _namespaced(self.contributor_id, "contributor.contributor_id")
        _text(self.display_name, "contributor.display_name", maximum=255)
        _text(self.attribution, "contributor.attribution")

    def to_dict(self) -> dict[str, str]:
        return {
            "contributor_id": self.contributor_id,
            "display_name": self.display_name,
            "attribution": self.attribution,
        }

    @classmethod
    def from_dict(cls, value: object) -> HistoricalContributor:
        record = _mapping(
            value,
            "contributor",
            frozenset({"contributor_id", "display_name", "attribution"}),
        )
        return cls(
            contributor_id=_namespaced(
                record["contributor_id"], "contributor.contributor_id"
            ),
            display_name=_text(
                record["display_name"], "contributor.display_name", maximum=255
            ),
            attribution=_text(record["attribution"], "contributor.attribution"),
        )


@dataclass(frozen=True)
class HistoricalVisibilityPolicy:
    visibility: ProjectionVisibility
    scope_id: str | None

    def __post_init__(self) -> None:
        if self.visibility not in {"public", "private", "team"}:
            raise HistoricalProjectionError("visibility.visibility is unsupported")
        if self.visibility == "team":
            _namespaced(self.scope_id, "visibility.scope_id")
        elif self.scope_id is not None:
            raise HistoricalProjectionError(
                "visibility.scope_id is permitted only for team visibility"
            )

    def to_dict(self) -> dict[str, str | None]:
        return {"visibility": self.visibility, "scope_id": self.scope_id}

    @classmethod
    def from_dict(cls, value: object) -> HistoricalVisibilityPolicy:
        record = _mapping(
            value,
            "visibility",
            frozenset({"visibility", "scope_id"}),
        )
        visibility = record["visibility"]
        if not _is_projection_visibility(visibility):
            raise HistoricalProjectionError("visibility.visibility is unsupported")
        scope = record["scope_id"]
        if scope is not None and not isinstance(scope, str):
            raise HistoricalProjectionError("visibility.scope_id must be a string or null")
        return cls(visibility, scope)


@dataclass(frozen=True)
class HistoricalProjectedArtifact:
    artifact_id: str
    kind: ProjectedArtifactKind
    availability: ProjectedArtifactAvailability
    evidence: HistoricalEvidenceReference | None
    reason: str | None

    def __post_init__(self) -> None:
        _namespaced(self.artifact_id, "projected_artifact.artifact_id")
        if self.kind not in _ARTIFACT_ROLE_COMPATIBILITY:
            raise HistoricalProjectionError("projected_artifact.kind is unsupported")
        if self.availability not in {"available", "unavailable", "failed"}:
            raise HistoricalProjectionError(
                "projected_artifact.availability is unsupported"
            )
        if self.availability == "available":
            if self.evidence is None or self.reason is not None:
                raise HistoricalProjectionError(
                    "available projected artifact requires evidence and forbids reason"
                )
        elif self.evidence is not None or self.reason is None:
            raise HistoricalProjectionError(
                f"{self.availability} projected artifact requires reason and forbids evidence"
            )
        if self.reason is not None:
            _text(self.reason, "projected_artifact.reason")

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "availability": self.availability,
            "evidence": None if self.evidence is None else self.evidence.to_dict(),
            "reason": self.reason,
        }

    @classmethod
    def from_dict(cls, value: object) -> HistoricalProjectedArtifact:
        record = _mapping(
            value,
            "projected_artifact",
            frozenset({"artifact_id", "kind", "availability", "evidence", "reason"}),
        )
        kind = record["kind"]
        availability = record["availability"]
        if kind not in _ARTIFACT_ROLE_COMPATIBILITY:
            raise HistoricalProjectionError("projected_artifact.kind is unsupported")
        if not _is_projected_artifact_availability(availability):
            raise HistoricalProjectionError(
                "projected_artifact.availability is unsupported"
            )
        raw_evidence = record["evidence"]
        raw_reason = record["reason"]
        return cls(
            artifact_id=_namespaced(
                record["artifact_id"], "projected_artifact.artifact_id"
            ),
            kind=kind,
            availability=availability,
            evidence=(
                None
                if raw_evidence is None
                else HistoricalEvidenceReference.from_dict(raw_evidence)
            ),
            reason=_optional_text(raw_reason, "projected_artifact.reason"),
        )


@dataclass(frozen=True)
class HistoricalProjectedRun:
    design_id: str
    design_version: int
    run_id: str
    contributor_id: str
    visibility: HistoricalVisibilityPolicy
    source: HistoricalEvidenceReference
    source_repository_path: str
    envelope: HistoricalEnvelopeReference
    artifacts: tuple[HistoricalProjectedArtifact, ...]

    def __post_init__(self) -> None:
        _namespaced(self.design_id, "projected_run.design_id")
        _positive_integer(self.design_version, "projected_run.design_version")
        _namespaced(self.run_id, "projected_run.run_id")
        _namespaced(self.contributor_id, "projected_run.contributor_id")
        _safe_logical_path(
            self.source_repository_path,
            "projected_run.source_repository_path",
        )
        artifact_ids = tuple(item.artifact_id for item in self.artifacts)
        if len(artifact_ids) != len(set(artifact_ids)):
            raise HistoricalProjectionError(
                "projected_run.artifacts must have unique artifact IDs"
            )

    @property
    def identity(self) -> tuple[str, int, str]:
        return (self.design_id, self.design_version, self.run_id)

    def to_dict(self) -> dict[str, object]:
        return {
            "design_id": self.design_id,
            "design_version": self.design_version,
            "run_id": self.run_id,
            "contributor_id": self.contributor_id,
            "visibility": self.visibility.to_dict(),
            "source": self.source.to_dict(),
            "source_repository_path": self.source_repository_path,
            "envelope": self.envelope.to_dict(),
            "artifacts": [item.to_dict() for item in self.artifacts],
        }

    @classmethod
    def from_dict(cls, value: object) -> HistoricalProjectedRun:
        record = _mapping(
            value,
            "projected_run",
            frozenset(
                {
                    "design_id",
                    "design_version",
                    "run_id",
                    "contributor_id",
                    "visibility",
                    "source",
                    "source_repository_path",
                    "envelope",
                    "artifacts",
                }
            ),
        )
        return cls(
            design_id=_namespaced(record["design_id"], "projected_run.design_id"),
            design_version=_positive_integer(
                record["design_version"], "projected_run.design_version"
            ),
            run_id=_namespaced(record["run_id"], "projected_run.run_id"),
            contributor_id=_namespaced(
                record["contributor_id"], "projected_run.contributor_id"
            ),
            visibility=HistoricalVisibilityPolicy.from_dict(record["visibility"]),
            source=HistoricalEvidenceReference.from_dict(record["source"]),
            source_repository_path=_safe_logical_path(
                record["source_repository_path"],
                "projected_run.source_repository_path",
            ),
            envelope=HistoricalEnvelopeReference.from_dict(record["envelope"]),
            artifacts=tuple(
                HistoricalProjectedArtifact.from_dict(item)
                for item in _array(record["artifacts"], "projected_run.artifacts")
            ),
        )


@dataclass(frozen=True)
class HistoricalProjectionReview:
    review_authority_id: str
    review_revision: str
    evidence: str

    def __post_init__(self) -> None:
        _namespaced(self.review_authority_id, "projection_review.review_authority_id")
        _text(self.review_revision, "projection_review.review_revision", maximum=255)
        _text(self.evidence, "projection_review.evidence")

    def to_dict(self) -> dict[str, str]:
        return {
            "review_authority_id": self.review_authority_id,
            "review_revision": self.review_revision,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, value: object) -> HistoricalProjectionReview:
        record = _mapping(
            value,
            "projection_review",
            frozenset({"review_authority_id", "review_revision", "evidence"}),
        )
        return cls(
            review_authority_id=_namespaced(
                record["review_authority_id"],
                "projection_review.review_authority_id",
            ),
            review_revision=_text(
                record["review_revision"],
                "projection_review.review_revision",
                maximum=255,
            ),
            evidence=_text(record["evidence"], "projection_review.evidence"),
        )


@dataclass(frozen=True)
class HistoricalEstateProjection:
    projection_id: str
    version: str
    review: HistoricalProjectionReview
    inventories: tuple[HistoricalInventoryReference, ...]
    contributors: tuple[HistoricalContributor, ...]
    runs: tuple[HistoricalProjectedRun, ...]
    profile_id: str = HISTORICAL_ESTATE_PROJECTION_PROFILE_ID
    profile_version: str = HISTORICAL_ESTATE_PROJECTION_PROFILE_VERSION
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.schema_version != "1.0":
            raise HistoricalProjectionError("projection.schema_version is unsupported")
        if self.profile_id != HISTORICAL_ESTATE_PROJECTION_PROFILE_ID:
            raise HistoricalProjectionError("projection.profile_id is unsupported")
        if self.profile_version != HISTORICAL_ESTATE_PROJECTION_PROFILE_VERSION:
            raise HistoricalProjectionError("projection.profile_version is unsupported")
        _namespaced(self.projection_id, "projection.projection_id")
        _text(self.version, "projection.version", maximum=255)
        inventory_ids = tuple(item.root_id for item in self.inventories)
        if inventory_ids != tuple(sorted(inventory_ids)) or len(inventory_ids) != len(
            set(inventory_ids)
        ):
            raise HistoricalProjectionError(
                "projection.inventories must be unique and sorted by root ID"
            )
        if not self.inventories:
            raise HistoricalProjectionError("projection.inventories must not be empty")
        contributor_ids = tuple(item.contributor_id for item in self.contributors)
        if contributor_ids != tuple(sorted(contributor_ids)) or len(contributor_ids) != len(
            set(contributor_ids)
        ):
            raise HistoricalProjectionError(
                "projection.contributors must be unique and sorted"
            )
        contributor_set = set(contributor_ids)
        identities = tuple(item.identity for item in self.runs)
        if identities != tuple(sorted(identities)) or len(identities) != len(set(identities)):
            raise HistoricalProjectionError("projection.runs must be unique and sorted")
        for run in self.runs:
            if run.contributor_id not in contributor_set:
                raise HistoricalProjectionError(
                    f"projected run references unknown contributor {run.contributor_id!r}"
                )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "projection_id": self.projection_id,
            "version": self.version,
            "review": self.review.to_dict(),
            "inventories": [item.to_dict() for item in self.inventories],
            "contributors": [item.to_dict() for item in self.contributors],
            "runs": [item.to_dict() for item in self.runs],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def import_sha256(self) -> str:
        return hashlib.sha256(
            _canonical_bytes(
                {
                    "inventory_sha256": [
                        item.inventory_sha256 for item in self.inventories
                    ],
                    "projection_sha256": self.sha256(),
                }
            )
        ).hexdigest()

    @classmethod
    def from_dict(cls, value: object) -> HistoricalEstateProjection:
        record = _mapping(
            value,
            "projection",
            frozenset(
                {
                    "schema_version",
                    "profile_id",
                    "profile_version",
                    "projection_id",
                    "version",
                    "review",
                    "inventories",
                    "contributors",
                    "runs",
                }
            ),
        )
        return cls(
            schema_version=_text(
                record["schema_version"], "projection.schema_version", maximum=32
            ),
            profile_id=_namespaced(record["profile_id"], "projection.profile_id"),
            profile_version=_text(
                record["profile_version"], "projection.profile_version", maximum=32
            ),
            projection_id=_namespaced(
                record["projection_id"], "projection.projection_id"
            ),
            version=_text(record["version"], "projection.version", maximum=255),
            review=HistoricalProjectionReview.from_dict(record["review"]),
            inventories=tuple(
                HistoricalInventoryReference.from_dict(item)
                for item in _array(record["inventories"], "projection.inventories")
            ),
            contributors=tuple(
                HistoricalContributor.from_dict(item)
                for item in _array(record["contributors"], "projection.contributors")
            ),
            runs=tuple(
                HistoricalProjectedRun.from_dict(item)
                for item in _array(record["runs"], "projection.runs")
            ),
        )


def _expected_envelope_reference(
    envelope: HistoricalExperimentEnvelope,
) -> HistoricalEnvelopeReference:
    return HistoricalEnvelopeReference(
        envelope_id=envelope.envelope_id,
        version=envelope.version,
        envelope_sha256=envelope.sha256(),
        reproducibility_class=envelope.reproducibility_class,
        fes_sha256=envelope.expected_fes_sha256,
        missing_requirements=envelope.missing_requirements,
    )


def _validate_evidence(
    evidence: HistoricalEvidenceReference,
    *,
    inventories: Mapping[tuple[str, str], HistoricalEstateInventory],
    files: Mapping[tuple[str, str, str], HistoricalEstateFile],
) -> tuple[HistoricalEstateInventory, HistoricalEstateFile]:
    inventory_key = (evidence.root_id, evidence.inventory_sha256)
    inventory = inventories.get(inventory_key)
    if inventory is None:
        raise HistoricalProjectionError("evidence references an undeclared inventory")
    item = files.get((*inventory_key, evidence.logical_path))
    if item is None:
        raise HistoricalProjectionError("evidence references a missing inventory file")
    expected = (
        item.byte_length,
        item.sha256,
        item.candidate_role,
    )
    actual = (
        evidence.byte_length,
        evidence.file_sha256,
        evidence.candidate_role,
    )
    if actual != expected:
        raise HistoricalProjectionError("evidence differs from the exact inventory file")
    return inventory, item


def _validate_envelope_source(
    run: HistoricalProjectedRun,
    inventory: HistoricalEstateInventory,
    envelope: HistoricalExperimentEnvelope,
) -> None:
    source = envelope.source
    if (
        source.revision != inventory.root.revision
        or source.logical_path != run.source_repository_path
        or source.byte_length != run.source.byte_length
        or source.sha256 != run.source.file_sha256
    ):
        raise HistoricalProjectionError(
            "projected run source authority differs from its historical envelope"
        )


def validate_historical_estate_projection(
    projection: HistoricalEstateProjection,
    *,
    inventories: Sequence[HistoricalEstateInventory],
    envelopes: Sequence[HistoricalExperimentEnvelope],
) -> HistoricalEstateProjection:
    """Validate one reviewed projection against exact inventory and envelope authorities."""

    expected_inventory_refs = tuple(
        HistoricalInventoryReference(item.root.root_id, item.sha256())
        for item in inventories
    )
    if expected_inventory_refs != projection.inventories:
        raise HistoricalProjectionError(
            "supplied inventory tuple differs from projection authority"
        )
    inventory_lookup: dict[tuple[str, str], HistoricalEstateInventory] = {}
    file_lookup: dict[tuple[str, str, str], HistoricalEstateFile] = {}
    for reference, inventory in zip(
        expected_inventory_refs, inventories, strict=True
    ):
        inventory_key = (reference.root_id, reference.inventory_sha256)
        if inventory_key in inventory_lookup:
            raise HistoricalProjectionError("supplied inventories must be unique")
        inventory_lookup[inventory_key] = inventory
        for item in inventory.files:
            file_lookup[(*inventory_key, item.logical_path)] = item

    envelope_lookup: dict[tuple[str, str, str], HistoricalExperimentEnvelope] = {}
    for supplied_envelope in envelopes:
        authority_key = (
            supplied_envelope.envelope_id,
            supplied_envelope.version,
            supplied_envelope.sha256(),
        )
        if authority_key in envelope_lookup:
            raise HistoricalProjectionError("supplied envelopes must be unique")
        envelope_lookup[authority_key] = supplied_envelope

    for run in projection.runs:
        source_inventory, source_file = _validate_evidence(
            run.source,
            inventories=inventory_lookup,
            files=file_lookup,
        )
        if source_file.candidate_role != "source":
            raise HistoricalProjectionError("projected run source must have source role")
        envelope_key = (
            run.envelope.envelope_id,
            run.envelope.version,
            run.envelope.envelope_sha256,
        )
        matched_envelope = envelope_lookup.get(envelope_key)
        if matched_envelope is None:
            raise HistoricalProjectionError(
                "projected run references an unavailable historical envelope"
            )
        if run.envelope != _expected_envelope_reference(matched_envelope):
            raise HistoricalProjectionError(
                "projected run envelope reference differs from semantic authority"
            )
        _validate_envelope_source(run, source_inventory, matched_envelope)

        for artifact in run.artifacts:
            if artifact.availability != "available":
                continue
            assert artifact.evidence is not None
            _inventory, artifact_file = _validate_evidence(
                artifact.evidence,
                inventories=inventory_lookup,
                files=file_lookup,
            )
            if artifact_file.candidate_role not in _ARTIFACT_ROLE_COMPATIBILITY[
                artifact.kind
            ]:
                raise HistoricalProjectionError(
                    "projected artifact role is incompatible with its reviewed kind"
                )

    return projection


def _reject_float(_value: str) -> NoReturn:
    raise HistoricalProjectionError(
        "projection JSON must not contain binary floats or non-finite numbers"
    )


def _reject_constant(_value: str) -> NoReturn:
    raise HistoricalProjectionError(
        "projection JSON must not contain binary floats or non-finite numbers"
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise HistoricalProjectionError(
                f"projection JSON contains duplicate object key {key!r}"
            )
        result[key] = value
    return result


def load_historical_estate_projection_json(
    data: bytes,
    *,
    inventories: Sequence[HistoricalEstateInventory],
    envelopes: Sequence[HistoricalExperimentEnvelope],
    max_bytes: int = DEFAULT_MAX_HISTORICAL_PROJECTION_JSON_BYTES,
) -> HistoricalEstateProjection:
    """Strictly decode and validate one bounded reviewed projection document."""

    _positive_integer(max_bytes, "projection JSON max_bytes")
    if not isinstance(data, bytes):
        raise HistoricalProjectionError("projection JSON must be bytes")
    if len(data) > max_bytes:
        raise HistoricalProjectionError("projection JSON exceeds its byte limit")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise HistoricalProjectionError("projection JSON must be valid UTF-8") from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except HistoricalProjectionError:
        raise
    except (json.JSONDecodeError, RecursionError) as error:
        raise HistoricalProjectionError("projection JSON is malformed") from error
    if not isinstance(value, dict):
        raise HistoricalProjectionError("projection JSON root must be an object")
    projection = HistoricalEstateProjection.from_dict(value)
    return validate_historical_estate_projection(
        projection,
        inventories=inventories,
        envelopes=envelopes,
    )
