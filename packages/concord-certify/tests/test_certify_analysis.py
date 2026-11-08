"""Pure analysis and check logic on synthetic tracks (no plugin host)."""

from __future__ import annotations

import numpy as np
from concord_adapter_sdk import Channel, ClockInfo, SessionInfo, StreamRole, StreamSpec

from concord_certify import analysis
from concord_certify import checks_static as cs
from concord_certify import checks_stream as cst
from concord_certify.acquire import StreamTrack, new_acquisition
from concord_certify.model import Results


def spec(rate: float = 100.0, domain: str = "source") -> StreamSpec:
    return StreamSpec("s", StreamRole.SIGNAL, (Channel("a", "microvolts"),), rate,
                      ClockInfo(domain))  # type: ignore[arg-type]  # fmt: skip


def feed(track: StreamTrack, n_chunks: int, chunk: int, rate_ts: float, rate_wall: float,
         t0: float = 10.0, offset: float = 0.0) -> None:  # fmt: skip
    for k in range(n_chunks):
        first = k * chunk
        ts = t0 + np.arange(first, first + chunk) / rate_ts
        arrival = (first + chunk) / rate_wall
        track.add(first, ts, arrival, arrival + offset, None)


def test_rates_from_timestamps_and_delivery() -> None:
    t = StreamTrack(spec())
    feed(t, 200, 10, rate_ts=101.0, rate_wall=100.0)
    tr = analysis.timestamp_rate(t)
    assert tr is not None and abs(tr["rate_hz"] - 101.0) < 1e-6
    dr = analysis.delivery_rate(t)
    assert dr is not None and abs(dr["rate_hz"] - 100.0) < 1e-6
    j = analysis.jitter(t, 100.0)
    assert j["residual_ms"]["max"] < 1e-6
    assert abs(j["arrival_interval_ms"]["p50"] - 100.0) < 1e-6


def test_gap_and_overlap_counting() -> None:
    t = StreamTrack(spec())
    t.add(0, np.arange(10) / 100.0, 0.1, 0.1, None)
    t.add(15, (15 + np.arange(10)) / 100.0, 0.2, 0.2, None)  # 5 lost
    t.add(20, (25 + np.arange(10)) / 100.0, 0.3, 0.3, None)  # overlap
    assert (t.gaps, t.lost, t.overlaps, t.decreasing) == (1, 5, 1, 0)
    t.add(30, np.full(3, 0.01), 0.4, 0.4, None)
    assert t.decreasing == 1


def test_drift_and_offsets() -> None:
    t = StreamTrack(spec(domain="unix"))
    feed(t, 300, 10, rate_ts=100.0, rate_wall=100.0 * (1 + 500e-6), t0=0.0, offset=0.0)
    off = analysis.offsets(t, "unix")
    assert off is not None
    # the source clock runs 500 ppm fast relative to arrival: arrival - ts shrinks
    assert abs(off["drift_ppm"] + 500.0) < 5.0


def _acq(rate: float, rate_ts: float, rate_wall: float, domain: str = "source") -> object:
    info = SessionInfo((spec(rate, domain),), "s", True, False, "test")
    a = new_acquisition(info)
    feed(a.tracks["s"], 200, 10, rate_ts=rate_ts, rate_wall=rate_wall)
    a.t_start, a.t_end = 0.0, 20.0
    return a


def test_rate_and_throughput_checks() -> None:
    r = Results()
    a = _acq(100.0, 100.5, 100.0)
    cst.check_rate(r, a, 0.02)  # type: ignore[arg-type]
    cst.check_throughput(r, a, 0.02)  # type: ignore[arg-type]
    assert r.get("timing.rate").status == "pass"  # type: ignore[union-attr]
    assert r.get("performance.throughput").status == "pass"  # type: ignore[union-attr]
    r2 = Results()
    b = _acq(100.0, 97.0, 103.0)
    cst.check_rate(r2, b, 0.02)  # type: ignore[arg-type]
    cst.check_throughput(r2, b, 0.02)  # type: ignore[arg-type]
    assert r2.get("timing.rate").status == "fail"  # type: ignore[union-attr]
    assert "runs ahead" in r2.get("performance.throughput").reason  # type: ignore[union-attr]


def test_sample_counter_clock_rule() -> None:
    r = Results()
    a = _acq(100.0, 100.0, 100.0, "sample_counter")
    cst.check_clock_domain(r, a)  # type: ignore[arg-type]
    assert r.get("timing.clock_domain").status == "pass"  # type: ignore[union-attr]
    r2 = Results()
    b = _acq(100.0, 99.0, 100.0, "sample_counter")
    cst.check_clock_domain(r2, b)  # type: ignore[arg-type]
    assert r2.get("timing.clock_domain").status == "fail"  # type: ignore[union-attr]


def test_classify_problem_codes() -> None:
    info = SessionInfo(
        (spec(), StreamSpec("mk", StreamRole.MARKERS, (Channel("m"),), 0.0, ClockInfo("source"))),
        "s", True, False, "o",
    )  # fmt: skip
    assert cst.classify("chunk.timestamps.decreasing", "chunk['s']", info) == "timing.monotonic"
    assert cst.classify("chunk.timestamps.decreasing", "chunk['mk']", info) == "integrity.markers"
    assert cst.classify("chunk.index.overlap", "chunk['s']", info) == "integrity.sample_index"
    assert cst.classify("chunk.data.finite", "chunk['s']", info) == "integrity.chunk_validation"


def test_identity_diff_and_redaction() -> None:
    a = SessionInfo((spec(),), "s", True, False, "o")
    b_spec = StreamSpec("s", StreamRole.SIGNAL, (Channel("b", "microvolts"),), 100.0,
                        ClockInfo("source"))  # fmt: skip
    b = SessionInfo((b_spec,), "s", True, False, "o")
    diffs = cs.identity_diff(cs.session_identity(a), cs.session_identity(b))
    assert diffs == ["s.labels: ['a'] -> ['b']"]
    assert cs.identity_diff(cs.session_identity(a), cs.session_identity(a)) == []
    red = cs.redact({"API_Token": "x", "client_secret": "y", "Password": "z", "port": 1})
    assert red == {"API_Token": "<redacted>", "client_secret": "<redacted>",
                   "Password": "<redacted>", "port": 1}  # fmt: skip
