from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import cast

import pytest

from flybrian_engine import (
    BUNDLED_REVIEWED_CHAMPIONS_EXPORT_SHA256,
    HistoricalCatalogExportError,
    HistoricalCatalogExportRecord,
    build_reviewed_champions_export,
    load_bundled_reviewed_champions_export,
    reviewed_champions_authorities,
    validate_historical_estate_projection,
)

EXPECTED_EXTERNAL_KEYS = (
    "flybrian-serve:champion:C104_self_coupling_breakthrough",
    "flybrian-serve:champion:C109_motor_sign_fix",
    "flybrian-serve:champion:C131_WQS_v2_record",
    "flybrian-serve:champion:C145_walking_champion",
    "flybrian-serve:champion:C161_E2_walking_exploration",
    "flybrian-serve:champion:C173_VLM_standing_champion",
    "flybrian-serve:champion:C177_warmup_champion",
    "flybrian-serve:champion:C180_fxs_sweep_Basin_L",
    "flybrian-serve:champion:C180_standing_champion",
    "flybrian-serve:champion:C181_good_backup_uniform",
    "flybrian-serve:champion:C181_partial_flip_champion",
    "flybrian-serve:champion:C182_standing_champion",
)


def _projected_artifacts(record: HistoricalCatalogExportRecord) -> list[dict[str, object]]:
    historical = cast(dict[str, object], record.spec_json["historical_record"])
    return cast(list[dict[str, object]], historical["artifacts"])


def test_reviewed_champions_are_a_real_engine_validated_provenance_cohort() -> None:
    inventories, envelopes, projection = reviewed_champions_authorities()
    assert (
        validate_historical_estate_projection(
            projection,
            inventories=inventories,
            envelopes=envelopes,
        )
        is projection
    )

    export = build_reviewed_champions_export()
    assert export.projection_sha256 == projection.sha256()
    assert export.import_sha256 == projection.import_sha256()
    assert export.record_count == 12
    assert tuple(record.external_source_key for record in export.records) == (
        EXPECTED_EXTERNAL_KEYS
    )
    assert {record.reproducibility_class for record in export.records} == {"PROVENANCE_ONLY"}
    assert {record.visibility for record in export.records} == {"public"}
    assert {record.spec_version for record in export.records} == {"historical/provenance-1"}
    assert all(record.missing_requirements for record in export.records)
    assert all(
        artifact["availability"] in {"unavailable", "failed"}
        for record in export.records
        for artifact in _projected_artifacts(record)
    )


def test_reviewed_source_paths_are_regular_portable_authorities_not_symlink_aliases() -> None:
    _inventories, _envelopes, projection = reviewed_champions_authorities()
    paths = {run.source_repository_path for run in projection.runs}
    assert {
        "scripts/tools/cycle104_stride_regularity.py",
        "scripts/tools/cycle109_motor_range_diagnostic.py",
        "scripts/tools/cycle131_phase5_combined_stack.py",
        "scripts/tools/cycle145_phase5_combined.py",
        "experiments/c161_phase_e2_dng100_walking.py",
    }.issubset(paths)
    assert (
        not {
            "scripts/cycle104_stride_regularity.py",
            "scripts/cycle109_motor_range_diagnostic.py",
            "scripts/cycle131_phase5_combined_stack.py",
            "scripts/cycle145_phase5_combined.py",
            "experiments/c161_phase_e2_dng100.py",
        }
        & paths
    )


def test_bundled_export_is_byte_exact_and_contains_no_host_or_private_bytes() -> None:
    built = build_reviewed_champions_export()
    loaded = load_bundled_reviewed_champions_export()
    assert loaded == built
    assert built.sha256() == BUNDLED_REVIEWED_CHAMPIONS_EXPORT_SHA256
    assert hashlib.sha256(built.canonical_bytes()).hexdigest() == (
        BUNDLED_REVIEWED_CHAMPIONS_EXPORT_SHA256
    )
    text = built.canonical_bytes().decode("utf-8")
    assert "/Users/" not in text
    assert "tyroachford" not in text.casefold()
    assert "credential" not in text.casefold()
    assert "private_key" not in text.casefold()
    assert "source_code" not in text
    assert "artifact_bytes" not in text


def test_catalog_export_identity_changes_with_reviewed_metadata() -> None:
    export = build_reviewed_champions_export()
    first = export.records[0]
    changed = dataclasses.replace(first, description=f"{first.description} Reviewed change.")
    changed_export = dataclasses.replace(export, records=(changed, *export.records[1:]))
    assert changed.source_metadata_checksum_sha256 != first.source_metadata_checksum_sha256
    assert changed_export.sha256() != export.sha256()


def test_bundled_loader_rejects_class_and_hash_tampering() -> None:
    raw = json.loads(build_reviewed_champions_export().canonical_bytes())
    raw["records"][0]["reproducibilityClass"] = "RUNNABLE_EMBODIED"
    data = json.dumps(raw, separators=(",", ":"), sort_keys=True).encode()
    with pytest.raises(HistoricalCatalogExportError, match="reproducibility"):
        load_bundled_reviewed_champions_export(data=data)

    raw = json.loads(build_reviewed_champions_export().canonical_bytes())
    raw["projectionSha256"] = "0" * 64
    data = json.dumps(raw, separators=(",", ":"), sort_keys=True).encode()
    with pytest.raises(HistoricalCatalogExportError, match="projection"):
        load_bundled_reviewed_champions_export(data=data)


def test_catalog_export_strictly_rejects_unknown_fields_and_binary_floats() -> None:
    raw = json.loads(build_reviewed_champions_export().canonical_bytes())
    raw["unknown"] = True
    with pytest.raises(HistoricalCatalogExportError, match="fields differ"):
        load_bundled_reviewed_champions_export(
            data=json.dumps(raw, separators=(",", ":"), sort_keys=True).encode()
        )

    text = build_reviewed_champions_export().canonical_bytes().decode("utf-8")
    altered = text.replace('"recordCount":12', '"recordCount":12.0', 1).encode()
    with pytest.raises(HistoricalCatalogExportError, match="floats"):
        load_bundled_reviewed_champions_export(data=altered)
