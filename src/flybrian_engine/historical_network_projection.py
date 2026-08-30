"""Merge source-captured neural populations into the canonical projection manifest."""

from __future__ import annotations

import copy
from collections.abc import Mapping

from .historical_normalization import (
    HistoricalNormalizationError,
    canonical_sha256,
)


def merge_historical_network_projection(
    manifest: Mapping[str, object],
    normalized_bundle: Mapping[str, object],
    capture_receipt: Mapping[str, object],
) -> dict[str, object]:
    """Associate every definition in one captured writer collection automatically."""

    if manifest.get("schemaVersion") != "flybrian-historical-network-projections/2":
        raise HistoricalNormalizationError("network projection manifest version is unsupported")
    collection_id = capture_receipt.get("collection_id")
    source_revision = capture_receipt.get("source_revision")
    source_sha256 = capture_receipt.get("source_sha256")
    projection = capture_receipt.get("network_projection")
    if (
        not isinstance(collection_id, str)
        or not isinstance(source_revision, str)
        or not isinstance(source_sha256, str)
        or not isinstance(projection, dict)
    ):
        raise HistoricalNormalizationError("network projection capture receipt is incomplete")
    if manifest.get("sourceRevision") != source_revision:
        raise HistoricalNormalizationError("capture and manifest source revisions differ")
    projection_sha256 = projection.get("sha256")
    if not isinstance(projection_sha256, str):
        raise HistoricalNormalizationError("captured network projection has no identity")
    projection_without_identity = {
        key: value for key, value in projection.items() if key != "sha256"
    }
    if canonical_sha256(projection_without_identity) != projection_sha256:
        raise HistoricalNormalizationError("captured network projection identity differs")

    definitions = normalized_bundle.get("definitions")
    if not isinstance(definitions, list):
        raise HistoricalNormalizationError("normalized bundle definitions are missing")
    selected: list[tuple[str, str]] = []
    for definition in definitions:
        if not isinstance(definition, dict):
            raise HistoricalNormalizationError("normalized definition is malformed")
        configuration = definition.get("scientific_configuration")
        implementation = (
            configuration.get("implementation") if isinstance(configuration, dict) else None
        )
        if not isinstance(implementation, dict):
            continue
        if implementation.get("writer_collection") != collection_id:
            continue
        definition_id = definition.get("definition_id")
        selector = implementation.get("writer_selector")
        if not isinstance(definition_id, str) or not isinstance(selector, str):
            raise HistoricalNormalizationError("normalized writer identity is incomplete")
        selected.append((definition_id, selector))
    if not selected:
        raise HistoricalNormalizationError(
            f"normalized bundle contains no definitions for {collection_id}"
        )

    result = copy.deepcopy(dict(manifest))
    collections = result.get("collections")
    projections = result.get("projections")
    definition_projection_ids = result.get("definitionProjectionIds")
    unknown_definition_ids = result.get("unknownDefinitionIds")
    if (
        not isinstance(collections, dict)
        or not isinstance(projections, dict)
        or not isinstance(definition_projection_ids, dict)
        or not isinstance(unknown_definition_ids, list)
    ):
        raise HistoricalNormalizationError("network projection manifest is malformed")
    projections[projection_sha256] = copy.deepcopy(projection)
    collections[collection_id] = {
        "captureReceiptSha256": capture_receipt.get("sha256"),
        "selectors": {
            selector: projection_sha256 for _, selector in sorted(selected)
        },
        "sourceSha256": source_sha256,
    }
    selected_ids = {definition_id for definition_id, _ in selected}
    for definition_id in selected_ids:
        definition_projection_ids[definition_id] = projection_sha256
    result["unknownDefinitionIds"] = sorted(
        definition_id
        for definition_id in unknown_definition_ids
        if definition_id not in selected_ids
    )
    result.pop("sha256", None)
    result["sha256"] = canonical_sha256(result)
    return result
