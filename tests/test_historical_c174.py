from __future__ import annotations

import builtins
from dataclasses import replace
from decimal import Decimal

import pytest

from flybrian_engine import (
    C174_OPTION_PROFILE,
    C174_PROFILE_SHA256,
    C174_SELECTORS,
    C174_SOURCE_AUTHORITY,
    C174ResolutionError,
    C174ResolvedExperiment,
    HistoricalOptionResolution,
    HistoricalVariationPatch,
    apply_c174_variations,
    resolve_c174_batch,
    resolve_c174_experiment,
)

EXPECTED_NAMES = (
    "--index",
    "--seed",
    "--j-gab",
    "--sim-ms",
    "--ft-stiff",
    "--coxa-stiff",
    "--vd",
    "--boost-min",
    "--force-gain",
    "--vrest-anti",
    "--angle-gain",
    "--ts-mult",
    "--poisson-n",
    "--no-poisson-mn",
    "--anti-boost",
    "--pro-suppress",
    "--t1-ab",
    "--t2-ab",
    "--t3-ab",
    "--warmup",
    "--pre-settle-ms",
    "--abduct-bias",
    "--abduct-stiff",
    "--t1-ts",
    "--t2-ts",
    "--t3-ts",
    "--zero-coxa-segs",
    "--coxa-scale",
    "--t1-cxs",
    "--t2-cxs",
    "--t3-cxs",
    "--femur-scale",
    "--tibia-scale",
    "--true-adex",
    "--pitch-K",
    "--pitch-tau",
    "--pitch-target",
    "--height-K",
    "--height-tau",
    "--height-target",
    "--height-dof",
    "--symmetrize-lr",
    "--l-ext-boost",
    "--tarsus-friction",
    "--init-z",
    "--troch-boost",
    "--t1-tb",
    "--t2-tb",
    "--t3-tb",
    "--jdamp-mult",
    "--cs-gain",
    "--coxa-abd-K",
    "--coxa-abd-K-t1",
    "--coxa-abd-K-t2",
    "--pro-vrest",
    "--cs-tau",
)


def resolution(result: C174ResolvedExperiment, option_id: str) -> HistoricalOptionResolution:
    return next(item for item in result.options if item.option_id == option_id)


def test_c174_profile_matches_exact_declaration_and_selector_census() -> None:
    assert tuple(item.legacy_name for item in C174_OPTION_PROFILE) == EXPECTED_NAMES
    assert tuple(item.source_line for item in C174_OPTION_PROFILE) == (
        *range(2390, 2409),
        2409,
        2413,
        2418,
        2421,
        2423,
        2425,
        2427,
        2429,
        2432,
        2435,
        2437,
        2439,
        2441,
        2444,
        2447,
        2453,
        2456,
        2459,
        2462,
        2465,
        2468,
        2471,
        2475,
        2479,
        2483,
        2488,
        2492,
        2496,
        2498,
        2500,
        2502,
        2505,
        2510,
        2512,
        2514,
        2516,
        2519,
    )
    assert len(C174_OPTION_PROFILE) == 56
    assert C174_SOURCE_AUTHORITY.sha256 == (
        "35b2cf1e2e18fe0ef512a567dc474c279a02c0f6f8cb08adbd990eb9c89f4038"
    )
    assert len(C174_SELECTORS) == 16
    assert tuple(item.selector for item in C174_SELECTORS) == tuple(range(16))
    assert C174_SELECTORS[7].force_gain_override == Decimal("1")
    assert C174_SELECTORS[13].angle_gain_override == Decimal("2")
    assert C174_PROFILE_SHA256 == (
        "e40b92239962417e718dc81c22368ef5326d74e6a6069d812e131d22bfe1aa94"
    )


def test_defaults_include_implicit_boolean_false_and_batch_expands() -> None:
    batch = resolve_c174_batch({})
    assert tuple(item.selector.selector for item in batch) == tuple(range(16))
    first = batch[0]
    assert resolution(first, "c174.drive.exclude_motor_neurons").effective_value is False
    assert resolution(first, "c174.neural.true_adex").effective_value is False
    assert resolution(first, "c174.transform.symmetrize_lr").effective_value is False
    assert first.envelope.reproducibility_class == "PROVENANCE_ONLY"
    assert first.envelope.missing_requirements == tuple(sorted(first.envelope.missing_requirements))


def test_selector_overrides_preserve_requested_and_effective_values() -> None:
    force = resolve_c174_experiment(7, {"--force-gain": "9"})
    force_option = resolution(force, "c174.feedback.force_gain")
    assert force_option.requested_value == Decimal("9")
    assert force_option.effective_value == Decimal("1")
    assert force_option.origin == "derived"
    assert force_option.application == "ignored"
    assert "OPTION_RESOLUTION" not in force.envelope.missing_requirements
    assert "SELECTOR_FORCE_OVERRIDE" in force.discrepancies

    angle = resolve_c174_experiment(13, {"--angle-gain": "9"})
    angle_option = resolution(angle, "c174.feedback.angle_gain")
    assert angle_option.requested_value == Decimal("9")
    assert angle_option.effective_value == Decimal("2")
    assert angle_option.application == "ignored"
    assert "SELECTOR_ANGLE_OVERRIDE" in angle.discrepancies


def test_null_fallback_exact_zero_and_global_gate_discrepancy() -> None:
    result = resolve_c174_experiment(
        2,
        {
            "--anti-boost": "2",
            "--t1-ab": "0",
            "--ft-stiff": "0.04",
            "--coxa-stiff": None,
            "--coxa-abd-K": "0",
            "--coxa-abd-K-t1": "2",
        },
    )
    assert resolution(result, "c174.drive.t1_anti_boost").effective_value == Decimal("0")
    assert resolution(result, "c174.body.coxa_stiffness").effective_value == Decimal("0.04")
    gated = resolution(result, "c174.body.t1_coxa_abduction_k")
    assert gated.requested_value == Decimal("2")
    assert gated.effective_value == Decimal("0")
    assert gated.application == "ignored"
    assert "GLOBAL_GATE_SUPPRESSES_TIER_OVERRIDE" in result.discrepancies
    result_stages = {item.stage_id: item for item in result.controller_profile.stages}
    assert result_stages["coxa_abduction_correction"].activation_condition is False

    active = resolve_c174_experiment(2, {"--coxa-abd-K": "1", "--coxa-abd-K-t1": "2"})
    assert resolution(active, "c174.body.t1_coxa_abduction_k").effective_value == Decimal("2")
    active_stages = {item.stage_id: item for item in active.controller_profile.stages}
    assert active_stages["coxa_abduction_correction"].activation_condition is True

    display = resolve_c174_experiment(2, {"--anti-boost": "2", "--t1-ab": "0"})
    assert "DISPLAY_TRUTHINESS_DIFFERS_FROM_EXECUTION_NULL_FALLBACK" in (display.discrepancies)


def test_modes_build_distinct_direct_and_muscle_controller_profiles() -> None:
    muscle = resolve_c174_experiment(4, {})
    direct = resolve_c174_experiment(12, {})
    assert muscle.controller_profile.sha256() != direct.controller_profile.sha256()
    assert any(stage.kind == "muscle_drive" for stage in muscle.controller_profile.stages)
    assert not any(stage.kind == "muscle_drive" for stage in direct.controller_profile.stages)
    assert any(stage.kind == "joint_torque_transform" for stage in direct.controller_profile.stages)
    assert muscle.sha256() == ("1d1cea52dad5b301ff1de0bb3d3588953cb674eb09ac5da8f32c13b93e88d579")
    assert direct.sha256() == ("1683db8e64045cca2f24f7cb6e244572c728b46e5e2d1598e5b12a00522043cc")

    warmup = resolve_c174_experiment(4, {"--sim-ms": 500, "--warmup": [2, 1, 0]})
    schedule = next(
        stage
        for stage in warmup.controller_profile.stages
        if stage.stage_id == "open_loop_schedule"
    )
    assert tuple((item.start_ms, item.end_ms) for item in schedule.phases) == (
        (Decimal("0"), Decimal("200")),
        (Decimal("200"), Decimal("400")),
        (Decimal("400"), Decimal("500")),
    )

    feedback = resolve_c174_experiment(7, {})
    stages = {item.stage_id: item for item in feedback.controller_profile.stages}
    assert stages["angle_force_feedback"].activation_condition is True
    assert stages["pitch_feedback"].activation_condition is False
    assert stages["height_feedback"].activation_condition is False
    assert stages["campaniform_feedback"].activation_condition is False

    negative_pitch = resolve_c174_experiment(2, {"--pitch-K": "-1"})
    negative_stages = {item.stage_id: item for item in negative_pitch.controller_profile.stages}
    assert negative_stages["pitch_feedback"].activation_condition is False


def test_alias_identity_invocation_and_segment_canonicalization() -> None:
    result = resolve_c174_experiment(
        2,
        {"seed": 43, "--zero-coxa-segs": ["T3", "T1", "T3"]},
        invocation=("--seed", "43"),
    )
    assert result.envelope.invocation == ("--seed", "43")
    assert resolution(result, "simulation.seed").effective_value == 43
    assert resolution(result, "c174.transform.zero_coxa_segments").effective_value == (
        "T1",
        "T3",
    )
    with pytest.raises(C174ResolutionError, match="duplicate aliases"):
        resolve_c174_experiment(2, {"seed": 43, "--seed": 44})
    with pytest.raises(C174ResolutionError, match="must not include selector"):
        resolve_c174_batch({"--index": 2})


def test_c174_variation_recomputes_controller_and_binds_lineage() -> None:
    base = resolve_c174_experiment(2, {})
    patch = HistoricalVariationPatch(
        base_envelope_sha256=base.envelope.sha256(),
        patch_id="anti-boost-1",
        target_kind="option",
        target="c174.drive.anti_boost",
        before_canonical_value="0",
        after_canonical_value="1",
        reason="Reviewed anti-gravity drive variation",
    )
    varied = apply_c174_variations(base, (patch,), new_version="1.1")
    assert resolution(varied, "c174.drive.anti_boost").effective_value == Decimal("1")
    assert resolution(varied, "c174.drive.t1_anti_boost").effective_value == Decimal("1")
    assert varied.controller_profile.sha256() != base.controller_profile.sha256()
    assert varied.envelope.lineage is not None
    assert varied.envelope.lineage.parent_sha256 == base.envelope.sha256()
    assert varied.envelope.variation_patches == (patch,)

    tier_base = resolve_c174_experiment(2, {"--anti-boost": "1", "--t1-ab": "2"})
    clear_tier = replace(
        patch,
        base_envelope_sha256=tier_base.envelope.sha256(),
        target="c174.drive.t1_anti_boost",
        before_canonical_value="2",
        after_canonical_value=None,
    )
    cleared = apply_c174_variations(tier_base, (clear_tier,), new_version="1.1")
    assert resolution(cleared, "c174.drive.t1_anti_boost").effective_value == Decimal("1")

    with pytest.raises(C174ResolutionError, match="base envelope"):
        apply_c174_variations(
            base,
            (replace(patch, base_envelope_sha256="0" * 64),),
            new_version="1.1",
        )
    with pytest.raises(C174ResolutionError, match="before value"):
        apply_c174_variations(
            base,
            (replace(patch, before_canonical_value="2"),),
            new_version="1.1",
        )

    overridden = resolve_c174_experiment(7, {})
    suppressed = replace(
        patch,
        base_envelope_sha256=overridden.envelope.sha256(),
        target="c174.feedback.force_gain",
        before_canonical_value="1",
        after_canonical_value="2",
    )
    with pytest.raises(C174ResolutionError, match="suppressed"):
        apply_c174_variations(overridden, (suppressed,), new_version="1.1")


@pytest.mark.parametrize(
    ("selector", "values", "message"),
    (
        (True, {}, "selector"),
        (16, {}, "selector"),
        (-1, {}, "selector"),
        (0, {"--unknown": 1}, "unknown"),
        (0, {"--seed": True}, "integer"),
        (0, {"--height-dof": "coxa"}, "choice"),
        (0, {"--warmup": [1, 2]}, "arity"),
        (0, {"--sim-ms": 0}, "positive"),
        (0, {"--pre-settle-ms": -1}, "non-negative"),
        (0, {"--pitch-tau": "0"}, "positive"),
        (0, {"--zero-coxa-segs": []}, "at least one segment"),
        (0, {"--zero-coxa-segs": ["T1", "T4"]}, "segment"),
        (0, {"--pitch-K": "NaN"}, "finite"),
    ),
)
def test_invalid_selector_and_option_values_reject(
    selector: object,
    values: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(C174ResolutionError, match=message):
        resolve_c174_experiment(selector, values)


def test_resolver_never_opens_or_executes_source(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> object:
        raise AssertionError("resolver crossed source execution boundary")

    monkeypatch.setattr(builtins, "open", forbidden)
    result = resolve_c174_experiment(2, {"--seed": 43, "--true-adex": True})
    assert resolution(result, "simulation.seed").effective_value == 43
    assert resolution(result, "c174.neural.true_adex").effective_value is True
