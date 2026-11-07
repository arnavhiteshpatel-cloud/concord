"""Adapter SDK validation (brainos_adapter_sdk.validate): one malformed-input test per rule.

Each test asserts the exact problem code, so a rule that stops firing fails loudly.
"""

from __future__ import annotations

import dataclasses
from typing import Any

import numpy as np
import pytest
from brainos_adapter_sdk import (
    Channel,
    Chunk,
    ClockInfo,
    DeviceInfo,
    MarkerChunk,
    Modality,
    OptionSpec,
    PluginManifest,
    SessionInfo,
    StreamRole,
    StreamSpec,
)
from brainos_adapter_sdk import validate as v

CLOCK = ClockInfo("source")


def manifest(**over: Any) -> PluginManifest:
    base = PluginManifest(
        name="my-plugin",
        version="0.1.0",
        api_version="1.0",
        display_name="My plugin",
        description="Test plugin",
        author="Me",
        license="MIT",
        roles=frozenset(StreamRole),
        options={"port": OptionSpec("str", "Serial port", default="/dev/ttyUSB0")},
    )
    return dataclasses.replace(base, **over)


def sig(**over: Any) -> StreamSpec:
    base = StreamSpec(
        "eeg",
        StreamRole.SIGNAL,
        (Channel("C3", "microvolts"), Channel("C4", "microvolts")),
        250.0,
        CLOCK,
        modality=Modality.EEG,
        invasive=False,
    )
    return dataclasses.replace(base, **over)


def session(*streams: StreamSpec, **over: Any) -> SessionInfo:
    base = SessionInfo(
        streams=streams or (sig(),),
        primary_stream="eeg",
        synthetic=True,
        prerecorded=False,
        origin="test",
    )
    return dataclasses.replace(base, **over)


def codes(problems: list[v.Problem], severity: str | None = "error") -> set[str]:
    return {p.code for p in problems if severity is None or p.severity == severity}


# ----------------------------------------------------------------------------- manifest


def test_valid_manifest_has_no_problems() -> None:
    assert v.validate_manifest(manifest()) == []


@pytest.mark.parametrize(
    ("over", "code"),
    [
        ({"name": "bad name!"}, "manifest.name"),
        ({"name": ""}, "manifest.name"),
        ({"version": "1.0"}, "manifest.version"),
        ({"version": "v1.0.0"}, "manifest.version"),
        ({"api_version": "1"}, "manifest.api_version.format"),
        ({"api_version": "2.0"}, "manifest.api_version.incompatible"),
        ({"api_version": "1.1"}, "manifest.api_version.incompatible"),  # newer minor than host
        ({"api_version": "0.9"}, "manifest.api_version.incompatible"),
        ({"display_name": " "}, "manifest.display_name"),
        ({"description": ""}, "manifest.description"),
        ({"author": ""}, "manifest.author"),
        ({"license": ""}, "manifest.license"),
        ({"ecosystem": "Bad Eco"}, "manifest.ecosystem"),
        ({"roles": frozenset()}, "manifest.roles.empty"),
        ({"roles": frozenset({StreamRole.SIGNAL, "pointer"})}, "manifest.roles.unknown"),
        ({"roles": frozenset({StreamRole.MARKERS})}, "manifest.roles.no_primary"),
        ({"options": {"Bad Name": OptionSpec("str", "x")}}, "option.name"),
        ({"options": {"x": OptionSpec("list", "x")}}, "option.type"),  # type: ignore[arg-type]
        ({"options": {"x": OptionSpec("str", "")}}, "option.description"),
        ({"options": {"x": OptionSpec("choice", "x")}}, "option.choices"),
        ({"options": {"x": OptionSpec("choice", "x", choices=("a", "a"))}}, "option.choices"),
        ({"options": {"x": OptionSpec("int", "x", choices=("a",))}}, "option.choices"),
        ({"options": {"x": OptionSpec("int", "x", default="abc")}}, "option.default"),
        (
            {"options": {"x": OptionSpec("choice", "x", default="c", choices=("a",))}},
            "option.default",
        ),
        ({"options": {"x": "not a spec"}}, "option.type"),
    ],
)
def test_malformed_manifest(over: dict[str, Any], code: str) -> None:
    assert code in codes(v.validate_manifest(manifest(**over)))


def test_manifest_wrong_type() -> None:
    assert codes(v.validate_manifest({"name": "x"})) == {"manifest.type"}


def test_api_compatibility_rule() -> None:
    assert v.api_compatible("1.0", "1.0")[0]
    assert v.api_compatible("1.0", "1.3")[0]  # older minor runs on a newer host
    assert not v.api_compatible("1.4", "1.3")[0]
    ok, msg = v.api_compatible("2.0", "1.0")
    assert not ok and "major" in msg


def test_required_option_with_default_is_a_warning() -> None:
    p = v.validate_manifest(manifest(options={"x": OptionSpec("int", "x", 1, required=True)}))
    assert codes(p, "warning") == {"option.required_with_default"} and not v.has_errors(p)


def test_entry_point_name_rule() -> None:
    assert v.validate_entry_point_name("example-mi-eeg") == []
    for bad in ("Upper", "x" * 25, "has space", "-lead"):
        assert codes(v.validate_entry_point_name(bad)) == {"entry_point.name"}


# ----------------------------------------------------------------------------- options


def test_options_defaults_coercion_and_errors() -> None:
    specs = {
        "n": OptionSpec("int", "n", default=3),
        "f": OptionSpec("float", "f"),
        "b": OptionSpec("bool", "b", default=False),
        "c": OptionSpec("choice", "c", default="a", choices=("a", "b")),
        "s": OptionSpec("str", "s", required=True),
    }
    resolved, problems = v.validate_options(specs, {"f": "2.5", "b": "true", "s": "x"})
    assert problems == []
    assert resolved == {"n": 3, "f": 2.5, "b": True, "c": "a", "s": "x"}
    _, problems = v.validate_options(specs, {"n": "x", "f": "nan", "c": "z", "zz": 1, "b": 2})
    found = {(p.code, p.where) for p in problems}
    assert ("options.invalid", "options.n") in found
    assert ("options.invalid", "options.f") in found
    assert ("options.invalid", "options.c") in found
    assert ("options.invalid", "options.b") in found
    assert ("options.unknown", "options.zz") in found
    assert ("options.missing", "options.s") in found
    _, problems = v.validate_options(specs, {"n": True, "s": "x"})  # bool is not an int
    assert codes(problems) == {"options.invalid"}


# ----------------------------------------------------------------------------- devices


def test_devices_rules() -> None:
    assert v.validate_devices([DeviceInfo("dev0", "Device")]) == []
    assert codes(v.validate_devices("nope")) == {"devices.type"}
    assert codes(v.validate_devices([object()])) == {"device.type"}
    assert codes(v.validate_devices([DeviceInfo("Bad Key", "D")])) == {"device.key"}
    dup = [DeviceInfo("a", "A"), DeviceInfo("a", "B")]
    assert codes(v.validate_devices(dup)) == {"device.key.duplicate"}
    assert codes(v.validate_devices([DeviceInfo("a", "")])) == {"device.display_name"}
    bad_details = DeviceInfo("a", "A", details={"k": 1})  # type: ignore[dict-item]
    assert codes(v.validate_devices([bad_details])) == {"device.details"}
    many = [DeviceInfo(f"d{i}", "D") for i in range(65)]
    assert "devices.count" in codes(v.validate_devices(many))


# ----------------------------------------------------------------------------- session


def test_valid_session_has_no_problems() -> None:
    beh = StreamSpec(
        "cue", StreamRole.BEHAVIOR, (Channel("cue_class"),), 50.0, CLOCK, quantity="class"
    )
    mk = StreamSpec("mk", StreamRole.MARKERS, (Channel("m"),), 0.0, CLOCK)
    assert v.validate_session_info(session(sig(), beh, mk), manifest()) == []


@pytest.mark.parametrize(
    ("streams", "over", "code"),
    [
        ((sig(stream_id="Bad Id"),), {"primary_stream": "Bad Id"}, "stream.id"),
        ((sig(), sig()), {}, "session.streams.duplicate"),
        ((sig(channels=()),), {}, "stream.channels.empty"),
        ((sig(channels=tuple(Channel(f"c{i}") for i in range(1025))),), {}, "stream.channels.count"),
        ((sig(channels=(Channel("C3"), Channel("C3"))),), {}, "stream.channels.duplicate"),
        ((sig(channels=(Channel(""), Channel("C4"))),), {}, "channel.label.empty"),
        ((sig(channels=(Channel("C3", unit=""),)),), {}, "channel.unit"),
        ((sig(nominal_rate_hz=-1.0),), {}, "stream.rate"),
        ((sig(nominal_rate_hz=float("nan")),), {}, "stream.rate"),
        ((sig(nominal_rate_hz=0.0),), {}, "stream.rate.irregular"),
        ((sig(nominal_rate_hz=200_000.0),), {}, "stream.rate"),
        ((sig(clock=ClockInfo("gps")),), {}, "stream.clock"),  # type: ignore[arg-type]
        ((sig(modality=Modality.EEG, invasive=True),), {}, "stream.invasive.inconsistent"),
        ((sig(modality=Modality.INTRACORTICAL, invasive=False),), {}, "stream.invasive.inconsistent"),
        ((sig(modality="fnirs"),), {}, "stream.modality"),
        ((sig(bin_ms=20.0),), {}, "stream.bin_ms.not_applicable"),
        ((sig(model_id="m"),), {}, "stream.model_id.not_applicable"),
        ((sig(quantity="velocity"),), {}, "stream.quantity.not_applicable"),
        ((sig(),), {"primary_stream": "nope"}, "session.primary.missing"),
        ((sig(), StreamSpec("mk", StreamRole.MARKERS, (Channel("m"),), 0.0, CLOCK)),
         {"primary_stream": "mk"}, "session.primary.role"),
        ((sig(), StreamSpec("mk", StreamRole.MARKERS, (Channel("m"),), 0.0, ClockInfo("unix"))),
         {}, "session.clock.mixed"),
        ((sig(),), {"origin": ""}, "session.origin"),
        ((sig(),), {"synthetic": "yes"}, "session.synthetic"),
    ],
)  # fmt: skip
def test_malformed_session(
    streams: tuple[StreamSpec, ...], over: dict[str, Any], code: str
) -> None:
    assert code in codes(v.validate_session_info(session(*streams, **over), manifest()))


def test_role_specific_session_rules() -> None:
    m = manifest()
    counts = StreamSpec("spk", StreamRole.SPIKE_COUNTS, (Channel("e1"),), 50.0, CLOCK)
    p = v.validate_session_info(session(counts, primary_stream="spk"), m)
    assert "stream.bin_ms.missing" in codes(p)
    p = v.validate_session_info(
        session(dataclasses.replace(counts, bin_ms=10.0), primary_stream="spk"), m
    )
    assert codes(p, "warning") == {"stream.bin_ms.rate_mismatch"}
    dec = StreamSpec("dec", StreamRole.DECODER_OUTPUT, (Channel("vx"),), 50.0, CLOCK)
    assert "stream.model_id.missing" in codes(
        v.validate_session_info(session(dec, primary_stream="dec"), m)
    )
    beh = StreamSpec(
        "b", StreamRole.BEHAVIOR, (Channel("x" * 33),), 50.0, CLOCK, modality=Modality.EEG
    )
    found = codes(v.validate_session_info(session(sig(), beh), m))
    assert {"channel.label.length", "stream.modality.not_applicable"} <= found
    mk = StreamSpec("mk", StreamRole.MARKERS, (Channel("a"), Channel("b")), 0.0, CLOCK)
    assert "stream.channels.count" in codes(v.validate_session_info(session(sig(), mk), m))


def test_undeclared_role_is_rejected() -> None:
    m = manifest(roles=frozenset({StreamRole.SIGNAL}))
    beh = StreamSpec("b", StreamRole.BEHAVIOR, (Channel("x"),), 50.0, CLOCK)
    assert "stream.role.undeclared" in codes(v.validate_session_info(session(sig(), beh), m))


def test_synthetic_and_prerecorded_is_a_warning() -> None:
    p = v.validate_session_info(session(sig(), prerecorded=True), manifest())
    assert codes(p, "warning") == {"session.synthetic_and_prerecorded"} and not v.has_errors(p)


def test_session_wrong_type() -> None:
    assert codes(v.validate_session_info("x", manifest())) == {"session.type"}
    assert codes(v.validate_session_info(session(streams=()), manifest())) == {
        "session.streams.empty"
    }


# ----------------------------------------------------------------------------- chunks


def chunk(n: int = 4, first: int = 0, t0: float = 1.0, ch: int = 2, **over: Any) -> Chunk:
    data = over.pop("data", np.zeros((n, ch), np.float32))
    ts = over.pop("timestamps", t0 + np.arange(n) / 250.0)
    return Chunk(over.pop("stream_id", "eeg"), data, ts, first)


@pytest.fixture
def cv() -> v.ChunkValidator:
    mk = StreamSpec("mk", StreamRole.MARKERS, (Channel("m"),), 0.0, CLOCK)
    spk = StreamSpec("spk", StreamRole.SPIKE_COUNTS, (Channel("e1"),), 50.0, CLOCK, bin_ms=20.0)
    return v.ChunkValidator(session(sig(), mk, spk))


def test_valid_chunks_and_gap_warning(cv: v.ChunkValidator) -> None:
    assert cv.check(chunk()) == []
    assert cv.next_index("eeg") == 4
    gap = cv.check(chunk(first=10, t0=2.0))
    assert codes(gap, "warning") == {"chunk.index.gap"} and not v.has_errors(gap)
    assert cv.next_index("eeg") == 14
    assert cv.check(MarkerChunk("mk", ("cue left",), np.array([2.0]))) == []
    assert cv.check(Chunk("spk", np.array([[0], [3]], np.int16), np.array([1.0, 1.02]), 0)) == []


@pytest.mark.parametrize(
    ("item", "code"),
    [
        ("not a chunk", "chunk.type"),
        (chunk(stream_id="nope"), "chunk.stream.unknown"),
        (chunk(stream_id="mk"), "chunk.kind_mismatch"),
        (MarkerChunk("eeg", ("x",), np.array([1.0])), "chunk.kind_mismatch"),
        (chunk(data=[[0, 0]]), "chunk.data.type"),
        (chunk(data=np.zeros((4, 2), complex)), "chunk.data.dtype"),
        (chunk(data=np.zeros((4, 2), bool)), "chunk.data.dtype"),
        (chunk(data=np.zeros(4, np.float32)), "chunk.data.shape"),
        (chunk(ch=3), "chunk.data.channels"),
        (chunk(timestamps=np.arange(3.0)), "chunk.timestamps.length"),
        (chunk(timestamps=[1.0, 2.0, 3.0, 4.0]), "chunk.timestamps.type"),
        (chunk(timestamps=np.array([1.0, np.nan, 2.0, 3.0])), "chunk.timestamps.finite"),
        (chunk(timestamps=np.array([-1.0, 0.0, 1.0, 2.0])), "chunk.timestamps.negative"),
        (chunk(timestamps=np.array([1.0, 0.5, 2.0, 3.0])), "chunk.timestamps.decreasing"),
        (chunk(data=np.full((4, 2), np.inf, np.float32)), "chunk.data.finite"),
        (Chunk("eeg", np.zeros((4, 2)), np.arange(4.0), -1), "chunk.index"),
        (Chunk("eeg", np.zeros((4, 2)), np.arange(4.0), 1.5), "chunk.index"),  # type: ignore[arg-type]
        (Chunk("spk", np.array([[-1]], np.int32), np.array([1.0]), 0), "chunk.counts.invalid"),
        (Chunk("spk", np.array([[0.5]]), np.array([1.0]), 0), "chunk.counts.invalid"),
        (MarkerChunk("mk", ("",), np.array([1.0])), "chunk.labels.empty"),
        (MarkerChunk("mk", ("x" * 129,), np.array([1.0])), "chunk.labels.length"),
        (MarkerChunk("mk", ("a", "b"), np.array([1.0])), "chunk.timestamps.length"),
        (MarkerChunk("mk", "ab", np.array([1.0, 2.0])), "chunk.labels.type"),  # type: ignore[arg-type]
    ],
)
def test_malformed_chunk(cv: v.ChunkValidator, item: Any, code: str) -> None:
    assert code in codes(cv.check(item))


def test_chunk_state_across_calls(cv: v.ChunkValidator) -> None:
    assert cv.check(chunk(n=4, first=0, t0=1.0)) == []
    # overlap: index goes back
    assert codes(cv.check(chunk(n=4, first=2, t0=2.0))) == {"chunk.index.overlap"}
    # decreasing across calls (first ts before previous last)
    assert codes(cv.check(chunk(n=4, first=4, t0=0.5))) == {"chunk.timestamps.decreasing"}
    # rejected chunks did not advance the state
    assert cv.next_index("eeg") == 4
    assert cv.check(chunk(n=4, first=4, t0=1.1)) == []


def test_oversized_chunk(cv: v.ChunkValidator) -> None:
    big = np.zeros((v.MAX_CHUNK_SAMPLES + 1, 2), np.int8)
    assert "chunk.too_large" in codes(cv.check(chunk(data=big, timestamps=np.zeros(len(big)))))


def test_read_result_must_be_a_sequence(cv: v.ChunkValidator) -> None:
    assert codes(cv.check_all(None)) == {"read.type"}
    assert codes(cv.check_all("abc")) == {"read.type"}
    assert cv.check_all([]) == []


def test_empty_chunk_is_a_warning(cv: v.ChunkValidator) -> None:
    p = cv.check(chunk(n=0, timestamps=np.zeros(0)))
    assert codes(p, "warning") == {"chunk.empty"} and not v.has_errors(p)


def test_problem_roundtrip_and_summary() -> None:
    p = v.Problem("a.b", "msg", "warning", "where")
    assert v.Problem.from_dict(p.to_dict()) == p
    assert v.summarize([p]) == "no errors"
    errs = [v.Problem(f"c{i}", f"m{i}") for i in range(5)]
    assert v.summarize(errs).endswith("(+2 more)")
