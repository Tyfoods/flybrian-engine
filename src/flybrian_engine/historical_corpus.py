"""Consumer-neutral catalog exports from reviewed historical projections."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, NoReturn, TypeGuard, cast

from .historical_envelopes import HistoricalExperimentEnvelope, ReproducibilityClass
from .historical_projection import (
    HistoricalEstateProjection,
    HistoricalProjectedRun,
)

HISTORICAL_CATALOG_EXPORT_PROFILE_ID = "org.flybrian.historical-catalog-export"
HISTORICAL_CATALOG_EXPORT_PROFILE_VERSION = "1.0"
HISTORICAL_PROVENANCE_SPEC_VERSION = "historical/provenance-1"
DEFAULT_MAX_HISTORICAL_CATALOG_EXPORT_BYTES = 64 * 1024 * 1024

CatalogVisibility = Literal["public", "private", "team"]
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NAMESPACE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]*(?:[.:][A-Za-z0-9][A-Za-z0-9_.:-]*)+$"
)


def _is_catalog_visibility(value: object) -> TypeGuard[CatalogVisibility]:
    return value == "public" or value == "private" or value == "team"


def _is_reproducibility_class(value: object) -> TypeGuard[ReproducibilityClass]:
    return value in (
        "PROVENANCE_ONLY",
        "RUNNABLE_CONNECTOME",
        "RUNNABLE_EMBODIED",
    )


class HistoricalCatalogExportError(ValueError):
    """A reviewed historical catalog export is malformed or contradictory."""


def _text(value: object, path: str, *, maximum: int = 8192) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise HistoricalCatalogExportError(f"{path} must be a non-empty trimmed string")
    if len(value) > maximum:
        raise HistoricalCatalogExportError(
            f"{path} must contain at most {maximum} characters"
        )
    if unicodedata.normalize("NFC", value) != value:
        raise HistoricalCatalogExportError(f"{path} must use NFC Unicode normalization")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise HistoricalCatalogExportError(f"{path} must not contain control characters")
    return value


def _namespaced(value: object, path: str) -> str:
    checked = _text(value, path, maximum=255)
    if _NAMESPACE.fullmatch(checked) is None:
        raise HistoricalCatalogExportError(f"{path} must be namespaced")
    return checked


def _sha256(value: object, path: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise HistoricalCatalogExportError(f"{path} must be lowercase SHA-256")
    return value


def _positive_integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalCatalogExportError(f"{path} must be a positive integer")
    return value


def _non_negative_integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise HistoricalCatalogExportError(f"{path} must be a non-negative integer")
    return value


def _mapping(value: object, path: str, fields: frozenset[str]) -> Mapping[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise HistoricalCatalogExportError(f"{path} must be an object")
    actual = frozenset(value)
    if actual != fields:
        missing = ", ".join(sorted(fields - actual)) or "none"
        unknown = ", ".join(sorted(actual - fields)) or "none"
        raise HistoricalCatalogExportError(
            f"{path} fields differ (missing: {missing}; unknown: {unknown})"
        )
    return cast(Mapping[str, object], value)


def _array(value: object, path: str) -> Sequence[object]:
    if not isinstance(value, list):
        raise HistoricalCatalogExportError(f"{path} must be an array")
    return cast(Sequence[object], value)


def _canonical_value(value: object, path: str = "value") -> object:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        raise HistoricalCatalogExportError(f"{path} must not contain binary floats")
    if isinstance(value, tuple | list):
        return [
            _canonical_value(item, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise HistoricalCatalogExportError(f"{path} object keys must be strings")
        return {
            key: _canonical_value(item, f"{path}.{key}")
            for key, item in value.items()
        }
    raise HistoricalCatalogExportError(f"{path} contains unsupported value")


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


@dataclass(frozen=True)
class HistoricalCatalogMetadata:
    design_id: str
    design_version: int
    run_id: str
    external_source_key: str
    name: str
    description: str
    tags: tuple[str, ...]
    commit_message: str

    def __post_init__(self) -> None:
        _namespaced(self.design_id, "catalog_metadata.design_id")
        _positive_integer(self.design_version, "catalog_metadata.design_version")
        _namespaced(self.run_id, "catalog_metadata.run_id")
        _namespaced(self.external_source_key, "catalog_metadata.external_source_key")
        _text(self.name, "catalog_metadata.name", maximum=512)
        _text(self.description, "catalog_metadata.description")
        if tuple(sorted(self.tags)) != self.tags or len(set(self.tags)) != len(self.tags):
            raise HistoricalCatalogExportError(
                "catalog_metadata.tags must be unique and sorted"
            )
        for tag in self.tags:
            _text(tag, "catalog_metadata.tags item", maximum=128)
        _text(self.commit_message, "catalog_metadata.commit_message", maximum=1024)

    @property
    def identity(self) -> tuple[str, int, str]:
        return (self.design_id, self.design_version, self.run_id)


@dataclass(frozen=True)
class HistoricalCatalogExportRecord:
    design_id: str
    design_version: int
    run_id: str
    external_source_key: str
    name: str
    description: str
    tags: tuple[str, ...]
    visibility: CatalogVisibility
    reproducibility_class: ReproducibilityClass
    missing_requirements: tuple[str, ...]
    spec_version: str
    spec_json: dict[str, object]
    commit_message: str

    def __post_init__(self) -> None:
        _namespaced(self.design_id, "catalog_record.design_id")
        _positive_integer(self.design_version, "catalog_record.design_version")
        _namespaced(self.run_id, "catalog_record.run_id")
        _namespaced(self.external_source_key, "catalog_record.external_source_key")
        _text(self.name, "catalog_record.name", maximum=512)
        _text(self.description, "catalog_record.description")
        if tuple(sorted(self.tags)) != self.tags or len(set(self.tags)) != len(self.tags):
            raise HistoricalCatalogExportError(
                "catalog_record.tags must be unique and sorted"
            )
        for tag in self.tags:
            _text(tag, "catalog_record.tags item", maximum=128)
        if self.visibility not in {"public", "private", "team"}:
            raise HistoricalCatalogExportError("catalog_record.visibility is unsupported")
        if self.reproducibility_class not in {
            "PROVENANCE_ONLY",
            "RUNNABLE_CONNECTOME",
            "RUNNABLE_EMBODIED",
        }:
            raise HistoricalCatalogExportError(
                "catalog_record.reproducibility_class is unsupported"
            )
        if (
            tuple(sorted(self.missing_requirements)) != self.missing_requirements
            or len(set(self.missing_requirements)) != len(self.missing_requirements)
        ):
            raise HistoricalCatalogExportError(
                "catalog_record.missing_requirements must be unique and sorted"
            )
        for requirement in self.missing_requirements:
            checked = _text(
                requirement,
                "catalog_record.missing_requirements item",
                maximum=255,
            )
            if checked != checked.upper():
                raise HistoricalCatalogExportError(
                    "catalog_record.missing_requirements must be uppercase codes"
                )
        if self.reproducibility_class == "PROVENANCE_ONLY":
            if self.spec_version != HISTORICAL_PROVENANCE_SPEC_VERSION:
                raise HistoricalCatalogExportError(
                    "provenance catalog record requires historical provenance spec"
                )
            if not self.missing_requirements:
                raise HistoricalCatalogExportError(
                    "provenance catalog record requires missing requirements"
                )
        elif self.missing_requirements:
            raise HistoricalCatalogExportError(
                "runnable reproducibility class must not contain missing requirements"
            )
        _text(self.spec_version, "catalog_record.spec_version", maximum=255)
        canonical = _canonical_value(self.spec_json, "catalog_record.spec_json")
        if not isinstance(canonical, dict):
            raise HistoricalCatalogExportError("catalog_record.spec_json must be an object")
        object.__setattr__(self, "spec_json", copy.deepcopy(canonical))
        _text(self.commit_message, "catalog_record.commit_message", maximum=1024)
        self._validate_spec_projection()

    def _validate_spec_projection(self) -> None:
        if self.reproducibility_class != "PROVENANCE_ONLY":
            return
        record = _mapping(
            self.spec_json,
            "catalog_record.spec_json",
            frozenset({"specVersion", "historical_record"}),
        )
        if record["specVersion"] != HISTORICAL_PROVENANCE_SPEC_VERSION:
            raise HistoricalCatalogExportError(
                "catalog_record spec version differs from provenance projection"
            )
        historical = _mapping(
            record["historical_record"],
            "catalog_record.spec_json.historical_record",
            frozenset(
                {
                    "schema_version",
                    "design_id",
                    "design_version",
                    "run_id",
                    "projection",
                    "review",
                    "contributor",
                    "visibility",
                    "source",
                    "envelope",
                    "reproducibility_class",
                    "missing_requirements",
                    "artifacts",
                }
            ),
        )
        if (
            historical["design_id"],
            historical["design_version"],
            historical["run_id"],
        ) != self.identity:
            raise HistoricalCatalogExportError(
                "catalog_record identity differs from provenance projection"
            )
        if historical["visibility"] != self.visibility:
            raise HistoricalCatalogExportError(
                "catalog_record visibility differs from provenance projection"
            )
        if historical["reproducibility_class"] != self.reproducibility_class:
            raise HistoricalCatalogExportError(
                "catalog_record reproducibility differs from provenance projection"
            )
        if historical["missing_requirements"] != list(self.missing_requirements):
            raise HistoricalCatalogExportError(
                "catalog_record missing requirements differ from provenance projection"
            )

    @property
    def identity(self) -> tuple[str, int, str]:
        return (self.design_id, self.design_version, self.run_id)

    def _identity_dict(self) -> dict[str, object]:
        return {
            "designId": self.design_id,
            "designVersion": self.design_version,
            "runId": self.run_id,
            "externalSourceKey": self.external_source_key,
            "name": self.name,
            "description": self.description,
            "tags": list(self.tags),
            "source": "import",
            "visibility": self.visibility,
            "reproducibilityClass": self.reproducibility_class,
            "missingRequirements": list(self.missing_requirements),
            "specVersion": self.spec_version,
            "specJson": copy.deepcopy(self.spec_json),
            "commitMessage": self.commit_message,
        }

    @property
    def source_metadata_checksum_sha256(self) -> str:
        return _digest(self._identity_dict())

    def to_dict(self) -> dict[str, object]:
        value = self._identity_dict()
        value["sourceMetadataChecksumSha256"] = self.source_metadata_checksum_sha256
        return value

    @classmethod
    def from_dict(cls, value: object) -> HistoricalCatalogExportRecord:
        record = _mapping(
            value,
            "catalog_record",
            frozenset(
                {
                    "designId",
                    "designVersion",
                    "runId",
                    "externalSourceKey",
                    "sourceMetadataChecksumSha256",
                    "name",
                    "description",
                    "tags",
                    "source",
                    "visibility",
                    "reproducibilityClass",
                    "missingRequirements",
                    "specVersion",
                    "specJson",
                    "commitMessage",
                }
            ),
        )
        if record["source"] != "import":
            raise HistoricalCatalogExportError("catalog_record.source must be import")
        visibility = record["visibility"]
        reproducibility = record["reproducibilityClass"]
        if not _is_catalog_visibility(visibility):
            raise HistoricalCatalogExportError("catalog_record.visibility is unsupported")
        if not _is_reproducibility_class(reproducibility):
            raise HistoricalCatalogExportError(
                "catalog_record.reproducibility_class is unsupported"
            )
        raw_spec = record["specJson"]
        if not isinstance(raw_spec, dict):
            raise HistoricalCatalogExportError("catalog_record.specJson must be an object")
        result = cls(
            design_id=_namespaced(record["designId"], "catalog_record.designId"),
            design_version=_positive_integer(
                record["designVersion"], "catalog_record.designVersion"
            ),
            run_id=_namespaced(record["runId"], "catalog_record.runId"),
            external_source_key=_namespaced(
                record["externalSourceKey"], "catalog_record.externalSourceKey"
            ),
            name=_text(record["name"], "catalog_record.name", maximum=512),
            description=_text(record["description"], "catalog_record.description"),
            tags=tuple(
                _text(item, "catalog_record.tags item", maximum=128)
                for item in _array(record["tags"], "catalog_record.tags")
            ),
            visibility=visibility,
            reproducibility_class=reproducibility,
            missing_requirements=tuple(
                _text(item, "catalog_record.missingRequirements item", maximum=255)
                for item in _array(
                    record["missingRequirements"],
                    "catalog_record.missingRequirements",
                )
            ),
            spec_version=_text(
                record["specVersion"], "catalog_record.specVersion", maximum=255
            ),
            spec_json=cast(dict[str, object], raw_spec),
            commit_message=_text(
                record["commitMessage"],
                "catalog_record.commitMessage",
                maximum=1024,
            ),
        )
        supplied_checksum = _sha256(
            record["sourceMetadataChecksumSha256"],
            "catalog_record.sourceMetadataChecksumSha256",
        )
        if supplied_checksum != result.source_metadata_checksum_sha256:
            raise HistoricalCatalogExportError(
                "catalog_record source metadata checksum differs"
            )
        return result


@dataclass(frozen=True)
class HistoricalCatalogExport:
    projection_id: str
    projection_version: str
    projection_sha256: str
    import_sha256: str
    records: tuple[HistoricalCatalogExportRecord, ...]
    profile_id: str = HISTORICAL_CATALOG_EXPORT_PROFILE_ID
    profile_version: str = HISTORICAL_CATALOG_EXPORT_PROFILE_VERSION
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.schema_version != "1.0":
            raise HistoricalCatalogExportError("catalog_export.schema_version is unsupported")
        if self.profile_id != HISTORICAL_CATALOG_EXPORT_PROFILE_ID:
            raise HistoricalCatalogExportError("catalog_export.profile_id is unsupported")
        if self.profile_version != HISTORICAL_CATALOG_EXPORT_PROFILE_VERSION:
            raise HistoricalCatalogExportError("catalog_export.profile_version is unsupported")
        _namespaced(self.projection_id, "catalog_export.projection_id")
        _text(self.projection_version, "catalog_export.projection_version", maximum=255)
        _sha256(self.projection_sha256, "catalog_export.projection_sha256")
        _sha256(self.import_sha256, "catalog_export.import_sha256")
        identities = tuple(item.identity for item in self.records)
        if identities != tuple(sorted(identities)) or len(identities) != len(set(identities)):
            raise HistoricalCatalogExportError(
                "catalog_export.records must be unique and sorted by reviewed identity"
            )
        external_keys = tuple(item.external_source_key for item in self.records)
        if len(external_keys) != len(set(external_keys)):
            raise HistoricalCatalogExportError(
                "catalog_export.records must have unique external source keys"
            )

    @property
    def record_count(self) -> int:
        return len(self.records)

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": self.schema_version,
            "profileId": self.profile_id,
            "profileVersion": self.profile_version,
            "projectionId": self.projection_id,
            "projectionVersion": self.projection_version,
            "projectionSha256": self.projection_sha256,
            "importSha256": self.import_sha256,
            "recordCount": self.record_count,
            "records": [item.to_dict() for item in self.records],
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    @classmethod
    def from_dict(cls, value: object) -> HistoricalCatalogExport:
        record = _mapping(
            value,
            "catalog_export",
            frozenset(
                {
                    "schemaVersion",
                    "profileId",
                    "profileVersion",
                    "projectionId",
                    "projectionVersion",
                    "projectionSha256",
                    "importSha256",
                    "recordCount",
                    "records",
                }
            ),
        )
        result = cls(
            schema_version=_text(
                record["schemaVersion"], "catalog_export.schemaVersion", maximum=32
            ),
            profile_id=_namespaced(record["profileId"], "catalog_export.profileId"),
            profile_version=_text(
                record["profileVersion"], "catalog_export.profileVersion", maximum=32
            ),
            projection_id=_namespaced(
                record["projectionId"], "catalog_export.projectionId"
            ),
            projection_version=_text(
                record["projectionVersion"],
                "catalog_export.projectionVersion",
                maximum=255,
            ),
            projection_sha256=_sha256(
                record["projectionSha256"], "catalog_export.projectionSha256"
            ),
            import_sha256=_sha256(
                record["importSha256"], "catalog_export.importSha256"
            ),
            records=tuple(
                HistoricalCatalogExportRecord.from_dict(item)
                for item in _array(record["records"], "catalog_export.records")
            ),
        )
        count = _non_negative_integer(record["recordCount"], "catalog_export.recordCount")
        if count != result.record_count:
            raise HistoricalCatalogExportError("catalog_export.recordCount differs")
        return result


def _historical_provenance_spec(
    projection: HistoricalEstateProjection,
    run: HistoricalProjectedRun,
    envelope: HistoricalExperimentEnvelope,
    contributor: object,
) -> dict[str, object]:
    if not hasattr(contributor, "to_dict"):
        raise HistoricalCatalogExportError("projection contributor cannot be serialized")
    return {
        "specVersion": HISTORICAL_PROVENANCE_SPEC_VERSION,
        "historical_record": {
            "schema_version": "1.0",
            "design_id": run.design_id,
            "design_version": run.design_version,
            "run_id": run.run_id,
            "projection": {
                "projection_id": projection.projection_id,
                "version": projection.version,
                "projection_sha256": projection.sha256(),
                "import_sha256": projection.import_sha256(),
            },
            "review": projection.review.to_dict(),
            "contributor": contributor.to_dict(),
            "visibility": run.visibility.visibility,
            "source": {
                "repository_path": run.source_repository_path,
                "evidence": run.source.to_dict(),
            },
            "envelope": envelope.to_dict(),
            "reproducibility_class": envelope.reproducibility_class,
            "missing_requirements": list(envelope.missing_requirements),
            "artifacts": [artifact.to_dict() for artifact in run.artifacts],
        },
    }


def build_historical_catalog_export(
    projection: HistoricalEstateProjection,
    *,
    envelopes: Sequence[HistoricalExperimentEnvelope],
    metadata: Sequence[HistoricalCatalogMetadata],
) -> HistoricalCatalogExport:
    """Project one already-validated reviewed manifest into a catalog transport."""

    metadata_lookup = {item.identity: item for item in metadata}
    if len(metadata_lookup) != len(metadata):
        raise HistoricalCatalogExportError("catalog metadata identities must be unique")
    run_identities = {item.identity for item in projection.runs}
    if set(metadata_lookup) != run_identities:
        raise HistoricalCatalogExportError(
            "catalog metadata identities differ from reviewed projection"
        )
    envelope_lookup = {
        (item.envelope_id, item.version, item.sha256()): item for item in envelopes
    }
    if len(envelope_lookup) != len(envelopes):
        raise HistoricalCatalogExportError("catalog envelopes must be unique")
    contributor_lookup = {
        item.contributor_id: item for item in projection.contributors
    }

    records: list[HistoricalCatalogExportRecord] = []
    for run in projection.runs:
        details = metadata_lookup[run.identity]
        envelope = envelope_lookup.get(
            (
                run.envelope.envelope_id,
                run.envelope.version,
                run.envelope.envelope_sha256,
            )
        )
        if envelope is None:
            raise HistoricalCatalogExportError(
                "catalog run references unavailable envelope authority"
            )
        if run.visibility.visibility != "public":
            raise HistoricalCatalogExportError(
                "public catalog export accepts only public reviewed records"
            )
        contributor = contributor_lookup.get(run.contributor_id)
        if contributor is None:
            raise HistoricalCatalogExportError(
                "catalog run references unavailable contributor authority"
            )
        if envelope.reproducibility_class == "PROVENANCE_ONLY":
            spec_version = HISTORICAL_PROVENANCE_SPEC_VERSION
            spec_json = _historical_provenance_spec(
                projection, run, envelope, contributor
            )
        else:
            if envelope.fes is None:
                raise HistoricalCatalogExportError(
                    "runnable envelope does not contain exact FES"
                )
            spec_version = "1.0"
            spec_json = copy.deepcopy(envelope.fes)
        records.append(
            HistoricalCatalogExportRecord(
                design_id=run.design_id,
                design_version=run.design_version,
                run_id=run.run_id,
                external_source_key=details.external_source_key,
                name=details.name,
                description=details.description,
                tags=details.tags,
                visibility=run.visibility.visibility,
                reproducibility_class=envelope.reproducibility_class,
                missing_requirements=envelope.missing_requirements,
                spec_version=spec_version,
                spec_json=spec_json,
                commit_message=details.commit_message,
            )
        )

    return HistoricalCatalogExport(
        projection_id=projection.projection_id,
        projection_version=projection.version,
        projection_sha256=projection.sha256(),
        import_sha256=projection.import_sha256(),
        records=tuple(records),
    )


def _reject_float(_value: str) -> NoReturn:
    raise HistoricalCatalogExportError(
        "historical catalog JSON must not contain binary floats or non-finite numbers"
    )


def _reject_constant(_value: str) -> NoReturn:
    raise HistoricalCatalogExportError(
        "historical catalog JSON must not contain binary floats or non-finite numbers"
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise HistoricalCatalogExportError(
                f"historical catalog JSON contains duplicate object key {key!r}"
            )
        result[key] = value
    return result


def load_historical_catalog_export_json(
    data: bytes,
    *,
    max_bytes: int = DEFAULT_MAX_HISTORICAL_CATALOG_EXPORT_BYTES,
) -> HistoricalCatalogExport:
    """Strictly decode one bounded consumer-neutral catalog export."""

    _positive_integer(max_bytes, "historical catalog JSON max_bytes")
    if not isinstance(data, bytes):
        raise HistoricalCatalogExportError("historical catalog JSON must be bytes")
    if len(data) > max_bytes:
        raise HistoricalCatalogExportError("historical catalog JSON exceeds its byte limit")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise HistoricalCatalogExportError(
            "historical catalog JSON must be valid UTF-8"
        ) from error
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except HistoricalCatalogExportError:
        raise
    except (json.JSONDecodeError, RecursionError) as error:
        raise HistoricalCatalogExportError("historical catalog JSON is malformed") from error
    if not isinstance(value, dict):
        raise HistoricalCatalogExportError("historical catalog JSON root must be an object")
    return HistoricalCatalogExport.from_dict(value)
