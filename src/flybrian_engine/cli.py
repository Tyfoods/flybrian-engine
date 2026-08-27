"""Command-line entry point for validation, execution, and local serving."""

from __future__ import annotations

import argparse
import json
import secrets
from collections.abc import Sequence
from pathlib import Path

from . import __version__
from .runner import default_registry, run_experiment, serve
from .schema import ValidationError, validate_experiment_spec


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
    local = commands.add_parser("serve")
    local.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "::1"])
    local.add_argument("--port", default=8765, type=int)
    local.add_argument("--token")
    local.add_argument("--output", type=Path, default=Path("flybrian-runs"))
    return root


def main(argv: Sequence[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "health":
            print(json.dumps({
                "status": "healthy",
                "engine_version": __version__,
                "protocol_version": "1",
                "backends": [item.__dict__ for item in default_registry().capabilities()],
            }, sort_keys=True))
        elif args.command == "validate":
            spec = validate_experiment_spec(_load(args.experiment))
            print(json.dumps({"valid": True, "sha256": spec.sha256()}, sort_keys=True))
        elif args.command == "run":
            result = run_experiment(_load(args.experiment), args.output, args.backend)
            print(json.dumps(result, sort_keys=True))
        else:
            token = args.token or secrets.token_urlsafe(32)
            connection = {"host": args.host, "port": args.port, "token": token}
            print(json.dumps(connection, sort_keys=True), flush=True)
            serve(host=args.host, port=args.port, token=token, output_dir=args.output)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, ValidationError) as error:
        print(json.dumps({"error": str(error)}, sort_keys=True))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
