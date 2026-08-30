"""Select one retained standing run from its original historical writer."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import shutil
import subprocess
import tarfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Literal

from .historical_normalization import (
    HistoricalNormalizationError,
    canonical_json_bytes,
    canonical_sha256,
)
from .historical_standing_estate import (
    STANDING_COLLECTIONS,
    StandingCollectionAuthority,
    read_collection_rows,
)

_OPERATIONAL_FIELDS = frozenset({"elapsed_s", "runtime_s", "time_s"})

# These are the calls that correspond one-for-one, in source order, with rows
# appended by each reviewed writer. Calls made only for summaries are omitted.
_DISPATCH_NAMES: dict[str, tuple[str, ...]] = {
    "c148-phase0b": ("run_closed_loop_from_network",),
    "c148-phase1": ("run_standing_trial",),
    "c148-phase1c": ("run_trial",),
    "c148-phase1d": ("run_trial",),
    "c148-phase1e": ("servo_settle",),
    "c148-phase1f": ("run_trial",),
    "c148-phase2-validation": ("run_trial_with_traj",),
    "c148-phase2a": ("run_trial",),
    "c148-phase2a2": ("run_trial",),
    "c148-phase2b": ("run_trial",),
    "c148-phase4": ("run_trial_full",),
    "c149-phase0": ("run_trial_with_contacts",),
    "c149-phase1": ("run_trial",),
    "c149-phase2": ("run_trial",),
    "c149-phase3": ("run_validation_trial",),
    "c150-phase0": ("run_brian2_only",),
    "c150-phase1": ("run_trial",),
    "c150-phase1b": ("run_trial",),
    "c150-phase2": ("run_trial",),
    "c150-phase2b": ("run_diagnostic_trial",),
    "c150-phase2c": ("run_trial",),
    "c150-phase3": ("run_hyperpol_trial",),
    "c150-phase4": ("run_validation_trial",),
    "c151-phase0": ("run_trial",),
    "c151-phase1": ("run_trial",),
    "c151-phase1b": ("run_trial",),
    "c152-phase0": ("run_trial", "run_closed_loop_from_network"),
    "c152-phase1": ("run_closed_loop_from_network", "run_trial"),
    "c152-phase2": ("run_trial",),
    "c153-phase1": ("run_trial",),
    "c153-phase2": ("run_trial",),
    "c154-phase1": ("run_trial",),
    "c154-phase1b": ("run_trial",),
    "c154-phase2": ("run_trial",),
    "c154-phase3": ("run_trial",),
    "c155-phase1": ("run_trial",),
    "c155-phase1b": ("run_exp",),
    "c155-phase1c": ("run_trial",),
    "c155-phase1d": ("run_trial",),
    "c156-phase1": ("run_openloop", "run_step_response"),
    "c156-phase2": ("run_trial",),
    "c156-phase2b": ("run_openloop", "run_neural_trial"),
}

# Some retained aggregate files contain appended experiments whose producing
# source bytes were not retained. Only the source-generated prefix is runnable.
_SOURCE_ROW_COUNTS = {"c156-phase1": 36}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _authority(collection_id: str) -> StandingCollectionAuthority:
    matching = [item for item in STANDING_COLLECTIONS if item.collection_id == collection_id]
    if len(matching) != 1:
        raise HistoricalNormalizationError(f"unknown standing collection: {collection_id}")
    return matching[0]


def _materialize(value: object) -> object:
    if type(value).__name__ == "_DecimalToken":
        return float(str(value))
    if isinstance(value, dict):
        return {key: _materialize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_materialize(item) for item in value]
    return value


def _metric_payload(collection_id: str, row: Mapping[str, object]) -> object:
    if collection_id in {"c151-phase0", "c151-phase1", "c151-phase1b"}:
        payload = dict(_materialize(dict(row)))
        payload.setdefault("contact_log", [])
        payload.setdefault("elevation_log", [])
        payload.setdefault("n_neurons", 0)
        return payload
    if collection_id in {"c148-phase1", "c148-phase1c", "c148-phase1d"}:
        return _materialize(row["standing_metrics"])
    if collection_id in {
        "c148-phase1f",
        "c148-phase1e",
        "c148-phase2a",
        "c148-phase2a2",
        "c148-phase2b",
        "c150-phase1",
        "c150-phase1b",
        "c150-phase2",
        "c150-phase2c",
        "c150-phase4",
    }:
        return _materialize(row["metrics"])
    if collection_id == "c150-phase0":
        return _materialize(row["results"])
    if collection_id == "c150-phase3":
        payload = dict(_materialize(row["result"]))
        payload["elev_trajectory"] = _materialize(row.get("elev_trajectory", []))
        return payload
    if collection_id in {"c152-phase1", "c152-phase2"}:
        payload = dict(_materialize(dict(row)))
        payload["perstep_fn"] = _StubPerStep({})
        return payload
    return _materialize(dict(row))


def _stub_value(
    collection_id: str,
    row: Mapping[str, object],
    function_name: str,
) -> object:
    materialized = _materialize(dict(row))
    if function_name == "run_closed_loop_from_network":
        return _StubResults()
    if collection_id == "c148-phase2-validation":
        return (materialized["metrics"], [], materialized.get("jtf"), _StubResults())
    if collection_id == "c148-phase4":
        return (
            materialized["metrics"],
            materialized.get("per_dof_corr", {}),
            materialized.get("elev_ratio"),
            [],
        )
    if collection_id == "c149-phase0":
        return (
            materialized["walking"],
            materialized["coordination"],
            materialized.get("n_circuit", 0),
            materialized.get("n_interleg", 0),
        )
    if collection_id in {"c149-phase1", "c149-phase2"}:
        return (
            materialized["walking"],
            materialized["coordination"],
            materialized.get("n_circuit", 0),
        )
    if collection_id == "c149-phase3":
        return (
            materialized["walking"],
            materialized["coordination"],
            0,
            [],
            [],
        )
    if collection_id == "c150-phase2b":
        return (
            materialized["metrics"],
            materialized["dof_analysis"],
            materialized["seg_contact"],
        )
    if collection_id == "c152-phase0":
        return (_StubPerStep(materialized), materialized.get("mn_rates", {}), _StubResults())
    return _metric_payload(collection_id, row)


class _StubResults:
    def __init__(self) -> None:
        self.qpos_history: list[object] = []
        self.motor_commands: list[object] = []
        self.spike_times: dict[str, list[object]] = {}


class _StubPerStep:
    def __init__(self, row: Mapping[str, object]) -> None:
        diagnostic = row.get("diagnostic", {})
        self.contact_log: list[object] = []
        self.elevation_log: list[object] = []
        self.ctrl78_log: list[object] = []
        self.joint_pos_log: list[object] = []
        if isinstance(diagnostic, dict):
            count = int(diagnostic.get("n_windows", 0) or 0)
            self.elevation_log = [diagnostic.get("elev_final", 0.0)] * count
            self.ctrl78_log = [[0.0] * 78 for _ in range(count)]
            self.contact_log = [{} for _ in range(count)]
            segments = ("T1L", "T1R", "T2L", "T2R", "T3L", "T3R")
            dofs = (
                "coxa_abduct",
                "coxa_twist",
                "coxa",
                "trochanter",
                "femur",
                "tibia",
                "tarsus1",
                "tarsus2",
            )
            positions = {segment: {dof: 0.0 for dof in dofs} for segment in segments}
            self.joint_pos_log = [positions for _ in range(count)]


class _RetainedDecisionDict(dict[object, object]):
    """Expose retained values to writer decisions while serializing fresh values."""

    def __init__(self, fresh: Mapping[object, object], retained: Mapping[object, object]) -> None:
        super().__init__(fresh)
        self._retained = retained

    def __getitem__(self, key: object) -> object:
        fresh = super().__getitem__(key)
        retained = self._retained.get(key, fresh)
        return _retained_decision_context(fresh, retained)

    def get(self, key: object, default: object = None) -> object:
        if key not in self:
            return default
        return self[key]


def _retained_decision_context(fresh: object, retained: object) -> object:
    if isinstance(fresh, Mapping) and isinstance(retained, Mapping):
        return _RetainedDecisionDict(fresh, retained)
    if isinstance(fresh, tuple) and isinstance(retained, tuple) and len(fresh) == len(retained):
        return tuple(
            _retained_decision_context(fresh_item, retained_item)
            for fresh_item, retained_item in zip(fresh, retained, strict=True)
        )
    return retained


class _Dispatch:
    def __init__(
        self,
        collection_id: str,
        retained_rows: Sequence[Mapping[str, object]],
        target_index: int,
        replay_prefix: bool = True,
    ) -> None:
        self.collection_id = collection_id
        self.retained_rows = retained_rows
        self.target_index = target_index
        self.replay_prefix = replay_prefix
        self.index = 0

    def __call__(self, function: object, /, *args: object, **kwargs: object) -> object:
        index = self.index
        self.index += 1
        if index >= len(self.retained_rows):
            raise HistoricalNormalizationError(
                f"{self.collection_id} writer invoked more experiments than retained rows"
            )
        if index == self.target_index or (self.replay_prefix and index < self.target_index):
            if not callable(function):
                raise HistoricalNormalizationError("selected historical call is not callable")
            fresh = function(*args, **kwargs)
            retained = _stub_value(
                self.collection_id,
                self.retained_rows[index],
                getattr(function, "__name__", ""),
            )
            return _retained_decision_context(fresh, retained)
        return _stub_value(
            self.collection_id,
            self.retained_rows[index],
            getattr(function, "__name__", ""),
        )


def _capture_closed_loop_result(result: object, artifact_dir: str) -> None:
    """Persist replay authority from the selected writer without changing its result."""
    qpos = getattr(result, "qpos_history", None)
    motor_commands = getattr(result, "motor_commands", None)
    if qpos is None or motor_commands is None or len(qpos) == 0:
        return
    import numpy as np

    target = Path(artifact_dir)
    np.save(target / "qpos_trajectory.npy", np.asarray(qpos))
    np.save(target / "motor_commands.npy", np.asarray(motor_commands))


def _capture_network_projection(network_data: object, artifact_dir: str) -> object:
    """Persist the exact model assignment consumed by the retained runner."""
    if not isinstance(network_data, Mapping):
        raise HistoricalNormalizationError("closed-loop network_data must be an object")
    mappings = network_data.get("id_mappings")
    if not isinstance(mappings, Mapping):
        raise HistoricalNormalizationError("closed-loop network_data lacks id_mappings")

    assignments: dict[str, list[int]] = {}
    for model_name, mapping in sorted(mappings.items(), key=lambda item: str(item[0])):
        if (
            not isinstance(model_name, str)
            or not isinstance(mapping, Sequence)
            or isinstance(mapping, (str, bytes))
            or len(mapping) < 1
            or not isinstance(mapping[0], Mapping)
        ):
            raise HistoricalNormalizationError("closed-loop id_mappings are malformed")
        neuron_ids = sorted(int(neuron_id) for neuron_id in mapping[0])
        assignments[model_name] = neuron_ids

    projection: dict[str, object] = {
        "schema_version": "1.0",
        "model_assignments": assignments,
        "neuron_count": sum(len(neuron_ids) for neuron_ids in assignments.values()),
    }
    projection["sha256"] = canonical_sha256(projection)
    target = Path(artifact_dir) / "network_projection.json"
    target.write_bytes(canonical_json_bytes(projection) + b"\n")
    return network_data


class _WriterSelector(ast.NodeTransformer):
    def __init__(
        self,
        *,
        dispatch_names: tuple[str, ...],
        collection_id: str,
        target_row: Mapping[str, object],
        project_root: Path,
        output_dir: Path,
    ) -> None:
        self.dispatch_names = frozenset(dispatch_names)
        self.collection_id = collection_id
        self.target_row = target_row
        self.project_root = project_root
        self.output_dir = output_dir
        self.project_assignments = 0
        self.output_assignments = 0
        self.dispatched_calls = 0
        self._inside_main = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.AST:
        if node.name == "main":
            self._inside_main += 1
            node = self.generic_visit(node)
            self._inside_main -= 1
            return node
        return self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> ast.AST | list[ast.stmt]:
        captures_closed_loop = (
            isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "run_closed_loop_from_network"
        )
        node = self.generic_visit(node)
        assigned = {target.id for target in node.targets if isinstance(target, ast.Name)}
        if "PROJECT" in assigned:
            node.value = ast.Call(
                func=ast.Name(id="Path", ctx=ast.Load()),
                args=[ast.Constant(value=str(self.project_root))],
                keywords=[],
            )
            self.project_assignments += 1
        if "OUT_DIR" in assigned:
            node.value = ast.Call(
                func=ast.Name(id="Path", ctx=ast.Load()),
                args=[ast.Constant(value=str(self.output_dir))],
                keywords=[],
            )
            self.output_assignments += 1
        if "census_dir" in assigned:
            node.value = ast.Call(
                func=ast.Name(id="Path", ctx=ast.Load()),
                args=[ast.Constant(value=str(self.output_dir.parent / "c155_phase0"))],
                keywords=[],
            )
        if (
            captures_closed_loop
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
        ):
            return [
                node,
                ast.Expr(
                    value=ast.Call(
                        func=ast.Name(id="__flybrian_capture__", ctx=ast.Load()),
                        args=[node.targets[0], ast.Constant(value=str(self.output_dir))],
                        keywords=[],
                    )
                ),
            ]
        return node

    def visit_Call(self, node: ast.Call) -> ast.AST:
        node = self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id == "run_closed_loop_from_network":
            for keyword in node.keywords:
                if keyword.arg == "network_data":
                    keyword.value = ast.Call(
                        func=ast.Name(id="__flybrian_capture_network__", ctx=ast.Load()),
                        args=[keyword.value, ast.Constant(value=str(self.output_dir))],
                        keywords=[],
                    )
        if (
            self._inside_main
            and isinstance(node.func, ast.Name)
            and node.func.id in self.dispatch_names
        ):
            self.dispatched_calls += 1
            return ast.Call(
                func=ast.Name(id="__flybrian_dispatch__", ctx=ast.Load()),
                args=[node.func, *node.args],
                keywords=node.keywords,
            )
        return node

    def visit_For(self, node: ast.For) -> ast.AST:
        node = self.generic_visit(node)
        if self.collection_id != "c148-phase0b":
            return node
        if (
            isinstance(node.target, ast.Name)
            and node.target.id == "cfg"
            and isinstance(node.iter, ast.Name)
            and node.iter.id == "configs"
        ):
            candidate = ast.Name(id="candidate", ctx=ast.Load())
            node.iter = ast.ListComp(
                elt=candidate,
                generators=[
                    ast.comprehension(
                        target=ast.Name(id="candidate", ctx=ast.Store()),
                        iter=ast.Name(id="configs", ctx=ast.Load()),
                        ifs=[
                            ast.Compare(
                                left=ast.Subscript(
                                    value=candidate,
                                    slice=ast.Constant(value="name"),
                                    ctx=ast.Load(),
                                ),
                                ops=[ast.Eq()],
                                comparators=[ast.Constant(value=self.target_row["config"])],
                            )
                        ],
                        is_async=0,
                    )
                ],
            )
        if isinstance(node.target, ast.Name) and node.target.id == "seed":
            node.iter = ast.List(
                elts=[ast.Constant(value=self.target_row["seed"])],
                ctx=ast.Load(),
            )
        return node


def _selected_source(
    source_bytes: bytes,
    *,
    authority: StandingCollectionAuthority,
    target_row: Mapping[str, object],
    project_root: Path,
    output_dir: Path,
) -> str:
    try:
        tree = ast.parse(source_bytes, filename=authority.source_path)
    except SyntaxError as error:
        raise HistoricalNormalizationError(
            f"{authority.collection_id} writer cannot be parsed"
        ) from error
    dispatch_names = _DISPATCH_NAMES.get(authority.collection_id)
    if not dispatch_names:
        raise HistoricalNormalizationError(
            f"{authority.collection_id} does not have a reviewed selection profile"
        )
    selector = _WriterSelector(
        dispatch_names=dispatch_names,
        collection_id=authority.collection_id,
        target_row=target_row,
        project_root=project_root,
        output_dir=output_dir,
    )
    transformed = selector.visit(tree)
    ast.fix_missing_locations(transformed)
    if selector.project_assignments != 1 or selector.output_assignments != 1:
        raise HistoricalNormalizationError(
            f"{authority.collection_id} writer no longer has one PROJECT and OUT_DIR authority"
        )
    if selector.dispatched_calls == 0:
        raise HistoricalNormalizationError(
            f"{authority.collection_id} writer has no reviewed experiment calls"
        )
    return ast.unparse(transformed)


def _fresh_rows(path: Path) -> list[Mapping[str, object]]:
    loaded: object = json.loads(
        path.read_bytes(),
        parse_float=lambda token: token,
        parse_constant=lambda token: token,
    )
    if isinstance(loaded, list):
        candidate = loaded
    elif isinstance(loaded, dict):
        candidate = next(
            (
                loaded[key]
                for key in ("results", "all_results", "runs", "sweep_results")
                if isinstance(loaded.get(key), list)
            ),
            None,
        )
    else:
        candidate = None
    if not isinstance(candidate, list) or not all(isinstance(item, dict) for item in candidate):
        raise HistoricalNormalizationError("selected writer output has no result-row collection")
    return candidate


def _scientific(row: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in row.items() if key not in _OPERATIONAL_FIELDS}


def _number(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _numeric_comparison(
    retained: object,
    fresh: object,
    *,
    path: str = "$",
) -> tuple[list[str], float, float]:
    if type(retained) is type(fresh) and retained == fresh:
        return [], 0.0, 0.0
    if isinstance(retained, bool) or isinstance(fresh, bool):
        return [path], 0.0, 0.0
    if isinstance(retained, int) or isinstance(fresh, int):
        return ([path] if retained != fresh else []), 0.0, 0.0
    retained_number = _number(retained)
    fresh_number = _number(fresh)
    if retained_number is not None and fresh_number is not None:
        absolute = abs(retained_number - fresh_number)
        relative = absolute / max(abs(retained_number), abs(fresh_number), 1e-300)
        mismatch = absolute > 1e-8 and relative > 1e-7
        return ([path] if mismatch else []), absolute, relative
    if isinstance(retained, dict) and isinstance(fresh, dict):
        if set(retained) != set(fresh):
            return [path], 0.0, 0.0
        mismatches: list[str] = []
        max_absolute = 0.0
        max_relative = 0.0
        for key in sorted(retained):
            child, absolute, relative = _numeric_comparison(
                retained[key], fresh[key], path=f"{path}.{key}"
            )
            mismatches.extend(child)
            max_absolute = max(max_absolute, absolute)
            max_relative = max(max_relative, relative)
        return mismatches, max_absolute, max_relative
    if isinstance(retained, list) and isinstance(fresh, list):
        if len(retained) != len(fresh):
            return [path], 0.0, 0.0
        mismatches = []
        max_absolute = 0.0
        max_relative = 0.0
        for index, (retained_item, fresh_item) in enumerate(zip(retained, fresh, strict=True)):
            child, absolute, relative = _numeric_comparison(
                retained_item, fresh_item, path=f"{path}[{index}]"
            )
            mismatches.extend(child)
            max_absolute = max(max_absolute, absolute)
            max_relative = max(max_relative, relative)
        return mismatches, max_absolute, max_relative
    return [path], 0.0, 0.0


def execute_standing_selection(
    *,
    repository_root: Path,
    output_dir: Path,
    python_executable: Path,
    revision: str,
    collection_id: str,
    row_index: int,
    route: Literal["standalone", "flybrian_local", "flybrian_cloud"] = "standalone",
    selection_mode: Literal["exact_prefix", "retained_context"] = "exact_prefix",
    execute_target: bool = True,
) -> dict[str, object]:
    """Run one retained row while replaying the writer's historical decision context."""

    root = repository_root.resolve(strict=True)
    authority = _authority(collection_id)
    source_bytes = (root / authority.source_path).read_bytes()
    if _sha256(source_bytes) != authority.source_sha256:
        raise HistoricalNormalizationError(f"{collection_id} writer differs from reviewed bytes")
    retained_rows = read_collection_rows(authority, repository_root=root)
    if row_index < 0 or row_index >= len(retained_rows):
        raise HistoricalNormalizationError(f"{collection_id} row index is out of range")
    source_row_count = _SOURCE_ROW_COUNTS.get(collection_id, len(retained_rows))
    if row_index >= source_row_count:
        raise HistoricalNormalizationError(
            f"{collection_id} row {row_index} is retained evidence, but its appending "
            "writer source was not recovered"
        )

    target = output_dir.resolve()
    target.mkdir(parents=True, exist_ok=False)
    artifact_dir = target / "artifacts"
    artifact_dir.mkdir()
    premn_source = root / "output/c153_phase0/premn_ids_strong.json"
    if premn_source.is_file():
        premn_target = target / "c153_phase0/premn_ids_strong.json"
        premn_target.parent.mkdir(parents=True)
        shutil.copyfile(premn_source, premn_target)
    if collection_id == "c155-phase1c":
        census_target = target / "c155_phase0/snpp_intermediates.json"
        census_target.parent.mkdir(parents=True, exist_ok=True)
        with tarfile.open(root / "output/c155_phase0.tar.gz", "r:gz") as archive:
            member = archive.extractfile("c155_phase0/snpp_intermediates.json")
            if member is None:
                raise HistoricalNormalizationError(
                    "C155 phase-0 archive lacks snpp_intermediates.json"
                )
            census_target.write_bytes(member.read())
    selected_source = _selected_source(
        source_bytes,
        authority=authority,
        target_row=retained_rows[row_index],
        project_root=root,
        output_dir=artifact_dir,
    )
    launcher = target / "selected_historical_standing.py"
    launcher.write_text(
        "import json, pathlib, sys\n"
        + "from flybrian_engine.historical_standing_selection import _Dispatch\n"
        + "from flybrian_engine.historical_standing_estate import "
        + "STANDING_COLLECTIONS, read_collection_rows\n"
        + "root = pathlib.Path(" + repr(str(root)) + ")\n"
        + "authority = next(x for x in STANDING_COLLECTIONS if x.collection_id == "
        + repr(collection_id) + ")\n"
        + "rows = read_collection_rows(authority, repository_root=root)\n"
        + "__flybrian_dispatch__ = _Dispatch(" + repr(collection_id) + ", rows, "
        + repr(
            0
            if collection_id == "c148-phase0b" and execute_target
            else row_index
            if execute_target
            else -1
        )
        + ", replay_prefix="
        + repr(selection_mode == "exact_prefix") + ")\n"
        + "source = " + repr(selected_source) + "\n"
        + "namespace = {'__file__': str(root / " + repr(authority.source_path) + "), "
        + "'__name__': 'flybrian_historical_selection', "
        + "'__flybrian_dispatch__': __flybrian_dispatch__, "
        + "'__flybrian_capture__': __import__("
        + repr("flybrian_engine.historical_standing_selection")
        + ", fromlist=['_capture_closed_loop_result'])._capture_closed_loop_result, "
        + "'__flybrian_capture_network__': __import__("
        + repr("flybrian_engine.historical_standing_selection")
        + ", fromlist=['_capture_network_projection'])._capture_network_projection}\n"
        + "exec(compile(source, namespace['__file__'], 'exec'), namespace)\n"
        + "organized_root = root / 'scripts'\n"
        + "for imported_module in tuple(sys.modules.values()):\n"
        + "    imported_project = getattr(imported_module, 'PROJECT', None)\n"
        + "    if (imported_project is not None "
        + "and pathlib.Path(imported_project) == organized_root):\n"
        + "        imported_module.PROJECT = root\n"
        + "        imported_output = getattr(imported_module, 'OUT_DIR', None)\n"
        + "        if imported_output is not None:\n"
        + "            imported_output = pathlib.Path(imported_output)\n"
        + "            try:\n"
        + "                imported_relative = imported_output.relative_to(organized_root)\n"
        + "            except ValueError:\n"
        + "                pass\n"
        + "            else:\n"
        + "                imported_module.OUT_DIR = root / imported_relative\n"
        + "namespace['main']()\n"
        + "expected_rows = "
        + repr(1 if collection_id == "c148-phase0b" else source_row_count)
        + "\n"
        + "if __flybrian_dispatch__.index != expected_rows:\n"
        + "    raise RuntimeError(\n"
        + "        f'writer dispatched {__flybrian_dispatch__.index} rows; "
        + "expected {expected_rows}'\n"
        + "    )\n",
        encoding="utf-8",
    )
    stdout_path = target / "stdout.log"
    stderr_path = target / "stderr.log"
    environment = os.environ.copy()
    environment["PYTHONHASHSEED"] = "0"
    environment["MPLCONFIGDIR"] = str(target / "matplotlib")
    engine_source = str(Path(__file__).resolve().parents[1])
    environment["PYTHONPATH"] = os.pathsep.join(
        item for item in (engine_source, environment.get("PYTHONPATH", "")) if item
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
    fresh_path = artifact_dir / Path(authority.archive_member or authority.result_path).name
    if not fresh_path.is_file():
        tail = stderr_path.read_text(encoding="utf-8", errors="replace")[-2_000:]
        raise HistoricalNormalizationError(
            f"selected {collection_id} writer exited with status {completed.returncode} "
            f"before producing its result artifact: {tail}"
        )
    fresh_rows = _fresh_rows(fresh_path)
    expected_fresh_rows = 1 if collection_id == "c148-phase0b" else source_row_count
    if len(fresh_rows) != expected_fresh_rows:
        raise HistoricalNormalizationError(
            f"selected {collection_id} writer emitted {len(fresh_rows)} rows; "
            f"expected {expected_fresh_rows}"
        )
    if not execute_target:
        receipt = {
            "schema_version": "1.0",
            "collection_id": collection_id,
            "source_row_count": source_row_count,
            "retained_row_count": len(retained_rows),
            "writer_result_sha256": _sha256(fresh_path.read_bytes()),
            "writer_exit_status": completed.returncode,
            "stdout_path": str(stdout_path.relative_to(target)),
            "stderr_path": str(stderr_path.relative_to(target)),
        }
        receipt["sha256"] = canonical_sha256(receipt)
        (target / "receipt.json").write_text(
            json.dumps(receipt, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return receipt
    retained_science = _scientific(retained_rows[row_index])
    fresh_index = 0 if collection_id == "c148-phase0b" else row_index
    fresh_science = _scientific(fresh_rows[fresh_index])
    retained_sha = canonical_sha256(retained_science)
    fresh_sha = canonical_sha256(fresh_science)
    differing_fields = sorted(
        key
        for key in set(retained_science) | set(fresh_science)
        if retained_science.get(key) != fresh_science.get(key)
    )
    scientific_path = artifact_dir / "scientific_result.json"
    scientific_path.write_bytes(canonical_json_bytes(fresh_science) + b"\n")
    mismatch_paths, max_absolute_difference, max_relative_difference = _numeric_comparison(
        retained_science, fresh_science
    )
    exact = retained_science == fresh_science
    installed = subprocess.run(
        (str(python_executable.resolve(strict=True)), "-m", "pip", "freeze", "--all"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    python_version = subprocess.run(
        (str(python_executable.resolve(strict=True)), "--version"),
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    receipt: dict[str, object] = {
        "schema_version": "1.0",
        "collection_id": collection_id,
        "row_index": row_index,
        "route": route,
        "selection_mode": selection_mode,
        "writer_exit_status": completed.returncode,
        "source_revision": revision,
        "source_sha256": authority.source_sha256,
        "requested_duration_ms": authority.duration_ms,
        "comparison": {
            "profile_id": "org.flybrian.comparison.standing-local-numeric",
            "profile_version": "1.0",
            "status": (
                "exact"
                if exact
                else "numerically_equivalent"
                if not mismatch_paths
                else "different"
            ),
            "excluded_fields": sorted(_OPERATIONAL_FIELDS),
            "differing_fields": differing_fields,
            "numeric_mismatch_paths": mismatch_paths,
            "absolute_tolerance": "1e-8",
            "relative_tolerance": "1e-7",
            "maximum_absolute_difference": repr(max_absolute_difference),
            "maximum_relative_difference": repr(max_relative_difference),
            "retained_scientific_sha256": retained_sha,
            "fresh_scientific_sha256": fresh_sha,
        },
        "environment": {
            "python": str(python_executable.resolve(strict=True)),
            "python_version": python_version,
            "installed_distributions_sha256": canonical_sha256(
                sorted(line.strip() for line in installed if line.strip())
            ),
        },
        "artifacts": {
            "scientific_result": {
                "path": str(scientific_path.relative_to(target)),
                "sha256": _sha256(scientific_path.read_bytes()),
            },
            "writer_result": {
                "path": str(fresh_path.relative_to(target)),
                "sha256": _sha256(fresh_path.read_bytes()),
            },
        },
        "stdout_path": str(stdout_path.relative_to(target)),
        "stderr_path": str(stderr_path.relative_to(target)),
    }
    qpos_path = artifact_dir / "qpos_trajectory.npy"
    motor_path = artifact_dir / "motor_commands.npy"
    if qpos_path.is_file() and motor_path.is_file():
        artifacts = receipt["artifacts"]
        if not isinstance(artifacts, dict):
            raise HistoricalNormalizationError("standing receipt artifacts are malformed")
        artifacts["qpos_trajectory"] = {
            "path": str(qpos_path.relative_to(target)),
            "sha256": _sha256(qpos_path.read_bytes()),
            "frame_interval_ms": 32,
        }
        artifacts["motor_commands"] = {
            "path": str(motor_path.relative_to(target)),
            "sha256": _sha256(motor_path.read_bytes()),
            "frame_interval_ms": 32,
        }
    receipt["sha256"] = canonical_sha256(receipt)
    (target / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt
