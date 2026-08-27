"""Versioned scientific artifact manifest shared by local and cloud consumers."""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Literal

ArtifactStatus = Literal["available", "unavailable", "failed"]
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MEDIA_TYPE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$"
)


def _identifier(value: object, path: str) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ValueError(f"{path} must be a safe 1-128 character identifier")
    return value


def _string(value: object, path: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{path} must be a non-empty string of at most {maximum} characters")
    return value


def _sha256(value: object, path: str, *, optional: bool = False) -> str | None:
    if optional and value is None:
        return None
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{path} must be a lower-case SHA-256")
    return value


def _required_sha256(value: object, path: str) -> str:
    result = _sha256(value, path)
    if result is None:
        raise AssertionError("required SHA-256 unexpectedly resolved to None")
    return result


def _integer(value: object, path: str, *, non_negative: bool = False) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{path} must be an integer")
    if non_negative and value < 0:
        raise ValueError(f"{path} must be non-negative")
    return value


def _boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path} must be a boolean")
    return value


def _object(value: object, path: str) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{path} must be an object with string keys")
    return value


def _array(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise ValueError(f"{path} must be an array")
    return value


def _safe_relative_path(value: object, path: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{path} must be a safe relative path")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError(f"{path} must be a safe relative path")
    return relative.as_posix()


def _path_inside(root: Path, path: Path) -> Path:
    resolved_root = root.resolve()
    resolved_path = path.resolve()
    try:
        resolved_path.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError(f"artifact path {path} escapes the run root") from error
    return resolved_path


@dataclass(frozen=True)
class Artifact:
    key: str
    kind: str
    media_type: str
    relative_path: str
    size_bytes: int
    sha256: str

    def __post_init__(self) -> None:
        _identifier(self.key, "artifact.key")
        _identifier(self.kind, "artifact.kind")
        if not isinstance(self.media_type, str) or _MEDIA_TYPE.fullmatch(self.media_type) is None:
            raise ValueError("artifact.media_type must be an Internet media type")
        _safe_relative_path(self.relative_path, "artifact.relative_path")
        _integer(self.size_bytes, "artifact.size_bytes", non_negative=True)
        _sha256(self.sha256, "artifact.sha256")

    @classmethod
    def from_file(
        cls,
        *,
        key: str,
        kind: str,
        media_type: str,
        path: Path,
        root: Path,
    ) -> Artifact:
        resolved_root = root.resolve()
        resolved_path = _path_inside(resolved_root, path)
        if not resolved_path.is_file():
            raise ValueError(f"artifact path {path} must be a file")
        data = resolved_path.read_bytes()
        return cls(
            key=key,
            kind=kind,
            media_type=media_type,
            relative_path=resolved_path.relative_to(resolved_root).as_posix(),
            size_bytes=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
        )

    @classmethod
    def from_dict(cls, value: object) -> Artifact:
        record = _object(value, "artifact")
        return cls(
            key=_identifier(record.get("key"), "artifact.key"),
            kind=_identifier(record.get("kind"), "artifact.kind"),
            media_type=_string(record.get("media_type"), "artifact.media_type", maximum=255),
            relative_path=_safe_relative_path(
                record.get("relative_path"),
                "artifact.relative_path",
            ),
            size_bytes=_integer(
                record.get("size_bytes"),
                "artifact.size_bytes",
                non_negative=True,
            ),
            sha256=_required_sha256(record.get("sha256"), "artifact.sha256"),
        )


@dataclass(frozen=True)
class DatasetReference:
    dataset_id: str
    sha256: str | None = None

    def __post_init__(self) -> None:
        _string(self.dataset_id, "dataset.dataset_id", maximum=255)
        _sha256(self.sha256, "dataset.sha256", optional=True)

    @classmethod
    def from_dict(cls, value: object) -> DatasetReference:
        record = _object(value, "dataset")
        return cls(
            dataset_id=_string(record.get("dataset_id"), "dataset.dataset_id", maximum=255),
            sha256=_sha256(record.get("sha256"), "dataset.sha256", optional=True),
        )


@dataclass(frozen=True)
class ArtifactDisposition:
    kind: str
    status: ArtifactStatus
    artifact_keys: tuple[str, ...] = ()
    reason: str | None = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        _identifier(self.kind, "disposition.kind")
        if self.status not in {"available", "unavailable", "failed"}:
            raise ValueError("disposition.status is invalid")
        for key in self.artifact_keys:
            _identifier(key, "disposition.artifact_keys item")
        if len(self.artifact_keys) != len(set(self.artifact_keys)):
            raise ValueError("disposition.artifact_keys must be unique")
        if self.status == "available":
            if not self.artifact_keys:
                raise ValueError("available disposition requires artifact keys")
            if self.reason is not None:
                raise ValueError("available disposition must not contain a reason")
            return
        if self.artifact_keys:
            raise ValueError(f"{self.status} disposition must not reference artifacts")
        _string(self.reason, f"{self.status} disposition requires a reason")

    @classmethod
    def from_dict(cls, value: object) -> ArtifactDisposition:
        record = _object(value, "disposition")
        raw_status = record.get("status")
        if raw_status not in {"available", "unavailable", "failed"}:
            raise ValueError("disposition.status is invalid")
        artifact_keys = tuple(
            _identifier(item, "disposition.artifact_keys item")
            for item in _array(record.get("artifact_keys"), "disposition.artifact_keys")
        )
        reason = record.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise ValueError("disposition.reason must be a string or null")
        return cls(
            kind=_identifier(record.get("kind"), "disposition.kind"),
            status=raw_status,
            artifact_keys=artifact_keys,
            reason=reason,
        )


@dataclass(frozen=True)
class ArtifactManifest:
    run_id: str
    engine_version: str
    backend_id: str
    backend_version: str
    experiment_spec_version: str
    experiment_sha256: str
    random_seed: int
    datasets: tuple[DatasetReference, ...]
    scientific_execution: bool
    deterministic_for_fixed_seed: bool
    artifacts: tuple[Artifact, ...]
    dispositions: tuple[ArtifactDisposition, ...]
    schema_version: str = "1.1"

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if self.schema_version != "1.1":
            raise ValueError("manifest.schema_version must equal '1.1'")
        _identifier(self.run_id, "manifest.run_id")
        _string(self.engine_version, "manifest.engine_version", maximum=64)
        _identifier(self.backend_id, "manifest.backend_id")
        _string(self.backend_version, "manifest.backend_version", maximum=64)
        _string(self.experiment_spec_version, "manifest.experiment_spec_version", maximum=64)
        _sha256(self.experiment_sha256, "manifest.experiment_sha256")
        _integer(self.random_seed, "manifest.random_seed", non_negative=True)
        _boolean(self.scientific_execution, "manifest.scientific_execution")
        _boolean(
            self.deterministic_for_fixed_seed,
            "manifest.deterministic_for_fixed_seed",
        )
        if not self.datasets:
            raise ValueError("manifest must reference at least one dataset")
        dataset_ids = [dataset.dataset_id for dataset in self.datasets]
        if len(dataset_ids) != len(set(dataset_ids)):
            raise ValueError("manifest dataset IDs must be unique")
        artifact_by_key = {artifact.key: artifact for artifact in self.artifacts}
        if len(artifact_by_key) != len(self.artifacts):
            raise ValueError("manifest artifact keys must be unique")
        disposition_kinds = [disposition.kind for disposition in self.dispositions]
        if len(disposition_kinds) != len(set(disposition_kinds)):
            raise ValueError("manifest disposition kinds must be unique")
        referenced_keys: list[str] = []
        for disposition in self.dispositions:
            disposition.validate()
            for key in disposition.artifact_keys:
                artifact = artifact_by_key.get(key)
                if artifact is None:
                    raise ValueError(f"disposition references missing artifact {key!r}")
                if artifact.kind != disposition.kind:
                    raise ValueError(
                        "available disposition must reference an artifact of the same kind"
                    )
                referenced_keys.append(key)
        if len(referenced_keys) != len(set(referenced_keys)):
            raise ValueError("an artifact cannot be referenced by multiple dispositions")
        orphaned = sorted(set(artifact_by_key) - set(referenced_keys))
        if orphaned:
            raise ValueError("available artifacts require a disposition: " + ", ".join(orphaned))

    def disposition(self, kind: str) -> ArtifactDisposition:
        for disposition in self.dispositions:
            if disposition.kind == kind:
                return disposition
        raise KeyError(f"manifest has no disposition for {kind!r}")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "engine_version": self.engine_version,
            "backend_id": self.backend_id,
            "backend_version": self.backend_version,
            "experiment_spec_version": self.experiment_spec_version,
            "experiment_sha256": self.experiment_sha256,
            "random_seed": self.random_seed,
            "datasets": [
                {"dataset_id": dataset.dataset_id, "sha256": dataset.sha256}
                for dataset in self.datasets
            ],
            "scientific_execution": self.scientific_execution,
            "deterministic_for_fixed_seed": self.deterministic_for_fixed_seed,
            "artifacts": [
                {
                    "key": artifact.key,
                    "kind": artifact.kind,
                    "media_type": artifact.media_type,
                    "relative_path": artifact.relative_path,
                    "size_bytes": artifact.size_bytes,
                    "sha256": artifact.sha256,
                }
                for artifact in self.artifacts
            ],
            "dispositions": [
                {
                    "kind": disposition.kind,
                    "status": disposition.status,
                    "artifact_keys": list(disposition.artifact_keys),
                    "reason": disposition.reason,
                }
                for disposition in self.dispositions
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True) + "\n"

    @classmethod
    def from_dict(cls, value: object) -> ArtifactManifest:
        record = _object(value, "manifest")
        return cls(
            schema_version=_string(record.get("schema_version"), "manifest.schema_version"),
            run_id=_identifier(record.get("run_id"), "manifest.run_id"),
            engine_version=_string(record.get("engine_version"), "manifest.engine_version"),
            backend_id=_identifier(record.get("backend_id"), "manifest.backend_id"),
            backend_version=_string(record.get("backend_version"), "manifest.backend_version"),
            experiment_spec_version=_string(
                record.get("experiment_spec_version"),
                "manifest.experiment_spec_version",
            ),
            experiment_sha256=_required_sha256(
                record.get("experiment_sha256"),
                "manifest.experiment_sha256",
            ),
            random_seed=_integer(
                record.get("random_seed"),
                "manifest.random_seed",
                non_negative=True,
            ),
            datasets=tuple(
                DatasetReference.from_dict(item)
                for item in _array(record.get("datasets"), "manifest.datasets")
            ),
            scientific_execution=_boolean(
                record.get("scientific_execution"),
                "manifest.scientific_execution",
            ),
            deterministic_for_fixed_seed=_boolean(
                record.get("deterministic_for_fixed_seed"),
                "manifest.deterministic_for_fixed_seed",
            ),
            artifacts=tuple(
                Artifact.from_dict(item)
                for item in _array(record.get("artifacts"), "manifest.artifacts")
            ),
            dispositions=tuple(
                ArtifactDisposition.from_dict(item)
                for item in _array(record.get("dispositions"), "manifest.dispositions")
            ),
        )

    @classmethod
    def read(cls, path: Path) -> ArtifactManifest:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            raise ValueError("manifest must contain valid JSON") from error
        return cls.from_dict(value)

    def verify_files(self, root: Path) -> None:
        for artifact in self.artifacts:
            path = _path_inside(root, root / artifact.relative_path)
            if not path.is_file():
                raise ValueError(f"artifact {artifact.key!r} is missing")
            data = path.read_bytes()
            if (
                len(data) != artifact.size_bytes
                or hashlib.sha256(data).hexdigest() != artifact.sha256
            ):
                raise ValueError(f"artifact {artifact.key!r} size or SHA-256 does not match")

    def write(self, path: Path) -> None:
        temporary = path.with_name(f".{path.name}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as handle:
                handle.write(self.to_json())
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
