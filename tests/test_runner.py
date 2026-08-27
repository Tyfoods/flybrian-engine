from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import cast

import pytest

from flybrian_engine.cli import main
from flybrian_engine.runner import CompatibilityError, create_server, run_experiment

FIXTURE = Path(__file__).parents[1] / "examples" / "minimal-experiment.json"
HETEROGENEOUS_FIXTURE = Path(__file__).parents[1] / "examples" / "heterogeneous-experiment.json"


def test_reference_backend_emits_verified_manifest(tmp_path: Path) -> None:
    experiment = json.loads(FIXTURE.read_text(encoding="utf-8"))
    manifest = run_experiment(experiment, tmp_path, run_id="run_fixture")
    assert manifest["backend_id"] == "reference"
    assert manifest["schema_version"] == "1.1"
    assert manifest["engine_version"] == "0.1.0"
    assert manifest["experiment_spec_version"] == "1.0"
    assert manifest["random_seed"] == 42
    assert manifest["scientific_execution"] is False
    assert manifest["deterministic_for_fixed_seed"] is True
    assert manifest["datasets"] == [{"dataset_id": "fixture:v1", "sha256": None}]
    artifacts = cast(list[dict[str, object]], manifest["artifacts"])
    artifact = artifacts[0]
    assert artifact["relative_path"] == "summary.json"
    assert manifest["dispositions"] == [{
        "artifact_keys": ["summary"],
        "kind": "summary",
        "reason": None,
        "status": "available",
    }]
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


def test_cli_returns_structured_compatibility_issues_without_allocation(
    tmp_path: Path,
    capsys: object,
) -> None:
    assert main([
        "run",
        str(HETEROGENEOUS_FIXTURE),
        "--output",
        str(tmp_path),
    ]) == 2
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
            data=json.dumps({
                "experiment": unsupported,
                "run_id": "http_must_not_exist",
            }).encode(),
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
