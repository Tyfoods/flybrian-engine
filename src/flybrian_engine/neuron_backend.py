"""NEURON execution of the retained Figure 8 FES through NetPyNE."""

from __future__ import annotations

import hashlib
import importlib.metadata
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from .artifacts import ArtifactManifest
from .backends import BackendCapabilities, CompatibilityIssue
from .model_catalog import MANC_MODEL, public_model_ids
from .schema import ExperimentSpec


def runtime_version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def load_mechanism() -> None:
    import neuron

    names = (
        "FlyBrianChurginLIF",
        "FlyBrianBasicLIF",
        "FlyBrianFirstOrderRate",
        "FlyBrianPassiveTwo",
    )
    if all(hasattr(neuron.h, name) for name in names):
        return
    sources = sorted((Path(__file__).parent / "mechanisms").glob("*.mod"))
    digest = hashlib.sha256(
        b"".join(source.name.encode() + source.read_bytes() for source in sources)
    ).hexdigest()[:16]
    cache = Path(
        os.environ.get("FLYBRIAN_MECHANISM_CACHE", str(Path.home() / ".cache/flybrian/mechanisms"))
    )
    build = cache / f"{platform.system()}-{platform.machine()}-{runtime_version('neuron')}-{digest}"
    library = list(build.glob("*/libnrnmech.*")) if build.exists() else []
    if not library:
        compiler = Path(sys.executable).parent / "nrnivmodl"
        if not compiler.is_file():
            raise RuntimeError(f"NEURON mechanism compiler is missing: {compiler}")
        build.mkdir(parents=True, exist_ok=True)
        for source in sources:
            shutil.copyfile(source, build / source.name)
        result = subprocess.run([str(compiler), "."], cwd=build, text=True, capture_output=True)
        if result.returncode:
            raise RuntimeError(
                f"FlyBrianChurginLIF compilation failed:\n{result.stdout}\n{result.stderr}"
            )
    if not neuron.load_mechanisms(str(build)) or not all(hasattr(neuron.h, name) for name in names):
        raise RuntimeError(f"Could not load compiled FlyBrianChurginLIF from {build}")


class NeuronBackend:
    @property
    def capabilities(self) -> BackendCapabilities:
        nrn, netpyne = runtime_version("neuron"), runtime_version("netpyne")
        availability, reason = "available", None
        if nrn is None or netpyne is None:
            availability, reason = (
                "not_installed",
                "Install flybrian-engine[neuron] to run NEURON (NetPyNE).",
            )
        elif nrn != "9.0.2" or netpyne != "1.1.1":
            availability, reason = (
                "incompatible_runtime",
                f"Expected NEURON 9.0.2 / NetPyNE 1.1.1; installed {nrn} / {netpyne}.",
            )
        return BackendCapabilities(
            backend_id="neuron",
            backend_version=nrn or "0",
            experiment_spec_versions=("1.0",),
            neuron_model_families=("compartmental", "lif", "rate", "lif_churgin_projection_neuron"),
            neuron_model_ids=(
                *public_model_ids(),
                "lif.churgin_projection.figure8.v1",
                MANC_MODEL.model_id,
            ),
            embodiment_modes=("none", "direct_actuator"),
            artifact_kinds=("standardized_results",),
            deterministic_for_fixed_seed=True,
            scientific_execution=True,
            availability=availability,
            unavailable_reason=reason,
        )

    def compatibility_issues(self, spec: ExperimentSpec) -> tuple[CompatibilityIssue, ...]:
        from .manc import compatibility_issues as manc_issues
        from .manc import is_manc

        if is_manc(spec):
            return manc_issues(spec)
        if spec.embodiment_mode != "none":
            return (
                CompatibilityIssue(
                    "unsupported_body_execution",
                    "embodied_config",
                    "Body execution is currently translated for the ordinary MANC walking profile.",
                ),
            )
        if "neuron_models" in spec.value:
            from .public_models import compatibility_issues

            return compatibility_issues(spec)
        from .figure8 import compatibility_issues

        return compatibility_issues(spec)

    def run(self, spec: ExperimentSpec, output_dir: Path, run_id: str) -> ArtifactManifest:
        if "neuron_models" in spec.value:
            from .neuron_public_models import run_public_models

            load_mechanism()
            return run_public_models(spec, output_dir, run_id, self.capabilities)
        import numpy as np
        from netpyne import sim, specs

        from .body_execution import attach_body_artifacts, execution_duration_ms, run_body
        from .figure8 import (
            GROUP,
            current_schedule,
            is_figure8,
            prepare_execution,
            recording_ids,
            write_result,
        )

        load_mechanism()
        execution = prepare_execution(spec)
        network = execution.network
        p = execution.parameters
        run_dir = output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=False)
        params, cfg = specs.NetParams(), specs.SimConfig()
        params.popParams["biological"] = {"cellType": "churgin", "numCells": len(network.ids)}
        params.cellParams["churgin"] = {
            "conds": {"cellType": "churgin"},
            "secs": {
                "soma": {
                    "geom": {"L": 1, "diam": 1, "nseg": 1},
                    "threshold": 0.5,
                    "pointps": {
                        "cell": {
                            "mod": "FlyBrianChurginLIF",
                            "vref": "spike_out",
                            "synList": ["ace", "gab", "glu", "current"],
                            **{
                                key: value
                                for key, value in p.items()
                                if key not in {"resistance", "j_ace", "j_gab", "j_glu"}
                            },
                            "tau_m": p["resistance"] * p["capacitance"] / 1000,
                        }
                    },
                }
            },
        }
        params.defaultThreshold = 0.5
        for code, name in enumerate(("ace", "gab", "glu")):
            mask = network.transmitters == code
            if not mask.any():
                continue
            params.connParams[name] = {
                "preConds": {"pop": "biological"},
                "postConds": {"pop": "biological"},
                "connList": np.column_stack(
                    (network.sources[mask], network.targets[mask])
                ).tolist(),
                "weight": (network.weights[mask] * p["j_" + name]).tolist(),
                "delay": 0,
                "sec": "soma",
                "loc": 0.5,
                "synMech": name,
            }
        for key, cell in spec.value["neurons"][GROUP].items():
            gid = int(np.searchsorted(network.ids, int(key)))
            if gid >= len(network.ids) or int(network.ids[gid]) != int(key):
                raise ValueError(f"Neuron {key} is absent from the retained network")
            for ci, current in enumerate(cell["external_currents"]):
                for pi, (start, stop, amp) in enumerate(
                    current_schedule(current, spec.value["sim_time_ms"])
                ):
                    for edge, time, weight in [("start", start, amp), ("stop", stop, -amp)]:
                        name = f"current_{key}_{ci}_{pi}_{edge}"
                        params.stimSourceParams[name] = {
                            "type": "NetStim",
                            "start": time,
                            "number": 1,
                            "interval": 1,
                            "noise": 0,
                        }
                        params.stimTargetParams[name] = {
                            "source": name,
                            "conds": {"pop": "biological", "cellList": [gid]},
                            "sec": "soma",
                            "loc": 0.5,
                            "synMech": "current",
                            "weight": weight,
                            "delay": 0,
                        }
        for drive_index, drive in enumerate(execution.drives):
            gids = np.searchsorted(network.ids, drive.targets).tolist()
            for event_index, time in enumerate(drive.times_ms):
                name = f"poisson_{drive_index}_{event_index}"
                params.stimSourceParams[name] = {
                    "type": "NetStim",
                    "start": time,
                    "number": 1,
                    "interval": 1,
                    "noise": 0,
                }
                params.stimTargetParams[name] = {
                    "source": name,
                    "conds": {"pop": "biological", "cellList": gids},
                    "sec": "soma",
                    "loc": 0.5,
                    "synMech": drive.transmitter,
                    "weight": drive.weight_ns,
                    "delay": 0,
                }
        ids = recording_ids(spec, network)
        cfg.duration = execution_duration_ms(spec)
        cfg.dt = 0.1
        cfg.recordStep = 0.1
        cfg.cvode_active = False
        cfg.seeds = {
            "conn": spec.value["random_seed"],
            "stim": spec.value["random_seed"],
            "loc": spec.value["random_seed"],
        }
        cfg.recordCells = np.searchsorted(network.ids, ids).tolist()
        # Keep the retained profile's published observation convention. Ordinary
        # MANC records the state consumed by Euler, matching the hosted baseline.
        cfg.recordTraces = {
            name: {
                "sec": "soma",
                "loc": 0.5,
                "pointp": "cell",
                "var": name if is_figure8(spec) else f"sampled_{name}",
            }
            for name in ["vm", "g_ace", "g_gab", "g_glu", "I_ext"]
        }
        cfg.verbose = False
        cfg.progressBar = False
        cfg.analysis = {}
        cfg.saveJson = False
        cfg.savePickle = False
        cfg.allowSelfConns = True
        cfg.gatherOnlySimData = True
        cfg.saveCellConns = False
        cfg.saveCellSecs = False
        sim.initialize(netParams=params, simConfig=cfg)
        sim.net.createPops()
        sim.net.createCells()
        for key, cell in spec.value["neurons"][GROUP].items():
            gid = int(np.searchsorted(network.ids, int(key)))
            sim.net.cells[gid].secs["soma"]["pointps"]["cell"]["hObj"].tau_m = (
                cell.get("parameter_overrides", {}).get("R_m", p["resistance"])
                * p["capacitance"]
                / 1000
            )
        sim.net.connectCells()
        # NetPyNE 1.1.1 connList unconditionally skips self-edges; its cell API supports them.
        for edge in np.flatnonzero(network.sources == network.targets):
            gid = int(network.sources[edge])
            name = ("ace", "gab", "glu")[network.transmitters[edge]]
            sim.net.cells[gid].addConn(
                {
                    "preGid": gid,
                    "sec": "soma",
                    "loc": 0.5,
                    "synMech": name,
                    "weight": float(network.weights[edge] * p["j_" + name]),
                    "delay": 0,
                }
            )
        actual_connections = sum(len(cell.conns) for cell in sim.net.cells)
        if actual_connections != len(network.sources):
            raise RuntimeError(
                f"NetPyNE created {actual_connections} connections; expected {len(network.sources)}"
            )
        sim.net.addStims()
        sim.setupRecording()
        body = None
        boundary_spikes = []
        if spec.embodiment_mode == "none":
            sim.runSim()
        else:
            from netpyne.sim.run import postRun, prepareSimWithIntervalFunc

            prepareSimWithIntervalFunc()
            points = {
                int(nid): sim.net.cells[index].secs["soma"]["pointps"]["cell"]["hObj"]
                for index, nid in enumerate(network.ids)
            }

            def current_tick_spikes():
                seconds = round(float(sim.h.t) / cfg.dt) * cfg.dt / 1000
                return [
                    dict(neuron_id=nid, time_seconds=seconds)
                    for nid, point in points.items()
                    if point.spike_out > 0.5
                ]

            def window_spikes(start, stop):
                output = {}
                for gid, time in zip(sim.simData["spkid"], sim.simData["spkt"], strict=True):
                    # Event membership uses the shared 0.1 ms integration grid.
                    seconds = round(float(time) / 0.1) * 0.0001
                    if start <= seconds < stop:
                        output.setdefault(str(network.ids[int(gid)]), []).append(seconds)
                # Threshold vectors receive this tick's spike on the next advance.
                # The mechanism has already produced it at this body boundary.
                for spike in current_tick_spikes():
                    seconds = spike["time_seconds"]
                    if start <= seconds < stop:
                        output.setdefault(str(spike["neuron_id"]), []).append(seconds)
                return output

            def set_currents(currents):
                for point in points.values():
                    point.I_ext = 0
                for nid, current in currents.items():
                    point = points.get(nid)
                    if point is not None:
                        point.I_ext = current

            def advance(stop_ms):
                # Brian2's window ends before the tick at stop_ms. NEURON's
                # psolve includes that tick, so stop at this window's last tick
                # before applying the next window's sensory feedback.
                sim.pc.psolve(stop_ms - cfg.dt)

            body = run_body(spec, advance, window_spikes, set_currents)
            boundary_spikes = current_tick_spikes()
            postRun(cfg.duration)
        data = sim.simData
        spikes = []
        for gid, time in zip(data["spkid"], data["spkt"], strict=True):
            gid = int(gid)
            if not 0 <= gid < len(network.ids):
                raise RuntimeError(f"Unknown biological spike GID {gid}")
            if float(time) < cfg.duration:
                spikes.append(
                    dict(neuron_id=int(network.ids[gid]), time_seconds=float(time) / 1000)
                )
        spikes.extend(boundary_spikes)
        series = []
        for name, variable, unit, scale in [
            ("vm", "membrane_potential", "V", 0.001),
            ("g_ace", "g_ace", "S", 1e-9),
            ("g_gab", "g_gab", "S", 1e-9),
            ("g_glu", "g_glu", "S", 1e-9),
            ("I_ext", "external_current", "A", 1e-9),
        ]:
            for nid in ids:
                gid = int(np.searchsorted(network.ids, nid))
                values = np.asarray(data[name][f"cell_{gid}"])
                if body is not None:
                    values = np.append(values, getattr(points[nid], f"sampled_{name}"))
                times = np.arange(len(values)) * 0.0001
                mask = times < cfg.duration / 1000
                series.append(
                    dict(
                        neuron_id=nid,
                        compartment_id=None,
                        variable=variable,
                        unit=unit,
                        times_seconds=times[mask].tolist(),
                        values=(values[mask] * scale).tolist(),
                    )
                )
        manifest = write_result(
            spec, execution, run_dir, "neuron", runtime_version("neuron"), spikes, series
        )
        return manifest if body is None else attach_body_artifacts(spec, manifest, run_dir, body)
