"""Replay one retained NumPy-rate writer collection and select one exact row."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
from dataclasses import replace
from pathlib import Path
from typing import Literal, cast

from .historical_legacy_rate import (
    LegacyRateCollection,
    discover_legacy_rate_collections,
    expand_legacy_rate_collection,
)
from .historical_normalization import (
    HistoricalNormalizationError,
    canonical_json_bytes,
    canonical_sha256,
)
from .historical_standing_selection import _numeric_comparison

_OPERATIONAL_FIELDS = frozenset({"date", "elapsed_s", "runtime_s", "time_s"})


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _authority(repository_root: Path, collection_id: str) -> LegacyRateCollection:
    matches = [
        item
        for item in discover_legacy_rate_collections(repository_root=repository_root)
        if item.collection_id == collection_id
    ]
    if len(matches) != 1:
        raise HistoricalNormalizationError(f"unknown legacy-rate collection: {collection_id}")
    return matches[0]


class _WriterRedirector(ast.NodeTransformer):
    def __init__(self, *, repository_root: Path, output_dir: Path) -> None:
        self.repository_root = repository_root
        self.output_dir = output_dir
        self.output_assignments = 0

    def visit_Assign(self, node: ast.Assign) -> ast.AST:
        node = cast(ast.Assign, self.generic_visit(node))
        names = {target.id for target in node.targets if isinstance(target, ast.Name)}
        if "PROJECT" in names or "ROOT" in names:
            node.value = ast.Call(
                func=ast.Name(id="Path", ctx=ast.Load()),
                args=[ast.Constant(value=str(self.repository_root))],
                keywords=[],
            )
        if names.intersection({"OUT_DIR", "OUTPUT_DIR"}):
            original_is_text = isinstance(node.value, ast.Constant) and isinstance(
                node.value.value, str
            )
            node.value = (
                ast.Constant(value=str(self.output_dir))
                if original_is_text
                else ast.Call(
                    func=ast.Name(id="Path", ctx=ast.Load()),
                    args=[ast.Constant(value=str(self.output_dir))],
                    keywords=[],
                )
            )
            self.output_assignments += 1
        return node


def _redirected_source(
    source_bytes: bytes,
    *,
    source_path: str,
    repository_root: Path,
    output_dir: Path,
) -> str:
    try:
        tree = ast.parse(source_bytes, filename=source_path)
    except SyntaxError as error:
        raise HistoricalNormalizationError("legacy-rate writer cannot be parsed") from error
    redirector = _WriterRedirector(
        repository_root=repository_root,
        output_dir=output_dir,
    )
    transformed = redirector.visit(tree)
    ast.fix_missing_locations(transformed)
    if redirector.output_assignments != 1:
        raise HistoricalNormalizationError(
            f"legacy-rate writer has {redirector.output_assignments} output roots; expected one"
        )
    return ast.unparse(transformed)


def _science(value: object) -> object:
    if isinstance(value, dict):
        return {
            key: _science(item)
            for key, item in value.items()
            if key not in _OPERATIONAL_FIELDS
        }
    if isinstance(value, list):
        return [_science(item) for item in value]
    return value


def execute_legacy_rate_selection(
    *,
    repository_root: Path,
    output_dir: Path,
    python_executable: Path,
    revision: str,
    collection_id: str,
    selector: str,
    route: Literal["standalone", "flybrian_local", "flybrian_cloud"] = "standalone",
) -> dict[str, object]:
    """Replay the exact writer batch, then project and compare the selected row."""

    root = repository_root.resolve(strict=True)
    collection = _authority(root, collection_id)
    retained = expand_legacy_rate_collection(collection, repository_root=root)
    matches = [row for row in retained.runs if row.selector == selector]
    if len(matches) != 1:
        raise HistoricalNormalizationError(
            f"legacy-rate selector does not identify one retained row: {selector}"
        )
    retained_row = matches[0]
    target = output_dir.resolve()
    target.mkdir(parents=True, exist_ok=False)
    artifacts = target / "artifacts"
    artifacts.mkdir()

    source_path = root / collection.source_path
    source_bytes = source_path.read_bytes()
    if _sha256(source_bytes) != collection.source_sha256:
        raise HistoricalNormalizationError(
            f"{collection_id} writer differs from discovered authority"
        )
    redirected = _redirected_source(
        source_bytes,
        source_path=collection.source_path,
        repository_root=root,
        output_dir=artifacts,
    )
    launcher = target / "replay_legacy_rate_writer.py"
    launcher.write_text(
        "source = " + repr(redirected) + "\n"
        + "namespace = {'__file__': " + repr(str(source_path))
        + ", '__name__': '__main__'}\n"
        + "exec(compile(source, namespace['__file__'], 'exec'), namespace)\n",
        encoding="utf-8",
    )
    stdout_path = target / "stdout.log"
    stderr_path = target / "stderr.log"
    environment = os.environ.copy()
    environment["PYTHONHASHSEED"] = "0"
    environment["MPLCONFIGDIR"] = str(target / "matplotlib")
    engine_source = str(Path(__file__).resolve().parents[1])
    environment["PYTHONPATH"] = os.pathsep.join(
        item
        for item in (str(root), engine_source, environment.get("PYTHONPATH", ""))
        if item
    )
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        completed = subprocess.run(
            (str(python_executable.resolve(strict=True)), str(launcher)),
            cwd=root,
            env=environment,
            stdout=stdout,
            stderr=stderr,
            check=False,
        )
    fresh_path = artifacts / Path(collection.archive_member or collection.result_path).name
    if completed.returncode != 0 or not fresh_path.is_file():
        tail = stderr_path.read_text(encoding="utf-8", errors="replace")[-4_000:]
        raise HistoricalNormalizationError(
            f"legacy-rate writer exited with status {completed.returncode}: {tail}"
        )
    fresh_bytes = fresh_path.read_bytes()
    fresh_collection = replace(
        collection,
        result_path=fresh_path.name,
        result_sha256=_sha256(fresh_bytes),
        result_byte_length=len(fresh_bytes),
        archive_member=None,
        archive_sha256=None,
        archive_byte_length=None,
    )
    fresh = expand_legacy_rate_collection(
        fresh_collection,
        repository_root=artifacts,
    )
    fresh_matches = [row for row in fresh.runs if row.selector == selector]
    if len(fresh_matches) != 1:
        raise HistoricalNormalizationError(
            "replayed writer did not reproduce the selected result-row identity"
        )
    retained_science = _science(dict(retained_row.result))
    fresh_science = _science(dict(fresh_matches[0].result))
    mismatch_paths, maximum_absolute, maximum_relative = _numeric_comparison(
        retained_science,
        fresh_science,
    )
    exact = retained_science == fresh_science
    scientific_path = artifacts / "scientific_result.json"
    scientific_path.write_bytes(canonical_json_bytes(fresh_science) + b"\n")
    receipt: dict[str, object] = {
        "schema_version": "1.0",
        "collection_id": collection_id,
        "selector": selector,
        "route": route,
        "source_revision": revision,
        "source_sha256": collection.source_sha256,
        "requested_duration_ms": retained_row.duration_ms or collection.duration_ms,
        "writer_exit_status": completed.returncode,
        "comparison": {
            "profile_id": "org.flybrian.comparison.legacy-rate-numeric",
            "profile_version": "1.0",
            "status": (
                "exact"
                if exact
                else "numerically_equivalent"
                if not mismatch_paths
                else "different"
            ),
            "excluded_fields": sorted(_OPERATIONAL_FIELDS),
            "numeric_mismatch_paths": mismatch_paths,
            "absolute_tolerance": "1e-8",
            "relative_tolerance": "1e-7",
            "maximum_absolute_difference": repr(maximum_absolute),
            "maximum_relative_difference": repr(maximum_relative),
            "retained_scientific_sha256": canonical_sha256(retained_science),
            "fresh_scientific_sha256": canonical_sha256(fresh_science),
        },
        "artifacts": {
            "scientific_result": {
                "path": str(scientific_path.relative_to(target)),
                "sha256": _sha256(scientific_path.read_bytes()),
            },
            "writer_result": {
                "path": str(fresh_path.relative_to(target)),
                "sha256": _sha256(fresh_bytes),
            },
        },
        "stdout_path": str(stdout_path.relative_to(target)),
        "stderr_path": str(stderr_path.relative_to(target)),
    }
    receipt["sha256"] = canonical_sha256(receipt)
    (target / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt
