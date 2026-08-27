"""Deterministic, non-executing inventory of historical experiment estates."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypeAlias

HISTORICAL_ESTATE_INVENTORY_PROFILE_ID = "org.flybrian.historical-estate-inventory"
HISTORICAL_ESTATE_INVENTORY_PROFILE_VERSION = "1.0"

EstateAccess = Literal["public", "private", "restricted"]
EstateRedistribution = Literal["permitted", "prohibited", "unknown"]
EstateCandidateRole = Literal[
    "source", "result", "array", "video", "image", "narrative", "archive", "unknown"
]
EstateImportDisposition = Literal[
    "source_candidate", "artifact_candidate", "review_required"
]
EstateExcludedEntryKind = Literal["file", "directory"]
EstateExclusionReason = Literal["platform_metadata", "python_bytecode_cache"]
EstateClassification: TypeAlias = tuple[str, EstateCandidateRole, EstateImportDisposition]

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_NAMESPACE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]*(?:[.:][A-Za-z0-9][A-Za-z0-9_.:-]*)+$"
)
_WINDOWS_RESERVED = {
    "aux",
    "com1",
    "com2",
    "com3",
    "com4",
    "com5",
    "com6",
    "com7",
    "com8",
    "com9",
    "con",
    "lpt1",
    "lpt2",
    "lpt3",
    "lpt4",
    "lpt5",
    "lpt6",
    "lpt7",
    "lpt8",
    "lpt9",
    "nul",
    "prn",
}
_SECRET_WORDS = re.compile(r"(?:credential|secret|token|password|private[_-]?key)", re.I)
_SECRET_SUFFIXES = {".jks", ".key", ".p12", ".pfx", ".pem"}
_CHUNK_BYTES = 1024 * 1024


class HistoricalEstateError(ValueError):
    """A historical estate cannot be safely or deterministically inventoried."""


def _text(value: object, path: str, *, maximum: int = 2048) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise HistoricalEstateError(f"{path} must be a non-empty trimmed string")
    if len(value) > maximum:
        raise HistoricalEstateError(f"{path} must contain at most {maximum} characters")
    if any(unicodedata.category(character).startswith("C") for character in value):
        raise HistoricalEstateError(f"{path} must not contain control characters")
    if unicodedata.normalize("NFC", value) != value:
        raise HistoricalEstateError(f"{path} must use NFC Unicode normalization")
    return value


def _positive_integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise HistoricalEstateError(f"{path} must be a positive integer")
    return value


def _safe_logical_path(value: object, path: str, *, maximum: int = 2048) -> str:
    checked = _text(value, path, maximum=maximum)
    if checked.startswith(("/", "\\")) or "\\" in checked:
        raise HistoricalEstateError(f"{path} must be a POSIX relative path")
    parts = checked.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise HistoricalEstateError(f"{path} contains an unsafe path segment")
    for part in parts:
        if re.search(r"[<>:\"|?*]", part) is not None:
            raise HistoricalEstateError(f"{path} contains a nonportable path character")
        if part.endswith((" ", ".")) or re.search(r"[ .]\.", part) is not None:
            raise HistoricalEstateError(f"{path} contains a nonportable trailing space or dot")
        stem = part.split(".", 1)[0].casefold()
        if stem in _WINDOWS_RESERVED:
            raise HistoricalEstateError(f"{path} contains a reserved Windows path segment")
    return checked


def _reject_sensitive_path(logical_path: str) -> None:
    parts = logical_path.split("/")
    for part in parts:
        folded = part.casefold()
        if part.startswith(".") and part != ".gitkeep":
            raise HistoricalEstateError(
                f"historical estate contains hidden path component: {logical_path}"
            )
        if (
            folded == ".env"
            or folded.startswith(".env.")
            or _SECRET_WORDS.search(folded) is not None
            or Path(folded).suffix in _SECRET_SUFFIXES
            or folded in {"id_rsa", "id_dsa", "id_ecdsa", "id_ed25519"}
        ):
            raise HistoricalEstateError(
                f"historical estate contains a sensitive path: {logical_path}"
            )


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


@dataclass(frozen=True)
class HistoricalEstateLimits:
    max_files: int = 100_000
    max_file_bytes: int = 128 * 1024**3
    max_total_bytes: int = 2 * 1024**4
    max_depth: int = 32
    max_path_chars: int = 2048

    def __post_init__(self) -> None:
        for name in (
            "max_files",
            "max_file_bytes",
            "max_total_bytes",
            "max_depth",
            "max_path_chars",
        ):
            _positive_integer(getattr(self, name), f"limits.{name}")


@dataclass(frozen=True)
class HistoricalEstateRoot:
    root_id: str
    revision: str
    logical_root: str
    license_id: str
    access: EstateAccess
    redistribution: EstateRedistribution
    physical_root: Path

    def __post_init__(self) -> None:
        if _NAMESPACE.fullmatch(_text(self.root_id, "estate_root.root_id", maximum=255)) is None:
            raise HistoricalEstateError("estate_root.root_id must be namespaced")
        _text(self.revision, "estate_root.revision", maximum=255)
        _safe_logical_path(self.logical_root, "estate_root.logical_root", maximum=1024)
        _text(self.license_id, "estate_root.license_id", maximum=255)
        if self.access not in {"public", "private", "restricted"}:
            raise HistoricalEstateError("estate_root.access is unsupported")
        if self.redistribution not in {"permitted", "prohibited", "unknown"}:
            raise HistoricalEstateError("estate_root.redistribution is unsupported")
        if not isinstance(self.physical_root, Path):
            raise HistoricalEstateError("estate_root.physical_root must be a pathlib.Path")

    def to_dict(self) -> dict[str, str]:
        return {
            "root_id": self.root_id,
            "revision": self.revision,
            "logical_root": self.logical_root,
            "license_id": self.license_id,
            "access": self.access,
            "redistribution": self.redistribution,
        }


def classify_historical_estate_file(logical_path: str) -> EstateClassification:
    """Classify one safe logical path by extension without parsing its contents."""

    checked = _safe_logical_path(logical_path, "logical_path")
    folded = checked.casefold()
    if folded.endswith(".tar.gz") or folded.endswith(".tgz"):
        return ("application/gzip", "archive", "review_required")
    suffix = Path(folded).suffix
    classifications: dict[str, EstateClassification] = {
        ".py": ("text/x-python", "source", "source_candidate"),
        ".json": ("application/json", "result", "artifact_candidate"),
        ".csv": ("text/csv", "result", "artifact_candidate"),
        ".npy": ("application/x-npy", "array", "artifact_candidate"),
        ".npz": ("application/x-npz", "array", "artifact_candidate"),
        ".mp4": ("video/mp4", "video", "artifact_candidate"),
        ".png": ("image/png", "image", "artifact_candidate"),
        ".jpg": ("image/jpeg", "image", "artifact_candidate"),
        ".jpeg": ("image/jpeg", "image", "artifact_candidate"),
        ".md": ("text/markdown", "narrative", "review_required"),
        ".txt": ("text/plain", "narrative", "review_required"),
        ".log": ("text/plain", "narrative", "review_required"),
        ".zip": ("application/zip", "archive", "review_required"),
    }
    return classifications.get(
        suffix, ("application/octet-stream", "unknown", "review_required")
    )


@dataclass(frozen=True)
class HistoricalEstateFile:
    logical_path: str
    byte_length: int
    sha256: str
    media_kind: str
    candidate_role: EstateCandidateRole
    import_disposition: EstateImportDisposition
    collection: str | None

    def __post_init__(self) -> None:
        checked = _safe_logical_path(self.logical_path, "estate_file.logical_path")
        if isinstance(self.byte_length, bool) or not isinstance(self.byte_length, int):
            raise HistoricalEstateError("estate_file.byte_length must be a non-negative integer")
        if self.byte_length < 0:
            raise HistoricalEstateError("estate_file.byte_length must be a non-negative integer")
        if not isinstance(self.sha256, str) or _SHA256.fullmatch(self.sha256) is None:
            raise HistoricalEstateError("estate_file.sha256 must be lowercase SHA-256")
        expected = classify_historical_estate_file(checked)
        actual = (self.media_kind, self.candidate_role, self.import_disposition)
        if actual != expected:
            raise HistoricalEstateError("estate_file classification differs from profile")
        expected_collection = checked.split("/", 1)[0] if "/" in checked else None
        if self.collection != expected_collection:
            raise HistoricalEstateError("estate_file.collection differs from logical path")

    def to_dict(self) -> dict[str, object]:
        return {
            "logical_path": self.logical_path,
            "byte_length": self.byte_length,
            "sha256": self.sha256,
            "media_kind": self.media_kind,
            "candidate_role": self.candidate_role,
            "import_disposition": self.import_disposition,
            "collection": self.collection,
        }


@dataclass(frozen=True)
class HistoricalEstateExclusion:
    logical_path: str
    entry_kind: EstateExcludedEntryKind
    reason: EstateExclusionReason

    def __post_init__(self) -> None:
        checked = _safe_logical_path(self.logical_path, "estate_exclusion.logical_path")
        name = checked.rsplit("/", 1)[-1]
        expected: tuple[EstateExcludedEntryKind, EstateExclusionReason] | None = None
        if name == ".DS_Store":
            expected = ("file", "platform_metadata")
        elif name.casefold().endswith(".pyc"):
            expected = ("file", "python_bytecode_cache")
        elif name == "__pycache__":
            expected = ("directory", "python_bytecode_cache")
        if expected is None or (self.entry_kind, self.reason) != expected:
            raise HistoricalEstateError("estate_exclusion differs from fixed profile")

    def to_dict(self) -> dict[str, str]:
        return {
            "logical_path": self.logical_path,
            "entry_kind": self.entry_kind,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class HistoricalEstateCollection:
    collection_id: str
    file_count: int
    total_bytes: int
    role_counts: tuple[tuple[EstateCandidateRole, int], ...]

    def __post_init__(self) -> None:
        _safe_logical_path(self.collection_id, "estate_collection.collection_id", maximum=255)
        if "/" in self.collection_id:
            raise HistoricalEstateError("estate_collection.collection_id must be top-level")
        if isinstance(self.file_count, bool) or not isinstance(self.file_count, int):
            raise HistoricalEstateError("estate_collection.file_count must be non-negative integer")
        if isinstance(self.total_bytes, bool) or not isinstance(self.total_bytes, int):
            raise HistoricalEstateError(
                "estate_collection.total_bytes must be non-negative integer"
            )
        if self.file_count < 0 or self.total_bytes < 0:
            raise HistoricalEstateError("estate_collection counts must be non-negative")
        if tuple(sorted(self.role_counts)) != self.role_counts:
            raise HistoricalEstateError("estate_collection.role_counts must be sorted")
        roles = [role for role, _count in self.role_counts]
        if len(roles) != len(set(roles)):
            raise HistoricalEstateError("estate_collection.role_counts must be unique")
        for role, count in self.role_counts:
            if role not in {
                "source",
                "result",
                "array",
                "video",
                "image",
                "narrative",
                "archive",
                "unknown",
            }:
                raise HistoricalEstateError("estate_collection contains unsupported role")
            if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
                raise HistoricalEstateError("estate_collection role count must be positive integer")
        if sum(count for _role, count in self.role_counts) != self.file_count:
            raise HistoricalEstateError("estate_collection role counts differ from file_count")

    def to_dict(self) -> dict[str, object]:
        return {
            "collection_id": self.collection_id,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "role_counts": [
                {"role": role, "count": count} for role, count in self.role_counts
            ],
        }


def _build_collections(
    files: tuple[HistoricalEstateFile, ...],
) -> tuple[HistoricalEstateCollection, ...]:
    grouped: dict[str, list[HistoricalEstateFile]] = {}
    for item in files:
        if item.collection is not None:
            grouped.setdefault(item.collection, []).append(item)
    result: list[HistoricalEstateCollection] = []
    for collection_id in sorted(grouped):
        members = grouped[collection_id]
        counts = Counter(item.candidate_role for item in members)
        result.append(
            HistoricalEstateCollection(
                collection_id=collection_id,
                file_count=len(members),
                total_bytes=sum(item.byte_length for item in members),
                role_counts=tuple(sorted(counts.items())),
            )
        )
    return tuple(result)


@dataclass(frozen=True)
class HistoricalEstateInventory:
    root: HistoricalEstateRoot
    files: tuple[HistoricalEstateFile, ...]
    exclusions: tuple[HistoricalEstateExclusion, ...]
    collections: tuple[HistoricalEstateCollection, ...]
    total_file_count: int
    excluded_entry_count: int
    total_bytes: int
    profile_id: str = HISTORICAL_ESTATE_INVENTORY_PROFILE_ID
    profile_version: str = HISTORICAL_ESTATE_INVENTORY_PROFILE_VERSION
    schema_version: str = "1.0"

    def __post_init__(self) -> None:
        if self.profile_id != HISTORICAL_ESTATE_INVENTORY_PROFILE_ID:
            raise HistoricalEstateError("estate_inventory.profile_id is unsupported")
        if self.profile_version != HISTORICAL_ESTATE_INVENTORY_PROFILE_VERSION:
            raise HistoricalEstateError("estate_inventory.profile_version is unsupported")
        if self.schema_version != "1.0":
            raise HistoricalEstateError("estate_inventory.schema_version is unsupported")
        paths = tuple(item.logical_path for item in self.files)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise HistoricalEstateError("estate_inventory.files must be unique and sorted")
        if len({path.casefold() for path in paths}) != len(paths):
            raise HistoricalEstateError("estate_inventory.files must not case-fold collide")
        exclusion_paths = tuple(item.logical_path for item in self.exclusions)
        if exclusion_paths != tuple(sorted(exclusion_paths)) or len(exclusion_paths) != len(
            set(exclusion_paths)
        ):
            raise HistoricalEstateError("estate_inventory.exclusions must be unique and sorted")
        all_paths = (*paths, *exclusion_paths)
        if len({path.casefold() for path in all_paths}) != len(all_paths):
            raise HistoricalEstateError("estate_inventory entries must not case-fold collide")
        if self.total_file_count != len(self.files):
            raise HistoricalEstateError("estate_inventory.total_file_count differs from files")
        if self.excluded_entry_count != len(self.exclusions):
            raise HistoricalEstateError(
                "estate_inventory.excluded_entry_count differs from exclusions"
            )
        if self.total_bytes != sum(item.byte_length for item in self.files):
            raise HistoricalEstateError("estate_inventory.total_bytes differs from files")
        if self.collections != _build_collections(self.files):
            raise HistoricalEstateError("estate_inventory.collections differ from files")

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "root": self.root.to_dict(),
            "files": [item.to_dict() for item in self.files],
            "exclusions": [item.to_dict() for item in self.exclusions],
            "collections": [item.to_dict() for item in self.collections],
            "total_file_count": self.total_file_count,
            "excluded_entry_count": self.excluded_entry_count,
            "total_bytes": self.total_bytes,
        }

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())

    def sha256(self) -> str:
        return hashlib.sha256(self.canonical_bytes()).hexdigest()


@dataclass(frozen=True)
class _EntryIdentity:
    device: int
    inode: int
    mode: int
    size: int
    modified_ns: int

    @classmethod
    def from_stat(cls, value: os.stat_result) -> _EntryIdentity:
        return cls(
            device=value.st_dev,
            inode=value.st_ino,
            mode=value.st_mode,
            size=value.st_size,
            modified_ns=value.st_mtime_ns,
        )


def _read_chunk(descriptor: int, length: int) -> bytes:
    return os.read(descriptor, length)


def _hash_regular_file(path: Path, expected: _EntryIdentity) -> str:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise HistoricalEstateError(
            f"failed to open historical estate file: {path.name}"
        ) from error
    digest = hashlib.sha256()
    total = 0
    try:
        opened = _EntryIdentity.from_stat(os.fstat(descriptor))
        if opened != expected or not stat.S_ISREG(opened.mode):
            raise HistoricalEstateError(f"historical estate file changed before read: {path.name}")
        while True:
            chunk = _read_chunk(descriptor, _CHUNK_BYTES)
            if not chunk:
                break
            digest.update(chunk)
            total += len(chunk)
        finished = _EntryIdentity.from_stat(os.fstat(descriptor))
    except OSError as error:
        raise HistoricalEstateError(
            f"failed to read historical estate file: {path.name}"
        ) from error
    finally:
        os.close(descriptor)
    try:
        after = _EntryIdentity.from_stat(path.stat(follow_symlinks=False))
    except OSError as error:
        raise HistoricalEstateError(f"historical estate file disappeared: {path.name}") from error
    if total != expected.size or finished != expected or after != expected:
        raise HistoricalEstateError(
            f"historical estate file changed while being inventoried: {path.name}"
        )
    return digest.hexdigest()


def _scan_directory(
    root: Path,
    directory: Path,
    relative_parts: tuple[str, ...],
    limits: HistoricalEstateLimits,
    files: list[HistoricalEstateFile],
    exclusions: list[HistoricalEstateExclusion],
    running_bytes: list[int],
) -> None:
    try:
        before = _EntryIdentity.from_stat(directory.stat(follow_symlinks=False))
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda entry: entry.name)
    except OSError as error:
        raise HistoricalEstateError("failed to enumerate historical estate directory") from error
    if not stat.S_ISDIR(before.mode):
        raise HistoricalEstateError("historical estate traversal encountered a non-directory")

    for entry in entries:
        logical_parts = (*relative_parts, entry.name)
        logical_path = "/".join(logical_parts)
        entry_path = Path(entry.path)
        _safe_logical_path(
            logical_path,
            "historical estate logical path",
            maximum=limits.max_path_chars,
        )
        if len(logical_parts) > limits.max_depth:
            raise HistoricalEstateError(
                f"historical estate path depth exceeds limit: {logical_path}"
            )
        try:
            if entry.is_symlink():
                raise HistoricalEstateError(
                    f"historical estate symlink is forbidden: {logical_path}"
                )
            # DirEntry.stat() is cached and reports zero for st_ino/st_dev on
            # Windows.  A fresh path stat preserves the identity fields that
            # os.fstat() returns after the file is opened, so the race guard is
            # both portable and meaningful.
            entry_stat = entry_path.stat(follow_symlinks=False)
        except OSError as error:
            raise HistoricalEstateError(
                f"failed to inspect historical estate entry: {logical_path}"
            ) from error
        try:
            entry_path.resolve(strict=True).relative_to(root)
        except (OSError, ValueError) as error:
            raise HistoricalEstateError(
                f"historical estate entry escapes the root: {logical_path}"
            ) from error
        exclusion: HistoricalEstateExclusion | None = None
        if entry.name == ".DS_Store" and stat.S_ISREG(entry_stat.st_mode):
            exclusion = HistoricalEstateExclusion(
                logical_path, "file", "platform_metadata"
            )
        elif entry.name.casefold().endswith(".pyc") and stat.S_ISREG(entry_stat.st_mode):
            exclusion = HistoricalEstateExclusion(
                logical_path, "file", "python_bytecode_cache"
            )
        elif entry.name == "__pycache__" and stat.S_ISDIR(entry_stat.st_mode):
            exclusion = HistoricalEstateExclusion(
                logical_path, "directory", "python_bytecode_cache"
            )
        if exclusion is not None:
            exclusions.append(exclusion)
            continue
        _reject_sensitive_path(logical_path)
        if stat.S_ISDIR(entry_stat.st_mode):
            _scan_directory(
                root,
                entry_path,
                logical_parts,
                limits,
                files,
                exclusions,
                running_bytes,
            )
            continue
        if not stat.S_ISREG(entry_stat.st_mode):
            raise HistoricalEstateError(
                f"historical estate contains a non-regular entry: {logical_path}"
            )
        if len(files) >= limits.max_files:
            raise HistoricalEstateError("historical estate file count exceeds limit")
        if entry_stat.st_size > limits.max_file_bytes:
            raise HistoricalEstateError(
                f"historical estate per-file byte limit exceeded: {logical_path}"
            )
        next_total = running_bytes[0] + entry_stat.st_size
        if next_total > limits.max_total_bytes:
            raise HistoricalEstateError("historical estate aggregate byte limit exceeded")
        expected = _EntryIdentity.from_stat(entry_stat)
        digest = _hash_regular_file(entry_path, expected)
        media_kind, role, disposition = classify_historical_estate_file(logical_path)
        files.append(
            HistoricalEstateFile(
                logical_path=logical_path,
                byte_length=entry_stat.st_size,
                sha256=digest,
                media_kind=media_kind,
                candidate_role=role,
                import_disposition=disposition,
                collection=logical_parts[0] if len(logical_parts) > 1 else None,
            )
        )
        running_bytes[0] = next_total

    try:
        after = _EntryIdentity.from_stat(directory.stat(follow_symlinks=False))
    except OSError as error:
        raise HistoricalEstateError(
            "historical estate directory disappeared during scan"
        ) from error
    if after != before:
        raise HistoricalEstateError("historical estate directory changed during scan")


_DEFAULT_LIMITS = HistoricalEstateLimits()


def inventory_historical_estate(
    root: HistoricalEstateRoot,
    limits: HistoricalEstateLimits = _DEFAULT_LIMITS,
) -> HistoricalEstateInventory:
    """Hash and classify one bounded estate without parsing or executing payloads."""

    if not isinstance(root, HistoricalEstateRoot):
        raise HistoricalEstateError("root must be HistoricalEstateRoot")
    if not isinstance(limits, HistoricalEstateLimits):
        raise HistoricalEstateError("limits must be HistoricalEstateLimits")
    physical_root = root.physical_root
    if not physical_root.is_absolute():
        raise HistoricalEstateError("estate_root.physical_root must be absolute")
    if physical_root.is_symlink():
        raise HistoricalEstateError("estate_root.physical_root must not be a symlink")
    try:
        resolved_root = physical_root.resolve(strict=True)
    except OSError as error:
        raise HistoricalEstateError("estate_root.physical_root does not exist") from error
    if not resolved_root.is_dir():
        raise HistoricalEstateError("estate_root.physical_root must be a directory")

    files: list[HistoricalEstateFile] = []
    exclusions: list[HistoricalEstateExclusion] = []
    running_bytes = [0]
    _scan_directory(
        resolved_root,
        resolved_root,
        (),
        limits,
        files,
        exclusions,
        running_bytes,
    )
    ordered = tuple(sorted(files, key=lambda item: item.logical_path))
    ordered_exclusions = tuple(sorted(exclusions, key=lambda item: item.logical_path))
    folded = [item.logical_path.casefold() for item in ordered]
    folded.extend(item.logical_path.casefold() for item in ordered_exclusions)
    if len(folded) != len(set(folded)):
        raise HistoricalEstateError("historical estate logical paths case-fold collide")
    collections = _build_collections(ordered)
    return HistoricalEstateInventory(
        root=root,
        files=ordered,
        exclusions=ordered_exclusions,
        collections=collections,
        total_file_count=len(ordered),
        excluded_entry_count=len(ordered_exclusions),
        total_bytes=running_bytes[0],
    )
