"""Deterministic run-candidate census over an immutable historical estate inventory."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from .historical_envelopes import (
    STATIC_PYTHON_EXTRACTOR_ID,
    STATIC_PYTHON_EXTRACTOR_VERSION,
    HistoricalEnvelopeError,
    HistoricalSourceAuthority,
    extract_static_python_experiment,
)
from .historical_estate import HistoricalEstateFile, HistoricalEstateInventory

HISTORICAL_CENSUS_PROFILE_ID = "org.flybrian.historical-census"
HISTORICAL_CENSUS_PROFILE_VERSION = "1.1"
MAX_CENSUS_JSON_BYTES = 64 * 1024 * 1024

FileDisposition = Literal[
    "run_evidence",
    "supporting_artifact",
    "source_evidence",
    "unresolved_result",
]

_RUN_CONTAINERS = frozenset(
    {
        "all_results",
        "multi_seed",
        "per_seed",
        "results",
        "runs",
        "seed_results",
        "sweep_results",
    }
)
_RUN_IDENTITY_FIELDS = frozenset(
    {
        "config",
        "config_name",
        "config_num",
        "experiment",
        "exp_idx",
        "label",
        "name",
        "params",
        "parameters",
        "random_seed",
        "seed",
    }
)
_RUN_OUTCOME_FIELDS = frozenset(
    {
        "all_pass",
        "combined_score",
        "contacts",
        "displacement_cm",
        "elevation",
        "elevation_FL",
        "elapsed_s",
        "forward_cm",
        "fwd_cm",
        "gate",
        "gates",
        "hCV",
        "height_cv",
        "metrics",
        "pitch_deg",
        "result",
        "runtime_s",
        "sim_ms",
        "sim_time_s",
        "speed_cm_s",
        "status",
        "tarsi",
        "tarsi_contact",
        "verdict",
        "wqs",
        "wqs_score",
    }
)


class HistoricalCensusError(ValueError):
    """Historical census evidence is incomplete, mutable, or contradictory."""


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _pointer_token(value: object) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def _looks_like_run_record(value: object) -> bool:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        return False
    fields = frozenset(value)
    return bool(fields & _RUN_IDENTITY_FIELDS) and bool(fields & _RUN_OUTCOME_FIELDS)


def _container_rows(value: object, pointer: str) -> list[tuple[str, dict[str, object]]]:
    rows: list[tuple[str, dict[str, object]]] = []
    if isinstance(value, list):
        for index, item in enumerate(value):
            if _looks_like_run_record(item):
                assert isinstance(item, dict)
                rows.append((f"{pointer}/{index}", item))
    elif isinstance(value, dict):
        for key in sorted(value):
            item = value[key]
            if _looks_like_run_record(item):
                assert isinstance(item, dict)
                rows.append((f"{pointer}/{_pointer_token(key)}", item))
    return rows


def _run_rows(value: object) -> list[tuple[str, dict[str, object]]]:
    if isinstance(value, list):
        return _container_rows(value, "")
    if not isinstance(value, dict):
        return []
    nested: list[tuple[str, dict[str, object]]] = []
    for key in sorted(_RUN_CONTAINERS & value.keys()):
        nested.extend(_container_rows(value[key], f"/{_pointer_token(key)}"))
    if nested:
        return nested
    if _looks_like_run_record(value):
        return [("", value)]
    return []


def _seed_text(record: dict[str, object]) -> str | None:
    value = record.get("seed", record.get("random_seed"))
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        return None
    return str(value)


@dataclass(frozen=True)
class HistoricalRunCandidate:
    candidate_id: str
    evidence_path: str
    evidence_sha256: str
    json_pointer: str
    observed_fields: tuple[str, ...]
    observed_seed: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_id": self.candidate_id,
            "evidence_path": self.evidence_path,
            "evidence_sha256": self.evidence_sha256,
            "json_pointer": self.json_pointer,
            "observed_fields": list(self.observed_fields),
            "observed_seed": self.observed_seed,
        }


@dataclass(frozen=True)
class HistoricalCensusFile:
    logical_path: str
    file_sha256: str
    candidate_role: str
    disposition: FileDisposition
    reason: str
    run_candidate_ids: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "logical_path": self.logical_path,
            "file_sha256": self.file_sha256,
            "candidate_role": self.candidate_role,
            "disposition": self.disposition,
            "reason": self.reason,
            "run_candidate_ids": list(self.run_candidate_ids),
        }


@dataclass(frozen=True)
class HistoricalSourceCandidate:
    indexed_path: str
    authority_path: str
    byte_length: int
    sha256: str
    domain: str
    cycle: int | None
    is_alias: bool
    extraction_status: Literal["extracted", "review_required"]
    option_count: int
    config_table_count: int
    config_entry_count: int
    extraction_dispositions: tuple[str, ...]
    review_reason: str | None

    def to_dict(self) -> dict[str, object]:
        return {
            "indexed_path": self.indexed_path,
            "authority_path": self.authority_path,
            "byte_length": self.byte_length,
            "sha256": self.sha256,
            "domain": self.domain,
            "cycle": self.cycle,
            "is_alias": self.is_alias,
            "extraction_status": self.extraction_status,
            "option_count": self.option_count,
            "config_table_count": self.config_table_count,
            "config_entry_count": self.config_entry_count,
            "extraction_dispositions": list(self.extraction_dispositions),
            "review_reason": self.review_reason,
        }


@dataclass(frozen=True)
class HistoricalCensus:
    inventory_root_id: str
    inventory_sha256: str
    inventory_file_count: int
    inventory_exclusion_count: int
    files: tuple[HistoricalCensusFile, ...]
    run_candidates: tuple[HistoricalRunCandidate, ...]
    source_index_sha256: str | None = None
    indexed_source_count: int = 0
    sources: tuple[HistoricalSourceCandidate, ...] = ()

    def __post_init__(self) -> None:
        paths = tuple(item.logical_path for item in self.files)
        if paths != tuple(sorted(set(paths))):
            raise HistoricalCensusError("census files must be unique and sorted")
        if len(paths) != self.inventory_file_count:
            raise HistoricalCensusError("census does not reconcile the inventory file count")
        candidate_ids = tuple(item.candidate_id for item in self.run_candidates)
        candidate_order = tuple(
            (item.evidence_path, item.json_pointer) for item in self.run_candidates
        )
        if len(candidate_ids) != len(set(candidate_ids)) or candidate_order != tuple(
            sorted(candidate_order)
        ):
            raise HistoricalCensusError("run candidates must be unique and sorted")
        referenced = tuple(
            candidate_id for item in self.files for candidate_id in item.run_candidate_ids
        )
        if set(referenced) != set(candidate_ids) or len(referenced) != len(candidate_ids):
            raise HistoricalCensusError("census file-to-run references do not reconcile")
        source_paths = tuple(item.indexed_path for item in self.sources)
        if source_paths != tuple(sorted(set(source_paths))):
            raise HistoricalCensusError("indexed sources must be unique and sorted")
        if len(source_paths) != self.indexed_source_count:
            raise HistoricalCensusError("census does not reconcile the indexed source count")
        if bool(self.source_index_sha256) != bool(self.sources):
            raise HistoricalCensusError("source index identity and source records must coexist")

    @property
    def reconciled_file_count(self) -> int:
        return len(self.files)

    @property
    def sha256(self) -> str:
        return _digest(self.to_dict(include_sha256=False))

    def to_dict(self, *, include_sha256: bool = True) -> dict[str, object]:
        dispositions: dict[str, int] = {}
        for item in self.files:
            dispositions[item.disposition] = dispositions.get(item.disposition, 0) + 1
        result: dict[str, object] = {
            "profile_id": HISTORICAL_CENSUS_PROFILE_ID,
            "profile_version": HISTORICAL_CENSUS_PROFILE_VERSION,
            "inventory_root_id": self.inventory_root_id,
            "inventory_sha256": self.inventory_sha256,
            "inventory_file_count": self.inventory_file_count,
            "inventory_exclusion_count": self.inventory_exclusion_count,
            "reconciled_file_count": self.reconciled_file_count,
            "run_candidate_count": len(self.run_candidates),
            "source_index_sha256": self.source_index_sha256,
            "indexed_source_count": self.indexed_source_count,
            "disposition_counts": dict(sorted(dispositions.items())),
            "files": [item.to_dict() for item in self.files],
            "run_candidates": [item.to_dict() for item in self.run_candidates],
            "sources": [item.to_dict() for item in self.sources],
        }
        if include_sha256:
            result["sha256"] = self.sha256
        return result

    def canonical_bytes(self) -> bytes:
        return _canonical_bytes(self.to_dict())


def _verified_json_bytes(item: HistoricalEstateFile, evidence_root: Path) -> bytes:
    path = evidence_root.joinpath(*item.logical_path.split("/"))
    try:
        data = path.read_bytes()
    except OSError as error:
        raise HistoricalCensusError(
            f"failed to read inventoried evidence: {item.logical_path}"
        ) from error
    if len(data) != item.byte_length or hashlib.sha256(data).hexdigest() != item.sha256:
        raise HistoricalCensusError(
            f"historical evidence changed after inventory: {item.logical_path}"
        )
    return data


def _candidate(
    item: HistoricalEstateFile,
    pointer: str,
    record: dict[str, object],
) -> HistoricalRunCandidate:
    identity = hashlib.sha256(f"{item.logical_path}\0{item.sha256}\0{pointer}".encode()).hexdigest()
    return HistoricalRunCandidate(
        candidate_id=f"org.flybrian.run-candidate.{identity}",
        evidence_path=item.logical_path,
        evidence_sha256=item.sha256,
        json_pointer=pointer,
        observed_fields=tuple(sorted(record)),
        observed_seed=_seed_text(record),
    )


def _indexed_sources(
    repository_root: Path,
    source_index_path: Path,
) -> tuple[str, tuple[HistoricalSourceCandidate, ...]]:
    try:
        resolved_repository = repository_root.resolve(strict=True)
        resolved_index = source_index_path.resolve(strict=True)
    except OSError as error:
        raise HistoricalCensusError("historical source index is unavailable") from error
    if not resolved_index.is_relative_to(resolved_repository):
        raise HistoricalCensusError("historical source index escapes repository root")
    index_bytes = resolved_index.read_bytes()
    try:
        index = json.loads(index_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HistoricalCensusError("historical source index is not valid JSON") from error
    if not isinstance(index, dict) or not isinstance(index.get("scripts"), list):
        raise HistoricalCensusError("historical source index has no scripts array")

    sources: list[HistoricalSourceCandidate] = []
    for position, raw in enumerate(index["scripts"]):
        if not isinstance(raw, dict):
            raise HistoricalCensusError(f"source index scripts[{position}] must be an object")
        indexed_path = raw.get("path")
        domain = raw.get("domain")
        cycle = raw.get("cycle")
        if not isinstance(indexed_path, str) or not indexed_path:
            raise HistoricalCensusError(f"source index scripts[{position}].path is invalid")
        if not isinstance(domain, str) or not domain:
            raise HistoricalCensusError(f"source index scripts[{position}].domain is invalid")
        if cycle is not None and (isinstance(cycle, bool) or not isinstance(cycle, int)):
            raise HistoricalCensusError(f"source index scripts[{position}].cycle is invalid")
        indexed_source = resolved_repository.joinpath(*indexed_path.split("/"))
        try:
            resolved_source = indexed_source.resolve(strict=True)
        except OSError as error:
            raise HistoricalCensusError(
                f"indexed historical source is unavailable: {indexed_path}"
            ) from error
        if not resolved_source.is_relative_to(resolved_repository):
            raise HistoricalCensusError(f"indexed source escapes repository: {indexed_path}")
        authority_path = resolved_source.relative_to(resolved_repository).as_posix()
        source_bytes = resolved_source.read_bytes()
        source_sha256 = hashlib.sha256(source_bytes).hexdigest()
        authority = HistoricalSourceAuthority(
            repository="flybrian-serve",
            revision="inventory-bound-working-snapshot",
            logical_path=authority_path,
            byte_length=len(source_bytes),
            sha256=source_sha256,
            license_id="NOASSERTION",
            access="private",
            redistribution="unknown",
            extractor_id=STATIC_PYTHON_EXTRACTOR_ID,
            extractor_version=STATIC_PYTHON_EXTRACTOR_VERSION,
        )
        try:
            extraction = extract_static_python_experiment(source_bytes, authority)
        except HistoricalEnvelopeError as error:
            sources.append(
                HistoricalSourceCandidate(
                    indexed_path=indexed_path,
                    authority_path=authority_path,
                    byte_length=len(source_bytes),
                    sha256=source_sha256,
                    domain=domain,
                    cycle=cycle,
                    is_alias=indexed_path != authority_path,
                    extraction_status="review_required",
                    option_count=0,
                    config_table_count=0,
                    config_entry_count=0,
                    extraction_dispositions=(),
                    review_reason=str(error),
                )
            )
            continue
        sources.append(
            HistoricalSourceCandidate(
                indexed_path=indexed_path,
                authority_path=authority_path,
                byte_length=len(source_bytes),
                sha256=source_sha256,
                domain=domain,
                cycle=cycle,
                is_alias=indexed_path != authority_path,
                extraction_status="extracted",
                option_count=len(extraction.options),
                config_table_count=len(extraction.config_tables),
                config_entry_count=sum(table.entry_count for table in extraction.config_tables),
                extraction_dispositions=tuple(
                    disposition.code for disposition in extraction.dispositions
                ),
                review_reason=None,
            )
        )
    sources.sort(key=lambda item: item.indexed_path)
    if len(sources) != len({item.indexed_path for item in sources}):
        raise HistoricalCensusError("historical source index contains duplicate paths")
    return hashlib.sha256(index_bytes).hexdigest(), tuple(sources)


def build_historical_census(
    inventory: HistoricalEstateInventory,
    *,
    evidence_root: Path,
    repository_root: Path | None = None,
    source_index_path: Path | None = None,
) -> HistoricalCensus:
    """Reconcile every inventoried file without inferring scientific configuration."""

    if not isinstance(inventory, HistoricalEstateInventory):
        raise HistoricalCensusError("inventory must be HistoricalEstateInventory")
    if not isinstance(evidence_root, Path) or not evidence_root.is_absolute():
        raise HistoricalCensusError("evidence_root must be an absolute pathlib.Path")
    try:
        resolved_evidence = evidence_root.resolve(strict=True)
        resolved_inventory = inventory.root.physical_root.resolve(strict=True)
    except OSError as error:
        raise HistoricalCensusError("historical evidence root is unavailable") from error
    if resolved_evidence != resolved_inventory:
        raise HistoricalCensusError("evidence_root differs from inventory authority")
    if (repository_root is None) != (source_index_path is None):
        raise HistoricalCensusError(
            "repository_root and source_index_path must be supplied together"
        )

    files: list[HistoricalCensusFile] = []
    candidates: list[HistoricalRunCandidate] = []
    for item in inventory.files:
        disposition: FileDisposition = "supporting_artifact"
        reason = "The file is retained as supporting experiment evidence."
        item_candidates: list[HistoricalRunCandidate] = []
        if item.candidate_role == "source":
            disposition = "source_evidence"
            reason = "The output estate contains a retained source artifact."
        elif item.candidate_role == "result":
            disposition = "unresolved_result"
            reason = (
                "The result file contains no explicit run-record structure in census profile 1.0."
            )
            if item.logical_path.casefold().endswith(".json"):
                if item.byte_length > MAX_CENSUS_JSON_BYTES:
                    reason = "The JSON result exceeds the census parser byte boundary."
                else:
                    data = _verified_json_bytes(item, resolved_evidence)
                    try:
                        parsed = json.loads(data)
                    except (UnicodeDecodeError, json.JSONDecodeError):
                        reason = "The inventoried result is not valid UTF-8 JSON."
                    else:
                        rows = _run_rows(parsed)
                        item_candidates = [
                            _candidate(item, pointer, record) for pointer, record in rows
                        ]
                        if item_candidates:
                            disposition = "run_evidence"
                            reason = (
                                "The JSON contains explicit result records with both run identity "
                                "and scientific outcome fields."
                            )
        item_candidates.sort(key=lambda candidate: candidate.json_pointer)
        candidates.extend(item_candidates)
        files.append(
            HistoricalCensusFile(
                logical_path=item.logical_path,
                file_sha256=item.sha256,
                candidate_role=item.candidate_role,
                disposition=disposition,
                reason=reason,
                run_candidate_ids=tuple(candidate.candidate_id for candidate in item_candidates),
            )
        )
    candidates.sort(key=lambda candidate: (candidate.evidence_path, candidate.json_pointer))
    source_index_sha256: str | None = None
    sources: tuple[HistoricalSourceCandidate, ...] = ()
    if repository_root is not None and source_index_path is not None:
        source_index_sha256, sources = _indexed_sources(repository_root, source_index_path)
    return HistoricalCensus(
        inventory_root_id=inventory.root.root_id,
        inventory_sha256=inventory.sha256(),
        inventory_file_count=inventory.total_file_count,
        inventory_exclusion_count=inventory.excluded_entry_count,
        files=tuple(files),
        run_candidates=tuple(candidates),
        source_index_sha256=source_index_sha256,
        indexed_source_count=len(sources),
        sources=sources,
    )
