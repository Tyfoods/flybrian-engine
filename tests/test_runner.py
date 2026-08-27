from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import cast

import pytest

from flybrian_engine.cli import main
from flybrian_engine.runner import create_server, run_experiment

FIXTURE = Path(__file__).parents[1] / "examples" / "minimal-experiment.json"


def test_reference_backend_emits_verified_manifest(tmp_path: Path) -> None:
    experiment = json.loads(FIXTURE.read_text(encoding="utf-8"))
    manifest = run_experiment(experiment, tmp_path, run_id="run_fixture")
    assert manifest["backend_id"] == "reference"
    assert manifest["schema_version"] == "1.0"
    artifacts = cast(list[dict[str, object]], manifest["artifacts"])
    artifact = artifacts[0]
    assert artifact["relative_path"] == "summary.json"
    assert (tmp_path / "run_fixture" / "manifest.json").is_file()


def test_cli_health_validate_and_duplicate_run_failure(tmp_path: Path, capsys: object) -> None:
    assert main(["health"]) == 0
    assert main(["validate", str(FIXTURE)]) == 0
    assert main(["run", str(FIXTURE), "--output", str(tmp_path)]) == 0
    first = json.loads(capsys.readouterr().out.splitlines()[-1])  # type: ignore[attr-defined]
    assert first["backend_id"] == "reference"


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
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
