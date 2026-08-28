"""Reviewed normalization profiles for historical framework standing experiments."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping

from .historical_envelopes import (
    STATIC_PYTHON_EXTRACTOR_ID,
    STATIC_PYTHON_EXTRACTOR_VERSION,
    HistoricalSourceAuthority,
)
from .historical_normalization import (
    HistoricalArtifactReference,
    HistoricalClaim,
    HistoricalNormalizationBundle,
    HistoricalNormalizationError,
    HistoricalRunOccurrence,
    NormalizedExperimentDefinition,
    canonical_sha256,
)

C148_PHASE0_SOURCE_PATH = "scripts/standing/c148_phase0_standing_test.py"
C148_PHASE0_RESULT_PATH = "output/c148_phase0/phase0_results.json"
C148_PHASE0_SOURCE_SHA256 = "321fe10609d7926da4a3ac8bd0b94a0a249d0b90240d25aedc5572c43d4ca784"
C148_PHASE0_RESULT_SHA256 = "dbc9abdab7c7b1bedb3f7bd266efc134ada65798de09f35de869d8697ab5337b"
C148_PHASE0_DURATION_MS = 3_000


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _slug(value: str) -> str:
    return value.casefold().replace("_", "-").replace(".", "-")


def _decimal_text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value:
        raise HistoricalNormalizationError(f"{path} must preserve an exact JSON decimal token")
    return value


def _integer(value: object, path: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HistoricalNormalizationError(f"{path} must be an integer")
    return value


def _boolean(value: object, path: str) -> bool:
    if not isinstance(value, bool):
        raise HistoricalNormalizationError(f"{path} must be boolean")
    return value


def _text(value: object, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise HistoricalNormalizationError(f"{path} must be non-empty text")
    return value


def _source_authority(source_bytes: bytes, revision: str) -> HistoricalSourceAuthority:
    if _digest(source_bytes) != C148_PHASE0_SOURCE_SHA256:
        raise HistoricalNormalizationError("C148 phase-0 source differs from its reviewed bytes")
    return HistoricalSourceAuthority(
        repository="flybrian-serve",
        revision=revision,
        logical_path=C148_PHASE0_SOURCE_PATH,
        byte_length=len(source_bytes),
        sha256=C148_PHASE0_SOURCE_SHA256,
        license_id="proprietary-unpublished",
        access="private",
        redistribution="not-allowed",
        extractor_id=STATIC_PYTHON_EXTRACTOR_ID,
        extractor_version=STATIC_PYTHON_EXTRACTOR_VERSION,
    )


def _records(result_bytes: bytes) -> list[Mapping[str, object]]:
    if _digest(result_bytes) != C148_PHASE0_RESULT_SHA256:
        raise HistoricalNormalizationError("C148 phase-0 result differs from its reviewed bytes")
    loaded: object = json.loads(result_bytes, parse_float=str)
    if not isinstance(loaded, list) or len(loaded) != 25:
        raise HistoricalNormalizationError("C148 phase-0 result must contain 25 run records")
    records: list[Mapping[str, object]] = []
    for index, item in enumerate(loaded):
        if not isinstance(item, dict) or set(item) != {
            "config",
            "motor_scale",
            "use_rl_targets",
            "seed",
            "standing_metrics",
            "elapsed_s",
        }:
            raise HistoricalNormalizationError(
                f"C148 phase-0 result row {index} has an unreviewed shape"
            )
        records.append(item)
    return records


def build_c148_phase0_normalization_bundle(
    *,
    source_bytes: bytes,
    result_bytes: bytes,
    revision: str,
) -> HistoricalNormalizationBundle:
    """Normalize the exact five-configuration by five-seed C148 phase-0 standing sweep."""

    source = _source_authority(source_bytes, revision)
    definitions: list[NormalizedExperimentDefinition] = []
    claims: list[HistoricalClaim] = []
    occurrences: list[HistoricalRunOccurrence] = []
    artifacts: list[HistoricalArtifactReference] = []
    observed_combinations: set[tuple[str, bool, int]] = set()

    for index, record in enumerate(_records(result_bytes)):
        config_name = _text(record["config"], f"records[{index}].config")
        motor_scale = _decimal_text(record["motor_scale"], f"records[{index}].motor_scale")
        use_rl_targets = _boolean(
            record["use_rl_targets"], f"records[{index}].use_rl_targets"
        )
        seed = _integer(record["seed"], f"records[{index}].seed")
        observed_combinations.add((motor_scale, use_rl_targets, seed))
        configuration: dict[str, object] = {
            "schema_version": "1.0",
            "requested_duration_ms": C148_PHASE0_DURATION_MS,
            "effective_duration_ms": C148_PHASE0_DURATION_MS,
            "random_seed": seed,
            "selector": {"config": config_name},
            "option_definitions": [
                {
                    "option_id": "motor_scale",
                    "label": "Motor scale",
                    "value_kind": "decimal",
                    "unit": "1",
                },
                {
                    "option_id": "use_rl_targets",
                    "label": "Use RL stance targets",
                    "value_kind": "boolean",
                    "unit": None,
                },
            ],
            "option_resolutions": [
                {
                    "option_id": "motor_scale",
                    "effective_value": motor_scale,
                    "origin": "recorded_result",
                },
                {
                    "option_id": "use_rl_targets",
                    "effective_value": use_rl_targets,
                    "origin": "recorded_result",
                },
            ],
        }
        identity = canonical_sha256(
            {
                "source_sha256": source.sha256,
                "duration_ms": C148_PHASE0_DURATION_MS,
                "motor_scale": motor_scale,
                "use_rl_targets": use_rl_targets,
                "seed": seed,
            }
        )
        definition_id = f"org.flybrian.definition.c148-phase0-{identity[:16]}"
        definition = NormalizedExperimentDefinition(
            definition_id=definition_id,
            version="1.0",
            family_id="org.flybrian.family.c148-phase0-standing-test",
            scientific_configuration=configuration,
            source=source,
        )
        claim_id = f"org.flybrian.claim.c148-phase0-{_slug(config_name)}-s{seed}"
        occurrence_id = f"org.flybrian.occurrence.c148-phase0-row-{index}"
        artifact_id = f"org.flybrian.artifact.c148-phase0-row-{index}-result-batch"
        definitions.append(definition)
        claims.append(
            HistoricalClaim(
                claim_id=claim_id,
                definition_id=definition_id,
                name=f"C148 phase 0 — {config_name}, seed {seed}",
                description=(
                    "A retained 3,000 ms C148 standing run comparing RL-derived stance targets "
                    f"with the zero-position baseline at motor scale {motor_scale}."
                ),
                tags=("c148", "historical", "standing"),
            )
        )
        occurrences.append(
            HistoricalRunOccurrence(
                occurrence_id=occurrence_id,
                definition_id=definition_id,
                claim_ids=(claim_id,),
                evidence=(
                    f"{C148_PHASE0_RESULT_PATH}#/{index}",
                    f"result SHA-256 {C148_PHASE0_RESULT_SHA256}",
                    f"source SHA-256 {C148_PHASE0_SOURCE_SHA256}",
                ),
            )
        )
        artifacts.append(
            HistoricalArtifactReference(
                artifact_id=artifact_id,
                definition_id=definition_id,
                kind="result_batch",
                logical_path=C148_PHASE0_RESULT_PATH,
                byte_length=len(result_bytes),
                sha256=C148_PHASE0_RESULT_SHA256,
                disposition="bound",
                disposition_reason=(
                    f"JSON pointer /{index} is the retained result row for this occurrence."
                ),
                comparison="canonical_json",
                excluded_json_fields=("elapsed_s",),
            )
        )

    expected = {
        (motor_scale, use_rl_targets, seed)
        for motor_scale, use_rl_targets in (
            ("0.0", True),
            ("0.1", True),
            ("0.25", True),
            ("0.5", True),
            ("0.5", False),
        )
        for seed in range(5)
    }
    if observed_combinations != expected:
        raise HistoricalNormalizationError(
            "C148 phase-0 rows do not match the reviewed five-configuration, five-seed sweep"
        )
    return HistoricalNormalizationBundle(
        bundle_id="org.flybrian.normalization.c148-phase0-standing",
        version="1.0",
        definitions=tuple(definitions),
        claims=tuple(claims),
        occurrences=tuple(occurrences),
        inputs=(),
        artifacts=tuple(artifacts),
        recipes=(),
    )
