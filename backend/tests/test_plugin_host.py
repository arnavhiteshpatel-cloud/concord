"""Plugin host: binary IPC framing, bit-exact round trips, typed errors, stdout isolation,
and ``--list`` probing every plugin in its own process (broken ones cannot affect others).
"""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from brainos_adapter_sdk import Chunk, MarkerChunk, ipc
from brainos_adapter_sdk.client import HostDied, HostError, SyncHostClient

from .plugin_helpers import PLUGINS_DIR, make_dist, ref

ENV = {"PYTHONPATH": os.pathsep.join([str(PLUGINS_DIR), os.environ.get("PYTHONPATH", "")])}


@pytest.fixture
def host() -> Iterator[SyncHostClient]:
    c = SyncHostClient(ref("GoodPlugin"), env=ENV)
    yield c
    c.shutdown()


# ----------------------------------------------------------------------------- framing


@pytest.mark.parametrize("dtype", ["<f4", "<f8", "<i2", "<i4", "<i8", "|u1", "|i1", "<u2"])
def test_frame_roundtrip_is_bit_exact(dtype: str) -> None:
    rng = np.random.default_rng(3)
    a = (rng.standard_normal((37, 5)) * 1000).astype(dtype)
    raw = ipc.encode_message({"id": 1, "x": "y"}, [a, np.arange(37.0)])
    header, arrays = ipc.read_message(io.BytesIO(raw))  # type: ignore[misc]
    assert header["id"] == 1 and header["buffers"][0] == {"dtype": dtype, "shape": [37, 5]}
    assert arrays[0].dtype == np.dtype(dtype) and arrays[0].shape == (37, 5)
    assert arrays[0].tobytes() == a.tobytes()  # identical bits
    assert np.array_equal(arrays[1], np.arange(37.0))


def test_big_endian_and_non_contiguous_arrays_are_normalised() -> None:
    a = np.arange(12, dtype=">f4").reshape(3, 4)[:, ::2]  # big-endian, strided
    _, arrays = ipc.read_message(io.BytesIO(ipc.encode_message({}, [a])))  # type: ignore[misc]
    assert arrays[0].dtype == np.dtype("<f4") and np.array_equal(arrays[0], a)


def test_clean_eof_returns_none() -> None:
    assert ipc.read_message(io.BytesIO(b"")) is None


@pytest.mark.parametrize(
    "raw",
    [
        b"\xff\xff\xff\xff",  # absurd length (garbage on the channel)
        b"\x00\x00\x00\x05hello",  # not JSON
        b"\x00\x00\x00\x02[]",  # JSON but not an object
        b"\x00\x00\x00\x10{\"a\":1}",  # truncated inside a frame
        ipc.LENGTH.pack(40) + b'{"buffers":[{"dtype":"<c8","shape":[1]}]}',
        ipc.LENGTH.pack(43) + b'{"buffers":[{"dtype":"<f4","shape":[2,2]}]}' + ipc.LENGTH.pack(4) + b"abcd",
        ipc.LENGTH.pack(13) + b'{"buffers":1}',
    ],
)  # fmt: skip
def test_malformed_frames_raise_wire_error(raw: bytes) -> None:
    with pytest.raises(ipc.WireError):
        ipc.read_message(io.BytesIO(raw))


def test_chunk_wire_roundtrip_and_malformed_headers() -> None:
    c = Chunk("eeg", np.arange(6, dtype=np.int16).reshape(3, 2), np.array([1.0, 1.5, 2.0]), 7)
    m = MarkerChunk("mk", ("cue left",), np.array([1.25]))
    heads, arrays = ipc.chunks_to_wire([c, m])
    back = ipc.chunks_from_wire(heads, arrays)
    assert isinstance(back[0], Chunk) and back[0].first_index == 7
    assert back[0].data.dtype == np.int16 and np.array_equal(back[0].data, c.data)
    assert isinstance(back[1], MarkerChunk) and back[1].labels == ("cue left",)
    with pytest.raises(ipc.WireError):
        ipc.chunks_from_wire(heads, arrays[:-1])
    with pytest.raises(ipc.WireError):
        ipc.chunks_from_wire([{"kind": "video", "stream_id": "x"}], [])
    with pytest.raises(ipc.WireError):
        ipc.chunks_from_wire(heads, [*arrays, arrays[0]])


def test_manifest_and_session_wire_rejects_bad_types() -> None:
    from brainos_adapter_sdk.ipc import manifest_from_dict, stream_from_dict

    with pytest.raises(ipc.WireError):
        manifest_from_dict({"name": 1})
    good = {
        "stream_id": "s",
        "role": "signal",
        "channels": [{"label": "a"}],
        "nominal_rate_hz": 10,
        "clock": {"domain": "source"},
    }
    assert stream_from_dict(good).nominal_rate_hz == 10.0
    for bad in ({"role": "pointer"}, {"nominal_rate_hz": True}, {"modality": "fmri"}):
        with pytest.raises(ipc.WireError):
            stream_from_dict({**good, **bad})


# ----------------------------------------------------------------------------- host


def test_host_round_trip_values_are_bit_exact(host: SyncHostClient) -> None:
    from bos_test_plugins import signal_values

    assert host.hello["protocol"] == ipc.PROTOCOL and host.hello["loaded"]
    m = host.manifest()
    assert m["compatible"] and m["manifest"]["name"] == "bos-test-plugins"
    assert host.discover(0.5)["devices"][0]["device_key"] == "dev0"
    opened = host.open("dev0", {"unit": "millivolts"})
    assert opened["options"] == {"fail_after": 0, "unit": "millivolts"}  # defaults applied
    assert opened["info"]["streams"][0]["channels"][0]["unit"] == "millivolts"
    got: list[Chunk] = []
    while sum(c.data.shape[0] for c in got) < 100:
        got += [c for c in host.read(0.2) if isinstance(c, Chunk)]
    for c in got:
        assert c.data.dtype == np.float32 and c.data.shape[1] == 4  # dtype/shape preserved
        expected = signal_values(c.first_index, c.data.shape[0])
        assert c.data.tobytes() == expected.tobytes()
    stats = host.stats()
    assert stats["stats"]["reads"] >= 1 and stats["host"]["samples"] > 0


def test_typed_errors(host: SyncHostClient) -> None:
    with pytest.raises(HostError) as e:
        host.read()
    assert e.value.type == ipc.NOT_OPEN
    with pytest.raises(HostError) as e:
        host.open("dev0", {"unit": "kilovolts", "nope": 1})
    assert e.value.type == ipc.INVALID_OPTIONS
    assert {p["code"] for p in e.value.problems} == {"options.invalid", "options.unknown"}
    with pytest.raises(HostError) as e:
        host.open("dev9")
    assert e.value.type == ipc.OPEN_FAILED and "dev9" in e.value.message
    with pytest.raises(HostError) as e:
        host.request("stimulate")  # there is no such command (read-only)
    assert e.value.type == ipc.BAD_REQUEST
    assert host.request("ping", {"nonce": 5})[0]["nonce"] == 5


@pytest.mark.parametrize(
    ("cls", "error", "fragment"),
    [
        ("OpenCrashPlugin", ipc.INTERNAL_ERROR, "RuntimeError: bug in open"),
        ("OpenFailsPlugin", ipc.OPEN_FAILED, "unplugged"),
        ("UndeclaredRolePlugin", ipc.INVALID_SESSION, "not declared in the manifest"),
        ("Api2Plugin", ipc.INCOMPATIBLE, "API 2.0"),
    ],
)
def test_open_failures_are_typed(cls: str, error: str, fragment: str) -> None:
    with SyncHostClient(ref(cls), env=ENV) as c, pytest.raises(HostError) as e:
        c.open("dev0")
    assert e.value.type == error and fragment in e.value.message
    if error == ipc.INTERNAL_ERROR:
        assert e.value.traceback and "bug in open" in e.value.traceback


@pytest.mark.parametrize(
    ("cls", "code"),
    [
        ("UndeclaredStreamPlugin", "chunk.stream.unknown"),
        ("WrongChannelsPlugin", "chunk.data.channels"),
        ("DecreasingTimestampsPlugin", "chunk.timestamps.decreasing"),
        ("NaNPlugin", "chunk.data.finite"),
    ],
)
def test_invalid_data_stops_the_session(cls: str, code: str) -> None:
    with SyncHostClient(ref(cls), env=ENV) as c:
        c.open("dev0")
        with pytest.raises(HostError) as e:
            for _ in range(50):
                c.read(0.2)
        assert e.value.type == ipc.INVALID_DATA
        assert code in {p["code"] for p in e.value.problems}
        with pytest.raises(HostError) as e2:
            c.read()
        assert e2.value.type == ipc.NOT_OPEN and "stopped" in e2.value.message


def test_plugin_stdout_cannot_corrupt_the_channel() -> None:
    with SyncHostClient(ref("GarbagePlugin"), env=ENV) as c:
        c.open("dev0")
        n = 0
        for _ in range(10):
            n += sum(x.data.shape[0] for x in c.read(0.2) if isinstance(x, Chunk))
        assert n > 0
        log = "\n".join(c.stderr_tail)
    assert "hello from plugin open()" in log and "chatty read" in log


def test_host_exit_and_hang_are_detected() -> None:
    with SyncHostClient(ref("ExitPlugin"), env=ENV) as c:
        c.open("dev0")
        with pytest.raises(HostDied, match="code 3"):
            for _ in range(50):
                c.read(0.2)
    with SyncHostClient(ref("HangPlugin"), env=ENV) as c:
        c.open("dev0")
        with pytest.raises(HostDied, match="did not answer"):
            c.read(0.05, grace_s=0.5)
        assert c.proc.poll() is not None  # killed


def test_sys_exit_in_plugin_is_an_internal_error() -> None:
    with SyncHostClient(ref("SysExitPlugin"), env=ENV) as c:
        c.open("dev0")
        with pytest.raises(HostError) as e:
            for _ in range(20):
                c.read(0.2)
        assert e.value.type == ipc.INTERNAL_ERROR and "SystemExit" in e.value.message


@pytest.mark.parametrize(
    ("target", "fragment"),
    [
        ("bos_test_plugins.import_error:Plugin", "not installed"),
        ("bos_test_plugins:NotAPlugin", "not a SourcePlugin"),
        ("bos_test_plugins:Missing", "Missing"),
        ("no-such-entry-point", "no 'brainos.sources' entry point"),
    ],
)
def test_load_errors_are_reported_in_hello(target: str, fragment: str) -> None:
    with SyncHostClient(target, env=ENV) as c:
        assert c.hello["loaded"] is False
        assert fragment in c.hello["load_error"]["message"]
        with pytest.raises(HostError) as e:
            c.manifest()
        assert e.value.type == ipc.LOAD_FAILED


def test_list_probes_each_plugin_in_isolation(tmp_path: Path) -> None:
    site = make_dist(
        tmp_path / "site",
        {
            "t-good": "bos_test_plugins:GoodPlugin",
            "t-import-error": "bos_test_plugins.import_error:Plugin",
            "t-api2": "bos_test_plugins:Api2Plugin",
            "t-hang-open": "bos_test_plugins:HangPlugin",  # discover works; only read hangs
            "t-not-plugin": "bos_test_plugins:NotAPlugin",
            "t-hang-discover": "bos_test_plugins:HangDiscoverPlugin",
            "Bad_Name": "bos_test_plugins:GoodPlugin",
        },
    )
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([str(site), str(PLUGINS_DIR)]),
    }
    out = subprocess.run(
        [
            *(sys.executable, "-m", "brainos_adapter_sdk.host", "--list"),
            *("--discover-timeout", "0.5", "--timeout", "2"),
        ],
        capture_output=True,
        env=env,
        timeout=120,
        check=True,
    )
    doc = json.loads(out.stdout)
    by = {p["name"]: p for p in doc["plugins"]}
    assert by["t-good"]["status"] == "compatible"
    assert by["t-good"]["devices"][0]["device_key"] == "dev0"
    assert by["t-good"]["dist"] == {"name": "bos-test-plugins", "version": "0.0.1"}
    assert by["t-import-error"]["status"] == "load_error"
    assert "not installed" in by["t-import-error"]["error"]["message"]
    assert by["t-api2"]["status"] == "rejected"
    assert "manifest.api_version.incompatible" in {p["code"] for p in by["t-api2"]["problems"]}
    assert by["t-not-plugin"]["status"] == "load_error"
    assert by["Bad_Name"]["status"] == "rejected" and by["Bad_Name"]["manifest"] is None
    assert by["t-hang-open"]["status"] == "compatible"
    # hung in discover(): killed after the bounded wait, still listed, other plugins unaffected
    assert by["t-hang-discover"]["status"] == "compatible"
    assert by["t-hang-discover"]["devices"] is None
    assert "did not answer" in by["t-hang-discover"]["discovery_error"]["message"]
