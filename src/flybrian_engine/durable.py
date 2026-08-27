"""Durable, origin-neutral local job records and isolated worker scheduling."""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import threading
import uuid
from collections import deque
from contextlib import suppress
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import TracebackType
from typing import IO, Any, Literal

from .artifacts import Artifact, ArtifactManifest
from .backends import BackendRegistry, CompatibilityIssue, assess_backend_compatibility
from .brian2_backend import Brian2Backend
from .reference import ReferenceBackend
from .schema import ExperimentSpec, ValidationError, validate_experiment_spec
from .version import __version__

JobState = Literal[
    "queued",
    "running",
    "cancellation_requested",
    "succeeded",
    "failed",
    "cancelled",
    "outcome_unknown",
]

TERMINAL_STATES = frozenset({"succeeded", "failed", "cancelled", "outcome_unknown"})
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_TRANSITIONS: dict[str, frozenset[str]] = {
    "queued": frozenset({"running", "cancelled"}),
    "running": frozenset({"succeeded", "failed", "cancellation_requested", "outcome_unknown"}),
    "cancellation_requested": frozenset({"succeeded", "failed", "cancelled", "outcome_unknown"}),
}


class CompatibilityError(ValueError):
    """A valid experiment cannot be executed by the selected backend."""

    def __init__(self, issues: tuple[CompatibilityIssue, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(issue.message for issue in issues))


class DuplicateJobError(ValueError):
    """A durable job already owns the requested run ID."""


class InvalidTransitionError(ValueError):
    """A durable status transition violates the lifecycle contract."""


class QueueFullError(RuntimeError):
    """The configured durable queue has no admission capacity."""


def validated_identifier(value: object, name: str) -> str:
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


def preflight_experiment(
    value: Any,
    backend_id: str,
    registry: BackendRegistry | None = None,
) -> ExperimentSpec:
    spec = validate_experiment_spec(value)
    resolved_backend_id = validated_identifier(backend_id, "backend_id")
    backend = (registry or default_registry()).get(resolved_backend_id)
    issues = assess_backend_compatibility(
        spec,
        backend.capabilities,
        engine_version=__version__,
    ) + backend.compatibility_issues(spec)
    if issues:
        raise CompatibilityError(issues)
    return spec


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def safe_error_message(error: BaseException, root: Path) -> str:
    """Bound and redact a control-plane error before persisting or returning it."""
    message = " ".join(str(error).splitlines())
    resolved_root = str(root.resolve())
    if resolved_root:
        message = message.replace(resolved_root, "<runner-root>")
    return message[:1000] or error.__class__.__name__


def _json_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError(f"{path.name} must contain a JSON object")
    return value


def _atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, indent=2, sort_keys=True, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        with suppress(OSError):
            os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class DurableJobStore:
    """Atomic protocol-1 job records below a user-selected runner root."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.control_root = self.root / ".runner-v1"
        self.jobs_root = self.control_root / "jobs"
        self.jobs_root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.control_root, 0o700)
            os.chmod(self.jobs_root, 0o700)
        except OSError:
            pass
        self._lock = threading.RLock()

    def job_root(self, run_id: str) -> Path:
        return self.jobs_root / validated_identifier(run_id, "run_id")

    def request_path(self, run_id: str) -> Path:
        return self.job_root(run_id) / "request.json"

    def result_path(self, run_id: str) -> Path:
        return self.job_root(run_id) / "worker-result.json"

    def status_path(self, run_id: str) -> Path:
        return self.job_root(run_id) / "status.json"

    def admit(
        self,
        spec: ExperimentSpec,
        backend_id: str,
        run_id: str,
    ) -> dict[str, Any]:
        resolved_run_id = validated_identifier(run_id, "run_id")
        resolved_backend_id = validated_identifier(backend_id, "backend_id")
        submitted_at = _now()
        request = {
            "protocol_version": "1",
            "run_id": resolved_run_id,
            "backend_id": resolved_backend_id,
            "engine_version": __version__,
            "accepted_at": submitted_at,
            "experiment_sha256": spec.sha256(),
            "experiment": spec.value,
        }
        status: dict[str, Any] = {
            "protocol_version": "1",
            "run_id": resolved_run_id,
            "backend_id": resolved_backend_id,
            "engine_version": __version__,
            "state": "queued",
            "revision": 1,
            "submitted_at": submitted_at,
            "started_at": None,
            "finished_at": None,
            "worker_pid": None,
            "cancellation_requested_at": None,
            "manifest_relative_path": None,
            "error": None,
        }
        job_root = self.job_root(resolved_run_id)
        with self._lock:
            try:
                job_root.mkdir(mode=0o700)
            except FileExistsError as error:
                raise DuplicateJobError(f"job {resolved_run_id!r} already exists") from error
            try:
                _atomic_json(job_root / "request.json", request)
                _atomic_json(job_root / "status.json", status)
            except BaseException:
                for child in job_root.iterdir():
                    child.unlink(missing_ok=True)
                job_root.rmdir()
                raise
        return dict(status)

    def request(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            path = self.request_path(run_id)
            if not path.is_file():
                raise KeyError(f"unknown job {run_id!r}")
            value = _json_object(path)
            self._validate_record_identity(value, run_id, "request")
            return value

    def status(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            path = self.status_path(run_id)
            if not path.is_file():
                raise KeyError(f"unknown job {run_id!r}")
            value = _json_object(path)
            self._validate_record_identity(value, run_id, "status")
            state = value.get("state")
            if state not in set(_TRANSITIONS) | TERMINAL_STATES:
                raise ValueError(f"status for {run_id!r} has an unknown state")
            revision = value.get("revision")
            if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
                raise ValueError(f"status for {run_id!r} has an invalid revision")
            return value

    @staticmethod
    def _validate_record_identity(value: dict[str, Any], run_id: str, kind: str) -> None:
        if value.get("protocol_version") != "1":
            raise ValueError(f"{kind} for {run_id!r} uses an unsupported protocol version")
        if value.get("run_id") != run_id:
            raise ValueError(f"{kind} identity does not match its durable directory")

    def transition(self, run_id: str, state: JobState, **changes: object) -> dict[str, Any]:
        with self._lock:
            previous = self.status(run_id)
            current_state = str(previous["state"])
            if state not in _TRANSITIONS.get(current_state, frozenset()):
                raise InvalidTransitionError(f"cannot transition {current_state} to {state}")
            updated = dict(previous)
            updated.update(changes)
            updated["state"] = state
            updated["revision"] = int(previous["revision"]) + 1
            if state == "running" and updated.get("started_at") is None:
                updated["started_at"] = _now()
            if state == "cancellation_requested":
                updated["cancellation_requested_at"] = _now()
            if state in TERMINAL_STATES:
                updated["finished_at"] = _now()
                updated["worker_pid"] = None
            _atomic_json(self.status_path(run_id), updated)
            return updated

    def recover(self) -> list[str]:
        queued: list[tuple[str, str]] = []
        with self._lock:
            for job_root in sorted(self.jobs_root.iterdir()):
                if not job_root.is_dir():
                    continue
                run_id = validated_identifier(job_root.name, "run_id")
                status = self.status(run_id)
                state = status["state"]
                if state == "queued":
                    queued.append((str(status["submitted_at"]), run_id))
                elif state in {"running", "cancellation_requested"}:
                    self.transition(
                        run_id,
                        "outcome_unknown",
                        error={
                            "code": "runner_restarted",
                            "message": "runner restarted without a terminal worker receipt",
                        },
                    )
        return [run_id for _, run_id in sorted(queued)]


@dataclass
class _WorkerProcess:
    process: subprocess.Popen[bytes]
    stdout: IO[bytes]
    stderr: IO[bytes]

    def close_logs(self) -> None:
        self.stdout.close()
        self.stderr.close()


class DurableJobManager:
    """Bounded scheduler for durable jobs executed in isolated Python workers."""

    def __init__(
        self,
        root: Path,
        *,
        max_workers: int = 1,
        max_queued: int = 64,
        autostart: bool = True,
    ) -> None:
        if max_workers < 1 or max_workers > 64:
            raise ValueError("max_workers must be between 1 and 64")
        if max_queued < 1 or max_queued > 10000:
            raise ValueError("max_queued must be between 1 and 10000")
        self.store = DurableJobStore(root)
        self.max_workers = max_workers
        self.max_queued = max_queued
        self._queue = deque(self.store.recover())
        if len(self._queue) > max_queued:
            raise ValueError("persisted queue exceeds max_queued; increase the bound to recover")
        self._workers: dict[str, _WorkerProcess] = {}
        self._condition = threading.Condition(threading.RLock())
        self._closing = False
        self._thread: threading.Thread | None = None
        if autostart:
            self.start()

    @property
    def root(self) -> Path:
        return self.store.root

    def start(self) -> None:
        with self._condition:
            if self._closing:
                raise RuntimeError("job manager is shutting down")
            if self._thread is not None:
                return
            self._thread = threading.Thread(target=self._scheduler_loop, daemon=True)
            self._thread.start()

    def submit(
        self,
        value: Any,
        *,
        backend_id: str = "reference",
        run_id: str | None = None,
    ) -> dict[str, Any]:
        spec = preflight_experiment(value, backend_id)
        resolved_run_id = validated_identifier(
            run_id if run_id is not None else f"run_{uuid.uuid4().hex}",
            "run_id",
        )
        with self._condition:
            if self._closing:
                raise RuntimeError("job manager is shutting down")
            if len(self._queue) >= self.max_queued:
                raise QueueFullError("durable runner queue is full")
            status = self.store.admit(spec, backend_id, resolved_run_id)
            self._queue.append(resolved_run_id)
            self._condition.notify_all()
            return status

    def status(self, run_id: str) -> dict[str, Any]:
        return self.store.status(run_id)

    def cancel(self, run_id: str) -> dict[str, Any]:
        with self._condition:
            status = self.store.status(run_id)
            state = status["state"]
            if state == "cancelled":
                return status
            if state == "queued":
                with suppress(ValueError):
                    self._queue.remove(run_id)
                return self.store.transition(run_id, "cancelled")
            if state == "running":
                updated = self.store.transition(run_id, "cancellation_requested")
                worker = self._workers.get(run_id)
                if worker is None:
                    return self.store.transition(
                        run_id,
                        "outcome_unknown",
                        error={
                            "code": "worker_identity_lost",
                            "message": "runner could not prove worker termination",
                        },
                    )
                worker.process.terminate()
                self._condition.notify_all()
                return updated
            raise InvalidTransitionError(f"cannot cancel job in {state} state")

    def manifest(self, run_id: str) -> ArtifactManifest:
        status = self.store.status(run_id)
        if status["state"] != "succeeded":
            raise InvalidTransitionError("manifest is available only after successful completion")
        expected = f"{run_id}/manifest.json"
        if status.get("manifest_relative_path") != expected:
            raise ValueError("durable status has an invalid manifest path")
        run_root = self.root / run_id
        manifest_path = run_root / "manifest.json"
        if manifest_path.is_symlink():
            raise ValueError("manifest must not be a symbolic link")
        manifest = ArtifactManifest.read(manifest_path)
        if manifest.run_id != run_id:
            raise ValueError("manifest run identity does not match the durable job")
        manifest.verify_files(run_root)
        return manifest

    def artifact(self, run_id: str, key: str) -> tuple[Artifact, bytes]:
        manifest = self.manifest(run_id)
        try:
            artifact = next(item for item in manifest.artifacts if item.key == key)
        except StopIteration as error:
            raise KeyError(f"manifest has no artifact {key!r}") from error
        run_root = (self.root / run_id).resolve()
        candidate = run_root / artifact.relative_path
        if candidate.is_symlink() or any(parent.is_symlink() for parent in candidate.parents):
            raise ValueError("artifact path must not contain symbolic links")
        resolved = candidate.resolve()
        try:
            resolved.relative_to(run_root)
        except ValueError as error:
            raise ValueError("artifact path escapes the run root") from error
        data = resolved.read_bytes()
        if len(data) != artifact.size_bytes or hashlib.sha256(data).hexdigest() != artifact.sha256:
            raise ValueError(f"artifact {artifact.key!r} size or SHA-256 does not match")
        return artifact, data

    def shutdown(self) -> None:
        with self._condition:
            if self._closing and self._thread is None:
                return
            self._closing = True
            for run_id, worker in tuple(self._workers.items()):
                status = self.store.status(run_id)
                if status["state"] == "running":
                    self.store.transition(run_id, "cancellation_requested")
                worker.process.terminate()
            self._condition.notify_all()
        if self._thread is not None:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                with self._condition:
                    for worker in self._workers.values():
                        worker.process.kill()
                    self._condition.notify_all()
                self._thread.join(timeout=5)
            self._thread = None

    def __enter__(self) -> DurableJobManager:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.shutdown()

    def _scheduler_loop(self) -> None:
        while True:
            with self._condition:
                self._reap_workers()
                if not self._closing:
                    while self._queue and len(self._workers) < self.max_workers:
                        self._launch(self._queue.popleft())
                if self._closing and not self._workers:
                    return
                self._condition.wait(timeout=0.05)

    def _launch(self, run_id: str) -> None:
        job_root = self.store.job_root(run_id)
        result_path = self.store.result_path(run_id)
        result_path.unlink(missing_ok=True)
        stdout = (job_root / "stdout.log").open("ab")
        stderr = (job_root / "stderr.log").open("ab")
        command = [
            sys.executable,
            "-m",
            "flybrian_engine.worker",
            "--request",
            str(self.store.request_path(run_id)),
            "--output",
            str(self.root),
            "--result",
            str(result_path),
        ]
        try:
            process = subprocess.Popen(command, stdout=stdout, stderr=stderr, shell=False)
        except OSError as error:
            stdout.close()
            stderr.close()
            self.store.transition(
                run_id,
                "failed",
                error={
                    "code": "worker_launch_failed",
                    "message": safe_error_message(error, self.root),
                },
            )
            return
        self._workers[run_id] = _WorkerProcess(process, stdout, stderr)
        self.store.transition(run_id, "running", worker_pid=process.pid)

    def _reap_workers(self) -> None:
        for run_id, worker in tuple(self._workers.items()):
            return_code = worker.process.poll()
            if return_code is None:
                continue
            worker.close_logs()
            del self._workers[run_id]
            self._finish_worker(run_id, return_code)

    def _finish_worker(self, run_id: str, return_code: int) -> None:
        status = self.store.status(run_id)
        result = self._worker_result(run_id)
        if return_code == 0 and result.get("ok") is True:
            try:
                manifest = ArtifactManifest.from_dict(result.get("manifest"))
                if manifest.run_id != run_id:
                    raise ValueError("worker manifest run ID does not match")
                manifest.verify_files(self.root / run_id)
            except (OSError, ValueError) as receipt_error:
                self.store.transition(
                    run_id,
                    "failed",
                    error={
                        "code": "invalid_worker_receipt",
                        "message": safe_error_message(receipt_error, self.root),
                    },
                )
                return
            self.store.transition(
                run_id,
                "succeeded",
                manifest_relative_path=f"{run_id}/manifest.json",
                error=None,
            )
            return
        if status["state"] == "cancellation_requested":
            self.store.transition(run_id, "cancelled")
            return
        result_error = result.get("error")
        if isinstance(result_error, dict):
            raw_code = result_error.get("code")
            raw_message = result_error.get("message")
            code = (
                raw_code
                if isinstance(raw_code, str) and _RUN_ID.fullmatch(raw_code) is not None
                else "worker_execution_failed"
            )
            message = safe_error_message(
                RuntimeError(raw_message if isinstance(raw_message, str) else "worker failed"),
                self.root,
            )
            result_error = {"code": code, "message": message}
        else:
            result_error = {
                "code": "worker_exit_without_receipt",
                "message": f"worker exited with status {return_code} without a valid receipt",
            }
        self.store.transition(run_id, "failed", error=result_error)

    def _worker_result(self, run_id: str) -> dict[str, Any]:
        path = self.store.result_path(run_id)
        if not path.is_file() or path.is_symlink():
            return {}
        try:
            return _json_object(path)
        except (OSError, ValueError, json.JSONDecodeError):
            return {}
