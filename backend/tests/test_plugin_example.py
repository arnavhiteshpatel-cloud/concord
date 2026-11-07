"""End to end with the example third-party adapter (installed editable, entry point
``example-mi-eeg``): discovered by a real server at startup, listed via REST, configured,
connected, streamed over the WebSocket, recorded and replayed, and reconnected after its
host process is killed. Also: the generator's ERD effect, and the IPC throughput script.
"""

from __future__ import annotations

import asyncio
import itertools
import os
import signal
import subprocess
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest
import uvicorn
from brainos_example_adapter.generator import (
    BLOCK,
    GeneratorConfig,
    MotorImageryGenerator,
)

from brainos.contracts.events import EventEnvelope
from brainos.sdk import BrainOSError, EventStream, RuntimeClient, is_event
from brainos.server import create_app

from .conftest import _free_port, make_settings

PLUGIN = "example-mi-eeg"
DEVICE = "plugin:example-mi-eeg:mi-eeg"
OPTIONS = {"seed": 7, "montage": "16", "cue_duration_s": 2.0, "effect_size": 0.5}
LABELS_16 = ["Fp1", "Fp2", "F3", "Fz", "F4", "T7", "C3", "Cz", "C4", "T8", "P3", "Pz", "P4", "O1", "Oz", "O2"]  # fmt: skip
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def server(tmp_path: Path) -> Iterator[str]:
    port = _free_port()
    settings = make_settings(tmp_path, port=port, discover_plugins=True)
    server = uvicorn.Server(
        uvicorn.Config(create_app(settings), host="127.0.0.1", port=port, log_level="warning")
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            if httpx.get(base + "/api/v1/health", timeout=0.5).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    yield base
    server.should_exit = True
    thread.join(timeout=15)


def generated(cfg: GeneratorConfig, n_samples: int) -> tuple[np.ndarray, np.ndarray, list[Any]]:  # type: ignore[type-arg]
    gen = MotorImageryGenerator(cfg)
    blocks = [gen.next_block() for _ in range(n_samples // BLOCK + 1)]
    eeg = np.concatenate([b.eeg for b in blocks])
    cue = np.concatenate([b.cue for b in blocks])
    return eeg, cue, [m for b in blocks for m in b.markers]


async def collect(stream: EventStream, seconds: float) -> list[EventEnvelope]:
    out: list[EventEnvelope] = []

    async def run() -> None:
        async for item in stream:
            if is_event(item):
                out.append(item)

    with pytest.raises(TimeoutError):
        await asyncio.wait_for(run(), seconds)
    return out


def check_bit_exact(evs: list[EventEnvelope], cfg: GeneratorConfig) -> int:
    frames = [e for e in evs if e.event_type == "recording.frame"]
    assert frames, "no frames"
    end = max(f.payload.first_sample_index + len(f.payload.samples[0]) for f in frames)  # type: ignore[union-attr]
    eeg, cue, markers = generated(cfg, end)
    for f in frames:
        p = f.payload
        a = p.first_sample_index  # type: ignore[union-attr]
        got = np.array(p.samples).T  # type: ignore[union-attr]
        assert np.array_equal(got, eeg[a : a + got.shape[0]].astype(np.float64)), a
        assert p.unit == "uV" and p.channel_count == 16  # type: ignore[union-attr]
    t = [(f.payload.first_sample_index, f.device_timestamp_ns) for f in frames]  # type: ignore[union-attr]
    for (i0, t0), (i1, t1) in itertools.pairwise(t):
        assert t0 is not None and t1 is not None
        assert abs((t1 - t0) - (i1 - i0) / 250.0 * 1e9) < 1_000  # one clock, 1 µs
    beh = [e for e in evs if e.event_type == "behavior.sample"]
    assert beh
    for b in beh:
        p = b.payload
        assert p.quantity == "class" and p.dims == ["cue_class"]  # type: ignore[union-attr]
        assert p.values == [float(cue[p.sample_index * 5])]  # type: ignore[union-attr]
    labels = {m[1] for m in markers if m[0] < end}
    got_labels = {e.payload.label for e in evs if e.event_type == "recording.annotation"}  # type: ignore[union-attr]
    assert got_labels and got_labels <= labels
    return len(frames)


async def test_example_adapter_end_to_end(server: str, tmp_path: Path) -> None:
    async with RuntimeClient(server) as c:
        # startup discovery runs in the background
        for _ in range(200):
            st = await c.plugins()
            if st["discovered_at_ns"]:
                break
            await asyncio.sleep(0.05)
        st = await c.discover_plugins(0.5)
        plugin = next(p for p in st["plugins"] if p["name"] == PLUGIN)
        assert plugin["status"] == "compatible" and plugin["reason"] is None
        assert plugin["package"] == "brainos-example-adapter" and plugin["version"] == "0.1.0"
        assert plugin["roles"] == ["behavior", "markers", "signal"]
        assert {o["name"] for o in plugin["options"]} == {
            "seed",
            "montage",
            "cue_duration_s",
            "effect_size",
        }
        assert (
            plugin["devices"][0]["device_id"] == DEVICE and not plugin["devices"][0]["configured"]
        )

        with pytest.raises(BrainOSError) as e:
            await c.configure_plugin(PLUGIN, "mi-eeg", {"montage": "32"})
        assert e.value.status == 400 and "montage" in e.value.message
        with pytest.raises(BrainOSError) as e:
            await c.configure_plugin(PLUGIN, "mi-eeg", {"effect_size": 3})
        assert e.value.status == 502 and "effect_size" in e.value.message  # plugin's own check

        desc = await c.configure_plugin(PLUGIN, "mi-eeg", OPTIONS)
        assert desc.device_id == DEVICE and desc.kind == "simulated" and desc.synthetic
        assert desc.modality == "eeg" and desc.invasive is False
        integ = desc.integration
        assert integ is not None and integ.kind == "plugin" and integ.isolated
        assert (integ.package, integ.version, integ.api_version) == (
            "brainos-example-adapter",
            "0.1.0",
            "1.0",
        )
        rec = next(x for x in desc.capabilities if x.capability == "recording")
        assert rec.params["channel_labels"] == LABELS_16 and rec.params["unit"] == "uV"
        assert {x.capability for x in desc.capabilities} == {
            "recording",
            "behavior",
            "device_status",
        }
        assert DEVICE in {d.device_id for d in await c.devices()}
        idle_meta = await c._call("GET", f"/devices/{DEVICE}/source")
        assert idle_meta["plugin"]["package"] == "brainos-example-adapter"

        # --- connect and stream through the runtime -> WebSocket -> SDK (validated envelopes)
        stream = await EventStream.connect(
            app_id="plugin-e2e",
            app_name="plugin e2e",
            optional=["recording", "behavior"],
            base_url=server,
        )
        async with stream:
            await c.connect(DEVICE)
            evs = await collect(stream, 3.0)
        cfg = GeneratorConfig(**OPTIONS)  # type: ignore[arg-type]
        n_frames = check_bit_exact(evs, cfg)
        assert n_frames >= 15
        assert all(
            e.provenance.adapter == "brainos-example-adapter@0.1.0"
            for e in evs
            if e.event_type != "device.status"
        )
        assert all(e.provenance.synthetic for e in evs)

        # --- record, then replay the recording
        name = await c.start_recording("mi-plugin-test")
        await asyncio.sleep(1.5)
        info = await c.stop_recording()
        assert info["events"] > 10
        stream = await EventStream.connect(
            app_id="plugin-e2e-replay",
            app_name="replay",
            optional=["recording", "behavior"],
            base_url=server,
        )
        async with stream:
            await c.switch(f"replay:{name}")
            replayed = await collect(stream, 1.5)
        frames = [e for e in replayed if e.event_type == "recording.frame"]
        assert frames and all(e.provenance.replayed for e in frames)
        check_bit_exact(replayed, cfg)

        # --- the processing pipeline runs on the plugin's signal like on any source
        await c.switch(DEVICE)
        # 250 Hz: the bin must be a whole number of samples (the 50 ms default is not)
        status = await c.start_pipeline(
            "band_power", bin_ms=100, band_low_hz=8.0, band_high_hz=12.0
        )
        assert status["running"] and status["output"]["channel_count"] == 16
        for _ in range(100):
            status = await c.pipeline()
            if status["counters"].get("features_out", 0) > 0:
                break
            await asyncio.sleep(0.05)
        assert status["counters"]["features_out"] > 0, status
        await c.stop_pipeline()

        # --- kill the plugin host: the runtime reconnects with a fresh process
        meta = await c._call("GET", f"/devices/{DEVICE}/source")
        pid = meta["host_pid"]
        assert pid and pid != os.getpid()
        os.kill(pid, signal.SIGKILL)
        for _ in range(200):
            d = await c.diagnostics()
            snap = await c.runtime()
            if d["counters"]["reconnect_successes"] >= 1 and snap.state == "streaming":
                break
            await asyncio.sleep(0.05)
        else:
            raise AssertionError(f"no reconnect: {d['counters']} {snap.state}")
        meta = await c._call("GET", f"/devices/{DEVICE}/source")
        assert meta["host_pid"] not in (None, pid)
        await c.disconnect()
        assert (await c._call("DELETE", f"/sources/{DEVICE}"))["removed"] is True


async def test_rest_errors(server: str) -> None:
    async with RuntimeClient(server) as c:
        await c.discover_plugins(0.2)
        with pytest.raises(BrainOSError) as e:
            await c.configure_plugin("no-such-plugin", "x")
        assert e.value.status == 404
        with pytest.raises(BrainOSError) as e:
            await c.configure_plugin(PLUGIN, "mi-eeg", {"unknown": 1})
        assert e.value.status == 400 and "unknown option" in e.value.message
        with pytest.raises(BrainOSError) as e:
            await c.connect("plugin:example-mi-eeg:not-configured")
        assert e.value.status == 404


def test_generator_mu_desynchronisation() -> None:
    """Imagined left -> lower 8-12 Hz power at C4 than at rest; right -> at C3."""
    cfg = GeneratorConfig(seed=3, montage="8", cue_duration_s=4.0, effect_size=0.5)
    gen = MotorImageryGenerator(cfg)
    eeg, cue, _ = generated(cfg, 250 * 4 * 40)
    labels = list(gen.labels)
    c3, c4 = labels.index("C3"), labels.index("C4")
    win = 250  # 1 s windows, skipping the first second of each cue (ERD onset)
    power: dict[tuple[int, int], list[float]] = {}
    for start in range(0, len(cue) - 4 * 250, 4 * 250):
        k = int(cue[start])
        seg = eeg[start + 250 : start + 4 * 250]
        for ch in (c3, c4):
            for w in range(0, len(seg) - win + 1, win):
                spec = np.abs(np.fft.rfft(seg[w : w + win, ch] * np.hanning(win))) ** 2
                f = np.fft.rfftfreq(win, 1 / 250)
                power.setdefault((k, ch), []).append(float(spec[(f >= 8) & (f <= 12)].sum()))
    mean = {key: float(np.mean(v)) for key, v in power.items()}
    assert mean[(1, c4)] < 0.6 * mean[(0, c4)]  # left imagery: C4 desynchronises
    assert mean[(2, c3)] < 0.6 * mean[(0, c3)]  # right imagery: C3 desynchronises
    assert mean[(1, c3)] > 0.8 * mean[(0, c3)]  # ipsilateral stays (mostly)
    assert set(np.unique(cue)) == {0, 1, 2}


def test_ipc_throughput_benchmark_runs() -> None:
    """64 ch x 30 kHz float32 through the real host; numbers are printed, not asserted."""
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "bench_plugins.py"), "--seconds", "0.4"],
        capture_output=True,
        text=True,
        timeout=180,
        check=True,
    )
    print(out.stdout)
    rows = [r for r in out.stdout.splitlines() if r.startswith("| ") and " ms) |" in r]
    assert len(rows) == 3 and all("| yes |" in r for r in rows)  # bit-exact in every cell
