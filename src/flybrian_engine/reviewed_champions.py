"""Reviewed source-only launch cohort for FlyBrian's historical champions."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from importlib.resources import files
from pathlib import Path
from typing import Literal

from .historical_c174 import resolve_c174_experiment
from .historical_corpus import (
    HistoricalCatalogExport,
    HistoricalCatalogExportError,
    HistoricalCatalogMetadata,
    build_historical_catalog_export,
    load_historical_catalog_export_json,
)
from .historical_envelopes import (
    STATIC_PYTHON_EXTRACTOR_ID,
    STATIC_PYTHON_EXTRACTOR_VERSION,
    HistoricalExperimentEnvelope,
    HistoricalSourceAuthority,
)
from .historical_estate import (
    HistoricalEstateCollection,
    HistoricalEstateFile,
    HistoricalEstateInventory,
    HistoricalEstateRoot,
    classify_historical_estate_file,
)
from .historical_projection import (
    HistoricalContributor,
    HistoricalEnvelopeReference,
    HistoricalEstateProjection,
    HistoricalEvidenceReference,
    HistoricalInventoryReference,
    HistoricalProjectedArtifact,
    HistoricalProjectedRun,
    HistoricalProjectionReview,
    HistoricalVisibilityPolicy,
    validate_historical_estate_projection,
)

REVIEWED_CHAMPIONS_SOURCE_REVISION = "d08d4a8cd20b44d54a583515ccb39586d505215d"
BUNDLED_REVIEWED_CHAMPIONS_EXPORT_SHA256 = (
    "275037b39263bf5aac579c388c521496f9b327f472a44c7e8cd03510fc0b3cad"
)

_ROOT_ID = "org.flybrian.estate.reviewed-champions-source-v1"
_PROJECTION_ID = "org.flybrian.historical.reviewed-champions-v1"
_CONTRIBUTOR_ID = "org.flybrian.contributor.research-corpus"
_GENERIC_MISSING_REQUIREMENTS = (
    "ARTIFACT_CONTRACT",
    "BACKEND_PROFILE",
    "BODY_MODEL",
    "CONNECTIVITY",
    "CONTROLLER_PROFILE",
    "DATASET_RELEASE",
    "DEPENDENCY_LOCK",
    "ENVIRONMENT",
    "FES",
    "INITIAL_STATE",
    "MOTOR_MAPPING",
    "NEURON_MODELS",
    "NEURON_SELECTION",
    "OPTION_RESOLUTION",
    "RESULT_EVIDENCE",
    "SIMULATION_TIMING",
    "UNIT_AUTHORITY",
)


def _source_file(
    logical_path: str,
    byte_length: int,
    sha256: str,
) -> HistoricalEstateFile:
    media_kind, role, disposition = classify_historical_estate_file(logical_path)
    return HistoricalEstateFile(
        logical_path=logical_path,
        byte_length=byte_length,
        sha256=sha256,
        media_kind=media_kind,
        candidate_role=role,
        import_disposition=disposition,
        collection=logical_path.split("/", 1)[0],
    )


_SOURCE_FILES = tuple(
    sorted(
        (
            _source_file(
                "scripts/tools/cycle131_phase5_combined_stack.py",
                20_993,
                "d6d63aa65a531068a54ba1b37c44315b37ac237fa402086d4f2af04fb8ea948c",
            ),
            _source_file(
                "scripts/tools/cycle145_phase5_combined.py",
                23_506,
                "11da8887199881fd5e2fb24c295d3cb1965873bfe061f7c106daf04b225d5ad7",
            ),
            _source_file(
                "scripts/tools/cycle109_motor_range_diagnostic.py",
                16_272,
                "8aac11fe3209684502142e671ebc710e6c8e09f05d71b9a5a8475f943e43d54b",
            ),
            _source_file(
                "scripts/tools/cycle104_stride_regularity.py",
                33_454,
                "3b9c2cca87cfd8106a80d0ec382c5bc138cc55e9cf1c8672e3c0fbe8f1d7d297",
            ),
            _source_file(
                "experiments/c173_phase1c_hill_standing.py",
                38_618,
                "4e3dff8aef47d09773779cb600d1ed15f04afcb4598b8a3cc1de104be31ff7b0",
            ),
            _source_file(
                "experiments/c174_phase1_per_muscle.py",
                144_532,
                "35b2cf1e2e18fe0ef512a567dc474c279a02c0f6f8cb08adbd990eb9c89f4038",
            ),
            _source_file(
                "experiments/c161_phase_e2_dng100_walking.py",
                36_949,
                "f7fbbcff2e4da7e7a3058d78a7117d206c09adbc9c20bb230e1c778eb1d02209",
            ),
            _source_file(
                "experiments/c182_phase_b3_multiseed.py",
                5_942,
                "82aed2fe460df6c6b42d681b715d4ed1603e9b4a0ee3e4fa14b77ab340da5013",
            ),
        ),
        key=lambda item: item.logical_path,
    )
)
_FILE_BY_PATH = {item.logical_path: item for item in _SOURCE_FILES}


def _source_inventory() -> HistoricalEstateInventory:
    return HistoricalEstateInventory(
        root=HistoricalEstateRoot(
            root_id=_ROOT_ID,
            revision=REVIEWED_CHAMPIONS_SOURCE_REVISION,
            logical_root="flybrian-serve/reviewed-champions-v1",
            license_id="proprietary-unpublished",
            access="private",
            redistribution="prohibited",
            physical_root=Path("."),
        ),
        files=_SOURCE_FILES,
        exclusions=(),
        collections=(
            HistoricalEstateCollection(
                "experiments",
                4,
                226_041,
                (("source", 4),),
            ),
            HistoricalEstateCollection(
                "scripts",
                4,
                94_225,
                (("source", 4),),
            ),
        ),
        total_file_count=8,
        excluded_entry_count=0,
        total_bytes=320_266,
    )


def _source_authority(logical_path: str) -> HistoricalSourceAuthority:
    item = _FILE_BY_PATH[logical_path]
    return HistoricalSourceAuthority(
        repository="flybrian-serve",
        revision=REVIEWED_CHAMPIONS_SOURCE_REVISION,
        logical_path=logical_path,
        byte_length=item.byte_length,
        sha256=item.sha256,
        license_id="proprietary-unpublished",
        access="private",
        redistribution="not-allowed",
        extractor_id=STATIC_PYTHON_EXTRACTOR_ID,
        extractor_version=STATIC_PYTHON_EXTRACTOR_VERSION,
    )


def _generic_envelope(
    champion_id: str,
    source_path: str,
    invocation: Sequence[str],
    *,
    selector: str | None = None,
    extra_missing: Sequence[str] = (),
) -> HistoricalExperimentEnvelope:
    return HistoricalExperimentEnvelope(
        envelope_id=f"org.flybrian.history.champion.{champion_id.casefold().replace('_', '-')}",
        version="1.0",
        source=_source_authority(source_path),
        selector=selector,
        invocation=tuple(invocation),
        options=(),
        controller_profile=None,
        fes=None,
        expected_fes_sha256=None,
        source_artifacts=(),
        missing_requirements=tuple(sorted(set(_GENERIC_MISSING_REQUIREMENTS) | set(extra_missing))),
        lineage=None,
    )


def _c174_envelope(
    requested_values: Mapping[str, object],
    invocation: Sequence[str],
) -> HistoricalExperimentEnvelope:
    return resolve_c174_experiment(
        4,
        requested_values,
        invocation=tuple(invocation),
    ).envelope


_C177_VALUES: dict[str, object] = {
    "--seed": 42,
    "--sim-ms": 5_000,
    "--femur-scale": "1.5",
    "--ts-mult": "7.75",
    "--t1-ab": "0.97",
    "--t3-ab": "1.4",
    "--warmup": ["0.2", "0.4", "1.0"],
    "--ft-stiff": "0.0",
    "--coxa-stiff": "0.0",
    "--poisson-n": 10,
    "--no-poisson-mn": True,
}
_C181_PARTIAL_VALUES: dict[str, object] = {
    "--seed": 42,
    "--sim-ms": 5_000,
    "--ts-mult": "7.75",
    "--t1-ab": "0.97",
    "--t3-ab": "1.4",
    "--ft-stiff": "0.0",
    "--coxa-stiff": "0.0",
    "--poisson-n": 10,
    "--no-poisson-mn": True,
}
_C181_UNIFORM_VALUES: dict[str, object] = {
    "--seed": 42,
    "--sim-ms": 5_000,
    "--ts-mult": "7.75",
    "--ft-stiff": "0.0",
    "--coxa-stiff": "0.0",
    "--poisson-n": 10,
    "--no-poisson-mn": True,
}


def _invocation(source_path: str, values: Mapping[str, object]) -> tuple[str, ...]:
    result = [source_path, "--index", "4"]
    for key, value in values.items():
        if key == "--no-poisson-mn":
            if value is True:
                result.append(key)
            continue
        result.append(key)
        if isinstance(value, list):
            result.extend(str(item) for item in value)
        else:
            result.append(str(value))
    return tuple(result)


def _envelopes_by_champion() -> dict[str, HistoricalExperimentEnvelope]:
    c177_invocation = _invocation("experiments/c174_phase1_per_muscle.py", _C177_VALUES)
    c181_partial_invocation = _invocation(
        "experiments/c174_phase1_per_muscle.py", _C181_PARTIAL_VALUES
    )
    c181_uniform_invocation = _invocation(
        "experiments/c174_phase1_per_muscle.py", _C181_UNIFORM_VALUES
    )
    shared_c177 = _c174_envelope(_C177_VALUES, c177_invocation)
    return {
        "C104_self_coupling_breakthrough": _generic_envelope(
            "C104_self_coupling_breakthrough",
            "scripts/tools/cycle104_stride_regularity.py",
            ("scripts/cycle104_stride_regularity.py",),
        ),
        "C109_motor_sign_fix": _generic_envelope(
            "C109_motor_sign_fix",
            "scripts/tools/cycle109_motor_range_diagnostic.py",
            ("scripts/cycle109_motor_range_diagnostic.py",),
        ),
        "C131_WQS_v2_record": _generic_envelope(
            "C131_WQS_v2_record",
            "scripts/tools/cycle131_phase5_combined_stack.py",
            ("scripts/cycle131_phase5_combined_stack.py",),
        ),
        "C145_walking_champion": _generic_envelope(
            "C145_walking_champion",
            "scripts/tools/cycle145_phase5_combined.py",
            ("scripts/c145_phase5_combined.py",),
        ),
        "C161_E2_walking_exploration": _generic_envelope(
            "C161_E2_walking_exploration",
            "experiments/c161_phase_e2_dng100_walking.py",
            ("experiments/c161_phase_e2_dng100.py", "--index", "<0-13>"),
            selector="unresolved <0-13>",
            extra_missing=("SOURCE_PATH_CORRECTION",),
        ),
        "C173_VLM_standing_champion": _generic_envelope(
            "C173_VLM_standing_champion",
            "experiments/c173_phase1c_hill_standing.py",
            ("experiments/c173_phase1c_hill_standing.py", "--index", "21"),
            selector="21",
        ),
        "C177_warmup_champion": shared_c177,
        "C180_fxs_sweep_Basin_L": shared_c177,
        "C180_standing_champion": shared_c177,
        "C181_good_backup_uniform": _c174_envelope(_C181_UNIFORM_VALUES, c181_uniform_invocation),
        "C181_partial_flip_champion": _c174_envelope(_C181_PARTIAL_VALUES, c181_partial_invocation),
        "C182_standing_champion": _generic_envelope(
            "C182_standing_champion",
            "experiments/c182_phase_b3_multiseed.py",
            ("experiments/c182_phase_b3_multiseed.py",),
        ),
    }


_CATALOG_TEXT: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "C104_self_coupling_breakthrough": (
        ("C104_self_coupling_breakthrough: Self-coupling stride regularity (s9_x1 breakthrough)"),
        (
            "Curated walking experiment from the FlyBrian research corpus. Score: Qualitative "
            "breakthrough — first regular stepping. Historical milestone. Self-coupling in the "
            "CPG network produced the first regular stepping pattern, enabling all subsequent "
            "gait analysis. Also see cycle104b_fine_tune.py for parameter refinement."
        ),
        ("champion", "historical", "provenance", "walking"),
    ),
    "C109_motor_sign_fix": (
        "C109_motor_sign_fix: First real walking (motor sign correction breakthrough)",
        (
            "Curated walking experiment from the FlyBrian research corpus. Score: Qualitative "
            "breakthrough — first forward locomotion. Historical milestone. The motor sign "
            "correction made neural output map to anatomically correct joint torques and unlocked "
            "later walking work. No structured output directory exists from this era."
        ),
        ("champion", "historical", "provenance", "walking"),
    ),
    "C131_WQS_v2_record": (
        "C131_WQS_v2_record: WQS v2 (Walking Quality Score)",
        (
            "Curated walking experiment from the FlyBrian research corpus. Score: 10/13. "
            "Combined coxa control, femur control, stance blend, and i1 scaling; 6/6 legs "
            "stepped across 121 recorded strides. Complete execution parameters and result "
            "linkage remain under review."
        ),
        ("champion", "historical", "provenance", "walking"),
    ),
    "C145_walking_champion": (
        (
            "C145_walking_champion: WQS + visual quality "
            "(final walking champion before standing pivot)"
        ),
        (
            "Curated walking experiment from the FlyBrian research corpus. Score: 6/13 WQS "
            "across an 18-configuration, 56-run campaign using bCS_top10 and IN01B001. The "
            "reviewed source path corrects a historical symlink command; exact result/video "
            "edges remain unavailable in this cohort."
        ),
        ("champion", "historical", "provenance", "walking"),
    ),
    "C161_E2_walking_exploration": (
        "C161_E2_walking_exploration: DNg100 walking exploration (E1/E2 phases)",
        (
            "Curated walking experiment from the FlyBrian research corpus. Fourteen DNg100 "
            "drive configurations were recorded as standing-only. The historical command "
            "contains an unresolved <0-13> selector and stale source name, and its referenced "
            "summary is absent, so exact rerun remains unavailable."
        ),
        ("champion", "historical", "provenance", "walking"),
    ),
    "C173_VLM_standing_champion": (
        "C173_VLM_standing_champion: VLM composite standing score",
        (
            "Curated standing experiment from the FlyBrian research corpus. Reported score: "
            "7.9/10 combined with Hill-type muscle dynamics and an error-gated resistance-reflex "
            "proxy. Exact dataset, controller execution, and result evidence remain under review."
        ),
        ("champion", "historical", "provenance", "standing"),
    ),
    "C177_warmup_champion": (
        "C177_warmup_champion: Best pitch (closest to 0°) with tarsi=6/6",
        (
            "Curated standing experiment from the FlyBrian research corpus. Reported pitch=-4.8°, "
            "tarsi=6/6, and hCV=0.056 using a [0.2, 0.4, 1.0] warmup profile. Its exact "
            "C174 options are reviewed, while body/data/executor/result authorities remain "
            "incomplete."
        ),
        ("champion", "historical", "provenance", "standing"),
    ),
    "C180_fxs_sweep_Basin_L": (
        "C180_fxs_sweep_Basin_L: fxs=1.5 sweep reference (Basin L baseline)",
        (
            "Curated standing experiment from the FlyBrian research corpus. Reported pitch=-8.4°, "
            "hCV=0.162, and tarsi=6/6. It shares an exact reviewed C174 invocation with other "
            "historical labels; no scientific equivalence or result edge is inferred from that "
            "duplication."
        ),
        ("champion", "historical", "provenance", "standing"),
    ),
    "C180_standing_champion": (
        "C180_standing_champion: Best combined standing metrics (post T3-flip)",
        (
            "Curated standing experiment from the FlyBrian research corpus. Reported pitch=-10.8°, "
            "hCV=0.076, tarsi=6/6, and VLM=7.1. Later observations reported reproduction drift, "
            "so this exact reviewed C174 invocation remains provenance-only."
        ),
        ("champion", "historical", "provenance", "standing"),
    ),
    "C181_good_backup_uniform": (
        "C181_good_backup_uniform: Best T3 stance angles (uniform ab=1.0)",
        (
            "Curated standing experiment from the FlyBrian research corpus. Reported pitch=-10.5° "
            "and T3 coxa-abduction stance +14°. A dual-view review marked the lateral result as a "
            "false positive; exact artifact linkage remains unavailable."
        ),
        ("champion", "historical", "provenance", "standing"),
    ),
    "C181_partial_flip_champion": (
        "C181_partial_flip_champion: Best pitch with partial T3 flip (no warmup, no fxs)",
        (
            "Curated standing experiment from the FlyBrian research corpus. Reported pitch=-12.2°, "
            "hCV=0.084, tarsi=6/6, and lateral VLM=7.4 during the Basin H regression "
            "investigation. Exact reviewed C174 options are preserved without a runnable claim."
        ),
        ("champion", "historical", "provenance", "standing"),
    ),
    "C182_standing_champion": (
        "C182_standing_champion: Multi-seed standing (5/5 pass)",
        (
            "Curated standing experiment from the FlyBrian research corpus. The campaign reported "
            "all gates passing across five seeds with 6/6 tarsi. Complete option, dataset, "
            "controller, unit, and result authorities remain under review."
        ),
        ("champion", "historical", "provenance", "standing"),
    ),
}


def _slug(champion_id: str) -> str:
    return champion_id.casefold().replace("_", "-")


def _envelope_reference(envelope: HistoricalExperimentEnvelope) -> HistoricalEnvelopeReference:
    return HistoricalEnvelopeReference(
        envelope_id=envelope.envelope_id,
        version=envelope.version,
        envelope_sha256=envelope.sha256(),
        reproducibility_class=envelope.reproducibility_class,
        fes_sha256=envelope.expected_fes_sha256,
        missing_requirements=envelope.missing_requirements,
    )


def _artifacts(champion_id: str) -> tuple[HistoricalProjectedArtifact, ...]:
    slug = _slug(champion_id)
    result_availability: Literal["unavailable", "failed"] = (
        "failed" if champion_id == "C161_E2_walking_exploration" else "unavailable"
    )
    result_reason = (
        "The consolidation result reference is absent from the reviewed estate observation."
        if result_availability == "failed"
        else (
            "No immutable reviewed result edge and redistribution authority are included "
            "in this cohort."
        )
    )
    return (
        HistoricalProjectedArtifact(
            artifact_id=f"org.flybrian.historical.artifact.{slug}.motor-commands",
            kind="motor_commands",
            availability="unavailable",
            evidence=None,
            reason="No reviewed historical motor-command artifact is available for DigiFly replay.",
        ),
        HistoricalProjectedArtifact(
            artifact_id=f"org.flybrian.historical.artifact.{slug}.result",
            kind="result",
            availability=result_availability,
            evidence=None,
            reason=result_reason,
        ),
        HistoricalProjectedArtifact(
            artifact_id=f"org.flybrian.historical.artifact.{slug}.video",
            kind="video",
            availability="unavailable",
            evidence=None,
            reason=(
                "No immutable reviewed video edge and serving authority are included "
                "in this cohort."
            ),
        ),
    )


def reviewed_champions_authorities() -> tuple[
    tuple[HistoricalEstateInventory, ...],
    tuple[HistoricalExperimentEnvelope, ...],
    HistoricalEstateProjection,
]:
    """Construct and jointly validate the immutable reviewed champion authorities."""

    inventory = _source_inventory()
    envelopes_by_champion = _envelopes_by_champion()
    inventory_sha256 = inventory.sha256()
    runs: list[HistoricalProjectedRun] = []
    for champion_id, envelope in envelopes_by_champion.items():
        source_item = _FILE_BY_PATH[envelope.source.logical_path]
        slug = _slug(champion_id)
        runs.append(
            HistoricalProjectedRun(
                design_id=f"org.flybrian.historical.champion.{slug}",
                design_version=1,
                run_id=f"org.flybrian.historical.run.{slug}",
                contributor_id=_CONTRIBUTOR_ID,
                visibility=HistoricalVisibilityPolicy("public", None),
                source=HistoricalEvidenceReference(
                    root_id=_ROOT_ID,
                    inventory_sha256=inventory_sha256,
                    logical_path=source_item.logical_path,
                    byte_length=source_item.byte_length,
                    file_sha256=source_item.sha256,
                    candidate_role="source",
                ),
                source_repository_path=source_item.logical_path,
                envelope=_envelope_reference(envelope),
                artifacts=_artifacts(champion_id),
            )
        )
    projection = HistoricalEstateProjection(
        projection_id=_PROJECTION_ID,
        version="1.0",
        review=HistoricalProjectionReview(
            review_authority_id="org.flybrian.review.launch-corpus",
            review_revision="2026-08-27.1",
            evidence=(
                "Engineering provenance review of the 12 curated champion identities against "
                "flybrian-serve source revision d08d4a8; source-only cohort with no historical "
                "artifact-byte redistribution or runnable certification."
            ),
        ),
        inventories=(HistoricalInventoryReference(_ROOT_ID, inventory_sha256),),
        contributors=(
            HistoricalContributor(
                contributor_id=_CONTRIBUTOR_ID,
                display_name="FlyBrian research corpus",
                attribution=(
                    "Historical FlyBrian research campaign; individual contributor attribution "
                    "remains under review."
                ),
            ),
        ),
        runs=tuple(sorted(runs, key=lambda item: item.identity)),
    )
    unique_envelopes = {
        (item.envelope_id, item.version, item.sha256()): item
        for item in envelopes_by_champion.values()
    }
    envelopes = tuple(unique_envelopes[key] for key in sorted(unique_envelopes))
    validate_historical_estate_projection(
        projection,
        inventories=(inventory,),
        envelopes=envelopes,
    )
    return (inventory,), envelopes, projection


def build_reviewed_champions_export() -> HistoricalCatalogExport:
    """Build the deterministic public catalog export from reviewed engine authorities."""

    _inventories, envelopes, projection = reviewed_champions_authorities()
    metadata: list[HistoricalCatalogMetadata] = []
    champion_by_design = {
        f"org.flybrian.historical.champion.{_slug(champion_id)}": champion_id
        for champion_id in _CATALOG_TEXT
    }
    for run in projection.runs:
        champion_id = champion_by_design[run.design_id]
        name, description, tags = _CATALOG_TEXT[champion_id]
        metadata.append(
            HistoricalCatalogMetadata(
                design_id=run.design_id,
                design_version=run.design_version,
                run_id=run.run_id,
                external_source_key=f"flybrian-serve:champion:{champion_id}",
                name=name,
                description=description,
                tags=tags,
                commit_message=f"Imported reviewed FlyBrian champion {champion_id}",
            )
        )
    return build_historical_catalog_export(
        projection,
        envelopes=envelopes,
        metadata=tuple(metadata),
    )


def load_bundled_reviewed_champions_export(
    *,
    data: bytes | None = None,
) -> HistoricalCatalogExport:
    """Load the exact generated export included in the installed engine package."""

    if data is None:
        data = files("flybrian_engine").joinpath("data/reviewed_champions_v1.json").read_bytes()
    loaded = load_historical_catalog_export_json(data)
    built = build_reviewed_champions_export()
    if loaded.projection_sha256 != built.projection_sha256:
        raise HistoricalCatalogExportError(
            "bundled reviewed champions projection differs from engine authority"
        )
    if loaded.import_sha256 != built.import_sha256:
        raise HistoricalCatalogExportError(
            "bundled reviewed champions import differs from engine authority"
        )
    if loaded != built:
        raise HistoricalCatalogExportError(
            "bundled reviewed champions export differs from engine authority"
        )
    if loaded.sha256() != BUNDLED_REVIEWED_CHAMPIONS_EXPORT_SHA256:
        raise HistoricalCatalogExportError(
            "bundled reviewed champions export differs from pinned SHA-256"
        )
    return loaded
