"""A scripted decoder test source and test decoder (SYNTHETIC — not neural data, not trained).

For end-to-end tests of the application layer (Milestone 5, workstream C): a deterministic
way to make the *real* decoded-command path (source -> pipeline -> decoder -> command router ->
authorization -> app) produce known cursor movements and clicks, so a test can assert that a
specific word was selected on the communication board.

* :class:`ScriptedFeatureSource` — a simulated device (declared ``synthetic``) emitting
  ``features.vector`` frames (``log_band_power``, 20 ms bins, 3 channels ``f_vx``, ``f_vy``,
  ``f_click``) whose values follow a script of :class:`Segment` s. They are scripted numbers
  shaped like features, nothing measured.
* :func:`write_identity_model` — a hand-written ``brainos.model/1`` ridge file with identity
  weights (outputs ``vx``, ``vy``, ``click`` = the three feature values), marked in its
  method / training fields as a test model that was never fitted to data.
* :func:`click_program` — a script that, for each target point of the board's unit square
  (x right, y down), homes the cursor to the top-left corner (overshooting; the board clamps),
  moves to the point, rests, clicks once and rests again.

With the router mapping ``x_dim=vx, y_dim=vy, pointer_scale="native"`` and
``click={"output": "click"}``, the decoded commands reproduce the script exactly (the board
integrates on device timestamps). The test server for the Playwright e2e is
``python -m brainos.testing.scripted serve --port P --data-dir D --click-at X,Y ...``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from brainos.adapters.base import DeviceAdapter, EventDraft, NativePacket
from brainos.contracts.capabilities import Capability, CapabilityDescriptor, EventType
from brainos.contracts.events import Provenance, ProvenanceKind, Quality, QualityFlag
from brainos.contracts.protocol import DeviceDescriptor, DeviceKind

DEVICE_ID = "test-scripted-decoder"
ADAPTER = "test.scripted-decoder@0.1.0"
ORIGIN = "brainos:test-scripted-decoder"
MODEL_ID = "test-scripted-identity"
CHANNELS = ("f_vx", "f_vy", "f_click")
DIMS = ["vx", "vy", "click"]
BIN_MS = 20.0
FEATURE = "log_band_power"
UNIT = "log10(arbitrary^2)"
# router settings that reproduce the script (operator side)
ROUTER: dict[str, Any] = {
    "enabled": True,
    "x_dim": "vx",
    "y_dim": "vy",
    "pointer_scale": "native",
    "gain": 1.0,
    "deadzone": 0.0,
    "max_speed": 2.0,
    "click": {"output": "click", "threshold": 0.5, "min_confidence": 0.5, "refractory_ms": 300},
}


@dataclass(frozen=True)
class Segment:
    """``duration_s`` of constant outputs (velocity in workspace units / s, click 0..1)."""

    duration_s: float
    vx: float = 0.0
    vy: float = 0.0
    click: float = 0.0


def click_program(
    points: Sequence[tuple[float, float]],
    *,
    home_s: float = 0.6,
    move_s: float = 0.6,
    rest_s: float = 0.5,
    click_bins: int = 2,
    after_s: float = 1.2,
) -> list[Segment]:
    """Home to (0, 0), move to each point, rest, click once, rest (unit square, y down)."""
    segs: list[Segment] = []
    for x, y in points:
        if not (0 <= x <= 1 and 0 <= y <= 1):
            raise ValueError(f"target {x, y} outside the unit square")
        segs.append(Segment(home_s, -2.0, -2.0))  # 2 units/s x 0.6 s > 1: the corner from anywhere
        segs.append(Segment(move_s, x / move_s, y / move_s))
        segs.append(Segment(rest_s))
        segs.append(Segment(click_bins * BIN_MS / 1000, click=1.0))
        segs.append(Segment(after_s))
    return segs


def descriptor(device_id: str = DEVICE_ID) -> DeviceDescriptor:
    return DeviceDescriptor(
        device_id=device_id,
        display_name="Scripted decoder test source (synthetic)",
        kind=DeviceKind.SIMULATED,
        adapter=ADAPTER,
        native_format="python (test script)",
        description=(
            "Test source: scripted feature values that a hand-written identity test decoder turns "
            "into known cursor movements and clicks. Not neural data."
        ),
        capabilities=[
            CapabilityDescriptor(
                capability=Capability.NEURAL_FEATURES,
                params={
                    "feature": FEATURE,
                    "unit": UNIT,
                    "bin_ms": BIN_MS,
                    "channel_count": len(CHANNELS),
                    "channel_labels": list(CHANNELS),
                },
                description="scripted values (synthetic test source)",
            ),
            CapabilityDescriptor(capability=Capability.DEVICE_STATUS),
        ],
        synthetic=True,
    )


class ScriptedFeatureSource(DeviceAdapter):
    """Emits one 20 ms bin per 20 ms / ``speed``: zeros for ``start_after_s``, the program, then
    zeros (or the program again with ``loop``). Receive-only like every adapter."""

    origin = ORIGIN

    def __init__(
        self,
        program: Sequence[Segment],
        *,
        device_id: str = DEVICE_ID,
        start_after_s: float = 2.0,
        speed: float = 1.0,
        loop: bool = False,
    ) -> None:
        self.descriptor = descriptor(device_id)
        self.speed, self.loop = speed, loop
        self._bins: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * round(
            start_after_s * 1000 / BIN_MS
        )
        self._program: list[tuple[float, float, float]] = []
        for s in program:
            self._program += [(s.vx, s.vy, s.click)] * max(1, round(s.duration_s * 1000 / BIN_MS))
        self._bins += self._program
        self._t0: float | None = None
        self._k = 0

    async def open(self) -> None:
        self._t0 = time.monotonic()
        self._k = 0

    async def close(self) -> None:
        self._t0 = None

    def set_paused(self, paused: bool) -> None:
        """The runtime discards packets while paused; the script keeps time."""

    def values(self, k: int) -> tuple[float, float, float]:
        if k < len(self._bins):
            return self._bins[k]
        if self.loop and self._program:
            return self._program[(k - len(self._bins)) % len(self._program)]
        return (0.0, 0.0, 0.0)

    async def read(self) -> NativePacket:
        assert self._t0 is not None
        due = self._t0 + (self._k + 1) * BIN_MS / 1000 / self.speed
        await asyncio.sleep(max(0.0, due - time.monotonic()))
        k = self._k
        self._k += 1
        return NativePacket((k, self.values(k)))

    def normalize(self, packet: NativePacket) -> Sequence[EventDraft]:
        k, vals = packet.data
        return [
            EventDraft(
                EventType.FEATURES_VECTOR,
                {
                    "feature": FEATURE,
                    "unit": UNIT,
                    "band_hz": None,
                    "bin_ms": BIN_MS,
                    "bin_index": k,
                    "channel_count": len(CHANNELS),
                    "values": [float(v) for v in vals],
                },
                Quality(score=1.0, flags=[QualityFlag.SYNTHETIC]),
                Provenance(
                    kind=ProvenanceKind.PROCESSED_FEATURE,
                    adapter=ADAPTER,
                    synthetic=True,
                    origin=ORIGIN,
                ),
                # device clock: bin end (never 0, which would mean "no device timestamp")
                round((k + 1) * BIN_MS * 1e6),
            )
        ]


def write_identity_model(models_dir: Path) -> Path:
    """The hand-written test decoder: outputs = inputs (no filter, no scaling)."""
    n = len(CHANNELS)
    model = {
        "model_id": MODEL_ID,
        "space": "test_scripted_cursor",
        "quantity": "velocity_and_click",
        "dims": DIMS,
        "unit": "workspace/s; click 0..1",
        "bin_ms": BIN_MS,
        "tau_ms": BIN_MS,
        "kernel": [1.0],
        "x_mean": [0.0] * n,
        "x_std": [1.0] * n,
        "weights": [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)],
        "intercept": [0.0] * n,
        "alpha": 0.0,
        "training": {
            "note": "hand-written identity test decoder; never fitted to any data",
            "sessions": [],
        },
        "evaluations": [],
        "created_at": "",
        "method": "TEST ONLY: identity mapping of scripted test features (not a trained decoder)",
        "schema": "brainos.model/1",
        "version": 1,
        "input": {
            "event_type": "features.vector",
            "feature": FEATURE,
            "bin_ms": BIN_MS,
            "channel_count": n,
            "channel_labels": list(CHANNELS),
        },
        "source": {"identity": ORIGIN, "description": "scripted decoder test source (synthetic)"},
    }
    models_dir.mkdir(parents=True, exist_ok=True)
    path = models_dir / f"{MODEL_ID}.json"
    path.write_text(json.dumps(model, indent=1))
    return path


def _point(text: str) -> tuple[float, float]:
    x, y = (float(v) for v in text.split(","))
    return x, y


def main(argv: list[str] | None = None) -> int:
    """Serve BrainOS (console + board) with the scripted source registered (for e2e tests)."""
    ap = argparse.ArgumentParser(description=main.__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8766)
    s.add_argument("--data-dir", type=Path, required=True)
    s.add_argument("--click-at", type=_point, action="append", default=[], metavar="X,Y")
    s.add_argument("--start-after-s", type=float, default=2.0)
    args = ap.parse_args(argv)

    import uvicorn

    from brainos.server import create_app
    from brainos.server.settings import Settings

    settings = Settings(port=args.port, data_dir=args.data_dir, log_level="WARNING")
    write_identity_model(settings.models_dir)
    app = create_app(settings)
    program = click_program(args.click_at)
    app.state.services.runtime.registry.register(
        descriptor(),
        lambda: ScriptedFeatureSource(program, start_after_s=args.start_after_s),
    )
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
