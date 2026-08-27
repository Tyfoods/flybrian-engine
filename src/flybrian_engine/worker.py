"""Isolated durable-runner worker process."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path

from .durable import (
    CompatibilityError,
    _atomic_json,
    _json_object,
    safe_error_message,
    validated_identifier,
)
from .runner import run_experiment
from .schema import ValidationError, validate_experiment_spec


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m flybrian_engine.worker")
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    return parser


def _validated_paths(request_path: Path, result_path: Path, output_root: Path) -> str:
    jobs_root = (output_root.resolve() / ".runner-v1" / "jobs").resolve()
    resolved_request = request_path.resolve()
    resolved_result = result_path.resolve()
    try:
        request_relative = resolved_request.relative_to(jobs_root)
        result_relative = resolved_result.relative_to(jobs_root)
    except ValueError as error:
        raise ValueError(
            "worker control paths must remain inside the runner control root"
        ) from error
    if len(request_relative.parts) != 2 or request_relative.parts[1] != "request.json":
        raise ValueError("worker request path has an invalid shape")
    if result_relative.parts != (request_relative.parts[0], "worker-result.json"):
        raise ValueError("worker result path does not match the request job")
    return validated_identifier(request_relative.parts[0], "run_id")


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        run_id = _validated_paths(args.request, args.result, args.output)
        request = _json_object(args.request)
        if request.get("protocol_version") != "1" or request.get("run_id") != run_id:
            raise ValueError("worker request identity is invalid")
        backend_id = validated_identifier(request.get("backend_id"), "backend_id")
        experiment = request.get("experiment")
        spec = validate_experiment_spec(experiment)
        expected_hash = request.get("experiment_sha256")
        if expected_hash != hashlib.sha256(spec.canonical_bytes()).hexdigest():
            raise ValueError("worker request experiment checksum does not match")
        manifest = run_experiment(
            experiment,
            args.output.resolve(),
            backend_id=backend_id,
            run_id=run_id,
        )
        _atomic_json(args.result, {"protocol_version": "1", "ok": True, "manifest": manifest})
        return 0
    except CompatibilityError as error:
        _atomic_json(
            args.result,
            {
                "protocol_version": "1",
                "ok": False,
                "error": {
                    "code": "incompatible_experiment",
                    "message": "experiment is incompatible with the selected backend",
                    "issues": [issue.__dict__ for issue in error.issues],
                },
            },
        )
    except (
        OSError,
        UnicodeError,
        ValueError,
        KeyError,
        json.JSONDecodeError,
        ValidationError,
    ) as error:
        _atomic_json(
            args.result,
            {
                "protocol_version": "1",
                "ok": False,
                "error": {
                    "code": "worker_execution_failed",
                    "message": safe_error_message(error, args.output),
                },
            },
        )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
