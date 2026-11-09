"""M5 P0: the neural-to-command chain on GENUINE T15 data, through the unchanged runtime.

replayed T15 block -> pipeline (historical passthrough, or Concord Kalman + click on the two
feature streams) -> operator-enabled command router -> authorized app. Checks that what reaches
the app is exactly what the offline evaluation computes (docs/CURSOR_CLICK.md), with the right
provenance, and that leakage / frame errors are refused.

Needs the T15 demo subset (``python -m concord.datasets.dryad``); skipped loudly without it
unless CONCORD_REQUIRE_T15=1.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytest.importorskip("scipy")

from concord.adapters.cursorclick.reader import load
from concord.adapters.cursorclick.source import neural_streams
from concord.adapters.simulated import OperatorIntentSource
from concord.contracts import Capability
from concord.datasets.dryad import manifest
from concord.decoding import click as clickdec
from concord.decoding import kalman
from concord.evaluation.cursorclick import intention_labels
from concord.evaluation.run_cursorclick import click_labels
from concord.runtime import DeviceRegistry, Recorder, Runtime, RuntimeCommandError
from concord.runtime.pipeline import ClickRule, PipelineStartRequest, RouterSpec

from .conftest import subscribe
from .helpers import drain, events, link_or_copy, wait_for

REPO = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("CONCORD_TEST_T15", REPO / "data" / "datasets" / "dryad-prr4xgxzq"))
NAMES = [f.filename for f in manifest("t15-cursor-click").blocks(468) if f.block in (0, 1, 2, 3)]
FILES = [DATA / n for n in NAMES]
PRESENT = all(f.exists() for f in FILES)
if not PRESENT and os.environ.get("CONCORD_REQUIRE_T15") == "1":
    raise RuntimeError(f"CONCORD_REQUIRE_T15=1 but the T15 demo files are missing in {DATA}")
pytestmark = pytest.mark.skipif(
    not PRESENT,
    reason=f"T15 cursor+click files not found in {DATA}; run `python -m concord.datasets.dryad`",
)

GRID_ID = "t15:day00468-block03-grid-evaluation"
TRAIN_ID = "t15:day00468-block01-radial8-calibration"
GAIN = 1 / 0.92  # board workspace (unit square) = the 0.92-screen-height task grid
IDENTITY = "dryad:10.5061/dryad.prr4xgxzq:t15"
# commands + decoder outputs only: the 2 x 256-channel feature streams would overflow a test queue
CMD_CAPS = [
    Capability.POINTER_INTENT,
    Capability.SELECTION,
    Capability.KINEMATIC_INTENT,
    Capability.CONTROL_STATUS,
]


@pytest.fixture(scope="module")
def models(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Any, Any]:
    """Kalman + click fitted on calibration blocks 0-2 only (the selected settings)."""
    cal = [load(f) for f in FILES[:3]]
    inputs = neural_streams(cal[0])
    feats = [np.hstack([b.tx, b.sbp]).astype(np.float64) for b in cal]
    training = {"sessions": [f"t15-day00468-block{b.block:02d}" for b in cal]}
    src = {"identity": IDENTITY, "description": "T15 day 468"}
    kal = kalman.fit(
        feats,
        [intention_labels(b) for b in cal],
        inputs=inputs,
        transforms=["identity", "log1p"],
        smoothing_tau_ms=0.0,
        shrinkage=0.1,
        dims=["vx", "vy"],
        unit="screen_height/s",
        space="t15_screen",
        model_id_prefix="t15",
        y_axis="up",
        training=training,
        source=src,
    )
    lab = [click_labels(b) for b in cal]
    clk = clickdec.fit(
        feats,
        [y for y, _ in lab],
        [w for _, w in lab],
        inputs=inputs,
        transforms=["identity", "log1p"],
        smoothing_tau_ms=50.0,
        l2=1000.0,
        space="t15_screen",
        model_id_prefix="t15",
        training=training,
        source=src,
    )
    clk.decision = {"threshold": 0.7, "hold_bins": 10, "refractory_ms": 1000.0}
    d = tmp_path_factory.mktemp("models")
    kal.save(d / f"{kal.model_id}.json")
    clk.save(d / f"{clk.model_id}.json")
    return d, kal, clk


@pytest.fixture
async def rt(tmp_path: Path, models: tuple[Path, Any, Any]) -> AsyncIterator[Runtime]:
    root = tmp_path / "data"
    (root / "datasets").mkdir(parents=True)
    for f in FILES:
        link_or_copy(root / "datasets" / f.name, f)
    reg = DeviceRegistry(OperatorIntentSource(), root / "recordings", models_dir=models[0])
    runtime = Runtime(reg, Recorder(root / "recordings"))
    yield runtime
    await runtime.shutdown()


def _pointer_router(**kw: Any) -> RouterSpec:
    base: dict[str, Any] = dict(
        enabled=True,
        x_dim="vx",
        y_dim="vy",
        pointer_scale="native",
        gain=GAIN,
        deadzone=0.0,
        invert_y=True,
        max_speed=10.0,
    )
    base.update(kw)
    return RouterSpec(**base)


async def _collect(rt: Runtime, sub: Any, n_bins: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    def step() -> bool:
        out.extend(drain(sub))
        return len(events(out, "intent.pointer")) >= n_bins

    await wait_for(step, timeout=60, interval=0.02)
    await asyncio.sleep(0.1)
    out.extend(drain(sub))
    return out


def _bin(e: dict[str, Any]) -> int:
    return round(e["device_timestamp_ns"] / 10_000_000) - 1  # bin end -> bin index


async def test_historical_outputs_reach_the_app_labelled_historical(rt: Runtime) -> None:
    """Passthrough of the original decoders: pointer = recorded velocity x gain (y flipped),
    selections at the recorded clicks; every command says model_origin historical, replayed."""
    await rt.connect(GRID_ID)
    with pytest.raises(RuntimeCommandError, match="invert_y"):
        rt.start_pipeline(
            PipelineStartRequest(
                processing={"preset": "decoded_passthrough"}, router=_pointer_router(invert_y=False)
            )
        )
    rt.authorize_app("test", [Capability.POINTER_INTENT, Capability.SELECTION])
    sub = subscribe(rt, optional=CMD_CAPS)
    rt.start_pipeline(
        PipelineStartRequest(
            processing={"preset": "decoded_passthrough"},
            router=_pointer_router(click=ClickRule(output="click", threshold=0.5)),
        )
    )
    await rt.set_playback_speed(8.0)
    msgs = await _collect(rt, sub, 1500)
    b = load(FILES[3])
    ptr = events(msgs, "intent.pointer")
    for e in ptr[:1500]:
        i = _bin(e)
        vx, vy = b.cursor_decoder[i] * GAIN
        assert e["payload"]["vx"] == pytest.approx(vx, abs=1e-6)  # payload rounded to 1e-6
        assert e["payload"]["vy"] == pytest.approx(-vy, abs=1e-6)
    sel = events(msgs, "intent.selection")
    last = _bin(ptr[-1])
    expected = [int(c) for c in b.click_bins() if c <= last]
    assert expected and [_bin(e) for e in sel][: len(expected)] == expected
    for e in ptr + sel:
        p = e["provenance"]
        assert p["kind"] == "decoded_intent" and p["model_origin"] == "historical"
        assert p["replayed"] is True
        assert p["model_id"] in ("t15-historical-velocity", "t15-historical-click")


async def test_concord_decoders_through_the_chain_equal_the_offline_evaluation(
    rt: Runtime, models: tuple[Path, Any, Any]
) -> None:
    """Concord Kalman + click on the two joined feature streams of a held-out block: decoded
    values equal offline prediction, clicks equal the offline click rule, provenance concord."""
    _, kal, clk = models
    await rt.connect(GRID_ID)
    rt.authorize_app("test", [Capability.POINTER_INTENT, Capability.SELECTION])
    sub = subscribe(rt, optional=CMD_CAPS)
    rule = ClickRule(**clickdec.router_click_rule(clk.decision))
    st = rt.start_pipeline(
        PipelineStartRequest(
            processing={"preset": "features_passthrough"},
            model_id=kal.model_id,
            model_ids=[clk.model_id],
            router=_pointer_router(click=rule),
        )
    )
    assert [d["model_id"] for d in st.decoders] == [kal.model_id, clk.model_id]
    await rt.set_playback_speed(8.0)
    msgs = await _collect(rt, sub, 1500)
    b = load(FILES[3])
    x = np.hstack([b.tx, b.sbp]).astype(np.float64)
    off_v = kal.predict(x)
    off_p = clk.predict(x)[:, 0]
    dec = events(msgs, "intent.kinematics")
    vel = {
        _bin(e): e["payload"]["values"] for e in dec if e["provenance"]["model_id"] == kal.model_id
    }
    prob = {
        _bin(e): e["payload"]["values"][0]
        for e in dec
        if e["provenance"]["model_id"] == clk.model_id
    }
    n = min(max(vel), max(prob))
    assert n >= 1000
    assert np.allclose([vel[i] for i in range(n)], off_v[:n], atol=1e-9)
    assert np.allclose([prob[i] for i in range(n)], off_p[:n], atol=1e-12)
    ptr = events(msgs, "intent.pointer")
    assert all(e["provenance"]["model_origin"] == "concord" for e in ptr)
    sel = [_bin(e) for e in events(msgs, "intent.selection") if _bin(e) < n]
    offline = clickdec.decision_events(off_p[:n], 0.7, 10, 100).tolist()
    assert sel == offline
    assert all(
        e["provenance"]["model_id"] == clk.model_id for e in events(msgs, "intent.selection")
    )


async def test_concord_models_refused_on_their_training_block(
    rt: Runtime, models: tuple[Path, Any, Any]
) -> None:
    _, kal, _ = models
    await rt.connect(TRAIN_ID)
    with pytest.raises(RuntimeCommandError, match="training session"):
        rt.start_pipeline(
            PipelineStartRequest(
                processing={"preset": "features_passthrough"}, model_id=kal.model_id
            )
        )
