"""Deterministic contract backend; not a biological simulation."""

from __future__ import annotations

import json
from pathlib import Path

from .artifacts import Artifact, ArtifactDisposition, ArtifactManifest, DatasetReference
from .backends import BackendCapabilities, CompatibilityIssue
from .schema import ExperimentSpec
from .version import __version__


class ReferenceBackend:
    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(
            backend_id="reference",
            backend_version="1.0.0",
            experiment_spec_versions=("1.0",),
            neuron_model_families=("lif",),
            neuron_model_ids=(),
            embodiment_modes=("none",),
            artifact_kinds=("summary",),
            deterministic_for_fixed_seed=True,
            scientific_execution=False,
        )

    def run(self, spec: ExperimentSpec, output_dir: Path, run_id: str) -> ArtifactManifest:
        run_dir = output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        neuron_count = sum(len(family) for family in spec.value["neurons"].values())
        summary_path = run_dir / "summary.json"
        summary_path.write_text(json.dumps({
            "backend": "reference",
            "experiment_sha256": spec.sha256(),
            "neuron_count": neuron_count,
            "random_seed": spec.value["random_seed"],
            "sim_time_ms": spec.value["sim_time_ms"],
            "warning": "Contract verification only; no biological dynamics were simulated.",
        }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        artifact = Artifact.from_file(
            key="summary",
            kind="summary",
            media_type="application/json",
            path=summary_path,
            root=run_dir,
        )
        manifest = ArtifactManifest(
            run_id=run_id,
            engine_version=__version__,
            backend_id=self.capabilities.backend_id,
            backend_version=self.capabilities.backend_version,
            experiment_spec_version=str(spec.value["spec_version"]),
            experiment_sha256=spec.sha256(),
            random_seed=int(spec.value["random_seed"]),
            datasets=(DatasetReference(dataset_id=str(spec.value["dataset"])),),
            scientific_execution=self.capabilities.scientific_execution,
            deterministic_for_fixed_seed=self.capabilities.deterministic_for_fixed_seed,
            artifacts=(artifact,),
            dispositions=(ArtifactDisposition(
                kind="summary",
                status="available",
                artifact_keys=("summary",),
            ),),
        )
        manifest.write(run_dir / "manifest.json")
        return manifest

    def compatibility_issues(self, spec: ExperimentSpec) -> tuple[CompatibilityIssue, ...]:
        return ()
