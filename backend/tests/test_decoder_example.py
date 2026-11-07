"""Milestone 5 (workstream A), end to end: the separately installed example decoder plugin
(``examples/decoders/brainos-example-decoder``, depends only on brainos-decoder-sdk) runs in an
isolated decoder host behind a real server; an SDK application receives its decoded actions
only after the operator authorizes it. Data: the in-test, declared-SYNTHETIC motor-imagery
source — this shows the integration path, not decoding of real EEG."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytest.importorskip("scipy")

from brainos.server import create_app

from .conftest import free_port, make_settings, serve
from .helpers import wait_for
from .mi_source import MotorImageryAdapter

PLUGIN = "example-mi-lateralization"
MODEL = "example-mi-lateralization-0.1.0"
WARMUP_BINS = 300  # 30 s of 100 ms bins
BAND = {"band_low_hz": 8.0, "band_high_hz": 13.0, "bin_ms": 100.0}
RULES = [
    {
        "output": "left",
        "threshold": 0.8,
        "hold_ms": 300,
        "refractory_ms": 1000,
        "action": "activate",
    },
    {
        "output": "right",
        "threshold": 0.8,
        "hold_ms": 300,
        "refractory_ms": 1000,
        "action": "cancel",
    },
]


def _installed() -> bool:
    return any(ep.name == PLUGIN for ep in metadata.entry_points(group="brainos.decoders"))


@pytest.fixture
def server(tmp_path: Path) -> Iterator[tuple[str, Any]]:
    assert _installed(), (
        "the example decoder plugin is not installed; `make setup` installs "
        "examples/decoders/brainos-example-decoder"
    )
    port = free_port()
    app = create_app(make_settings(tmp_path, port=port))
    rt = app.state.services.runtime
    kw = {"device_id": "test-mi", "speed": 20.0, "seed": 7}
    rt.registry.register(MotorImageryAdapter(**kw).descriptor, lambda: MotorImageryAdapter(**kw))
    for base in serve(app, port):
        yield base, rt


class App:
    """A plain SDK application: needs `selection`, records everything it receives."""

    def __init__(self, app_id: str, required: list[str]) -> None:
        self.app_id, self.required = app_id, required
        self.events: list[Any] = []
        self.stream: Any = None

    async def run(self, base: str) -> None:
        from brainos.sdk import EventStream, is_event

        self.stream = await EventStream.connect(
            app_id=self.app_id, app_name=self.app_id, required=self.required, base_url=base
        )
        async with self.stream as s:
            async for item in s:
                if is_event(item):
                    self.events.append(item)

    def of(self, event_type: str) -> list[Any]:
        return [e for e in self.events if e.event_type.value == event_type]


async def test_example_decoder_plugin_end_to_end(server: tuple[str, Any]) -> None:
    from brainos.sdk import BrainOSError, RuntimeClient

    base, _rt = server
    app = App("mi-menu", ["selection"])
    observer = App("observer", ["kinematic_intent", "behavior"])
    tasks = [asyncio.create_task(app.run(base)), asyncio.create_task(observer.run(base))]
    try:
        async with RuntimeClient(base) as op:
            disc = await op._call("POST", "/models/discover", {})
            assert disc["plugins"] >= 1 and disc["error"] is None
            await op.connect("test-mi")
            # preview: listed as a plugin, incompatible until channels are mapped by label
            preview = await op._call(
                "GET", "/models?preset=band_power&bin_ms=100&band_low_hz=8&band_high_hz=13"
            )
            info = next(m for m in preview if m["summary"]["model_id"] == MODEL)
            s = info["summary"]
            assert s["origin"] == "plugin" and s["execution"] == "isolated"
            assert s["family"] == "example-lateralization" and not s["participant_specific"]
            assert info["checked_against"] == "band_power preview"
            assert info["mapping_available"] and info["compatible"] is False
            assert any("enable explicit channel mapping" in e for e in info["errors"])
            with pytest.raises(BrainOSError) as exc:
                await op.start_pipeline("band_power", model_id=MODEL, **BAND)
            assert exc.value.code == "incompatible_decoder"
            assert "model expects 2 channels labelled C3, C4; source provides 8 channels" in str(
                exc.value
            )
            st = await op.start_pipeline(
                "band_power",
                model_id=MODEL,
                allow_channel_mapping=True,
                router={"enabled": True, "discrete": RULES},
                **BAND,
            )
            d = st["decoder"]
            assert d["origin"] == "plugin" and d["state"] == "ready" and d["pid"]
            assert st["channel_mapping"]
            assert any("mapped by label" in w for w in st["compatibility_warnings"])
            # default deny: decoded actions exist, the app is not authorized
            await wait_for(lambda: app.stream is not None, timeout=10)
            await wait_for(lambda: app.stream.negotiation.status.value == "suspended", timeout=10)
            assert [r.reason.value for r in app.stream.negotiation.rejected] == ["not_authorized"]
            await wait_for(lambda: len(observer.of("intent.kinematics")) >= 200, timeout=30)
            assert app.of("intent.selection") == []
            await op.authorize_app("mi-menu", ["selection"])
            await wait_for(lambda: len(app.of("intent.selection")) >= 3, timeout=60)
            sel = app.of("intent.selection")
            for e in sel:
                p = e.provenance
                assert p.kind.value == "decoded_intent" and p.model_id == MODEL
                assert p.model_origin == "brainos" and p.synthetic
            assert {e.payload.action for e in sel} <= {"activate", "cancel"}
            # 240 s of synthetic source time (20x real time) for the accuracy check below
            await wait_for(lambda: len(observer.of("intent.kinematics")) >= 2400, timeout=60)
            status = await op.pipeline()
            assert status["counters"]["decoder_failures"] == 0 and status["counters"]["errors"] == 0
            mon = status["decoder"]["monitor"]
            assert mon["labels"]["metric"] == "balanced_accuracy"
            await op.stop_pipeline()
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    # the decoded posteriors against the source's cue labels: above chance (synthetic data)
    kin = observer.of("intent.kinematics")
    warm = WARMUP_BINS  # the rule's running baselines settle first
    beh = {e.device_timestamp_ns: e.payload.values[0] for e in observer.of("behavior.sample")}
    pairs = []
    for e in kin[warm:]:
        ts = e.device_timestamp_ns
        near = min(beh, key=lambda t: abs(t - ts)) if beh else None
        if near is not None and abs(near - ts) <= 50_000_000:  # within half a 100 ms bin
            pairs.append((int(np.argmax(e.payload.values)), int(beh[near])))
    pred, true = np.array(pairs).T
    recalls = [float(np.mean(pred[true == c] == c)) for c in range(3) if np.any(true == c)]
    assert len(pairs) > 1500 and np.mean(recalls) > 0.40, (len(pairs), recalls)
    assert all(
        e.provenance.model_id == MODEL and e.provenance.model_origin == "brainos" for e in kin
    )
