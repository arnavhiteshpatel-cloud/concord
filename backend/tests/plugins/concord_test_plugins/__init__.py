"""Test source plugins (adapter SDK only), most of them deliberately broken.

Never installed into the environment: tests reach them as ``module:Class`` references or
through a temporary ``*.dist-info`` with entry points, with this directory on the plugin
host's PYTHONPATH. Each class exercises one failure the host / runtime must contain.
"""

from __future__ import annotations

import os
import sys
import time
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

import numpy as np
from concord_adapter_sdk import (
    Channel,
    Chunk,
    ClockInfo,
    DeviceInfo,
    LinkLost,
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

N_CH = 4
RATE = 1000.0
CHUNK = 20
CLOCK = ClockInfo("source", "test clock")


def manifest(
    api_version: str = "1.0", roles: frozenset[StreamRole] | None = None
) -> PluginManifest:
    return PluginManifest(
        name="concord-test-plugins",
        version="0.0.1",
        api_version=api_version,
        display_name="Concord test plugin",
        description="Deliberately misbehaving plugins for Concord tests.",
        author="Concord tests",
        license="Proprietary",
        roles=roles or frozenset({StreamRole.SIGNAL, StreamRole.MARKERS}),
        options={
            "fail_after": OptionSpec("int", "raise LinkLost after this many reads (0 = never)", 0),
            "unit": OptionSpec(
                "choice", "signal unit", default="microvolts",
                choices=("microvolts", "millivolts", "none"),
            ),
            "close_marker": OptionSpec("str", "file written by close() (tests)"),
        },
    )  # fmt: skip


def signal_values(first: int, n: int, n_ch: int = N_CH) -> np.ndarray[Any, np.dtype[np.float32]]:
    """Deterministic test values: sample i, channel c -> i * 0.25 + c + 0.125 (exact in f32)."""
    idx = np.arange(first, first + n, dtype=np.float64)[:, None]
    return (idx * 0.25 + np.arange(n_ch)[None, :] + 0.125).astype(np.float32)


class DemoSession(SourceSession):
    def __init__(self, plugin: GoodPlugin, options: Mapping[str, Any]) -> None:
        self.plugin = plugin
        unit = options.get("unit", "microvolts")
        self.fail_after = int(options.get("fail_after", 0))
        self.close_marker = options.get("close_marker")
        self._info = SessionInfo(
            streams=(
                StreamSpec(
                    "sig",
                    StreamRole.SIGNAL,
                    tuple(Channel(f"ch{i}", None if unit == "none" else unit) for i in range(N_CH)),
                    RATE,
                    CLOCK,
                    modality=Modality.INTRACORTICAL,
                ),
                StreamSpec("mk", StreamRole.MARKERS, (Channel("marker"),), 0.0, CLOCK),
                *plugin.extra_streams(),
            ),
            primary_stream="sig",
            synthetic=True,
            prerecorded=False,
            origin="concord-test-plugins",
        )
        self.reads = 0
        self.index = 0
        self.t0 = time.monotonic()

    @property
    def info(self) -> SessionInfo:
        return self._info

    def _pace(self, timeout_s: float) -> bool:
        due = self.t0 + (self.index + CHUNK) / RATE
        wait = due - time.monotonic()
        if wait > timeout_s:
            time.sleep(timeout_s)
            return False
        if wait > 0:
            time.sleep(wait)
        return True

    def read(self, timeout_s: float) -> Sequence[Chunk | MarkerChunk]:
        self.reads += 1
        if self.fail_after and self.reads > self.fail_after:
            raise LinkLost("test link dropped")
        if not self._pace(timeout_s):
            return []
        out = self.plugin.make_chunks(self)
        self.index += CHUNK
        return out

    def close(self) -> None:
        if self.close_marker:
            with open(self.close_marker, "a") as f:
                f.write(f"closed after {self.reads} reads\n")

    def stats(self) -> Mapping[str, int | float]:
        return {"reads": self.reads}


class GoodPlugin(SourcePlugin):
    """Well-behaved: 4 ch @ 1 kHz, marker every 100 samples."""

    manifest: ClassVar[PluginManifest] = manifest()

    def discover(self, timeout_s: float) -> Sequence[DeviceInfo]:
        return [DeviceInfo("dev0", "Test device", "a test device")]

    def open(self, device_key: str, options: Mapping[str, Any]) -> SourceSession:
        if device_key != "dev0":
            raise OpenFailed(f"no device {device_key!r}")
        return DemoSession(self, options)

    def extra_streams(self) -> tuple[StreamSpec, ...]:
        return ()

    def timestamps(self, s: DemoSession) -> np.ndarray[Any, np.dtype[np.float64]]:
        return 1.0 + np.arange(s.index, s.index + CHUNK) / RATE

    def make_chunks(self, s: DemoSession) -> list[Chunk | MarkerChunk]:
        ts = self.timestamps(s)
        out: list[Chunk | MarkerChunk] = [Chunk("sig", signal_values(s.index, CHUNK), ts, s.index)]
        if s.index % 100 == 0:
            out.append(MarkerChunk("mk", (f"m{s.index}",), ts[:1].copy()))
        return out


class OpenFailsPlugin(GoodPlugin):
    def open(self, device_key: str, options: Mapping[str, Any]) -> SourceSession:
        raise OpenFailed("test device is unplugged")


class OpenCrashPlugin(GoodPlugin):
    def open(self, device_key: str, options: Mapping[str, Any]) -> SourceSession:
        raise RuntimeError("bug in open")


class HangPlugin(GoodPlugin):
    def make_chunks(self, s: DemoSession) -> list[Chunk | MarkerChunk]:
        time.sleep(3600)
        return []


class GarbagePlugin(GoodPlugin):
    """Writes to stdout (print and the raw fd) - must not corrupt the IPC channel."""

    def open(self, device_key: str, options: Mapping[str, Any]) -> SourceSession:
        print("hello from plugin open()")
        os.write(1, b"\x00\x00\x00\x05garbage-on-fd1\n")
        return super().open(device_key, options)

    def make_chunks(self, s: DemoSession) -> list[Chunk | MarkerChunk]:
        print("chatty read", s.index)
        sys.stdout.flush()
        os.write(1, b"\xff\xff\xff\xff")
        return super().make_chunks(s)


class ExitPlugin(GoodPlugin):
    def make_chunks(self, s: DemoSession) -> list[Chunk | MarkerChunk]:
        if s.index >= 2 * CHUNK:
            os._exit(3)
        return super().make_chunks(s)


class SysExitPlugin(GoodPlugin):
    def make_chunks(self, s: DemoSession) -> list[Chunk | MarkerChunk]:
        sys.exit(2)


class UndeclaredRolePlugin(GoodPlugin):
    """The session declares a DECODER_OUTPUT stream; the manifest does not have that role."""

    def extra_streams(self) -> tuple[StreamSpec, ...]:
        return (
            StreamSpec(
                "dec",
                StreamRole.DECODER_OUTPUT,
                (Channel("vx"), Channel("vy")),
                50.0,
                CLOCK,
                model_id="m1",
            ),
        )


class UndeclaredStreamPlugin(GoodPlugin):
    def make_chunks(self, s: DemoSession) -> list[Chunk | MarkerChunk]:
        out = super().make_chunks(s)
        if s.index >= CHUNK:
            out.append(Chunk("bogus", signal_values(0, 2), np.array([9.0, 9.1]), 0))
        return out


class WrongChannelsPlugin(GoodPlugin):
    def make_chunks(self, s: DemoSession) -> list[Chunk | MarkerChunk]:
        if s.index >= CHUNK:
            return [Chunk("sig", signal_values(s.index, CHUNK, 3), self.timestamps(s), s.index)]
        return super().make_chunks(s)


class DecreasingTimestampsPlugin(GoodPlugin):
    def timestamps(self, s: DemoSession) -> np.ndarray[Any, np.dtype[np.float64]]:
        ts = super().timestamps(s)
        return ts - 0.5 if s.index >= CHUNK else ts


class NaNPlugin(GoodPlugin):
    def make_chunks(self, s: DemoSession) -> list[Chunk | MarkerChunk]:
        out = super().make_chunks(s)
        c = out[0]
        assert isinstance(c, Chunk)
        if s.index >= CHUNK:
            c.data[0, 0] = np.nan
        return out


class SlowReadPlugin(GoodPlugin):
    """Each read takes 0.3 s (long enough to cancel a request while the plugin works)."""

    def make_chunks(self, s: DemoSession) -> list[Chunk | MarkerChunk]:
        time.sleep(0.3)
        return super().make_chunks(s)


class HangDiscoverPlugin(GoodPlugin):
    def discover(self, timeout_s: float) -> Sequence[DeviceInfo]:
        time.sleep(3600)
        return []


class Api2Plugin(GoodPlugin):
    manifest: ClassVar[PluginManifest] = manifest(api_version="2.0")


class NotAPlugin:
    """Not a SourcePlugin subclass."""


class FastPlugin(SourcePlugin):
    """Throughput: 64 ch x 30 kHz float32, unpaced; options pick the chunk size."""

    manifest: ClassVar[PluginManifest] = PluginManifest(
        name="concord-test-plugins",
        version="0.0.1",
        api_version="1.0",
        display_name="Fast test plugin",
        description="Unpaced 64 x 30 kHz float32 for IPC throughput measurement.",
        author="Concord tests",
        license="Proprietary",
        roles=frozenset({StreamRole.SIGNAL}),
        options={"chunk": OptionSpec("int", "samples per chunk", default=1500)},
    )

    def discover(self, timeout_s: float) -> Sequence[DeviceInfo]:
        return [DeviceInfo("fast", "Fast device")]

    def open(self, device_key: str, options: Mapping[str, Any]) -> SourceSession:
        return FastSession(int(options.get("chunk", 1500)))


class FastSession(SourceSession):
    def __init__(self, chunk: int) -> None:
        self.chunk = chunk
        self.index = 0
        rng = np.random.default_rng(0)
        self.block = rng.standard_normal((chunk, 64)).astype(np.float32)
        self._info = SessionInfo(
            streams=(
                StreamSpec(
                    "sig",
                    StreamRole.SIGNAL,
                    tuple(Channel(f"e{i}", "microvolts") for i in range(64)),
                    30_000.0,
                    ClockInfo("sample_counter"),
                    modality=Modality.INTRACORTICAL,
                ),
            ),
            primary_stream="sig",
            synthetic=True,
            prerecorded=False,
            origin="concord-test-plugins:fast",
        )

    @property
    def info(self) -> SessionInfo:
        return self._info

    def read(self, timeout_s: float) -> Sequence[Chunk | MarkerChunk]:
        ts = np.arange(self.index, self.index + self.chunk) / 30_000.0
        c = Chunk("sig", self.block, ts, self.index)
        self.index += self.chunk
        return [c]

    def close(self) -> None:
        pass
