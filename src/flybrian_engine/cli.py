"""Command-line entry point for validation, execution, and local serving."""

from __future__ import annotations

import argparse
import json
import secrets
from collections.abc import Sequence
from pathlib import Path

from .historical_census import build_historical_census
from .historical_estate import HistoricalEstateRoot, inventory_historical_estate
from .historical_normalization import canonical_json_bytes
from .historical_python_backend import HistoricalExecutionError, execute_locked_python_recipe
from .historical_standing import (
    C148_PHASE0_RESULT_PATH,
    C148_PHASE0_SOURCE_PATH,
    build_c148_phase0_normalization_bundle,
    execute_c148_phase0_selection,
)
from .historical_standing_estate import (
    STANDING_COLLECTIONS,
    audit_standing_estate,
    build_standing_estate_normalization_bundle,
)
from .historical_standing_selection import execute_standing_selection
from .reviewed_champions import build_reviewed_c174_normalization_bundle
from .runner import CompatibilityError, create_server, default_registry, run_experiment
from .schema import ValidationError, validate_experiment_spec
from .version import __version__


def _load(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="flybrian-engine")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("health")
    validate = commands.add_parser("validate")
    validate.add_argument("experiment", type=Path)
    run = commands.add_parser("run")
    run.add_argument("experiment", type=Path)
    run.add_argument("--backend", default="reference")
    run.add_argument("--output", type=Path, default=Path("flybrian-runs"))
    historical = commands.add_parser("run-historical")
    historical.add_argument("bundle_id", choices=["reviewed-c174"])
    historical.add_argument(
        "--route",
        choices=["standalone", "flybrian_local", "flybrian_cloud"],
        default="flybrian_local",
    )
    historical.add_argument("--source-root", type=Path, required=True)
    historical.add_argument("--python", type=Path, required=True)
    historical.add_argument("--output", type=Path, required=True)
    census = commands.add_parser("census-historical")
    census.add_argument("--repository-root", type=Path, required=True)
    census.add_argument("--output-root", type=Path, required=True)
    census.add_argument("--revision", required=True)
    census.add_argument("--output", type=Path, required=True)
    normalize_standing = commands.add_parser("normalize-historical-standing")
    normalize_standing.add_argument("collection", choices=["c148-phase0", "standing-estate"])
    normalize_standing.add_argument("--repository-root", type=Path, required=True)
    normalize_standing.add_argument("--revision", required=True)
    normalize_standing.add_argument("--output", type=Path, required=True)
    run_standing = commands.add_parser("run-historical-standing")
    run_standing.add_argument("collection", choices=["c148-phase0"])
    run_standing.add_argument("--repository-root", type=Path, required=True)
    run_standing.add_argument("--python", type=Path, required=True)
    run_standing.add_argument("--revision", required=True)
    run_standing.add_argument("--config", required=True)
    run_standing.add_argument("--seed", type=int, required=True)
    run_standing.add_argument(
        "--route",
        choices=["standalone", "flybrian_local", "flybrian_cloud"],
        default="standalone",
    )
    run_standing.add_argument("--output", type=Path, required=True)
    run_standing_row = commands.add_parser("run-historical-standing-row")
    run_standing_row.add_argument(
        "collection",
        choices=[
            item.collection_id
            for item in STANDING_COLLECTIONS
            if item.collection_id != "c148-phase0"
        ],
    )
    run_standing_row.add_argument("--repository-root", type=Path, required=True)
    run_standing_row.add_argument("--python", type=Path, required=True)
    run_standing_row.add_argument("--revision", required=True)
    run_standing_row.add_argument("--row", type=int, required=True)
    run_standing_row.add_argument(
        "--route",
        choices=["standalone", "flybrian_local", "flybrian_cloud"],
        default="standalone",
    )
    run_standing_row.add_argument(
        "--selection-mode",
        choices=["exact_prefix", "retained_context"],
        default="exact_prefix",
    )
    run_standing_row.add_argument("--output", type=Path, required=True)
    audit_standing = commands.add_parser("audit-historical-standing")
    audit_standing.add_argument("--repository-root", type=Path, required=True)
    audit_standing.add_argument("--revision", required=True)
    audit_standing.add_argument("--output", type=Path, required=True)
    local = commands.add_parser("serve")
    local.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "::1"])
    local.add_argument("--port", default=8765, type=int)
    local.add_argument("--token")
    local.add_argument("--output", type=Path, default=Path("flybrian-runs"))
    local.add_argument("--workers", default=1, type=int)
    local.add_argument("--max-queued", default=64, type=int)
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "health":
            print(
                json.dumps(
                    {
                        "status": "healthy",
                        "engine_version": __version__,
                        "protocol_version": "1",
                        "backends": [item.__dict__ for item in default_registry().capabilities()],
                    },
                    sort_keys=True,
                )
            )
        elif args.command == "validate":
            spec = validate_experiment_spec(_load(args.experiment))
            print(json.dumps({"valid": True, "sha256": spec.sha256()}, sort_keys=True))
        elif args.command == "run":
            result = run_experiment(_load(args.experiment), args.output, args.backend)
            print(json.dumps(result, sort_keys=True))
        elif args.command == "run-historical":
            bundle = build_reviewed_c174_normalization_bundle()
            recipe = next(item for item in bundle.recipes if item.route == args.route)
            receipt = execute_locked_python_recipe(
                recipe,
                bundle.inputs,
                bundle.artifacts,
                source_root=args.source_root,
                output_dir=args.output,
                python_executable=args.python,
            )
            print(json.dumps(receipt.to_dict(), sort_keys=True))
        elif args.command == "census-historical":
            repository_root = args.repository_root.resolve(strict=True)
            output_root = args.output_root.resolve(strict=True)
            inventory = inventory_historical_estate(
                HistoricalEstateRoot(
                    root_id="org.flybrian.estate.historical-output",
                    revision=args.revision,
                    logical_root="output",
                    license_id="NOASSERTION",
                    access="private",
                    redistribution="unknown",
                    physical_root=output_root,
                )
            )
            census = build_historical_census(
                inventory,
                evidence_root=output_root,
                repository_root=repository_root,
                source_index_path=repository_root / "consolidation/experiments_index.json",
            )
            args.output.write_bytes(census.canonical_bytes() + b"\n")
            print(
                json.dumps(
                    {
                        "census_sha256": census.sha256,
                        "inventory_sha256": census.inventory_sha256,
                        "reconciled_file_count": census.reconciled_file_count,
                        "run_candidate_count": len(census.run_candidates),
                        "indexed_source_count": census.indexed_source_count,
                    },
                    sort_keys=True,
                )
            )
        elif args.command == "normalize-historical-standing":
            repository_root = args.repository_root.resolve(strict=True)
            if args.collection == "c148-phase0":
                bundle = build_c148_phase0_normalization_bundle(
                    source_bytes=(repository_root / C148_PHASE0_SOURCE_PATH).read_bytes(),
                    result_bytes=(repository_root / C148_PHASE0_RESULT_PATH).read_bytes(),
                    revision=args.revision,
                )
            else:
                bundle = build_standing_estate_normalization_bundle(
                    repository_root=repository_root,
                    revision=args.revision,
                )
            args.output.write_bytes(canonical_json_bytes(bundle.to_dict()) + b"\n")
            print(
                json.dumps(
                    {
                        "bundle_sha256": bundle.sha256,
                        "definition_count": len(bundle.definitions),
                        "occurrence_count": len(bundle.occurrences),
                        "recipe_count": len(bundle.recipes),
                    },
                    sort_keys=True,
                )
            )
        elif args.command == "run-historical-standing":
            receipt = execute_c148_phase0_selection(
                source_root=args.repository_root,
                output_dir=args.output,
                python_executable=args.python,
                revision=args.revision,
                config_name=args.config,
                seed=args.seed,
                route=args.route,
            )
            print(json.dumps(receipt, sort_keys=True))
        elif args.command == "run-historical-standing-row":
            receipt = execute_standing_selection(
                repository_root=args.repository_root,
                output_dir=args.output,
                python_executable=args.python,
                revision=args.revision,
                collection_id=args.collection,
                row_index=args.row,
                route=args.route,
                selection_mode=args.selection_mode,
            )
            print(json.dumps(receipt, sort_keys=True))
        elif args.command == "audit-historical-standing":
            receipt = audit_standing_estate(
                repository_root=args.repository_root.resolve(strict=True),
                revision=args.revision,
            )
            args.output.write_bytes(canonical_json_bytes(receipt) + b"\n")
            print(
                json.dumps(
                    {
                        "receipt_sha256": receipt["sha256"],
                        "collection_count": receipt["collection_count"],
                        "run_row_count": receipt["run_row_count"],
                        "unresolved_result_count": len(receipt["unresolved_results"]),
                    },
                    sort_keys=True,
                )
            )
        else:
            token = args.token or secrets.token_urlsafe(32)
            server = create_server(
                host=args.host,
                port=args.port,
                token=token,
                output_dir=args.output,
                max_workers=args.workers,
                max_queued=args.max_queued,
            )
            connection = {
                "host": args.host,
                "port": server.server_port,
                "token": token,
                "protocol_version": "1",
            }
            print(json.dumps(connection, sort_keys=True), flush=True)
            try:
                server.serve_forever()
            finally:
                server.server_close()
    except CompatibilityError as error:
        print(
            json.dumps(
                {
                    "error": "experiment is incompatible with the selected backend",
                    "issues": [issue.__dict__ for issue in error.issues],
                },
                sort_keys=True,
            )
        )
        return 2
    except (
        HistoricalExecutionError,
        OSError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
        ValidationError,
    ) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
