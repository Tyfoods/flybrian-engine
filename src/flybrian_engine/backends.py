"""Stable simulator backend contract and explicit registry."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .artifacts import ArtifactManifest
from .schema import ExperimentSpec


@dataclass(frozen=True)
class BackendCapabilities:
    backend_id: str
    backend_version: str
    experiment_spec_versions: tuple[str, ...]
    neuron_model_families: tuple[str, ...]
    embodiment_modes: tuple[str, ...]


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
