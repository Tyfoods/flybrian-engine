from __future__ import annotations

import json
from pathlib import Path

import pytest

from flybrian_engine import (
    HistoricalCensusError,
    HistoricalEstateRoot,
    build_historical_census,
    inventory_historical_estate,
)


def _inventory(root: Path):  # type: ignore[no-untyped-def]
    return inventory_historical_estate(
        HistoricalEstateRoot(
            root_id="org.flybrian.estate.census-fixture",
            revision="fixture-1",
            logical_root="output",
            license_id="MIT",
            access="private",
            redistribution="unknown",
            physical_root=root,
        )
    )


def test_census_counts_explicit_result_rows_without_promoting_diagnostics(
    tmp_path: Path,
) -> None:
    campaign = tmp_path / "campaign"
    campaign.mkdir()
    (campaign / "results.json").write_text(
        json.dumps(
            {
                "seed": 42,
                "status": "complete",
                "results": [
                    {"config": "a", "seed": 42, "elevation": -0.1},
                    {"config": "b", "seed": 43, "elevation": -0.2},
                ],
            }
        ),
        encoding="utf-8",
    )
    (campaign / "diagnostics.json").write_text(
        json.dumps([{"time_s": 0.1, "body_z": 0.2}, {"time_s": 0.2, "body_z": 0.3}]),
        encoding="utf-8",
    )
    (campaign / "broken.json").write_text("{", encoding="utf-8")
    (campaign / "replay.mp4").write_bytes(b"video")

    census = build_historical_census(_inventory(tmp_path), evidence_root=tmp_path)

    assert census.inventory_file_count == 4
    assert census.reconciled_file_count == 4
    assert len(census.run_candidates) == 2
    assert [candidate.json_pointer for candidate in census.run_candidates] == [
        "/results/0",
        "/results/1",
    ]
    dispositions = {item.logical_path: item.disposition for item in census.files}
    assert dispositions == {
        "campaign/broken.json": "unresolved_result",
        "campaign/diagnostics.json": "unresolved_result",
        "campaign/replay.mp4": "supporting_artifact",
        "campaign/results.json": "run_evidence",
    }


def test_census_rejects_evidence_changed_after_inventory(tmp_path: Path) -> None:
    result = tmp_path / "result.json"
    result.write_text('{"seed":42,"elevation":-0.1}', encoding="utf-8")
    inventory = _inventory(tmp_path)
    result.write_text('{"seed":43,"elevation":-0.1}', encoding="utf-8")

    with pytest.raises(HistoricalCensusError, match="changed after inventory"):
        build_historical_census(inventory, evidence_root=tmp_path)
