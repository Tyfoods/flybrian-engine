from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from flybrian_engine.durable import (
    DuplicateJobError,
    DurableJobManager,
    DurableJobStore,
    InvalidTransitionError,
    QueueFullError,
)
from flybrian_engine.schema import validate_experiment_spec

FIXTURE = Path(__file__).parents[1] / "examples" / "minimal-experiment.json"


def experiment() -> object:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def wait_for_terminal(manager: DurableJobManager, run_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = manager.status(run_id)
        if status["state"] in {"succeeded", "failed", "cancelled", "outcome_unknown"}:
            return status
        time.sleep(0.01)
    raise AssertionError(f"job {run_id} did not reach a terminal state")


def wait_for_state(
    manager: DurableJobManager,
    run_id: str,
    expected: str,
) -> dict[str, object]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        status = manager.status(run_id)
        if status["state"] == expected:
            return status
        if status["state"] in {"succeeded", "failed", "cancelled", "outcome_unknown"}:
            raise AssertionError(f"job {run_id} reached {status['state']} before {expected}")
        time.sleep(0.001)
    raise AssertionError(f"job {run_id} did not reach {expected}")


def test_atomic_admission_is_immutable_and_duplicate_safe(tmp_path: Path) -> None:
    store = DurableJobStore(tmp_path)
    spec = validate_experiment_spec(experiment())
    status = store.admit(spec, backend_id="reference", run_id="durable_fixture")

    assert status["state"] == "queued"
    assert status["revision"] == 1
    request_path = tmp_path / ".runner-v1" / "jobs" / "durable_fixture" / "request.json"
    status_path = request_path.with_name("status.json")
    original_request = request_path.read_bytes()
    original_status = status_path.read_bytes()

    with pytest.raises(DuplicateJobError):
        store.admit(spec, backend_id="reference", run_id="durable_fixture")

    assert request_path.read_bytes() == original_request
    assert status_path.read_bytes() == original_status


def test_transition_revisions_and_terminal_immutability(tmp_path: Path) -> None:
    store = DurableJobStore(tmp_path)
    store.admit(validate_experiment_spec(experiment()), "reference", "state_fixture")
    running = store.transition("state_fixture", "running", worker_pid=123)
    assert running["revision"] == 2
    succeeded = store.transition(
        "state_fixture",
        "succeeded",
        manifest_relative_path="state_fixture/manifest.json",
    )
    assert succeeded["revision"] == 3

    with pytest.raises(InvalidTransitionError):
        store.transition("state_fixture", "failed", error={"code": "late"})
    assert store.status("state_fixture") == succeeded


def test_recovery_requeues_queued_and_marks_interrupted_running_unknown(tmp_path: Path) -> None:
    store = DurableJobStore(tmp_path)
    spec = validate_experiment_spec(experiment())
    store.admit(spec, "reference", "queued_fixture")
    store.admit(spec, "reference", "running_fixture")
    store.transition("running_fixture", "running", worker_pid=999999)

    queued = store.recover()

    assert queued == ["queued_fixture"]
    recovered = store.status("running_fixture")
    assert recovered["state"] == "outcome_unknown"
    assert recovered["error"] == {
        "code": "runner_restarted",
        "message": "runner restarted without a terminal worker receipt",
    }


def test_scheduler_executes_persisted_request_and_reconnects(tmp_path: Path) -> None:
    manager = DurableJobManager(tmp_path, max_workers=1, max_queued=4)
    try:
        accepted = manager.submit(experiment(), backend_id="reference", run_id="job_fixture")
        assert accepted["state"] == "queued"
        terminal = wait_for_terminal(manager, "job_fixture")
        assert terminal["state"] == "succeeded"
        assert terminal["manifest_relative_path"] == "job_fixture/manifest.json"
        manifest = manager.manifest("job_fixture")
        assert manifest.run_id == "job_fixture"
        artifact, body = manager.artifact("job_fixture", "summary")
        assert artifact.key == "summary"
        assert body
    finally:
        manager.shutdown()


def test_queued_cancellation_allocates_no_scientific_output(tmp_path: Path) -> None:
    manager = DurableJobManager(tmp_path, max_workers=1, max_queued=4, autostart=False)
    try:
        manager.submit(experiment(), backend_id="reference", run_id="cancel_fixture")
        cancelled = manager.cancel("cancel_fixture")
        assert cancelled["state"] == "cancelled"
        assert not (tmp_path / "cancel_fixture").exists()
    finally:
        manager.shutdown()


def test_artifact_checksum_change_is_rejected(tmp_path: Path) -> None:
    manager = DurableJobManager(tmp_path, max_workers=1, max_queued=4)
    try:
        manager.submit(experiment(), backend_id="reference", run_id="tamper_fixture")
        assert wait_for_terminal(manager, "tamper_fixture")["state"] == "succeeded"
        artifact, _ = manager.artifact("tamper_fixture", "summary")
        path = tmp_path / "tamper_fixture" / artifact.relative_path
        path.write_bytes(b"tampered")
        with pytest.raises(ValueError, match="size or SHA-256"):
            manager.artifact("tamper_fixture", artifact.key)
    finally:
        manager.shutdown()


def test_queue_bound_rejects_without_allocating_a_second_record(tmp_path: Path) -> None:
    manager = DurableJobManager(tmp_path, max_workers=1, max_queued=1, autostart=False)
    try:
        manager.submit(experiment(), backend_id="reference", run_id="first_fixture")
        with pytest.raises(QueueFullError):
            manager.submit(experiment(), backend_id="reference", run_id="overflow_fixture")
        assert not (tmp_path / ".runner-v1" / "jobs" / "overflow_fixture").exists()
    finally:
        manager.shutdown()


def test_running_cancellation_records_request_and_truthful_race_outcome(tmp_path: Path) -> None:
    manager = DurableJobManager(tmp_path, max_workers=1, max_queued=4)
    try:
        manager.submit(experiment(), backend_id="reference", run_id="running_cancel")
        wait_for_state(manager, "running_cancel", "running")
        requested = manager.cancel("running_cancel")
        assert requested["state"] == "cancellation_requested"
        assert requested["cancellation_requested_at"] is not None
        terminal = wait_for_terminal(manager, "running_cancel")
        assert terminal["state"] in {"cancelled", "succeeded"}
        assert terminal["state"] != "outcome_unknown"
    finally:
        manager.shutdown()


def test_shutdown_preserves_queued_job_for_restart(tmp_path: Path) -> None:
    first = DurableJobManager(tmp_path, max_workers=1, max_queued=4, autostart=False)
    first.submit(experiment(), backend_id="reference", run_id="restart_queue")
    first.shutdown()

    recovered = DurableJobManager(tmp_path, max_workers=1, max_queued=4, autostart=False)
    try:
        assert recovered.status("restart_queue")["state"] == "queued"
        assert recovered.cancel("restart_queue")["state"] == "cancelled"
    finally:
        recovered.shutdown()
