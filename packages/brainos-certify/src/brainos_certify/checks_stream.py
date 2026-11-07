"""Checks on what the plugin delivered: timestamps, ordering, loss, validity, performance.

Thresholds (documented in docs/CERTIFICATION.md; all reported with the measured values):

* rate / throughput: |measured / nominal - 1| <= ``rate_tolerance`` (default 2 %) over the run
* jitter: warning when the 99th percentile of timestamp residuals exceeds one sample period
* drift of the source clock against the host's monotonic clock: warning above 1000 ppm
* ``unix`` clock: fail when the median offset from the wall clock exceeds 60 s (not unix
  time); warning when samples are stamped > 0.5 s in the future or arrive > 5 s late
* ``sample_counter`` clock: timestamps must equal t0 + index / nominal rate (1 µs)
* host CPU: warning above 80 % of one core
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from brainos_adapter_sdk import SessionInfo, StreamRole
from brainos_adapter_sdk import validate as v

from brainos_certify import analysis
from brainos_certify.acquire import Acquisition, StreamTrack
from brainos_certify.model import Results

JITTER_WARN_PERIODS = 1.0
DRIFT_WARN_PPM = 1000.0
UNIX_FAIL_OFFSET_S = 60.0
UNIX_WARN_FUTURE_S = 0.5
UNIX_WARN_LATE_S = 5.0
SAMPLE_COUNTER_TOL_S = 1e-6
CPU_WARN_PERCENT = 80.0
MARKER_ALIGN_S = 1.0
DATA_CHECKS = (
    "timing.rate",
    "timing.jitter",
    "timing.clock_domain",
    "performance.throughput",
    "performance.latency",
    "performance.host_resources",
    "performance.ipc",
)
_WHERE = re.compile(r"chunk\['(.+)'\]")


def classify(code: str, where: str, info: SessionInfo) -> str:
    """Which check a chunk-validation problem belongs to."""
    m = _WHERE.match(where or "")
    role = None
    if m:
        spec = next((s for s in info.streams if s.stream_id == m.group(1)), None)
        role = StreamRole(spec.role) if spec is not None else None
    if code == "chunk.timestamps.decreasing":
        return "integrity.markers" if role is StreamRole.MARKERS else "timing.monotonic"
    if code in ("chunk.index.overlap", "chunk.index"):
        return "integrity.sample_index"
    return "integrity.chunk_validation"


def mapped_problems(acqs: Mapping[str, Acquisition]) -> dict[str, list[str]]:
    """Validation errors (host InvalidData + local re-validation) grouped by check id."""
    out: dict[str, list[str]] = {}
    for name, a in acqs.items():
        found: list[tuple[str, str, str]] = []
        f = a.failure
        if f is not None and f.type == "InvalidData":
            for p in f.problems:
                found.append((str(p.get("code")), str(p.get("where", "")), str(p.get("message"))))
        for q in a.local_errors:
            found.append((q.code, q.where, q.message))
        for code, where, msg in found:
            cid = classify(code, where, a.info)
            text = f"{name}: {code}{' ' + where if where else ''}: {msg}"
            if text not in out.setdefault(cid, []):
                out[cid].append(text)
    return out


def _failure_text(a: Acquisition) -> str:
    f = a.failure
    return f"{f.type}: {f.message}" if f is not None else ""


# ----------------------------------------------------------------------------- integrity


def check_read(
    results: Results, a: Acquisition, duration_s: float, mapped: Mapping[str, list[str]]
) -> None:
    f = a.failure
    ev = {
        "requested_s": duration_s,
        "ran_s": round(a.duration_s, 3),
        "reads": a.reads,
        "empty_reads": a.empty_reads,
        "samples": a.samples,
        "first_data_after_s": round(a.first_data_s, 3) if a.first_data_s is not None else None,
        "failure": f.to_dict() if f is not None else None,
    }
    if f is not None:
        what = {
            "HostDied": "the plugin host died or hung",
            "InvalidData": "the host stopped the session after invalid data",
            "LinkLost": "the plugin reported a link loss during a normal run",
            "ConfigurationChanged": "the plugin reported a configuration change",
            "InternalError": "plugin code raised an unexpected exception",
        }.get(f.type, f"read failed ({f.type})")
        see = ""
        if f.type == "InvalidData":
            cause = [
                cid for cid, msgs in mapped.items() if any(m.startswith("main:") for m in msgs)
            ]
            see = f" (cause: {', '.join(sorted(cause))})" if cause else ""
        results.set(
            "integrity.read", "fail", f"after {f.after_s:.2f} s {what}{see}: {f.message}", ev
        )
    elif a.samples == 0:
        results.set("integrity.read", "fail", f"no data in {a.duration_s:.1f} s", ev)
    else:
        results.set(
            "integrity.read",
            "pass",
            f"{a.reads} reads over {a.duration_s:.1f} s, {a.samples} samples (all streams), "
            "no errors",
            ev,
        )


def check_chunks(
    results: Results, acqs: Mapping[str, Acquisition], mapped: Mapping[str, list[str]]
) -> None:
    errs = mapped.get("integrity.chunk_validation", [])
    warnings = [
        f"{n}: {p.code}: {p.message}"
        for n, a in acqs.items()
        for p in a.local_problems
        if p.severity == "warning" and p.code != "chunk.index.gap"
    ]
    chunks = sum(t.chunks for a in acqs.values() for t in a.tracks.values())
    notices: dict[str, int] = {}
    for a in acqs.values():
        for code, n in a.notice_counts.items():
            notices[code] = notices.get(code, 0) + n
    ev = {
        "chunks_validated": chunks,
        "errors": errs[:20],
        "warnings": warnings[:20],
        "host_notices": notices,
    }
    if errs:
        results.set("integrity.chunk_validation", "fail", errs[0], ev)
    elif warnings:
        results.set("integrity.chunk_validation", "warn", warnings[0], ev)
    else:
        results.set(
            "integrity.chunk_validation",
            "pass",
            f"{chunks} chunks validated by the host and again by the certifier",
            ev,
        )


def check_monotonic(
    results: Results, acqs: Mapping[str, Acquisition], mapped: Mapping[str, list[str]]
) -> None:
    errs = list(mapped.get("timing.monotonic", []))
    per: dict[str, Any] = {}
    n = 0
    for name, a in acqs.items():
        for sid, t in a.tracks.items():
            if t.is_markers:
                continue
            n += t.samples
            per[f"{name}.{sid}"] = {"samples": t.samples, "decreases": t.decreasing}
            if t.decreasing:
                errs.append(f"{name}: stream {sid!r}: {t.decreasing} timestamp decrease(s)")
    ev = {"streams": per}
    if errs:
        results.set("timing.monotonic", "fail", errs[0], ev)
    elif n == 0:
        results.set("timing.monotonic", "not_run", "no numeric samples received", ev)
    else:
        results.set(
            "timing.monotonic",
            "pass",
            f"{n} timestamps in {len(acqs)} session(s) never decrease (within or across chunks)",
            ev,
        )


def check_sample_index(
    results: Results, acqs: Mapping[str, Acquisition], mapped: Mapping[str, list[str]]
) -> None:
    errs = list(mapped.get("integrity.sample_index", []))
    per: dict[str, Any] = {}
    gaps = lost = samples = 0
    for name, a in acqs.items():
        for sid, t in a.tracks.items():
            if t.is_markers:
                continue
            samples += t.samples
            per[f"{name}.{sid}"] = {
                "samples": t.samples,
                "first_index": t.first_index,
                "gaps": t.gaps,
                "lost_samples": t.lost,
                "overlaps": t.overlaps,
                "loss_fraction": round(t.lost / (t.lost + t.samples), 6)
                if t.lost + t.samples
                else 0.0,
            }
            gaps += t.gaps
            lost += t.lost
            if t.overlaps:
                errs.append(f"{name}: stream {sid!r}: {t.overlaps} overlapping chunk(s)")
    ev = {"streams": per, "gaps": gaps, "lost_samples": lost, "samples": samples}
    if errs:
        results.set("integrity.sample_index", "fail", errs[0], ev)
    elif gaps:
        results.set(
            "integrity.sample_index",
            "warn",
            f"{gaps} gap(s), {lost} sample(s) lost of {samples + lost} "
            f"({100.0 * lost / (samples + lost):.3f} %); no overlaps",
            ev,
        )
    elif samples == 0:
        results.set("integrity.sample_index", "not_run", "no numeric samples received", ev)
    else:
        results.set(
            "integrity.sample_index",
            "pass",
            f"{samples} samples in {len(acqs)} session(s): 0 gaps, 0 overlaps",
            ev,
        )


def check_markers(
    results: Results, acqs: Mapping[str, Acquisition], mapped: Mapping[str, list[str]]
) -> None:
    main = next(iter(acqs.values()))
    markers = [t for t in main.tracks.values() if t.is_markers]
    if not markers:
        results.set(
            "integrity.markers",
            "not_run",
            "not applicable: the session declares no markers stream",
            applicable=False,
        )
        return
    errs = list(mapped.get("integrity.markers", []))
    primary = main.primary()
    span = (
        (primary.arrivals[0].ts_first, primary.arrivals[-1].ts_last) if primary.arrivals else None
    )
    per: dict[str, Any] = {}
    warns: list[str] = []
    for name, a in acqs.items():
        for t in a.tracks.values():
            if not t.is_markers:
                continue
            if t.decreasing:
                errs.append(f"{name}: {t.spec.stream_id!r}: {t.decreasing} marker time decrease(s)")
            per[f"{name}.{t.spec.stream_id}"] = {"markers": t.samples, "decreases": t.decreasing}
    for t in markers:
        if t.samples == 0:
            warns.append(f"no markers on {t.spec.stream_id!r} in {main.duration_s:.1f} s")
            continue
        if span is not None:
            ts = t.timestamps()
            outside = int(((ts < span[0] - MARKER_ALIGN_S) | (ts > span[1] + MARKER_ALIGN_S)).sum())
            per[f"main.{t.spec.stream_id}"]["outside_primary_span"] = outside
            if outside:
                warns.append(
                    f"{outside} marker(s) on {t.spec.stream_id!r} lie > {MARKER_ALIGN_S:g} s "
                    "outside the primary stream's time span (clock mismatch?)"
                )
    ev = {"streams": per, "primary_span": list(span) if span else None}
    if errs:
        results.set("integrity.markers", "fail", errs[0], ev)
    elif warns:
        results.set("integrity.markers", "warn", warns[0], ev)
    else:
        n = sum(t.samples for t in markers)
        results.set(
            "integrity.markers",
            "pass",
            f"{n} marker(s) in order, within the primary stream's time span",
            ev,
        )


def check_plugin_stats(
    results: Results, reply: Mapping[str, Any] | None, error: str | None
) -> None:
    if error is not None:
        results.set("integrity.plugin_stats", "fail", f"stats() failed: {error}")
        return
    if reply is None:
        results.set("integrity.plugin_stats", "not_run", "no open session to query")
        return
    stats = reply.get("stats") or {}
    invalid = int(reply.get("invalid_stats") or 0)
    ev = {"plugin_stats": stats, "invalid_stats": invalid, "host_counters": reply.get("host")}
    lossy = {
        k: val
        for k, val in stats.items()
        if any(w in k.lower() for w in ("drop", "lost", "overflow", "malformed", "missed"))
        and isinstance(val, int | float)
        and val > 0
    }
    if invalid:
        results.set(
            "integrity.plugin_stats",
            "warn",
            f"{invalid} stats() entr(ies) dropped by the host (keys must be short strings, "
            "values finite numbers)",
            ev,
        )
    elif lossy:
        results.set("integrity.plugin_stats", "warn", f"plugin reports {lossy}", ev)
    else:
        results.set(
            "integrity.plugin_stats",
            "pass",
            f"{len(stats)} counter(s), none reporting loss"
            if stats
            else "stats() returns no counters (optional)",
            ev,
        )


# ----------------------------------------------------------------------------- timing


def _regular(a: Acquisition) -> list[StreamTrack]:
    return [t for t in a.tracks.values() if not t.is_markers and t.spec.nominal_rate_hz > 0]


def data_checks_not_run(results: Results, a: Acquisition) -> bool:
    """If the main acquisition was cut short, the measurement checks do not run."""
    if a.failure is None and a.samples > 0:
        return False
    why = (
        f"main acquisition stopped after {a.failure.after_s:.2f} s ({a.failure.type}); "
        "see integrity.read"
        if a.failure is not None
        else "no data received"
    )
    results.not_run(DATA_CHECKS, why)
    return True


def check_rate(results: Results, a: Acquisition, tol: float) -> None:
    regular = _regular(a)
    if not regular:
        results.set(
            "timing.rate",
            "not_run",
            "not applicable: no stream declares a nominal rate (all irregular)",
            applicable=False,
        )
        return
    per: dict[str, Any] = {}
    fails: list[str] = []
    notes: list[str] = []
    for t in regular:
        nominal = t.spec.nominal_rate_hz
        rec: dict[str, Any] = {"nominal_hz": nominal, "clock": t.spec.clock.domain}
        per[t.spec.stream_id] = rec
        if t.samples < 2:
            fails.append(
                f"{t.spec.stream_id!r} declared at {nominal:g} Hz delivered "
                f"{t.samples} sample(s) in {a.duration_s:.1f} s"
            )
            continue
        tr = analysis.timestamp_rate(t)
        rec.update(tr or {})
        if t.spec.clock.domain == "sample_counter":
            rec["note"] = (
                "timestamps derived from the sample counter: equal to nominal by construction"
            )
            notes.append(t.spec.stream_id)
            continue
        rate = (tr or {}).get("rate_hz")
        if rate is None:
            fails.append(f"{t.spec.stream_id!r}: timestamps do not advance")
            continue
        err = rate / nominal - 1.0
        rec["error_percent"] = round(100 * err, 3)
        if abs(err) > tol:
            fails.append(
                f"{t.spec.stream_id!r}: {rate:.4g} Hz from timestamps vs nominal {nominal:g} Hz "
                f"({100 * err:+.2f} %, tolerance ±{100 * tol:g} %)"
            )
    ev = {"tolerance_percent": 100 * tol, "streams": per}
    if fails:
        results.set("timing.rate", "fail", fails[0], ev)
        return
    p = per.get(a.info.primary_stream) or next(iter(per.values()))
    if "error_percent" in p:
        reason = (
            f"primary {p.get('rate_hz')} Hz from timestamps vs nominal {p['nominal_hz']:g} Hz "
            f"({p['error_percent']:+.3f} %, tolerance ±{100 * tol:g} %)"
        )
    else:
        reason = "rates within tolerance; " + ", ".join(
            f"{sid}: by construction (sample_counter)" for sid in notes
        )
    results.set("timing.rate", "pass", reason, ev)


def check_jitter(results: Results, a: Acquisition) -> None:
    regular = _regular(a)
    per: dict[str, Any] = {}
    warns: list[str] = []
    for t in regular:
        j = analysis.jitter(t, t.spec.nominal_rate_hz)
        per[t.spec.stream_id] = j
        period_ms = 1e3 / t.spec.nominal_rate_hz
        res = j.get("residual_ms") or {}
        if (
            t.spec.clock.domain != "sample_counter"
            and res.get("p99") is not None
            and res["p99"] > JITTER_WARN_PERIODS * period_ms
        ):
            warns.append(
                f"{t.spec.stream_id!r}: p99 timestamp residual {res['p99']:.3g} ms > "
                f"{JITTER_WARN_PERIODS:g} sample period ({period_ms:.3g} ms)"
            )
    for t in a.tracks.values():
        if t not in regular and len(t.arrivals) >= 2:
            per[t.spec.stream_id] = analysis.jitter(t, 0.0)
    if not per:
        results.set("timing.jitter", "not_run", "no stream delivered enough data", {})
        return
    ev = {"streams": per, "warn_threshold_sample_periods": JITTER_WARN_PERIODS}
    if warns:
        results.set("timing.jitter", "warn", warns[0], ev)
        return
    prim = per.get(a.info.primary_stream) or next(iter(per.values()))
    res = prim.get("residual_ms") or {}
    arr = prim.get("arrival_interval_ms") or {}
    results.set(
        "timing.jitter",
        "pass",
        f"primary timestamp residual p50/p99/max {res.get('p50')}/{res.get('p99')}/"
        f"{res.get('max')} ms; arrival interval p50/p99 {arr.get('p50')}/{arr.get('p99')} ms",
        ev,
    )


def check_clock_domain(results: Results, a: Acquisition) -> None:
    t = a.primary()
    domain = t.spec.clock.domain
    off = analysis.offsets(t, domain)
    if off is None:
        results.set("timing.clock_domain", "not_run", "no data on the primary stream")
        return
    ev: dict[str, Any] = {"domain": domain, "description": t.spec.clock.description, **off}
    drift = off.get("drift_ppm")
    med = off["offset_newest_s"].get("p50", 0.0)
    lo = off["offset_newest_s"].get("min", 0.0)
    status, reason = "pass", ""
    if domain in ("unix", "lsl") and off["reference_clock"] != "host monotonic clock":
        if abs(med) > UNIX_FAIL_OFFSET_S:
            status = "fail"
            reason = (
                f"timestamps are {med:.4g} s away from the {off['reference_clock']}: not "
                f"{domain} time as declared"
            )
        elif lo < -UNIX_WARN_FUTURE_S:
            status, reason = "warn", f"samples stamped up to {-lo:.3f} s in the future"
        elif med > UNIX_WARN_LATE_S:
            status, reason = "warn", f"samples arrive {med:.3f} s after their timestamps"
        else:
            reason = (
                f"{domain} timestamps within {med * 1e3:.2f} ms (median) of the "
                f"{off['reference_clock']}"
            )
    elif domain == "sample_counter":
        resid = analysis.sample_counter_residual(t, t.spec.nominal_rate_hz)
        ev["sample_counter_residual_s"] = resid
        tol = max(SAMPLE_COUNTER_TOL_S, 1e-12 * abs(t.arrivals[-1].ts_last))
        if resid is not None and resid > tol:
            status = "fail"
            reason = (
                f"timestamps deviate up to {resid:.3g} s from first + index / nominal rate: not a "
                "sample counter as declared"
            )
        else:
            reason = "timestamps equal first + index / nominal rate (sample counter)"
    else:
        reason = (
            f"{domain} clock: offset to host monotonic {med:.4g} s (origin unknown by "
            "declaration; not checkable)"
        )
    if status == "pass" and drift is not None and abs(drift) > DRIFT_WARN_PPM:
        status = "warn"
        reason = f"source clock drifts {drift:+.0f} ppm against the host's monotonic clock"
    elif drift is not None:
        reason += f"; drift {drift:+.1f} ppm vs host monotonic"
    results.set("timing.clock_domain", status, reason, ev)  # type: ignore[arg-type]


# ----------------------------------------------------------------------------- performance


def check_throughput(results: Results, a: Acquisition, tol: float) -> None:
    per: dict[str, Any] = {}
    fails: list[str] = []
    for t in a.tracks.values():
        nominal = t.spec.nominal_rate_hz
        rec: dict[str, Any] = {
            "samples": t.samples,
            "chunks": t.chunks,
            "samples_per_s_overall": round(t.samples / a.duration_s, 3) if a.duration_s else None,
            "nominal_hz": nominal,
        }
        per[t.spec.stream_id] = rec
        if t.is_markers or nominal <= 0:
            continue
        dr = analysis.delivery_rate(t)
        rec.update(dr or {})
        rate = (dr or {}).get("rate_hz")
        if rate is None:
            fails.append(f"{t.spec.stream_id!r}: too few chunks to measure delivery")
            continue
        err = rate / nominal - 1.0
        rec["error_percent"] = round(100 * err, 3)
        if abs(err) > tol:
            word = "falls behind" if err < 0 else "runs ahead of real time"
            fails.append(
                f"{t.spec.stream_id!r} {word}: delivered {rate:.4g} samples/s vs nominal "
                f"{nominal:g} Hz ({100 * err:+.2f} %, tolerance ±{100 * tol:g} %)"
            )
    ev = {
        "duration_s": round(a.duration_s, 3),
        "tolerance_percent": 100 * tol,
        "streams": per,
        "ipc_bytes_received": a.bytes,
        "ipc_bytes_per_s": round(a.bytes / a.duration_s, 1) if a.duration_s else None,
    }
    if fails:
        results.set("performance.throughput", "fail", fails[0], ev)
        return
    p = per[a.info.primary_stream]
    if "error_percent" in p:
        reason = (
            f"primary delivered {p['rate_hz']} samples/s over {a.duration_s:.1f} s vs nominal "
            f"{p['nominal_hz']:g} Hz ({p['error_percent']:+.3f} %); "
            f"{ev['ipc_bytes_per_s']} B/s over IPC"
        )
    else:
        reason = (
            f"irregular primary: {p['samples']} samples in {a.duration_s:.1f} s "
            f"({p['samples_per_s_overall']}/s); {ev['ipc_bytes_per_s']} B/s over IPC"
        )
    results.set("performance.throughput", "pass", reason, ev)


def check_latency(results: Results, a: Acquisition) -> None:
    t = a.primary()
    domain = t.spec.clock.domain
    off = analysis.offsets(t, domain)
    if (
        domain not in ("unix", "lsl")
        or off is None
        or off["reference_clock"] == "host monotonic clock"
    ):
        results.set(
            "performance.latency",
            "not_run",
            f"not applicable: clock domain {domain!r} has no known relation to a host clock "
            "(latency cannot be measured; see timing.clock_domain for the offset)",
            applicable=False,
        )
        return
    newest = analysis.distribution([x * 1e3 for x in _offsets(t, off["reference_clock"])])
    oldest = off["offset_oldest_s"]
    ev = {
        "reference_clock": off["reference_clock"],
        "newest_sample_latency_ms": newest,
        "oldest_sample_latency_s": oldest,
        "note": "read latency = arrival time at the certifier minus the sample's own timestamp; "
        "machine-dependent, includes the source's buffering and the plugin's read timeout",
    }
    results.set(
        "performance.latency",
        "pass",
        f"newest-sample latency p50/p95/p99/max {newest.get('p50')}/{newest.get('p95')}/"
        f"{newest.get('p99')}/{newest.get('max')} ms",
        ev,
    )


def _offsets(t: StreamTrack, ref: str) -> list[float]:
    if ref.startswith("wall"):
        return [x.t_wall - x.ts_last for x in t.arrivals]
    return [(x.t_lsl or 0.0) - x.ts_last for x in t.arrivals]


def check_resources(results: Results, summary: Mapping[str, Any] | None) -> None:
    if summary is None:
        results.set(
            "performance.host_resources",
            "not_run",
            "not applicable: /proc is not available on this OS",
            applicable=False,
        )
        return
    cpu = summary.get("cpu_percent_of_one_core")
    ev = dict(summary)
    reason = (
        f"host process CPU {cpu} % of one core, RSS peak {summary.get('rss_mib_peak')} MiB "
        f"(median {summary.get('rss_mib_median')} MiB)"
    )
    if cpu is not None and cpu > CPU_WARN_PERCENT:
        results.set("performance.host_resources", "warn", reason + " (near saturation)", ev)
    else:
        results.set("performance.host_resources", "pass", reason, ev)


def check_ipc(
    results: Results,
    a: Acquisition,
    host_counters: Mapping[str, Any] | None,
    ping_ms: list[float],
) -> None:
    dur = a.duration_s
    hc = dict(host_counters or {})
    ev = {
        "host_counters": hc,
        "host_bytes_per_s": round(float(hc.get("bytes", 0)) / dur, 1) if dur else None,
        "reads_per_s": round(a.reads / dur, 2) if dur else None,
        "empty_read_fraction": round(a.empty_reads / a.reads, 4) if a.reads else None,
        "ping_round_trip_ms": analysis.distribution(ping_ms),
    }
    ping = analysis.distribution(ping_ms)
    results.set(
        "performance.ipc",
        "pass",
        f"{ev['host_bytes_per_s']} B/s, {ev['reads_per_s']} reads/s; ping round trip "
        f"p50/p99 {ping.get('p50')}/{ping.get('p99')} ms",
        ev,
    )


def problems_text(problems: list[v.Problem]) -> list[str]:
    return [f"{p.code}: {p.message}" for p in problems]
