"""Canonical identities for normalized historical experiment estates.

The records in this module deliberately separate a scientific definition from
the names people used for it, the occasions on which it ran, the bytes it
produced, and the executable recipe capable of reproducing it.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from .historical_envelopes import HistoricalSourceAuthority

HistoricalRoute = Literal["standalone", "flybrian_local", "flybrian_cloud"]
ArtifactDisposition = Literal[
    "bound",
    "candidate_overwrite_risk",
    "missing",
]
ComparisonStatus = Literal["equal", "different", "not_compared"]
InputKind = Literal["file", "tree"]
ArtifactComparison = Literal["exact_bytes", "canonical_json"]

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*(?:[.:][A-Za-z0-9][A-Za-z0-9_.:-]*)+$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class HistoricalNormalizationError(ValueError):
    """A normalized historical record is malformed or contradictory."""


def _identifier(value: object, path: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise HistoricalNormalizationError(f"{path} must be a namespaced identifier")
    return value


def _text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise HistoricalNormalizationError(f"{path} must be non-empty trimmed text")
    return value


def _sha256(value: object, path: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise HistoricalNormalizationError(f"{path} must be lowercase SHA-256")
    return value


def _canonical_value(value: object, path: str = "value") -> object:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        raise HistoricalNormalizationError(f"{path} must not contain binary floats")
    if isinstance(value, tuple | list):
        return [_canonical_value(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise HistoricalNormalizationError(f"{path} keys must be strings")
        return {key: _canonical_value(item, f"{path}.{key}") for key, item in value.items()}
    raise HistoricalNormalizationError(f"{path} contains an unsupported value")


def canonical_json_bytes(value: object) -> bytes:
    """Serialize identity-bearing records without platform-dependent formatting."""
    return json.dumps(
        _canonical_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


@dataclass(frozen=True)
class NormalizedExperimentDefinition:
    definition_id: str
    version: str
    family_id: str
    scientific_configuration: Mapping[str, object]
    source: HistoricalSourceAuthority

    def __post_init__(self) -> None:
        _identifier(self.definition_id, "definition.definition_id")
        _text(self.version, "definition.version")
        _identifier(self.family_id, "definition.family_id")
        configuration = _canonical_value(
            self.scientific_configuration,
            "definition.scientific_configuration",
        )
        if not isinstance(configuration, dict):
            raise HistoricalNormalizationError(
                "definition.scientific_configuration must be an object"
            )
        object.__setattr__(self, "scientific_configuration", configuration)

    @property
    def scientific_identity_sha256(self) -> str:
        return canonical_sha256(
            {
                "family_id": self.family_id,
                "scientific_configuration": self.scientific_configuration,
                "source": self.source.to_dict(),
            }
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "definition_id": self.definition_id,
            "version": self.version,
            "family_id": self.family_id,
            "scientific_identity_sha256": self.scientific_identity_sha256,
            "scientific_configuration": self.scientific_configuration,
            "source": self.source.to_dict(),
        }


@dataclass(frozen=True)
class HistoricalClaim:
    claim_id: str
    definition_id: str
    name: str
    description: str
    tags: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.claim_id, "claim.claim_id")
        _identifier(self.definition_id, "claim.definition_id")
        _text(self.name, "claim.name")
        _text(self.description, "claim.description")
        if tuple(sorted(set(self.tags))) != self.tags:
            raise HistoricalNormalizationError("claim.tags must be unique and sorted")
        for tag in self.tags:
            _text(tag, "claim.tags item")

    def to_dict(self) -> dict[str, object]:
        return {
            "claim_id": self.claim_id,
            "definition_id": self.definition_id,
            "name": self.name,
            "description": self.description,
            "tags": list(self.tags),
        }


@dataclass(frozen=True)
class HistoricalRunOccurrence:
    occurrence_id: str
    definition_id: str
    claim_ids: tuple[str, ...]
    evidence: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.occurrence_id, "occurrence.occurrence_id")
        _identifier(self.definition_id, "occurrence.definition_id")
        if not self.claim_ids or tuple(sorted(set(self.claim_ids))) != self.claim_ids:
            raise HistoricalNormalizationError(
                "occurrence.claim_ids must be non-empty, unique, and sorted"
            )
        for claim_id in self.claim_ids:
            _identifier(claim_id, "occurrence.claim_ids item")
        for evidence in self.evidence:
            _text(evidence, "occurrence.evidence item")

    def to_dict(self) -> dict[str, object]:
        return {
            "occurrence_id": self.occurrence_id,
            "definition_id": self.definition_id,
            "claim_ids": list(self.claim_ids),
            "evidence": list(self.evidence),
        }


@dataclass(frozen=True)
class HistoricalArtifactReference:
    artifact_id: str
    definition_id: str
    kind: str
    logical_path: str
    byte_length: int
    sha256: str
    disposition: ArtifactDisposition
    disposition_reason: str
    comparison: ArtifactComparison = "exact_bytes"
    excluded_json_fields: tuple[str, ...] = ()
    frame_interval_ms: int | None = None

    def __post_init__(self) -> None:
        _identifier(self.artifact_id, "artifact.artifact_id")
        _identifier(self.definition_id, "artifact.definition_id")
        _text(self.kind, "artifact.kind")
        path = _text(self.logical_path, "artifact.logical_path")
        if path.startswith(("/", "\\")) or ".." in path.replace("\\", "/").split("/"):
            raise HistoricalNormalizationError("artifact.logical_path must be relative and safe")
        if isinstance(self.byte_length, bool) or self.byte_length < 0:
            raise HistoricalNormalizationError("artifact.byte_length must be non-negative")
        _sha256(self.sha256, "artifact.sha256")
        if self.disposition not in {
            "bound",
            "candidate_overwrite_risk",
            "missing",
        }:
            raise HistoricalNormalizationError("artifact.disposition is unsupported")
        _text(self.disposition_reason, "artifact.disposition_reason")
        if self.comparison not in {"exact_bytes", "canonical_json"}:
            raise HistoricalNormalizationError("artifact.comparison is unsupported")
        if self.comparison == "exact_bytes" and self.excluded_json_fields:
            raise HistoricalNormalizationError("exact byte comparison cannot exclude JSON fields")
        if tuple(sorted(set(self.excluded_json_fields))) != self.excluded_json_fields:
            raise HistoricalNormalizationError(
                "artifact.excluded_json_fields must be unique and sorted"
            )
        for field in self.excluded_json_fields:
            _text(field, "artifact.excluded_json_fields item")
        if self.frame_interval_ms is not None and (
            isinstance(self.frame_interval_ms, bool)
            or not isinstance(self.frame_interval_ms, int)
            or self.frame_interval_ms <= 0
        ):
            raise HistoricalNormalizationError(
                "artifact.frame_interval_ms must be a positive integer"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "definition_id": self.definition_id,
            "kind": self.kind,
            "logical_path": self.logical_path,
            "byte_length": self.byte_length,
            "sha256": self.sha256,
            "disposition": self.disposition,
            "disposition_reason": self.disposition_reason,
            "comparison": self.comparison,
            "excluded_json_fields": list(self.excluded_json_fields),
            "frame_interval_ms": self.frame_interval_ms,
        }


@dataclass(frozen=True)
class HistoricalInputReference:
    input_id: str
    kind: InputKind
    logical_path: str
    byte_length: int
    sha256: str
    file_count: int
    provenance: str
    packaged_resource: str | None = None
    packaged_resource_encoding: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.input_id, "input.input_id")
        if self.kind not in {"file", "tree"}:
            raise HistoricalNormalizationError("input.kind is unsupported")
        path = _text(self.logical_path, "input.logical_path")
        if path.startswith(("/", "\\")) or ".." in path.replace("\\", "/").split("/"):
            raise HistoricalNormalizationError("input.logical_path must be relative and safe")
        if isinstance(self.byte_length, bool) or self.byte_length < 0:
            raise HistoricalNormalizationError("input.byte_length must be non-negative")
        _sha256(self.sha256, "input.sha256")
        if isinstance(self.file_count, bool) or self.file_count <= 0:
            raise HistoricalNormalizationError("input.file_count must be positive")
        if self.kind == "file" and self.file_count != 1:
            raise HistoricalNormalizationError("file input must have file_count 1")
        _text(self.provenance, "input.provenance")
        if self.packaged_resource is not None:
            resource = _text(self.packaged_resource, "input.packaged_resource")
            if "/" in resource or "\\" in resource or resource in {".", ".."}:
                raise HistoricalNormalizationError(
                    "input.packaged_resource must be a package-local filename"
                )
            if self.kind != "file":
                raise HistoricalNormalizationError("only file inputs may use a packaged resource")
            if self.packaged_resource_encoding != "base64":
                raise HistoricalNormalizationError(
                    "packaged input resources must declare base64 encoding"
                )
        elif self.packaged_resource_encoding is not None:
            raise HistoricalNormalizationError(
                "packaged_resource_encoding requires packaged_resource"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "input_id": self.input_id,
            "kind": self.kind,
            "logical_path": self.logical_path,
            "byte_length": self.byte_length,
            "sha256": self.sha256,
            "file_count": self.file_count,
            "provenance": self.provenance,
            "packaged_resource": self.packaged_resource,
            "packaged_resource_encoding": self.packaged_resource_encoding,
        }


@dataclass(frozen=True)
class HistoricalExecutionRecipe:
    recipe_id: str
    definition_id: str
    definition_sha256: str
    route: HistoricalRoute
    executor_id: str
    executor_version: str
    source: HistoricalSourceAuthority
    argv: tuple[str, ...]
    input_ids: tuple[str, ...]
    artifact_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.recipe_id, "recipe.recipe_id")
        _identifier(self.definition_id, "recipe.definition_id")
        _sha256(self.definition_sha256, "recipe.definition_sha256")
        if self.route not in {"standalone", "flybrian_local", "flybrian_cloud"}:
            raise HistoricalNormalizationError("recipe.route is unsupported")
        _identifier(self.executor_id, "recipe.executor_id")
        _text(self.executor_version, "recipe.executor_version")
        if not self.argv:
            raise HistoricalNormalizationError("recipe.argv must not be empty")
        for argument in self.argv:
            _text(argument, "recipe.argv item")
        if not self.input_ids or tuple(sorted(set(self.input_ids))) != self.input_ids:
            raise HistoricalNormalizationError(
                "recipe.input_ids must be non-empty, unique, and sorted"
            )
        for input_id in self.input_ids:
            _identifier(input_id, "recipe.input_ids item")
        if not self.artifact_ids or tuple(sorted(set(self.artifact_ids))) != self.artifact_ids:
            raise HistoricalNormalizationError(
                "recipe.artifact_ids must be non-empty, unique, and sorted"
            )
        for artifact_id in self.artifact_ids:
            _identifier(artifact_id, "recipe.artifact_ids item")

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_dict(include_sha256=False))

    def to_dict(self, *, include_sha256: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "recipe_id": self.recipe_id,
            "definition_id": self.definition_id,
            "definition_sha256": self.definition_sha256,
            "route": self.route,
            "executor_id": self.executor_id,
            "executor_version": self.executor_version,
            "source": self.source.to_dict(),
            "argv": list(self.argv),
            "input_ids": list(self.input_ids),
            "artifact_ids": list(self.artifact_ids),
        }
        if include_sha256:
            result["sha256"] = self.sha256
        return result


@dataclass(frozen=True)
class HistoricalComparedArtifact:
    artifact_id: str
    kind: str
    comparison: ArtifactComparison
    left_sha256: str
    right_sha256: str
    status: ComparisonStatus
    excluded_json_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.artifact_id, "compared_artifact.artifact_id")
        _text(self.kind, "compared_artifact.kind")
        if self.comparison not in {"exact_bytes", "canonical_json"}:
            raise HistoricalNormalizationError("compared_artifact.comparison is unsupported")
        _sha256(self.left_sha256, "compared_artifact.left_sha256")
        _sha256(self.right_sha256, "compared_artifact.right_sha256")
        if self.status not in {"equal", "different"}:
            raise HistoricalNormalizationError(
                "compared_artifact.status must be equal or different"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "comparison": self.comparison,
            "left_sha256": self.left_sha256,
            "right_sha256": self.right_sha256,
            "status": self.status,
            "excluded_json_fields": list(self.excluded_json_fields),
        }


@dataclass(frozen=True)
class HistoricalComparisonReceipt:
    comparison_id: str
    definition_id: str
    left_recipe_sha256: str
    right_recipe_sha256: str
    status: ComparisonStatus
    artifacts: tuple[HistoricalComparedArtifact, ...]
    differences: tuple[str, ...]

    def __post_init__(self) -> None:
        _identifier(self.comparison_id, "comparison.comparison_id")
        _identifier(self.definition_id, "comparison.definition_id")
        _sha256(self.left_recipe_sha256, "comparison.left_recipe_sha256")
        _sha256(self.right_recipe_sha256, "comparison.right_recipe_sha256")
        if self.status not in {"equal", "different", "not_compared"}:
            raise HistoricalNormalizationError("comparison.status is unsupported")
        artifact_ids = tuple(item.artifact_id for item in self.artifacts)
        if not artifact_ids or tuple(sorted(set(artifact_ids))) != artifact_ids:
            raise HistoricalNormalizationError(
                "comparison.artifacts must be non-empty, unique, and sorted"
            )
        for difference in self.differences:
            _text(difference, "comparison.differences item")
        if self.status == "equal" and self.differences:
            raise HistoricalNormalizationError("equal comparison must not contain differences")

    def to_dict(self) -> dict[str, object]:
        return {
            "comparison_id": self.comparison_id,
            "definition_id": self.definition_id,
            "left_recipe_sha256": self.left_recipe_sha256,
            "right_recipe_sha256": self.right_recipe_sha256,
            "status": self.status,
            "artifacts": [item.to_dict() for item in self.artifacts],
            "differences": list(self.differences),
        }


@dataclass(frozen=True)
class HistoricalNormalizationBundle:
    bundle_id: str
    version: str
    definitions: tuple[NormalizedExperimentDefinition, ...]
    claims: tuple[HistoricalClaim, ...]
    occurrences: tuple[HistoricalRunOccurrence, ...]
    inputs: tuple[HistoricalInputReference, ...]
    artifacts: tuple[HistoricalArtifactReference, ...]
    recipes: tuple[HistoricalExecutionRecipe, ...]
    comparisons: tuple[HistoricalComparisonReceipt, ...] = ()

    def __post_init__(self) -> None:
        _identifier(self.bundle_id, "bundle.bundle_id")
        _text(self.version, "bundle.version")
        if not self.definitions:
            raise HistoricalNormalizationError("bundle.definitions must not be empty")
        self._validate_references()

    def _validate_references(self) -> None:
        definition_records = {item.definition_id: item for item in self.definitions}
        definitions = set(definition_records)
        if len(definitions) != len(self.definitions):
            raise HistoricalNormalizationError("bundle definition IDs must be unique")
        claims = {item.claim_id for item in self.claims}
        inputs = {item.input_id for item in self.inputs}
        artifacts = {item.artifact_id for item in self.artifacts}
        recipes = {item.recipe_id for item in self.recipes}
        if len(claims) != len(self.claims):
            raise HistoricalNormalizationError("bundle claim IDs must be unique")
        if len(inputs) != len(self.inputs):
            raise HistoricalNormalizationError("bundle input IDs must be unique")
        if len(artifacts) != len(self.artifacts):
            raise HistoricalNormalizationError("bundle artifact IDs must be unique")
        if len(recipes) != len(self.recipes):
            raise HistoricalNormalizationError("bundle recipe IDs must be unique")
        for record in (
            *self.claims,
            *self.occurrences,
            *self.artifacts,
            *self.recipes,
            *self.comparisons,
        ):
            if record.definition_id not in definitions:
                raise HistoricalNormalizationError(
                    f"{record.__class__.__name__} references an unknown definition"
                )
        for occurrence in self.occurrences:
            if not set(occurrence.claim_ids) <= claims:
                raise HistoricalNormalizationError("occurrence references an unknown claim")
        for recipe in self.recipes:
            if not set(recipe.input_ids) <= inputs:
                raise HistoricalNormalizationError("recipe references an unknown input")
            if not set(recipe.artifact_ids) <= artifacts:
                raise HistoricalNormalizationError("recipe references an unknown artifact")
            if (
                recipe.definition_sha256
                != definition_records[recipe.definition_id].scientific_identity_sha256
            ):
                raise HistoricalNormalizationError(
                    "recipe definition checksum differs from its definition"
                )

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_dict(include_sha256=False))

    def to_dict(self, *, include_sha256: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": "1.0",
            "bundle_id": self.bundle_id,
            "version": self.version,
            "definitions": [item.to_dict() for item in self.definitions],
            "claims": [item.to_dict() for item in self.claims],
            "occurrences": [item.to_dict() for item in self.occurrences],
            "inputs": [item.to_dict() for item in self.inputs],
            "artifacts": [item.to_dict() for item in self.artifacts],
            "recipes": [item.to_dict() for item in self.recipes],
            "comparisons": [item.to_dict() for item in self.comparisons],
        }
        if include_sha256:
            result["sha256"] = self.sha256
        return result
