"""PluginAdapter in the runtime: normalization, isolation and failure containment.

Every misbehaving plugin must be rejected or stopped with a specific error while the
runtime stays healthy (a simulated device connects afterwards).
"""

from __future__ import annotations

import os
import signal
from pathlib import Path

import numpy as np
import pytest
from brainos_adapter_sdk import ipc

from brainos.adapters.plugin import PluginAdapter
from brainos.contracts.protocol import DeviceKind, ErrorCode, Modality, RuntimeState
from brainos.runtime import Runtime, RuntimeCommandError
from brainos.runtime.plugins import (
    PluginOpenError,
    PluginOptionsError,
    PluginRegistry,
    PluginUnavailableError,
)

from .conftest import subscribe
from .helpers import drain, events, wait_for
from .plugin_helpers import PLUGINS_DIR, make_dist, spec


async def _connect(rt: Runtime, cls: str, *, probe: bool = True, **over: object) -> str:
    s = spec(cls, **over)  # type: ignore[arg-type]
    await rt.registry.plugins.register(s, probe=probe)
    await rt.connect(s.device_id)
    return s.device_id


async def _healthy(rt: Runtime) -> None:
    """After any plugin failure the runtime still connects another device."""
    await rt.disconnect()
    await rt.connect("sim-a")
    assert rt.state is RuntimeState.STREAMING
    await rt.disconnect()


async def test_good_plugin_events_are_valid_and_bit_exact(runtime: Runtime) -> None:
    from bos_test_plugins import CHUNK, signal_values

    sub = subscribe(runtime)
    await _connect(runtime, "GoodPlugin", options={"fail_after": 0, "unit": "millivolts"})
    dev = runtime.device
    assert dev is not None
    assert dev.kind is DeviceKind.SIMULATED and dev.synthetic
    assert dev.modality is Modality.INTRACORTICAL and dev.invasive is True  # by category
    assert dev.integration is not None and dev.integration.kind == "plugin"
    assert dev.integration.isolated and dev.integration.package == "bos-test-plugins"
    assert dev.adapter == "bos-test-plugins@0.0.1"
    rec = next(c for c in dev.capabilities if c.capability == "recording")
    assert rec.params["unit"] == "uV" and rec.params["channel_labels"] == [
        f"ch{i}" for i in range(4)
    ]
    msgs: list[dict[str, object]] = []

    def enough() -> bool:
        msgs.extend(drain(sub))
        return len(events(msgs, "recording.frame")) >= 10

    await wait_for(enough, timeout=10)
    frames = events(msgs, "recording.frame")
    for f in frames:
        p = f["payload"]
        assert p["unit"] == "uV" and p["channel_count"] == 4 and p["sample_rate_hz"] == 1000.0
        first, n = p["first_sample_index"], len(p["samples"][0])
        # millivolts -> µV: exactly float32 value (as float64) x 1000
        expected = signal_values(first, n).astype(np.float64) * 1000.0
        assert np.array_equal(np.array(p["samples"]).T, expected)
        assert f["device_timestamp_ns"] == round((1.0 + first / 1000.0) * 1e9)
        assert f["provenance"]["kind"] == "raw_signal" and f["provenance"]["synthetic"]
        assert "synthetic" in f["quality"]["flags"]
    assert frames[0]["payload"]["first_sample_index"] == 0
    assert all(len(f["payload"]["samples"][0]) == CHUNK for f in frames)
    marks = events(msgs, "recording.annotation")
    assert marks and marks[0]["payload"]["label"] == "m0"
    d = runtime.diagnostics
    assert d.validation_errors == 0 and d.undeclared_capability == 0 and d.decode_errors == 0
    meta = runtime.adapter.source_metadata()  # type: ignore[union-attr]
    assert meta["isolated"] and meta["host_pid"] != os.getpid()
    await runtime.disconnect()


async def test_disconnect_closes_the_plugin_session_gracefully(
    runtime: Runtime, tmp_path: Path
) -> None:
    """The pump is cancelled mid-read on disconnect; the pending answer is drained and the
    host shut down cleanly, so the plugin's close() runs (it releases the device)."""
    marker = tmp_path / "closed.txt"
    opts = {"fail_after": 0, "unit": "microvolts", "close_marker": str(marker)}
    await _connect(runtime, "GoodPlugin", options=opts)
    adapter = runtime.adapter
    assert isinstance(adapter, PluginAdapter)
    await wait_for(lambda: adapter.counters["chunks"] > 3, timeout=10)
    probe_closes = marker.read_text().count("closed")  # configure's probe also closed once
    await runtime.disconnect()
    assert marker.read_text().count("closed") == probe_closes + 1
    assert adapter.last_exit is None or "code 0" in adapter.last_exit


async def test_cancelled_request_is_drained(tmp_path: Path) -> None:
    import asyncio

    from brainos.adapters.plugin.host_client import AsyncHostClient

    marker = tmp_path / "closed.txt"
    c = AsyncHostClient("bos_test_plugins:SlowReadPlugin", extra_path=[str(PLUGINS_DIR)])
    try:
        await c.start(10)
        opts = {"close_marker": str(marker)}
        await c.request("open", {"device_key": "dev0", "options": opts}, timeout_s=10)
        task = asyncio.create_task(c.request("read", {"timeout_s": 1.0}, timeout_s=5))
        await asyncio.sleep(0.1)  # the plugin is inside read() now
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert c.alive  # not killed
        result, _ = await c.request("ping", {"nonce": 1}, timeout_s=5)  # read answer drained
        assert result["nonce"] == 1
    finally:
        code = await c.close()
    assert code == 0
    assert "closed" in marker.read_text()


async def test_unknown_unit_is_arbitrary(runtime: Runtime) -> None:
    sub = subscribe(runtime)
    await _connect(runtime, "GoodPlugin", options={"fail_after": 0, "unit": "none"})
    rec = next(c for c in runtime.device.capabilities if c.capability == "recording")  # type: ignore[union-attr]
    assert rec.params["unit"] == "arbitrary"
    msgs: list[dict[str, object]] = []
    await wait_for(lambda: bool(msgs.extend(drain(sub)) or events(msgs, "recording.frame")), 10)
    assert events(msgs, "recording.frame")[0]["payload"]["unit"] == "arbitrary"
    await runtime.disconnect()


async def test_open_failure_is_contained(runtime: Runtime) -> None:
    with pytest.raises(RuntimeCommandError) as e:
        await _connect(runtime, "OpenFailsPlugin", probe=False)
    assert e.value.code is ErrorCode.DEVICE_ERROR and "unplugged" in e.value.message
    assert runtime.state is RuntimeState.ERROR
    await _healthy(runtime)


@pytest.mark.parametrize(
    ("cls", "fragment"),
    [
        ("UndeclaredRolePlugin", "stream.role.undeclared"),
        ("OpenCrashPlugin", "RuntimeError: bug in open"),
        ("Api2Plugin", "written for adapter SDK API 2.0"),
    ],
)
async def test_rejected_at_open(runtime: Runtime, cls: str, fragment: str) -> None:
    with pytest.raises(RuntimeCommandError) as e:
        await _connect(runtime, cls, probe=False)
    assert "plugin stopped" in e.value.message and fragment in e.value.message
    await _healthy(runtime)


@pytest.mark.parametrize(
    ("cls", "fragment"),
    [
        ("UndeclaredStreamPlugin", "'bogus'"),
        ("WrongChannelsPlugin", "3 channels; stream declares 4"),
        ("DecreasingTimestampsPlugin", "timestamps"),
        ("NaNPlugin", "NaN"),
        ("SysExitPlugin", "SystemExit"),
    ],
)
async def test_invalid_data_stops_the_plugin(runtime: Runtime, cls: str, fragment: str) -> None:
    await _connect(runtime, cls, probe=False)
    await wait_for(lambda: runtime.state is RuntimeState.ERROR, timeout=15)
    err = runtime.snapshot().last_error or ""
    assert "plugin stopped" in err and fragment in err, err
    await _healthy(runtime)


async def test_hanging_plugin_is_killed_and_eventually_stopped(runtime: Runtime) -> None:
    await _connect(runtime, "HangPlugin", probe=False)
    await wait_for(lambda: runtime.state is RuntimeState.ERROR, timeout=30, interval=0.05)
    err = runtime.snapshot().last_error or ""
    assert "failed before delivering any data" in err and "did not answer" in err, err
    assert runtime.diagnostics.link_errors >= 3
    await _healthy(runtime)


async def test_host_crash_reconnects(runtime: Runtime) -> None:
    """os._exit in plugin code: link error, fresh host, data flows again."""
    sub = subscribe(runtime)
    await _connect(runtime, "ExitPlugin", probe=False)
    await wait_for(lambda: runtime.diagnostics.reconnect_successes >= 1, timeout=15)
    drain(sub)
    msgs: list[dict[str, object]] = []
    await wait_for(lambda: bool(msgs.extend(drain(sub)) or events(msgs, "recording.frame")), 10)
    statuses = [e["payload"]["detail"] for e in events(msgs, "device.status")]
    assert runtime.state in (RuntimeState.STREAMING, RuntimeState.RECONNECTING), statuses
    await runtime.disconnect()


async def test_killed_host_reconnects(runtime: Runtime) -> None:
    sub = subscribe(runtime)
    await _connect(runtime, "GoodPlugin")
    adapter = runtime.adapter
    assert isinstance(adapter, PluginAdapter) and adapter.host_pid
    old = adapter.host_pid
    os.kill(old, signal.SIGKILL)
    await wait_for(lambda: runtime.diagnostics.reconnect_successes >= 1, timeout=10)
    assert adapter.host_pid not in (None, old)
    drain(sub)
    msgs: list[dict[str, object]] = []
    await wait_for(lambda: bool(msgs.extend(drain(sub)) or events(msgs, "recording.frame")), 10)
    assert runtime.state is RuntimeState.STREAMING
    errs = [e.message for e in runtime.diagnostics_snapshot().recent_errors]
    assert any("SIGKILL" in m for m in errs), errs
    await runtime.disconnect()


async def test_link_lost_reconnects(runtime: Runtime) -> None:
    await _connect(runtime, "GoodPlugin", options={"fail_after": 5, "unit": "microvolts"})
    await wait_for(lambda: runtime.diagnostics.reconnect_successes >= 2, timeout=15)
    assert runtime.state in (RuntimeState.STREAMING, RuntimeState.RECONNECTING)
    adapter = runtime.adapter
    assert isinstance(adapter, PluginAdapter) and adapter.counters["link_lost"] >= 2
    await runtime.disconnect()


async def test_stdout_garbage_does_not_break_streaming(runtime: Runtime) -> None:
    sub = subscribe(runtime)
    await _connect(runtime, "GarbagePlugin")
    msgs: list[dict[str, object]] = []

    def enough() -> bool:
        msgs.extend(drain(sub))
        return len(events(msgs, "recording.frame")) >= 5

    await wait_for(enough, timeout=10)
    assert runtime.diagnostics.link_errors == 0
    log = runtime.adapter.source_metadata()["log_tail"]  # type: ignore[union-attr]
    assert any("chatty read" in line for line in log)
    await runtime.disconnect()


# ----------------------------------------------------------------------------- registry


@pytest.fixture
def plugin_site(tmp_path: Path) -> Path:
    return make_dist(
        tmp_path / "site",
        {
            "t-good": "bos_test_plugins:GoodPlugin",
            "t-open-fails": "bos_test_plugins:OpenFailsPlugin",
            "t-api2": "bos_test_plugins:Api2Plugin",
            "t-import-error": "bos_test_plugins.import_error:Plugin",
            "t-long-name-plugin-xxxxx": "bos_test_plugins:GoodPlugin",
        },
    )


async def test_registry_discovery_and_configure(plugin_site: Path) -> None:
    reg = PluginRegistry(extra_path=(str(plugin_site), str(PLUGINS_DIR)), discover_timeout_s=0.5)
    records = {r.name: r for r in await reg.discover()}
    assert records["t-good"].status == "compatible"
    assert records["t-good"].devices[0].device_id == "plugin:t-good:dev0"
    assert records["t-api2"].status == "rejected" and "API 2.0" in (records["t-api2"].reason or "")
    assert records["t-import-error"].status == "load_error"
    # 24-char entry point + "dev0" still fits the 64-char device id
    assert records["t-long-name-plugin-xxxxx"].devices[0].device_id is not None
    desc = await reg.configure("t-good", "dev0", {"unit": "millivolts", "fail_after": "0"})
    assert desc.device_id == "plugin:t-good:dev0" and reg.owns(desc.device_id)
    assert reg.source_metadata(desc.device_id)["options"] == {"unit": "millivolts", "fail_after": 0}  # type: ignore[index]
    with pytest.raises(PluginUnavailableError, match="cannot be used"):
        await reg.configure("t-api2", "dev0", {})
    with pytest.raises(PluginUnavailableError, match="no installed plugin"):
        await reg.configure("nope", "dev0", {})
    with pytest.raises(PluginOptionsError, match="unknown option"):
        await reg.configure("t-good", "dev0", {"rate": 5})
    with pytest.raises(PluginOptionsError):
        await reg.configure("t-good", "Bad Key", {})
    with pytest.raises(PluginOpenError, match="unplugged"):
        await reg.configure("t-open-fails", "dev0", {})
    assert reg.remove(desc.device_id) and not reg.owns(desc.device_id)


def test_device_id_rules() -> None:
    from brainos.adapters.plugin import device_id

    assert device_id("example-mi-eeg", "mi-eeg") == "plugin:example-mi-eeg:mi-eeg"
    with pytest.raises(ValueError, match="64"):
        device_id("x" * 24, "y" * 40)


def test_ipc_error_types_cover_recoverable_set() -> None:
    from brainos.adapters.plugin.adapter import RECOVERABLE

    assert {ipc.LINK_LOST, ipc.CONFIGURATION_CHANGED} == RECOVERABLE


def test_device_modality_comes_from_the_primary_stream_only() -> None:
    """Regression (BrainFlow synthetic board): the primary EXG stream's modality is
    ambiguous (undeclared) while a secondary sensor stream declares ``other``; the device
    must report 'not declared', not 'other'."""
    from brainos_adapter_sdk.api import (
        Channel,
        ClockInfo,
        Modality,
        SessionInfo,
        StreamRole,
        StreamSpec,
    )

    from brainos.adapters.plugin.mapping import neural_modality

    clock = ClockInfo("unix")

    def spec(sid: str, modality: Modality | None, invasive: bool | None = None) -> StreamSpec:
        return StreamSpec(sid, StreamRole.SIGNAL, (Channel("a"),), 250.0, clock, modality, invasive)

    def info(*streams: StreamSpec) -> SessionInfo:
        return SessionInfo(streams, "exg", synthetic=True, prerecorded=False, origin="t")

    assert neural_modality(info(spec("exg", None), spec("aux", Modality.OTHER))) == (None, None)
    assert neural_modality(info(spec("exg", Modality.EEG), spec("aux", Modality.OTHER))) == (
        Modality.EEG,
        False,
    )
    assert neural_modality(info(spec("exg", Modality.ECOG))) == (Modality.ECOG, True)
    assert neural_modality(info(spec("exg", None, invasive=False))) == (None, False)
