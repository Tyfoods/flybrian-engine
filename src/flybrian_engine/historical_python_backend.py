"""Locked execution of reviewed historical Python-source recipes."""

from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from .historical_normalization import (
    HistoricalArtifactReference,
    HistoricalComparedArtifact,
    HistoricalComparisonReceipt,
    HistoricalExecutionRecipe,
    HistoricalInputReference,
    HistoricalNormalizationError,
    canonical_sha256,
)


class HistoricalExecutionError(RuntimeError):
    """A locked source recipe cannot be admitted or did not complete."""


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _tree_identity(path: Path) -> tuple[int, int, str]:
    records: list[dict[str, object]] = []
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        records.append(
            {
                "path": item.relative_to(path).as_posix(),
                "byte_length": item.stat().st_size,
                "sha256": _file_sha256(item),
            }
        )
    payload = json.dumps(records, sort_keys=True, separators=(",", ":")).encode()
    return (
        len(records),
        sum(int(item["byte_length"]) for item in records),
        hashlib.sha256(payload).hexdigest(),
    )


def _safe_path(root: Path, logical_path: str) -> Path:
    candidate = (root / logical_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise HistoricalExecutionError(
            f"declared path escapes the source root: {logical_path}"
        ) from error
    return candidate


def _git(root: Path, *arguments: str) -> str:
    result = subprocess.run(
        ("git", "-C", str(root), *arguments),
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise HistoricalExecutionError(
            "source root is not the declared Git checkout: "
            + (result.stderr.strip() or result.stdout.strip())
        )
    return result.stdout.strip()


def materialize_packaged_historical_inputs(
    inputs: Sequence[HistoricalInputReference],
    *,
    source_root: Path,
) -> tuple[Path, ...]:
    """Materialize exact packaged file inputs into an ephemeral source checkout."""
    root = source_root.resolve()
    if not root.is_dir():
        raise HistoricalExecutionError("source root does not exist")
    data_root = files("flybrian_engine").joinpath("data")
    produced: list[Path] = []
    for declared in inputs:
        if declared.packaged_resource is None:
            continue
        resource = data_root.joinpath(declared.packaged_resource)
        try:
            encoded = b"".join(resource.read_bytes().split())
            payload = base64.b64decode(encoded, validate=True)
        except (FileNotFoundError, ValueError) as error:
            raise HistoricalExecutionError(
                f"packaged historical input is unavailable: {declared.input_id}"
            ) from error
        if (
            len(payload) != declared.byte_length
            or hashlib.sha256(payload).hexdigest() != declared.sha256
        ):
            raise HistoricalExecutionError(
                f"packaged historical input identity differs: {declared.input_id}"
            )
        destination = _safe_path(root, declared.logical_path)
        if destination.exists():
            raise HistoricalExecutionError(
                f"historical input destination already exists: {declared.logical_path}"
            )
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(payload)
        produced.append(destination)
    return tuple(produced)


def validate_historical_input_references(
    inputs: Sequence[HistoricalInputReference],
    *,
    source_root: Path,
) -> None:
    """Require every declared historical input to match its exact file or tree identity."""

    root = source_root.resolve()
    for declared_input in inputs:
        input_path = _safe_path(root, declared_input.logical_path)
        if declared_input.kind == "file":
            if not input_path.is_file():
                raise HistoricalExecutionError(
                    f"declared input is missing: {declared_input.logical_path}"
                )
            count, byte_length, digest = 1, input_path.stat().st_size, _file_sha256(input_path)
        else:
            if not input_path.is_dir():
                raise HistoricalExecutionError(
                    f"declared input tree is missing: {declared_input.logical_path}"
                )
            count, byte_length, digest = _tree_identity(input_path)
        if (
            count != declared_input.file_count
            or byte_length != declared_input.byte_length
            or digest != declared_input.sha256
        ):
            raise HistoricalExecutionError(
                f"declared input identity differs: {declared_input.logical_path}"
            )


@dataclass(frozen=True)
class HistoricalProducedArtifact:
    artifact_id: str
    kind: str
    logical_path: str
    captured_path: str
    byte_length: int
    sha256: str
    historical_candidate_sha256: str
    frame_interval_ms: int | None

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "logical_path": self.logical_path,
            "captured_path": self.captured_path,
            "byte_length": self.byte_length,
            "sha256": self.sha256,
            "historical_candidate_sha256": self.historical_candidate_sha256,
            "frame_interval_ms": self.frame_interval_ms,
        }


@dataclass(frozen=True)
class HistoricalExecutionReceipt:
    receipt_id: str
    definition_id: str
    recipe_id: str
    recipe_sha256: str
    route: str
    source_revision: str
    source_sha256: str
    interpreter: str
    interpreter_version: str
    installed_distributions_sha256: str
    argv: tuple[str, ...]
    artifacts: tuple[HistoricalProducedArtifact, ...]
    stdout_path: str
    stderr_path: str

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_dict(include_sha256=False))

    def to_dict(self, *, include_sha256: bool = True) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": "1.0",
            "receipt_id": self.receipt_id,
            "definition_id": self.definition_id,
            "recipe_id": self.recipe_id,
            "recipe_sha256": self.recipe_sha256,
            "route": self.route,
            "source_revision": self.source_revision,
            "source_sha256": self.source_sha256,
            "interpreter": self.interpreter,
            "interpreter_version": self.interpreter_version,
            "installed_distributions_sha256": self.installed_distributions_sha256,
            "argv": list(self.argv),
            "artifacts": [item.to_dict() for item in self.artifacts],
            "stdout_path": self.stdout_path,
            "stderr_path": self.stderr_path,
        }
        if include_sha256:
            result["sha256"] = self.sha256
        return result


def execute_locked_python_recipe(
    recipe: HistoricalExecutionRecipe,
    inputs: Sequence[HistoricalInputReference],
    artifacts: Sequence[HistoricalArtifactReference],
    *,
    source_root: Path,
    output_dir: Path,
    python_executable: Path,
) -> HistoricalExecutionReceipt:
    """Execute one manifest command after exact source and checkout admission.

    The source checkout must be an ephemeral clean worktree at the recipe's
    declared revision because historical scripts may write deterministic output
    filenames inside their repository root.
    """
    root = source_root.resolve()
    if not root.is_dir():
        raise HistoricalExecutionError("source root does not exist")
    revision = _git(root, "rev-parse", "HEAD")
    if revision != recipe.source.revision:
        raise HistoricalExecutionError(
            f"source checkout is {revision}; recipe requires {recipe.source.revision}"
        )
    dirty = _git(root, "status", "--porcelain", "--untracked-files=no")
    if dirty:
        raise HistoricalExecutionError("source checkout contains tracked modifications")
    source_path = _safe_path(root, recipe.source.logical_path)
    if not source_path.is_file():
        raise HistoricalExecutionError("declared historical source is missing")
    if source_path.stat().st_size != recipe.source.byte_length:
        raise HistoricalExecutionError("declared historical source byte length differs")
    if _file_sha256(source_path) != recipe.source.sha256:
        raise HistoricalExecutionError("declared historical source checksum differs")
    if recipe.argv[0] != recipe.source.logical_path:
        raise HistoricalExecutionError("recipe argv must begin with its declared source path")
    selected_inputs = {item.input_id: item for item in inputs}
    if set(recipe.input_ids) != set(selected_inputs):
        raise HistoricalNormalizationError(
            "execution received inputs other than the recipe's declared set"
        )
    validate_historical_input_references(tuple(selected_inputs.values()), source_root=root)
    selected = {item.artifact_id: item for item in artifacts}
    if set(recipe.artifact_ids) != set(selected):
        raise HistoricalNormalizationError(
            "execution received artifacts other than the recipe's declared set"
        )
    for artifact in selected.values():
        output_path = _safe_path(root, artifact.logical_path)
        if output_path.exists():
            raise HistoricalExecutionError(
                f"ephemeral source checkout already contains {artifact.logical_path}"
            )
    interpreter = python_executable.absolute()
    if not interpreter.is_file():
        raise HistoricalExecutionError("Python interpreter does not exist")
    target = output_dir.resolve()
    target.mkdir(parents=True, exist_ok=False)
    stdout_path = target / "stdout.log"
    stderr_path = target / "stderr.log"
    environment = os.environ.copy()
    environment["PYTHONHASHSEED"] = "0"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        completed = subprocess.run(
            (str(interpreter), *recipe.argv),
            cwd=root,
            env=environment,
            stdout=stdout,
            stderr=stderr,
            check=False,
        )
    if completed.returncode != 0:
        raise HistoricalExecutionError(
            f"historical source exited with status {completed.returncode}; see stderr.log"
        )
    artifact_dir = target / "artifacts"
    artifact_dir.mkdir()
    produced: list[HistoricalProducedArtifact] = []
    for index, artifact_id in enumerate(recipe.artifact_ids):
        declared = selected[artifact_id]
        source_artifact = _safe_path(root, declared.logical_path)
        if not source_artifact.is_file():
            raise HistoricalExecutionError(
                f"historical source did not produce {declared.logical_path}"
            )
        captured = artifact_dir / f"{index:02d}-{source_artifact.name}"
        shutil.copyfile(source_artifact, captured)
        produced.append(
            HistoricalProducedArtifact(
                artifact_id=declared.artifact_id,
                kind=declared.kind,
                logical_path=declared.logical_path,
                captured_path=str(captured.relative_to(target)),
                byte_length=captured.stat().st_size,
                sha256=_file_sha256(captured),
                historical_candidate_sha256=declared.sha256,
                frame_interval_ms=declared.frame_interval_ms,
            )
        )
    version = subprocess.run(
        (str(interpreter), "--version"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    installed_distributions = subprocess.run(
        (str(interpreter), "-m", "pip", "freeze", "--all"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    installed_distributions_sha256 = canonical_sha256(
        sorted(line.strip() for line in installed_distributions if line.strip())
    )
    receipt = HistoricalExecutionReceipt(
        receipt_id=f"org.flybrian.receipt.{recipe.route.replace('_', '-')}.{recipe.sha256[:16]}",
        definition_id=recipe.definition_id,
        recipe_id=recipe.recipe_id,
        recipe_sha256=recipe.sha256,
        route=recipe.route,
        source_revision=revision,
        source_sha256=recipe.source.sha256,
        interpreter=str(interpreter),
        interpreter_version=version,
        installed_distributions_sha256=installed_distributions_sha256,
        argv=recipe.argv,
        artifacts=tuple(produced),
        stdout_path=str(stdout_path.relative_to(target)),
        stderr_path=str(stderr_path.relative_to(target)),
    )
    (target / "receipt.json").write_text(
        json.dumps(receipt.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for artifact_id in recipe.artifact_ids:
        _safe_path(root, selected[artifact_id].logical_path).unlink()
    return receipt


def compare_historical_execution_artifacts(
    *,
    comparison_id: str,
    definition_id: str,
    left_recipe: HistoricalExecutionRecipe,
    right_recipe: HistoricalExecutionRecipe,
    artifacts: Sequence[HistoricalArtifactReference],
    left_paths: dict[str, Path],
    right_paths: dict[str, Path],
) -> HistoricalComparisonReceipt:
    """Compare two executions using the artifact authorities' declared semantics."""
    declared = {item.artifact_id: item for item in artifacts}
    expected_ids = set(declared)
    if set(left_paths) != expected_ids or set(right_paths) != expected_ids:
        raise HistoricalNormalizationError("comparison paths must match the declared artifact set")
    differences: list[str] = []
    compared: list[HistoricalComparedArtifact] = []
    for artifact_id in sorted(expected_ids):
        authority = declared[artifact_id]
        left = left_paths[artifact_id]
        right = right_paths[artifact_id]
        if not left.is_file() or not right.is_file():
            raise HistoricalExecutionError(f"comparison artifact is missing: {artifact_id}")
        left_sha256 = _file_sha256(left)
        right_sha256 = _file_sha256(right)
        if authority.comparison == "exact_bytes":
            equal = left_sha256 == right_sha256
        else:
            equal = _comparable_json(left, authority.excluded_json_fields) == _comparable_json(
                right,
                authority.excluded_json_fields,
            )
        if not equal:
            differences.append(f"{artifact_id} differs under {authority.comparison}")
        compared.append(
            HistoricalComparedArtifact(
                artifact_id=artifact_id,
                kind=authority.kind,
                comparison=authority.comparison,
                left_sha256=left_sha256,
                right_sha256=right_sha256,
                status="equal" if equal else "different",
                excluded_json_fields=authority.excluded_json_fields,
            )
        )
    return HistoricalComparisonReceipt(
        comparison_id=comparison_id,
        definition_id=definition_id,
        left_recipe_sha256=left_recipe.sha256,
        right_recipe_sha256=right_recipe.sha256,
        status="equal" if not differences else "different",
        artifacts=tuple(compared),
        differences=tuple(differences),
    )


def _comparable_json(path: Path, excluded_fields: tuple[str, ...]) -> object:
    try:
        value: object = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HistoricalExecutionError(f"comparison artifact is not valid JSON: {path}") from error
    return _without_operational_fields(value, frozenset(excluded_fields))


def _without_operational_fields(value: object, excluded_fields: frozenset[str]) -> object:
    if isinstance(value, dict):
        return {
            key: _without_operational_fields(item, excluded_fields)
            for key, item in value.items()
            if key not in excluded_fields
        }
    if isinstance(value, list):
        return [_without_operational_fields(item, excluded_fields) for item in value]
    return value
