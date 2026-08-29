"""Normalize the retained C91-C134 NumPy-rate writer collections.

The historical research scripts are the scientific authority.  This module
does not translate their dynamics.  It binds each exact writer to the exact
JSON collection it wrote, expands the collection into physical run evidence,
and separates configuration from observed outcomes.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import tarfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .historical_envelopes import (
    STATIC_PYTHON_EXTRACTOR_ID,
    STATIC_PYTHON_EXTRACTOR_VERSION,
    HistoricalSourceAuthority,
)
from .historical_normalization import (
    HistoricalArtifactReference,
    HistoricalClaim,
    HistoricalExecutionRecipe,
    HistoricalInputReference,
    HistoricalNormalizationBundle,
    HistoricalNormalizationError,
    HistoricalRunOccurrence,
    NormalizedExperimentDefinition,
    canonical_json_bytes,
    canonical_sha256,
)
from .historical_standing import C148_PHASE0_INPUTS

LEGACY_RATE_PROFILE_ID = "org.flybrian.legacy-rate-writer-collection"
LEGACY_RATE_PROFILE_VERSION = "1.0"

_CYCLE_SOURCE = re.compile(r"cycle(?P<cycle>9[1-9]|1[01][0-9]|12[0-9]|13[0-4])(?:[^0-9]|$)")
_RESULT_CONTAINERS = (
    "all_results",
    "per_seed",
    "results",
    "runs",
    "seed_results",
    "sweep_results",
    "part_a",
    "part_b",
)
_IDENTITY_FIELDS = frozenset(
    {
        "adapt",
        "amp",
        "approach",
        "config",
        "config_name",
        "damping_gain",
        "dof_set",
        "experiment",
        "gain",
        "inh_gain",
        "k_z_damp",
        "kwargs",
        "label",
        "module_gain",
        "name",
        "params",
        "parameters",
        "part",
        "power",
        "random_seed",
        "reflex",
        "scope",
        "seed",
        "self_gain",
        "source",
        "strength",
        "tau_scale",
        "test",
        "xinh_gain",
    }
)
_OUTCOME_FIELDS = frozenset(
    {
        "all_pass",
        "at_7plus",
        "at_8plus",
        "at_9plus",
        "at_10plus",
        "clq",
        "combined_score",
        "contacts",
        "df",
        "displacement_cm",
        "elev",
        "elev_x_fwd",
        "elevation",
        "fails",
        "forward_cm",
        "fwd",
        "fwd_cm",
        "gate",
        "gate_pass",
        "hcv",
        "height_cv",
        "jtf_primary",
        "loco_gate",
        "mean_clq",
        "mean_df",
        "mean_elev",
        "mean_fwd",
        "mean_hcv",
        "mean_jtf",
        "mean_wqs",
        "metrics",
        "n_gate",
        "n_legs_stepping",
        "n_total",
        "n_total_strides",
        "per_leg_jtf",
        "per_metric",
        "pitch",
        "roll",
        "rom_util",
        "speed_cm_s",
        "status",
        "strides",
        "tarsi",
        "verdict",
        "warns",
        "wqs",
        "wqs_v1",
        "wqs_v2",
        "yaw_zero",
    }
)
_OPERATIONAL_FIELDS = frozenset({"date", "elapsed_s", "runtime_s", "time_s"})
_SUMMARY_FIELDS = frozenset(
    {
        "config_summaries",
        "summaries",
        "multiseed",
        "multiseed_report",
    }
)


class _DecimalToken(str):
    """A JSON decimal token retained as exact source text."""


@dataclass(frozen=True)
class LegacyRateCollection:
    collection_id: str
    cycle: int
    source_path: str
    source_sha256: str
    source_byte_length: int
    result_path: str
    result_sha256: str
    result_byte_length: int
    duration_ms: int
    seeds: tuple[int, ...]
    default_seed: int | None
    archive_member: str | None = None
    archive_sha256: str | None = None
    archive_byte_length: int | None = None

    @property
    def evidence_locator(self) -> str:
        if self.archive_member is None:
            return self.result_path
        return f"{self.result_path}!{self.archive_member}"

    def to_dict(self) -> dict[str, object]:
        return {
            "collection_id": self.collection_id,
            "cycle": self.cycle,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "source_byte_length": self.source_byte_length,
            "result_path": self.result_path,
            "result_sha256": self.result_sha256,
            "result_byte_length": self.result_byte_length,
            "duration_ms": self.duration_ms,
            "seeds": list(self.seeds),
            "default_seed": self.default_seed,
            "archive_member": self.archive_member,
            "archive_sha256": self.archive_sha256,
            "archive_byte_length": self.archive_byte_length,
        }


@dataclass(frozen=True)
class LegacyRateRunEvidence:
    pointer: str
    selector: str
    seed: int | None
    duration_ms: int | None
    parameters: Mapping[str, object]
    result: Mapping[str, object]


@dataclass(frozen=True)
class LegacyRateCollectionExpansion:
    collection: LegacyRateCollection
    runs: tuple[LegacyRateRunEvidence, ...]
    declared_run_count: int | None
    unresolved_run_count: int


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(data: bytes) -> object:
    return json.loads(data.decode("utf-8"), parse_float=_DecimalToken)


def _safe_relative(path: PurePosixPath) -> str | None:
    text = path.as_posix()
    if text.startswith("/") or ".." in path.parts:
        return None
    return text[2:] if text.startswith("./") else text


def _eval_path(node: ast.AST, names: Mapping[str, PurePosixPath]) -> PurePosixPath | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return PurePosixPath(node.value)
    if isinstance(node, ast.Name):
        return names.get(node.id)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "Path"
        and len(node.args) == 1
    ):
        return _eval_path(node.args[0], names)
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "join"
        and isinstance(node.func.value, ast.Attribute)
        and node.func.value.attr == "path"
        and isinstance(node.func.value.value, ast.Name)
        and node.func.value.value.id == "os"
    ):
        parts = [_eval_path(argument, names) for argument in node.args]
        if parts and all(part is not None for part in parts):
            result = parts[0]
            assert result is not None
            for part in parts[1:]:
                assert part is not None
                result /= part
            return result
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        left = _eval_path(node.left, names)
        right = _eval_path(node.right, names)
        if left is not None and right is not None:
            return left / right
    return None


def _static_paths(tree: ast.AST) -> dict[str, PurePosixPath]:
    names: dict[str, PurePosixPath] = {"PROJECT": PurePosixPath(".")}
    assignments = [node for node in ast.walk(tree) if isinstance(node, ast.Assign)]
    for _ in range(4):
        changed = False
        for node in assignments:
            value = _eval_path(node.value, names)
            if value is None:
                continue
            for target in node.targets:
                if isinstance(target, ast.Name) and names.get(target.id) != value:
                    names[target.id] = value
                    changed = True
        if not changed:
            break
    return names


def _written_json_paths(tree: ast.AST) -> tuple[str, ...]:
    names = _static_paths(tree)
    paths: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id != "open" or not node.args:
            continue
        mode: object = None
        if len(node.args) > 1 and isinstance(node.args[1], ast.Constant):
            mode = node.args[1].value
        for keyword in node.keywords:
            if keyword.arg == "mode" and isinstance(keyword.value, ast.Constant):
                mode = keyword.value.value
        if not isinstance(mode, str) or not any(flag in mode for flag in ("w", "a", "x")):
            continue
        path = _eval_path(node.args[0], names)
        if path is None or path.suffix.lower() != ".json":
            continue
        safe = _safe_relative(path)
        if safe is not None and safe.startswith("output/"):
            paths.add(safe)
    return tuple(sorted(paths))


def _literal_integer_sequence(tree: ast.AST, name: str) -> tuple[int, ...]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name) and target.id == name for target in node.targets):
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            continue
        values: list[int] = []
        for item in node.value.elts:
            if not isinstance(item, ast.Constant) or isinstance(item.value, bool):
                break
            if not isinstance(item.value, int):
                break
            values.append(item.value)
        else:
            return tuple(values)
    return ()


def _imported_integer_sequence(
    tree: ast.AST,
    *,
    repository_root: Path,
    name: str,
) -> tuple[int, ...]:
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        if not any(alias.name == name for alias in node.names):
            continue
        module_path = repository_root / f"{node.module.replace('.', '/')}.py"
        if not module_path.is_file():
            continue
        imported_tree = ast.parse(module_path.read_bytes(), filename=module_path.as_posix())
        values = _literal_integer_sequence(imported_tree, name)
        if values:
            return values
    return ()


def _duration_ms(tree: ast.AST) -> int | None:
    candidates: list[int] = []
    names = {"sim_ms", "SIM_MS", "sim_time_ms", "SIM_TIME_MS"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            targets = [target.id for target in node.targets if isinstance(target, ast.Name)]
            value = node.value
        elif isinstance(node, ast.arg):
            continue
        else:
            continue
        if not names.intersection(targets) or not isinstance(value, ast.Constant):
            continue
        if isinstance(value.value, bool) or not isinstance(value.value, (int, float)):
            continue
        milliseconds = int(value.value)
        if milliseconds > 0 and float(milliseconds) == float(value.value):
            candidates.append(milliseconds)
    if 3_000 in candidates:
        return 3_000
    unique = sorted(set(candidates))
    return unique[0] if len(unique) == 1 else None


def _default_seed(tree: ast.AST) -> int | None:
    values: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        positional = [*node.args.posonlyargs, *node.args.args]
        defaults = [None] * (len(positional) - len(node.args.defaults)) + list(node.args.defaults)
        for argument, default in zip(positional, defaults, strict=True):
            if argument.arg not in {"seed", "random_seed"} or default is None:
                continue
            if (
                isinstance(default, ast.Constant)
                and isinstance(default.value, int)
                and not isinstance(default.value, bool)
            ):
                values.add(default.value)
        for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults, strict=True):
            if argument.arg not in {"seed", "random_seed"} or default is None:
                continue
            if (
                isinstance(default, ast.Constant)
                and isinstance(default.value, int)
                and not isinstance(default.value, bool)
            ):
                values.add(default.value)
    return next(iter(values)) if len(values) == 1 else None


def _result_bytes(
    repository_root: Path, result_path: str
) -> tuple[bytes, str, str | None, str | None, int | None]:
    direct = repository_root / result_path
    if direct.is_file():
        data = direct.read_bytes()
        return data, result_path, None, None, None
    result = PurePosixPath(result_path)
    if len(result.parts) < 3 or result.parts[0] != "output":
        raise HistoricalNormalizationError(f"missing legacy result {result_path}")
    directory = result.parts[1]
    archive_path = repository_root / "output" / f"{directory}.tar.gz"
    member = f"{directory}/{result.name}"
    if not archive_path.is_file():
        raise HistoricalNormalizationError(f"missing legacy result {result_path}")
    archive_bytes = archive_path.read_bytes()
    with tarfile.open(archive_path, "r:gz") as archive:
        try:
            extracted = archive.extractfile(member)
        except KeyError as error:
            raise HistoricalNormalizationError(
                f"missing legacy result member {archive_path.name}!{member}"
            ) from error
        if extracted is None:
            raise HistoricalNormalizationError(
                f"missing legacy result member {archive_path.name}!{member}"
            )
        data = extracted.read()
    return data, f"output/{archive_path.name}", member, _sha256(archive_bytes), len(archive_bytes)


def discover_legacy_rate_collections(
    *, repository_root: Path
) -> tuple[LegacyRateCollection, ...]:
    """Discover exact C91-C134 source/result bindings declared by writer code."""
    collections: list[LegacyRateCollection] = []
    seen_results: set[str] = set()
    for source_path in sorted((repository_root / "scripts").rglob("cycle*.py")):
        if source_path.is_symlink():
            continue
        logical_source = source_path.relative_to(repository_root).as_posix()
        match = _CYCLE_SOURCE.search(source_path.name)
        if match is None:
            continue
        cycle = int(match.group("cycle"))
        source_bytes = source_path.read_bytes()
        tree = ast.parse(source_bytes, filename=logical_source)
        seeds = _literal_integer_sequence(tree, "SEEDS") or _imported_integer_sequence(
            tree,
            repository_root=repository_root,
            name="SEEDS",
        )
        duration = _duration_ms(tree)
        default_seed = _default_seed(tree)
        for declared_result in _written_json_paths(tree):
            if declared_result in seen_results:
                raise HistoricalNormalizationError(
                    f"legacy result has multiple writer authorities: {declared_result}"
                )
            try:
                data, evidence_path, member, archive_sha, archive_size = _result_bytes(
                    repository_root, declared_result
                )
            except HistoricalNormalizationError:
                continue
            if not _contains_run_evidence(_json(data)):
                continue
            seen_results.add(declared_result)
            slug = PurePosixPath(declared_result).parent.name.replace("_", "-")
            filename_slug = PurePosixPath(declared_result).stem.replace("_", "-")
            collection_id = f"{slug}-{filename_slug}"
            collections.append(
                LegacyRateCollection(
                    collection_id=collection_id,
                    cycle=cycle,
                    source_path=logical_source,
                    source_sha256=_sha256(source_bytes),
                    source_byte_length=len(source_bytes),
                    result_path=evidence_path,
                    result_sha256=_sha256(data),
                    result_byte_length=len(data),
                    duration_ms=duration or 3_000,
                    seeds=seeds,
                    default_seed=default_seed,
                    archive_member=member,
                    archive_sha256=archive_sha,
                    archive_byte_length=archive_size,
                )
            )
    ids = tuple(item.collection_id for item in collections)
    if len(ids) != len(set(ids)):
        raise HistoricalNormalizationError("legacy collection IDs are not unique")
    return tuple(sorted(collections, key=lambda item: item.collection_id))


def _is_mapping(value: object) -> bool:
    return isinstance(value, dict) and all(isinstance(key, str) for key in value)


def _is_run_row(value: object) -> bool:
    if not _is_mapping(value):
        return False
    assert isinstance(value, dict)
    fields = frozenset(value)
    if (
        "seed" not in fields
        and "random_seed" not in fields
        and not {"results", "per_seed"}.intersection(fields)
        and (
            "n_seeds" in fields
            or (
                any(field.startswith("mean_") for field in fields)
                and not {"fwd", "elev", "wqs", "wqs_v2", "jtf_primary"}.intersection(fields)
            )
        )
    ):
        return False
    parameter_fields = fields - _OUTCOME_FIELDS - _OPERATIONAL_FIELDS
    return bool(parameter_fields) and bool(fields & _OUTCOME_FIELDS)


def _contains_run_evidence(value: object) -> bool:
    if isinstance(value, list):
        return any(_is_run_row(item) or _contains_run_evidence(item) for item in value)
    if not _is_mapping(value):
        return False
    assert isinstance(value, dict)
    if _is_run_row(value):
        return True
    return any(
        key in _RESULT_CONTAINERS
        or key == "config_summaries"
        or key.endswith("_per_seed")
        or key.endswith("_results")
        for key in value
    ) or any(_contains_run_evidence(item) for item in value.values())


def _materialize(value: object) -> object:
    if isinstance(value, _DecimalToken):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _materialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_materialize(item) for item in value]
    return value


def _seed(value: object) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise HistoricalNormalizationError("legacy run seed must be an integer or null")
    return value


def _split_row(row: Mapping[str, object]) -> tuple[dict[str, object], dict[str, object]]:
    parameters = {
        key: _materialize(value)
        for key, value in row.items()
        if key not in _OUTCOME_FIELDS
        and key not in _OPERATIONAL_FIELDS
        and key not in {"seed", "random_seed"}
        and not key.endswith("_per_seed")
    }
    result = {
        key: _materialize(value)
        for key, value in row.items()
        if key not in _OPERATIONAL_FIELDS
    }
    return parameters, result


def _row_duration_ms(row: Mapping[str, object]) -> int | None:
    for name in ("sim_ms", "sim_time_ms", "duration_ms"):
        value = row.get(name)
        if isinstance(value, bool):
            continue
        if isinstance(value, int) and value > 0:
            return value
        if isinstance(value, _DecimalToken):
            try:
                parsed = float(value)
            except ValueError:
                continue
            integer = int(parsed)
            if integer > 0 and float(integer) == parsed:
                return integer
    return None


def _direct_rows(value: object, pointer: str) -> list[LegacyRateRunEvidence]:
    rows: list[LegacyRateRunEvidence] = []
    if not isinstance(value, list):
        return rows
    for index, item in enumerate(value):
        child_pointer = f"{pointer}/{index}"
        if not _is_mapping(item):
            continue
        assert isinstance(item, dict)
        nested = item.get("results", item.get("per_seed"))
        if isinstance(nested, list) and any(_is_run_row(child) for child in nested):
            parent = {
                key: _materialize(entry)
                for key, entry in item.items()
                if key not in {"results", "per_seed"}
                and key not in _OUTCOME_FIELDS
                and key not in _OPERATIONAL_FIELDS
            }
            nested_name = "results" if "results" in item else "per_seed"
            for child_index, child in enumerate(nested):
                if not _is_mapping(child):
                    continue
                assert isinstance(child, dict)
                parameters, result = _split_row(child)
                parameters = {**parent, **parameters}
                rows.append(
                    LegacyRateRunEvidence(
                        pointer=f"{child_pointer}/{nested_name}/{child_index}",
                        selector=f"{pointer}/{index}:{child_index}",
                        seed=_seed(child.get("seed", child.get("random_seed"))),
                        duration_ms=_row_duration_ms(child) or _row_duration_ms(item),
                        parameters=parameters,
                        result=result,
                    )
                )
        elif _is_run_row(item):
            parameters, result = _split_row(item)
            rows.append(
                LegacyRateRunEvidence(
                    pointer=child_pointer,
                    selector=f"{pointer}/{index}",
                    seed=_seed(item.get("seed", item.get("random_seed"))),
                    duration_ms=_row_duration_ms(item),
                    parameters=parameters,
                    result=result,
                )
            )
    return rows


def _summary_rows(
    summaries: object,
    *,
    pointer: str,
    seeds: Sequence[int],
) -> list[LegacyRateRunEvidence]:
    if not isinstance(summaries, list) or not seeds:
        return []
    rows: list[LegacyRateRunEvidence] = []
    for summary_index, summary in enumerate(summaries):
        if not _is_mapping(summary):
            continue
        assert isinstance(summary, dict)
        vectors = {
            key: value
            for key, value in summary.items()
            if key.endswith("_per_seed") and isinstance(value, list) and len(value) == len(seeds)
        }
        if not vectors:
            continue
        parameters = {
            key: _materialize(value)
            for key, value in summary.items()
            if key not in vectors
            and key not in _OUTCOME_FIELDS
            and key not in _OPERATIONAL_FIELDS
        }
        for seed_index, seed in enumerate(seeds):
            result = {
                key.removesuffix("_per_seed"): _materialize(values[seed_index])
                for key, values in sorted(vectors.items())
            }
            result.update(
                {
                    "label": _materialize(summary.get("label", summary.get("config"))),
                    "seed": seed,
                }
            )
            rows.append(
                LegacyRateRunEvidence(
                    pointer=f"{pointer}/{summary_index}/seed/{seed_index}",
                    selector=f"{pointer}/{summary_index}:{seed_index}",
                    seed=seed,
                    duration_ms=_row_duration_ms(summary),
                    parameters=parameters,
                    result=result,
                )
            )
    return rows


def _named_summary_rows(
    root: Mapping[str, object], *, seeds: Sequence[int]
) -> list[LegacyRateRunEvidence]:
    if not seeds:
        return []
    rows: list[LegacyRateRunEvidence] = []
    for name, summary in root.items():
        if name in {"metadata", *_SUMMARY_FIELDS} or not isinstance(summary, dict):
            continue
        vectors = {
            key: value
            for key, value in summary.items()
            if key.endswith("_per_seed")
            and isinstance(value, list)
            and len(value) == len(seeds)
        }
        if not vectors:
            continue
        parameters: dict[str, object] = {"label": name}
        metadata = root.get("metadata")
        if isinstance(metadata, dict):
            named_config = metadata.get(f"{name.removesuffix('_combo')}_config")
            if isinstance(named_config, dict):
                parameters["configuration"] = _materialize(named_config)
        for seed_index, seed in enumerate(seeds):
            result = {
                key.removesuffix("_per_seed"): _materialize(values[seed_index])
                for key, values in sorted(vectors.items())
            }
            result.update({"label": name, "seed": seed})
            rows.append(
                LegacyRateRunEvidence(
                    pointer=f"/{name}/seed/{seed_index}",
                    selector=f"/{name}:{seed_index}",
                    seed=seed,
                    duration_ms=_row_duration_ms(summary),
                    parameters=parameters,
                    result=result,
                )
            )
    return rows


def _baseline_rows(
    root: Mapping[str, object], *, seeds: Sequence[int]
) -> list[LegacyRateRunEvidence]:
    if not seeds:
        return []
    vectors = {
        key: value
        for key, value in root.items()
        if key.startswith("baseline_")
        and key.endswith("_per_seed")
        and isinstance(value, list)
        and len(value) == len(seeds)
    }
    if not vectors:
        return []
    rows: list[LegacyRateRunEvidence] = []
    for index, seed in enumerate(seeds):
        result = {
            key.removeprefix("baseline_").removesuffix("_per_seed"): _materialize(value[index])
            for key, value in sorted(vectors.items())
        }
        result.update({"label": "baseline", "seed": seed})
        rows.append(
            LegacyRateRunEvidence(
                pointer=f"/baseline/seed/{index}",
                selector=f"/baseline:{index}",
                seed=seed,
                duration_ms=_row_duration_ms(root),
                parameters={"label": "baseline"},
                result=result,
            )
        )
    return rows


def _declared_grid_rows(
    root: Mapping[str, object],
    *,
    seeds: Sequence[int],
    existing: Sequence[LegacyRateRunEvidence],
) -> list[LegacyRateRunEvidence]:
    """Recover a complete two-axis grid when the aggregate declares it exactly.

    C133 phase 1 crashed while writing its full result aggregate.  Its repaired
    aggregate preserves the exact run count, seed vector, named DOF-set mapping,
    gain vector, and ten per-config scientific summaries.  The writer source
    contains the matching nested loops.  This structural rule recovers the
    missing configurations without inventing outcomes.
    """
    metadata = root.get("metadata")
    if not isinstance(metadata, dict) or not seeds:
        return []
    declared = metadata.get("total_runs")
    dof_sets = metadata.get("dof_sets")
    gains = metadata.get("blend_gains")
    if (
        isinstance(declared, bool)
        or not isinstance(declared, int)
        or not isinstance(dof_sets, dict)
        or not all(isinstance(name, str) for name in dof_sets)
        or not isinstance(gains, list)
        or not all(
            isinstance(gain, (int, _DecimalToken)) and not isinstance(gain, bool)
            for gain in gains
        )
    ):
        return []
    expected = (1 + len(dof_sets) * len(gains)) * len(seeds)
    if expected != declared:
        return []
    existing_keys = {
        (row.parameters.get("dof_set"), str(row.parameters.get("gain")), row.seed)
        for row in existing
    }
    rows: list[LegacyRateRunEvidence] = []
    for dof_index, dof_set in enumerate(dof_sets):
        for gain_index, gain in enumerate(gains):
            for seed_index, seed in enumerate(seeds):
                key = (dof_set, str(gain), seed)
                if key in existing_keys:
                    continue
                gain_text = str(gain)
                label = f"{dof_set}_g{float(gain_text):.2f}"
                rows.append(
                    LegacyRateRunEvidence(
                        pointer=(
                            f"/source_declared_grid/{dof_index}/{gain_index}/"
                            f"seed/{seed_index}"
                        ),
                        selector=f"/source_declared_grid/{dof_index}/{gain_index}:{seed_index}",
                        seed=seed,
                        duration_ms=None,
                        parameters={
                            "dof_set": dof_set,
                            "dof_set_members": _materialize(dof_sets[dof_set]),
                            "gain": _materialize(gain),
                            "label": label,
                        },
                        result={},
                    )
                )
    return rows


def _named_mapping_rows(
    value: object,
    *,
    pointer: str,
    duration_ms: int | None = None,
) -> list[LegacyRateRunEvidence]:
    """Expand a result map whose keys are exact source-generated run labels."""
    if not _is_mapping(value):
        return []
    assert isinstance(value, dict)
    rows: list[LegacyRateRunEvidence] = []
    for label, result_value in value.items():
        if not _is_mapping(result_value):
            continue
        assert isinstance(result_value, dict)
        materialized_result = _materialize(result_value)
        assert isinstance(materialized_result, dict)
        rows.append(
            LegacyRateRunEvidence(
                pointer=f"{pointer}/{label}",
                selector=f"{pointer}/{label}",
                seed=_seed(result_value.get("seed", result_value.get("random_seed"))),
                duration_ms=_row_duration_ms(result_value) or duration_ms,
                parameters={"label": label},
                result={"label": label, **materialized_result},
            )
        )
    return rows


def expand_legacy_rate_collection(
    collection: LegacyRateCollection, *, repository_root: Path
) -> LegacyRateCollectionExpansion:
    if collection.archive_member is None:
        data, _, _, _, _ = _result_bytes(repository_root, collection.result_path)
    else:
        data, _, _, _, _ = _read_archive_collection(collection, repository_root)
    if _sha256(data) != collection.result_sha256:
        raise HistoricalNormalizationError(
            f"legacy result differs from discovered authority: {collection.evidence_locator}"
        )
    value = _json(data)
    rows: list[LegacyRateRunEvidence] = []
    declared: int | None = None
    if isinstance(value, list):
        rows.extend(_direct_rows(value, ""))
    elif _is_mapping(value):
        assert isinstance(value, dict)
        metadata = value.get("metadata")
        if isinstance(metadata, dict):
            raw_declared = metadata.get("total_runs")
            if isinstance(raw_declared, int) and not isinstance(raw_declared, bool):
                declared = raw_declared
        detailed = False
        container_keys = tuple(
            key
            for key in value
            if key in _RESULT_CONTAINERS or key.endswith("_results")
        )
        for key in container_keys:
            direct = _direct_rows(value.get(key), f"/{key}")
            if direct:
                rows.extend(direct)
                detailed = True
        if not detailed:
            rows.extend(
                _summary_rows(
                    value.get("config_summaries"),
                    pointer="/config_summaries",
                    seeds=collection.seeds,
                )
            )
            rows.extend(_baseline_rows(value, seeds=collection.seeds))
            rows.extend(_named_summary_rows(value, seeds=collection.seeds))
            rows.extend(
                _declared_grid_rows(
                    value,
                    seeds=collection.seeds,
                    existing=rows,
                )
            )
        if not rows and "stability_map" in value and "wqs_scores" in value:
            rows.extend(
                _named_mapping_rows(
                    value.get("stability_map"),
                    pointer="/stability_map",
                    duration_ms=3_000,
                )
            )
            rows.extend(
                _named_mapping_rows(
                    value.get("wqs_scores"),
                    pointer="/wqs_scores",
                    duration_ms=6_000,
                )
            )
    unique = {(row.pointer, row.selector) for row in rows}
    if len(unique) != len(rows):
        raise HistoricalNormalizationError(
            f"legacy run pointers are not unique in {collection.collection_id}"
        )
    unresolved = max(0, (declared or len(rows)) - len(rows))
    return LegacyRateCollectionExpansion(
        collection=collection,
        runs=tuple(rows),
        declared_run_count=declared,
        unresolved_run_count=unresolved,
    )


def _read_archive_collection(
    collection: LegacyRateCollection, repository_root: Path
) -> tuple[bytes, str, str | None, str | None, int | None]:
    if collection.archive_member is None:
        raise HistoricalNormalizationError("legacy archive member is missing")
    archive_path = repository_root / collection.result_path
    archive_bytes = archive_path.read_bytes()
    if _sha256(archive_bytes) != collection.archive_sha256:
        raise HistoricalNormalizationError(
            f"legacy archive differs from discovered authority: {collection.result_path}"
        )
    with tarfile.open(archive_path, "r:gz") as archive:
        extracted = archive.extractfile(collection.archive_member)
        if extracted is None:
            raise HistoricalNormalizationError(
                f"legacy archive member is missing: {collection.evidence_locator}"
            )
        data = extracted.read()
    return (
        data,
        collection.result_path,
        collection.archive_member,
        collection.archive_sha256,
        len(archive_bytes),
    )


def _source_authority(
    collection: LegacyRateCollection, *, revision: str
) -> HistoricalSourceAuthority:
    return HistoricalSourceAuthority(
        repository="flybrian-serve",
        revision=revision,
        logical_path=collection.source_path,
        byte_length=collection.source_byte_length,
        sha256=collection.source_sha256,
        license_id="proprietary-unpublished",
        access="private",
        redistribution="not-allowed",
        extractor_id=STATIC_PYTHON_EXTRACTOR_ID,
        extractor_version=STATIC_PYTHON_EXTRACTOR_VERSION,
    )


def _context_input(collection: LegacyRateCollection) -> HistoricalInputReference:
    if collection.archive_member is None:
        byte_length = collection.result_byte_length
        digest = collection.result_sha256
    else:
        if collection.archive_byte_length is None or collection.archive_sha256 is None:
            raise HistoricalNormalizationError("legacy archive authority is incomplete")
        byte_length = collection.archive_byte_length
        digest = collection.archive_sha256
    return HistoricalInputReference(
        input_id=f"org.flybrian.input.legacy-rate.{collection.collection_id}.retained-context",
        kind="file",
        logical_path=collection.result_path,
        byte_length=byte_length,
        sha256=digest,
        file_count=1,
        provenance="Retained writer aggregate used as exact run and selector evidence.",
    )


def _configuration(
    collection: LegacyRateCollection, row: LegacyRateRunEvidence
) -> dict[str, object]:
    duration_ms = row.duration_ms or collection.duration_ms
    parameters = dict(row.parameters)
    option_values = _flatten_option_values(parameters)
    return {
        "requested_duration_ms": duration_ms,
        "effective_duration_ms": duration_ms,
        "random_seed": row.seed if row.seed is not None else collection.default_seed,
        "recorded_parameters": parameters,
        "option_definitions": [
            {
                "option_id": f"recorded.{name}",
                "label": name.replace(".", " · ").replace("_", " ").title(),
                "value_kind": _option_value_kind(value),
                "unit": None,
                "resolution_rule": "Exact value recorded by the historical writer evidence.",
            }
            for name, value in option_values
        ],
        "option_resolutions": [
            {
                "option_id": f"recorded.{name}",
                "requested_value": value,
                "effective_value": value,
                "source": "retained_writer_evidence",
            }
            for name, value in option_values
        ],
        "implementation": {
            "backend": "historical_numpy_rate_source",
            "neuron_models": "continuous_rate_euler_1ms",
            "controller": "source_bound",
            "body": "flybody_mujoco_source_bound",
            "writer_collection": collection.collection_id,
            "writer_selector": row.selector,
        },
    }


def _flatten_option_values(
    value: Mapping[str, object], prefix: str = ""
) -> list[tuple[str, object]]:
    flattened: list[tuple[str, object]] = []
    for key, item in sorted(value.items()):
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(item, dict):
            flattened.extend(_flatten_option_values(item, name))
        elif item is None or isinstance(item, (bool, int, str, list)):
            flattened.append((name, item))
    return flattened


def _option_value_kind(value: object) -> str:
    if isinstance(value, _DecimalToken):
        return "decimal"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, list):
        if all(
            isinstance(item, (int, _DecimalToken)) and not isinstance(item, bool)
            for item in value
        ):
            return "decimal_list"
        return "text_list"
    if value is None:
        return "null"
    return "string"


_CORE_INPUT_IDS = frozenset(
    {
        "org.flybrian.input.c148-phase0.connectivity-part-1",
        "org.flybrian.input.c148-phase0.connectivity-part-2",
        "org.flybrian.input.c148-phase0.connectivity-part-3",
        "org.flybrian.input.c148-phase0.dependency-lock",
        "org.flybrian.input.c148-phase0.flybody-model-tree",
    }
)
_MODULE_INPUT_IDS = frozenset(
    {
        "org.flybrian.input.c148-phase0.e1i1-connectivity",
        "org.flybrian.input.c148-phase0.module-memberships",
    }
)


def _execution_inputs(collection: LegacyRateCollection) -> tuple[HistoricalInputReference, ...]:
    wanted = set(_CORE_INPUT_IDS)
    if collection.cycle >= 121:
        wanted.update(_MODULE_INPUT_IDS)
    shared = [item for item in C148_PHASE0_INPUTS if item.input_id in wanted]
    return tuple(sorted([*shared, _context_input(collection)], key=lambda item: item.input_id))


def build_legacy_rate_normalization_bundle(
    *,
    repository_root: Path,
    revision: str,
    include_recipes: bool = True,
) -> HistoricalNormalizationBundle:
    """Normalize every retained C91-C134 run that has exact row evidence."""
    discovered = discover_legacy_rate_collections(repository_root=repository_root)
    expansions = tuple(
        expand_legacy_rate_collection(item, repository_root=repository_root)
        for item in discovered
    )
    expansions = tuple(item for item in expansions if item.runs or item.declared_run_count)
    collections = tuple(item.collection for item in expansions)
    definitions: dict[str, NormalizedExperimentDefinition] = {}
    claims: list[HistoricalClaim] = []
    occurrences: list[HistoricalRunOccurrence] = []
    artifacts: list[HistoricalArtifactReference] = []
    recipes: list[HistoricalExecutionRecipe] = []
    inputs_by_id = {
        item.input_id: item
        for collection in collections
        for item in _execution_inputs(collection)
    }
    inputs = tuple(sorted(inputs_by_id.values(), key=lambda item: item.input_id))
    input_ids = {
        item.collection_id: tuple(
            reference.input_id for reference in _execution_inputs(item)
        )
        for item in collections
    }
    for expansion in expansions:
        collection = expansion.collection
        source = _source_authority(collection, revision=revision)
        for index, row in enumerate(expansion.runs):
            configuration = _configuration(collection, row)
            family_id = f"org.flybrian.family.legacy-rate.c{collection.cycle}"
            identity = canonical_sha256(
                {
                    "family_id": family_id,
                    "scientific_configuration": configuration,
                    "source": source.to_dict(),
                }
            )
            definition_id = f"org.flybrian.definition.{collection.collection_id}-{identity[:16]}"
            definitions.setdefault(
                definition_id,
                NormalizedExperimentDefinition(
                    definition_id=definition_id,
                    version="1.0",
                    family_id=family_id,
                    scientific_configuration=configuration,
                    source=source,
                ),
            )
            claim_id = f"org.flybrian.claim.{collection.collection_id}-run-{index}"
            occurrence_id = f"org.flybrian.occurrence.{collection.collection_id}-run-{index}"
            artifact_id = f"org.flybrian.artifact.{collection.collection_id}-run-{index}-result"
            label = row.parameters.get("label", row.parameters.get("config", f"run {index}"))
            claims.append(
                HistoricalClaim(
                    claim_id=claim_id,
                    definition_id=definition_id,
                    name=f"C{collection.cycle} {collection.collection_id} — {label}",
                    description=(
                        f"Retained {(row.duration_ms or collection.duration_ms):,} ms "
                        f"NumPy-rate execution at "
                        f"{collection.evidence_locator}#{row.pointer}."
                    ),
                    tags=(f"c{collection.cycle}", "legacy-rate", "walking"),
                )
            )
            occurrences.append(
                HistoricalRunOccurrence(
                    occurrence_id=occurrence_id,
                    definition_id=definition_id,
                    claim_ids=(claim_id,),
                    evidence=(
                        f"{collection.evidence_locator}#{row.pointer}",
                        f"result SHA-256 {collection.result_sha256}",
                        f"source SHA-256 {collection.source_sha256}",
                    ),
                )
            )
            artifact_value = row.result or configuration
            artifact_bytes = canonical_json_bytes(artifact_value)
            artifact_kind = "scientific_result" if row.result else "source_declared_request"
            artifact_filename = (
                "scientific_result.json" if row.result else "source_declared_request.json"
            )
            artifacts.append(
                HistoricalArtifactReference(
                    artifact_id=artifact_id,
                    definition_id=definition_id,
                    kind=artifact_kind,
                    logical_path=(
                        f"normalized/legacy-rate/{collection.collection_id}/"
                        f"run-{index}/{artifact_filename}"
                    ),
                    byte_length=len(artifact_bytes),
                    sha256=_sha256(artifact_bytes),
                    disposition="bound",
                    disposition_reason=(
                        f"Canonical projection of exact retained evidence pointer {row.pointer}."
                        if row.result
                        else (
                            "Exact source-declared configuration; the overwritten result row "
                            "was not retained."
                        )
                    ),
                    comparison="canonical_json",
                )
            )
            if include_recipes:
                for route in ("flybrian_cloud", "flybrian_local", "standalone"):
                    recipes.append(
                        HistoricalExecutionRecipe(
                            recipe_id=(
                                f"org.flybrian.recipe.{collection.collection_id}-run-"
                                f"{index}.{route}"
                            ),
                            definition_id=definition_id,
                            definition_sha256=definitions[
                                definition_id
                            ].scientific_identity_sha256,
                            route=route,
                            executor_id="org.flybrian.executor.selected-legacy-rate-row",
                            executor_version="1.0",
                            source=source,
                            argv=(
                                collection.source_path,
                                "--flybrian-evidence-selector",
                                row.selector,
                            ),
                            input_ids=input_ids[collection.collection_id],
                            artifact_ids=(artifact_id,),
                        )
                    )
    return HistoricalNormalizationBundle(
        bundle_id="org.flybrian.normalization.legacy-rate-c91-c134",
        version="1.0",
        definitions=tuple(sorted(definitions.values(), key=lambda item: item.definition_id)),
        claims=tuple(sorted(claims, key=lambda item: item.claim_id)),
        occurrences=tuple(sorted(occurrences, key=lambda item: item.occurrence_id)),
        inputs=inputs,
        artifacts=tuple(sorted(artifacts, key=lambda item: item.artifact_id)),
        recipes=tuple(sorted(recipes, key=lambda item: item.recipe_id)),
    )


def audit_legacy_rate_estate(*, repository_root: Path, revision: str) -> dict[str, object]:
    discovered = discover_legacy_rate_collections(repository_root=repository_root)
    expansions = tuple(
        expand_legacy_rate_collection(item, repository_root=repository_root)
        for item in discovered
    )
    expansions = tuple(item for item in expansions if item.runs or item.declared_run_count)
    collections = tuple(item.collection for item in expansions)
    receipt: dict[str, object] = {
        "schema_version": "1.0",
        "profile_id": LEGACY_RATE_PROFILE_ID,
        "profile_version": LEGACY_RATE_PROFILE_VERSION,
        "source_repository": "flybrian-serve",
        "source_revision": revision,
        "collection_count": len(collections),
        "retained_run_count": sum(len(item.runs) for item in expansions),
        "retained_result_run_count": sum(
            1 for item in expansions for row in item.runs if row.result
        ),
        "source_declared_only_run_count": sum(
            1 for item in expansions for row in item.runs if not row.result
        ),
        "unresolved_declared_run_count": sum(item.unresolved_run_count for item in expansions),
        "collections": [
            {
                **item.collection.to_dict(),
                "retained_run_count": len(item.runs),
                "declared_run_count": item.declared_run_count,
                "unresolved_declared_run_count": item.unresolved_run_count,
            }
            for item in expansions
        ],
    }
    receipt["sha256"] = canonical_sha256(receipt)
    return receipt
