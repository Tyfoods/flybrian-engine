"""Stable simulator backend contract and explicit registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from .artifacts import ArtifactManifest
from .schema import ExperimentSpec


@dataclass(frozen=True)
class BackendCapabilities:
    backend_id: str
    backend_version: str
    experiment_spec_versions: tuple[str, ...]
    neuron_model_families: tuple[str, ...]
    embodiment_modes: tuple[str, ...]
    artifact_kinds: tuple[str, ...]
    deterministic_for_fixed_seed: bool
    scientific_execution: bool


@dataclass(frozen=True)
class CompatibilityIssue:
    code: str
    path: str
    message: str


class Backend(Protocol):
    @property
    def capabilities(self) -> BackendCapabilities: ...

    def run(self, spec: ExperimentSpec, output_dir: Path, run_id: str) -> ArtifactManifest: ...


class BackendRegistry:
    def __init__(self) -> None:
        self._backends: dict[str, Backend] = {}

    def register(self, backend: Backend) -> None:
        backend_id = backend.capabilities.backend_id
        if backend_id in self._backends:
            raise ValueError(f"backend {backend_id!r} is already registered")
        self._backends[backend_id] = backend

    def get(self, backend_id: str) -> Backend:
        try:
            return self._backends[backend_id]
        except KeyError as error:
            raise KeyError(f"unknown backend {backend_id!r}") from error

    def capabilities(self) -> tuple[BackendCapabilities, ...]:
        return tuple(backend.capabilities for backend in self._backends.values())


def assess_backend_compatibility(
    spec: ExperimentSpec,
    capabilities: BackendCapabilities,
    *,
    engine_version: str,
) -> tuple[CompatibilityIssue, ...]:
    issues: list[CompatibilityIssue] = []
    spec_version = str(spec.value["spec_version"])
    if spec_version not in capabilities.experiment_spec_versions:
        issues.append(CompatibilityIssue(
            code="unsupported_spec_version",
            path="spec_version",
            message=f"backend does not support experiment spec {spec_version!r}",
        ))
    requested = set(spec.requested_artifact_kinds)
    unsupported_artifacts = sorted(requested - set(capabilities.artifact_kinds))
    if unsupported_artifacts:
        issues.append(CompatibilityIssue(
            code="unsupported_artifact",
            path="artifact_requests",
            message="backend does not emit: " + ", ".join(unsupported_artifacts),
        ))

    if spec.embodiment_mode not in capabilities.embodiment_modes:
        issues.append(CompatibilityIssue(
            code="unsupported_embodiment_mode",
            path="embodied_config.drive_mode",
            message=f"backend does not support embodiment mode {spec.embodiment_mode!r}",
        ))

    execution = spec.value.get("execution")
    if isinstance(execution, dict):
        required_backend = execution.get("backend_id")
        if required_backend != capabilities.backend_id:
            issues.append(CompatibilityIssue(
                code="backend_id_mismatch",
                path="execution.backend_id",
                message=(
                    f"experiment requires backend {required_backend!r}; "
                    f"selected backend is {capabilities.backend_id!r}"
                ),
            ))
        else:
            backend_constraint = execution.get("backend_version")
            if isinstance(backend_constraint, str) and Version(
                capabilities.backend_version
            ) not in SpecifierSet(backend_constraint):
                issues.append(CompatibilityIssue(
                    code="backend_version_mismatch",
                    path="execution.backend_version",
                    message=(
                        f"backend {capabilities.backend_version!r} does not satisfy "
                        f"{backend_constraint!r}"
                    ),
                ))
        engine_constraint = execution.get("engine_version")
        if isinstance(engine_constraint, str) and Version(engine_version) not in SpecifierSet(
            engine_constraint
        ):
            issues.append(CompatibilityIssue(
                code="engine_version_mismatch",
                path="execution.engine_version",
                message=f"engine {engine_version!r} does not satisfy {engine_constraint!r}",
            ))

    models = spec.value.get("neuron_models")
    if isinstance(models, dict):
        for model_id, raw_model in sorted(models.items()):
            if not isinstance(raw_model, dict):
                continue
            family = str(raw_model["family"])
            if family not in capabilities.neuron_model_families:
                issues.append(CompatibilityIssue(
                    code="unsupported_model_family",
                    path=f"neuron_models.{model_id}.family",
                    message=f"backend does not support model family {family!r}",
                ))
    else:
        for family in spec.model_families:
            if family not in capabilities.neuron_model_families:
                issues.append(CompatibilityIssue(
                    code="unsupported_model_family",
                    path=f"neurons.{family}",
                    message=f"backend does not support model family {family!r}",
                ))
    return tuple(sorted(issues, key=lambda issue: (issue.path, issue.code)))
