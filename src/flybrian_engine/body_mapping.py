"""Shared retained motor and sensory transfer policy for closed-loop FlyBrian execution.

The legacy policy is preserved for numerical translation, including its joint-address
convention. Backend translation does not reinterpret anatomical gains or feedback.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np


@dataclass
class ActuatorInfo:
    """One of the 90 flybody actuators (full MJCF)."""

    index: int
    name: str
    body_part: str
    joint_type: str
    ctrl_range: tuple[float, float] = (-1.0, 1.0)


@dataclass
class MotorNeuronInfo:
    """A motor neuron identified in the connectome."""

    neuron_id: int
    subclass: str
    exit_nerve: str
    target_muscle: str
    systematic_type: str


@dataclass
class NeuronActuatorLink:
    """One mapping from a motor neuron to an actuator."""

    neuron_id: int
    actuator_index: int
    weight: float = 1.0
    confidence: float = 0.5
    source: str = "manual"
    sign: float = 1.0  # +1.0 for extensors, -1.0 for flexors (muscle action direction)


@dataclass
class MappingConfig:
    """Complete mapping state for an experiment."""

    mapping_id: str = "default"
    links: list[NeuronActuatorLink] = field(default_factory=list)
    actuators: list[ActuatorInfo] = field(default_factory=list)
    motor_neurons: list[MotorNeuronInfo] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "mapping_id": self.mapping_id,
            "links": [asdict(link) for link in self.links],
        }

    @classmethod
    def from_dict(cls, d: dict) -> MappingConfig:
        return cls(
            mapping_id=d.get("mapping_id", "default"),
            links=[NeuronActuatorLink(**link) for link in d.get("links", [])],
        )


# Static actuator list from the flybody MJCF (90 actuators, indices 0-89).
# This avoids requiring mujoco at import time.
FLYBODY_ACTUATORS: list[ActuatorInfo] = [
    # Head (0-3)
    ActuatorInfo(0, "head_abduct", "head", "head", ctrl_range=(-0.200, 0.200)),
    ActuatorInfo(1, "head_twist", "head", "head", ctrl_range=(-3.000, 3.000)),
    ActuatorInfo(2, "head", "head", "head", ctrl_range=(-0.500, 0.300)),
    ActuatorInfo(3, "rostrum", "head", "mouth", ctrl_range=(-1.240, 0.183)),
    # Mouth (4-7)
    ActuatorInfo(4, "haustellum_abduct", "mouth", "mouth", ctrl_range=(-0.087, 0.087)),
    ActuatorInfo(5, "haustellum", "mouth", "mouth", ctrl_range=(-1.590, 0.700)),
    ActuatorInfo(6, "labrum_left", "mouth", "mouth", ctrl_range=(-0.005, 1.050)),
    ActuatorInfo(7, "labrum_right", "mouth", "mouth", ctrl_range=(-0.005, 1.050)),
    # Antennae (8-13)
    ActuatorInfo(8, "antenna_abduct_left", "antennae", "antenna", ctrl_range=(-0.400, 0.800)),
    ActuatorInfo(9, "antenna_twist_left", "antennae", "antenna", ctrl_range=(-0.100, 0.090)),
    ActuatorInfo(10, "antenna_extend_left", "antennae", "antenna", ctrl_range=(-0.200, 0.500)),
    ActuatorInfo(11, "antenna_abduct_right", "antennae", "antenna", ctrl_range=(-0.400, 0.800)),
    ActuatorInfo(12, "antenna_twist_right", "antennae", "antenna", ctrl_range=(-0.100, 0.090)),
    ActuatorInfo(13, "antenna_extend_right", "antennae", "antenna", ctrl_range=(-0.200, 0.500)),
    # Wings (14-19)
    ActuatorInfo(14, "wing_yaw_left", "wings", "wing", ctrl_range=(-1.000, 1.000)),
    ActuatorInfo(15, "wing_roll_left", "wings", "wing", ctrl_range=(-1.000, 1.000)),
    ActuatorInfo(16, "wing_pitch_left", "wings", "wing", ctrl_range=(-1.000, 1.000)),
    ActuatorInfo(17, "wing_yaw_right", "wings", "wing", ctrl_range=(-1.000, 1.000)),
    ActuatorInfo(18, "wing_roll_right", "wings", "wing", ctrl_range=(-1.000, 1.000)),
    ActuatorInfo(19, "wing_pitch_right", "wings", "wing", ctrl_range=(-1.000, 1.000)),
    # Abdomen (20-21)
    ActuatorInfo(20, "abdomen_abduct", "abdomen", "abdomen", ctrl_range=(-0.700, 0.700)),
    ActuatorInfo(21, "abdomen", "abdomen", "abdomen", ctrl_range=(-1.050, 0.700)),
    # T1 Left (22-31)
    ActuatorInfo(22, "coxa_abduct_T1_left", "T1_left", "coxa", ctrl_range=(-1.000, 0.700)),
    ActuatorInfo(23, "coxa_twist_T1_left", "T1_left", "coxa", ctrl_range=(-0.800, 0.800)),
    ActuatorInfo(24, "coxa_T1_left", "T1_left", "coxa", ctrl_range=(-0.200, 1.700)),
    ActuatorInfo(25, "femur_twist_T1_left", "T1_left", "femur", ctrl_range=(-1.000, 1.000)),
    ActuatorInfo(26, "femur_T1_left", "T1_left", "femur", ctrl_range=(-0.150, 2.000)),
    ActuatorInfo(27, "tibia_T1_left", "T1_left", "tibia", ctrl_range=(-1.350, 1.300)),
    ActuatorInfo(28, "tarsus_T1_left", "T1_left", "tarsus", ctrl_range=(-0.700, 1.200)),
    ActuatorInfo(29, "tarsus2_T1_left", "T1_left", "tarsus", ctrl_range=(-0.900, 0.900)),
    ActuatorInfo(30, "tarsus3_T1_left", "T1_left", "tarsus"),
    ActuatorInfo(31, "tarsus4_T1_left", "T1_left", "tarsus"),
    # T1 Right (32-41)
    ActuatorInfo(32, "coxa_abduct_T1_right", "T1_right", "coxa", ctrl_range=(-1.000, 0.700)),
    ActuatorInfo(33, "coxa_twist_T1_right", "T1_right", "coxa", ctrl_range=(-0.800, 0.800)),
    ActuatorInfo(34, "coxa_T1_right", "T1_right", "coxa", ctrl_range=(-0.200, 1.700)),
    ActuatorInfo(35, "femur_twist_T1_right", "T1_right", "femur", ctrl_range=(-1.000, 1.000)),
    ActuatorInfo(36, "femur_T1_right", "T1_right", "femur", ctrl_range=(-0.150, 2.000)),
    ActuatorInfo(37, "tibia_T1_right", "T1_right", "tibia", ctrl_range=(-1.350, 1.300)),
    ActuatorInfo(38, "tarsus_T1_right", "T1_right", "tarsus", ctrl_range=(-0.700, 1.200)),
    ActuatorInfo(39, "tarsus2_T1_right", "T1_right", "tarsus", ctrl_range=(-0.900, 0.900)),
    ActuatorInfo(40, "tarsus3_T1_right", "T1_right", "tarsus"),
    ActuatorInfo(41, "tarsus4_T1_right", "T1_right", "tarsus"),
    # T2 Left (42-51)
    ActuatorInfo(42, "coxa_abduct_T2_left", "T2_left", "coxa", ctrl_range=(-0.500, 0.300)),
    ActuatorInfo(43, "coxa_twist_T2_left", "T2_left", "coxa", ctrl_range=(-0.750, 0.800)),
    ActuatorInfo(44, "coxa_T2_left", "T2_left", "coxa", ctrl_range=(-0.200, 0.900)),
    ActuatorInfo(45, "femur_twist_T2_left", "T2_left", "femur", ctrl_range=(-1.000, 1.000)),
    ActuatorInfo(46, "femur_T2_left", "T2_left", "femur", ctrl_range=(-0.150, 2.000)),
    ActuatorInfo(47, "tibia_T2_left", "T2_left", "tibia", ctrl_range=(-1.350, 1.300)),
    ActuatorInfo(48, "tarsus_T2_left", "T2_left", "tarsus", ctrl_range=(-1.000, 1.800)),
    ActuatorInfo(49, "tarsus2_T2_left", "T2_left", "tarsus", ctrl_range=(-0.900, 0.900)),
    ActuatorInfo(50, "tarsus3_T2_left", "T2_left", "tarsus"),
    ActuatorInfo(51, "tarsus4_T2_left", "T2_left", "tarsus"),
    # T2 Right (52-61)
    ActuatorInfo(52, "coxa_abduct_T2_right", "T2_right", "coxa", ctrl_range=(-0.500, 0.300)),
    ActuatorInfo(53, "coxa_twist_T2_right", "T2_right", "coxa", ctrl_range=(-0.750, 0.800)),
    ActuatorInfo(54, "coxa_T2_right", "T2_right", "coxa", ctrl_range=(-0.200, 0.900)),
    ActuatorInfo(55, "femur_twist_T2_right", "T2_right", "femur", ctrl_range=(-1.000, 1.000)),
    ActuatorInfo(56, "femur_T2_right", "T2_right", "femur", ctrl_range=(-0.150, 2.000)),
    ActuatorInfo(57, "tibia_T2_right", "T2_right", "tibia", ctrl_range=(-1.350, 1.300)),
    ActuatorInfo(58, "tarsus_T2_right", "T2_right", "tarsus", ctrl_range=(-1.000, 1.800)),
    ActuatorInfo(59, "tarsus2_T2_right", "T2_right", "tarsus", ctrl_range=(-0.900, 0.900)),
    ActuatorInfo(60, "tarsus3_T2_right", "T2_right", "tarsus"),
    ActuatorInfo(61, "tarsus4_T2_right", "T2_right", "tarsus"),
    # T3 Left (62-71)
    ActuatorInfo(62, "coxa_abduct_T3_left", "T3_left", "coxa", ctrl_range=(-0.900, 0.250)),
    ActuatorInfo(63, "coxa_twist_T3_left", "T3_left", "coxa", ctrl_range=(-0.150, 0.800)),
    ActuatorInfo(64, "coxa_T3_left", "T3_left", "coxa", ctrl_range=(-0.300, 1.300)),
    ActuatorInfo(65, "femur_twist_T3_left", "T3_left", "femur", ctrl_range=(-1.000, 1.000)),
    ActuatorInfo(66, "femur_T3_left", "T3_left", "femur", ctrl_range=(-0.700, 1.500)),
    ActuatorInfo(67, "tibia_T3_left", "T3_left", "tibia", ctrl_range=(-1.350, 1.300)),
    ActuatorInfo(68, "tarsus_T3_left", "T3_left", "tarsus", ctrl_range=(-0.800, 1.200)),
    ActuatorInfo(69, "tarsus2_T3_left", "T3_left", "tarsus", ctrl_range=(-0.900, 0.900)),
    ActuatorInfo(70, "tarsus3_T3_left", "T3_left", "tarsus"),
    ActuatorInfo(71, "tarsus4_T3_left", "T3_left", "tarsus"),
    # T3 Right (72-81)
    ActuatorInfo(72, "coxa_abduct_T3_right", "T3_right", "coxa", ctrl_range=(-0.900, 0.250)),
    ActuatorInfo(73, "coxa_twist_T3_right", "T3_right", "coxa", ctrl_range=(-0.150, 0.800)),
    ActuatorInfo(74, "coxa_T3_right", "T3_right", "coxa", ctrl_range=(-0.300, 1.300)),
    ActuatorInfo(75, "femur_twist_T3_right", "T3_right", "femur", ctrl_range=(-1.000, 1.000)),
    ActuatorInfo(76, "femur_T3_right", "T3_right", "femur", ctrl_range=(-0.700, 1.500)),
    ActuatorInfo(77, "tibia_T3_right", "T3_right", "tibia", ctrl_range=(-1.350, 1.300)),
    ActuatorInfo(78, "tarsus_T3_right", "T3_right", "tarsus", ctrl_range=(-0.800, 1.200)),
    ActuatorInfo(79, "tarsus2_T3_right", "T3_right", "tarsus", ctrl_range=(-0.900, 0.900)),
    ActuatorInfo(80, "tarsus3_T3_right", "T3_right", "tarsus"),
    ActuatorInfo(81, "tarsus4_T3_right", "T3_right", "tarsus"),
    # Adhesion (82-89)
    ActuatorInfo(82, "adhere_labrum_left", "adhesion", "adhesion", ctrl_range=(0.000, 1.000)),
    ActuatorInfo(83, "adhere_labrum_right", "adhesion", "adhesion", ctrl_range=(0.000, 1.000)),
    ActuatorInfo(84, "adhere_claw_T1_left", "adhesion", "adhesion", ctrl_range=(0.000, 1.000)),
    ActuatorInfo(85, "adhere_claw_T1_right", "adhesion", "adhesion", ctrl_range=(0.000, 1.000)),
    ActuatorInfo(86, "adhere_claw_T2_left", "adhesion", "adhesion", ctrl_range=(0.000, 1.000)),
    ActuatorInfo(87, "adhere_claw_T2_right", "adhesion", "adhesion", ctrl_range=(0.000, 1.000)),
    ActuatorInfo(88, "adhere_claw_T3_left", "adhesion", "adhesion", ctrl_range=(0.000, 1.000)),
    ActuatorInfo(89, "adhere_claw_T3_right", "adhesion", "adhesion", ctrl_range=(0.000, 1.000)),
]

# ─── 90-dim → 78-dim Actuator Index Mapping ──────────────────────────
# The FLYBODY_ACTUATORS list above is 90 entries (10 per leg including
# tarsus3 + tarsus4). The menagerie flybody scene.xml has only 78
# actuators (8 per leg — tarsus3/tarsus4 removed). The two index spaces
# are identical through index 29, then completely diverge.
# MAP_90_TO_78[i] = j means 90-dim index i → 78-dim ctrl index j.
# MAP_90_TO_78[i] = None means the actuator doesn't exist in 78-dim.
MAP_90_TO_78: dict[int, int | None] = {}
for _i in range(22):  # head, mouth, antennae, wings, abdomen: 1:1
    MAP_90_TO_78[_i] = _i
_off78 = 22
for _leg90 in [22, 32, 42, 52, 62, 72]:  # 6 legs, each 10-block in 90-dim
    for _j in range(8):  # first 8 are real actuators
        MAP_90_TO_78[_leg90 + _j] = _off78 + _j
    MAP_90_TO_78[_leg90 + 8] = None  # tarsus3 (absent in 78-dim)
    MAP_90_TO_78[_leg90 + 9] = None  # tarsus4 (absent in 78-dim)
    _off78 += 8
for _i in range(8):  # adhesion: 82-89 → 70-77
    MAP_90_TO_78[82 + _i] = 70 + _i


def remap_to_ctrlrange(cmd: np.ndarray) -> np.ndarray:
    """Remap 90-dim commands from [-1, 1] to actual MuJoCo ctrlranges.

    Maps: -1 → lo, 0 → midpoint, +1 → hi for each actuator.
    Input should already be clipped to [-1, 1].
    """
    out = cmd.copy()
    for act in FLYBODY_ACTUATORS:
        lo, hi = act.ctrl_range
        mid = (hi + lo) / 2.0
        half_range = (hi - lo) / 2.0
        out[act.index] = mid + np.clip(out[act.index], -1.0, 1.0) * half_range
    return out


def cmd_90_to_ctrl_78(cmd: np.ndarray) -> np.ndarray:
    """Convert a 90-dim motor command array to 78-dim MuJoCo ctrl array.

    Uses MAP_90_TO_78 index mapping. Tarsus3/tarsus4 values are dropped.
    """
    ctrl = np.zeros(78)
    for idx_90, idx_78 in MAP_90_TO_78.items():
        if idx_78 is not None:
            ctrl[idx_78] = cmd[idx_90]
    return ctrl


def spikes_to_firing_rates(
    spike_times: dict[str, list[float]],
    mapping: MappingConfig,
    window_ms: float = 32.0,
    sim_time_ms: float = 500.0,
) -> np.ndarray:
    """Convert spike trains to raw (unnormalized) actuator firing rates.

    Returns (num_windows, 90) array of weighted firing rate sums per actuator.
    """
    num_windows = max(1, math.ceil(sim_time_ms / window_ms))
    raw = np.zeros((num_windows, 90))

    neuron_to_actuators: dict[int, list[tuple]] = defaultdict(list)
    for link in mapping.links:
        neuron_to_actuators[link.neuron_id].append(
            (link.actuator_index, link.weight, getattr(link, "sign", 1.0))
        )

    if not neuron_to_actuators:
        return raw

    for window_idx in range(num_windows):
        t_start_s = (window_idx * window_ms) / 1000.0
        t_end_s = ((window_idx + 1) * window_ms) / 1000.0

        for neuron_id_str, times in spike_times.items():
            neuron_id = int(neuron_id_str)
            if neuron_id not in neuron_to_actuators:
                continue

            spikes_in_window = sum(1 for t in times if t_start_s <= t < t_end_s)
            if spikes_in_window == 0:
                continue

            firing_rate = spikes_in_window / (window_ms / 1000.0)  # Hz

            for actuator_idx, weight, sign in neuron_to_actuators[neuron_id]:
                raw[window_idx, actuator_idx] += firing_rate * weight * sign

    return raw


def normalize_motor_commands(
    raw: np.ndarray,
    mode: str = "peak_normalize",
    reference: np.ndarray | None = None,
) -> np.ndarray:
    """Normalize raw firing-rate motor commands to ctrl_range [-1, 1].

    Args:
        raw: (num_windows, 90) raw weighted firing rate sums.
        mode: Normalization strategy:
            - "peak_normalize": Scale each actuator by its global peak.
            - "z_score": Mean-center, variance-normalize, then scale to [-1,1].
            - "matched": Scale to match reference statistics (needs reference).
            - "clip_only": No normalization, just clip to ctrl_range.
            - "raw": No normalization, no remap. Returns unmodified firing-rate sums.
        reference: (T, 90) reference motor commands for "matched" mode.

    Returns:
        (num_windows, 90) normalized commands clipped to ctrl_range,
        or raw firing-rate sums if mode="raw".
    """
    commands = raw.copy()

    if mode == "raw":
        return commands

    if mode == "peak_normalize":
        for col in range(commands.shape[1]):
            peak = np.max(np.abs(commands[:, col]))
            if peak > 0:
                commands[:, col] /= peak

    elif mode == "z_score":
        for col in range(commands.shape[1]):
            col_data = commands[:, col]
            mean = np.mean(col_data)
            std = np.std(col_data)
            if std > 0:
                commands[:, col] = (col_data - mean) / std
            else:
                commands[:, col] = 0.0
        # Scale z-scores to [-1, 1] range
        global_max = np.max(np.abs(commands))
        if global_max > 0:
            commands /= global_max

    elif mode == "matched" and reference is not None:
        for col in range(commands.shape[1]):
            ref_std = np.std(reference[:, col])
            ref_mean = np.mean(reference[:, col])
            raw_std = np.std(commands[:, col])
            raw_mean = np.mean(commands[:, col])

            if raw_std > 0:
                commands[:, col] = (commands[:, col] - raw_mean) / raw_std * ref_std + ref_mean
            else:
                commands[:, col] = ref_mean

    # Remap normalized [-1, 1] commands to actual MuJoCo ctrlrange per actuator.
    # Command = -1.0 → actuator at lo (full flexion)
    # Command =  0.0 → actuator at midpoint (neutral)
    # Command = +1.0 → actuator at hi (full extension)
    for act in FLYBODY_ACTUATORS:
        lo, hi = act.ctrl_range
        mid = (hi + lo) / 2.0
        half_range = (hi - lo) / 2.0
        commands[:, act.index] = mid + np.clip(commands[:, act.index], -1.0, 1.0) * half_range

    return commands


def spikes_to_motor_commands(
    spike_times: dict[str, list[float]],
    mapping: MappingConfig,
    window_ms: float = 32.0,
    sim_time_ms: float = 500.0,
    normalize_mode: str = "peak_normalize",
    reference: np.ndarray | None = None,
) -> np.ndarray:
    """Convert spike trains to normalized motor commands.

    Args:
        spike_times: Dict mapping str(neuron_id) -> spike times in seconds.
        mapping: MappingConfig with NeuronActuatorLinks.
        window_ms: Time bin size for firing rate calculation.
        sim_time_ms: Total simulation time in ms.
        normalize_mode: "peak_normalize", "z_score", "matched", or "clip_only".
        reference: Reference commands for "matched" mode.

    Returns:
        (num_windows, 90) array of actuator commands in ctrl_range.
    """
    raw = spikes_to_firing_rates(spike_times, mapping, window_ms, sim_time_ms)
    return normalize_motor_commands(raw, mode=normalize_mode, reference=reference)


# MuJoCo joint name patterns for each leg segment.
# These map body_part labels to the joint names in the flybody MJCF.
# Joints are grouped by type for separate angle/velocity extraction.
LEG_JOINT_NAMES: dict[str, list[str]] = {
    "T1_left": [
        "coxa_abduct_T1_left",
        "coxa_twist_T1_left",
        "coxa_T1_left",
        "femur_twist_T1_left",
        "femur_T1_left",
        "tibia_T1_left",
        "tarsus_T1_left",
        "tarsus2_T1_left",
        "tarsus3_T1_left",
        "tarsus4_T1_left",
    ],
    "T1_right": [
        "coxa_abduct_T1_right",
        "coxa_twist_T1_right",
        "coxa_T1_right",
        "femur_twist_T1_right",
        "femur_T1_right",
        "tibia_T1_right",
        "tarsus_T1_right",
        "tarsus2_T1_right",
        "tarsus3_T1_right",
        "tarsus4_T1_right",
    ],
    "T2_left": [
        "coxa_abduct_T2_left",
        "coxa_twist_T2_left",
        "coxa_T2_left",
        "femur_twist_T2_left",
        "femur_T2_left",
        "tibia_T2_left",
        "tarsus_T2_left",
        "tarsus2_T2_left",
        "tarsus3_T2_left",
        "tarsus4_T2_left",
    ],
    "T2_right": [
        "coxa_abduct_T2_right",
        "coxa_twist_T2_right",
        "coxa_T2_right",
        "femur_twist_T2_right",
        "femur_T2_right",
        "tibia_T2_right",
        "tarsus_T2_right",
        "tarsus2_T2_right",
        "tarsus3_T2_right",
        "tarsus4_T2_right",
    ],
    "T3_left": [
        "coxa_abduct_T3_left",
        "coxa_twist_T3_left",
        "coxa_T3_left",
        "femur_twist_T3_left",
        "femur_T3_left",
        "tibia_T3_left",
        "tarsus_T3_left",
        "tarsus2_T3_left",
        "tarsus3_T3_left",
        "tarsus4_T3_left",
    ],
    "T3_right": [
        "coxa_abduct_T3_right",
        "coxa_twist_T3_right",
        "coxa_T3_right",
        "femur_twist_T3_right",
        "femur_T3_right",
        "tibia_T3_right",
        "tarsus_T3_right",
        "tarsus2_T3_right",
        "tarsus3_T3_right",
        "tarsus4_T3_right",
    ],
}

# Nerve name -> body_part mapping (mirrors mapping.py EXIT_NERVE_TO_BODY_PART)
NERVE_TO_BODY_PART: dict[str, str] = {
    "ProLN_L": "T1_left",
    "ProLN_R": "T1_right",
    "MesoLN_L": "T2_left",
    "MesoLN_R": "T2_right",
    "MetaLN_L": "T3_left",
    "MetaLN_R": "T3_right",
}


# DOF groups for per-joint sensory signals.
# Maps group name -> indices into the 10-element joint array per leg.
# Biologically grounded: separate proprioceptors per joint segment
# (hair plates for coxa, femoral chordotonal organ for femur/tibia).
DOF_GROUPS = {
    "coxa": [0, 1, 2],  # coxa_abduct, coxa_twist, coxa
    "femur": [3, 4],  # femur_twist, femur
    "tibia": [5],  # tibia
    # tarsus DOFs (indices 6-9) use old mean behavior
}
DOF_GROUP_NAMES = list(DOF_GROUPS.keys())  # ["coxa", "femur", "tibia"]


@dataclass
class SensoryGains:
    """Gain parameters for sensory signal -> current conversion."""

    angle_gain: float = 2.0  # nA per radian (SNpp tonic)
    velocity_gain: float = 0.5  # nA per rad/s (SNch phasic)
    angle_offset: float = 0.0  # resting angle offset (radians)
    velocity_threshold: float = 0.01  # min velocity to produce current (rad/s)
    force_gain: float = 1.0  # nA per Newton (SNta campaniform)
    force_threshold: float = 0.001  # min force to produce current (N)
    per_dof: bool = True  # per-DOF sensory signals (False = old averaging)


@dataclass
class SensoryMappingConfig:
    """Complete sensory mapping configuration.

    Maps body_part -> {snpp_ids, snch_ids, snta_ids} and stores gain parameters.
    """

    snpp_by_nerve: dict[str, list[int]] = field(default_factory=dict)
    snch_by_nerve: dict[str, list[int]] = field(default_factory=dict)
    snta_by_nerve: dict[str, list[int]] = field(default_factory=dict)
    gains: SensoryGains = field(default_factory=SensoryGains)

    def to_dict(self) -> dict:
        return {
            "snpp_by_nerve": self.snpp_by_nerve,
            "snch_by_nerve": self.snch_by_nerve,
            "snta_by_nerve": self.snta_by_nerve,
            "gains": asdict(self.gains),
        }

    @classmethod
    def from_dict(cls, d: dict) -> SensoryMappingConfig:
        return cls(
            snpp_by_nerve=d.get("snpp_by_nerve", {}),
            snch_by_nerve=d.get("snch_by_nerve", {}),
            snta_by_nerve=d.get("snta_by_nerve", {}),
            gains=SensoryGains(**d.get("gains", {})),
        )

    def save(self, path: Path) -> Path:
        path.write_text(json.dumps(self.to_dict(), indent=2))
        return path

    @classmethod
    def load(cls, path: Path) -> SensoryMappingConfig:
        d = json.loads(path.read_text())
        return cls.from_dict(d)

    @property
    def all_snpp_ids(self) -> list[int]:
        ids: set[int] = set()
        for v in self.snpp_by_nerve.values():
            ids.update(v)
        return sorted(ids)

    @property
    def all_snch_ids(self) -> list[int]:
        ids: set[int] = set()
        for v in self.snch_by_nerve.values():
            ids.update(v)
        return sorted(ids)

    @property
    def all_snta_ids(self) -> list[int]:
        ids: set[int] = set()
        for v in self.snta_by_nerve.values():
            ids.update(v)
        return sorted(ids)


def _resolve_joint_indices(
    model,
    body_part: str,
) -> list[int]:
    """Get qpos/qvel indices for a leg segment's joints.

    Args:
        model: MuJoCo MjModel instance
        body_part: e.g. "T1_left"

    Returns:
        List of qpos indices for the leg's joints.
    """
    import mujoco

    joint_names = LEG_JOINT_NAMES.get(body_part, [])
    indices = []
    for jname in joint_names:
        jid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, jname)
        if jid >= 0:
            indices.append(model.jnt_qposadr[jid])
    return indices


# MuJoCo sensordata indices for force/touch sensors per leg nerve.
# force_tarsus: 3-axis contact forces, touch_claw: 1D scalar contact.
FORCE_SENSOR_INDICES: dict[str, tuple[list[int], int]] = {
    "ProLN_L": ([9, 10, 11], 27),  # force_tarsus_T1_left,  touch_claw_T1_left
    "ProLN_R": ([12, 13, 14], 28),  # force_tarsus_T1_right, touch_claw_T1_right
    "MesoLN_L": ([15, 16, 17], 29),  # force_tarsus_T2_left,  touch_claw_T2_left
    "MesoLN_R": ([18, 19, 20], 30),  # force_tarsus_T2_right, touch_claw_T2_right
    "MetaLN_L": ([21, 22, 23], 31),  # force_tarsus_T3_left,  touch_claw_T3_left
    "MetaLN_R": ([24, 25, 26], 32),  # force_tarsus_T3_right, touch_claw_T3_right
}


def body_state_to_sensory_currents(
    qpos: np.ndarray,
    qvel: np.ndarray,
    sensory_mapping: SensoryMappingConfig,
    model=None,
    joint_index_cache: dict[str, list[int]] | None = None,
    sensordata: np.ndarray | None = None,
) -> dict[int, float]:
    """Convert MuJoCo body state to sensory neuron input currents.

    Args:
        qpos: Full joint angle array from MuJoCo data.qpos
        qvel: Full joint velocity array from MuJoCo data.qvel
        sensory_mapping: SensoryMappingConfig with neuron IDs and gains
        model: MuJoCo MjModel (needed to resolve joint names to indices)
        joint_index_cache: Pre-computed {body_part: [qpos_indices]}.
            If None and model is provided, will be computed.
        sensordata: MuJoCo data.sensordata for SNta contact force mapping.

    Returns:
        {neuron_id: input_current_nA} for each sensory neuron.
    """
    gains = sensory_mapping.gains
    currents: dict[int, float] = {}

    for nerve, body_part in NERVE_TO_BODY_PART.items():
        # Get joint indices for this leg
        if joint_index_cache and body_part in joint_index_cache:
            joint_idxs = joint_index_cache[body_part]
        elif model is not None:
            joint_idxs = _resolve_joint_indices(model, body_part)
        else:
            joint_idxs = []

        if joint_idxs:
            # Extract angles and velocities for this leg
            angles = np.array([qpos[i] for i in joint_idxs])
            velocities = np.array([qvel[i] for i in joint_idxs])

            snpp_ids = sensory_mapping.snpp_by_nerve.get(nerve, [])
            snch_ids = sensory_mapping.snch_by_nerve.get(nerve, [])

            if gains.per_dof and len(angles) >= 6:
                # --- Per-DOF sensory signals ---
                # Split neurons into thirds: coxa / femur / tibia
                n_groups = len(DOF_GROUP_NAMES)

                # Compute per-group angle signals
                group_angle_signals = []
                group_velocity_signals = []
                for gname in DOF_GROUP_NAMES:
                    gidxs = DOF_GROUPS[gname]
                    valid = [i for i in gidxs if i < len(angles)]
                    if valid:
                        g_angle = float(np.mean(np.abs(angles[valid] - gains.angle_offset)))
                        g_vel = float(np.mean(np.abs(velocities[valid])))
                    else:
                        g_angle = 0.0
                        g_vel = 0.0
                    group_angle_signals.append(g_angle)
                    group_velocity_signals.append(g_vel)

                # SNpp: split into n_groups subgroups by index
                snpp_chunk = max(1, len(snpp_ids) // n_groups)
                for gi in range(n_groups):
                    start = gi * snpp_chunk
                    if gi == n_groups - 1:
                        sub_ids = snpp_ids[start:]  # last group gets remainder
                    else:
                        sub_ids = snpp_ids[start : start + snpp_chunk]
                    snpp_current = group_angle_signals[gi] * gains.angle_gain
                    for nid in sub_ids:
                        currents[nid] = snpp_current

                # SNch: split into n_groups subgroups by index
                snch_chunk = max(1, len(snch_ids) // n_groups)
                for gi in range(n_groups):
                    start = gi * snch_chunk
                    if gi == n_groups - 1:
                        sub_ids = snch_ids[start:]
                    else:
                        sub_ids = snch_ids[start : start + snch_chunk]
                    g_vel = group_velocity_signals[gi]
                    if g_vel < gains.velocity_threshold:
                        snch_current = 0.0
                    else:
                        snch_current = g_vel * gains.velocity_gain
                    for nid in sub_ids:
                        currents[nid] = snch_current

            else:
                # --- Legacy: average all DOFs ---
                mean_angle = float(np.mean(np.abs(angles - gains.angle_offset)))
                snpp_current = mean_angle * gains.angle_gain
                for nid in snpp_ids:
                    currents[nid] = snpp_current

                mean_velocity = float(np.mean(np.abs(velocities)))
                if mean_velocity < gains.velocity_threshold:
                    snch_current = 0.0
                else:
                    snch_current = mean_velocity * gains.velocity_gain
                for nid in snch_ids:
                    currents[nid] = snch_current

        # SNta: campaniform -- current proportional to contact force
        snta_ids = sensory_mapping.snta_by_nerve.get(nerve, [])
        if snta_ids and sensordata is not None:
            sensor_info = FORCE_SENSOR_INDICES.get(nerve)
            if sensor_info is not None:
                force_idxs, touch_idx = sensor_info
                force_magnitude = float(np.linalg.norm(sensordata[force_idxs]))
                touch_value = float(sensordata[touch_idx])
                total_force = force_magnitude + abs(touch_value)
                if total_force < gains.force_threshold:
                    snta_current = 0.0
                else:
                    snta_current = total_force * gains.force_gain
                for nid in snta_ids:
                    currents[nid] = snta_current

    return currents
