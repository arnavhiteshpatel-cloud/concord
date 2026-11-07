"""Milestone 3 benchmarks: live protocols -> runtime -> pipeline, measured on this machine.

Publishers run in a SEPARATE PROCESS (``python -m brainos.testing.publish``), speaking real
LSL (liblsl) or the Open Ephys ZMQ wire format, so the runtime process is measured on its
own. Nothing here touches hardware: these are software/protocol measurements.

Latency definitions (same host, same clock):
* LSL *acquisition -> feature/command*: ``pylsl.local_clock()`` when an in-process bus tap
  sees the event, minus the LSL timestamp of the newest sample the event depends on (the
  bin end). Includes LSL transport, adapter polling (5 ms), runtime validation and the
  pipeline. The publisher stamps samples when it pushes them.
* *ingest -> derived*: runtime ingest of the input envelope to ingest of the derived event
  (pipeline queueing + processing), reported by the pipeline itself.

Usage: python scripts/bench_live.py [--seconds 10] [--soak 120] [--write docs/BENCHMARKS_LIVE.md]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import platform
import resource
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

from brainos.adapters.simulated import OperatorIntentSource
from brainos.contracts.events import EventEnvelope
from brainos.runtime import DeviceRegistry, Recorder, Runtime
from brainos.runtime.pipeline import PipelineStartRequest, RouterSpec

REPO = Path(__file__).resolve().parents[1]
DATA = REPO / "data" / "datasets" / "dandi-000954"
TRAIN = DATA / "sub-HumanPitt-held-in-calib_ses-19250108T110520.nwb"
EVAL = DATA / "sub-HumanPitt-held-in-calib_ses-19250108T111022.nwb"
WARMUP_S = 2.0  # connection + 1 s RMS threshold estimation, excluded from rate/latency stats


def _publisher(*args: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [sys.executable, "-m", "brainos.testing.publish", *args],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _stop(p: subprocess.Popen[bytes]) -> None:
    p.terminate()
    try:
        p.wait(5)
    except subprocess.TimeoutExpired:
        p.kill()


def _pct(v: list[float], q: float) -> float:
    return float(np.percentile(v, q)) if v else float("nan")


def _rss_mb() -> float:
    with open("/proc/self/status") as fh:
        for line in fh:
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) / 1024
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024


def _free_port_pair() -> int:
    for _ in range(100):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            p: int = s.getsockname()[1]
        if p < 65534:
            with socket.socket() as s2:
                try:
                    s2.bind(("127.0.0.1", p + 1))
                    return p
                except OSError:
                    continue
    raise RuntimeError("no free port pair")


class Tap:
    """Bus tap measuring acquisition->event latency on the LSL clock for selected events."""

    def __init__(self, event_types: set[str], adapter_prefix: str = "brainos.pipeline") -> None:
        import pylsl

        self.clock = pylsl.local_clock
        self.types = event_types
        self.prefix = adapter_prefix
        self.lat_ms: list[float] = []
        self.count = 0
        self.armed = False

    def __call__(self, env: EventEnvelope, _json: str) -> None:
        if env.event_type.value not in self.types or not env.provenance.adapter.startswith(
            self.prefix
        ):
            return
        self.count += 1
        if self.armed and env.device_timestamp_ns is not None:
            self.lat_ms.append(self.clock() * 1e3 - env.device_timestamp_ns / 1e6)


async def _discover(reg: DeviceRegistry, want: Callable[[], bool], limit_s: float = 10) -> None:
    end = time.monotonic() + limit_s
    while time.monotonic() < end:
        await asyncio.to_thread(reg.live.discover_lsl, 1.0)
        if want():
            return
    raise RuntimeError("publisher stream not discovered")


async def lsl_raw(channels: int, seconds: float, tmp: Path) -> dict[str, Any]:
    sid = f"bench-ephys-{channels}-{os.getpid()}"
    pub = _publisher("lsl-ephys", "--channels", str(channels), "--source-id", sid, "--no-latent")
    try:
        reg = DeviceRegistry(OperatorIntentSource(), tmp / "rec", models_dir=tmp / "m")
        await _discover(reg, lambda: any(s.key == sid for s in reg.live.streams()))
        rt = Runtime(reg, Recorder(tmp / "rec"))
        tap = Tap({"features.binned"})
        rt.bus.add_tap(tap)
        await rt.connect(f"lsl:{sid}")
        rt.start_pipeline(PipelineStartRequest(processing={"preset": "spikeband_threshold"}))
        await asyncio.sleep(WARMUP_S)
        tap.armed = True
        st0 = rt.adapter.source_metadata()["stats"]  # type: ignore[union-attr]
        f0, cpu0, t0 = tap.count, time.process_time(), time.monotonic()
        await asyncio.sleep(seconds)
        dt = time.monotonic() - t0
        cpu = time.process_time() - cpu0
        st1 = rt.adapter.source_metadata()["stats"]  # type: ignore[union-attr]
        ps = rt.pipeline.status()
        out = {
            "channels": channels,
            "seconds": dt,
            "samples_per_s": (st1["samples"] - st0["samples"]) / dt,
            "gaps": st1["gaps"],
            "missing": st1["estimated_missing_samples"],
            "features_per_s": (tap.count - f0) / dt,
            "lat_p50": _pct(tap.lat_ms, 50),
            "lat_p99": _pct(tap.lat_ms, 99),
            "lat_max": max(tap.lat_ms) if tap.lat_ms else float("nan"),
            "proc_p50_us": ps.processing_us.p50,
            "proc_p99_us": ps.processing_us.p99,
            "dropped_inputs": ps.counters["dropped_inputs"],
            "errors": ps.counters["errors"],
            "cpu_pct": 100 * cpu / dt,
            "validation_errors": rt.diagnostics.validation_errors,
        }
        await rt.shutdown()
        return out
    finally:
        _stop(pub)


async def falcon_decode(seconds: float, tmp: Path) -> dict[str, Any] | None:
    if not (TRAIN.exists() and EVAL.exists()):
        return None
    from brainos.adapters.nwb.reader import load
    from brainos.datasets import session_of
    from brainos.decoding.ridge import fit

    rec = load(TRAIN)
    assert rec.behavior is not None
    counts = np.vstack([c for _, c in rec.iter_counts()]).astype(np.float64)
    b = rec.behavior
    model = fit(
        counts,
        b.values,
        b.valid,
        dims=b.dims,
        unit=b.unit,
        bin_ms=20.0,
        space="falcon_h1_7dof",
        training={"file": TRAIN.name, "session": session_of(TRAIN.name)},
        source={"identity": "dandi:000954:HumanPitt"},
    )
    model.save(tmp / "m" / f"{model.model_id}.json")
    prefix = f"bench-falcon-{os.getpid()}"
    pub = _publisher("falcon", str(EVAL), "--speed", "1", "--source-prefix", prefix)
    try:
        reg = DeviceRegistry(OperatorIntentSource(), tmp / "rec", models_dir=tmp / "m")
        keys = {f"{prefix}-{r}" for r in ("counts", "behavior", "markers")}
        await _discover(reg, lambda: keys <= {s.key for s in reg.live.streams()})
        reg.live.configure_lsl(f"{prefix}-counts", f"{prefix}-behavior", f"{prefix}-markers")
        rt = Runtime(reg, Recorder(tmp / "rec"))
        tap = Tap({"intent.pointer"})
        rt.bus.add_tap(tap)
        await rt.connect(f"lsl:{prefix}-counts")
        rt.start_pipeline(
            PipelineStartRequest(
                processing={"preset": "features_passthrough"},
                model_id=model.model_id,
                router=RouterSpec(enabled=True, x_dim="tx", y_dim="ty"),
            )
        )
        await asyncio.sleep(1.0)
        tap.armed = True
        c0, cpu0, t0 = tap.count, time.process_time(), time.monotonic()
        await asyncio.sleep(seconds)
        dt = time.monotonic() - t0
        cpu = time.process_time() - cpu0
        ps = rt.pipeline.status()
        st = rt.adapter.source_metadata()["stats"]  # type: ignore[union-attr]
        out = {
            "seconds": dt,
            "commands_per_s": (tap.count - c0) / dt,
            "lat_p50": _pct(tap.lat_ms, 50),
            "lat_p99": _pct(tap.lat_ms, 99),
            "lat_max": max(tap.lat_ms) if tap.lat_ms else float("nan"),
            "proc_p50_us": ps.processing_us.p50,
            "proc_p99_us": ps.processing_us.p99,
            "gaps": st["gaps"],
            "dropped_inputs": ps.counters["dropped_inputs"],
            "cpu_pct": 100 * cpu / dt,
        }
        await rt.shutdown()
        return out
    finally:
        _stop(pub)


async def openephys_raw(channels: int, seconds: float, tmp: Path) -> dict[str, Any]:
    from brainos.adapters.openephys import OpenEphysConfig

    port = _free_port_pair()
    pub = _publisher("openephys", "--port", str(port), "--channels", str(channels))
    try:
        await asyncio.sleep(1.0)
        reg = DeviceRegistry(OperatorIntentSource(), tmp / "rec", models_dir=tmp / "m")
        desc = reg.live.configure_openephys(
            OpenEphysConfig(host="127.0.0.1", data_port=port, unit="uV")
        )
        rt = Runtime(reg, Recorder(tmp / "rec"))
        tap = Tap({"features.binned"})
        rt.bus.add_tap(tap)
        await rt.connect(desc.device_id)
        rt.start_pipeline(PipelineStartRequest(processing={"preset": "spikeband_threshold"}))
        await asyncio.sleep(WARMUP_S)
        meta0 = rt.adapter.source_metadata()["counters"]  # type: ignore[union-attr]
        f0, cpu0, t0 = tap.count, time.process_time(), time.monotonic()
        await asyncio.sleep(seconds)
        dt = time.monotonic() - t0
        cpu = time.process_time() - cpu0
        c = rt.adapter.source_metadata()["counters"]  # type: ignore[union-attr]
        ps = rt.pipeline.status()
        out = {
            "channels": channels,
            "seconds": dt,
            "samples_per_s": (c["samples_emitted"] - meta0["samples_emitted"]) / dt,
            "missed_messages": c["missed_messages"],
            "incomplete_blocks": c["incomplete_blocks"],
            "malformed": c["malformed"],
            "features_per_s": (tap.count - f0) / dt,
            "ingest_p50_ms": ps.pipeline_latency_ms.p50,
            "ingest_p99_ms": ps.pipeline_latency_ms.p99,
            "proc_p50_us": ps.processing_us.p50,
            "proc_p99_us": ps.processing_us.p99,
            "dropped_inputs": ps.counters["dropped_inputs"],
            "cpu_pct": 100 * cpu / dt,
        }
        await rt.shutdown()
        return out
    finally:
        _stop(pub)


async def lsl_reconnect(tmp: Path, outage_s: float = 2.0) -> dict[str, Any]:
    """Publisher process killed under load and restarted with the same source_id."""
    from brainos.contracts.protocol import RuntimeState

    sid = f"bench-reconnect-{os.getpid()}"
    args = ("lsl-ephys", "--channels", "32", "--source-id", sid, "--no-latent")
    pub = _publisher(*args)
    try:
        reg = DeviceRegistry(OperatorIntentSource(), tmp / "rec", models_dir=tmp / "m")
        await _discover(reg, lambda: any(s.key == sid for s in reg.live.streams()))
        rt = Runtime(reg, Recorder(tmp / "rec"), reconnect_backoff_s=(0.5, 0.5, 1.0, 1.0, 2.0))
        await rt.connect(f"lsl:{sid}")
        rt.start_pipeline(PipelineStartRequest(processing={"preset": "spikeband_threshold"}))
        await asyncio.sleep(3.0)
        _stop(pub)
        t_kill = time.monotonic()
        while rt.state is not RuntimeState.RECONNECTING and time.monotonic() - t_kill < 15:  # noqa: ASYNC110
            await asyncio.sleep(0.01)
        detect = time.monotonic() - t_kill
        await asyncio.sleep(max(0.0, outage_s - detect))
        pub = _publisher(*args)
        t_restart = time.monotonic()
        n0 = rt.diagnostics.totals["recording.frame"]

        def back() -> bool:
            frames = rt.diagnostics.totals["recording.frame"]
            return frames > n0 and rt.state is RuntimeState.STREAMING

        while not back() and time.monotonic() - t_restart < 30:  # noqa: ASYNC110
            await asyncio.sleep(0.01)
        recover = time.monotonic() - t_restart
        out = {
            "detect_s": detect,
            "recover_s": recover,
            "state": rt.state.value,
            "reconnects": rt.diagnostics.reconnect_successes,
            "pipeline_running": rt.pipeline.running,
        }
        await rt.shutdown()
        return out
    finally:
        _stop(pub)


async def soak(seconds: float, tmp: Path) -> dict[str, Any]:
    sid = f"bench-soak-{os.getpid()}"
    pub = _publisher("lsl-ephys", "--channels", "32", "--source-id", sid)
    try:
        reg = DeviceRegistry(OperatorIntentSource(), tmp / "rec", models_dir=tmp / "m")
        await _discover(reg, lambda: any(s.key == sid for s in reg.live.streams()))
        reg.live.configure_lsl(sid, sid + "-behavior", None)
        rt = Runtime(reg, Recorder(tmp / "rec"))
        tap = Tap({"features.binned"})
        rt.bus.add_tap(tap)
        await rt.connect(f"lsl:{sid}")
        rt.start_pipeline(PipelineStartRequest(processing={"preset": "spikeband_threshold"}))
        await asyncio.sleep(WARMUP_S)
        rss0, f0, t0 = _rss_mb(), tap.count, time.monotonic()
        tap.armed = True
        await asyncio.sleep(seconds)
        dt = time.monotonic() - t0
        st = rt.adapter.source_metadata()["stats"]  # type: ignore[union-attr]
        ps = rt.pipeline.status()
        out = {
            "seconds": dt,
            "features": tap.count - f0,
            "expected_features": dt * 50,
            "gaps": st["gaps"],
            "missing": st["estimated_missing_samples"],
            "dropped_inputs": ps.counters["dropped_inputs"],
            "errors": ps.counters["errors"],
            "lat_p50": _pct(tap.lat_ms, 50),
            "lat_p99": _pct(tap.lat_ms, 99),
            "rss0": rss0,
            "rss1": _rss_mb(),
            "regressions": rt.diagnostics.timestamp_regressions,
            "validation_errors": rt.diagnostics.validation_errors,
        }
        await rt.shutdown()
        return out
    finally:
        _stop(pub)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=10.0)
    ap.add_argument("--soak", type=float, default=120.0)
    ap.add_argument("--write", type=Path, default=None)
    args = ap.parse_args()
    tmp = Path(tempfile.mkdtemp())
    (tmp / "m").mkdir()
    s = args.seconds
    lines: list[str] = []
    p = lines.append
    p("# BrainOS live-acquisition benchmarks (Milestone 3)\n")
    p(
        "> Measured on the machine below by `scripts/bench_live.py`. Publishers run in a separate "
        "process and speak real LSL (liblsl) or the Open Ephys ZMQ wire format; **no hardware "
        "was involved**. Synthetic signals are declared synthetic; FALCON H1 is real human data "
        "streamed as *prerecorded*. Re-run on your own machine: `make bench-live`.\n"
    )
    p(
        f"Measured {time.strftime('%Y-%m-%d %H:%M %Z')} with "
        f"`python scripts/bench_live.py --seconds {s:g} --soak {args.soak:g}`.\n"
    )
    p("| | |\n|---|---|")
    p(f"| machine | `{platform.machine()}` · {platform.platform()} |")
    p(f"| cpu count | {os.cpu_count()} |")
    p(f"| python | {sys.version.split()[0]} |")
    import pylsl

    p(f"| liblsl | {pylsl.library_info()} |")
    p("")

    p("## 1. LSL broadband ephys -> spike-band threshold crossings (20 ms bins)\n")
    p(
        "Synthetic 30 kHz float32 stream. *Acq->feature latency* is defined in the script "
        "docstring (LSL clock, same host; a bin cannot be emitted before its last sample "
        "arrives). CPU = runtime process (adapter + runtime + pipeline), % of one core.\n"
    )
    p(
        "| channels | samples/s/ch received | gaps / missing | features/s "
        "| acq->feature p50 / p99 / max ms | pipeline µs/input p50 / p99 | dropped inputs | CPU % |"
    )
    p("|---:|---:|---:|---:|---:|---:|---:|---:|")
    for ch in (32, 96):
        r = asyncio.run(lsl_raw(ch, s, tmp))
        p(
            f"| {ch} | {r['samples_per_s']:,.0f} | {r['gaps']} / {r['missing']} "
            f"| {r['features_per_s']:.1f} | {r['lat_p50']:.1f} / {r['lat_p99']:.1f} / "
            f"{r['lat_max']:.1f} | {r['proc_p50_us']:,.0f} / {r['proc_p99_us']:,.0f} "
            f"| {r['dropped_inputs']} | {r['cpu_pct']:.0f} |"
        )
        print(lines[-1], flush=True)
    p("")

    p("## 2. Open Ephys ZMQ -> spike-band threshold crossings\n")
    p(
        "Synthetic 30 kHz stream, 1024-sample blocks (one ZMQ message per channel per block, "
        "as the plugin sends). Open Ephys sample numbers are not on a clock shared with this "
        "host, so latency is reported from runtime ingest of a block to the derived feature "
        "(pipeline queueing + processing).\n"
    )
    p(
        "| channels | samples/s/ch | missed msgs / incomplete blocks / malformed | features/s "
        "| ingest->feature p50 / p99 ms | pipeline µs/input p50 / p99 | dropped inputs | CPU % |"
    )
    p("|---:|---:|---:|---:|---:|---:|---:|---:|")
    for ch in (32, 64):
        r = asyncio.run(openephys_raw(ch, s, tmp))
        p(
            f"| {ch} | {r['samples_per_s']:,.0f} | {r['missed_messages']} / "
            f"{r['incomplete_blocks']} / {r['malformed']} | {r['features_per_s']:.1f} "
            f"| {r['ingest_p50_ms']:.1f} / {r['ingest_p99_ms']:.1f} | {r['proc_p50_us']:,.0f} / "
            f"{r['proc_p99_us']:,.0f} | {r['dropped_inputs']} | {r['cpu_pct']:.0f} |"
        )
        print(lines[-1], flush=True)
    p("")

    p("## 3. FALCON H1 over LSL (real data, prerecorded) -> decoder -> router -> command\n")
    r3 = asyncio.run(falcon_decode(s, tmp))
    if r3 is None:
        p("Not measured: real data not downloaded (`make dataset`).\n")
    else:
        p(
            "Block 19250108T111022 streamed at 1x (50 bins/s, 176 units) with a ridge decoder "
            "trained on block 19250108T110520 and the command router on. Latency: LSL stamp of "
            "the bin -> `intent.pointer` (decoded_intent) ingested.\n"
        )
        p(
            "| commands/s | bin->command p50 / p99 / max ms | pipeline µs/bin p50 / p99 "
            "| gaps | dropped inputs | CPU % |\n|---:|---:|---:|---:|---:|---:|"
        )
        p(
            f"| {r3['commands_per_s']:.1f} | {r3['lat_p50']:.1f} / {r3['lat_p99']:.1f} / "
            f"{r3['lat_max']:.1f} | {r3['proc_p50_us']:,.0f} / {r3['proc_p99_us']:,.0f} "
            f"| {r3['gaps']} | {r3['dropped_inputs']} | {r3['cpu_pct']:.0f} |"
        )
        print(lines[-1], flush=True)
    p("")

    p("## 4. Reconnect under load (LSL, 32 ch @ 30 kHz, pipeline running)\n")
    r4 = asyncio.run(lsl_reconnect(tmp))
    p(
        "The publisher process is killed, then restarted ~2 s later with the same `source_id`. "
        "*Detect* = kill -> runtime state `reconnecting`; *recover* = restart -> frames "
        "flowing again (includes the publisher's own start-up and LSL resolution).\n"
    )
    p("| detect s | recover s | final state | reconnects | pipeline survived |")
    p("|---:|---:|---|---:|---|")
    p(
        f"| {r4['detect_s']:.2f} | {r4['recover_s']:.2f} | {r4['state']} | {r4['reconnects']} "
        f"| {'yes' if r4['pipeline_running'] else 'no (stopped; restart it)'} |"
    )
    print(lines[-1], flush=True)
    p("")

    p(f"## 5. Soak: {args.soak:g} s, LSL 32 ch @ 30 kHz + behavior stream, spike-band pipeline\n")
    r5 = asyncio.run(soak(args.soak, tmp))
    p(
        "| seconds | features / expected | gaps / missing samples | dropped inputs | errors "
        "| acq->feature p50 / p99 ms | RSS start -> end MB | ts regressions | invalid |"
    )
    p("|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    p(
        f"| {r5['seconds']:.0f} | {r5['features']:,} / {r5['expected_features']:,.0f} "
        f"| {r5['gaps']} / {r5['missing']} | {r5['dropped_inputs']} | {r5['errors']} "
        f"| {r5['lat_p50']:.1f} / {r5['lat_p99']:.1f} | {r5['rss0']:.0f} -> {r5['rss1']:.0f} "
        f"| {r5['regressions']} | {r5['validation_errors']} |"
    )
    print(lines[-1], flush=True)
    p("")
    p(
        "Notes: software/protocol measurements on one host. They do not characterize any "
        "amplifier, implant or network, and say nothing about closed-loop control performance."
    )
    text = "\n".join(lines) + "\n"
    print(text)
    if args.write:
        args.write.write_text(text)
        print(f"wrote {args.write}")


if __name__ == "__main__":
    main()
