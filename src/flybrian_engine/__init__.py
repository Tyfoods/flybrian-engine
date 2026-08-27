"""Public scientific execution boundary for FlyBrian."""

from .artifacts import Artifact, ArtifactManifest
from .backends import (
    Backend,
    BackendCapabilities,
    BackendRegistry,
    CompatibilityIssue,
    assess_backend_compatibility,
)
from .runner import CompatibilityError
from .schema import ExperimentSpec, ValidationError, validate_experiment_spec
from .version import __version__

__all__ = [
    "Artifact",
    "ArtifactManifest",
    "Backend",
    "BackendCapabilities",
    "BackendRegistry",
    "CompatibilityError",
    "CompatibilityIssue",
    "ExperimentSpec",
    "ValidationError",
    "__version__",
    "assess_backend_compatibility",
    "validate_experiment_spec",
]
