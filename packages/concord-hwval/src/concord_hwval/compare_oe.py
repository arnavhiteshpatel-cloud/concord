"""Compare a Concord Open Ephys (ZMQ Interface) recording with the GUI's Binary recording.

Setup: in the Open Ephys GUI signal chain, the ZMQ Interface (which Concord reads) and a
Record Node in Binary format see the same data, i.e. no processor between them changes it
(``... -> ZMQ Interface -> Record Node``). Concord frames carry the GUI's sample numbers
(``first_sample_index``), so every Concord sample maps exactly onto a Binary-file row. The
Record Node stores ``round(µV / bit_volts)`` as int16, so values agree to half a
quantisation step (GUI v1.1.0 ``SIMDConverter``); clipped int16 values are not compared.
"""

from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from concord_hwval import checks as C
from concord_hwval import report as R
from concord_hwval import timing as T
from concord_hwval.concord_rec import ConcordRecording, Frame, load_concord_recording
from concord_hwval.engine import compare, diagnose, map_by_key
from concord_hwval.model import Category, Check, Status, Thresholds, overall
from concord_hwval.oe_ref import (
    INT16_MAX,
    INT16_MIN,
    OEContinuous,
    OERecording,
    load_oe_recording,
    official_crosscheck,
)
from concord_hwval.scope import equipment_check, evidence_scope, load_equipment

OE_ADAPTER_PREFIX = "concord.openephys.zmq@"
UNIT_TO_UV = {"uv": 1.0, "µv": 1.0, "μv": 1.0, "mv": 1e3, "v": 1e6}
PLAYBACK_PROCESSORS = ("File Reader",)

LIMITATIONS = [
    "The Record Node stores 16-bit integers: values are verified to half a quantisation step "
    "(bit_volts / 2), not bit for bit. Samples at the int16 limits (clipped in the file) are "
    "excluded from the value comparison.",
    "Values are comparable only if no processor that changes data sits between the ZMQ "
    "Interface and the Record Node; the channel 'history' in structure.oebin is used to check "
    "this.",
    "The ZMQ Interface does not transmit units; unless the Concord operator declared the unit, "
    "Concord labels values 'arbitrary' and they are compared unscaled against the file's µV.",
    "Concord does not emit data received while it learns the stream layout on connect "
    "(docs/OPEN_EPHYS.md); that start-up interval is outside the overlap and is not loss.",
    "Data from the GUI's File Reader is file playback, not hardware, even though it passes "
    "through the real GUI and plugin.",
]


@dataclass
class OEOptions:
    stream: str | None = None
    equipment: Path | None = None
    thresholds: Thresholds = field(default_factory=Thresholds)
    command: list[str] | None = None


def _identity(
    rec: ConcordRecording, oe: OERecording, choice: str | None
) -> tuple[OEContinuous, Check]:
    p = rec.recording_params
    concord_stream = p.get("stream") if isinstance(p.get("stream"), str) else None
    stream = oe.stream(choice or (concord_stream if len(oe.continuous) > 1 else None))
    adapter = str(rec.device.get("adapter", ""))
    problems = []
    if not adapter.startswith(OE_ADAPTER_PREFIX):
        problems.append(
            f"Concord recording was made by adapter {adapter!r}, not the Open Ephys ZMQ adapter"
        )
    legacy = oe.version < 0.6  # GUI 0.5.x: no named streams in structure.oebin
    if concord_stream is not None and concord_stream != stream.stream_name and not legacy:
        problems.append(
            f"Concord stream {concord_stream!r} vs reference stream {stream.stream_name!r}"
        )
    names_b = rec.channel_labels() or []
    names_r = [c.name for c in stream.channels]
    unknown = [n for n in names_b if n not in names_r]
    if unknown:
        problems.append(f"Concord channels not in the reference: {unknown[:10]}")
    ev = {
        "concord_stream": concord_stream,
        "reference_stream": stream.describe(),
        "reference_streams": [c.stream_name for c in oe.continuous],
        "concord_adapter": adapter,
        "concord_origin": rec.provenance_flags()["origins"],
        "gui_version": oe.gui_version,
    }
    if problems:
        st, msg = Status.FAIL, "; ".join(problems)
    elif concord_stream is None:
        st, msg = Status.INCONCLUSIVE, "Concord descriptor names no stream; matched by layout"
    elif legacy:
        st, msg = (
            Status.PASS,
            (f"GUI {oe.gui_version} recordings name no streams; identified by channel names"),
        )
    else:
        st, msg = Status.PASS, f"same Open Ephys stream {stream.stream_name!r}"
    return stream, Check(
        "IDENTITY",
        "Both recordings are of the same Open Ephys stream",
        Category.IDENTITY,
        True,
        st,
        msg,
        "Concord descriptor 'stream' equals the structure.oebin stream_name; every Concord "
        "channel name exists in the reference; the Concord adapter is the Open Ephys ZMQ "
        "adapter.",
        ev,
    )


def _chain_check(stream: OEContinuous) -> tuple[Check, list[str]]:
    hist = sorted({c.history for c in stream.channels if c.history})
    playback = []
    if stream.source_processor_name in PLAYBACK_PROCESSORS:
        playback.append(
            f"the reference stream's source processor is "
            f"{stream.source_processor_name!r} (file playback, not hardware)"
        )
    if not hist:
        return Check(
            "META-CHAIN",
            "ZMQ Interface and Record Node see the same data",
            Category.METADATA,
            True,
            Status.NOT_TESTED,
            "structure.oebin has no channel history (GUI < 0.6?): the signal chain cannot be "
            "checked; values may legitimately differ if a processor sits between the ZMQ "
            "Interface and the Record Node",
            "Parse the channel 'history' of structure.oebin.",
            {"history": hist},
        ), playback
    problems = []
    for h in hist:
        parts = [x.strip() for x in h.split("->")]
        if "ZMQ Interface" not in parts:
            problems.append(f"history {h!r} does not pass through the ZMQ Interface")
            continue
        zi = parts.index("ZMQ Interface")
        between = [x for x in parts[zi + 1 :] if x != "Record Node"]
        if between:
            problems.append(f"processors between ZMQ Interface and Record Node: {between}")
    st = Status.INCONCLUSIVE if problems else Status.PASS
    return Check(
        "META-CHAIN",
        "ZMQ Interface and Record Node see the same data",
        Category.METADATA,
        True,
        st,
        "; ".join(problems) if problems else f"signal chain {hist[0]!r}",
        "Each channel's 'history' in structure.oebin must contain the ZMQ Interface with no "
        "processor between it and the Record Node; otherwise Concord and the file legitimately "
        "carry different values.",
        {"history": hist, "source_processor": stream.source_processor_name},
    ), playback


def _metadata(
    rec: ConcordRecording, stream: OEContinuous
) -> tuple[list[Check], list[int], float, str]:
    p = rec.recording_params
    names_b = rec.channel_labels() or []
    names_r = [c.name for c in stream.channels]
    frame_ch = sorted({f.data.shape[1] for f in rec.frames})
    out: list[Check] = []
    probs = []
    if names_b and len(set(names_r)) == len(names_r):
        chmap = [names_r.index(n) if n in names_r else -1 for n in names_b]
    else:
        chmap = list(range(frame_ch[0] if frame_ch else 0))
        if not names_b:
            probs.append("Concord descriptor lists no channel names")
    if len(frame_ch) != 1:
        probs.append(f"Concord frames have differing channel counts {frame_ch}")
    elif names_b and frame_ch[0] != len(names_b):
        probs.append(f"frames have {frame_ch[0]} channels, descriptor names {len(names_b)}")
    if -1 in chmap:
        probs.append("some Concord channel names are not in the reference")
    subset = len(chmap) < len(names_r)
    ordered = all(b > a for a, b in itertools.pairwise(chmap))
    if not ordered and -1 not in chmap:
        probs.append("Concord channel names are not in the reference order")
    out.append(
        Check(
            "META-CHANNELS",
            "Channel count and channel identities agree",
            Category.METADATA,
            True,
            Status.FAIL if probs else Status.PASS,
            "; ".join(probs)
            if probs
            else (
                f"{len(chmap)} channels"
                + (
                    f" (a selection of the {len(names_r)} recorded)"
                    if subset
                    else ", names identical in order"
                )
            ),
            "Concord channel_names (sent by the ZMQ Interface) must each be a reference "
            "channel_name, in reference order; the ZMQ Interface may send a selection.",
            {"concord_channels": names_b, "reference_channels": names_r, "mapping": chmap},
        )
    )
    rates = sorted({f.rate for f in rec.frames})
    rprob = []
    if rates != [stream.sample_rate]:
        rprob.append(f"frames declare {rates} Hz, reference {stream.sample_rate:g} Hz")
    if p.get("sample_rate_hz") not in (None, stream.sample_rate):
        rprob.append(f"descriptor sample_rate_hz {p.get('sample_rate_hz')}")
    out.append(
        Check(
            "META-RATE",
            "Declared sampling rate agrees",
            Category.METADATA,
            True,
            Status.FAIL if rprob else Status.PASS,
            "; ".join(rprob) if rprob else f"{stream.sample_rate:g} Hz on both sides",
            "sample_rate_hz of every frame and of the descriptor equals the structure.oebin "
            "sample_rate.",
            {
                "reference": stream.sample_rate,
                "concord_frames": rates,
                "concord_descriptor": p.get("sample_rate_hz"),
            },
        )
    )
    units_b = sorted({f.unit for f in rec.frames})
    src_unit = str(p.get("source_unit", "unknown"))
    ref_units = sorted({c.units for c in stream.channels})
    uprob = []
    factor = 1.0
    if units_b == ["uV"]:
        ref_u = ref_units[0].lower() if len(ref_units) == 1 else None
        if ref_u not in UNIT_TO_UV:
            uprob.append(f"Concord reports µV but the reference channel units are {ref_units}")
        else:
            factor = UNIT_TO_UV[ref_u]
        if src_unit.lower() != (ref_u or ""):
            uprob.append(
                f"operator declared the GUI unit as {src_unit!r}, the file says {ref_units}"
            )
        text = (
            f"Concord converted from the operator-declared unit {src_unit!r} to µV; "
            f"reference {ref_units} x bit_volts -> µV x {factor:g}"
        )
    elif units_b == ["arbitrary"]:
        text = (
            f"Concord labels values 'arbitrary' (unit not declared by the operator); "
            f"compared unscaled with the reference in {ref_units} (int16 x bit_volts)"
        )
    else:
        uprob.append(f"Concord frames carry units {units_b}")
        text = "mixed units"
    out.append(
        Check(
            "META-UNITS",
            "Units are interpreted correctly",
            Category.METADATA,
            True,
            Status.FAIL if uprob else Status.PASS,
            "; ".join(uprob)
            if uprob
            else (
                "Concord 'uV' matches the file's units"
                if units_b == ["uV"]
                else "Concord honestly reports 'arbitrary' (the ZMQ protocol carries no unit); "
                "set the unit in Concord to get µV"
            ),
            "If Concord reports µV, the operator-declared unit must equal the structure.oebin "
            "channel units; 'arbitrary' is always a correct label for this protocol.",
            {
                "concord_units": units_b,
                "concord_source_unit": src_unit,
                "reference_units": ref_units,
            },
        )
    )
    return out, chmap, factor, text


def _parse_ttl(value: Any) -> tuple[int, int, int] | None:
    if not isinstance(value, str):
        return None
    m = re.fullmatch(r"line=(\d+) state=(\d+) word=(\d+)", value.strip())
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def _events_check(
    rec: ConcordRecording, oe: OERecording, stream: OEContinuous, frames: list[Frame]
) -> Check:
    ttl = [t for t in oe.ttl if t.folder == stream.folder_name and len(t.sample_numbers)]
    ours = [a for a in rec.annotations if a.label == "ttl"]
    method = (
        "Reference TTL events (events/<stream>/TTL: sample_numbers, states = ±(line+1), "
        "full_words) within the sample range Concord covered are matched with Concord "
        "'ttl' annotations (sample = device_timestamp x rate) on (sample, line, state)."
    )
    if not ttl and not ours:
        return Check(
            "EVENTS",
            "TTL events agree",
            Category.INTEGRITY,
            False,
            Status.NOT_TESTED,
            "no TTL events in either recording (use a pulse generator to test events)",
            method,
            {},
        )
    if not frames:
        return Check(
            "EVENTS",
            "TTL events agree",
            Category.INTEGRITY,
            True,
            Status.NOT_TESTED,
            "no Concord frames",
            method,
            {},
        )
    lo = frames[0].index
    hi = max(f.index + f.n for f in frames)
    rate = stream.sample_rate
    ref: list[tuple[int, int, int]] = []
    for t in ttl:
        for sn, ln, up in zip(t.sample_numbers, t.lines, t.rising, strict=True):
            if lo <= int(sn) < hi:
                ref.append((int(sn), int(ln), 1 if up else 0))
    got: list[tuple[int, int, int]] = []
    unparsed = 0
    for a in ours:
        v = _parse_ttl(a.value)
        if v is None or a.t_dev_ns is None:
            unparsed += 1
            continue
        got.append((round(a.t_dev_ns * rate / 1e9), v[0], v[1]))
    rs, gs = sorted(ref), sorted(got)
    missing = sorted(set(rs) - set(gs))
    extra = sorted(set(gs) - set(rs))
    ev = {
        "reference_events_in_range": len(rs),
        "concord_events": len(gs),
        "missing_in_concord": missing[:20],
        "extra_in_concord": extra[:20],
        "unparsed_concord_annotations": unparsed,
        "sample_range": [lo, hi],
    }
    st = Status.FAIL if missing or extra or unparsed else Status.PASS
    msg = (
        f"{len(rs)} reference TTL events, {len(gs)} in Concord; "
        f"{len(missing)} missing, {len(extra)} extra"
    )
    return Check("EVENTS", "TTL events agree", Category.INTEGRITY, True, st, msg, method, ev)


def _ts_check(frames: list[Frame], rows: list[int | None], stream: OEContinuous) -> Check:
    rate = stream.sample_rate
    bad = []
    n = 0
    for f in frames:
        if f.t_dev_ns is None:
            bad.append({"frame_seq": f.seq, "problem": "no device timestamp"})
            continue
        n += 1
        expect = f.index * 1e9 / rate
        if abs(f.t_dev_ns - expect) > 1.0:
            bad.append(
                {"frame_seq": f.seq, "device_timestamp_ns": f.t_dev_ns, "expected_ns": expect}
            )
    ref_rel: dict[str, Any] = {}
    if stream.timestamps is not None:
        xs, ys = [], []
        for f, r in zip(frames, rows, strict=True):
            if r is not None and f.t_dev_ns is not None:
                xs.append(f.t_dev_ns / 1e9)
                ys.append(float(stream.timestamps[r]) - f.t_dev_ns / 1e9)
        if len(xs) >= 3:
            fit = T.fit_line(np.asarray(xs), np.asarray(ys))
            ref_rel = {
                "reference_minus_concord_median_s": float(np.median(ys)),
                "max_abs_s": float(np.max(np.abs(ys))),
                "drift_ppm": None if fit is None else fit.slope * 1e6,
            }
    ev = {
        "frames": n,
        "mismatches": len(bad),
        "examples": bad[:10],
        "reference_timestamps_npy_vs_concord": ref_rel,
    }
    st = Status.FAIL if bad else (Status.PASS if n else Status.NOT_TESTED)
    msg = (
        f"{len(bad)} frame(s) have device timestamps that are not sample_number / rate"
        if bad
        else f"all {n} frame timestamps equal sample_number / rate"
    )
    if ref_rel:
        msg += (
            f"; reference timestamps.npy minus Concord: median "
            f"{ref_rel['reference_minus_concord_median_s']:.3g} s"
        )
    return Check(
        "TS-AGREE",
        "Timestamps agree with the sample clock",
        Category.TIMING,
        True,
        st,
        msg,
        "Concord device_timestamp_ns must equal round(sample_number / sample_rate x 1e9) "
        "(docs/OPEN_EPHYS.md); the Record Node's timestamps.npy (synchronised seconds) is "
        "compared as an offset/drift (it may be synchronised to another stream).",
        ev,
    )


def _ref_file_check(stream: OEContinuous, crosscheck: dict[str, Any]) -> Check:
    problems = list(stream.problems)
    breaks = T.sample_number_breaks(stream.sample_numbers)
    ev = {
        "problems": problems,
        "sample_numbers": breaks,
        "rows": stream.n,
        "official_reader": crosscheck,
    }
    st = Status.FAIL if problems or stream.n < 2 else Status.PASS
    return Check(
        "REF-FILE",
        "Reference Binary recording is readable and consistent",
        Category.INPUT,
        True,
        st,
        "; ".join(problems) if problems else f"{stream.n} rows x {len(stream.channels)} channels",
        "structure.oebin parsed; continuous.dat size a multiple of channels x 2 bytes; "
        "sample_numbers.npy and timestamps.npy have one entry per row.",
        ev,
    )


def _reader_check(crosscheck: dict[str, Any]) -> Check:
    st = Status(crosscheck.get("status", "not_tested"))
    return Check(
        "REF-READER",
        "Parser agrees with the official Open Ephys reader",
        Category.INPUT,
        st is Status.FAIL,
        st,
        "; ".join(crosscheck.get("problems", []))
        or crosscheck.get("reason")
        or f"identical to {crosscheck.get('reader')}",
        "Load the same recording with open-ephys-python-tools (BinaryRecording) and compare "
        "channel names, bit_volts, sample rate, every sample number, scaled values at three "
        "rows and the TTL event count. Required only if it fails.",
        crosscheck,
    )


def _ref_continuity(stream: OEContinuous) -> Check:
    b = T.sample_number_breaks(stream.sample_numbers)
    if b["jumps"] == 0 and b["regressions"] == 0:
        st, msg = Status.PASS, "sample numbers are contiguous"
    else:
        st = Status.INCONCLUSIVE
        msg = (
            f"the reference has {b['jumps']} sample-number jump(s) ({b['missing_numbers']} "
            f"numbers absent) and {b['regressions']} reset(s)/regression(s): a discontinuity "
            "in the acquisition or recording (e.g. the File Reader looping, a restart)"
        )
    return Check(
        "REF-CONTINUITY",
        "Reference recording is continuous",
        Category.SOURCE,
        False,
        st,
        msg,
        "Differences between successive sample_numbers.npy entries must be exactly 1.",
        b,
    )


def compare_openephys(oe_path: Path, concord_path: Path, opts: OEOptions) -> dict[str, Any]:
    th = opts.thresholds
    oe = load_oe_recording(oe_path)
    rec = load_concord_recording(concord_path)
    equipment = load_equipment(opts.equipment) if opts.equipment else None
    stream, identity = _identity(rec, oe, opts.stream)
    crosscheck = official_crosscheck(oe, stream)
    checks: list[Check] = [
        _ref_file_check(stream, crosscheck),
        _reader_check(crosscheck),
        C.concord_file(rec),
        identity,
    ]
    chain, playback = _chain_check(stream)
    meta, chmap, factor, unit_text = _metadata(rec, stream)
    checks += [chain, *meta]
    nb = len(chmap)
    rate = stream.sample_rate
    bv = np.asarray([c.bit_volts for c in stream.channels], dtype=np.float64)
    samples = stream.samples

    def ref_rows(a: int, b: int) -> NDArray[np.float64]:
        out: NDArray[np.float64] = samples[a:b].astype(np.float64) * bv * factor
        return out

    def clipped(a: int, b: int) -> NDArray[np.bool_]:
        s = samples[a:b]
        out: NDArray[np.bool_] = (s <= INT16_MIN) | (s >= INT16_MAX)
        return out

    frames = [f for f in rec.frames if f.data.shape[1] == nb and -1 not in chmap]
    keys: list[float | int | None] = [f.index for f in frames]
    sn = stream.sample_numbers
    maps = map_by_key(frames, keys, sn, 0.5)
    sn_sorted = np.all(np.diff(sn) > 0) if len(sn) > 1 else True
    for m, k in zip(maps, keys, strict=True):
        if m.row is None and not m.outside and k is not None and sn_sorted:
            j = int(np.searchsorted(sn, k))
            if 0 < j < len(sn) and sn[j] - sn[j - 1] > 1:
                m.in_reference_gap = True
    ref_atol_all = [th.quantisation_steps * b * factor for b in bv]
    atol = [ref_atol_all[j] for j in chmap] if -1 not in chmap else [0.0] * nb
    comp = compare(
        frames,
        maps,
        ref_rows,
        stream.n,
        chmap if -1 not in chmap else [0] * nb,
        atol,
        0.0,
        th.float32_rtol,
        clipped=clipped,
        content_probes=th.content_probe_frames,
        content_window=int(max(10 * rate, 10_000)),
    )
    diag = diagnose(comp, chmap, ref_atol_all, 0.0)
    labels_b = rec.channel_labels() or [str(i) for i in range(nb)]
    labels_r = [c.name for c in stream.channels]

    def key_of(row: int) -> int:
        return int(sn[row])

    tol_text = (
        f"|diff| <= {th.quantisation_steps:g} x bit_volts of the channel "
        f"({sorted(set(bv.tolist()))} µV) — the Record Node's int16 rounding; samples "
        "clipped at the int16 limits are excluded."
    )
    checks += [
        C.overlap(comp, rate, th),
        C.sample_counts(comp),
        C.loss(comp, rate, th, key_of, set()),
        C.duplicates(comp),
        C.extra(comp),
        C.order(frames, comp),
        C.content(comp),
        C.values(comp, tol_text, labels_b),
        C.channel_order(comp, diag, labels_b, labels_r),
        C.scale(comp, diag, unit_text),
        C.loss_reporting(frames, comp, rec.status_events),
        _ts_check(frames, [m.row for m in maps], stream),
        _events_check(rec, oe, stream, frames),
    ]
    if chain.status is Status.INCONCLUSIVE:
        # a processor between the ZMQ Interface and the Record Node changes the data: value
        # differences are expected there and prove nothing either way
        for c in checks:
            if (
                c.id in ("VALUES", "SCALE", "CHANNEL-ORDER", "ALIGN-CONTENT")
                and c.status is Status.FAIL
            ):
                c.status = Status.INCONCLUSIVE
                c.summary += " — not comparable: " + chain.summary
    # source time for the delay analysis: the reference row on the sample clock. Rows keep
    # counting through a sample-number reset (File Reader loop, restart), the GUI's sample
    # numbers do not.
    row_of = {m.frame: m.row for m in maps}
    dev_s: list[float | None] = [
        None if row_of.get(i) is None else float(row_of[i]) / rate  # type: ignore[arg-type]
        for i in range(len(frames))
    ]
    relation = T.ingest_relation(frames, dev_s, None)
    checks.append(C.delay(relation, th, False))
    checks.append(_ref_continuity(stream))
    eq = equipment_check(equipment)
    checks.append(eq)
    verdict = overall(checks)
    overlap_s = comp.overlap_rows() / rate
    if equipment is not None:
        kind = (equipment.get("signal_source") or {}).get("kind")
        if kind in ("file_playback", "software_simulator"):
            playback.append(f"operator declared the source as {kind}")
    scope = evidence_scope(
        protocol="the Open Ephys ZMQ Interface",
        verdict=verdict,
        overlap_s=overlap_s,
        equipment=equipment,
        equipment_ok=eq.status is Status.PASS,
        playback_or_synthetic=playback,
    )
    miss = comp.missing_rows
    summary = {
        "acquisition_protocol": "Open Ephys GUI: ZMQ Interface (reference: Record Node, Binary)",
        "stream": f"{stream.stream_name} from {stream.source_processor_name}",
        "gui_version": oe.gui_version,
        "channels": nb,
        "channel_names": labels_b,
        "sample_rate_hz": rate,
        "reference_samples": stream.n,
        "concord_samples": comp.concord_samples,
        "overlap_s": overlap_s,
        "samples_compared": comp.compared_samples,
        "missing_in_concord": int(miss.size),
        "estimated_loss_fraction": (miss.size / comp.overlap_rows())
        if comp.overlap_rows()
        else None,
        "duplicated_in_concord": comp.duplicated_samples,
        "concord_samples_without_counterpart": comp.unmatched_samples,
        "values_out_of_tolerance": sum(c.n - c.within for c in comp.channels),
        "max_abs_value_diff_uV": max((c.max_abs for c in comp.channels), default=None),
        "concord_ingest_drift_ppm": relation.get("drift_ppm"),
        "excess_delay_max_s": relation.get("excess_delay_max_s"),
        "reference_sample_number_breaks": T.sample_number_breaks(sn)["jumps"]
        + T.sample_number_breaks(sn)["regressions"],
        "result": verdict.value,
    }
    acquisition = {
        "protocol": "Open Ephys ZMQ Interface",
        "reference_software": f"Open Ephys GUI {oe.gui_version} Record Node (Binary format)",
        "reference_recording": str(oe.path),
        "reference_stream": stream.describe(),
        "concord_device": {
            k: rec.device.get(k)
            for k in ("device_id", "display_name", "kind", "adapter", "native_format")
        },
        "concord_recording_params": rec.recording_params,
        "sync_messages": oe.sync_messages,
    }
    inputs = [
        R.file_entry("reference_openephys_recording", oe.path),
        R.file_entry("concord_recording", concord_path),
    ]
    if opts.equipment:
        inputs.append(R.file_entry("equipment_manifest", opts.equipment))
    return R.build(
        protocol="openephys",
        inputs=inputs,
        acquisition=acquisition,
        summary=summary,
        checks=checks,
        thresholds=th,
        limitations=LIMITATIONS,
        scope=scope,
        command=opts.command,
    )
