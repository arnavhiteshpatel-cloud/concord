"""Milestone 4: established ecosystems through the plugin host and the unchanged runtime.

* BrainFlow (official ``BoardShim`` API, synthetic board) as an installed plugin.
* BCI2000 App Connector output, replayed from datagrams recorded from a real BCI2000 3.6
  build (``packages/brainos-bci2000/tests/fixtures``): processed control information only.

Both run in the plugin host (a separate process); neither yields an application command
by itself.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import socket
import threading
import time
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("brainflow")
pytest.importorskip("brainos_bci2000")

from brainos.contracts.events import EventEnvelope
from brainos.sdk import EventStream, RuntimeClient, is_event

from .test_plugin_example import server  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parents[2]
BCI_FIXTURE = ROOT / "packages/brainos-bci2000/tests/fixtures/bci2000_connector_output.json"


async def _wait_plugins(c: RuntimeClient) -> dict[str, Any]:
    for _ in range(300):
        st = await c.plugins()
        if st["discovered_at_ns"]:
            return st
        await asyncio.sleep(0.05)
    raise AssertionError("plugin discovery did not finish")


async def _collect(stream: EventStream, seconds: float) -> list[EventEnvelope]:
    out: list[EventEnvelope] = []

    async def run() -> None:
        async for item in stream:
            if is_event(item):
                out.append(item)

    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(run(), seconds)
    return out


def _by_name(st: dict[str, Any], name: str) -> dict[str, Any]:
    return next(p for p in st["plugins"] if p["name"] == name)


async def test_brainflow_synthetic_board_through_plugin_host(server: str) -> None:  # noqa: F811
    async with RuntimeClient(server) as c:
        st = await _wait_plugins(c)
        bf = _by_name(st, "brainflow")
        assert bf["status"] == "compatible", bf
        dev = await c.configure_plugin("brainflow", "synthetic", {})
        assert dev.integration is not None and dev.integration.ecosystem == "brainflow"
        assert dev.integration.isolated and dev.integration.kind == "plugin"
        assert dev.synthetic and dev.kind.value == "simulated"
        # BrainFlow's synthetic board lists the same rows as EEG, EMG, ECG and EOG:
        # the modality is ambiguous, so it is not declared (never guessed)
        assert dev.modality is None and dev.invasive is None
        async with await EventStream.connect(
            app_id="eco-test",
            app_name="eco",
            optional=["recording", "pointer_intent"],
            base_url=server,
        ) as stream:
            await c.connect(dev.device_id)
            evs = await _collect(stream, 3.0)
        await c.disconnect()
    frames = [e for e in evs if e.event_type == "recording.frame"]
    assert frames, "no frames from BrainFlow"
    exg = [f for f in frames if f.payload.channel_count == 16]  # type: ignore[union-attr]
    assert exg and all(f.payload.unit == "uV" for f in exg)  # type: ignore[union-attr]
    assert all(f.provenance.synthetic and f.provenance.kind.value == "raw_signal" for f in frames)
    assert all(f.provenance.origin == "brainflow:SYNTHETIC_BOARD" for f in frames)
    n = sum(len(f.payload.samples[0]) for f in exg)  # type: ignore[union-attr]
    span = (exg[-1].device_timestamp_ns or 0) - (exg[0].device_timestamp_ns or 0)
    assert span > 0 and 200 < n / (span / 1e9) < 300  # nominal 250 Hz, generous tolerance
    assert not [e for e in evs if e.event_type.startswith("intent.")]  # signal is not a command


def _replay_bci2000(port: int, stop: threading.Event) -> None:
    """Re-send the recorded BCI2000 datagrams with their original timing, looping (a run
    of ~2 s; the plugin learns its layout at configure time and again on connect)."""
    raw = json.loads(BCI_FIXTURE.read_text())["datagrams"]
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        while not stop.is_set():
            t0 = time.monotonic()
            for t, text in raw:
                if stop.is_set():
                    return
                delay = t0 + t - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                s.sendto(text.encode("ascii"), ("127.0.0.1", port))
            time.sleep(0.3)  # a short pause between runs, as between BCI2000 runs
    finally:
        s.close()


async def test_bci2000_app_connector_through_plugin_host(server: str) -> None:  # noqa: F811
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    stop = threading.Event()
    opts = {
        "port": port,
        "sampling_rate_hz": 256,
        "sample_block_size": 8,
        "declare_synthetic": True,
    }
    feeder = threading.Thread(target=_replay_bci2000, args=(port, stop), daemon=True)
    feeder.start()
    async with RuntimeClient(server) as c:
        st = await _wait_plugins(c)
        assert _by_name(st, "bci2000")["status"] == "compatible"
        dev = await c.configure_plugin("bci2000", "app-connector", opts)
        assert dev.integration is not None and dev.integration.ecosystem == "bci2000"
        # processed control information: no raw-signal capability is offered
        assert "recording" not in {
            c.capability.value for c in dev.capabilities if not c.params.get("annotations_only")
        }
        try:
            async with await EventStream.connect(
                app_id="eco-bci",
                app_name="eco",
                optional=[
                    "kinematic_intent",
                    "behavior",
                    "recording",
                    "pointer_intent",
                    "selection",
                ],
                base_url=server,
            ) as stream:
                await c.connect(dev.device_id)
                evs = await _collect(stream, 3.0)
            await c.disconnect()
        finally:
            stop.set()
            feeder.join(5)
    kin = [e for e in evs if e.event_type == "intent.kinematics"]
    assert kin, "no control-signal events"
    assert all(e.provenance.kind.value == "decoded_intent" for e in kin)
    assert all(
        e.provenance.model_id and "bci2000-control-signal" in e.provenance.model_id for e in kin
    )
    assert not [
        e for e in evs if e.event_type in ("intent.pointer", "intent.selection", "intent.text")
    ]
    assert not [e for e in evs if e.event_type == "recording.frame"]  # no raw signal claimed
