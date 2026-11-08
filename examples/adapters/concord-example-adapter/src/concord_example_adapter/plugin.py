"""The Concord source plugin: wraps the generator in the public adapter SDK API.

Only ``concord_adapter_sdk`` and numpy are imported - a plugin never imports Concord.
Concord runs this code in a separate process (the plugin host), validates everything it
declares and returns, and turns it into standard events:

* stream ``eeg``     (SIGNAL)   -> ``recording.frame`` in microvolts
* stream ``cue``     (BEHAVIOR) -> ``behavior.sample`` (quantity ``class``)
* stream ``markers`` (MARKERS)  -> ``recording.annotation`` ("cue left", ...)
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np
from concord_adapter_sdk import (
    Channel,
    Chunk,
    ClockInfo,
    DeviceInfo,
    InvalidOptions,
    MarkerChunk,
    Modality,
    OptionSpec,
    PluginManifest,
    SessionInfo,
    SourcePlugin,
    SourceSession,
    StreamRole,
    StreamSpec,
)

from concord_example_adapter import __version__
from concord_example_adapter.generator import (
    BEHAVIOR_DECIMATION,
    BLOCK,
    FS_HZ,
    MONTAGES,
    GeneratorConfig,
    MotorImageryGenerator,
)

DEVICE_KEY = "mi-eeg"
MAX_BLOCKS_PER_READ = 20  # at most 2 s of data per read() (catch-up after a stall)


def _config(options: Mapping[str, Any]) -> GeneratorConfig:
    """Options arrive validated against the manifest's OptionSpecs (types, choices);
    value ranges are checked here."""
    try:
        return GeneratorConfig(
            seed=int(options["seed"]),
            montage=str(options["montage"]),
            cue_duration_s=float(options["cue_duration_s"]),
            effect_size=float(options["effect_size"]),
        )
    except (KeyError, ValueError) as exc:
        raise InvalidOptions(str(exc)) from exc


class MotorImageryEEGSession(SourceSession):
    def __init__(self, config: GeneratorConfig) -> None:
        self.generator = MotorImageryGenerator(config)
        # Clock: sample index / 250 Hz, anchored at open() to this host's monotonic clock,
        # so timestamps keep increasing across reconnects. One clock for all three streams.
        self._t0 = time.monotonic()
        clock = ClockInfo(
            "source", "generator sample clock: monotonic time at open() + sample index / 250 Hz"
        )
        labels = self.generator.labels
        self._info = SessionInfo(
            streams=(
                StreamSpec(
                    stream_id="eeg",
                    role=StreamRole.SIGNAL,
                    channels=tuple(Channel(lab, unit="microvolts", type="EEG") for lab in labels),
                    nominal_rate_hz=FS_HZ,
                    clock=clock,
                    modality=Modality.EEG,
                    invasive=False,
                ),
                StreamSpec(
                    stream_id="cue",
                    role=StreamRole.BEHAVIOR,
                    channels=(Channel("cue_class", unit=None, type="class"),),
                    nominal_rate_hz=FS_HZ / BEHAVIOR_DECIMATION,
                    clock=clock,
                    quantity="class",
                ),
                StreamSpec(
                    stream_id="markers",
                    role=StreamRole.MARKERS,
                    channels=(Channel("cue"),),
                    nominal_rate_hz=0.0,
                    clock=clock,
                ),
            ),
            primary_stream="eeg",
            synthetic=True,  # generated data: Concord labels it "Simulated data"
            prerecorded=False,
            origin=f"concord-example-adapter:mi-eeg:seed={config.seed}",
        )
        self._blocks = 0
        self._catchups = 0
        self._closed = False

    @property
    def info(self) -> SessionInfo:
        return self._info

    def _due(self) -> int:
        return int((time.monotonic() - self._t0) * FS_HZ) // BLOCK

    def read(self, timeout_s: float) -> Sequence[Chunk | MarkerChunk]:
        if self._closed:
            return []
        due = self._due()
        if due <= self._blocks:  # nothing due yet: wait for the next block (or the timeout)
            wait = (self._blocks + 1) * BLOCK / FS_HZ - (time.monotonic() - self._t0)
            time.sleep(max(0.0, min(wait, timeout_s)))
            due = self._due()
            if due <= self._blocks:
                return []
        n = min(due - self._blocks, MAX_BLOCKS_PER_READ)
        if due - self._blocks > MAX_BLOCKS_PER_READ:
            self._catchups += 1
        blocks = [self.generator.next_block() for _ in range(n)]
        self._blocks += n
        first = blocks[0].first_index
        eeg = np.concatenate([b.eeg for b in blocks])
        cue = np.concatenate([b.cue for b in blocks])
        idx = np.arange(first, first + eeg.shape[0])
        ts = self._t0 + idx / FS_HZ
        out: list[Chunk | MarkerChunk] = [
            Chunk("eeg", eeg, ts, first),
            Chunk(
                "cue",
                cue[::BEHAVIOR_DECIMATION, None].astype(np.float32),
                ts[::BEHAVIOR_DECIMATION],
                first // BEHAVIOR_DECIMATION,
            ),
        ]
        marks = [m for b in blocks for m in b.markers]
        if marks:
            out.append(
                MarkerChunk(
                    "markers",
                    tuple(label for _, label in marks),
                    np.array([self._t0 + i / FS_HZ for i, _ in marks]),
                )
            )
        return out

    def stats(self) -> Mapping[str, int | float]:
        return {"samples": self._blocks * BLOCK, "catch_up_reads": self._catchups}

    def close(self) -> None:
        self._closed = True


class MotorImageryEEGPlugin(SourcePlugin):
    manifest = PluginManifest(
        name="concord-example-adapter",
        version=__version__,
        api_version="1.0",
        display_name="Example: motor-imagery EEG generator",
        description=(
            "Declared-synthetic EEG for demos and tutorials: 8 or 16 channels at 250 Hz with "
            "1/f background, mu and alpha rhythms, and a rest/left/right cue schedule in which "
            "imagined movement lowers mu power over the opposite motor cortex. Not brain data."
        ),
        author="Concord developers",
        license="Proprietary (internal preview)",
        roles=frozenset({StreamRole.SIGNAL, StreamRole.BEHAVIOR, StreamRole.MARKERS}),
        options={
            "seed": OptionSpec("int", "Random seed (same seed, same signal)", default=1),
            "montage": OptionSpec(
                "choice", "Channel set (10-20 labels)", default="8", choices=tuple(MONTAGES)
            ),
            "cue_duration_s": OptionSpec("float", "Length of each cue, 1-30 s", default=4.0),
            "effect_size": OptionSpec(
                "float", "Mu amplitude reduction during imagery, 0-0.95", default=0.5
            ),
        },
    )

    def discover(self, timeout_s: float) -> Sequence[DeviceInfo]:
        # A generator is always "present": one virtual device.
        return [
            DeviceInfo(
                device_key=DEVICE_KEY,
                display_name="Motor-imagery EEG generator",
                description="Synthetic EEG with a rest / left / right cue schedule.",
                details={"rate": "250 Hz", "channels": "8 or 16 (10-20)"},
            )
        ]

    def open(self, device_key: str, options: Mapping[str, Any]) -> SourceSession:
        if device_key != DEVICE_KEY:
            raise InvalidOptions(
                f"unknown device {device_key!r}; this plugin offers {DEVICE_KEY!r}"
            )
        return MotorImageryEEGSession(_config(options))
