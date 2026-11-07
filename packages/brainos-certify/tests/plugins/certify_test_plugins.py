"""Crafted plugins for brainos-certify's tests (adapter SDK only; never installed).

``DefectPlugin`` is well behaved unless its ``defect`` option names one defect; each defect
is meant to be caught by one specific certification check. Reached as ``module:Class``
with this directory on the plugin host's path.
"""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

import numpy as np
from brainos_adapter_sdk import (
    Channel,
    Chunk,
    ClockInfo,
    DeviceInfo,
    MarkerChunk,
    Modality,
    OpenFailed,
    OptionSpec,
    PluginManifest,
    SessionInfo,
    SourcePlugin,
    SourceSession,
    StreamRole,
    StreamSpec,
)

RATE = 500.0
CHUNK = 10
N_CH = 4
DEFECTS = (
    "none",
    "unknown_units",
    "no_modality",
    "shuffle_labels",
    "wrong_rate",
    "gaps",
    "overlap",
    "decreasing",
    "marker_disorder",
    "markers_off_clock",
    "nan",
    "hang_read",
    "stale_lock",
    "unix_offset",
    "jitter",
    "invalid_stats",
    "lossy_stats",
)


def manifest(
    api_version: str = "1.0", description: str = "Plugin for certify tests."
) -> PluginManifest:
    return PluginManifest(
        name="certify-test-plugins",
        version="0.0.1",
        api_version=api_version,
        display_name="Certify test plugin",
        description=description,
        author="brainos-certify tests",
        license="Proprietary",
        roles=frozenset({StreamRole.SIGNAL, StreamRole.MARKERS}),
        options={
            "defect": OptionSpec("choice", "defect to exhibit", default="none", choices=DEFECTS),
            "clock": OptionSpec("choice", "timestamp clock", default="source",
                                choices=("source", "unix")),
            "lock_file": OptionSpec("str", "lock file (defect stale_lock)", default=""),
            "api_token": OptionSpec("str", "a secret-looking option (redaction test)", default=""),
        },
    )  # fmt: skip


_OPENS = [0]  # opens in this host process


class DefectSession(SourceSession):
    def __init__(self, options: Mapping[str, Any]) -> None:
        _OPENS[0] += 1
        self.defect = str(options.get("defect", "none"))
        self.clock = str(options.get("clock", "source"))
        self.lock_file = str(options.get("lock_file") or "")
        if self.defect == "stale_lock" and self.lock_file:
            if os.path.exists(self.lock_file):
                raise OpenFailed(f"device busy: lock file {self.lock_file} exists")
            with open(self.lock_file, "w") as f:
                f.write(str(os.getpid()))
        labels = [f"ch{i}" for i in range(N_CH)]
        if self.defect == "shuffle_labels" and _OPENS[0] > 1:
            labels.reverse()
        unit = None if self.defect == "unknown_units" else "microvolts"
        modality = None if self.defect == "no_modality" else Modality.ECOG
        domain = "unix" if self.clock == "unix" or self.defect == "unix_offset" else "source"
        clock = ClockInfo(domain, "certify test clock")  # type: ignore[arg-type]
        self._info = SessionInfo(
            streams=(
                StreamSpec("sig", StreamRole.SIGNAL, tuple(Channel(x, unit) for x in labels),
                           RATE, clock, modality=modality),
                StreamSpec("mk", StreamRole.MARKERS, (Channel("marker"),), 0.0, clock),
            ),
            primary_stream="sig",
            synthetic=True,
            prerecorded=False,
            origin="certify-test-plugins",
        )  # fmt: skip
        self.rate = 450.0 if self.defect == "wrong_rate" else RATE
        self.index = 0
        self.sent = 0  # samples produced (indices may skip with defect "gaps")
        self.chunks = 0
        self.t0 = time.monotonic()
        self.t0_wall = time.time()
        self.last_ts = -1.0
        self.rng = np.random.default_rng(0)
        self.closed = False

    @property
    def info(self) -> SessionInfo:
        return self._info

    def _ts(self, first: int, n: int) -> np.ndarray[Any, np.dtype[np.float64]]:
        idx = np.arange(first, first + n, dtype=np.float64)
        if self.defect == "unix_offset":
            base = self.t0  # monotonic seconds declared as unix time
        elif self.clock == "unix":
            base = self.t0_wall
        else:
            base = 1.0
        ts = base + idx / self.rate
        if self.defect == "jitter":
            ts = ts + self.rng.uniform(0, 4.0 / self.rate, n)
            ts = np.maximum.accumulate(np.maximum(ts, self.last_ts))
        return ts

    def read(self, timeout_s: float) -> Sequence[Chunk | MarkerChunk]:
        due = self.t0 + (self.sent + CHUNK) / self.rate
        wait = due - time.monotonic()
        if wait > timeout_s:
            time.sleep(timeout_s)
            return []
        if wait > 0:
            time.sleep(wait)
        self.chunks += 1
        if self.defect == "hang_read" and self.chunks > 5:
            time.sleep(3600)
        if self.defect == "gaps" and self.chunks % 10 == 0:
            self.index += 5
        first = self.index
        ts = self._ts(first, CHUNK)
        if self.defect == "overlap" and self.chunks == 6:
            first -= 5  # timestamps keep increasing; the sample index goes back
        if self.defect == "decreasing" and self.chunks == 6:
            ts = ts - 1.0
        data = np.arange(CHUNK * N_CH, dtype=np.float32).reshape(CHUNK, N_CH) + first
        if self.defect == "nan" and self.chunks == 6:
            data[0, 0] = np.nan
        out: list[Chunk | MarkerChunk] = [Chunk("sig", data, ts, first)]
        if self.chunks % 5 == 0:
            mts = ts[:1].copy()
            if self.defect == "marker_disorder" and self.chunks == 10:
                mts = mts - 0.5
            if self.defect == "markers_off_clock":
                mts = mts + 100.0
            out.append(MarkerChunk("mk", (f"m{self.chunks}",), mts))
        self.index = first + CHUNK
        self.sent += CHUNK
        self.last_ts = float(ts[-1])
        return out

    def stats(self) -> Mapping[str, int | float]:
        if self.defect == "invalid_stats":
            return {"reads": self.chunks, "bad": "text"}  # type: ignore[dict-item]
        if self.defect == "lossy_stats":
            return {"dropped_packets": 3}
        return {"chunks": self.chunks}

    def close(self) -> None:
        if not self.closed and self.defect == "stale_lock" and self.lock_file:
            with contextlib.suppress(OSError):
                os.remove(self.lock_file)
        self.closed = True


class DefectPlugin(SourcePlugin):
    manifest: ClassVar[PluginManifest] = manifest()

    def discover(self, timeout_s: float) -> Sequence[DeviceInfo]:
        return [DeviceInfo("dev0", "Certify test device")]

    def open(self, device_key: str, options: Mapping[str, Any]) -> SourceSession:
        if device_key != "dev0":
            raise OpenFailed(f"no device {device_key!r}")
        return DefectSession(options)


class Api2Plugin(DefectPlugin):
    manifest: ClassVar[PluginManifest] = manifest(api_version="2.0")


class EmptyDescriptionPlugin(DefectPlugin):
    manifest: ClassVar[PluginManifest] = manifest(description="")


class NoDevicesPlugin(DefectPlugin):
    def discover(self, timeout_s: float) -> Sequence[DeviceInfo]:
        return []
