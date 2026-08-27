"""Public scientific execution boundary for FlyBrian."""

from .artifacts import Artifact, ArtifactManifest
from .backends import Backend, BackendCapabilities, BackendRegistry
from .schema import ExperimentSpec, ValidationError, validate_experiment_spec

__all__ = [
    "Artifact",
    "ArtifactManifest",
    "Backend",
    "BackendCapabilities",
    "BackendRegistry",
    "ExperimentSpec",
    "ValidationError",
    "validate_experiment_spec",
]

__version__ = "0.1.0"
