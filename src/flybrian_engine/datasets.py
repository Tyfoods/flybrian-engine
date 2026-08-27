"""Portable dataset manifests and immutable verified file access."""

from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import stat
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from urllib.parse import urlsplit

DatasetRole = Literal[
    "connectivity",
    "neurons",
    "motor_anatomy",
    "morphology",
    "crosswalk",
    "extension",
]
DatasetAccess = Literal["public", "token_required", "restricted"]
Redistribution = Literal["allowed", "prohibited", "unknown"]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MEDIA_TYPE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]*$")
_ROLES = {"connectivity", "neurons", "motor_anatomy", "morphology", "crosswalk", "extension"}


class DatasetVerificationError(ValueError):
    """Dataset bytes do not match their portable manifest."""


def _object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{path} must be an object with string keys")
    return value


def _string(value: object, path: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ValueError(f"{path} must be a non-empty string of at most {maximum} characters")
    return value


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{path} must be a non-negative integer")
    return value


def _source_url(value: object) -> str:
    source_url = _string(value, "manifest.source_url")
    message = "manifest.source_url must be an absolute HTTP(S) URL without credentials or fragment"
    try:
        parsed = urlsplit(source_url)
        hostname = parsed.hostname
        _ = parsed.port
    except ValueError as error:
        raise ValueError(message) from error
    if (
        source_url != source_url.strip()
        or parsed.scheme not in {"http", "https"}
        or not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise ValueError(message)
    return source_url


def _safe_path(value: object, path: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError(f"{path} must be a safe relative POSIX path")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or relative.as_posix() != value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise ValueError(f"{path} must be a safe relative POSIX path")
    return relative.as_posix()


@dataclass(frozen=True)
class DatasetFile:
    role: DatasetRole
    path: str
    sha256: str
    size_bytes: int
    media_type: str
    schema_id: str
    data_rows: int

    @classmethod
    def from_dict(cls, value: object, index: int) -> DatasetFile:
        path = f"files[{index}]"
        record = _object(value, path)
        expected = {
            "role",
            "path",
            "sha256",
            "size_bytes",
            "media_type",
            "schema_id",
            "data_rows",
        }
        unknown = sorted(set(record) - expected)
        missing = sorted(expected - set(record))
        if unknown or missing:
            raise ValueError(f"{path} fields differ: missing={missing}, unknown={unknown}")
        role = record["role"]
        if role not in _ROLES:
            raise ValueError(f"{path}.role is unsupported")
        digest = record["sha256"]
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise ValueError(f"{path}.sha256 must be a lower-case SHA-256")
        media_type = record["media_type"]
        if not isinstance(media_type, str) or _MEDIA_TYPE.fullmatch(media_type) is None:
            raise ValueError(f"{path}.media_type must be an Internet media type")
        return cls(
            role=role,
            path=_safe_path(record["path"], f"{path}.path"),
            sha256=digest,
            size_bytes=_integer(record["size_bytes"], f"{path}.size_bytes"),
            media_type=media_type,
            schema_id=_string(record["schema_id"], f"{path}.schema_id", maximum=255),
            data_rows=_integer(record["data_rows"], f"{path}.data_rows"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "role": self.role,
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
            "media_type": self.media_type,
            "schema_id": self.schema_id,
            "data_rows": self.data_rows,
        }


@dataclass(frozen=True)
class DatasetManifest:
    dataset_id: str
    provider: str
    release: str
    source_url: str
    citation: str | None
    license: str
    redistribution: Redistribution
    access: DatasetAccess
    files: tuple[DatasetFile, ...]
    schema_version: str = "1.0"

    @classmethod
    def from_dict(cls, value: object) -> DatasetManifest:
        record = _object(value, "manifest")
        expected = {
            "schema_version",
            "dataset_id",
            "provider",
            "release",
            "source_url",
            "citation",
            "license",
            "redistribution",
            "access",
            "files",
        }
        unknown = sorted(set(record) - expected)
        missing = sorted(expected - set(record))
        if unknown or missing:
            raise ValueError(f"manifest fields differ: missing={missing}, unknown={unknown}")
        if record["schema_version"] != "1.0":
            raise ValueError("manifest.schema_version must equal '1.0'")
        raw_files = record["files"]
        if not isinstance(raw_files, list) or not raw_files:
            raise ValueError("manifest.files must be a non-empty array")
        files = tuple(DatasetFile.from_dict(item, index) for index, item in enumerate(raw_files))
        paths = [item.path for item in files]
        if len(paths) != len(set(paths)):
            raise ValueError("manifest.files paths must be unique")
        if len({path.casefold() for path in paths}) != len(paths):
            raise ValueError("manifest.files paths must not be case-colliding")
        citation = record["citation"]
        if citation is not None:
            citation = _string(citation, "manifest.citation")
        redistribution = record["redistribution"]
        if redistribution not in {"allowed", "prohibited", "unknown"}:
            raise ValueError("manifest.redistribution is unsupported")
        access = record["access"]
        if access not in {"public", "token_required", "restricted"}:
            raise ValueError("manifest.access is unsupported")
        return cls(
            dataset_id=_string(record["dataset_id"], "manifest.dataset_id", maximum=255),
            provider=_string(record["provider"], "manifest.provider", maximum=255),
            release=_string(record["release"], "manifest.release", maximum=255),
            source_url=_source_url(record["source_url"]),
            citation=citation,
            license=_string(record["license"], "manifest.license", maximum=255),
            redistribution=redistribution,
            access=access,
            files=files,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "dataset_id": self.dataset_id,
            "provider": self.provider,
            "release": self.release,
            "source_url": self.source_url,
            "citation": self.citation,
            "license": self.license,
            "redistribution": self.redistribution,
            "access": self.access,
            "files": [item.to_dict() for item in self.files],
        }

    def canonical_bytes(self) -> bytes:
        return json.dumps(
            self.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()

    def verify(self, root: Path) -> VerifiedDataset:
        return VerifiedDataset.create(self, root)


@dataclass(frozen=True)
class _Fingerprint:
    size: int
    sha256: str
    device: int
    inode: int
    modified_ns: int


def _path_for(root: Path, item: DatasetFile) -> Path:
    candidate = root.joinpath(*PurePosixPath(item.path).parts)
    current = root
    for part in PurePosixPath(item.path).parts:
        current = current / part
        if current.is_symlink():
            raise DatasetVerificationError(f"{item.path} must not contain a symbolic link")
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as error:
        raise DatasetVerificationError(f"{item.path} escapes the dataset root") from error
    return resolved


def _fingerprint(path: Path) -> _Fingerprint:
    try:
        with path.open("rb") as handle:
            file_stat = os.fstat(handle.fileno())
            if not stat.S_ISREG(file_stat.st_mode):
                raise DatasetVerificationError(f"{path.name} must be a regular file")
            digest = hashlib.sha256()
            size = 0
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
    except OSError as error:
        raise DatasetVerificationError(f"cannot read declared dataset file {path.name}") from error
    return _Fingerprint(
        size, digest.hexdigest(), file_stat.st_dev, file_stat.st_ino, file_stat.st_mtime_ns
    )


def _csv_data_rows(path: Path) -> int:
    try:
        with path.open("r", encoding="utf-8", errors="strict", newline="") as handle:
            reader = csv.reader(handle)
            next(reader)
            return sum(1 for _ in reader)
    except StopIteration as error:
        raise DatasetVerificationError(f"{path.name} has no CSV header") from error
    except (OSError, UnicodeError, csv.Error) as error:
        raise DatasetVerificationError(f"{path.name} is not valid UTF-8 CSV") from error


@dataclass(frozen=True)
class VerifiedDataset:
    manifest: DatasetManifest
    root: Path
    fingerprints: dict[str, _Fingerprint]

    @classmethod
    def create(cls, manifest: DatasetManifest, root: Path) -> VerifiedDataset:
        if root.is_symlink():
            raise DatasetVerificationError("dataset root must not be a symbolic link")
        resolved_root = root.resolve()
        if not resolved_root.is_dir():
            raise DatasetVerificationError("dataset root must be a directory")
        fingerprints: dict[str, _Fingerprint] = {}
        for item in manifest.files:
            path = _path_for(resolved_root, item)
            fingerprint = _fingerprint(path)
            if fingerprint.size != item.size_bytes or fingerprint.sha256 != item.sha256:
                raise DatasetVerificationError(f"{item.path} size or SHA-256 does not match")
            if item.media_type == "text/csv" and _csv_data_rows(path) != item.data_rows:
                raise DatasetVerificationError(f"{item.path} data-row count does not match")
            if _fingerprint(path) != fingerprint:
                raise DatasetVerificationError(f"{item.path} changed during verification")
            fingerprints[item.path] = fingerprint
        return cls(manifest, resolved_root, fingerprints)

    def files_for_schema(self, schema_id: str) -> tuple[DatasetFile, ...]:
        return tuple(item for item in self.manifest.files if item.schema_id == schema_id)

    def csv_rows(
        self,
        item: DatasetFile,
    ) -> Iterator[tuple[tuple[str, ...], int, tuple[str, ...]]]:
        expected = self.fingerprints.get(item.path)
        if expected is None:
            raise DatasetVerificationError(f"{item.path} is not part of this verified dataset")
        path = _path_for(self.root, item)
        if _fingerprint(path) != expected:
            raise DatasetVerificationError(f"{item.path} changed after verification")
        try:
            with path.open("r", encoding="utf-8", errors="strict", newline="") as handle:
                reader = csv.reader(handle)
                header = tuple(next(reader))
                for row_number, row in enumerate(reader, start=1):
                    yield header, row_number, tuple(row)
        except StopIteration as error:
            raise DatasetVerificationError(f"{item.path} has no CSV header") from error
        except (OSError, UnicodeError, csv.Error) as error:
            raise DatasetVerificationError(f"{item.path} is not valid UTF-8 CSV") from error
        if _fingerprint(path) != expected:
            raise DatasetVerificationError(f"{item.path} changed during parsing")

    def csv_header(self, item: DatasetFile) -> tuple[str, ...]:
        """Return a verified header for a header-only CSV source."""
        expected = self.fingerprints.get(item.path)
        if expected is None:
            raise DatasetVerificationError(f"{item.path} is not part of this verified dataset")
        path = _path_for(self.root, item)
        if _fingerprint(path) != expected:
            raise DatasetVerificationError(f"{item.path} changed after verification")
        try:
            with path.open("r", encoding="utf-8", errors="strict", newline="") as handle:
                header = tuple(next(csv.reader(handle)))
        except StopIteration as error:
            raise DatasetVerificationError(f"{item.path} has no CSV header") from error
        except (OSError, UnicodeError, csv.Error) as error:
            raise DatasetVerificationError(f"{item.path} is not valid UTF-8 CSV") from error
        if _fingerprint(path) != expected:
            raise DatasetVerificationError(f"{item.path} changed during header parsing")
        return header
