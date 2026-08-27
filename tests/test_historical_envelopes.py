from __future__ import annotations

import builtins
import hashlib
import json
from collections.abc import Callable
from dataclasses import replace

import pytest

from flybrian_engine import (
    HistoricalControllerPhase,
    HistoricalControllerProfile,
    HistoricalControllerStage,
    HistoricalEnvelopeError,
    HistoricalExperimentEnvelope,
    HistoricalLineage,
    HistoricalOptionResolution,
    HistoricalParameter,
    HistoricalSourceAuthority,
    HistoricalVariationPatch,
    StaticExtractionLimits,
    apply_historical_variations,
    extract_static_python_experiment,
)


def minimal_fes(*, embodied: bool = False) -> dict[str, object]:
    value: dict[str, object] = {
        "spec_version": "1.0",
        "metadata": {"name": "Historical fixture"},
        "dataset": "fixture:v1",
        "sim_time_ms": 10,
        "random_seed": 42,
        "neurons": {
            "lif": {
                "1": {
                    "neuron_id": 1,
                    "model_type": "lif",
                    "poisson_inputs": [],
                    "external_currents": [],
                    "record_spikes": True,
                    "record_variables": True,
                }
            }
        },
        "artifact_requests": ["standardized_results"],
        "neuron_models": {
            "lif": {
                "family": "lif",
                "parameters": {},
            }
        },
        "simulation": {
            "integration_method": "euler",
            "time_step": {"value": 0.1, "unit": "ms"},
        },
        "execution": {
            "backend_id": "reference",
            "engine_version": ">=0.1,<1",
        },
    }
    if embodied:
        value["embodied_config"] = {
            "enabled": True,
            "drive_mode": "direct_actuator",
            "mapping_id": "fixture",
            "firing_rate_window_ms": 1,
            "flybody": {"id": "fixture.fly", "version": "1"},
            "environment": {
                "id": "flat-ground",
                "version": "1",
                "initial_conditions": {"height": 0.1},
            },
            "direct_actuator": {
                "links": [
                    {"neuron_id": 1, "actuator_id": "joint", "weight": 1}
                ]
            },
        }
        value["artifact_requests"] = ["standardized_results", "motor_commands"]
    return value


def source_for(data: bytes) -> HistoricalSourceAuthority:
    return HistoricalSourceAuthority(
        repository="https://example.test/flybrian-history",
        revision="a" * 40,
        logical_path="experiments/example.py",
        byte_length=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        license_id="MIT",
        access="public",
        redistribution="allowed",
        extractor_id="org.flybrian.static-python-extractor",
        extractor_version="1.1",
    )


def remove_mapping_field(value: dict[str, object], container: str, field: str) -> object:
    mapping = value[container]
    assert isinstance(mapping, dict)
    return mapping.pop(field)


def option(
    option_id: str = "simulation.seed",
    *,
    effective_value: object = 42,
) -> HistoricalOptionResolution:
    return HistoricalOptionResolution(
        option_id=option_id,
        legacy_names=("--seed",),
        value_kind="integer",
        unit="1",
        default_value=42,
        requested_value=None,
        effective_value=effective_value,
        origin="default",
        application="applied",
        resolution_rule="declared_precedence.v1",
        target="/random_seed",
        notes="Source default",
    )


def controller() -> HistoricalControllerProfile:
    return HistoricalControllerProfile(
        profile_id="org.flybrian.controller.fixture",
        version="1.0",
        source="Test fixture",
        stages=(
            HistoricalControllerStage(
                stage_id="drive",
                kind="muscle_drive",
                profile_id="org.flybrian.drive.fixture",
                profile_version="1.0",
                profile_sha256="b" * 64,
                inputs=("spike_counts",),
                outputs=("muscle_drive",),
                parameters=(HistoricalParameter("normalizer", "30", "Hz"),),
                activation_condition=True,
                phases=(
                    HistoricalControllerPhase(
                        "0", "10", (HistoricalParameter("gain", "1", "1"),)
                    ),
                ),
            ),
        ),
    )


def envelope(
    *,
    fes: dict[str, object] | None = None,
    missing: tuple[str, ...] = (),
    embodied_controller: HistoricalControllerProfile | None = None,
) -> HistoricalExperimentEnvelope:
    source_bytes = b"print('fixture')\n"
    expected = None
    if fes is not None:
        expected = hashlib.sha256(
            json.dumps(
                fes, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
    return HistoricalExperimentEnvelope(
        envelope_id="org.flybrian.history.fixture",
        version="1.0",
        source=source_for(source_bytes),
        selector=None,
        invocation=("--seed", "42"),
        options=(option(),),
        controller_profile=embodied_controller,
        fes=fes,
        expected_fes_sha256=expected,
        source_artifacts=(),
        missing_requirements=missing,
        lineage=None,
    )


def test_envelope_derives_truthful_reproducibility_and_canonical_identity() -> None:
    unresolved = envelope(fes=None, missing=("DATASET", "NEURON_MODELS"))
    assert unresolved.reproducibility_class == "PROVENANCE_ONLY"
    assert unresolved.to_dict()["missing_requirements"] == [
        "DATASET",
        "NEURON_MODELS",
    ]

    neural = envelope(fes=minimal_fes())
    assert neural.reproducibility_class == "RUNNABLE_CONNECTOME"
    assert neural.sha256() == (
        "a40f4dd62d3b0fdf907c255856d9372d73e7cf6c736ec6ddaf9b46ade2f2db60"
    )
    embodied = envelope(fes=minimal_fes(embodied=True), embodied_controller=controller())
    assert embodied.reproducibility_class == "RUNNABLE_EMBODIED"
    assert embodied.sha256() == (
        "45d9edfcab74aa0d07072fd794ffd9ceca88ce76fad7b9375dead96f6e80de0d"
    )
    assert embodied.sha256() != neural.sha256()

    reordered = json.loads(json.dumps(minimal_fes(), sort_keys=False))
    reordered = dict(reversed(tuple(reordered.items())))
    assert envelope(fes=reordered).sha256() == neural.sha256()


def test_envelope_rejects_false_authority_and_non_exact_option_values() -> None:
    value = minimal_fes()
    with pytest.raises(HistoricalEnvelopeError, match="expected_fes_sha256"):
        replace(envelope(fes=value), expected_fes_sha256="0" * 64)
    with pytest.raises(HistoricalEnvelopeError, match="binary float"):
        replace(option(), value_kind="decimal", effective_value=0.1)
    with pytest.raises(HistoricalEnvelopeError, match="missing_requirements"):
        envelope(fes=value, missing=("DATASET", "DATASET"))
    incomplete = envelope(fes=minimal_fes(embodied=True), embodied_controller=None)
    assert incomplete.reproducibility_class == "PROVENANCE_ONLY"
    assert "CONTROLLER_PROFILE" in incomplete.missing_requirements

    unresolved = replace(option(), application="unresolved", effective_value=None)
    unresolved_envelope = replace(envelope(fes=value), options=(unresolved,))
    assert unresolved_envelope.reproducibility_class == "PROVENANCE_ONLY"
    assert "OPTION_RESOLUTION" in unresolved_envelope.missing_requirements

    unknown_revision = replace(
        envelope(fes=value), source=replace(source_for(b"print('fixture')\n"), revision="unknown")
    )
    assert unknown_revision.reproducibility_class == "PROVENANCE_ONLY"
    assert "SOURCE_REVISION" in unknown_revision.missing_requirements


@pytest.mark.parametrize(
    ("mutation", "missing"),
    (
        (lambda value: value.pop("neuron_models"), "NEURON_MODELS"),
        (lambda value: value.pop("simulation"), "SIMULATION_TIMING"),
        (lambda value: value.pop("execution"), "BACKEND_PROFILE"),
        (
            lambda value: remove_mapping_field(value, "embodied_config", "flybody"),
            "BODY_MODEL",
        ),
        (
            lambda value: remove_mapping_field(
                value, "embodied_config", "environment"
            ),
            "ENVIRONMENT",
        ),
        (
            lambda value: value.update(artifact_requests=["standardized_results"]),
            "ARTIFACT_CONTRACT",
        ),
    ),
)
def test_completeness_mutations_demote_runnable_status(
    mutation: Callable[[dict[str, object]], object],
    missing: str,
) -> None:
    value = minimal_fes(embodied=True)
    mutation(value)
    changed = envelope(fes=value, embodied_controller=controller())
    assert changed.reproducibility_class == "PROVENANCE_ONLY"
    assert missing in changed.missing_requirements


def test_controller_graph_rejects_cycles_overlap_and_executable_text() -> None:
    stage = controller().stages[0]
    with pytest.raises(HistoricalEnvelopeError, match="phase intervals"):
        replace(
            controller(),
            stages=(
                replace(
                    stage,
                    phases=(
                        HistoricalControllerPhase("0", "7", ()),
                        HistoricalControllerPhase("6", "10", ()),
                    ),
                ),
            ),
        )

    with pytest.raises(HistoricalEnvelopeError, match="overlap"):
        replace(
            stage,
            phases=(
                HistoricalControllerPhase("5", "10", ()),
                HistoricalControllerPhase("0", "5", ()),
            ),
        )
    with pytest.raises(HistoricalEnvelopeError, match="executable"):
        replace(
            stage,
            parameters=(HistoricalParameter("callback", "module:function", "code"),),
        )
    with pytest.raises(HistoricalEnvelopeError, match="earlier stage"):
        HistoricalControllerProfile(
            "org.flybrian.controller.bad",
            "1.0",
            "Test",
            (
                replace(stage, stage_id="first", inputs=("later",), outputs=("first",)),
                replace(stage, stage_id="second", inputs=("first",), outputs=("later",)),
            ),
        )


def test_controller_and_fes_variations_are_exact_and_non_overlapping() -> None:
    base = envelope(fes=minimal_fes(embodied=True), embodied_controller=controller())
    controller_patch = HistoricalVariationPatch(
        base_envelope_sha256=base.sha256(),
        patch_id="normalizer-31",
        target_kind="controller",
        target="/stages/drive/parameters/normalizer",
        before_canonical_value="30",
        after_canonical_value="31",
        reason="Exact controller variation",
    )
    fes_patch = HistoricalVariationPatch(
        base_envelope_sha256=base.sha256(),
        patch_id="time-step-02",
        target_kind="fes",
        target="/simulation/time_step/value",
        before_canonical_value="0.1",
        after_canonical_value="0.2",
        reason="Exact time-step variation",
    )
    varied = apply_historical_variations(
        base, (controller_patch, fes_patch), new_version="1.1"
    )
    assert varied.controller_profile is not None
    assert varied.controller_profile.stages[0].parameters[0].to_dict()["value"] == "31"
    assert varied.fes is not None
    assert varied.fes["simulation"] == {
        "integration_method": "euler",
        "time_step": {"value": 0.2, "unit": "ms"},
    }

    parent = replace(
        fes_patch,
        patch_id="simulation-parent",
        target="/simulation",
        before_canonical_value={
            "integration_method": "euler",
            "time_step": {"value": "0.1", "unit": "ms"},
        },
        after_canonical_value={
            "integration_method": "euler",
            "time_step": {"value": "0.1", "unit": "ms"},
        },
    )
    with pytest.raises(HistoricalEnvelopeError, match="overlap"):
        apply_historical_variations(
            base, (parent, fes_patch), new_version="1.1"
        )


def test_variations_require_exact_base_before_value_and_visible_seed_patch() -> None:
    base = envelope(fes=minimal_fes())
    patch = HistoricalVariationPatch(
        base_envelope_sha256=base.sha256(),
        patch_id="seed-43",
        target_kind="option",
        target="simulation.seed",
        before_canonical_value=42,
        after_canonical_value=43,
        reason="Independent seed variation",
    )
    varied = apply_historical_variations(base, (patch,), new_version="1.1")
    assert varied.version == "1.1"
    assert varied.options[0].effective_value == 43
    assert varied.fes is not None and varied.fes["random_seed"] == 43
    assert varied.lineage == HistoricalLineage(
        base.envelope_id, base.version, base.sha256(), "variation"
    )
    assert varied.sha256() != base.sha256()

    with pytest.raises(HistoricalEnvelopeError, match="base envelope"):
        apply_historical_variations(
            base,
            (replace(patch, base_envelope_sha256="0" * 64),),
            new_version="1.1",
        )
    with pytest.raises(HistoricalEnvelopeError, match="before value"):
        apply_historical_variations(
            base,
            (replace(patch, before_canonical_value=41),),
            new_version="1.1",
        )


def test_static_extractor_reads_literals_without_executing_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = b"""
import subprocess
CONFIGS = [{"label": "A", "gain": 1.5}]
parser.add_argument("--seed", type=int, default=42)
parser.add_argument("--mode", type=str, default="safe", choices=["safe", "fast"])
parser.add_argument("--enabled", action="store_true")
parser.add_argument("--dynamic", default=read_secret())
open("/must-not-open")
subprocess.run(["must-not-run"])
"""

    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("source execution boundary crossed")

    monkeypatch.setattr(builtins, "open", forbidden)
    result = extract_static_python_experiment(source, source_for(source))
    assert [item.legacy_name for item in result.options] == [
        "--seed",
        "--mode",
        "--enabled",
        "--dynamic",
    ]
    assert result.options[0].default_value == 42
    assert result.options[1].choices == ("safe", "fast")
    assert result.options[2].default_value is False
    assert result.options[3].default_value is None
    assert result.config_tables[0].name == "CONFIGS"
    assert result.config_tables[0].entry_count == 1
    assert {item.code for item in result.dispositions} == {"DYNAMIC_OPTION_DEFAULT"}
    assert result.receipt.option_count == 4
    assert result.receipt.config_entry_count == 1
    assert result.receipt.graph_sha256 == (
        "843b0bcc3b4ed1890f6ba039391631ea5937218de5945ff05ff017cbf4e1c26f"
    )


def test_static_extractor_enforces_source_identity_and_limits() -> None:
    source = b'parser.add_argument("--seed", default=42)\n'
    with pytest.raises(HistoricalEnvelopeError, match="source bytes"):
        extract_static_python_experiment(source + b"# changed\n", source_for(source))
    with pytest.raises(HistoricalEnvelopeError, match="maximum source bytes"):
        extract_static_python_experiment(
            source,
            source_for(source),
            StaticExtractionLimits(max_source_bytes=10),
        )
    with pytest.raises(HistoricalEnvelopeError, match="extractor profile"):
        extract_static_python_experiment(
            source,
            replace(source_for(source), extractor_version="1.0"),
        )
    dynamic = (
        b'parser.add_argument("--one", default=first())\n'
        b'parser.add_argument("--two", default=second())\n'
    )
    with pytest.raises(HistoricalEnvelopeError, match="maximum extraction dispositions"):
        extract_static_python_experiment(
            dynamic,
            source_for(dynamic),
            StaticExtractionLimits(max_dispositions=1),
        )


def test_source_authority_excludes_local_and_temporal_receipt_state() -> None:
    data = b"pass\n"
    source = source_for(data)
    serialized = source.to_dict()
    assert "local_path" not in serialized
    assert "timestamp" not in serialized
    assert source.sha256 == hashlib.sha256(data).hexdigest()
