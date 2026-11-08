"""A declared-synthetic LSL test signal for dry runs of the verification workflow.

It lets a lab rehearse docs/HARDWARE_VALIDATION.md (LabRecorder + BrainOS + comparison)
before connecting hardware. The stream declares itself synthetic
(``<desc><brainos><synthetic>true</synthetic>``), so BrainOS marks every frame synthetic and
no report can treat it as hardware evidence.

Samples carry their own sample-clock timestamps (``t0 + k / rate``), as an acquisition
device's driver would, and the values are a seeded, non-repeating mix of sines and noise so
that every stretch of samples can be located by content.
"""

from __future__ import annotations

import threading
import time
from typing import Any

import numpy as np
from numpy.typing import NDArray


def make_block(start: int, n: int, channels: int, rate: float, seed: int) -> NDArray[np.float32]:
    """Samples ``start .. start+n-1`` (deterministic for a given seed), in microvolts."""
    k = np.arange(start, start + n, dtype=np.float64)[:, None]
    ch = np.arange(channels, dtype=np.float64)[None, :]
    t = k / rate
    sines = 40.0 * np.sin(2 * np.pi * (7.0 + 3.0 * ch) * t + ch) + 15.0 * np.sin(
        2 * np.pi * 50.0 * t
    )
    # counter-based noise: independent of how the stream is chunked
    rng = np.random.Generator(np.random.Philox(key=seed, counter=[0, 0, 0, start]))
    noise = rng.standard_normal((n, channels)) * 5.0
    out: NDArray[np.float32] = (sines + noise + 100.0 * ch).astype(np.float32)
    return out


class LSLTestSignal:
    """Publish ``channels`` x ``rate`` Hz float32 (µV) until stopped or ``duration_s``."""

    def __init__(
        self,
        name: str = "hwval-test-signal",
        *,
        channels: int = 8,
        rate: float = 1000.0,
        chunk: int = 20,
        seed: int = 1,
        source_id: str | None = None,
        duration_s: float | None = None,
        drop: list[tuple[int, int]] | None = None,
    ) -> None:
        self.name, self.channels, self.rate, self.chunk = name, channels, rate, chunk
        self.seed = seed
        self.source_id = source_id or f"{name}-sid"
        self.duration_s = duration_s
        self.drop = drop or []  # (first sample, count) withheld at the source (a real gap)
        self.sent = 0
        self.stop = threading.Event()
        self.ready = threading.Event()
        self._thread: threading.Thread | None = None
        self.error: BaseException | None = None

    def _info(self) -> Any:
        import pylsl

        info = pylsl.StreamInfo(
            self.name, "EEG", self.channels, self.rate, "float32", self.source_id
        )
        desc = info.desc()
        desc.append_child_value("manufacturer", "brainos-hwval test signal (synthetic)")
        chs = desc.append_child("channels")
        for i in range(self.channels):
            c = chs.append_child("channel")
            c.append_child_value("label", f"T{i + 1}")
            c.append_child_value("unit", "microvolts")
            c.append_child_value("type", "EEG")
        b = desc.append_child("brainos")
        b.append_child_value("synthetic", "true")
        b.append_child_value("prerecorded", "false")
        return info

    def run(self) -> None:
        import pylsl

        try:
            outlet = pylsl.StreamOutlet(self._info(), chunk_size=self.chunk, max_buffered=60)
            self.ready.set()
            t0 = pylsl.local_clock()
            k = 0
            while not self.stop.is_set():
                if self.duration_s is not None and k / self.rate >= self.duration_s:
                    break
                due = t0 + (k + self.chunk) / self.rate
                wait = due - pylsl.local_clock()
                if wait > 0:
                    time.sleep(min(wait, 0.05))
                    continue
                block = make_block(k, self.chunk, self.channels, self.rate, self.seed)
                stamps = t0 + (k + np.arange(self.chunk)) / self.rate
                keep = np.ones(self.chunk, dtype=bool)
                for a, n in self.drop:
                    keep &= ~(
                        (np.arange(k, k + self.chunk) >= a) & (np.arange(k, k + self.chunk) < a + n)
                    )
                if keep.any():
                    outlet.push_chunk(block[keep], stamps[keep].tolist())
                k += self.chunk
                self.sent = k
            time.sleep(0.5)  # let inlets drain before the outlet disappears
        except BaseException as exc:  # surfaced to the caller via .error
            self.error = exc
            self.ready.set()

    def start(self) -> LSLTestSignal:
        self._thread = threading.Thread(target=self.run, name="hwval-test-signal", daemon=True)
        self._thread.start()
        self.ready.wait(10)
        return self

    def join(self, timeout: float | None = None) -> None:
        if self._thread is not None:
            self._thread.join(timeout)

    def close(self) -> None:
        self.stop.set()
        self.join(5)
