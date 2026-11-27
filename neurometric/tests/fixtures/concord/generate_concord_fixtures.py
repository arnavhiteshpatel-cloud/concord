"""Regenerate the Concord recording fixtures used by the NeuroMetric Concord importer tests.

These files are produced by Concord's OWN runtime and recorder (no hand-written envelopes),
so they are genuine ``concord.recording/1`` files. All data is SYNTHETIC (simulated devices or
a scripted test decoder); none is neural data or a person's input.

Run with an interpreter that has Concord installed (``backend[server,dsp]``), from anywhere:

    python neurometric/tests/fixtures/concord/generate_concord_fixtures.py

Outputs (next to this file):

* ``sim_a_pointer_select.concord.jsonl`` -- Simulated Profile A, raw frames excluded:
  ``intent.pointer`` (simulated_intent, 50 Hz) driven by a fixed operator pattern, two
  ``intent.selection`` (primary), telemetry and device status.
* ``sim_b_select_text.concord.jsonl`` -- Simulated Profile B, raw frames excluded:
  ``intent.selection`` and ``intent.text`` (simulated_intent).
* ``scripted_decoded_click.concord.jsonl`` -- the scripted test decoder through the real
  pipeline + command router: ``features.vector``, ``intent.kinematics`` (decoded_intent), and
  decoded ``intent.pointer`` / ``intent.selection`` (decoded_intent, model_origin=concord).
  Ground truth: integrating the decoded pointer events the way the Concord board does
  (start (0.5, 0.5), dt from device_timestamp_ns capped at 0.1 s, clamp to [0, 1], y down)
  puts the cursor at (0.625, 0.125) when the single click fires.

Timestamps (wall clock at generation) differ on every run; everything else is deterministic up
to scheduler timing (the number of 50 Hz pointer events in a window).
"""

from __future__ import annotations

import asyncio
import shutil
import tempfile
import time
from pathlib import Path

from concord.adapters.simulated import OperatorIntentSource
from concord.contracts.capabilities import Capability
from concord.runtime import DeviceRegistry, Recorder, Runtime
from concord.runtime.pipeline import PipelineStartRequest
from concord.runtime.router import RouterSpec
from concord.testing import scripted

OUT = Path(__file__).resolve().parent


async def _until(cond, timeout: float = 10.0) -> None:  # type: ignore[no-untyped-def]
    end = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > end:
            raise TimeoutError("condition not reached")
        await asyncio.sleep(0.01)


async def sim_a(tmp: Path) -> Path:
    intents = OperatorIntentSource()
    rt = Runtime(DeviceRegistry(intents, tmp, seed=7, replay_loop=False), Recorder(tmp))
    await rt.connect("sim-a")
    name = rt.start_recording("sim-a-pointer-select", exclude_raw=True)
    # operator pattern (normalized [-1, 1]; Profile A scales by max_speed 2.0 workspace/s)
    for vx, vy, dur in ((0.5, 0.0, 0.4), (0.0, 0.5, 0.4), (-0.25, -0.25, 0.4)):
        end = time.monotonic() + dur
        while time.monotonic() < end:
            intents.set_pointer(vx, vy)  # refresh before the 0.5 s dead-man
            await asyncio.sleep(0.05)
        if vx == 0.0:
            intents.submit_select()
    intents.set_pointer(0.0, 0.0)
    intents.submit_select()
    await asyncio.sleep(0.4)
    rt.stop_recording()
    await rt.shutdown()
    return tmp / f"{name}.concord.jsonl"


async def sim_b(tmp: Path) -> Path:
    intents = OperatorIntentSource()
    rt = Runtime(DeviceRegistry(intents, tmp, seed=7, replay_loop=False), Recorder(tmp))
    await rt.connect("sim-b")
    name = rt.start_recording("sim-b-select-text", exclude_raw=True)
    intents.submit_select()
    await asyncio.sleep(0.3)
    for ch in "hi":
        intents.submit_text(ch)
        await asyncio.sleep(0.25)
    await _until(lambda: rt.diagnostics.totals.get("intent.text", 0) >= 2)
    await asyncio.sleep(0.3)
    rt.stop_recording()
    await rt.shutdown()
    return tmp / f"{name}.concord.jsonl"


async def decoded(tmp: Path) -> Path:
    models = tmp / "models"
    scripted.write_identity_model(models)
    reg = DeviceRegistry(OperatorIntentSource(), tmp, models_dir=models, seed=1)
    program = scripted.click_program([(0.625, 0.125)])
    reg.register(
        scripted.descriptor(),
        lambda: scripted.ScriptedFeatureSource(program, start_after_s=0.2, speed=1.0),
    )
    rt = Runtime(reg, Recorder(tmp))
    await rt.connect(scripted.DEVICE_ID)
    name = rt.start_recording("scripted-decoded-click")
    rt.start_pipeline(
        PipelineStartRequest(
            processing={"preset": "features_passthrough"},
            model_id=scripted.MODEL_ID,
            router=RouterSpec.model_validate(scripted.ROUTER),
        )
    )
    rt.authorize_app("board", [Capability.POINTER_INTENT, Capability.SELECTION])
    await _until(lambda: rt.pipeline.counters["selections_out"] >= 1, timeout=15)
    await asyncio.sleep(1.5)
    rt.stop_recording()
    await rt.shutdown()
    return tmp / f"{name}.concord.jsonl"


async def main() -> None:
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d)
        for fn, target in (
            (sim_a, "sim_a_pointer_select.concord.jsonl"),
            (sim_b, "sim_b_select_text.concord.jsonl"),
            (decoded, "scripted_decoded_click.concord.jsonl"),
        ):
            sub = tmp / fn.__name__
            sub.mkdir()
            src = await fn(sub)
            shutil.copyfile(src, OUT / target)
            print(f"wrote {OUT / target} ({(OUT / target).stat().st_size} bytes)")


if __name__ == "__main__":
    asyncio.run(main())
