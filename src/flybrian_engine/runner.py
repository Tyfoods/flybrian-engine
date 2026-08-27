"""Engine composition and cross-platform loopback HTTP protocol."""

from __future__ import annotations

import json
import re
import secrets
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .backends import BackendRegistry, CompatibilityIssue, assess_backend_compatibility
from .brian2_backend import Brian2Backend
from .reference import ReferenceBackend
from .schema import ValidationError, validate_experiment_spec
from .version import __version__


class CompatibilityError(ValueError):
    """A valid experiment cannot be executed by the selected backend."""

    def __init__(self, issues: tuple[CompatibilityIssue, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))


_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _validated_identifier(value: object, name: str) -> str:
    if not isinstance(value, str) or _RUN_ID.fullmatch(value) is None:
        raise ValidationError(
            f"{name} must be a 1-64 character opaque identifier using "
            "letters, digits, '.', '_', or '-'"
        )
    return value


def default_registry() -> BackendRegistry:
    registry = BackendRegistry()
    registry.register(ReferenceBackend())
    registry.register(Brian2Backend())
    return registry


def run_experiment(
    value: Any,
    output_dir: Path,
    backend_id: str = "reference",
    run_id: str | None = None,
) -> dict[str, object]:
    spec = validate_experiment_spec(value)
    resolved_run_id = _validated_identifier(
        run_id if run_id is not None else f"run_{uuid.uuid4().hex}",
        "run_id",
    )
    resolved_backend_id = _validated_identifier(backend_id, "backend_id")
    backend = default_registry().get(resolved_backend_id)
    issues = assess_backend_compatibility(
        spec,
        backend.capabilities,
        engine_version=__version__,
    ) + backend.compatibility_issues(spec)
    if issues:
        raise CompatibilityError(issues)
    manifest = backend.run(spec, output_dir, resolved_run_id)
    return manifest.to_dict()


def create_server(*, host: str, port: int, token: str, output_dir: Path) -> ThreadingHTTPServer:
    registry = default_registry()

    class Handler(BaseHTTPRequestHandler):
        server_version = "flybrian-engine/0.1"

        def _json(self, status: HTTPStatus, value: object) -> None:
            body = json.dumps(value, sort_keys=True).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            return secrets.compare_digest(self.headers.get("Authorization", ""), f"Bearer {token}")

        def do_GET(self) -> None:
            if self.path == "/v1/health":
                self._json(HTTPStatus.OK, {"status": "healthy", "protocol_version": "1"})
                return
            if not self._authorized():
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "authorization required"})
                return
            if self.path == "/v1/capabilities":
                self._json(HTTPStatus.OK, {
                    "protocol_version": "1",
                    "backends": [capability.__dict__ for capability in registry.capabilities()],
                })
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

        def do_POST(self) -> None:
            if not self._authorized():
                self._json(HTTPStatus.UNAUTHORIZED, {"error": "authorization required"})
                return
            if self.path != "/v1/runs":
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 10 * 1024 * 1024:
                    raise ValidationError("request body must be between 1 byte and 10 MiB")
                body = json.loads(self.rfile.read(length))
                if not isinstance(body, dict) or "experiment" not in body:
                    raise ValidationError("request must contain experiment")
                result = run_experiment(
                    body["experiment"],
                    output_dir,
                    backend_id=body.get("backend_id", "reference"),
                    run_id=body.get("run_id"),
                )
                self._json(HTTPStatus.CREATED, result)
            except CompatibilityError as error:
                self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {
                    "error": "experiment is incompatible with the selected backend",
                    "issues": [issue.__dict__ for issue in error.issues],
                })
            except (ValidationError, ValueError, KeyError, json.JSONDecodeError) as error:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

        def log_message(self, format: str, *args: object) -> None:
            return

    return ThreadingHTTPServer((host, port), Handler)


def serve(*, host: str, port: int, token: str, output_dir: Path) -> None:
    create_server(host=host, port=port, token=token, output_dir=output_dir).serve_forever()
