"""Engine composition and cross-platform loopback HTTP protocol."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import secrets
import socket
import uuid
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from .durable import (
    CompatibilityError as _CompatibilityError,
)
from .durable import (
    DuplicateJobError,
    DurableJobManager,
    InvalidTransitionError,
    QueueFullError,
    preflight_experiment,
    safe_error_message,
    validated_identifier,
)
from .durable import (
    default_registry as _default_registry,
)
from .schema import ValidationError

CompatibilityError = _CompatibilityError
default_registry = _default_registry


def run_experiment(
    value: Any,
    output_dir: Path,
    backend_id: str = "reference",
    run_id: str | None = None,
) -> dict[str, object]:
    resolved_run_id = validated_identifier(
        run_id if run_id is not None else f"run_{uuid.uuid4().hex}",
        "run_id",
    )
    resolved_backend_id = validated_identifier(backend_id, "backend_id")
    registry = default_registry()
    spec = preflight_experiment(value, resolved_backend_id, registry)
    backend = registry.get(resolved_backend_id)
    manifest = backend.run(spec, output_dir, resolved_run_id)
    return manifest.to_dict()


class LocalRunnerServer(ThreadingHTTPServer):
    """Loopback server that owns and shuts down one durable job manager."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        handler: type[BaseHTTPRequestHandler],
        manager: DurableJobManager,
    ) -> None:
        self.job_manager = manager
        self._manager_closed = False
        super().__init__(address, handler)

    def server_close(self) -> None:
        if not self._manager_closed:
            self._manager_closed = True
            self.job_manager.shutdown()
        super().server_close()


class IPv6LocalRunnerServer(LocalRunnerServer):
    """IPv6 loopback variant with the same durable ownership semantics."""

    address_family = socket.AF_INET6


def create_server(
    *,
    host: str,
    port: int,
    token: str,
    output_dir: Path,
    max_workers: int = 1,
    max_queued: int = 64,
) -> LocalRunnerServer:
    try:
        if not ipaddress.ip_address(host).is_loopback:
            raise ValueError("local runner host must be a loopback IP address")
    except ValueError as error:
        raise ValueError("local runner host must be 127.0.0.1 or ::1") from error
    if host not in {"127.0.0.1", "::1"}:
        raise ValueError("local runner host must be 127.0.0.1 or ::1")
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("local runner port must be between 0 and 65535")
    if not isinstance(token, str) or not token:
        raise ValueError("local runner token must be non-empty")
    registry = default_registry()
    manager = DurableJobManager(
        output_dir,
        max_workers=max_workers,
        max_queued=max_queued,
    )

    class Handler(BaseHTTPRequestHandler):
        server_version = "flybrian-engine/0.1"

        @property
        def manager(self) -> DurableJobManager:
            server = self.server
            if not isinstance(server, LocalRunnerServer):
                raise RuntimeError("handler is not attached to a local runner server")
            return server.job_manager

        def _json(
            self,
            status: HTTPStatus,
            value: object,
            *,
            cache_control: str = "no-store",
            etag: str | None = None,
        ) -> None:
            body = json.dumps(value, sort_keys=True).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache_control)
            self.send_header("X-Content-Type-Options", "nosniff")
            if etag is not None:
                self.send_header("ETag", f'"{etag}"')
            self.end_headers()
            self.wfile.write(body)

        def _bytes(self, status: HTTPStatus, body: bytes, media_type: str, etag: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", media_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "private, immutable")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("ETag", f'"{etag}"')
            self.end_headers()
            self.wfile.write(body)

        def _authorized(self) -> bool:
            return secrets.compare_digest(self.headers.get("Authorization", ""), f"Bearer {token}")

        def _browser_request(self) -> bool:
            return any(
                self.headers.get(name) is not None
                for name in (
                    "Origin",
                    "Access-Control-Request-Method",
                    "Access-Control-Request-Headers",
                )
            )

        def _parts(self) -> tuple[str, ...]:
            parsed = urlsplit(self.path)
            if parsed.query or parsed.fragment:
                raise ValidationError("query strings and fragments are not supported")
            parts = tuple(unquote(part) for part in parsed.path.split("/") if part)
            if any("/" in part or "\\" in part for part in parts):
                raise ValidationError("request path contains an invalid encoded separator")
            return parts

        def _request_object(self) -> dict[str, object]:
            raw_length = self.headers.get("Content-Length", "")
            try:
                length = int(raw_length)
            except ValueError as error:
                raise ValidationError("Content-Length must be an integer") from error
            if length <= 0:
                raise ValidationError("request body must not be empty")
            if length > 10 * 1024 * 1024:
                raise OverflowError("request body exceeds 10 MiB")
            value = json.loads(self.rfile.read(length))
            if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
                raise ValidationError("request body must be a JSON object")
            return value

        def _deny_browser_or_auth(self) -> bool:
            if self._browser_request():
                self._json(
                    HTTPStatus.FORBIDDEN,
                    {
                        "protocol_version": "1",
                        "error": "browser origin is not paired",
                        "code": "origin_denied",
                    },
                )
                return True
            if not self._authorized():
                self._json(
                    HTTPStatus.UNAUTHORIZED,
                    {
                        "protocol_version": "1",
                        "error": "authorization required",
                        "code": "unauthorized",
                    },
                )
                return True
            return False

        def do_OPTIONS(self) -> None:
            if self._browser_request():
                self._json(
                    HTTPStatus.FORBIDDEN,
                    {
                        "protocol_version": "1",
                        "error": "browser origin is not paired",
                        "code": "origin_denied",
                    },
                )
                return
            self._json(
                HTTPStatus.METHOD_NOT_ALLOWED,
                {
                    "protocol_version": "1",
                    "error": "method not allowed",
                    "code": "method_not_allowed",
                },
            )

        def do_GET(self) -> None:
            if self._browser_request():
                self._json(
                    HTTPStatus.FORBIDDEN,
                    {
                        "protocol_version": "1",
                        "error": "browser origin is not paired",
                        "code": "origin_denied",
                    },
                )
                return
            try:
                parts = self._parts()
            except ValidationError as error:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"protocol_version": "1", "error": str(error), "code": "invalid_path"},
                )
                return
            if parts == ("v1", "health"):
                self._json(HTTPStatus.OK, {"status": "healthy", "protocol_version": "1"})
                return
            if self._deny_browser_or_auth():
                return
            if parts == ("v1", "capabilities"):
                self._json(
                    HTTPStatus.OK,
                    {
                        "protocol_version": "1",
                        "backends": [capability.__dict__ for capability in registry.capabilities()],
                        "runner": {
                            "durable_jobs": True,
                            "max_workers": self.manager.max_workers,
                            "max_queued": self.manager.max_queued,
                            "direct_browser_origins": False,
                        },
                    },
                )
                return
            try:
                if len(parts) == 3 and parts[:2] == ("v1", "jobs"):
                    self._json(HTTPStatus.OK, self.manager.status(parts[2]))
                    return
                if len(parts) == 4 and parts[:2] == ("v1", "jobs") and parts[3] == "manifest":
                    manifest = self.manager.manifest(parts[2]).to_dict()
                    body = json.dumps(manifest, sort_keys=True).encode()
                    self._json(
                        HTTPStatus.OK,
                        manifest,
                        cache_control="private, immutable",
                        etag=hashlib.sha256(body).hexdigest(),
                    )
                    return
                if len(parts) == 5 and parts[:2] == ("v1", "jobs") and parts[3] == "artifacts":
                    artifact, body = self.manager.artifact(parts[2], parts[4])
                    self._bytes(HTTPStatus.OK, body, artifact.media_type, artifact.sha256)
                    return
            except KeyError as error:
                self._json(
                    HTTPStatus.NOT_FOUND,
                    {"protocol_version": "1", "error": str(error), "code": "not_found"},
                )
                return
            except (InvalidTransitionError, OSError, ValueError) as error:
                self._json(
                    HTTPStatus.CONFLICT,
                    {
                        "protocol_version": "1",
                        "error": safe_error_message(error, output_dir),
                        "code": "artifact_unavailable",
                    },
                )
                return
            self._json(
                HTTPStatus.NOT_FOUND,
                {"protocol_version": "1", "error": "not found", "code": "not_found"},
            )

        def do_POST(self) -> None:
            if self._deny_browser_or_auth():
                return
            try:
                parts = self._parts()
                body = self._request_object()
            except OverflowError as error:
                self._json(
                    HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    {"protocol_version": "1", "error": str(error), "code": "body_too_large"},
                )
                return
            except (UnicodeError, ValidationError, json.JSONDecodeError) as error:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {"protocol_version": "1", "error": str(error), "code": "invalid_request"},
                )
                return
            try:
                if parts == ("v1", "jobs"):
                    unknown = sorted(set(body) - {"experiment", "backend_id", "run_id"})
                    if unknown:
                        raise ValidationError("unknown request fields: " + ", ".join(unknown))
                    if "experiment" not in body:
                        raise ValidationError("request must contain experiment")
                    backend_id = body.get("backend_id", "reference")
                    if not isinstance(backend_id, str):
                        raise ValidationError("backend_id must be a string")
                    run_id = body.get("run_id")
                    if run_id is not None and not isinstance(run_id, str):
                        raise ValidationError("run_id must be a string or null")
                    status = self.manager.submit(
                        body["experiment"],
                        backend_id=backend_id,
                        run_id=run_id,
                    )
                    self._json(HTTPStatus.ACCEPTED, status)
                    return
                if len(parts) == 4 and parts[:2] == ("v1", "jobs") and parts[3] == "cancel":
                    if body:
                        raise ValidationError("cancel request body must be an empty object")
                    self._json(HTTPStatus.OK, self.manager.cancel(parts[2]))
                    return
                if parts != ("v1", "runs"):
                    self._json(
                        HTTPStatus.NOT_FOUND,
                        {"protocol_version": "1", "error": "not found", "code": "not_found"},
                    )
                    return
                if set(body) - {"experiment", "backend_id", "run_id"}:
                    raise ValidationError("request contains unknown fields")
                if "experiment" not in body:
                    raise ValidationError("request must contain experiment")
                backend_id = body.get("backend_id", "reference")
                if not isinstance(backend_id, str):
                    raise ValidationError("backend_id must be a string")
                run_id = body.get("run_id")
                if run_id is not None and not isinstance(run_id, str):
                    raise ValidationError("run_id must be a string or null")
                result = run_experiment(
                    body["experiment"],
                    output_dir,
                    backend_id=backend_id,
                    run_id=run_id,
                )
                self._json(HTTPStatus.CREATED, result)
            except DuplicateJobError as error:
                self._json(
                    HTTPStatus.CONFLICT,
                    {"protocol_version": "1", "error": str(error), "code": "duplicate_job"},
                )
            except QueueFullError as error:
                self._json(
                    HTTPStatus.TOO_MANY_REQUESTS,
                    {"protocol_version": "1", "error": str(error), "code": "queue_full"},
                )
            except KeyError as error:
                self._json(
                    HTTPStatus.NOT_FOUND,
                    {"protocol_version": "1", "error": str(error), "code": "not_found"},
                )
            except InvalidTransitionError as error:
                self._json(
                    HTTPStatus.CONFLICT,
                    {"protocol_version": "1", "error": str(error), "code": "invalid_transition"},
                )
            except CompatibilityError as error:
                self._json(
                    HTTPStatus.UNPROCESSABLE_ENTITY,
                    {
                        "protocol_version": "1",
                        "error": "experiment is incompatible with the selected backend",
                        "code": "incompatible_experiment",
                        "issues": [issue.__dict__ for issue in error.issues],
                    },
                )
            except (ValidationError, ValueError, json.JSONDecodeError) as error:
                self._json(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "protocol_version": "1",
                        "error": safe_error_message(error, output_dir),
                        "code": "invalid_request",
                    },
                )
            except OSError as error:
                http_status = (
                    HTTPStatus.INSUFFICIENT_STORAGE
                    if error.errno == 28
                    else HTTPStatus.INTERNAL_SERVER_ERROR
                )
                self._json(
                    http_status,
                    {
                        "protocol_version": "1",
                        "error": safe_error_message(error, output_dir),
                        "code": "storage_failure" if error.errno == 28 else "execution_failure",
                    },
                )

        def log_message(self, format: str, *args: object) -> None:
            return

    try:
        server_type = IPv6LocalRunnerServer if host == "::1" else LocalRunnerServer
        return server_type((host, port), Handler, manager)
    except BaseException:
        manager.shutdown()
        raise


def serve(
    *,
    host: str,
    port: int,
    token: str,
    output_dir: Path,
    max_workers: int = 1,
    max_queued: int = 64,
) -> None:
    server = create_server(
        host=host,
        port=port,
        token=token,
        output_dir=output_dir,
        max_workers=max_workers,
        max_queued=max_queued,
    )
    try:
        server.serve_forever()
    finally:
        server.server_close()
