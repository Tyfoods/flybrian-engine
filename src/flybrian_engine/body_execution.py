"""One retained closed-loop neural/body execution and its recorded-motion artifacts."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import math
import os
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from numpy.typing import NDArray

if TYPE_CHECKING:
    import mujoco

from .artifacts import Artifact, ArtifactDisposition, ArtifactManifest, DatasetReference
from .backends import CompatibilityIssue
from .body_assets import verify_body_assets
from .body_mapping import (
    NERVE_TO_BODY_PART,
    MappingConfig,
    SensoryMappingConfig,
    _resolve_joint_indices,
    body_state_to_sensory_currents,
    cmd_90_to_ctrl_78,
    spikes_to_motor_commands,
)
from .schema import ExperimentSpec

POLICY = "flybody.closed_loop.legacy.v1"
DATA = Path(__file__).parent / "data"
CAMERAS = {
    "dorsal": (90, -90, 5),
    "lateral": (0, -30, 8),
    "anterior": (90, -15, 6),
}


def execution_duration_ms(spec: ExperimentSpec) -> float:
    requested = float(spec.value["sim_time_ms"])
    if spec.embodiment_mode == "none":
        return requested
    window = float(spec.value["embodied_config"]["firing_rate_window_ms"])
    return max(1, math.ceil(requested / window)) * window


def compatibility_issues(spec: ExperimentSpec) -> tuple[CompatibilityIssue, ...]:
    if spec.embodiment_mode == "none":
        return ()
    config = spec.value["embodied_config"]
    issues = []

    def require(condition: bool, path: str, message: str) -> None:
        if not condition:
            issues.append(CompatibilityIssue("unsupported_body_execution", path, message))

    require(
        spec.embodiment_mode == "direct_actuator" and config.get("closed_loop") is True,
        "embodied_config",
        "This body executor supports closed-loop direct actuator walking.",
    )
    require(
        config.get("mapping_id") == "biological_prior"
        and not spec.value.get("motor_mapping_overrides")
        and not config.get("direct_actuator"),
        "embodied_config.mapping_id",
        "This body executor uses the captured biological_prior mapping.",
    )
    require(
        config.get("firing_rate_window_ms") == 32,
        "embodied_config.firing_rate_window_ms",
        "The retained walking transfer policy uses 32 ms windows.",
    )
    require(
        config.get("motor_scaling_mode") == "uniform",
        "embodied_config.motor_scaling_mode",
        "The retained walking preset uses its existing uniform motor policy.",
    )
    require(
        not any(
            cell.get("external_currents")
            for group in spec.value["neurons"].values()
            for cell in group.values()
        ),
        "neurons",
        "This retained closed-loop policy uses Poisson drive and sensory feedback; "
        "direct-current coupling is not yet translated.",
    )
    require(
        config.get("camera_preset") in CAMERAS,
        "embodied_config.camera_preset",
        "Choose a supported body camera.",
    )
    resolution = config.get("video_resolution")
    require(
        isinstance(resolution, list)
        and len(resolution) == 2
        and all(
            isinstance(v, int) and not isinstance(v, bool) and 0 < v <= 2048 for v in resolution
        ),
        "embodied_config.video_resolution",
        "Body video resolution must contain two positive dimensions up to 2048 pixels.",
    )
    for key in ("video_fps", "playback_speed"):
        value = config.get(key)
        require(
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value)
            and value > 0,
            f"embodied_config.{key}",
            f"{key} must be positive and finite.",
        )
    for package, expected in (
        ("mujoco", "3.13.0"),
        ("imageio", "2.37.4"),
        ("imageio-ffmpeg", "0.6.0"),
    ):
        try:
            installed = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            installed = None
        require(
            installed == expected,
            "embodied_config",
            f"Enable body simulations: this policy requires {package} {expected}.",
        )
    root = os.environ.get("FLYBRIAN_BODY_MODEL_ROOT")
    require(
        root is not None and (Path(root) / "scene.xml").is_file(),
        "embodied_config",
        "Enable body simulations and provide the Flybody model assets (FLYBRIAN_BODY_MODEL_ROOT).",
    )
    return tuple(issues)


def load_body_model() -> mujoco.MjModel:
    import mujoco

    root_value = os.environ.get("FLYBRIAN_BODY_MODEL_ROOT")
    if root_value is None:
        raise FileNotFoundError("FLYBRIAN_BODY_MODEL_ROOT is required for body simulations.")
    root = Path(root_value)
    verify_body_assets(root)
    model = mujoco.MjModel.from_xml_path(str(root / "scene.xml"))
    if model.nu != 78 or model.nq != 109 or not math.isclose(model.opt.timestep, 0.0001):
        raise ValueError("Body model dimensions or timestep differ from the retained controller.")
    return model


@dataclass
class BodyResult:
    motor_commands: NDArray[np.float64]
    qpos: NDArray[np.float64]
    qvel: NDArray[np.float64]
    sensory_currents: list[dict[int, float]]
    model: mujoco.MjModel


def run_body(
    spec: ExperimentSpec,
    advance: Callable[[float], None],
    window_spikes: Callable[[float, float], dict[str, list[float]]],
    set_currents: Callable[[dict[int, float]], None],
) -> BodyResult:
    """Advance each neural window once, then apply its commands and next-window feedback."""
    import mujoco

    model = load_body_model()
    data = mujoco.MjData(model)
    mapping = MappingConfig.from_dict(json.loads((DATA / "walking-motor-mapping.json").read_text()))
    sensory = SensoryMappingConfig.from_dict(
        json.loads((DATA / "walking-sensory-mapping.json").read_text())
    )
    joints = {part: _resolve_joint_indices(model, part) for part in NERVE_TO_BODY_PART.values()}
    window = float(spec.value["embodied_config"]["firing_rate_window_ms"])
    windows = round(execution_duration_ms(spec) / window)
    commands, feedback = [], []
    poses, velocities = [data.qpos.copy()], [data.qvel.copy()]
    for index in range(windows):
        start, stop = index * window, (index + 1) * window
        advance(stop)
        spikes = window_spikes(start / 1000, stop / 1000)
        rebased = {key: [time - start / 1000 for time in times] for key, times in spikes.items()}
        command = spikes_to_motor_commands(rebased, mapping, window, window)[0]
        controls = cmd_90_to_ctrl_78(command)
        data.ctrl[:] = controls
        for _ in range(round(window / 2)):
            for _ in range(round(0.002 / model.opt.timestep)):
                mujoco.mj_step(model, data)
        if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
            raise RuntimeError(f"Non-finite body state after window {index + 1}")
        currents = body_state_to_sensory_currents(
            data.qpos,
            data.qvel,
            sensory,
            model=model,
            joint_index_cache=joints,
            sensordata=data.sensordata,
        )
        commands.append(controls)
        poses.append(data.qpos.copy())
        velocities.append(data.qvel.copy())
        feedback.append(currents)
        set_currents(currents)
    return BodyResult(
        np.asarray(commands), np.asarray(poses), np.asarray(velocities), feedback, model
    )


def render_recorded_body(spec: ExperimentSpec, body: BodyResult, destination: Path) -> None:
    """Render saved poses without a second physical simulation."""
    import imageio.v2 as imageio
    import mujoco

    config = spec.value["embodied_config"]
    width, height = config["video_resolution"]
    data = mujoco.MjData(body.model)
    camera = mujoco.MjvCamera()
    camera.azimuth, camera.elevation, camera.distance = CAMERAS[config["camera_preset"]]
    camera.type = mujoco.mjtCamera.mjCAMERA_TRACKING
    camera.trackbodyid = mujoco.mj_name2id(body.model, mujoco.mjtObj.mjOBJ_BODY, "thorax")
    fps, speed = config["video_fps"], config["playback_speed"]
    duration = execution_duration_ms(spec) / 1000
    window = config["firing_rate_window_ms"] / 1000
    with mujoco.Renderer(body.model, height=height, width=width) as renderer:
        writer = imageio.get_writer(destination, fps=fps, codec="libx264", macro_block_size=1)
        with writer:
            for frame in range(max(1, math.ceil(duration / speed * fps))):
                time = min(duration, frame * speed / fps)
                index = min(len(body.qpos) - 1, round(time / window))
                data.qpos[:] = body.qpos[index]
                data.qvel[:] = body.qvel[index]
                data.time = index * window
                mujoco.mj_forward(body.model, data)
                renderer.update_scene(data, camera=camera)
                writer.append_data(renderer.render())


def attach_body_artifacts(
    spec: ExperimentSpec, manifest: ArtifactManifest, root: Path, body: BodyResult
) -> ArtifactManifest:
    window = spec.value["embodied_config"]["firing_rate_window_ms"]
    duration = execution_duration_ms(spec)

    def save_json(name: str, value: object) -> None:
        (root / name).write_text(json.dumps(value, separators=(",", ":"), allow_nan=False))

    save_json(
        "motor_commands.json",
        {
            "commands": body.motor_commands.tolist(),
            "shape": list(body.motor_commands.shape),
            "window_ms": window,
            "sim_time_ms": duration,
        },
    )
    np.save(root / "qpos_trajectory.npy", body.qpos)
    np.save(root / "qvel_trajectory.npy", body.qvel)
    save_json("sensory-currents.json", body.sensory_currents)
    for source, target in (
        ("walking-motor-mapping.json", "executed-motor-mapping.json"),
        ("walking-sensory-mapping.json", "executed-sensory-mapping.json"),
        ("walking-body-model.json", "executed-body-model.json"),
    ):
        (root / target).write_bytes((DATA / source).read_bytes())
    receipt = {
        "policy": POLICY,
        "requested_duration_ms": spec.value["sim_time_ms"],
        "executed_duration_ms": duration,
        "window_ms": window,
        "initial_pose_recorded": True,
        "mujoco_version": importlib.metadata.version("mujoco"),
        "motor_mapping_sha256": hashlib.sha256(
            (DATA / "walking-motor-mapping.json").read_bytes()
        ).hexdigest(),
        "sensory_mapping_sha256": hashlib.sha256(
            (DATA / "walking-sensory-mapping.json").read_bytes()
        ).hexdigest(),
        "body_model_manifest_sha256": hashlib.sha256(
            (DATA / "walking-body-model.json").read_bytes()
        ).hexdigest(),
        "video_source": "recorded_qpos",
        "qpos_frame_interval_ms": window,
    }
    save_json("body-execution.json", receipt)
    render_recorded_body(spec, body, root / "embodied.mp4")
    descriptions = [
        ("motor_commands.json", "motor_commands", "application/json"),
        ("qpos_trajectory.npy", "qpos_trajectory", "application/x-npy"),
        ("qvel_trajectory.npy", "qvel_trajectory", "application/x-npy"),
        ("sensory-currents.json", "sensory_currents", "application/json"),
        ("executed-motor-mapping.json", "motor_mapping", "application/json"),
        ("executed-sensory-mapping.json", "sensory_mapping", "application/json"),
        ("executed-body-model.json", "body_model", "application/json"),
        ("body-execution.json", "body_execution", "application/json"),
        ("embodied.mp4", "video", "video/mp4"),
    ]
    artifacts = tuple(
        Artifact.from_file(key=kind, kind=kind, media_type=mime, path=root / name, root=root)
        for name, kind, mime in descriptions
    )
    completed = replace(
        manifest,
        artifacts=(*manifest.artifacts, *artifacts),
        datasets=(
            *manifest.datasets,
            DatasetReference(
                dataset_id="flybody.menagerie.legacy.v1",
                sha256=receipt["body_model_manifest_sha256"],
            ),
        ),
        dispositions=(
            *manifest.dispositions,
            *(
                ArtifactDisposition(kind=a.kind, status="available", artifact_keys=(a.key,))
                for a in artifacts
            ),
        ),
    )
    completed.write(root / "manifest.json")
    return completed
