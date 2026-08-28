from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import cast

import pytest

import flybrian_engine.cli as cli_module
from flybrian_engine.cli import main
from flybrian_engine.runner import CompatibilityError, create_server, run_experiment

FIXTURE = Path(__file__).parents[1] / "examples" / "minimal-experiment.json"
HETEROGENEOUS_FIXTURE = Path(__file__).parents[1] / "examples" / "heterogeneous-experiment.json"


def test_reference_backend_emits_verified_manifest(tmp_path: Path) -> None:
    experiment = json.loads(FIXTURE.read_text(encoding="utf-8"))
    manifest = run_experiment(experiment, tmp_path, run_id="run_fixture")
    assert manifest["backend_id"] == "reference"
    assert manifest["schema_version"] == "1.1"
    assert manifest["engine_version"] == "0.1.3"
    assert manifest["experiment_spec_version"] == "1.0"
    assert manifest["random_seed"] == 42
    assert manifest["scientific_execution"] is False
    assert manifest["deterministic_for_fixed_seed"] is True
    assert manifest["datasets"] == [{"dataset_id": "fixture:v1", "sha256": None}]
    artifacts = cast(list[dict[str, object]], manifest["artifacts"])
    artifact = artifacts[0]
    assert artifact["relative_path"] == "summary.json"
    assert manifest["dispositions"] == [
        {
            "artifact_keys": ["summary"],
            "kind": "summary",
            "reason": None,
            "status": "available",
        }
    ]
    assert (tmp_path / "run_fixture" / "manifest.json").is_file()


def test_reference_backend_rejects_valid_unsupported_science_before_allocation(
    tmp_path: Path,
) -> None:
    experiment = json.loads(HETEROGENEOUS_FIXTURE.read_text(encoding="utf-8"))
    with pytest.raises(CompatibilityError) as rejected:
        run_experiment(experiment, tmp_path, run_id="must_not_exist")
    assert [(issue.code, issue.path) for issue in rejected.value.issues] == [
        ("unsupported_artifact", "artifact_requests"),
        ("unsupported_embodiment_mode", "embodied_config.drive_mode"),
        ("backend_id_mismatch", "execution.backend_id"),
        ("unsupported_model_family", "neuron_models.compartmental_motor.family"),
        ("unsupported_model_family", "neuron_models.rate_controller.family"),
    ]
    assert not (tmp_path / "must_not_exist").exists()


def test_backend_and_engine_version_constraints_reject_before_allocation(tmp_path: Path) -> None:
    experiment = json.loads(FIXTURE.read_text(encoding="utf-8"))
    experiment["execution"] = {
        "backend_id": "reference",
        "backend_version": ">=2",
        "engine_version": ">=9",
    }
    with pytest.raises(CompatibilityError) as rejected:
        run_experiment(experiment, tmp_path, run_id="version_mismatch")
    assert [(issue.code, issue.path) for issue in rejected.value.issues] == [
        ("backend_version_mismatch", "execution.backend_version"),
        ("engine_version_mismatch", "execution.engine_version"),
    ]
    assert not (tmp_path / "version_mismatch").exists()


@pytest.mark.parametrize("run_id", ["../escape", "/absolute", "", "x" * 65, "has space"])
def test_untrusted_run_id_cannot_escape_or_allocate_output(tmp_path: Path, run_id: str) -> None:
    experiment = json.loads(FIXTURE.read_text(encoding="utf-8"))
    with pytest.raises(ValueError, match="opaque identifier"):
        run_experiment(experiment, tmp_path, run_id=run_id)
    assert list(tmp_path.iterdir()) == []


def test_cli_health_validate_and_duplicate_run_failure(tmp_path: Path, capsys: object) -> None:
    assert main(["health"]) == 0
    health = json.loads(capsys.readouterr().out.splitlines()[-1])  # type: ignore[attr-defined]
    assert health["backends"][0]["scientific_execution"] is False
    assert main(["validate", str(FIXTURE)]) == 0
    assert main(["run", str(FIXTURE), "--output", str(tmp_path)]) == 0
    first = json.loads(capsys.readouterr().out.splitlines()[-1])  # type: ignore[attr-defined]
    assert first["backend_id"] == "reference"


def test_cli_prints_bound_port_only_after_server_creation(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeServer:
        server_port = 43210
        served = False
        closed = False

        def serve_forever(self) -> None:
            self.served = True

        def server_close(self) -> None:
            self.closed = True

    server = FakeServer()
    monkeypatch.setattr(cli_module, "create_server", lambda **_kwargs: server)

    assert (
        main(
            [
                "serve",
                "--port",
                "0",
                "--token",
                "fixed",
                "--output",
                str(tmp_path),
            ]
        )
        == 0
    )
    connection = json.loads(capsys.readouterr().out)
    assert connection == {
        "host": "127.0.0.1",
        "port": 43210,
        "protocol_version": "1",
        "token": "fixed",
    }
    assert server.served is True
    assert server.closed is True


def test_cli_returns_structured_compatibility_issues_without_allocation(
    tmp_path: Path,
    capsys: object,
) -> None:
    assert (
        main(
            [
                "run",
                str(HETEROGENEOUS_FIXTURE),
                "--output",
                str(tmp_path),
            ]
        )
        == 2
    )
    rejection = json.loads(capsys.readouterr().out.splitlines()[-1])  # type: ignore[attr-defined]
    assert rejection["error"] == "experiment is incompatible with the selected backend"
    assert {issue["code"] for issue in rejection["issues"]} >= {
        "backend_id_mismatch",
        "unsupported_embodiment_mode",
        "unsupported_model_family",
    }
    assert list(tmp_path.iterdir()) == []


def test_loopback_protocol_requires_auth_and_runs_same_manifest(tmp_path: Path) -> None:
    server = create_server(host="127.0.0.1", port=0, token="secret", output_dir=tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        with urllib.request.urlopen(f"{base_url}/v1/health") as response:
            assert json.load(response)["status"] == "healthy"
        with pytest.raises(urllib.error.HTTPError) as unauthorized:
            urllib.request.urlopen(f"{base_url}/v1/capabilities")
        assert unauthorized.value.code == 401
        experiment = json.loads(FIXTURE.read_text(encoding="utf-8"))
        request = urllib.request.Request(
            f"{base_url}/v1/runs",
            data=json.dumps({"experiment": experiment, "run_id": "run_http"}).encode(),
            headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request) as response:
            assert response.status == 201
            assert json.load(response)["run_id"] == "run_http"

        unsupported = json.loads(HETEROGENEOUS_FIXTURE.read_text(encoding="utf-8"))
        rejected_request = urllib.request.Request(
            f"{base_url}/v1/runs",
            data=json.dumps(
                {
                    "experiment": unsupported,
                    "run_id": "http_must_not_exist",
                }
            ).encode(),
            headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as incompatible:
            urllib.request.urlopen(rejected_request)
        assert incompatible.value.code == 422
        rejection = json.load(incompatible.value)
        assert rejection["error"] == "experiment is incompatible with the selected backend"
        assert {issue["code"] for issue in rejection["issues"]} >= {
            "backend_id_mismatch",
            "unsupported_embodiment_mode",
            "unsupported_model_family",
        }
        assert not (tmp_path / "http_must_not_exist").exists()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def authorized_request(
    url: str, *, data: object | None = None, method: str = "GET"
) -> urllib.request.Request:
    body = None if data is None else json.dumps(data).encode()
    return urllib.request.Request(
        url,
        data=body,
        headers={"Authorization": "Bearer secret", "Content-Type": "application/json"},
        method=method,
    )


def test_durable_http_submit_reconnect_manifest_and_artifact(tmp_path: Path) -> None:
    server = create_server(host="127.0.0.1", port=0, token="secret", output_dir=tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        experiment = json.loads(FIXTURE.read_text(encoding="utf-8"))
        with urllib.request.urlopen(
            authorized_request(
                f"{base_url}/v1/jobs",
                data={"experiment": experiment, "run_id": "durable_http"},
                method="POST",
            )
        ) as response:
            assert response.status == 202
            assert json.load(response)["state"] == "queued"

        deadline = time.monotonic() + 5
        while True:
            with urllib.request.urlopen(
                authorized_request(f"{base_url}/v1/jobs/durable_http")
            ) as response:
                status = json.load(response)
            if status["state"] in {"succeeded", "failed", "cancelled", "outcome_unknown"}:
                break
            if time.monotonic() >= deadline:
                raise AssertionError("durable HTTP job did not finish")
            time.sleep(0.01)
        assert status["state"] == "succeeded"

        with urllib.request.urlopen(
            authorized_request(f"{base_url}/v1/jobs/durable_http/manifest")
        ) as response:
            manifest = json.load(response)
            assert manifest["run_id"] == "durable_http"
            assert response.headers["Cache-Control"] == "private, immutable"
        with urllib.request.urlopen(
            authorized_request(f"{base_url}/v1/jobs/durable_http/artifacts/summary")
        ) as response:
            assert response.headers["ETag"].strip('"') == manifest["artifacts"][0]["sha256"]
            assert json.load(response)["backend"] == "reference"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_browser_origin_is_denied_even_with_valid_token(tmp_path: Path) -> None:
    server = create_server(host="127.0.0.1", port=0, token="secret", output_dir=tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        request = authorized_request(f"{base_url}/v1/capabilities")
        request.add_header("Origin", "https://flybrian.ai")
        with pytest.raises(urllib.error.HTTPError) as denied:
            urllib.request.urlopen(request)
        assert denied.value.code == 403
        assert denied.value.headers.get("Access-Control-Allow-Origin") is None

        preflight = urllib.request.Request(
            f"{base_url}/v1/jobs",
            headers={
                "Origin": "https://flybrian.ai",
                "Access-Control-Request-Method": "POST",
            },
            method="OPTIONS",
        )
        with pytest.raises(urllib.error.HTTPError) as denied_preflight:
            urllib.request.urlopen(preflight)
        assert denied_preflight.value.code == 403
        assert denied_preflight.value.headers.get("Access-Control-Allow-Origin") is None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_server_factory_rejects_non_loopback_binding(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"127\.0\.0\.1 or ::1"):
        create_server(host="0.0.0.0", port=0, token="secret", output_dir=tmp_path)


def test_server_factory_supports_ipv6_loopback_when_available(tmp_path: Path) -> None:
    try:
        server = create_server(host="::1", port=0, token="secret", output_dir=tmp_path)
    except OSError as error:
        pytest.skip(f"IPv6 loopback is unavailable: {error}")
    server.server_close()


def test_durable_http_rejects_unknown_fields_and_duplicate_identity(tmp_path: Path) -> None:
    server = create_server(host="127.0.0.1", port=0, token="secret", output_dir=tmp_path)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    experiment = json.loads(FIXTURE.read_text(encoding="utf-8"))
    try:
        unknown = authorized_request(
            f"{base_url}/v1/jobs",
            data={"experiment": experiment, "run_id": "unknown_field", "backed_id": "typo"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as rejected:
            urllib.request.urlopen(unknown)
        assert rejected.value.code == 400
        assert not (tmp_path / ".runner-v1" / "jobs" / "unknown_field").exists()

        accepted = authorized_request(
            f"{base_url}/v1/jobs",
            data={"experiment": experiment, "run_id": "duplicate_http"},
            method="POST",
        )
        with urllib.request.urlopen(accepted) as response:
            assert response.status == 202
        duplicate = authorized_request(
            f"{base_url}/v1/jobs",
            data={"experiment": experiment, "run_id": "duplicate_http"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as conflict:
            urllib.request.urlopen(duplicate)
        assert conflict.value.code == 409
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
