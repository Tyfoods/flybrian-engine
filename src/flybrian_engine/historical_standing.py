"""Reviewed normalization profiles for historical framework standing experiments."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

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
from .historical_python_backend import validate_historical_input_references

C148_PHASE0_SOURCE_PATH = "scripts/standing/c148_phase0_standing_test.py"
C148_PHASE0_RESULT_PATH = "output/c148_phase0/phase0_results.json"
C148_PHASE0_SOURCE_SHA256 = "321fe10609d7926da4a3ac8bd0b94a0a249d0b90240d25aedc5572c43d4ca784"
C148_PHASE0_RESULT_SHA256 = "dbc9abdab7c7b1bedb3f7bd266efc134ada65798de09f35de869d8697ab5337b"
C148_PHASE0_DURATION_MS = 3_000
C148_PHASE0_ORIGINAL_PATH = "scripts/c148_phase0_standing_test.py"

_C148_PHASE0_INPUTS = (
    HistoricalInputReference(
        "org.flybrian.input.c148-phase0.connectivity-part-1",
        "file",
        "flybrian/data/unique_pairs_by_id_part1.csv",
        49_309_654,
        "b7c58ed0439247aed662e5e9ef71a766813f20748a065e435269fc6077b0ae9c",
        1,
        "MANC connectivity part consumed by load_connectivity().",
    ),
    HistoricalInputReference(
        "org.flybrian.input.c148-phase0.connectivity-part-2",
        "file",
        "flybrian/data/unique_pairs_by_id_part2.csv",
        48_494_576,
        "08225c0765f363d96f30281d6a4b594b7a4b9bff3f33dd7798928cdf624d9c26",
        1,
        "MANC connectivity part consumed by load_connectivity().",
    ),
    HistoricalInputReference(
        "org.flybrian.input.c148-phase0.connectivity-part-3",
        "file",
        "flybrian/data/unique_pairs_by_id_part3.csv",
        1_674_751,
        "785463bbe090103d36246a1d5a1f9579248315cfa7deb784f5a921214108709b",
        1,
        "MANC connectivity part consumed by load_connectivity().",
    ),
    HistoricalInputReference(
        "org.flybrian.input.c148-phase0.dependency-lock",
        "file",
        "flybrian/requirements.txt",
        2_195,
        "6dbeb0e52b2694f2a5171ef0b799dfbbc772424592d086b879b3b20ce40df4fb",
        1,
        "Scientific Python dependency lock retained with the source tree.",
    ),
    HistoricalInputReference(
        "org.flybrian.input.c148-phase0.e1i1-connectivity",
        "file",
        "output/d3_cycle120_e1i1_module_connectivity/e1i1_module_connectivity.json",
        22_120,
        "4482ea98b1ca893d5f9681a79299ffe1b57abf8371b70e15bbac61c57aa21e5d",
        1,
        "Retained C120 E1/I1 module connectivity consumed by the C148 circuit.",
    ),
    HistoricalInputReference(
        "org.flybrian.input.c148-phase0.flybody-model-tree",
        "tree",
        "flybrian/digifly/flybody_model",
        148_548_369,
        "cf6ae63b653117e0bab9cd9c22db0240716287b8a9d589c125a771f58668ffb8",
        179,
        "Retained FlyBody MuJoCo model tree used by the historical environment.",
    ),
    HistoricalInputReference(
        "org.flybrian.input.c148-phase0.module-memberships",
        "file",
        "output/d3_cycle119_module_discovery/module_memberships.json",
        37_958,
        "4f6c540ee42b08fd4f2326c33a4d36418d853f505a26f935ac4c2b41a7f0f6cd",
        1,
        "Retained C119 motor-module membership data consumed by C148.",
    ),
    HistoricalInputReference(
        "org.flybrian.input.c148-phase0.per-joint-pathway-atlas",
        "file",
        "output/c139_phase1/per_joint_pathway_atlas.json",
        244_612,
        "9f0dbf5837b16afe5f5b9edc98de9fddf76d47b7678e123a51bd459f27a08cbb",
        1,
        "Retained C139 sensory pathway atlas consumed by C148.",
    ),
    HistoricalInputReference(
        "org.flybrian.input.c148-phase0.rl-stance-kinematics",
        "file",
        "flybrian/digifly/rl_reference/walking_forward_kinematics.npz",
        3_474_800,
        "aade2f47aeebac5d5fe124d4b1fb8335ea7706844d7c24a4f7d61feb5c029814",
        1,
        "RL walking kinematics from which the C148 stance targets are derived.",
    ),
)


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _slug(value: str) -> str:
    return value.casefold().replace("_", "-").replace(".", "-")


def _decimal_text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise HistoricalNormalizationError(f"{path} must preserve an exact JSON decimal token")
    return value


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HistoricalNormalizationError(f"{path} must be an integer")
    return value


def _boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise HistoricalNormalizationError(f"{path} must be boolean")
    return value


def _text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoricalNormalizationError(f"{path} must be non-empty text")
    return value


def _source_authority(source_bytes: bytes, revision: str) -> HistoricalSourceAuthority:
    if _digest(source_bytes) != C148_PHASE0_SOURCE_SHA256:
        raise HistoricalNormalizationError("C148 phase-0 source differs from its reviewed bytes")
    return HistoricalSourceAuthority(
        repository="flybrian-serve",
        revision=revision,
        logical_path=C148_PHASE0_SOURCE_PATH,
        byte_length=len(source_bytes),
        sha256=C148_PHASE0_SOURCE_SHA256,
        license_id="proprietary-unpublished",
        access="private",
        redistribution="not-allowed",
        extractor_id=STATIC_PYTHON_EXTRACTOR_ID,
        extractor_version=STATIC_PYTHON_EXTRACTOR_VERSION,
    )


def _records(result_bytes: bytes) -> list[Mapping[str, object]]:
    if _digest(result_bytes) != C148_PHASE0_RESULT_SHA256:
        raise HistoricalNormalizationError("C148 phase-0 result differs from its reviewed bytes")
    loaded: object = json.loads(result_bytes, parse_float=str)
    if not isinstance(loaded, list) or len(loaded) != 25:
        raise HistoricalNormalizationError("C148 phase-0 result must contain 25 run records")
    records: list[Mapping[str, object]] = []
    for index, item in enumerate(loaded):
        if not isinstance(item, dict) or set(item) != {
            "config",
            "motor_scale",
            "use_rl_targets",
            "seed",
            "standing_metrics",
            "elapsed_s",
        }:
            raise HistoricalNormalizationError(
                f"C148 phase-0 result row {index} has an unreviewed shape"
            )
        records.append(item)
    return records


class _C148Phase0Selector(ast.NodeTransformer):
    def __init__(
        self,
        *,
        config_name: str,
        seed: int,
        output_dir: Path,
        project_root: Path,
    ) -> None:
        self.config_name = config_name
        self.seed = seed
        self.output_dir = output_dir
        self.project_root = project_root
        self.config_loop_count = 0
        self.seed_loop_count = 0
        self.project_assignment_count = 0
        self.result_capture_count = 0

    def visit_Assign(self, node: ast.Assign) -> ast.AST | list[ast.AST]:
        node = self.generic_visit(node)
        assigned_names = {
            target.id for target in node.targets if isinstance(target, ast.Name)
        }
        if "PROJECT" in assigned_names:
            node.value = ast.Call(
                func=ast.Name(id="Path", ctx=ast.Load()),
                args=[ast.Constant(value=str(self.project_root))],
                keywords=[],
            )
            self.project_assignment_count += 1
        if "OUT_DIR" in assigned_names:
            node.value = ast.Call(
                func=ast.Name(id="Path", ctx=ast.Load()),
                args=[ast.Constant(value=str(self.output_dir))],
                keywords=[],
            )
        if (
            assigned_names == {"results"}
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "run_closed_loop_from_network"
        ):
            capture = ast.parse(
                "np.save(OUT_DIR / 'qpos_trajectory.npy', "
                "np.asarray(results.qpos_history))\n"
                "np.save(OUT_DIR / 'motor_commands.npy', "
                "np.asarray(results.motor_commands))\n"
            ).body
            self.result_capture_count += 1
            return [node, *capture]
        return node

    def visit_For(self, node: ast.For) -> ast.AST:
        node = self.generic_visit(node)
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
                                comparators=[ast.Constant(value=self.config_name)],
                            )
                        ],
                        is_async=0,
                    )
                ],
            )
            self.config_loop_count += 1
        if (
            isinstance(node.target, ast.Name)
            and node.target.id == "seed"
            and isinstance(node.iter, ast.Name)
            and node.iter.id == "seeds"
        ):
            node.iter = ast.List(elts=[ast.Constant(value=self.seed)], ctx=ast.Load())
            self.seed_loop_count += 1
        return node


def _selected_c148_phase0_source(
    source_bytes: bytes,
    *,
    config_name: str,
    seed: int,
    output_dir: Path,
    project_root: Path,
) -> str:
    try:
        tree = ast.parse(source_bytes, filename=C148_PHASE0_ORIGINAL_PATH)
    except SyntaxError as error:
        raise HistoricalNormalizationError("C148 phase-0 source cannot be parsed") from error
    selector = _C148Phase0Selector(
        config_name=config_name,
        seed=seed,
        output_dir=output_dir,
        project_root=project_root,
    )
    transformed = selector.visit(tree)
    ast.fix_missing_locations(transformed)
    if (
        selector.project_assignment_count != 1
        or selector.config_loop_count != 1
        or selector.seed_loop_count != 1
        or selector.result_capture_count != 1
    ):
        raise HistoricalNormalizationError(
            "C148 phase-0 source no longer has its reviewed config/seed sweep shape"
        )
    return ast.unparse(transformed)


def _scientific_result(record: Mapping[str, object]) -> dict[str, object]:
    return {key: value for key, value in record.items() if key != "elapsed_s"}


def execute_c148_phase0_selection(
    *,
    source_root: Path,
    output_dir: Path,
    python_executable: Path,
    revision: str,
    config_name: str,
    seed: int,
    route: Literal["standalone", "flybrian_local"] = "standalone",
) -> dict[str, object]:
    """Execute one retained C148 row by selecting its original sweep coordinates."""

    root = source_root.resolve(strict=True)
    source_path = root / C148_PHASE0_SOURCE_PATH
    result_path = root / C148_PHASE0_RESULT_PATH
    source_bytes = source_path.read_bytes()
    result_bytes = result_path.read_bytes()
    _source_authority(source_bytes, revision)
    validate_historical_input_references(_C148_PHASE0_INPUTS, source_root=root)
    records = _records(result_bytes)
    matching = [
        record
        for record in records
        if record["config"] == config_name and record["seed"] == seed
    ]
    if len(matching) != 1:
        raise HistoricalNormalizationError(
            "C148 phase-0 selection does not identify exactly one retained run"
        )
    row_index = records.index(matching[0])
    bundle = build_c148_phase0_normalization_bundle(
        source_bytes=source_bytes,
        result_bytes=result_bytes,
        revision=revision,
    )
    selected_definition = next(
        definition
        for definition in bundle.definitions
        if definition.scientific_configuration["selector"] == {"config": config_name}
        and definition.scientific_configuration["random_seed"] == seed
    )
    selected_recipe = next(
        recipe
        for recipe in bundle.recipes
        if recipe.definition_id == selected_definition.definition_id and recipe.route == route
    )
    target = output_dir.resolve()
    target.mkdir(parents=True, exist_ok=False)
    artifact_dir = target / "artifacts"
    artifact_dir.mkdir()
    selected_source = _selected_c148_phase0_source(
        source_bytes,
        config_name=config_name,
        seed=seed,
        output_dir=artifact_dir,
        project_root=root,
    )
    launcher = target / "selected_c148_phase0.py"
    launcher.write_text(
        "source = "
        + repr(selected_source)
        + "\nnamespace = {'__file__': "
        + repr(str(root / C148_PHASE0_ORIGINAL_PATH))
        + ", '__name__': 'flybrian_historical_selection'}\n"
        + "exec(compile(source, namespace['__file__'], 'exec'), namespace)\n"
        + "import pathlib, sys\n"
        + "project_root = pathlib.Path("
        + repr(str(root))
        + ")\n"
        + "organized_root = project_root / 'scripts'\n"
        + "for imported_module in tuple(sys.modules.values()):\n"
        + "    imported_project = getattr(imported_module, 'PROJECT', None)\n"
        + "    if imported_project is not None "
        + "and pathlib.Path(imported_project) == organized_root:\n"
        + "        imported_module.PROJECT = project_root\n"
        + "namespace['main']()\n",
        encoding="utf-8",
    )
    stdout_path = target / "stdout.log"
    stderr_path = target / "stderr.log"
    environment = os.environ.copy()
    environment["PYTHONHASHSEED"] = "0"
    environment["MPLCONFIGDIR"] = str(target / "matplotlib")
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        completed = subprocess.run(
            (str(python_executable.resolve(strict=True)), str(launcher)),
            cwd=root,
            env=environment,
            stdout=stdout,
            stderr=stderr,
            check=False,
        )
    if completed.returncode != 0:
        raise HistoricalNormalizationError(
            f"selected C148 phase-0 source exited with status {completed.returncode}"
        )
    fresh_path = artifact_dir / "phase0_results.json"
    qpos_path = artifact_dir / "qpos_trajectory.npy"
    motor_commands_path = artifact_dir / "motor_commands.npy"
    fresh_records = json.loads(fresh_path.read_bytes(), parse_float=str)
    if not isinstance(fresh_records, list) or len(fresh_records) != 1:
        raise HistoricalNormalizationError("selected C148 phase-0 run did not emit one result row")
    fresh = fresh_records[0]
    if not isinstance(fresh, dict):
        raise HistoricalNormalizationError("selected C148 phase-0 result row is malformed")
    retained_science = _scientific_result(matching[0])
    fresh_science = _scientific_result(fresh)
    scientific_result_path = artifact_dir / "scientific_result.json"
    scientific_result_path.write_bytes(canonical_json_bytes(fresh_science) + b"\n")
    equal = retained_science == fresh_science
    differing_fields = sorted(
        key
        for key in set(retained_science) | set(fresh_science)
        if retained_science.get(key) != fresh_science.get(key)
    )
    receipt: dict[str, object] = {
        "schema_version": "1.0",
        "family_id": "org.flybrian.family.c148-phase0-standing-test",
        "definition_id": selected_definition.definition_id,
        "recipe_id": selected_recipe.recipe_id,
        "recipe_sha256": selected_recipe.sha256,
        "route": route,
        "source_revision": revision,
        "source_sha256": C148_PHASE0_SOURCE_SHA256,
        "original_logical_path": C148_PHASE0_ORIGINAL_PATH,
        "selector": {"config": config_name, "seed": seed},
        "requested_duration_ms": C148_PHASE0_DURATION_MS,
        "comparison": {
            "status": "equal" if equal else "different",
            "excluded_fields": ["elapsed_s"],
            "differing_fields": differing_fields,
            "retained_scientific_sha256": canonical_sha256(retained_science),
            "fresh_scientific_sha256": canonical_sha256(fresh_science),
        },
        "artifacts": [
            {
                "artifact_id": (
                    f"org.flybrian.artifact.c148-phase0-row-{row_index}-motor-commands"
                ),
                "kind": "motor_commands",
                "captured_path": str(motor_commands_path.relative_to(target)),
                "sha256": _digest(motor_commands_path.read_bytes()),
                "frame_interval_ms": 32,
            },
            {
                "artifact_id": (
                    f"org.flybrian.artifact.c148-phase0-row-{row_index}-qpos-trajectory"
                ),
                "kind": "qpos_trajectory",
                "captured_path": str(qpos_path.relative_to(target)),
                "sha256": _digest(qpos_path.read_bytes()),
                "frame_interval_ms": 32,
            },
            {
                "artifact_id": next(
                    artifact.artifact_id
                    for artifact in bundle.artifacts
                    if artifact.definition_id == selected_definition.definition_id
                    and artifact.kind == "scientific_result"
                ),
                "kind": "scientific_result",
                "captured_path": str(scientific_result_path.relative_to(target)),
                "sha256": _digest(scientific_result_path.read_bytes()),
                "frame_interval_ms": None,
            },
        ],
        "retained_result_sha256": C148_PHASE0_RESULT_SHA256,
        "stdout_path": str(stdout_path.relative_to(target)),
        "stderr_path": str(stderr_path.relative_to(target)),
    }
    receipt["sha256"] = canonical_sha256(receipt)
    (target / "receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return receipt


def build_c148_phase0_normalization_bundle(
    *,
    source_bytes: bytes,
    result_bytes: bytes,
    revision: str,
) -> HistoricalNormalizationBundle:
    """Normalize the exact five-configuration by five-seed C148 phase-0 standing sweep."""

    source = _source_authority(source_bytes, revision)
    definitions: list[NormalizedExperimentDefinition] = []
    claims: list[HistoricalClaim] = []
    occurrences: list[HistoricalRunOccurrence] = []
    artifacts: list[HistoricalArtifactReference] = []
    recipes: list[HistoricalExecutionRecipe] = []
    observed_combinations: set[tuple[str, bool, int]] = set()

    for index, record in enumerate(_records(result_bytes)):
        config_name = _text(record["config"], f"records[{index}].config")
        motor_scale = _decimal_text(record["motor_scale"], f"records[{index}].motor_scale")
        use_rl_targets = _boolean(
            record["use_rl_targets"], f"records[{index}].use_rl_targets"
        )
        seed = _integer(record["seed"], f"records[{index}].seed")
        observed_combinations.add((motor_scale, use_rl_targets, seed))
        configuration: dict[str, object] = {
            "schema_version": "1.0",
            "requested_duration_ms": C148_PHASE0_DURATION_MS,
            "effective_duration_ms": C148_PHASE0_DURATION_MS,
            "random_seed": seed,
            "selector": {"config": config_name},
            "option_definitions": [
                {
                    "option_id": "motor_scale",
                    "label": "Motor scale",
                    "value_kind": "decimal",
                    "unit": "1",
                },
                {
                    "option_id": "use_rl_targets",
                    "label": "Use RL stance targets",
                    "value_kind": "boolean",
                    "unit": None,
                },
            ],
            "option_resolutions": [
                {
                    "option_id": "motor_scale",
                    "effective_value": motor_scale,
                    "origin": "recorded_result",
                },
                {
                    "option_id": "use_rl_targets",
                    "effective_value": use_rl_targets,
                    "origin": "recorded_result",
                },
            ],
        }
        identity = canonical_sha256(
            {
                "source_sha256": source.sha256,
                "duration_ms": C148_PHASE0_DURATION_MS,
                "motor_scale": motor_scale,
                "use_rl_targets": use_rl_targets,
                "seed": seed,
            }
        )
        definition_id = f"org.flybrian.definition.c148-phase0-{identity[:16]}"
        definition = NormalizedExperimentDefinition(
            definition_id=definition_id,
            version="1.0",
            family_id="org.flybrian.family.c148-phase0-standing-test",
            scientific_configuration=configuration,
            source=source,
        )
        claim_id = f"org.flybrian.claim.c148-phase0-{_slug(config_name)}-s{seed}"
        occurrence_id = f"org.flybrian.occurrence.c148-phase0-row-{index}"
        artifact_id = f"org.flybrian.artifact.c148-phase0-row-{index}-result-batch"
        scientific_result_bytes = canonical_json_bytes(_scientific_result(record)) + b"\n"
        scientific_result_artifact_id = (
            f"org.flybrian.artifact.c148-phase0-row-{index}-scientific-result"
        )
        definitions.append(definition)
        claims.append(
            HistoricalClaim(
                claim_id=claim_id,
                definition_id=definition_id,
                name=f"C148 phase 0 — {config_name}, seed {seed}",
                description=(
                    "A retained 3,000 ms C148 standing run comparing RL-derived stance targets "
                    f"with the zero-position baseline at motor scale {motor_scale}."
                ),
                tags=("c148", "historical", "standing"),
            )
        )
        occurrences.append(
            HistoricalRunOccurrence(
                occurrence_id=occurrence_id,
                definition_id=definition_id,
                claim_ids=(claim_id,),
                evidence=(
                    f"{C148_PHASE0_RESULT_PATH}#/{index}",
                    f"result SHA-256 {C148_PHASE0_RESULT_SHA256}",
                    f"source SHA-256 {C148_PHASE0_SOURCE_SHA256}",
                ),
            )
        )
        artifacts.append(
            HistoricalArtifactReference(
                artifact_id=artifact_id,
                definition_id=definition_id,
                kind="result_batch",
                logical_path=C148_PHASE0_RESULT_PATH,
                byte_length=len(result_bytes),
                sha256=C148_PHASE0_RESULT_SHA256,
                disposition="bound",
                disposition_reason=(
                    f"JSON pointer /{index} is the retained result row for this occurrence."
                ),
                comparison="canonical_json",
                excluded_json_fields=("elapsed_s",),
            )
        )
        artifacts.append(
            HistoricalArtifactReference(
                artifact_id=scientific_result_artifact_id,
                definition_id=definition_id,
                kind="scientific_result",
                logical_path=f"normalized/c148-phase0/row-{index}/scientific_result.json",
                byte_length=len(scientific_result_bytes),
                sha256=_digest(scientific_result_bytes),
                disposition="bound",
                disposition_reason=(
                    f"Canonical scientific projection of retained JSON pointer /{index}; "
                    "elapsed_s is wall-clock evidence."
                ),
                comparison="canonical_json",
            )
        )
        input_ids = tuple(item.input_id for item in _C148_PHASE0_INPUTS)
        for route in ("standalone", "flybrian_local"):
            recipes.append(
                HistoricalExecutionRecipe(
                    recipe_id=f"org.flybrian.recipe.c148-phase0-row-{index}.{route}",
                    definition_id=definition_id,
                    definition_sha256=definition.scientific_identity_sha256,
                    route=route,
                    executor_id="org.flybrian.executor.selected-historical-sweep",
                    executor_version="1.0",
                    source=source,
                    argv=(
                        C148_PHASE0_SOURCE_PATH,
                        "--flybrian-config",
                        config_name,
                        "--flybrian-seed",
                        str(seed),
                    ),
                    input_ids=input_ids,
                    artifact_ids=(scientific_result_artifact_id,),
                )
            )

    expected = {
        (motor_scale, use_rl_targets, seed)
        for motor_scale, use_rl_targets in (
            ("0.0", True),
            ("0.1", True),
            ("0.25", True),
            ("0.5", True),
            ("0.5", False),
        )
        for seed in range(5)
    }
    if observed_combinations != expected:
        raise HistoricalNormalizationError(
            "C148 phase-0 rows do not match the reviewed five-configuration, five-seed sweep"
        )
    return HistoricalNormalizationBundle(
        bundle_id="org.flybrian.normalization.c148-phase0-standing",
        version="1.0",
        definitions=tuple(definitions),
        claims=tuple(claims),
        occurrences=tuple(occurrences),
        inputs=_C148_PHASE0_INPUTS,
        artifacts=tuple(artifacts),
        recipes=tuple(recipes),
    )
