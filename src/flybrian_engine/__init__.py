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
from .results import (
    ResultsValidationError,
    StandardizedResults,
    validate_standardized_results,
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
    "ResultsValidationError",
    "StandardizedResults",
    "ValidationError",
    "__version__",
    "assess_backend_compatibility",
    "validate_experiment_spec",
    "validate_standardized_results",
]
