"""Decoder host isolation: crash, hang, garbage, exceptions, invalid outputs, stdout.

Every test runs a real host process (``python -m brainos_decoder_sdk.host``)."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from dec_helpers import ENV, ref

from brainos_decoder_sdk import ipc
from brainos_decoder_sdk.client import DecoderHostDied, DecoderHostError, SyncDecoderHost


@pytest.fixture
def good() -> Iterator[SyncDecoderHost]:
    c = SyncDecoderHost(ref=ref("GoodDecoder"), env=ENV)
    yield c
    c.shutdown()


def _host(name: str) -> SyncDecoderHost:
    return SyncDecoderHost(ref=ref(name), env=ENV)


def test_good_decoder_round_trip_is_bit_exact_and_stateful(good: SyncDecoderHost) -> None:
    assert good.hello["protocol"] == ipc.PROTOCOL and good.hello["loaded"]
    m = good.manifest()
    assert m["compatible"] and m["manifest"]["model_id"] == "test-linear"
    with pytest.raises(DecoderHostError) as exc:
        good.step(np.zeros((1, 4)), None)
    assert exc.value.type == ipc.NOT_LOADED
    good.load()
    x = np.array([[0.1, 1 / 3, 2.0, 3.0], [0.2, 2 / 7, 0.0, 0.0]])
    values, conf = good.step(x, [0.02, 0.04])
    assert conf is None
    assert values.tobytes() == np.array([[0.1, 1 / 3], [0.1 + 0.2, 2 / 7]]).tobytes()
    good.reset()
    values, _ = good.step(x[:1], None)
    assert values[0, 0] == 0.1  # state was reset


def test_wrong_feature_width_is_refused_without_stopping(good: SyncDecoderHost) -> None:
    good.load()
    with pytest.raises(DecoderHostError) as exc:
        good.step(np.zeros((1, 5)), None)
    assert exc.value.type == ipc.INPUT_MISMATCH and "(n, 4)" in exc.value.message
    assert good.step(np.ones((1, 4)), None)[0].shape == (1, 2)  # still usable


def test_print_and_fd1_writes_do_not_corrupt_the_channel() -> None:
    with _host("PrintingDecoder") as c:
        c.load()
        for _ in range(3):
            assert c.step(np.ones((1, 4)), None)[0].shape == (1, 2)
    assert any("hello from a decoder" in line for line in c.stderr_tail)
    assert any("raw bytes on fd 1" in line for line in c.stderr_tail)


def test_crash_is_reported_as_host_death() -> None:
    c = _host("CrashDecoder")
    c.load()
    with pytest.raises(DecoderHostDied, match="exited"):
        c.step(np.ones((1, 4)), None)
    assert c.proc.poll() == 7
    c.shutdown()


def test_hang_is_killed_after_the_timeout() -> None:
    c = _host("HangDecoder")
    c.load()
    with pytest.raises(DecoderHostDied, match="did not answer"):
        c.step(np.ones((1, 4)), None, timeout_s=1.0)
    assert c.proc.poll() is not None  # killed
    c.shutdown()


@pytest.mark.parametrize(
    ("cls", "code"),
    [
        ("WrongShapeDecoder", "output.values.shape"),
        ("NaNDecoder", "output.values.finite"),
        ("BadPosteriorDecoder", "output.values.sum"),
        ("MissingVarianceDecoder", "output.confidence.missing"),
    ],
)
def test_invalid_output_stops_the_decoder(cls: str, code: str) -> None:
    with _host(cls) as c:
        c.load()
        with pytest.raises(DecoderHostError) as exc:
            c.step(np.ones((1, 4)), None)
        assert exc.value.type == ipc.INVALID_OUTPUT
        assert code in {p["code"] for p in exc.value.problems}
        with pytest.raises(DecoderHostError) as again:
            c.step(np.ones((1, 4)), None)
        assert again.value.type == ipc.STOPPED and "invalid output" in again.value.message


def test_exception_in_step_stops_the_decoder_with_a_traceback() -> None:
    with _host("RaisingDecoder") as c:
        c.load()
        with pytest.raises(DecoderHostError) as exc:
            c.step(np.ones((1, 4)), None)
        assert exc.value.type == ipc.INTERNAL_ERROR
        assert "ZeroDivisionError" in exc.value.message
        assert exc.value.traceback and "bug in decoder code" in exc.value.traceback
        with pytest.raises(DecoderHostError) as again:
            c.reset()
        assert again.value.type == ipc.STOPPED


def test_variance_confidence_crosses_the_wire() -> None:
    with _host("VarianceDecoder") as c:
        c.load()
        values, conf = c.step(np.ones((3, 4)), None)
        assert values.shape == (3, 2) and conf is not None
        assert np.array_equal(conf, np.tile([0.5, 0.25], (3, 1)))


def test_invalid_manifest_is_rejected_and_never_instantiated() -> None:
    with _host("BadManifestDecoder") as c:
        m = c.manifest()
        assert not m["compatible"]
        assert {p["code"] for p in m["problems"]} >= {"manifest.api_version", "manifest.modalities"}
        with pytest.raises(DecoderHostError) as exc:
            c.load()
        assert exc.value.type == ipc.INCOMPATIBLE


def test_load_failure_is_typed() -> None:
    with _host("LoadFailsDecoder") as c:
        with pytest.raises(DecoderHostError) as exc:
            c.load()
        assert exc.value.type == ipc.MODEL_LOAD_ERROR and "weights.npz" in exc.value.message


@pytest.mark.parametrize("name", ["NotADecoder", "NoSuchClass"])
def test_import_errors_are_reported_in_hello(name: str) -> None:
    with _host(name) as c:
        assert not c.hello["loaded"]
        assert c.hello["load_error"]["type"] == ipc.LOAD_FAILED
        with pytest.raises(DecoderHostError):
            c.load()


def test_garbage_on_the_channel_is_a_protocol_error(tmp_path: Path) -> None:
    script = tmp_path / "garbage.py"
    script.write_text("import sys\nsys.stdout.buffer.write(b'\\xff\\xff\\xff\\xffgarbage')\n")
    with pytest.raises(DecoderHostDied, match="protocol error"):
        SyncDecoderHost(command=[sys.executable, str(script)], hello_timeout_s=10)


def test_wrong_hello_is_refused(tmp_path: Path) -> None:
    script = tmp_path / "liar.py"
    script.write_text(
        "import sys\nfrom brainos_decoder_sdk import ipc\n"
        "ipc.write_message(sys.stdout.buffer, {'type': 'hello', 'protocol': 'other/9'})\n"
        "import time; time.sleep(5)\n"
    )
    with pytest.raises(DecoderHostDied, match="unexpected first message"):
        SyncDecoderHost(command=[sys.executable, str(script)], hello_timeout_s=10)


def test_check_command_reports_ok_and_failures() -> None:
    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", "brainos_decoder_sdk.host", *args],
            capture_output=True,
            text=True,
            timeout=120,
            env={**__import__("os").environ, **ENV},
        )

    ok = run(ref("GoodDecoder"), "--check", "--steps", "20")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "OK: manifest, load and every output passed validation" in ok.stdout
    bad = run(ref("NaNDecoder"), "--check", "--steps", "5")
    assert bad.returncode == 1 and "InvalidOutput" in bad.stdout
    rej = run(ref("BadManifestDecoder"), "--check")
    assert rej.returncode == 1 and "REJECTED" in rej.stdout


def test_list_probes_installed_entry_points(tmp_path: Path) -> None:
    site = tmp_path / "site"
    info = site / "bos_test_decoders-0.0.1.dist-info"
    info.mkdir(parents=True)
    (info / "METADATA").write_text(
        "Metadata-Version: 2.1\nName: bos-test-decoders\nVersion: 0.0.1\n"
    )
    (info / "entry_points.txt").write_text(
        "[brainos.decoders]\n"
        "good = bos_test_decoders:GoodDecoder\n"
        "bad-manifest = bos_test_decoders:BadManifestDecoder\n"
        "missing = bos_test_decoders:NoSuchClass\n"
    )
    import os

    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(site), ENV["PYTHONPATH"]])}
    r = subprocess.run(
        [sys.executable, "-m", "brainos_decoder_sdk.host", "--list"],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    assert r.returncode == 0, r.stderr
    doc = json.loads(r.stdout)
    by = {d["name"]: d for d in doc["decoders"]}
    assert by["good"]["status"] == "compatible"
    assert by["good"]["manifest"]["model_id"] == "test-linear"
    assert by["bad-manifest"]["status"] == "rejected"
    assert by["missing"]["status"] == "load_error"
