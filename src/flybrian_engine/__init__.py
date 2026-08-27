"""Public scientific execution boundary for FlyBrian."""

from .artifacts import (
    Artifact,
    ArtifactDisposition,
    ArtifactManifest,
    ArtifactStatus,
    DatasetReference,
)
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
    "ArtifactDisposition",
    "ArtifactManifest",
    "ArtifactStatus",
    "Backend",
    "BackendCapabilities",
    "BackendRegistry",
    "CompatibilityError",
    "CompatibilityIssue",
    "DatasetReference",
    "ExperimentSpec",
    "ValidationError",
    "__version__",
    "assess_backend_compatibility",
    "validate_experiment_spec",
]
