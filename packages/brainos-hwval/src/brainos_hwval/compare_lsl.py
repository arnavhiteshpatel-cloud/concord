"""Compare a BrainOS LSL recording with an XDF file recorded from the same stream.

Typical setup: one LSL outlet (acquisition software or a test publisher); LabRecorder and
BrainOS each open their own inlet and record at the same time. Both receive the same samples
with the same source timestamps, so every BrainOS sample must be found in the XDF file with
an identical timestamp and identical values (BrainOS converts declared voltage units to µV).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from brainos_hwval import checks as C
from brainos_hwval import report as R
from brainos_hwval import timing as T
from brainos_hwval.brainos_rec import BrainOSRecording, load_brainos_recording
from brainos_hwval.engine import compare, diagnose, map_by_key
from brainos_hwval.model import Category, Check, InputError, Status, Thresholds, overall
from brainos_hwval.scope import equipment_check, evidence_scope, load_equipment
from brainos_hwval.xdf_ref import XDFStream, load_xdf, unit_scales

LSL_ADAPTER_PREFIX = "brainos.lsl@"
SIDECAR_FORMAT = "brainos-hwval.capture/1"

LIMITATIONS = [
    "Both recordings receive the stream through liblsl. A defect that liblsl itself introduced "
    "before either inlet (e.g. in the outlet's buffer) would be invisible to this comparison; "
    "comparing against the acquisition device's own file format closes that gap.",
    "BrainOS stores one source timestamp per frame (its first sample); per-sample timestamps "
    "inside a frame are reconstructed as first + k / nominal rate. The reconstruction error is "
    "reported but BrainOS cannot be checked for per-sample timestamp fidelity.",
    "LSL carries no sequence numbers: a sample lost before both inlets (at the source) appears "
    "as the same gap in both recordings and is reported as a source discontinuity, not as "
    "BrainOS loss.",
    "Absolute ingest latency needs the clock pair measured by `brainos-hwval capture`; "
    "otherwise only delay variation (excess over the best case) and drift are measured.",
    "A software publisher or a file player is not hardware. LSL cannot tell hardware from "
    "playback; the source kind is what the operator declares in the equipment manifest.",
]


@dataclass
class LSLOptions:
    stream: str | None = None
    sidecar: Path | None = None
    equipment: Path | None = None
    thresholds: Thresholds = field(default_factory=Thresholds)
    command: list[str] | None = None


def _identity_from_descriptor(rec: BrainOSRecording) -> dict[str, str | None]:
    d = rec.device
    desc = str(d.get("description", ""))
    disp = str(d.get("display_name", ""))
    out: dict[str, str | None] = {"name": None, "hostname": None, "source_id": None, "type": None}
    m = re.search(
        r"Lab Streaming Layer stream (['\"])(.*?)\1 from (\S+) \(source_id (.*?)\)\.", desc
    )
    if m:
        out["name"], out["hostname"] = m.group(2), m.group(3)
        sid = m.group(4)
        out["source_id"] = None if sid == "not set" else sid
    m2 = re.match(r"LSL · (.*) \(([^()]*)\)", disp)
    if m2:
        out["name"] = out["name"] or m2.group(1)
        out["type"] = m2.group(2)
    p = rec.recording_params
    if isinstance(p.get("stream_type"), str):
        out["type"] = p["stream_type"]
    return out


def _load_sidecar(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InputError(f"capture sidecar not found: {path}") from exc
    except (OSError, ValueError) as exc:
        raise InputError(f"capture sidecar {path}: not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("format") != SIDECAR_FORMAT:
        raise InputError(f"{path}: not a brainos-hwval capture sidecar ({SIDECAR_FORMAT})")
    return data


def _sidecar_signal(sc: dict[str, Any] | None) -> dict[str, Any] | None:
    if not sc:
        return None
    meta = sc.get("source_metadata") or {}
    for s in meta.get("streams", []):
        if isinstance(s, dict) and s.get("role") == "signal":
            return s
    return None


def select_stream(
    streams: list[XDFStream],
    rec: BrainOSRecording,
    sidecar: dict[str, Any] | None,
    choice: str | None,
) -> tuple[XDFStream, Check]:
    numeric = [s for s in streams if s.is_numeric and s.nominal_srate > 0]
    ident = _identity_from_descriptor(rec)
    sig = _sidecar_signal(sidecar)
    listing = [s.describe() for s in streams]
    how = ""
    chosen: XDFStream | None = None
    if choice is not None:
        hits = [
            s
            for s in streams
            if choice in (s.name, str(s.stream_id), s.uid)
            or (s.source_id != "" and choice == s.source_id)
        ]
        if len(hits) != 1:
            raise InputError(
                f"--stream {choice!r} matches {len(hits)} XDF streams; streams in the file: "
                + json.dumps(
                    [{k: d[k] for k in ("stream_id", "name", "type", "source_id")} for d in listing]
                )
            )
        chosen, how = hits[0], f"operator choice --stream {choice!r}"
        if not chosen.is_numeric or chosen.nominal_srate <= 0:
            raise InputError(
                f"XDF stream {chosen.name!r} is not a regularly sampled numeric "
                "stream; it cannot be compared with recording.frame data"
            )
    elif sig and sig.get("uid"):
        hits = [s for s in numeric if s.uid == sig["uid"]]
        if len(hits) == 1:
            chosen, how = hits[0], "same LSL stream uid (capture sidecar)"
    if chosen is None and ident["name"]:
        hits = [
            s
            for s in numeric
            if s.name == ident["name"]
            and (ident["source_id"] is None or s.source_id == ident["source_id"])
            and (ident["hostname"] is None or s.hostname == ident["hostname"])
        ]
        if len(hits) == 1:
            chosen, how = hits[0], "stream name, source_id and host from the BrainOS descriptor"
    if chosen is None:
        n_ch = rec.channel_count
        rates = {f.rate for f in rec.frames}
        hits = [s for s in numeric if s.channel_count == n_ch and s.nominal_srate in rates]
        if len(hits) == 1:
            chosen, how = hits[0], "only stream with the same channel count and rate"
    if chosen is None:
        raise InputError(
            "cannot tell which XDF stream BrainOS recorded; pass --stream NAME. Streams: "
            + json.dumps(
                [
                    {
                        k: d[k]
                        for k in (
                            "stream_id",
                            "name",
                            "type",
                            "source_id",
                            "channel_count",
                            "nominal_srate",
                        )
                    }
                    for d in listing
                ]
            )
        )
    ev: dict[str, Any] = {
        "selected_by": how,
        "xdf_stream": chosen.describe(),
        "brainos_descriptor_identity": ident,
        "sidecar_identity": None
        if sig is None
        else {k: sig.get(k) for k in ("name", "type", "source_id", "hostname", "uid")},
        "streams_in_file": [
            {
                k: d[k]
                for k in (
                    "stream_id",
                    "name",
                    "type",
                    "source_id",
                    "channel_count",
                    "nominal_srate",
                    "samples",
                )
            }
            for d in listing
        ],
    }
    contradictions = []
    if ident["name"] is not None and ident["name"] != chosen.name:
        contradictions.append(f"name {ident['name']!r} vs {chosen.name!r}")
    if ident["source_id"] is not None and ident["source_id"] != chosen.source_id:
        contradictions.append(f"source_id {ident['source_id']!r} vs {chosen.source_id!r}")
    if ident["hostname"] is not None and ident["hostname"] != chosen.hostname:
        contradictions.append(f"host {ident['hostname']!r} vs {chosen.hostname!r}")
    if sig and sig.get("uid") and sig["uid"] != chosen.uid:
        contradictions.append(f"uid {sig['uid']!r} vs {chosen.uid!r}")
    adapter = str(rec.device.get("adapter", ""))
    if not adapter.startswith(LSL_ADAPTER_PREFIX):
        contradictions.append(f"BrainOS recording was made by adapter {adapter!r}, not LSL")
    if contradictions:
        st, msg = Status.FAIL, "BrainOS recorded a different stream: " + "; ".join(contradictions)
    elif sig and sig.get("uid") == chosen.uid:
        st, msg = Status.PASS, f"same LSL outlet (uid {chosen.uid})"
    elif ident["name"] and ident["source_id"] is not None:
        st, msg = Status.PASS, f"same stream name {chosen.name!r}, source_id and host"
    elif ident["name"]:
        st, msg = (
            Status.PASS,
            (f"same stream name {chosen.name!r} and host (the stream has no source_id)"),
        )
    else:
        st, msg = (
            Status.INCONCLUSIVE,
            ("BrainOS recording does not identify its stream; matched by shape only"),
        )
    ev["contradictions"] = contradictions
    return chosen, Check(
        "IDENTITY",
        "Both recordings are of the same LSL stream",
        Category.IDENTITY,
        True,
        st,
        msg,
        "XDF stream chosen by the capture sidecar's uid, else the stream name/source_id/host in "
        "the BrainOS device descriptor, else a unique channel count + rate; then every identity "
        "field available on both sides must agree.",
        ev,
    )


def _labels_brainos(rec: BrainOSRecording) -> list[str]:
    return rec.channel_labels() or []


def metadata_checks(rec: BrainOSRecording, s: XDFStream) -> tuple[list[Check], str, list[float]]:
    out: list[Check] = []
    p = rec.recording_params
    frame_ch = sorted({f.data.shape[1] for f in rec.frames})
    labels_b = _labels_brainos(rec)
    labels_x = [c.label for c in s.channels]
    expected_labels = [c.label or f"ch{c.index}" for c in s.channels] if s.channels else []
    problems = []
    if frame_ch != [s.channel_count]:
        problems.append(f"BrainOS frames have {frame_ch} channels, reference {s.channel_count}")
    if p.get("channel_count") not in (None, s.channel_count):
        problems.append(f"descriptor channel_count {p.get('channel_count')} vs {s.channel_count}")
    label_mismatch = [
        {"index": i, "brainos": b, "reference": x}
        for i, (b, x) in enumerate(zip(labels_b, expected_labels, strict=False))
        if b != x
    ]
    if labels_b and expected_labels and len(labels_b) != len(expected_labels):
        problems.append(f"{len(labels_b)} BrainOS labels vs {len(expected_labels)} in reference")
    if label_mismatch:
        problems.append(f"{len(label_mismatch)} channel label(s) differ")
    out.append(
        Check(
            "META-CHANNELS",
            "Channel count and channel identities agree",
            Category.METADATA,
            True,
            Status.FAIL if problems else Status.PASS,
            "; ".join(problems)
            if problems
            else f"{s.channel_count} channels, labels identical in order",
            "Channel count of every BrainOS frame and of the descriptor equals the XDF "
            "channel_count; the descriptor's channel_labels equal the XDF <channel><label> list in "
            "order (BrainOS names an unlabelled channel 'ch<i>').",
            {
                "reference_labels": labels_x,
                "brainos_labels": labels_b,
                "label_mismatches": label_mismatch[:20],
                "frame_channel_counts": frame_ch,
            },
        )
    )
    rates = sorted({f.rate for f in rec.frames})
    rprob = []
    if rates != [s.nominal_srate]:
        rprob.append(f"frames declare {rates} Hz, reference nominal {s.nominal_srate:g} Hz")
    if p.get("sample_rate_hz") not in (None, s.nominal_srate):
        rprob.append(f"descriptor sample_rate_hz {p.get('sample_rate_hz')}")
    out.append(
        Check(
            "META-RATE",
            "Declared sampling rate agrees",
            Category.METADATA,
            True,
            Status.FAIL if rprob else Status.PASS,
            "; ".join(rprob) if rprob else f"{s.nominal_srate:g} Hz on both sides",
            "sample_rate_hz of every BrainOS frame and of the descriptor equals the XDF "
            "nominal_srate.",
            {
                "reference_nominal_srate": s.nominal_srate,
                "brainos_frame_rates": rates,
                "brainos_descriptor_rate": p.get("sample_rate_hz"),
            },
        )
    )
    fprob = []
    if p.get("channel_format") not in (None, s.channel_format):
        fprob.append(f"channel_format {p.get('channel_format')!r} vs {s.channel_format!r}")
    if p.get("stream_type") not in (None, s.type):
        fprob.append(f"stream type {p.get('stream_type')!r} vs {s.type!r}")
    out.append(
        Check(
            "META-FORMAT",
            "Stream type and sample format agree",
            Category.METADATA,
            True,
            Status.FAIL if fprob else Status.PASS,
            "; ".join(fprob) if fprob else f"{s.type} / {s.channel_format}",
            "Descriptor stream_type and channel_format equal the XDF type and channel_format.",
            {
                "reference": {"type": s.type, "channel_format": s.channel_format},
                "brainos": {
                    "type": p.get("stream_type"),
                    "channel_format": p.get("channel_format"),
                },
            },
        )
    )
    scales, units = unit_scales(s)
    expected_unit = "uV" if scales is not None else "arbitrary"
    units_b = sorted({f.unit for f in rec.frames})
    uprob = []
    if units_b != [expected_unit]:
        uprob.append(
            f"BrainOS labels values {units_b}, but the reference channel units {units} "
            + (
                "are all known voltage units (expected 'uV')"
                if scales is not None
                else "are not all known voltage units (expected 'arbitrary')"
            )
        )
    used_scales = scales if (scales is not None and units_b == ["uV"]) else [1.0] * s.channel_count
    unit_text = (
        f"reference units {units} -> µV factors {scales}"
        if scales is not None
        else f"reference units {units}: not all known voltage units; compared unscaled"
    )
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
                "reference declares voltage units; BrainOS reports µV"
                if expected_unit == "uV"
                else "reference does not declare voltage units for every channel; BrainOS reports "
                "'arbitrary' (no guessing)"
            ),
            "If every XDF channel declares a known voltage unit (microvolts, millivolts, volts, "
            "nanovolts and abbreviations), BrainOS must label frames 'uV' (values converted); "
            "otherwise it must label them 'arbitrary' (values unscaled).",
            {"reference_units": units, "factors_to_uV": scales, "brainos_units": units_b},
        )
    )
    return out, unit_text, used_scales


def provenance_check(rec: BrainOSRecording, s: XDFStream) -> tuple[Check, list[str]]:
    pf = rec.provenance_flags()
    decl = s.declaration
    ref_syn = decl.get("synthetic", "").lower() in {"true", "1", "yes"}
    ref_pre = decl.get("prerecorded", "").lower() in {"true", "1", "yes"}
    problems = []
    if ref_syn and pf["frames_synthetic"] != [True]:
        problems.append("reference declares synthetic data but BrainOS frames are not synthetic")
    if not ref_syn and True in pf["frames_synthetic"]:
        problems.append("BrainOS marks frames synthetic but the reference declares no such thing")
    if ref_pre and pf["frames_replayed"] != [True]:
        problems.append("reference declares prerecorded data but BrainOS frames are not replayed")
    flags = []
    if ref_syn or True in pf["frames_synthetic"] or pf["header_synthetic"]:
        flags.append("the data is declared synthetic")
    if ref_pre or True in pf["frames_replayed"]:
        flags.append("the data is declared prerecorded (replayed)")
    return Check(
        "PROVENANCE",
        "Synthetic / prerecorded declarations are carried through",
        Category.METADATA,
        True,
        Status.FAIL if problems else Status.PASS,
        "; ".join(problems)
        if problems
        else (
            "declarations consistent"
            + (f" ({', '.join(flags)})" if flags else " (none declared: kind 'stream')")
        ),
        "The publisher's optional <desc><brainos><synthetic>/<prerecorded> declarations must "
        "appear as provenance synthetic / replayed on every BrainOS frame, and BrainOS must not "
        "add them on its own.",
        {"reference_declaration": decl or None, "brainos": pf},
    ), flags


def _ref_file_check(s: XDFStream) -> Check:
    ts = s.time_stamps
    vals = s.values
    problems: list[str] = []
    notes: list[str] = []
    if vals is None or vals.shape[0] != len(ts):
        problems.append("sample and timestamp counts differ")
    if vals is not None and vals.dtype.kind == "f" and not np.all(np.isfinite(vals)):
        notes.append(f"{int(np.sum(~np.isfinite(vals)))} non-finite values in the reference")
    fc = s.footer.get("sample_count")
    if fc is None:
        notes.append("no stream footer (recording may have been interrupted)")
    elif fc.isdigit() and int(fc) != len(ts):
        notes.append(
            f"footer sample_count {fc} vs {len(ts)} samples read (LabRecorder footer "
            "count; the samples themselves are authoritative)"
        )
    if len(ts) < 2:
        problems.append(f"only {len(ts)} samples")
    st = Status.FAIL if problems else Status.PASS
    return Check(
        "REF-FILE",
        "Reference XDF stream is readable and consistent",
        Category.INPUT,
        True,
        st,
        "; ".join(problems)
        if problems
        else f"{len(ts)} samples read by pyxdf" + (f" ({'; '.join(notes)})" if notes else ""),
        "pyxdf loads the file (synchronize_clocks=False, dejitter_timestamps=False); sample and "
        "timestamp counts must agree.",
        {
            "samples": len(ts),
            "footer": s.footer,
            "notes": notes,
            "pyxdf_effective_srate": s.pyxdf_effective_srate,
        },
    )


def compare_lsl(xdf_path: Path, brainos_path: Path, opts: LSLOptions) -> dict[str, Any]:
    th = opts.thresholds
    _hdr, streams = load_xdf(xdf_path)
    if not streams:
        raise InputError(f"{xdf_path}: the XDF file contains no streams")
    rec = load_brainos_recording(brainos_path)
    sidecar = _load_sidecar(opts.sidecar)
    equipment = load_equipment(opts.equipment) if opts.equipment else None
    s, identity = select_stream(streams, rec, sidecar, opts.stream)
    checks: list[Check] = [_ref_file_check(s), C.brainos_file(rec), identity]
    meta, unit_text, scales = metadata_checks(rec, s)
    checks += meta
    prov, declared_flags = provenance_check(rec, s)
    checks.append(prov)

    assert s.values is not None
    vals = s.values
    ts = s.time_stamps
    rate = s.nominal_srate
    period = 1.0 / rate
    nch = s.channel_count
    sc = np.asarray(scales, dtype=np.float64)

    def ref_rows(a: int, b: int) -> NDArray[np.float64]:
        out: NDArray[np.float64] = vals[a:b].astype(np.float64) * sc
        return out

    frames = [f for f in rec.frames if f.data.shape[1] == nch]
    keys = [None if f.t_dev_ns is None else f.t_dev_ns / 1e9 for f in frames]
    maps = map_by_key(frames, keys, ts, th.match_fraction_of_period * period)
    gp = T.gaps(ts, rate)
    gap_rows = gp.get("rows", [])
    gap_set = set(gap_rows)
    for m, k in zip(maps, keys, strict=True):
        if m.row is None and not m.outside and k is not None:
            j = int(np.searchsorted(ts, k))
            if j - 1 in gap_set:
                m.in_reference_gap = True
    chmap = list(range(nch))
    atol = [th.value_atol] * nch
    comp = compare(
        frames,
        maps,
        ref_rows,
        len(ts),
        chmap,
        atol,
        th.value_rtol,
        th.float32_rtol,
        content_probes=th.content_probe_frames,
        content_window=int(max(10 * rate, 10_000)),
    )
    diag = diagnose(comp, chmap, atol, th.value_rtol)
    labels_b = _labels_brainos(rec) or [f"ch{i}" for i in range(nch)]
    labels_r = [c.label or f"ch{c.index}" for c in s.channels] or [f"ch{i}" for i in range(nch)]

    def key_of(row: int) -> float:
        return float(ts[row])

    tol_text = (
        f"|diff| <= {th.value_atol:g} + {th.value_rtol:g} x |reference| (reference converted to "
        "BrainOS's unit in float64). Bit-exact values are counted separately ('exact'); a "
        "difference at single-precision level is an expected numerical tolerance."
    )
    checks += [
        C.overlap(comp, rate, th),
        C.sample_counts(comp),
        C.loss(comp, rate, th, key_of, gap_set),
        C.duplicates(comp),
        C.extra(comp),
        C.order(frames, comp),
        C.content(comp),
        C.values(comp, tol_text, labels_b),
        C.channel_order(comp, diag, labels_b, labels_r),
        C.scale(comp, diag, unit_text),
        C.loss_reporting(frames, comp, rec.status_events),
    ]
    checks.append(_timestamp_check(frames, comp, ts, th, rate))
    sig = _sidecar_signal(sidecar)
    w2s = _wall_to_source(sidecar, sig)
    relation = T.ingest_relation(frames, keys, w2s)
    checks.append(C.delay(relation, th, w2s is not None))
    rate_check, rate_ev = _rate_check(frames, keys, ts, gap_rows, rate, th)
    checks.append(rate_check)
    checks.append(_ref_gap_check(gp, comp, frames, ts, rate))
    clock = T.clock_offsets(
        s.clock_times,
        s.clock_values,
        float(ts[0]) if len(ts) else 0.0,
        float(ts[-1]) if len(ts) else 0.0,
    )
    checks.append(_clock_check(clock, relation))
    eq = equipment_check(equipment)
    checks.append(eq)

    verdict = overall(checks)
    overlap_s = comp.overlap_rows() / rate
    playback = [f"{x}" for x in declared_flags]
    if eq.status is Status.PASS and equipment is not None:
        kind = (equipment.get("signal_source") or {}).get("kind")
        if kind in ("file_playback", "software_simulator"):
            playback.append(f"operator declared the source as {kind}")
    scope = evidence_scope(
        protocol="Lab Streaming Layer",
        verdict=verdict,
        overlap_s=overlap_s,
        equipment=equipment,
        equipment_ok=eq.status is Status.PASS,
        playback_or_synthetic=playback,
    )
    miss = comp.missing_rows
    summary = {
        "acquisition_protocol": "Lab Streaming Layer (reference: XDF)",
        "stream": f"{s.name} ({s.type}) on {s.hostname}",
        "channels": nch,
        "channel_labels": labels_r,
        "nominal_rate_hz": rate,
        "effective_rate_reference_hz": rate_ev.get("reference_rate_hz"),
        "effective_rate_brainos_hz": rate_ev.get("brainos_rate_hz"),
        "reference_samples": len(ts),
        "brainos_samples": comp.brainos_samples,
        "overlap_s": overlap_s,
        "samples_compared": comp.compared_samples,
        "missing_in_brainos": int(miss.size),
        "estimated_loss_fraction": (miss.size / comp.overlap_rows())
        if comp.overlap_rows()
        else None,
        "duplicated_in_brainos": comp.duplicated_samples,
        "brainos_samples_without_counterpart": comp.unmatched_samples,
        "values_out_of_tolerance": sum(c.n - c.within for c in comp.channels),
        "max_abs_value_diff": max((c.max_abs for c in comp.channels), default=None),
        "max_timestamp_discrepancy_s": _max_abs([m.key_diff for m in comp.maps]),
        "reference_clock_drift_ppm": clock.get("drift_ppm"),
        "brainos_ingest_drift_ppm": relation.get("drift_ppm"),
        "latency_median_s": relation.get("latency_median_s"),
        "excess_delay_max_s": relation.get("excess_delay_max_s"),
        "reference_discontinuities": gp["gaps"] + gp["regressions"],
        "result": verdict.value,
    }
    acquisition = {
        "protocol": "Lab Streaming Layer",
        "reference_software": "XDF file (LabRecorder or compatible), read with pyxdf",
        "xdf_stream": s.describe(),
        "xdf_file_header": _hdr,
        "brainos_device": {
            k: rec.device.get(k)
            for k in ("device_id", "display_name", "kind", "adapter", "native_format")
        },
        "brainos_recording_note": rec.header.get("note"),
        "brainos_schema_version": rec.header.get("schema_version"),
        "capture_sidecar": None
        if sidecar is None
        else {
            k: sidecar.get(k)
            for k in ("brainos_version", "started_utc", "duration_s", "stop_reason", "host")
        },
    }
    inputs = [
        R.file_entry("reference_xdf", xdf_path),
        R.file_entry("brainos_recording", brainos_path),
    ]
    if opts.sidecar:
        inputs.append(R.file_entry("capture_sidecar", opts.sidecar))
    if opts.equipment:
        inputs.append(R.file_entry("equipment_manifest", opts.equipment))
    return R.build(
        protocol="lsl",
        inputs=inputs,
        acquisition=acquisition,
        summary=summary,
        checks=checks,
        thresholds=th,
        limitations=LIMITATIONS,
        scope=scope,
        command=opts.command,
    )


def _max_abs(xs: list[float | None]) -> float | None:
    v = [abs(x) for x in xs if x is not None]
    return max(v) if v else None


def _timestamp_check(
    frames: list[Any], comp: Any, ts: NDArray[np.float64], th: Thresholds, rate: float
) -> Check:
    diffs = np.asarray([m.key_diff for m in comp.maps if m.key_diff is not None])
    content_moved = [d for d in comp.content.get("disagreements", [])]
    # timestamps BrainOS gave frames that the content places elsewhere
    wrong = []
    for m in comp.maps:
        if m.content_row is not None and m.content_row != m.row:
            f = frames[m.frame]
            if f.t_dev_ns is not None:
                wrong.append(f.t_dev_ns / 1e9 - float(ts[m.content_row]))
    recon = 0.0
    for m in comp.maps[:: max(1, len(comp.maps) // 200)]:
        if m.row is None:
            continue
        f = frames[m.frame]
        b = min(m.row + f.n, len(ts))
        if f.t_dev_ns is None or b - m.row < 2:
            continue
        implied = f.t_dev_ns / 1e9 + np.arange(b - m.row) / rate
        recon = max(recon, float(np.max(np.abs(implied - ts[m.row : b]))))
    ev: dict[str, Any] = {
        "frames_with_timestamp_match": int(diffs.size),
        "max_abs_diff_s": float(np.max(np.abs(diffs))) if diffs.size else None,
        "median_diff_s": float(np.median(diffs)) if diffs.size else None,
        "exact_tolerance_s": th.timestamp_exact_s,
        "frames_whose_timestamp_contradicts_content": len(wrong),
        "content_timestamp_errors_s": wrong[:10],
        "intra_frame_reconstruction_max_error_s": recon,
        "content_disagreements": content_moved,
    }
    if not diffs.size and not wrong:
        return Check(
            "TS-AGREE",
            "Timestamps agree with the reference",
            Category.TIMING,
            True,
            Status.NOT_TESTED,
            "no frame could be placed",
            "—",
            ev,
        )
    worst = float(np.max(np.abs(diffs))) if diffs.size else 0.0
    if wrong:
        st = Status.FAIL
        msg = (
            f"{len(wrong)} frame(s) carry timestamps of other samples (error up to "
            f"{max(abs(w) for w in wrong):.6f} s)"
        )
    elif worst > th.timestamp_exact_s:
        st = Status.FAIL
        msg = f"BrainOS timestamps differ from the source timestamps by up to {worst:.3g} s"
    else:
        st = Status.PASS
        msg = (
            f"first-sample timestamps of {diffs.size} frames equal the source timestamps "
            f"(max |diff| {worst:.2g} s)"
        )
    return Check(
        "TS-AGREE",
        "Timestamps agree with the reference",
        Category.TIMING,
        True,
        st,
        msg,
        "Each BrainOS frame's device_timestamp_ns (source clock) is compared with the XDF raw "
        "timestamp of the sample it maps to; both are copies of the source's timestamps, so "
        f"any difference above {th.timestamp_exact_s:g} s is an error. Frames located by "
        "content at another sample are timestamp errors.",
        ev,
    )


def _rate_check(
    frames: list[Any],
    keys: list[float | None],
    ts: NDArray[np.float64],
    gap_rows: list[int],
    rate: float,
    th: Thresholds,
) -> tuple[Check, dict[str, Any]]:
    ref = T.effective_rate(ts, gap_rows)
    pts = [(f.index, k) for f, k in zip(frames, keys, strict=True) if k is not None]
    bos_rate = None
    if len(pts) >= 3:
        x = np.asarray([p[0] for p in pts], dtype=np.float64)
        y = np.asarray([p[1] for p in pts], dtype=np.float64)
        fit = T.fit_line(x, y)
        bos_rate = 1.0 / fit.slope if fit and fit.slope > 0 else None
    rp = T.ppm(ref.get("rate_hz"), rate)
    ev = {
        "nominal_hz": rate,
        "reference_rate_hz": ref.get("rate_hz"),
        "reference_ppm": rp,
        "brainos_rate_hz": bos_rate,
        "brainos_ppm": T.ppm(bos_rate, rate),
        "reference_segment": ref,
        "advisory_threshold_ppm": th.rate_ppm_advisory,
    }
    if rp is None:
        st, msg = Status.NOT_TESTED, "too few samples to measure the rate"
    elif abs(rp) > th.rate_ppm_advisory:
        st = Status.INCONCLUSIVE
        msg = (
            f"source timestamps imply {ref['rate_hz']:.4f} Hz, {rp:+.0f} ppm from the nominal "
            f"{rate:g} Hz: the source's timestamps or clock do not follow its declared rate"
        )
    else:
        st = Status.PASS
        msg = f"effective rate {ref['rate_hz']:.4f} Hz ({rp:+.1f} ppm from nominal)"
    return Check(
        "RATE-EFFECTIVE",
        "Effective sampling rate matches the nominal rate",
        Category.SOURCE,
        False,
        st,
        msg,
        "Linear fit of the reference's raw timestamps against sample number over the longest "
        "gap-free segment; the same fit over BrainOS frame timestamps vs first_sample_index. "
        "Advisory: this measures the source, not BrainOS.",
        ev,
    ), ev


def _ref_gap_check(
    gp: dict[str, Any], comp: Any, frames: list[Any], ts: NDArray[np.float64], rate: float
) -> Check:
    n = gp["gaps"] + gp["regressions"]
    bos_flagged = sum("dropped_samples" in f.flags for f in frames)
    ev = {
        "reference": {k: v for k, v in gp.items() if k != "rows"},
        "brainos_frames_flagged_dropped_samples": bos_flagged,
    }
    if n == 0:
        st, msg = Status.PASS, "the reference stream is continuous"
    else:
        st = Status.INCONCLUSIVE
        msg = (
            f"the reference itself has {gp['gaps']} gap(s) (~{gp['est_missing']} samples) and "
            f"{gp['regressions']} timestamp regression(s): source or recorder discontinuities"
        )
    return Check(
        "REF-CONTINUITY",
        "Reference stream is continuous",
        Category.SOURCE,
        False,
        st,
        msg,
        "Per-sample XDF timestamps: an interval > 1.5 periods (and > 2 ms beyond one period) is "
        "a gap; a non-increasing timestamp is a regression. Advisory: a discontinuity here is "
        "in the source or in LabRecorder, not in BrainOS.",
        ev,
    )


def _wall_to_source(sidecar: dict[str, Any] | None, sig: dict[str, Any] | None) -> float | None:
    if not sidecar or not sig:
        return None
    pairs = sidecar.get("clock_pairs") or []
    vals = []
    for p in pairs:
        try:
            vals.append(int(p["wall_ns"]) / 1e9 - float(p["lsl_local_clock_s"]))
        except (KeyError, TypeError, ValueError):
            continue
    corr = sig.get("time_correction_s")
    if not vals or not isinstance(corr, int | float):
        return None
    return float(np.median(vals)) + float(corr)


def _clock_check(clock: dict[str, Any], relation: dict[str, Any]) -> Check:
    ev = {"labrecorder_clock_offsets": clock, "brainos_ingest_vs_source": relation}
    if not clock.get("usable"):
        st = Status.NOT_TESTED
        msg = "no usable LabRecorder clock-offset measurements"
        if clock.get("discarded"):
            msg += f" ({clock['discarded']} implausible measurement(s) discarded)"
    else:
        drift = clock.get("drift_ppm")
        msg = (
            f"recorder-source offset median {clock['offset_median_s'] * 1e3:.3f} ms"
            + (f", drift {drift:+.2f} ppm" if drift is not None else "")
            + (
                f"; BrainOS wall clock vs source drift {relation['drift_ppm']:+.2f} ppm"
                if relation.get("drift_ppm") is not None
                else ""
            )
        )
        if clock.get("discarded"):
            msg += f"; {clock['discarded']} implausible measurement(s) discarded"
        st = Status.PASS
    return Check(
        "CLOCKS",
        "Clock offset and drift characterised",
        Category.SOURCE,
        False,
        st,
        msg,
        "Linear fit of LabRecorder's ClockOffset chunks (recorder minus source clock) against "
        "time; separately, BrainOS ingest wall clock minus source time against source time. "
        "Advisory: these characterise the clocks involved; offsets between clock domains are "
        "expected and are not errors.",
        ev,
    )
