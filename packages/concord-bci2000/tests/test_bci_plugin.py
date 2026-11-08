"""The App Connector plugin end to end over real UDP sockets.

* Replay of datagrams recorded from a genuine BCI2000 ConnectorOutput
  (``fixtures/bci2000_connector_output.json``, recorded with
  ``scripts/capture_app_connector.py``).
* A sender reproducing ConnectorOutput byte for byte (``connector_output.py``) for options,
  errors and configuration changes.
"""

from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from bci_contract import StreamTracker, check_manifest, check_session_info
from concord_adapter_sdk import (
    ConfigurationChanged,
    InvalidOptions,
    LinkLost,
    OpenFailed,
    SourceSession,
    StreamRole,
)
from concord_adapter_sdk.api import KEY_PATTERN
from concord_bci2000 import BCI2000AppConnectorPlugin
from connector_output import DEFAULT_STATES, Sender, block_lines, free_udp_port

FIXTURE = Path(__file__).parent / "fixtures" / "bci2000_connector_output.json"


def wait_bound(port: int, timeout: float = 5.0) -> None:
    """Return once someone (the plugin) has bound ``port``."""
    table = Path("/proc/net/udp")
    if not table.exists():  # not Linux: give open() a moment instead
        time.sleep(0.3)
        return
    needle = f":{port:04X} "
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        # local_address column is "<hex ip>:<hex port>"; never bind the port ourselves
        if any(needle in line.split()[1] + " " for line in table.read_text().splitlines()[1:]):
            return
        time.sleep(0.005)
    raise AssertionError(f"port {port} was never bound")


class Feeding:
    """Opens the plugin (open() blocks until it has learned the layout) while a sender
    thread feeds it; the sender keeps running while the test reads."""

    def __init__(
        self, options: Mapping[str, Any], send: Callable[[int], None], port: int | None = None
    ) -> None:
        self.port = port or free_udp_port()
        result: dict[str, Any] = {}

        def opener() -> None:
            try:
                result["session"] = BCI2000AppConnectorPlugin().open(
                    "app-connector", {"port": self.port, **options}
                )
            except BaseException as exc:
                result["error"] = exc

        t = threading.Thread(target=opener)
        t.start()
        wait_bound(self.port)
        self.sender = threading.Thread(target=send, args=(self.port,))
        self.sender.start()
        t.join(timeout=30)
        if "error" in result:
            self.sender.join()
            raise result["error"]
        self.session: SourceSession = result["session"]

    def sending(self) -> bool:
        return self.sender.is_alive()

    def close(self) -> None:
        self.sender.join()
        self.session.close()


def open_while(
    options: Mapping[str, Any], send: Callable[[int], None], port: int | None = None
) -> SourceSession:
    """Open while ``send`` feeds the plugin; returns once open() succeeded and sending ended."""
    feeding = Feeding(options, send, port)
    feeding.sender.join()
    return feeding.session


def states(st: int, target: int = 0) -> list[tuple[str, int]]:
    values = {"Recording": 1, "Running": 1, "FilePart": 1, "SourceTime": st, "TargetCode": target}
    return [(n, values.get(n, 0)) for n in DEFAULT_STATES]


def emulate(
    blocks: int, *, start: int = 0, channels: int = 2, elements: int = 4, target: int = 0
) -> Callable[[int], None]:
    def send(port: int) -> None:
        s = Sender(port)
        try:
            for k in range(start, start + blocks):
                sig = [[k + c + 0.01 * e for e in range(elements)] for c in range(channels)]
                s.send(block_lines(states((1000 + 31 * k) % 65536, target), sig))
                time.sleep(0.001)
        finally:
            s.close()

    return send


# ----------------------------------------------------------------- genuine BCI2000 capture


def _expected_blocks() -> list[dict[str, str]]:
    raw = json.loads(FIXTURE.read_text())["datagrams"]
    blocks: list[dict[str, str]] = []
    for _, text in raw:
        name, value = text.rstrip("\n").split(" ")
        if name == "Notes":
            blocks.append({})
        blocks[-1][name] = value
    return blocks


def test_replay_of_genuine_bci2000_output() -> None:
    raw = json.loads(FIXTURE.read_text())["datagrams"]

    def replay(port: int) -> None:
        s = Sender(port)
        t0 = time.monotonic()
        try:
            for t, text in raw:
                delay = t0 + t - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
                s.sock.sendto(text.encode("ascii"), s.addr)
        finally:
            s.close()

    feeding = Feeding(
        {"sampling_rate_hz": 256, "sample_block_size": 8, "declare_synthetic": True}, replay
    )
    session = feeding.session
    info = session.info
    check_session_info(info, BCI2000AppConnectorPlugin.manifest)
    tracker = StreamTracker(info)
    try:
        tracker.read_for(session, 6.0, until=lambda _: not feeding.sending())
        tracker.read_for(session, 0.3)
        stats = dict(session.stats())
    finally:
        feeding.close()

    streams = {s.stream_id: s for s in info.streams}
    assert info.primary_stream == "control_signal"
    assert "processed control information" in info.origin
    assert info.synthetic is True and info.prerecorded is False
    ctrl = streams["control_signal"]
    assert ctrl.role is StreamRole.DECODER_OUTPUT
    assert ctrl.model_id == "bci2000-control-signal" and ctrl.quantity == "control_signal"
    assert [c.label for c in ctrl.channels] == [
        f"Signal({c},{e})" for c in range(2) for e in range(8)
    ]
    assert all(c.unit is None for c in ctrl.channels)
    assert ctrl.nominal_rate_hz == 32.0
    assert ctrl.clock.domain == "source" and "SourceTime" in ctrl.clock.description
    assert [c.label for c in streams["states"].channels] == ["TargetCode", "ResultCode", "Feedback"]

    expected = _expected_blocks()
    complete = [b for b in expected if "Signal(1,7)" in b]
    assert len(expected) == len(complete) + 1  # the final block was truncated by StopRun
    got = tracker.stacked("control_signal")
    # the first block is used only to synchronise; every other complete block arrives
    assert got.shape == (len(complete) - 1, 16)
    want = np.array(
        [[float(b[f"Signal({c},{e})"]) for c in range(2) for e in range(8)] for b in complete[1:]]
    )
    assert np.array_equal(got, want)
    ts = tracker.all_timestamps("control_signal")
    st = np.array([int(b["SourceTime"]) for b in complete[1:]], dtype=float) / 1000.0
    assert np.allclose(ts - ts[0], st - st[0])
    assert 0.025 < float(np.median(np.diff(ts))) < 0.04  # 8 samples at 256 Hz = 31.25 ms
    assert tracker.gaps["control_signal"] == 0
    assert stats["dropped_packets"] == 0 and stats["malformed_lines"] == 0
    labels = [m for m, _ in tracker.markers["state_changes"]]
    assert labels == [
        "TargetCode 0->2",
        "Feedback 0->1",
        "TargetCode 2->0",
        "ResultCode 0->2",
        "Feedback 1->0",
    ]
    beh = tracker.stacked("states")
    assert set(np.unique(beh[:, 0])) == {0.0, 2.0}


# ----------------------------------------------------------------- reproduction sender


def test_manifest_and_discover() -> None:
    plugin = BCI2000AppConnectorPlugin()
    check_manifest(plugin.manifest)
    assert plugin.manifest.network is True
    assert plugin.manifest.ecosystem == "bci2000"
    assert "processed control information" in plugin.manifest.description
    assert StreamRole.SIGNAL not in plugin.manifest.roles  # never raw signal
    (dev,) = plugin.discover(0.1)
    assert KEY_PATTERN.match(dev.device_key)
    assert "processed control information" in dev.description


def test_emulated_session_values_and_stats() -> None:
    feeding = Feeding({"behavior_states": "TargetCode,Running", "marker_states": ""}, emulate(40))
    session = feeding.session
    info = session.info
    check_session_info(info, BCI2000AppConnectorPlugin.manifest)
    assert {s.stream_id for s in info.streams} == {"control_signal", "states"}
    assert info.synthetic is False  # not declared
    tracker = StreamTracker(info)
    try:
        tracker.read_for(session, 3.0, until=lambda t: t.samples.get("control_signal", 0) >= 39)
        stats = dict(session.stats())
    finally:
        feeding.close()
    got = tracker.stacked("control_signal")
    assert got.shape == (39, 8)  # block 0 only synchronises
    k = np.arange(1, 40)[:, None]
    want = np.hstack([k + c + 0.01 * np.arange(4) for c in range(2)])
    assert np.allclose(got, want, rtol=1e-6)  # %g keeps 6 significant digits
    assert np.array_equal(tracker.stacked("states")[:, 1], np.ones(39))
    assert stats["blocks"] >= 39


def test_layout_change_raises_configuration_changed() -> None:
    session = open_while({}, emulate(5))
    try:
        emulate(3, start=5, channels=3)(int(session.info.origin.split(":")[2].split(" ")[0]))
        with pytest.raises(ConfigurationChanged):
            StreamTracker(session.info).read_for(session, 2.0)
    finally:
        session.close()


def test_shrunk_layout_raises_configuration_changed() -> None:
    session = open_while({}, emulate(5))
    try:
        port = int(session.info.origin.split(":")[2].split(" ")[0])
        emulate(8, start=5, elements=2)(port)
        with pytest.raises(ConfigurationChanged):
            StreamTracker(session.info).read_for(session, 2.0)
    finally:
        session.close()


def test_close_is_idempotent_and_frees_the_port() -> None:
    port = free_udp_port()
    session = open_while({}, emulate(4), port)
    session.close()
    session.close()
    with pytest.raises(LinkLost):
        session.read(0.01)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", port))  # released
    s.close()


def test_no_data_is_open_failed_with_setup_hint() -> None:
    port = free_udp_port()
    with pytest.raises(OpenFailed, match="ConnectorOutputAddress"):
        BCI2000AppConnectorPlugin().open("app-connector", {"port": port, "open_timeout_s": 0.3})


def test_port_in_use_is_open_failed() -> None:
    port = free_udp_port()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("127.0.0.1", port))
    try:
        with pytest.raises(OpenFailed, match="cannot receive"):
            BCI2000AppConnectorPlugin().open("app-connector", {"port": port})
    finally:
        s.close()


def test_unknown_selected_state_is_invalid_options() -> None:
    with pytest.raises(InvalidOptions, match="does not send state"):
        open_while({"behavior_states": "TargetCode,NoSuchState"}, emulate(5))


@pytest.mark.parametrize(
    ("options", "match"),
    [
        ({"bogus": 1}, "unknown option"),
        ({"port": 0}, "1-65535"),
        ({"port": "abc"}, "integer"),
        ({"address": ""}, "address"),
        ({"sampling_rate_hz": 256}, "both"),
        ({"sampling_rate_hz": -1, "sample_block_size": 8}, ">= 0"),
        ({"clock": "wall"}, "clock"),
        ({"open_timeout_s": 0}, "> 0"),
        ({"declare_synthetic": "maybe"}, "true or false"),
        ({"behavior_states": 3}, "comma-separated"),
    ],
)
def test_invalid_options(options: dict[str, Any], match: str) -> None:
    with pytest.raises(InvalidOptions, match=match):
        BCI2000AppConnectorPlugin().open("app-connector", options)


def test_unknown_device_key() -> None:
    with pytest.raises(OpenFailed):
        BCI2000AppConnectorPlugin().open("bci2000-host", {})
