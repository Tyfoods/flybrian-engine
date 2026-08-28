"""Command-line entry point for validation, execution, and local serving."""

from __future__ import annotations

import argparse
import json
import secrets
from collections.abc import Sequence
from pathlib import Path

from .historical_python_backend import HistoricalExecutionError, execute_locked_python_recipe
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
