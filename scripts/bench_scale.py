"""Milestone 5 (E): BrainOS performance at scale, measured on this machine.

Every stream here is **benchmark-generated synthetic data** (declared ``synthetic`` in its
LSL metadata, origin ``brainos:bench-scale-synthetic``), and every decoder is a
**benchmark-generated random-weight decoder** (not trained; its outputs are meaningless and
no decoding quality is measured). No hardware is involved. Nothing is estimated: each number
is printed by the run that measured it.

Process layout of the live sections (the deployment shape): an LSL publisher process
(acquisition, ``scripts/bench_scale.py _pub-*``), the runtime server process
(``python -m brainos.server``: adapter + runtime + pipeline + decoder + router + WebSocket),
and this process as the SDK application (Python SDK ``EventStream`` over the WebSocket).
CPU and RSS are read from ``/proc`` for each process (Linux; "n/a" elsewhere).

Latency definitions (same host; the LSL clock is the host's monotonic clock in every process):
* *bin -> app*: ``pylsl.local_clock()`` when the SDK app has received **and validated** an
  event, minus the event's ``device_timestamp_ns`` (the LSL time of the last sample of the
  bin it depends on). For ``features.binned`` this covers LSL transport, adapter polling
  (5 ms), runtime validation, the processing chain, the WebSocket and SDK parsing; for
  ``intent.pointer`` it also covers the decoder and the command router (*end-to-end
  inference latency*: sample -> decoded event -> command delivered to an SDK app).
* *jitter*: standard deviation of the inter-arrival interval of ``features.binned`` at the
  app, and the 99th percentile of its absolute deviation from the bin period.

Usage:
    python scripts/bench_scale.py [--seconds 10] [--soak 600] [--quick]
        [--sections micro,alternatives,chain,raw,ecog,counts,multi,consumers,recovery,soak]
        [--json results.json] [--write docs/BENCHMARKS_SCALE.md]
    python scripts/bench_scale.py --compare before.json after.json   # before/after tables
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import ctypes
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np

ORIGIN = "brainos:bench-scale-synthetic"
FS_RAW = 30_000.0
WARMUP_S = 2.5  # LSL connect + 1 s RMS estimation + filter settling; excluded from stats
SECTIONS = (
    "micro",
    "alternatives",
    "chain",
    "raw",
    "ecog",
    "counts",
    "multi",
    "consumers",
    "recovery",
    "soak",
)
CONTRACT_MAX_FRAME_CHANNELS = 1024  # RecordingFramePayload.channel_count (contract 1.4)
RSS_CAP_MB = 2500.0  # the benchmark stops a runtime that grows beyond this (shared host)

# ============================================================================ helpers


def pct(values: list[float], q: float) -> float:
    return float(np.percentile(values, q)) if values else float("nan")


def lat_summary(values: list[float]) -> dict[str, float]:
    return {
        "n": len(values),
        "p50": pct(values, 50),
        "p95": pct(values, 95),
        "p99": pct(values, 99),
        "p999": pct(values, 99.9),
        "max": max(values) if values else float("nan"),
    }


def best_of(fn: Callable[[], object], reps: int = 7, inner: int = 1) -> float:
    """Best wall time of ``reps`` runs (seconds per call): the least-disturbed measurement."""
    best = float("inf")
    for _ in range(reps):
        t0 = time.perf_counter()
        for _ in range(inner):
            fn()
        best = min(best, (time.perf_counter() - t0) / inner)
    return best


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


class Proc:
    """CPU (user+system) and RSS of one process from /proc (Linux)."""

    TICK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self._cpu0 = self.cpu_s()
        self._t0 = time.monotonic()

    def cpu_s(self) -> float | None:
        try:
            with open(f"/proc/{self.pid}/stat") as fh:
                fields = fh.read().rsplit(")", 1)[1].split()
            return (int(fields[11]) + int(fields[12])) / self.TICK
        except (OSError, IndexError, ValueError):
            return None

    def mem_mb(self, key: str = "VmRSS") -> float | None:
        try:
            with open(f"/proc/{self.pid}/status") as fh:
                for line in fh:
                    if line.startswith(key + ":"):
                        return int(line.split()[1]) / 1024
        except OSError:
            return None
        return None

    def reset(self) -> None:
        self._cpu0, self._t0 = self.cpu_s(), time.monotonic()

    def cpu_pct(self) -> float | None:
        c = self.cpu_s()
        if c is None or self._cpu0 is None:
            return None
        return 100 * (c - self._cpu0) / max(1e-9, time.monotonic() - self._t0)


def machine() -> dict[str, Any]:
    info: dict[str, Any] = {
        "machine": platform.machine(),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "python": sys.version.split()[0],
        "numpy": np.__version__,
    }
    with contextlib.suppress(OSError), open("/proc/cpuinfo") as fh:
        for line in fh:
            if line.startswith("model name"):
                info["cpu"] = line.split(":", 1)[1].strip()
                break
    with contextlib.suppress(OSError), open("/proc/meminfo") as fh:
        info["mem_gb"] = round(int(fh.readline().split()[1]) / 1024 / 1024, 1)
    for mod in ("scipy", "pydantic", "pylsl", "orjson", "numba"):
        try:
            m = __import__(mod)
            info[mod] = getattr(m, "__version__", getattr(m, "VERSION", "?"))
        except ImportError:
            info[mod] = "not installed"
    with contextlib.suppress(Exception):
        import pylsl

        info["liblsl"] = pylsl.library_version()
    return info


def loadavg() -> str:
    try:
        return " ".join(f"{x:.2f}" for x in os.getloadavg())
    except OSError:
        return "n/a"


# ============================================================ publishers (own process)


def _labels(n: int) -> list[str]:
    return [f"ch{i:04d}" for i in range(n)]


def publish_raw(channels: int, rate: float, source_id: str, chunk_ms: float) -> None:
    """Synthetic broadband stream from a pre-generated looped buffer (declared synthetic).

    The buffer is generated once with ``SyntheticEphys`` (noise + spikes) for up to 256
    channels and tiled with per-copy time shifts, so the publisher costs only the LSL push.
    """
    import pylsl

    from brainos.testing.lsl_publishers import SyntheticEphys, _channels, _declare

    chunk = max(1, round(rate * chunk_ms / 1000))
    n_buf = chunk * max(1, round(0.25 * rate / chunk))  # ~0.25 s, whole chunks
    base_ch = min(channels, 256)
    gen = SyntheticEphys(channels=base_ch, fs=rate, seed=0)
    base = gen.chunk(n_buf)
    buf = np.empty((n_buf, channels), dtype=np.float32)
    for k in range(0, channels, base_ch):
        w = min(base_ch, channels - k)
        buf[:, k : k + w] = np.roll(base[:, :w], shift=(k // base_ch) * 997, axis=0)
    info = pylsl.StreamInfo(
        "BrainOS bench-scale synthetic ephys",
        "EEG",
        channels,
        rate,
        pylsl.cf_float32,
        source_id,
    )
    _channels(info.desc(), _labels(channels), "microvolts", "EEG")
    _declare(info.desc(), synthetic=True, prerecorded=False, origin=ORIGIN)
    out = pylsl.StreamOutlet(info, chunk_size=chunk, max_buffered=60)
    _pace(
        lambda k, stamp: out.push_chunk(buf[(k * chunk) % n_buf :][:chunk], stamp),
        chunk / rate,
    )


def publish_counts(channels: int, rate: float, source_id: str, behavior: bool) -> None:
    """Synthetic binned spike counts (type SpikeCounts, declared synthetic), one push per bin."""
    import pylsl

    from brainos.testing.lsl_publishers import _channels, _declare

    rng = np.random.default_rng(1)
    n_buf = int(rate * 10)
    buf = rng.poisson(1.5, size=(n_buf, channels)).astype(np.int16)
    info = pylsl.StreamInfo(
        "BrainOS bench-scale synthetic counts",
        "SpikeCounts",
        channels,
        rate,
        pylsl.cf_int16,
        source_id,
    )
    _channels(info.desc(), _labels(channels), "count", "SpikeCount")
    _declare(
        info.desc(),
        synthetic=True,
        prerecorded=False,
        origin=ORIGIN,
        feature="spike_count",
    )
    out = pylsl.StreamOutlet(info, chunk_size=1, max_buffered=60)
    beh = mk = None
    if behavior:
        b = pylsl.StreamInfo(
            "BrainOS bench-scale behavior",
            "Behavior",
            2,
            rate,
            pylsl.cf_float32,
            source_id + "-b",
        )
        _channels(b.desc(), ["vx", "vy"], "arbitrary", "Velocity")
        _declare(
            b.desc(),
            synthetic=True,
            prerecorded=False,
            origin=ORIGIN,
            quantity="velocity",
        )
        beh = pylsl.StreamOutlet(b)
        m = pylsl.StreamInfo(
            "BrainOS bench-scale markers",
            "Markers",
            1,
            0.0,
            pylsl.cf_string,
            source_id + "-m",
        )
        _declare(m.desc(), synthetic=True, prerecorded=False, origin=ORIGIN)
        mk = pylsl.StreamOutlet(m)

    def push(k: int, stamp: float) -> None:
        out.push_chunk(buf[k % n_buf : k % n_buf + 1], stamp)
        if beh is not None and mk is not None:
            beh.push_sample([float(np.cos(k / 50)), float(np.sin(k / 50))], stamp)
            if k % int(rate) == 0:
                mk.push_sample([f"trial {k // int(rate)}"], stamp)

    _pace(push, 1.0 / rate)


def _pace(push: Callable[[int, float], None], dt: float) -> None:
    import pylsl

    stop = False

    def _stop(*_: object) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    time.sleep(0.3)
    t0 = pylsl.local_clock()
    k = 0
    while not stop:
        target = t0 + (k + 1) * dt
        now = pylsl.local_clock()
        if target > now:
            time.sleep(target - now)
        push(k, target)  # stamp = time of the last sample in the chunk
        k += 1


def spawn_publisher(kind: str, channels: int, rate: float, sid: str, *extra: str) -> Proc:
    args = [
        sys.executable,
        __file__,
        kind,
        "--channels",
        str(channels),
        "--rate",
        str(rate),
    ]
    p = subprocess.Popen(
        [*args, "--source-id", sid, *extra],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _CHILDREN.append(p)
    return Proc(p.pid)


_CHILDREN: list[subprocess.Popen[bytes]] = []


def kill(proc: Proc) -> None:
    for p in list(_CHILDREN):
        if p.pid == proc.pid:
            p.terminate()
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()
                p.wait()
            _CHILDREN.remove(p)


def kill_all() -> None:
    for p in list(_CHILDREN):
        with contextlib.suppress(Exception):
            p.kill()
            p.wait(5)
    _CHILDREN.clear()


# ================================================================ server (own process)


class Server:
    def __init__(self, tmp: Path) -> None:
        self.port = free_port()
        self.data = tmp / f"server-{self.port}"
        (self.data / "models").mkdir(parents=True)
        env = {
            **os.environ,
            "BRAINOS_PORT": str(self.port),
            "BRAINOS_DATA_DIR": str(self.data),
            "BRAINOS_REPORTS_DIR": str(self.data / "reports"),
            "BRAINOS_STATIC_DIR": str(self.data / "no-static"),
            "BRAINOS_PLUGINS": "0",
            "BRAINOS_LOG_LEVEL": "ERROR",
        }
        self.log = open(self.data / "server.log", "wb")  # noqa: SIM115 - closed in stop()
        p = subprocess.Popen(
            [sys.executable, "-m", "brainos.server"],
            env=env,
            stdout=self.log,
            stderr=self.log,
        )
        _CHILDREN.append(p)
        self.proc = Proc(p.pid)
        self.base = f"http://127.0.0.1:{self.port}"
        self.started = time.monotonic()
        self.rss_killed_after_s: float | None = None
        self.rss_max_mb = 0.0
        self._watch: asyncio.Task[None] | None = None

    def watch_rss(self, cap_mb: float) -> None:
        """Kill the runtime if its RSS exceeds ``cap_mb`` (the host is shared: an overloaded
        runtime with count-bounded queues can otherwise grow until the OOM killer acts)."""

        async def run() -> None:
            while True:
                rss = self.proc.mem_mb()
                if rss is None:
                    return
                self.rss_max_mb = max(self.rss_max_mb, rss)
                if rss > cap_mb:
                    self.rss_killed_after_s = time.monotonic() - self.started
                    kill(self.proc)
                    return
                await asyncio.sleep(0.1)

        self._watch = asyncio.create_task(run())

    async def ready(self, limit_s: float = 30) -> None:
        import httpx

        end = time.monotonic() + limit_s
        async with httpx.AsyncClient() as c:
            while time.monotonic() < end:
                with contextlib.suppress(httpx.HTTPError):
                    if (await c.get(self.base + "/api/v1/health")).status_code == 200:
                        return
                await asyncio.sleep(0.1)
        raise RuntimeError("server did not start")

    def stop(self) -> None:
        if self._watch is not None:
            self._watch.cancel()
        kill(self.proc)
        self.log.close()


def write_random_decoder(models_dir: Path, channels: int, *, feature: str, bin_ms: float) -> str:
    """A random-weight ridge decoder (NOT trained; outputs meaningless) for timing only."""
    from brainos.decoding.ridge import TAU_MS, RidgeDecoder, exponential_kernel

    rng = np.random.default_rng(channels)
    w = rng.standard_normal((channels, 2)) / np.sqrt(channels)
    model = RidgeDecoder(
        model_id=f"bench-scale-random-{channels}ch-{int(bin_ms)}ms",
        space="bench_synthetic_2d",
        quantity="velocity",
        dims=["vx", "vy"],
        unit="arbitrary",
        bin_ms=bin_ms,
        tau_ms=TAU_MS,
        kernel=exponential_kernel(bin_ms).tolist(),
        x_mean=[1.5] * channels,
        x_std=[1.0] * channels,
        weights=w.tolist(),
        intercept=[0.0, 0.0],
        alpha=1.0,
        training={
            "behavior_std": [1.0, 1.0],
            "note": "benchmark: random weights, not trained",
        },
        method="benchmark-generated random weights (timing only; not a decoder)",
        input={
            "event_type": "features.binned",
            "feature": feature,
            "bin_ms": bin_ms,
            "channel_count": channels,
            "channel_labels": _labels(channels),
        },
        source={
            "identity": ORIGIN,
            "description": "benchmark-generated synthetic stream",
        },
    )
    model.save(models_dir / f"{model.model_id}.json")
    return model.model_id


class App:
    """SDK application (this process): records arrival latency of features and commands."""

    def __init__(self, base: str, app_id: str, required: list[str], optional: list[str]) -> None:
        self.base, self.app_id, self.required, self.optional = (
            base,
            app_id,
            required,
            optional,
        )
        self.armed = False
        self.feat_lat: list[float] = []
        self.cmd_lat: list[float] = []
        self.feat_arrivals: list[float] = []
        self.bins: list[int] = []
        self.frames = 0
        self.frame_bytes_max = 0
        self.received = 0
        self.stream: Any = None
        self.closed: str | None = None
        self.task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        from brainos.sdk import EventStream

        self.stream = await EventStream.connect(
            app_id=self.app_id,
            app_name=self.app_id,
            required=self.required,
            optional=self.optional,
            base_url=self.base,
        )
        self.task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        import pylsl

        from brainos.sdk import is_event

        clock = pylsl.local_clock
        try:
            async for item in self.stream:
                if not is_event(item):
                    continue
                now = clock()
                self.received += 1
                et = item.event_type.value
                if not self.armed:
                    continue
                dev = item.device_timestamp_ns
                if et == "features.binned" or et == "features.vector":
                    self.feat_arrivals.append(now)
                    self.bins.append(item.payload.bin_index)  # type: ignore[union-attr]
                    if dev is not None:
                        self.feat_lat.append(now * 1e3 - dev / 1e6)
                elif et == "intent.pointer" and dev is not None:
                    self.cmd_lat.append(now * 1e3 - dev / 1e6)
                elif et == "recording.frame":
                    self.frames += 1
        except Exception as exc:  # e.g. message too big for the SDK's 8 MiB limit
            self.closed = f"{type(exc).__name__}: {exc}"[:160]

    def arm(self) -> None:
        self.armed = True

    def summary(self, bin_ms: float) -> dict[str, Any]:
        iv = np.diff(self.feat_arrivals) * 1e3 if len(self.feat_arrivals) > 2 else np.array([])
        missing = (max(self.bins) - min(self.bins) + 1 - len(set(self.bins))) if self.bins else 0
        return {
            "features": len(self.bins),
            "missing_bins": int(missing),
            "feat": lat_summary(self.feat_lat),
            "cmd": lat_summary(self.cmd_lat),
            "commands": len(self.cmd_lat),
            "jitter_sd_ms": float(np.std(iv)) if iv.size else float("nan"),
            "jitter_p99_ms": float(np.percentile(np.abs(iv - bin_ms), 99)) if iv.size else 0.0,
            "delivery_gaps": self.stream.stats.delivery_gaps if self.stream else 0,
            "invalid": self.stream.stats.invalid if self.stream else 0,
            "frames": self.frames,
            "closed": self.closed,
        }

    async def stop(self) -> None:
        if self.task is not None:
            self.task.cancel()
            with contextlib.suppress(BaseException):
                await self.task
        if self.stream is not None:
            with contextlib.suppress(Exception):
                await self.stream.close()


async def open_lsl_source(rc: Any, sid: str, behavior: bool = False, limit: float = 20) -> str:
    end = time.monotonic() + limit
    want = {sid, sid + "-b", sid + "-m"} if behavior else {sid}
    while time.monotonic() < end:
        found = await rc.discover_lsl(1.0)
        keys = {s["key"] for s in found["streams"]}
        if want <= keys:
            if behavior:
                desc = await rc.configure_lsl(sid, sid + "-b", sid + "-m")
            else:
                desc = await rc.configure_lsl(sid)
            return str(desc.device_id)
    raise RuntimeError(f"LSL stream {sid} not discovered")


async def pipeline_stats(rc: Any, device_id: str) -> dict[str, Any] | None:
    """Runtime counters over REST, or None if the runtime did not answer within 5 s (a
    saturated runtime whose event loop is starved cannot serve REST)."""
    try:
        return await asyncio.wait_for(_pipeline_stats(rc, device_id), 5.0)
    except Exception:
        return None


async def _pipeline_stats(rc: Any, device_id: str) -> dict[str, Any]:
    pipe = await rc.pipeline()
    diag = await rc.diagnostics()
    src = await rc._call("GET", f"/devices/{device_id}/source")
    stats = src.get("stats") or {}
    return {
        "samples": stats.get("samples", 0),
        "gaps": stats.get("gaps", 0),
        "missing": stats.get("estimated_missing_samples", 0),
        "inputs": pipe["counters"]["inputs"],
        "dropped_inputs": pipe["counters"]["dropped_inputs"],
        "errors": pipe["counters"]["errors"],
        "features_out": pipe["counters"]["features_out"],
        "decoded_out": pipe["counters"]["decoded_out"],
        "commands_out": pipe["counters"]["commands_out"],
        "proc_us": pipe["processing_us"],
        "validation_errors": diag["counters"]["validation_errors"],
        "subscriber_drops": diag["counters"]["subscriber_drops"],
        "frames": next(
            (t["total"] for t in diag["event_types"] if t["event_type"] == "recording.frame"),
            0,
        ),
        "ingest_us": diag["pipeline_latency"],
        "delivery_us": diag["delivery_latency"],
    }


# ======================================================== live scenario (3 processes)


async def live_run(
    tmp: Path,
    *,
    kind: str,
    channels: int,
    rate: float,
    seconds: float,
    preset: str,
    bin_ms: float,
    decoder: bool = True,
    behavior: bool = False,
    raw_consumer: bool = False,
    stalled_consumer: bool = False,
    rss_every_s: float | None = None,
    server: Server | None = None,
) -> dict[str, Any]:

    own = server is None
    srv = server or Server(tmp)
    sid = f"bench-scale-{kind}-{channels}-{int(rate)}-{srv.port}"
    pub = (
        spawn_publisher("_pub-raw", channels, rate, sid)
        if kind == "raw"
        else spawn_publisher(
            "_pub-counts", channels, rate, sid, *(["--behavior"] if behavior else [])
        )
    )
    apps: list[App] = []
    try:
        return await _live_body(
            srv,
            sid,
            pub,
            apps,
            kind=kind,
            channels=channels,
            rate=rate,
            seconds=seconds,
            preset=preset,
            bin_ms=bin_ms,
            decoder=decoder,
            behavior=behavior,
            raw_consumer=raw_consumer,
            stalled_consumer=stalled_consumer,
            rss_every_s=rss_every_s,
        )
    except Exception as exc:  # recorded, not fatal: the report says what failed
        log = srv.data / "server.log"
        tail = log.read_text(errors="replace")[-400:] if log.exists() else ""
        err = f"{type(exc).__name__}: {exc}"[:200]
        if srv.rss_killed_after_s is not None:
            err = (
                f"runtime RSS exceeded {RSS_CAP_MB:.0f} MB {srv.rss_killed_after_s:.1f} s after "
                "start; stopped by the benchmark"
            )
        return {
            "kind": kind,
            "channels": channels,
            "rate": rate,
            "error": err,
            "server_log_tail": tail,
        }
    finally:
        for a in apps:
            await a.stop()
        for ws in _STALLED:
            with contextlib.suppress(Exception):
                ws.transport.abort()
        _STALLED.clear()
        kill(pub)
        if own:
            srv.stop()


async def _live_body(
    srv: Server,
    sid: str,
    pub: Proc,
    apps: list[App],
    *,
    kind: str,
    channels: int,
    rate: float,
    seconds: float,
    preset: str,
    bin_ms: float,
    decoder: bool,
    behavior: bool,
    raw_consumer: bool,
    stalled_consumer: bool,
    rss_every_s: float | None,
) -> dict[str, Any]:
    import httpx

    from brainos.sdk import RuntimeClient

    await srv.ready()
    if srv._watch is None:
        srv.watch_rss(RSS_CAP_MB)
    async with RuntimeClient(srv.base, timeout=30) as rc:
        # Applications connect first (as they would, before the operator starts a source):
        # a runtime that later saturates cannot complete new WebSocket handshakes.
        app = App(srv.base, "bench-app", ["neural_features"], ["pointer_intent"])
        await app.start()
        apps.append(app)
        viewer: tuple[Proc, Path] | None = None
        if raw_consumer:
            viewer = spawn_viewer(srv.base, srv.data / "viewer.json")
            await asyncio.sleep(1.0)  # connected before the source starts
        if stalled_consumer:
            await _stalled_client(srv.base)
        did = await open_lsl_source(rc, sid, behavior=behavior)
        feature = "threshold_crossing_count" if kind == "raw" else "spike_count"
        model_id = None
        router = None
        if decoder:
            model_id = write_random_decoder(
                srv.data / "models", channels, feature=feature, bin_ms=bin_ms
            )
            router = {"enabled": True, "x_dim": "vx", "y_dim": "vy"}
            await rc.authorize_app("bench-app", ["pointer_intent"])
        proc: dict[str, Any] = {"preset": preset}
        if preset == "spikeband_threshold":
            proc["bin_ms"] = bin_ms
        await rc.connect(did)
        try:
            await rc.start_pipeline(**proc, model_id=model_id, router=router)
        except Exception as exc:
            await asyncio.sleep(0.3)  # let the RSS watchdog record a kill it just made
            err = f"pipeline start failed: {type(exc).__name__}: {exc}"[:200]
            if isinstance(exc, httpx.TimeoutException):
                err = "pipeline start timed out: runtime unresponsive (event loop saturated)"
            if srv.rss_killed_after_s is not None:
                err = (
                    f"runtime RSS exceeded {RSS_CAP_MB:.0f} MB {srv.rss_killed_after_s:.1f} s "
                    "after start (before the pipeline could start); stopped by the benchmark"
                )
            return {"kind": kind, "channels": channels, "rate": rate, "error": err}
        await asyncio.sleep(WARMUP_S)
        for a in apps:
            a.arm()
        s0 = await pipeline_stats(rc, did)
        pub.reset()
        srv.proc.reset()
        if viewer is not None:
            viewer[0].reset()
            viewer[1].with_suffix(".arm").touch()  # the viewer counts from here
        me = Proc(os.getpid())
        t0 = time.monotonic()
        rss_trace: list[tuple[float, float]] = []
        if rss_every_s:
            while time.monotonic() - t0 < seconds:
                rss_trace.append((time.monotonic() - t0, srv.proc.mem_mb() or 0.0))
                await asyncio.sleep(min(rss_every_s, seconds - (time.monotonic() - t0)))
            rss_trace.append((time.monotonic() - t0, srv.proc.mem_mb() or 0.0))
        else:
            await asyncio.sleep(seconds)
        dt = time.monotonic() - t0
        cpu = {"publisher": pub.cpu_pct(), "runtime": srv.proc.cpu_pct(), "app": me.cpu_pct()}
        if viewer is not None:
            cpu["viewer"] = viewer[0].cpu_pct()
        rss = {
            "publisher": pub.mem_mb(),
            "runtime": srv.proc.mem_mb(),
            "runtime_peak": srv.proc.mem_mb("VmHWM"),
            "app": me.mem_mb(),
        }
        s1 = await pipeline_stats(rc, did)
        try:
            state = (await asyncio.wait_for(rc.runtime(), 5.0)).state
        except Exception:
            state = "unresponsive"
    summary = apps[0].summary(bin_ms)

    def delta(key: str) -> Any:
        return None if s0 is None or s1 is None else s1[key] - s0[key]

    out: dict[str, Any] = {
        "kind": kind,
        "channels": channels,
        "rate": rate,
        "preset": preset,
        "bin_ms": bin_ms,
        "seconds": dt,
        "rest_responsive": s0 is not None and s1 is not None,
        "samples_per_s_per_ch": None if delta("samples") is None else delta("samples") / dt,
        "gaps": delta("gaps"),
        "missing": delta("missing"),
        "frames_per_s": None if delta("frames") is None else delta("frames") / dt,
        "validation_errors": None if s1 is None else s1["validation_errors"],
        "inputs_per_s": None if delta("inputs") is None else delta("inputs") / dt,
        "dropped_inputs": delta("dropped_inputs"),
        "pipeline_errors": delta("errors"),
        "features_per_s": summary["features"] / dt,
        "expected_features_per_s": 1000.0 / bin_ms,
        "proc_us": None if s1 is None else s1["proc_us"],
        "ingest_us": None if s1 is None else s1["ingest_us"],
        "delivery_us": None if s1 is None else s1["delivery_us"],
        "subscriber_drops": delta("subscriber_drops"),
        "app": summary,
        "cpu_pct": cpu,
        "rss_mb": rss,
        "state": state,
        "loadavg": loadavg(),
        "rss_max_mb": srv.rss_max_mb,
    }
    if srv.rss_killed_after_s is not None:
        out["error"] = (
            f"runtime RSS exceeded {RSS_CAP_MB:.0f} MB {srv.rss_killed_after_s:.1f} s after "
            "start; stopped by the benchmark"
        )
    if viewer is not None:
        kill(viewer[0])  # SIGTERM: the viewer writes its counts and exits
        try:
            v = json.loads(viewer[1].read_text())
        except (OSError, ValueError):
            v = {"frames": 0, "bytes": 0, "delivery_gaps": 0, "closed": "no report"}
        out["viewer"] = v | {"frames_per_s": v["frames"] / dt, "mb_per_s": v["bytes"] / dt / 1e6}
    if rss_trace:
        out["rss_trace"] = rss_trace
    return out


async def _stalled_client(base: str) -> None:
    """A WebSocket client that completes the hello and then never reads (a frozen app)."""
    import websockets

    url = base.replace("http://", "ws://") + "/api/v1/stream"
    ws = await websockets.connect(url, max_size=None)
    hello = {
        "type": "hello",
        "protocol": "brainos.stream/1",
        "app": {"id": "bench-stalled", "name": "stalled", "kind": "sdk"},
        "capabilities": {"required": [], "optional": ["recording", "neural_features"]},
    }
    await ws.send(json.dumps(hello))
    await ws.recv()
    ws.transport.pause_reading()  # stop reading: the server's sends back up
    _STALLED.append(ws)


_STALLED: list[Any] = []


def spawn_viewer(base: str, out: Path) -> tuple[Proc, Path]:
    p = subprocess.Popen(
        [sys.executable, __file__, "_viewer", "--base", base, "--out", str(out)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _CHILDREN.append(p)
    return Proc(p.pid), out


def run_viewer(base: str, out: Path) -> None:
    """A raw-signal viewer app (own process): Python SDK client requesting ``recording``;
    counts frames and bytes after ``<out>.arm`` appears; writes counts on SIGTERM."""
    from brainos.sdk import EventStream, is_event

    stats: dict[str, Any] = {"frames": 0, "bytes": 0, "delivery_gaps": 0, "closed": None}
    arm = out.with_suffix(".arm")

    async def main() -> None:
        stream = await EventStream.connect(
            app_id="bench-raw-viewer", app_name="raw viewer", required=["recording"], base_url=base
        )
        armed = False
        gaps0 = 0
        try:
            async for item in stream:
                if not armed and arm.exists():
                    armed, gaps0 = True, stream.stats.delivery_gaps
                if armed and is_event(item) and item.event_type.value == "recording.frame":
                    stats["frames"] += 1
                    p = item.payload
                    stats["bytes"] += 8 * p.channel_count * len(p.samples[0])  # type: ignore[union-attr]
                stats["delivery_gaps"] = stream.stats.delivery_gaps - gaps0
        except Exception as exc:  # e.g. a frame larger than the SDK's 8 MiB message limit
            stats["closed"] = f"{type(exc).__name__}: {exc}"[:160]

    def stop(*_: object) -> None:
        out.write_text(json.dumps(stats))
        os._exit(0)

    signal.signal(signal.SIGTERM, stop)
    asyncio.run(main())
    stop()


# ==================================================================== micro (in-process)


def _offline_lsl_adapter(channels: int, rate: float) -> Any:
    from brainos.adapters.lsl import LSLAdapter, LSLSourceSpec
    from brainos.adapters.lsl.metadata import ChannelMeta, Declaration, StreamMeta

    meta = StreamMeta(
        name="bench",
        type="EEG",
        channel_count=channels,
        nominal_srate=rate,
        channel_format="float32",
        source_id="bench",
        hostname="localhost",
        uid="bench",
        created_at=0.0,
        channels=tuple(
            ChannelMeta(index=i, label=lab, unit="microvolts", type="EEG")
            for i, lab in enumerate(_labels(channels))
        ),
        declaration=Declaration(synthetic=True, origin=ORIGIN),
    )
    return LSLAdapter(LSLSourceSpec(device_id="lsl:bench", signal=meta))


async def _micro_one(channels: int, n: int, reps: int) -> dict[str, Any]:
    from brainos.adapters.simulated import OperatorIntentSource
    from brainos.contracts.capabilities import Capability
    from brainos.contracts.protocol import AppInfo, RuntimeState
    from brainos.runtime import DeviceRegistry, Recorder, Runtime
    from brainos.runtime.pipeline import PipelineStartRequest

    adapter = _offline_lsl_adapter(channels, FS_RAW)
    rng = np.random.default_rng(0)
    data = (rng.standard_normal((n, channels)) * 10).astype(np.float32)
    part = {"data": data, "ts": [1.0 + i / FS_RAW for i in range(n)], "first_index": 0}
    t_norm = best_of(lambda: adapter._signal_drafts(part), reps)
    # one 10 ms chunk may become several frames (frame size cap): every stage below handles
    # all of them, so each figure is per chunk of n samples
    drafts = adapter._signal_drafts(part)
    tmp = Path(tempfile.mkdtemp())
    rt = Runtime(DeviceRegistry(OperatorIntentSource(), tmp), Recorder(tmp), queue_size=64)
    # bypass connect(): the offline adapter is never opened; only its pure normalize() is used
    rt._device, rt._session_id, rt._adapter = (
        adapter.descriptor,
        "ses_benchmarkscale",
        adapter,
    )
    rt._state = RuntimeState.STREAMING
    now = time.monotonic_ns()

    def ingest_chunk() -> None:
        for d in drafts:
            rt._ingest(d, now)

    t_ingest = best_of(ingest_chunk, reps)
    sub = rt.register_app(AppInfo(id="m", name="m"), [], [Capability.RECORDING])

    async def send_chunk() -> int:
        ingest_chunk()
        size = 0
        for _ in drafts:
            frame, enq = await asyncio.wait_for(sub.next_message(), 5)
            while enq is None:  # a control message (runtime snapshot): not a frame
                frame, enq = await asyncio.wait_for(sub.next_message(), 5)
            size += len(frame)
        return size

    assert Capability.RECORDING in sub.allowed, sub.negotiation
    size = await send_chunk()
    t_send = float("inf")
    for _ in range(reps):
        t0 = time.perf_counter()
        await send_chunk()
        t_send = min(t_send, time.perf_counter() - t0)
    rt.unregister_app(sub.connection_id)
    captured: list[Any] = []
    rt.bus.add_tap(lambda env, _j: captured.append(env))
    rt.start_pipeline(PipelineStartRequest(processing={"preset": "spikeband_threshold"}))
    run = rt.pipeline._run

    def chunk_envs() -> list[Any]:
        captured.clear()
        ingest_chunk()
        return list(captured)

    for _ in range(int(1.2 * FS_RAW / n) + 2):  # past the 1 s RMS window
        for e in chunk_envs():
            rt.pipeline._process(run, e)
    envs = chunk_envs()

    def process_chunk() -> None:
        for e in envs:
            rt.pipeline._process(run, e)

    t_proc = best_of(process_chunk, reps)
    await rt.pipeline.aclose()
    values = n * channels
    frames_per_s = FS_RAW / n
    out = {
        "channels": channels,
        "samples": n,
        "frames": len(drafts),
        "json_bytes": size,
        "normalize_us": t_norm * 1e6,
        "ingest_us": t_ingest * 1e6,
        "ingest_send_us": t_send * 1e6,
        "process_us": t_proc * 1e6,
    }
    for k in ("normalize", "ingest", "ingest_send", "process"):
        out[k + "_ns_per_value"] = out[k + "_us"] * 1e3 / values
        out[k + "_core_pct"] = out[k + "_us"] * 1e-6 * frames_per_s * 100
    return out


def section_micro(quick: bool) -> list[dict[str, Any]]:
    reps = 3 if quick else 7
    return [asyncio.run(_micro_one(ch, 300, reps)) for ch in (64, 256, 1024)]


# ============================================================ alternatives (head-to-head)

_C_SOS = r"""
#include <stddef.h>
/* Direct-form II transposed SOS cascade, channels innermost (x is samples x channels,
   C order), so the inner loop is contiguous and vectorizable across channels. */
void sos_cascade(const double *sos, int nsec, double *x, size_t n, size_t ch, double *zi) {
    for (int s = 0; s < nsec; ++s) {
        const double b0 = sos[s*6+0], b1 = sos[s*6+1], b2 = sos[s*6+2];
        const double a1 = sos[s*6+4], a2 = sos[s*6+5];
        double *z0 = zi + (size_t)s*2*ch, *z1 = z0 + ch;
        for (size_t i = 0; i < n; ++i) {
            double *row = x + i*ch;
            for (size_t c = 0; c < ch; ++c) {
                double xi = row[c];
                double y = b0*xi + z0[c];
                z0[c] = b1*xi - a1*y + z1[c];
                z1[c] = b2*xi - a2*y;
                row[c] = y;
            }
        }
    }
}
"""


def _build_c(tmp: Path) -> Any:
    cc = shutil.which("cc") or shutil.which("gcc")
    if cc is None:
        return None
    src, lib = tmp / "sos.c", tmp / "libsos.so"
    src.write_text(_C_SOS)
    r = subprocess.run(
        [cc, "-O3", "-march=native", "-shared", "-fPIC", "-o", str(lib), str(src)],
        capture_output=True,
    )
    if r.returncode != 0:
        return None
    so = ctypes.CDLL(str(lib))
    so.sos_cascade.restype = None
    return so.sos_cascade


def _numba_sos() -> Any:
    try:
        import numba
    except ImportError:
        return None

    @numba.njit(cache=False, fastmath=False)  # type: ignore[misc]
    def sos(sos: Any, x: Any, zi: Any) -> None:
        n, ch = x.shape
        for s in range(sos.shape[0]):
            b0, b1, b2, a1, a2 = sos[s, 0], sos[s, 1], sos[s, 2], sos[s, 4], sos[s, 5]
            for i in range(n):
                for c in range(ch):
                    xi = x[i, c]
                    y = b0 * xi + zi[s, 0, c]
                    zi[s, 0, c] = b1 * xi - a1 * y + zi[s, 1, c]
                    zi[s, 1, c] = b2 * xi - a2 * y
                    x[i, c] = y

    return sos


def _alt_json(ch: int, reps: int, rng: np.random.Generator) -> list[dict[str, Any]]:
    from pydantic import TypeAdapter

    ta = TypeAdapter(list[list[float]])
    a = (rng.standard_normal((ch, 300)) * 10).astype(np.float32).astype(np.float64)
    lst = a.tolist()
    ref = ta.dump_json(lst)
    cands: dict[str, Callable[[], bytes]] = {
        "pydantic dump_json(list) [today, excl. tolist]": lambda: ta.dump_json(lst),
        "ndarray.tolist + pydantic": lambda: ta.dump_json(a.tolist()),
    }
    with contextlib.suppress(ImportError):
        import orjson

        cands["orjson(ndarray)"] = lambda: orjson.dumps(a, option=orjson.OPT_SERIALIZE_NUMPY)
        cands["orjson(list)"] = lambda: orjson.dumps(lst)
    with contextlib.suppress(ImportError):
        import msgspec

        enc = msgspec.json.Encoder()
        cands["msgspec(list)"] = lambda: enc.encode(lst)
    with contextlib.suppress(ImportError):
        from brainos.runtime.fastjson import samples_json

        cands["brainos.runtime.fastjson (shipped)"] = lambda: samples_json(a).encode()
    return [
        {
            "channels": ch,
            "method": name,
            "ns_per_value": best_of(fn, reps) / a.size * 1e9,
            "byte_identical": fn() == ref,
        }
        for name, fn in cands.items()
    ]


def _alt_validate(ch: int, reps: int, rng: np.random.Generator) -> list[dict[str, Any]]:
    from brainos.contracts.events import RecordingFramePayload

    a = (rng.standard_normal((ch, 300)) * 10).astype(np.float32).astype(np.float64)
    lst = a.tolist()
    payload = {
        "sample_rate_hz": FS_RAW,
        "channel_count": ch,
        "first_sample_index": 0,
        "unit": "uV",
        "samples": lst,
    }
    cands: dict[str, Callable[[], object]] = {
        "pydantic list[list[FiniteFloat]] (today)": lambda: RecordingFramePayload.model_validate(
            payload
        ),
        "numpy isfinite + shape": lambda: bool(np.isfinite(a).all()) and a.shape[0] == ch,
        "numpy owned float64 copy": lambda: np.array(a, dtype=np.float64, order="C"),
        "np.asarray(list) (pipeline input today)": lambda: np.asarray(lst, dtype=np.float64),
    }
    arr_payload = {**payload, "samples": a}
    try:
        RecordingFramePayload.model_validate(arr_payload)
        cands["RecordingFramePayload from ndarray (shipped)"] = lambda: (
            RecordingFramePayload.model_validate(arr_payload)
        )
    except Exception:
        pass
    return [
        {"channels": ch, "method": k, "ns_per_value": best_of(fn, reps) / a.size * 1e9}
        for k, fn in cands.items()
    ]


def _alt_sos(
    ch: int, reps: int, rng: np.random.Generator, c_sos: Any, nb_sos: Any
) -> list[dict[str, Any]]:
    from scipy import signal as sps

    sos = sps.butter(4, [250.0, 5000.0], btype="bandpass", fs=FS_RAW, output="sos")
    x = rng.standard_normal((300, ch)) * 10
    zi = np.zeros((sos.shape[0], 2, ch))
    ref_y, _ = sps.sosfilt(sos, x, axis=0, zi=zi)
    xt = np.ascontiguousarray(x.T)
    zit = np.zeros((sos.shape[0], ch, 2))
    xf = np.asfortranarray(x)

    def scipy_c() -> Any:
        return sps.sosfilt(sos, x, axis=0, zi=zi)[0]

    def scipy_f() -> Any:
        return sps.sosfilt(sos, xf, axis=0, zi=zi)[0]

    def scipy_t() -> Any:
        return sps.sosfilt(sos, xt, axis=1, zi=zit)[0].T

    rows: dict[str, Callable[[], Any]] = {
        "scipy.sosfilt, (n, ch) C order (today's list path)": scipy_c,
        "scipy.sosfilt, (n, ch) F order (= array-backed frame)": scipy_f,
        "scipy.sosfilt on (ch, n), axis=1": scipy_t,
    }
    if nb_sos is not None:
        nb_sos(sos, x.copy(), zi.copy())  # compile outside the timing

        def nb_run() -> Any:
            y = x.copy()
            nb_sos(sos, y, zi.copy())
            return y

        rows["numba, channels innermost (prototype)"] = nb_run
    if c_sos is not None:
        sos_c = np.ascontiguousarray(sos)
        dp = ctypes.POINTER(ctypes.c_double)

        def c_run() -> Any:
            y = x.copy()
            z = np.zeros((sos.shape[0], 2, ch))
            c_sos(
                sos_c.ctypes.data_as(dp),
                ctypes.c_int(sos.shape[0]),
                y.ctypes.data_as(dp),
                ctypes.c_size_t(y.shape[0]),
                ctypes.c_size_t(ch),
                z.ctypes.data_as(dp),
            )
            return y

        rows["C -O3 via ctypes, channels innermost (prototype)"] = c_run
    out = []
    for name, fn in rows.items():
        t = best_of(fn, reps)
        out.append(
            {
                "channels": ch,
                "method": name,
                "us_per_chunk": t * 1e6,
                "core_pct_30k": t * 100 * 100,
                "max_abs_err_uV": float(np.max(np.abs(fn() - ref_y))),
            }
        )
    return out


def _alt_chain_split(reps: int, rng: np.random.Generator) -> list[dict[str, Any]]:
    from brainos.processing import ProcessingSpec, SignalChain
    from brainos.processing.stages import common_average_reference

    ch = 1024
    chain = SignalChain(ProcessingSpec(preset="spikeband_threshold"), FS_RAW, ch, "uV")
    x = rng.standard_normal((300, ch)) * 10
    for _ in range(110):
        chain.push(x)
    filt = chain.pre[0]
    y = filt.process(x)
    tc = chain.tc
    assert tc is not None
    parts = {
        "bandpass (scipy sosfilt)": best_of(lambda: filt.process(x), reps),
        "common average reference": best_of(lambda: common_average_reference(y), reps),
        "threshold crossings + binning": best_of(lambda: tc.process(y), reps),
        "whole SignalChain.push": best_of(lambda: chain.push(x), reps),
    }
    return [{"stage": k, "us_per_chunk": v * 1e6} for k, v in parts.items()]


def _alt_deflate(ch: int, n: int, reps: int, rng: np.random.Generator) -> dict[str, Any]:
    """CPU cost of WebSocket permessage-deflate on one raw frame's JSON, as uvicorn's
    websockets server applies it by default (zlib defaults, 15-bit window, context kept)."""
    import zlib

    a = (rng.standard_normal((ch, n)) * 10).astype(np.float32).astype(np.float64)
    text = (json.dumps(a.tolist()) + " ").encode()  # size/shape like the frame's JSON text
    comp = zlib.compressobj(-1, zlib.DEFLATED, -15)
    out = b""

    def deflate() -> None:
        nonlocal out
        out = comp.compress(text) + comp.flush(zlib.Z_SYNC_FLUSH)

    t = best_of(deflate, reps)
    return {
        "channels": ch,
        "samples": n,
        "json_kb": len(text) / 1e3,
        "compressed_kb": len(out) / 1e3,
        "ms_per_frame": t * 1e3,
        "mb_per_s": len(text) / t / 1e6,
    }


def section_alternatives(quick: bool) -> dict[str, Any]:
    reps = 3 if quick else 7
    rng = np.random.default_rng(0)
    out: dict[str, Any] = {"json": [], "validate": [], "sos": [], "chain_split": []}
    for ch in (64, 1024):
        out["json"] += _alt_json(ch, reps, rng)
        out["validate"] += _alt_validate(ch, reps, rng)
    tmp = Path(tempfile.mkdtemp())
    c_sos, nb_sos = _build_c(tmp), _numba_sos()
    for ch in (256, 1024, 4096):
        out["sos"] += _alt_sos(ch, reps, rng, c_sos, nb_sos)
    shutil.rmtree(tmp, ignore_errors=True)
    out["chain_split"] = _alt_chain_split(reps, rng)
    out["deflate"] = [_alt_deflate(ch, n, reps, rng) for ch, n in ((64, 150), (256, 300))]
    return out


# ================================================================ processing throughput


def section_chain(quick: bool) -> list[dict[str, Any]]:
    from brainos.processing import ProcessingSpec, SignalChain

    rng = np.random.default_rng(0)
    rows = []
    configs = [
        ("spikeband_threshold", FS_RAW, 10.0, {}),
        ("ecog_high_gamma", 1000.0, 10.0, {}),
        ("band_power", 1000.0, 10.0, {"band_low_hz": 8, "band_high_hz": 30}),
    ]
    for preset, fs, chunk_ms, extra in configs:
        for ch in (64, 256, 1024, 2048, 4096):
            n = round(fs * chunk_ms / 1000)
            spec = ProcessingSpec(preset=preset, rms_window_s=0.2, **extra)  # type: ignore[arg-type]
            chain = SignalChain(spec, fs, ch, "uV")
            block = rng.standard_normal((n * 10, ch)) * 10
            warm = int(0.25 * fs / n) + 1
            for i in range(warm):
                chain.push(block[(i % 10) * n : (i % 10 + 1) * n])
            k = 0
            times = []
            budget = 0.6 if quick else 2.0
            t_end = time.perf_counter() + budget
            while time.perf_counter() < t_end or len(times) < 5:
                c = block[(k % 10) * n : (k % 10 + 1) * n]
                t0 = time.perf_counter()
                chain.push(c)
                times.append(time.perf_counter() - t0)
                k += 1
            med = float(np.median(times))
            rows.append(
                {
                    "preset": preset,
                    "fs": fs,
                    "channels": ch,
                    "chunk_samples": n,
                    "us_per_chunk_p50": med * 1e6,
                    "us_per_chunk_p99": pct(times, 99) * 1e6,
                    "core_pct": med / (chunk_ms / 1000) * 100,
                    "realtime_x": (chunk_ms / 1000) / med,
                }
            )
    return rows


# ======================================================================= live sections


async def section_raw(tmp: Path, seconds: float, quick: bool) -> list[dict[str, Any]]:
    rows = []
    for ch in (64, 256) if quick else (64, 256, 1024, 2048):
        r = await live_run(
            tmp,
            kind="raw",
            channels=ch,
            rate=FS_RAW,
            seconds=seconds,
            preset="spikeband_threshold",
            bin_ms=20.0,
            decoder=ch <= CONTRACT_MAX_FRAME_CHANNELS,
        )
        rows.append(r)
        print(_line("raw", r), flush=True)
    return rows


async def section_ecog(tmp: Path, seconds: float, quick: bool) -> list[dict[str, Any]]:
    rows = []
    for ch in (64, 256) if quick else (64, 256, 1024):
        r = await live_run(
            tmp,
            kind="raw",
            channels=ch,
            rate=1000.0,
            seconds=seconds,
            preset="ecog_high_gamma",
            bin_ms=50.0,
            decoder=False,
        )
        rows.append(r)
        print(_line("ecog", r), flush=True)
    return rows


async def section_counts(tmp: Path, seconds: float, quick: bool) -> list[dict[str, Any]]:
    rows = []
    for rate in (50.0, 100.0):
        for ch in (64, 1024, 4096) if quick else (64, 256, 1024, 2048, 4096):
            r = await live_run(
                tmp,
                kind="counts",
                channels=ch,
                rate=rate,
                seconds=seconds,
                preset="features_passthrough",
                bin_ms=1000.0 / rate,
                decoder=True,
            )
            rows.append(r)
            print(_line("counts", r), flush=True)
    return rows


async def section_multi(tmp: Path, seconds: float, quick: bool) -> dict[str, Any]:
    """(a) one source of three LSL streams (counts + behavior + markers): supported;
    (b) N independent runtime processes, each with its own source (one device per runtime)."""
    out: dict[str, Any] = {}
    out["one_source_three_streams"] = await live_run(
        tmp,
        kind="counts",
        channels=1024,
        rate=50.0,
        seconds=seconds,
        preset="features_passthrough",
        bin_ms=20.0,
        behavior=True,
    )
    print(_line("multi-streams", out["one_source_three_streams"]), flush=True)
    out["runtimes"] = []
    for n in (1, 2) if quick else (1, 2, 3):
        servers = [Server(tmp) for _ in range(n)]
        try:
            res = await asyncio.gather(
                *(
                    live_run(
                        tmp,
                        kind="raw",
                        channels=256,
                        rate=FS_RAW,
                        seconds=seconds,
                        preset="spikeband_threshold",
                        bin_ms=20.0,
                        server=s,
                    )
                    for s in servers
                )
            )
        finally:
            for s in servers:
                s.stop()
        out["runtimes"].append({"n": n, "runs": res})
        print(f"multi runtimes={n}: " + " | ".join(_line("", r) for r in res), flush=True)
    return out


async def section_consumers(tmp: Path, seconds: float, quick: bool) -> list[dict[str, Any]]:
    """A raw-signal viewer (SDK client requesting ``recording``) next to the command app, and
    a frozen client that never reads. Does the pipeline stay loss-free?"""
    rows = []
    for ch in (64, 256) if quick else (64, 256, 1024):
        r = await live_run(
            tmp,
            kind="raw",
            channels=ch,
            rate=FS_RAW,
            seconds=seconds,
            preset="spikeband_threshold",
            bin_ms=20.0,
            raw_consumer=True,
        )
        r["scenario"] = "raw viewer"
        rows.append(r)
        print(_line("viewer", r), flush=True)
    r = await live_run(
        tmp,
        kind="raw",
        channels=256,
        rate=FS_RAW,
        seconds=seconds,
        preset="spikeband_threshold",
        bin_ms=20.0,
        stalled_consumer=True,
    )
    r["scenario"] = "frozen client"
    rows.append(r)
    print(_line("frozen", r), flush=True)
    return rows


async def section_recovery(tmp: Path, quick: bool) -> list[dict[str, Any]]:
    from brainos.sdk import RuntimeClient

    rows = []
    for ch in (256,) if quick else (256, 1024):
        srv = Server(tmp)
        sid = f"bench-scale-recover-{ch}-{srv.port}"
        pub = spawn_publisher("_pub-raw", ch, FS_RAW, sid)
        app = App(srv.base, "bench-app", ["neural_features"], [])
        try:
            await srv.ready()
            srv.watch_rss(RSS_CAP_MB)
            async with RuntimeClient(srv.base, timeout=30) as rc:
                await app.start()  # before the source: a saturated runtime cannot accept it
                app.arm()
                did = await open_lsl_source(rc, sid)
                await rc.connect(did)
                await rc.start_pipeline("spikeband_threshold")
                await asyncio.sleep(4.0)
                if not app.bins:
                    raise RuntimeError("no features reached the app before the kill")
                kill(pub)
                t_kill = time.monotonic()
                while (await rc.runtime()).state != "reconnecting":
                    if time.monotonic() - t_kill > 15:
                        break
                    await asyncio.sleep(0.01)
                detect = time.monotonic() - t_kill
                await asyncio.sleep(max(0.0, 1.0 - detect))
                pub = spawn_publisher("_pub-raw", ch, FS_RAW, sid)
                t_restart = time.monotonic()
                n0 = len(app.bins)
                while time.monotonic() - t_restart < 30:
                    st = (await rc.runtime()).state
                    if st == "streaming" and len(app.bins) > n0:
                        break
                    await asyncio.sleep(0.01)
                recover = time.monotonic() - t_restart
                pipe = await rc.pipeline()
                rows.append(
                    {
                        "channels": ch,
                        "detect_s": detect,
                        "recover_s": recover,
                        "state": (await rc.runtime()).state,
                        "pipeline_running": pipe["running"],
                        "reconnects": (await rc.diagnostics())["counters"]["reconnect_successes"],
                    }
                )
                print(f"recovery {rows[-1]}", flush=True)
        except Exception as exc:  # recorded, not fatal
            err = f"{type(exc).__name__}: {exc}"[:200]
            if srv.rss_killed_after_s is not None:
                err = f"runtime RSS exceeded {RSS_CAP_MB:.0f} MB; stopped by the benchmark"
            rows.append({"channels": ch, "error": err})
            print(f"recovery ch={ch} ERROR {err}", flush=True)
        finally:
            await app.stop()
            kill(pub)
            srv.stop()
    return rows


async def section_soak(tmp: Path, seconds: float, channels: list[int]) -> list[dict[str, Any]]:
    rows = []
    for ch in channels:
        r = await live_run(
            tmp,
            kind="raw",
            channels=ch,
            rate=FS_RAW,
            seconds=seconds,
            preset="spikeband_threshold",
            bin_ms=20.0,
            rss_every_s=10.0,
        )
        print(_line("soak", r), flush=True)
        rows.append(r)
    return rows


def _line(tag: str, r: dict[str, Any]) -> str:
    if "error" in r:
        return f"{tag} ch={r.get('channels')} ERROR {r['error']}"
    a = r["app"]
    return (
        f"{tag} ch={r['channels']} rate={r['rate']:g} "
        f"samples/s/ch={f(r['samples_per_s_per_ch'], '.0f')} gaps={r['gaps']} "
        f"feat/s={r['features_per_s']:.1f} miss={a['missing_bins']} "
        f"feat p50/p99={f(a['feat']['p50'])}/{f(a['feat']['p99'])} "
        f"cmd p50/p99={f(a['cmd']['p50'])}/{f(a['cmd']['p99'])} drop={r['dropped_inputs']} "
        f"cpu rt={f(r['cpu_pct']['runtime'], '.0f')}% pub={f(r['cpu_pct']['publisher'], '.0f')}% "
        f"rss={f(r['rss_mb']['runtime'], '.0f')}MB verr={r['validation_errors']} "
        f"rest={'ok' if r['rest_responsive'] else 'UNRESPONSIVE'} load={r['loadavg']}"
    )


# ============================================================================ markdown


def _cmd(command: str) -> str:
    """The command as run, with absolute output paths shown by file name only."""
    return " ".join(Path(t).name if t.startswith("/") else t for t in command.split())


def f(v: Any, spec: str = ".1f") -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return format(v, spec)


def render(res: dict[str, Any]) -> str:
    L: list[str] = []
    p = L.append
    m = res["machine"]
    p("# BrainOS performance at scale (Milestone 5, workstream E)\n")
    p(
        "> Generated by `scripts/bench_scale.py` on the machine below; every number was "
        "measured by the run(s) listed. **All streams are benchmark-generated synthetic data** "
        f"(declared synthetic, origin `{ORIGIN}`) and **all decoders are random-weight "
        "decoders generated by the benchmark** (not trained; outputs meaningless; no decoding "
        "quality is measured). No hardware. Re-run: `make bench-scale`.\n"
    )
    if res.get("runs"):
        p("Assembled from these runs of the script (later runs supply the listed sections):\n")
        for run in res["runs"]:
            p(
                f"- {run['started']}: `{_cmd(run['command'])}` (load {run['load_start']} -> "
                f"{run['load_end']}): {', '.join(run['sections'])}"
            )
        p("")
    else:
        p(f"Measured {res['started']} with `{_cmd(res['command'])}`.\n")
    p("| | |\n|---|---|")
    for k in (
        "cpu",
        "machine",
        "platform",
        "cpu_count",
        "mem_gb",
        "python",
        "numpy",
        "scipy",
    ):
        if k in m:
            p(f"| {k} | {m[k]} |")
    for k in ("pydantic", "pylsl", "liblsl", "orjson", "numba"):
        if k in m:
            p(f"| {k} | {m[k]} |")
    p(f"| load average at start / end | {res['load_start']} / {res.get('load_end', '?')} |")
    p("")
    p(
        "Processes in the live sections: LSL publisher (acquisition) · runtime server "
        "(`python -m brainos.server`: adapter, runtime, pipeline, decoder, router, WebSocket) · "
        "SDK app (this script, Python SDK over the WebSocket). CPU = % of one core over the "
        "measurement window; RSS at the end of it. Latencies: see the script docstring "
        "(LSL clock = host monotonic clock in every process).\n"
    )
    if "micro" in res:
        p("## 1. Cost of the raw data path per 10 ms chunk (in-process, real code paths)\n")
        p(
            "One chunk of 300 samples (10 ms at 30 kHz) of float32 LSL data, as the LSL "
            "adapter turns it into `recording.frame` events (one, or several where the frame "
            "size cap applies). *normalize* = LSL adapter `normalize`; *ingest* = runtime "
            "stamp + validate + publish with no subscriber; *ingest + send* = the same plus "
            "one WebSocket subscriber granted `recording` dequeuing the frame text; *process* "
            "= pipeline (`spikeband_threshold`). % core = cost at 100 chunks/s (30 kHz).\n"
        )
        p(
            "| channels | frames · JSON MB per chunk | normalize µs (ns/value, % core) "
            "| ingest µs (…) | ingest + send µs (…) | process µs (…) |"
        )
        p("|---:|---:|---:|---:|---:|---:|")
        for r in res["micro"]:
            cells = [
                f"{r[k + '_us']:,.0f} ({r[k + '_ns_per_value']:.1f}, {r[k + '_core_pct']:.0f}%)"
                for k in ("normalize", "ingest", "ingest_send", "process")
            ]
            p(
                f"| {r['channels']} | {r.get('frames', 1)} · {r['json_bytes'] / 1e6:.2f} | "
                + " | ".join(cells)
                + " |"
            )
        p("")
    if "alternatives" in res:
        alt = res["alternatives"]
        p("## 2. Alternatives, head to head (with correctness checks)\n")
        p("### 2.1 JSON encoding of `samples` (channels x 300 float64 from float32 data)\n")
        p("| channels | method | ns/value | byte-identical to pydantic |\n|---:|---|---:|---|")
        for r in alt["json"]:
            p(
                f"| {r['channels']} | {r['method']} | {r['ns_per_value']:.1f} "
                f"| {'yes' if r['byte_identical'] else 'NO'} |"
            )
        p("\n### 2.2 Validation / conversion of `samples`\n")
        p("| channels | method | ns/value |\n|---:|---|---:|")
        for r in alt["validate"]:
            p(f"| {r['channels']} | {r['method']} | {r['ns_per_value']:.2f} |")
        p("\n### 2.3 Spike-band SOS filter (4th-order Butterworth 250-5000 Hz, 300 samples)\n")
        p(
            "Native rows are prototypes compiled by the benchmark (not shipped). Error = max "
            "|y - scipy| over the chunk.\n"
        )
        p(
            "| channels | method | µs/chunk | % core at 30 kHz | max abs error (µV) |\n"
            "|---:|---|---:|---:|---:|"
        )
        for r in alt["sos"]:
            p(
                f"| {r['channels']} | {r['method']} | {r['us_per_chunk']:,.0f} "
                f"| {r['core_pct_30k']:.1f} | {r['max_abs_err_uV']:.2e} |"
            )
        p("\n### 2.4 Where `SignalChain.push` time goes (spikeband, 1024 ch, 300 samples)\n")
        p("| stage | µs/chunk |\n|---|---:|")
        for r in alt["chain_split"]:
            p(f"| {r['stage']} | {r['us_per_chunk']:,.0f} |")
        if alt.get("deflate"):
            p("\n### 2.5 WebSocket permessage-deflate on raw-frame JSON (uvicorn's default)\n")
            p(
                "| channels x samples | JSON KB | deflated KB | ms per frame | MB/s |\n"
                "|---|---:|---:|---:|---:|"
            )
            for r in alt["deflate"]:
                p(
                    f"| {r['channels']} x {r['samples']} | {r['json_kb']:,.0f} "
                    f"| {r['compressed_kb']:,.0f} | {r['ms_per_frame']:.1f} | {r['mb_per_s']:.0f} |"
                )
        p("")
    if "chain" in res:
        p("## 3. Processing throughput (SignalChain alone, 10 ms chunks, one core)\n")
        p(
            "The DSP stages only (no runtime, no envelopes), synthetic Gaussian input. "
            "Real-time factor = seconds of data processed per second of CPU.\n"
        )
        p(
            "| preset | rate | channels | µs/chunk p50 / p99 | % of one core | real-time x |\n"
            "|---|---:|---:|---:|---:|---:|"
        )
        for r in res["chain"]:
            p(
                f"| {r['preset']} | {r['fs']:g} Hz | {r['channels']} | "
                f"{r['us_per_chunk_p50']:,.0f} / {r['us_per_chunk_p99']:,.0f} "
                f"| {r['core_pct']:.1f} | {r['realtime_x']:.1f} |"
            )
        p("")
    live_hdr = (
        "| channels | samples/s/ch | gaps / missing | frames/s · invalid | features/s (expected) "
        "· missing bins | feature bin->app p50 / p95 / p99 / p99.9 / max ms | command "
        "bin->app p50 / p99 / max ms | jitter sd / p99 ms | pipeline µs/input p50 / p99 "
        "| dropped inputs | CPU % pub / runtime / app | RSS MB runtime |"
    )
    live_sep = "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    if "raw" in res:
        p("## 4. Channel scaling, raw broadband 30 kHz -> spikeband -> decoder -> router -> app\n")
        p(
            "Synthetic float32 LSL stream (10 ms chunks) -> runtime -> `spikeband_threshold` "
            "(20 ms bins) -> random-weight ridge decoder -> command router -> authorized SDK "
            f"app. Contract 1.4 limits `recording.frame` to {CONTRACT_MAX_FRAME_CHANNELS} "
            "channels: rows above that show what the runtime does with such a stream.\n"
        )
        p(live_hdr)
        p(live_sep)
        for r in res["raw"]:
            p(_live_row(r))
        p("")
    if "ecog" in res:
        p("## 5. Channel scaling, 1 kHz (ECoG-rate) -> `ecog_high_gamma` (50 ms bins)\n")
        p(
            "Same synthetic generator at 1 kHz (not ECoG; a rate/size test). No decoder. "
            "The SDK app subscribes to `neural_features` (features.vector).\n"
        )
        p(live_hdr)
        p(live_sep)
        for r in res["ecog"]:
            p(_live_row(r))
        p("")
    if "counts" in res:
        p("## 6. Spike-count features over LSL (50 / 100 Hz bins) -> decoder -> router -> app\n")
        p(
            "Synthetic Poisson counts (type `SpikeCounts`, int16) -> `features_passthrough` "
            "-> random-weight ridge decoder -> command router -> authorized SDK app.\n"
        )
        p("| bin rate " + live_hdr)
        p("|---:" + live_sep)
        for r in res["counts"]:
            p(f"| {r['rate']:g} Hz " + _live_row(r))
        p("")
    if "multi" in res:
        mu = res["multi"]
        p("## 7. Concurrent acquisition streams\n")
        p(
            "The runtime connects **one device at a time** (`Runtime` holds one adapter). "
            "(a) One LSL source made of three streams (1024-ch counts at 50 Hz + 2-D behavior + "
            "markers), which the runtime supports. (b) N independent runtime **processes**, "
            "each with its own publisher (256 ch at 30 kHz, spikeband + decoder + router + app), "
            f"on this {res['machine'].get('cpu_count')}-CPU machine.\n"
        )
        p(live_hdr)
        p(live_sep)
        p(_live_row(mu["one_source_three_streams"]))
        p("")
        p(
            "| runtimes | per runtime: samples/s/ch · gaps · missing bins · feature p50 / p99 ms "
            "· command p99 ms · runtime CPU % |\n|---:|---|"
        )
        for g in mu["runtimes"]:
            cells = []
            for r in g["runs"]:
                if "error" in r:
                    cells.append(f"error: {r['error']}")
                    continue
                a = r["app"]
                cells.append(
                    f"{r['samples_per_s_per_ch']:,.0f} · {r['gaps']} · {a['missing_bins']} · "
                    f"{f(a['feat']['p50'])} / {f(a['feat']['p99'])} · {f(a['cmd']['p99'])} · "
                    f"{f(r['cpu_pct']['runtime'], '.0f')}"
                )
            p(f"| {g['n']} | " + "<br>".join(cells) + " |")
        p("")
    if "consumers" in res:
        p("## 8. Raw-signal viewers and frozen clients (WebSocket fan-out)\n")
        p(
            "Next to the command app, a second SDK client requests `recording` (raw frames, as "
            "the operator console does), or a client completes the hello and then never reads. "
            "The question is whether acquisition, the pipeline and the command app stay "
            "loss-free.\n"
        )
        p(
            "| scenario | channels | viewer frames/s received · MB/s of samples · delivery "
            "gaps · disconnected | subscriber drops | app missing bins · command p99 ms "
            "| pipeline dropped inputs | acquisition gaps | CPU % runtime / viewer | RSS MB |\n"
            "|---|---:|---|---:|---:|---:|---:|---:|---:|"
        )
        for r in res["consumers"]:
            if "error" in r:
                p(f"| {r.get('scenario')} | {r['channels']} | error: {r['error']} |||||||")
                continue
            v = r.get("viewer")
            vtxt = (
                f"{v['frames_per_s']:.1f} · {v['mb_per_s']:.1f} · {v['delivery_gaps']} · "
                f"{v['closed'] or 'no'}"
                if v
                else "— (client never reads)"
            )
            a = r["app"]
            p(
                f"| {r['scenario']} | {r['channels']} | {vtxt} | {f(r['subscriber_drops'], 'd')} "
                f"| {a['missing_bins']} · {f(a['cmd']['p99'])} | {f(r['dropped_inputs'], 'd')} "
                f"| {f(r['gaps'], 'd')} | {f(r['cpu_pct']['runtime'], '.0f')} / "
                f"{f(r['cpu_pct'].get('viewer'), '.0f')} | {f(r['rss_mb']['runtime'], '.0f')} |"
            )
        p("")
    if "recovery" in res:
        p("## 9. Failure recovery under load\n")
        p(
            "Publisher process killed while streaming (spikeband pipeline running), restarted "
            "~1 s later with the same `source_id`. *Detect* = kill -> runtime `reconnecting`; "
            "*recover* = restart -> features reaching the app again (includes publisher "
            "start-up and LSL resolution).\n"
        )
        p(
            "| channels | detect s | recover s | final state | reconnects | pipeline survived |\n"
            "|---:|---:|---:|---|---:|---|"
        )
        for r in res["recovery"]:
            if "error" in r:
                p(f"| {r['channels']} | error: {r['error']} |||||")
                continue
            p(
                f"| {r['channels']} | {r['detect_s']:.2f} | {r['recover_s']:.2f} | {r['state']} "
                f"| {r['reconnects']} | {'yes' if r['pipeline_running'] else 'no'} |"
            )
        p("")
    if "soak" in res:
        runs = res["soak"] if isinstance(res["soak"], list) else [res["soak"]]
        p("## 10. Long sessions at 30 kHz, full chain (spikeband -> decoder -> router -> app)\n")
        p(
            "| channels | seconds | features (expected) | missing bins | gaps / missing samples "
            "| dropped inputs | errors | feature p50 / p99 / p99.9 / max ms "
            "| command p50 / p99 / p99.9 / max ms | runtime RSS MB first / last / max "
            "(peak) | RSS trend MB/min | runtime CPU % |\n"
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
        )
        for r in runs:
            if "error" in r:
                p(f"| {r['channels']} | error: {r['error']} |||||||||||")
                continue
            a = r["app"]
            tr = r.get("rss_trace") or []
            rss = [x[1] for x in tr]
            slope = np.polyfit([x[0] for x in tr], rss, 1)[0] * 60 if len(rss) > 2 else None
            p(
                f"| {r['channels']} | {r['seconds']:.0f} | {a['features']:,} "
                f"({r['seconds'] * 50:,.0f}) | {a['missing_bins']} "
                f"| {f(r['gaps'], 'd')} / {f(r['missing'], 'd')} | {f(r['dropped_inputs'], 'd')} "
                f"| {f(r['pipeline_errors'], 'd')} | {f(a['feat']['p50'])} / {f(a['feat']['p99'])} / "
                f"{f(a['feat']['p999'])} / {f(a['feat']['max'])} | {f(a['cmd']['p50'])} / "
                f"{f(a['cmd']['p99'])} / {f(a['cmd']['p999'])} / {f(a['cmd']['max'])} "
                f"| {f(rss[0] if rss else None, '.0f')} / {f(rss[-1] if rss else None, '.0f')} / "
                f"{f(max(rss) if rss else None, '.0f')} ({f(r['rss_mb']['runtime_peak'], '.0f')})"
                f" | {f(slope, '+.2f')} | {f(r['cpu_pct']['runtime'], '.0f')} |"
            )
        p("")
    p(
        "Notes: software measurements on one shared host (other work may have been running; see "
        "load average). They characterize BrainOS's software path only — not any amplifier, "
        "implant, network or closed-loop performance."
    )
    return "\n".join(L) + "\n"


def _live_row(r: dict[str, Any]) -> str:
    if "error" in r:
        return f"| {r['channels']} | error: {r['error']} |||||||||||"
    a = r["app"]
    c = r["cpu_pct"]
    proc = r["proc_us"] or {}
    fe, cm = a["feat"], a["cmd"]
    if cm["n"]:
        cmd = f"{f(cm['p50'])} / {f(cm['p99'])} / {f(cm['max'])}"
    else:
        cmd = "— (no decoder)" if r["preset"] != "spikeband_threshold" else "— (none received)"
    frames = (
        f"{f(r['frames_per_s'], '.0f')} · {f(r['validation_errors'], 'd')}"
        if r["kind"] == "raw"
        else "—"
    )
    rest = "" if r["rest_responsive"] else " (runtime REST unresponsive)"
    return (
        f"| {r['channels']} | {f(r['samples_per_s_per_ch'], ',.0f')}{rest} "
        f"| {f(r['gaps'], 'd')} / {f(r['missing'], 'd')} "
        f"| {frames} | {r['features_per_s']:.1f} ({r['expected_features_per_s']:g}) · "
        f"{a['missing_bins']} | {f(fe['p50'])} / {f(fe['p95'])} / {f(fe['p99'])} / "
        f"{f(fe['p999'])} / {f(fe['max'])} | {cmd} | {f(a['jitter_sd_ms'], '.2f')} / "
        f"{f(a['jitter_p99_ms'], '.2f')} | {f(proc.get('p50'), ',.0f')} / "
        f"{f(proc.get('p99'), ',.0f')} | {f(r['dropped_inputs'], 'd')} "
        f"| {f(c['publisher'], '.0f')} / {f(c['runtime'], '.0f')} / {f(c['app'], '.0f')} "
        f"| {f(r['rss_mb']['runtime'], '.0f')} |"
    )


# ================================================================ before/after compare


def _cell(r: dict[str, Any], key: str) -> str:
    """One live-run metric for the comparison table ("failed" for a failed run)."""
    if "error" in r:
        return "failed"
    a = r["app"]
    value = {
        "cpu": f(r["cpu_pct"]["runtime"], ".0f"),
        "samples": f(r["samples_per_s_per_ch"], ",.0f"),
        "features": f"{r['features_per_s']:.1f}",
        "missing": str(a["missing_bins"]),
        "feat": f(a["feat"]["p99"]),
        "cmd": f(a["cmd"]["p99"]),
        "dropped": f(r["dropped_inputs"], "d"),
        "subdrops": f(r.get("subscriber_drops"), "d"),
        "viewer": f(r.get("viewer", {}).get("frames_per_s"), ".1f") if r.get("viewer") else "—",
    }[key]
    return value


def compare(before: dict[str, Any], after: dict[str, Any]) -> str:
    """Markdown tables: the same sections from two saved runs (e.g. 6b82e05 vs m5-perf)."""
    L: list[str] = []
    p = L.append
    p(
        f"Before: {before['started']} (`{before.get('label') or 'before'}`); "
        f"after: {after['started']} (`{after.get('label') or 'after'}`).\n"
    )
    if "micro" in before and "micro" in after:
        p("Per 10 ms chunk of 30 kHz data (section 1 of the report):\n")
        p("| channels | stage | before µs | after µs | speed-up |\n|---:|---|---:|---:|---:|")
        for b, a in zip(before["micro"], after["micro"], strict=True):
            for k in ("normalize", "ingest", "ingest_send", "process"):
                p(
                    f"| {b['channels']} | {k.replace('_', ' + ')} | {b[k + '_us']:,.0f} "
                    f"| {a[k + '_us']:,.0f} | {b[k + '_us'] / a[k + '_us']:.1f}x |"
                )
            tb = b["normalize_us"] + b["ingest_us"] + b["process_us"]
            ta = a["normalize_us"] + a["ingest_us"] + a["process_us"]
            p(
                f"| {b['channels']} | **normalize + ingest + process** | {tb:,.0f} | {ta:,.0f} "
                f"| **{tb / ta:.1f}x** |"
            )
        p("")
    cols = [
        ("cpu", "runtime CPU %"),
        ("samples", "samples/s/ch"),
        ("features", "features/s at app"),
        ("missing", "missing bins"),
        ("feat", "feature p99 ms"),
        ("cmd", "command p99 ms"),
        ("dropped", "dropped inputs"),
    ]
    for sec, extra in (("raw", []), ("ecog", []), ("counts", []), ("consumers", ["viewer"])):
        if sec not in before or sec not in after:
            continue
        keys = cols + [(k, "viewer frames/s") for k in extra]
        p(f"**{sec}** (before → after)\n")
        p("| channels | rate | " + " | ".join(t for _, t in keys) + " |")
        p("|---:|---:|" + "---:|" * len(keys))
        for b, a in zip(before[sec], after[sec], strict=False):
            name = f"{b.get('scenario', '')} {b['channels']}".strip()
            cells = [f"{_cell(b, k)} → {_cell(a, k)}" for k, _ in keys]
            p(f"| {name} | {b['rate']:g} | " + " | ".join(cells) + " |")
        failures = [(b, a) for b, a in zip(before[sec], after[sec], strict=False) if "error" in b]
        for b, a in failures:
            after_txt = a.get("error", "ran")
            p(f"\n- before, {b['channels']} ch: {b['error']}; after: {after_txt}.")
        p("")
    if "recovery" in before and "recovery" in after:
        p("**recovery** (before → after)\n")
        for b, a in zip(before["recovery"], after["recovery"], strict=False):
            bt = b.get("error") or f"recovered in {b['recover_s']:.2f} s"
            at = a.get("error") or f"recovered in {a['recover_s']:.2f} s"
            p(f"- {b['channels']} ch: {bt} → {at}")
        p("")
    return "\n".join(L) + "\n"


def assemble(runs: list[dict[str, Any]]) -> dict[str, Any]:
    """One report from several saved runs: later runs replace whole sections; the header
    lists every run and the sections it supplied (nothing is averaged or edited)."""
    merged: dict[str, Any] = {k: v for k, v in runs[0].items() if k not in SECTIONS}
    supplied: dict[int, list[str]] = {}
    for i, run in enumerate(runs):
        for sec in SECTIONS:
            if sec in run:
                merged[sec] = run[sec]
                for j in supplied:
                    if sec in supplied[j]:
                        supplied[j].remove(sec)
                supplied.setdefault(i, []).append(sec)
    merged["runs"] = [
        {
            "started": run["started"],
            "command": run["command"],
            "load_start": run.get("load_start"),
            "load_end": run.get("load_end"),
            "sections": supplied.get(i, []),
        }
        for i, run in enumerate(runs)
        if supplied.get(i)
    ]
    merged["load_start"] = runs[0].get("load_start")
    merged["load_end"] = runs[-1].get("load_end")
    return merged


# ================================================================================ main


def _run_sections(args: argparse.Namespace, res: dict[str, Any]) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="brainos-bench-scale-"))
    secs = args.sections.split(",") if args.sections else list(SECTIONS)
    s = args.seconds
    try:
        for name in secs:
            t0 = time.monotonic()
            print(f"== {name}", flush=True)
            if name == "micro":
                res[name] = section_micro(args.quick)
            elif name == "alternatives":
                res[name] = section_alternatives(args.quick)
            elif name == "chain":
                res[name] = section_chain(args.quick)
            elif name == "raw":
                res[name] = asyncio.run(section_raw(tmp, s, args.quick))
            elif name == "ecog":
                res[name] = asyncio.run(section_ecog(tmp, s, args.quick))
            elif name == "counts":
                res[name] = asyncio.run(section_counts(tmp, s, args.quick))
            elif name == "multi":
                res[name] = asyncio.run(section_multi(tmp, s, args.quick))
            elif name == "consumers":
                res[name] = asyncio.run(section_consumers(tmp, s, args.quick))
            elif name == "recovery":
                res[name] = asyncio.run(section_recovery(tmp, args.quick))
            elif name == "soak":
                chans = [int(c) for c in args.soak_channels.split(",")]
                res[name] = asyncio.run(section_soak(tmp, args.soak, chans))
            else:
                raise SystemExit(f"unknown section {name}")
            print(f"   {name}: {time.monotonic() - t0:.0f} s", flush=True)
    finally:
        kill_all()
        shutil.rmtree(tmp, ignore_errors=True)


def main() -> None:
    global RSS_CAP_MB
    if len(sys.argv) > 1 and sys.argv[1] == "_viewer":
        ap = argparse.ArgumentParser()
        ap.add_argument("kind")
        ap.add_argument("--base", required=True)
        ap.add_argument("--out", type=Path, required=True)
        a = ap.parse_args()
        run_viewer(a.base, a.out)
        return
    if len(sys.argv) > 1 and sys.argv[1] in ("_pub-raw", "_pub-counts"):
        ap = argparse.ArgumentParser()
        ap.add_argument("kind")
        ap.add_argument("--channels", type=int, required=True)
        ap.add_argument("--rate", type=float, required=True)
        ap.add_argument("--source-id", required=True)
        ap.add_argument("--chunk-ms", type=float, default=10.0)
        ap.add_argument("--behavior", action="store_true")
        a = ap.parse_args()
        if a.kind == "_pub-raw":
            publish_raw(a.channels, a.rate, a.source_id, a.chunk_ms)
        else:
            publish_counts(a.channels, a.rate, a.source_id, a.behavior)
        return
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--seconds", type=float, default=10.0, help="measurement window per cell")
    ap.add_argument("--soak", type=float, default=600.0, help="long-session duration (s)")
    ap.add_argument("--soak-channels", default="256", help="comma list of channel counts")
    ap.add_argument("--quick", action="store_true", help="fewer sizes, shorter runs")
    ap.add_argument("--sections", default=None, help=f"comma list of {','.join(SECTIONS)}")
    ap.add_argument("--json", type=Path, default=None, help="write raw results as JSON")
    ap.add_argument("--write", type=Path, default=None, help="write the markdown report")
    ap.add_argument("--label", default=None, help="label stored in the JSON (e.g. a commit)")
    ap.add_argument("--rss-cap-mb", type=float, default=2500.0, help="stop runtimes above")
    ap.add_argument("--compare", nargs=2, type=Path, metavar=("BEFORE", "AFTER"))
    ap.add_argument("--assemble", nargs="+", type=Path, help="render saved runs (later win)")
    args = ap.parse_args()
    RSS_CAP_MB = args.rss_cap_mb
    if args.compare:
        b, a = (json.loads(p.read_text()) for p in args.compare)
        print(compare(b, a))
        return
    if args.assemble:
        merged = assemble([json.loads(p.read_text()) for p in args.assemble])
        if args.json:
            args.json.write_text(json.dumps(merged, indent=1, default=str))
        text = render(merged)
        print(text)
        if args.write:
            args.write.write_text(text)
        return
    res: dict[str, Any] = {
        "started": time.strftime("%Y-%m-%d %H:%M %Z"),
        "command": "python scripts/bench_scale.py " + " ".join(sys.argv[1:]),
        "label": args.label,
        "machine": machine(),
        "load_start": loadavg(),
    }
    try:
        _run_sections(args, res)
    finally:
        res["load_end"] = loadavg()
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(res, indent=1, default=str))
    text = render(res)
    print(text)
    if args.write:
        args.write.write_text(text)
        print(f"wrote {args.write}")


if __name__ == "__main__":
    main()
