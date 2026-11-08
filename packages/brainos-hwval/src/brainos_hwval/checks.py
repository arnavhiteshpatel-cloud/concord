"""Checks shared by the LSL and Open Ephys comparisons.

Each function returns one :class:`Check` with the method used and the evidence. Statuses:
FAIL only for an observed integrity problem; INCONCLUSIVE when the data cannot decide
(too little overlap, a flat signal, unexplained mismatches for a sub-question); NOT_TESTED
when the input lacks what the check needs.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np

from brainos_hwval.brainos_rec import BrainOSRecording, Frame
from brainos_hwval.engine import Comparison, Diagnosis
from brainos_hwval.model import Category, Check, Status, Thresholds

KeyOf = Callable[[int], Any]  # reference row -> its key (timestamp or sample number)


def _runs(rows: np.ndarray[Any, Any]) -> list[tuple[int, int]]:
    if rows.size == 0:
        return []
    breaks = np.flatnonzero(np.diff(rows) != 1)
    starts = np.concatenate([[0], breaks + 1])
    ends = np.concatenate([breaks, [rows.size - 1]])
    return [(int(rows[s]), int(rows[e] - rows[s] + 1)) for s, e in zip(starts, ends, strict=True)]


def brainos_file(rec: BrainOSRecording) -> Check:
    ev: dict[str, Any] = {
        "event_counts": rec.event_counts,
        "frames": len(rec.frames),
        "malformed_lines": len(rec.malformed),
        "malformed_examples": rec.malformed[:5],
        "seq_gaps": len(rec.seq_gaps),
        "seq_gap_examples": rec.seq_gaps[:5],
        "seq_regressions": rec.seq_regressions,
        "contract": rec.contract,
    }
    problems = []
    if not rec.frames:
        problems.append(
            "no recording.frame events (raw frames excluded, or the source delivered only "
            "features): there are no samples to verify"
        )
    if rec.malformed:
        problems.append(f"{len(rec.malformed)} unreadable/invalid line(s)")
    if rec.seq_regressions:
        problems.append(f"{rec.seq_regressions} event(s) out of seq order")
    if rec.seq_gaps:
        missing = sum(b - a for a, b in rec.seq_gaps)
        problems.append(f"{missing} event seq number(s) absent from the file")
    if rec.contract.get("invalid_events"):
        problems.append(f"{rec.contract['invalid_events']} event(s) violate the BrainOS contract")
    status = Status.FAIL if problems else Status.PASS
    summary = (
        "; ".join(problems)
        if problems
        else (
            f"{len(rec.frames)} frames, every line readable, seq contiguous"
            + (", contract-valid" if rec.contract.get("validated") else "")
        )
    )
    return Check(
        "BOS-FILE",
        "BrainOS recording file is complete and well-formed",
        Category.INPUT,
        True,
        status,
        summary,
        "Parse every line; require the brainos.recording/1 header, contiguous envelope seq "
        "numbers (the recorder writes every published event), and — if BrainOS is installed — "
        "validation of every envelope against BrainOS's contract models.",
        ev,
    )


def overlap(comp: Comparison, rate: float, th: Thresholds) -> Check:
    rows = comp.overlap_rows()
    secs = rows / rate if rate > 0 else 0.0
    ev = {
        "overlap_rows": rows,
        "overlap_s": secs,
        "reference_row_span": list(comp.span) if comp.span else None,
        "reference_rows": comp.ref_rows,
        "brainos_samples": comp.brainos_samples,
        "brainos_samples_outside_reference": comp.outside_samples,
        "brainos_samples_past_reference_end": comp.beyond_end_samples,
        "min_overlap_s": th.min_overlap_s,
    }
    if rows == 0:
        st, msg = (
            Status.INCONCLUSIVE,
            (
                "no BrainOS sample could be placed in the reference: the recordings do not overlap "
                "or are not of the same stream/session"
            ),
        )
    elif secs < th.min_overlap_s:
        st, msg = (
            Status.INCONCLUSIVE,
            (f"only {secs:.2f} s overlap (< {th.min_overlap_s:g} s): too short to conclude"),
        )
    else:
        st, msg = Status.PASS, f"{secs:.2f} s of the recordings overlap ({rows} samples)"
    return Check(
        "OVERLAP",
        "Recordings overlap enough to compare",
        Category.INTEGRITY,
        True,
        st,
        msg,
        "Span from the first to the last reference sample that a BrainOS frame maps to. "
        "BrainOS samples before the reference started or after it stopped are not compared "
        "and not counted as errors.",
        ev,
    )


def sample_counts(comp: Comparison) -> Check:
    rows = comp.overlap_rows()
    if comp.span is None:
        return Check(
            "SAMPLE-COUNT",
            "Sample counts agree within the overlap",
            Category.INTEGRITY,
            True,
            Status.NOT_TESTED,
            "no overlap",
            "—",
            {},
        )
    lo, hi = comp.span
    claimed = int(comp.counts[lo:hi].sum())
    ev = {
        "reference_samples_in_overlap": rows,
        "brainos_samples_mapped_into_overlap": claimed,
        "difference": claimed - rows,
        "reference_total": comp.ref_rows,
        "brainos_total": comp.brainos_samples,
    }
    st = Status.PASS if claimed == rows and not comp.missing_rows.size else Status.FAIL
    return Check(
        "SAMPLE-COUNT",
        "Sample counts agree within the overlap",
        Category.INTEGRITY,
        True,
        st,
        f"reference {rows} vs BrainOS {claimed} samples in the overlap",
        "Count reference samples between the first and last BrainOS sample and the BrainOS "
        "samples mapped onto them (each counted once per frame that claims it).",
        ev,
    )


def loss(
    comp: Comparison, rate: float, th: Thresholds, key_of: KeyOf, ref_gap_rows: set[int]
) -> Check:
    miss = comp.missing_rows
    rows = comp.overlap_rows()
    frac = miss.size / rows if rows else 0.0
    runs = _runs(miss)
    # a run of missing rows that starts right after a reference discontinuity is still loss:
    # the reference has those samples and BrainOS does not.
    ev = {
        "missing_samples": int(miss.size),
        "missing_fraction": frac,
        "missing_runs": len(runs),
        "max_loss_fraction": th.max_loss_fraction,
        "runs": [
            {"reference_row": r, "length": n, "key": key_of(r), "duration_s": n / rate}
            for r, n in runs[:10]
        ],
        "estimated_lost_duration_s": miss.size / rate if rate > 0 else None,
    }
    if comp.span is None:
        st, msg = Status.NOT_TESTED, "no overlap"
    elif frac > th.max_loss_fraction:
        st = Status.FAIL
        msg = (
            f"BrainOS is missing {miss.size} reference sample(s) in {len(runs)} run(s) "
            f"({frac:.3g} of the overlap)"
        )
    else:
        st = Status.PASS
        msg = (
            "no reference sample is missing from BrainOS"
            if not miss.size
            else f"{miss.size} missing sample(s), within the allowed {th.max_loss_fraction:g}"
        )
    return Check(
        "LOSS",
        "No samples missing in BrainOS",
        Category.INTEGRITY,
        True,
        st,
        msg,
        "Reference samples inside the overlap that no BrainOS frame maps to.",
        ev,
    )


def duplicates(comp: Comparison) -> Check:
    d = comp.duplicated_samples
    rows = np.flatnonzero(comp.counts > 1)
    ev = {
        "duplicated_samples": d,
        "runs": [{"reference_row": r, "length": n} for r, n in _runs(rows)[:10]],
    }
    return Check(
        "DUPLICATES",
        "No duplicated samples in BrainOS",
        Category.INTEGRITY,
        True,
        Status.FAIL if d else Status.PASS,
        f"{d} reference sample(s) appear more than once in BrainOS" if d else "none",
        "Reference samples claimed by more than one BrainOS frame.",
        ev,
    )


def extra(comp: Comparison) -> Check:
    n = comp.unmatched_samples
    unmatched = [m for m in comp.maps if m.row is None and not m.outside]
    in_gap = [m for m in unmatched if m.in_reference_gap]
    ev = {
        "brainos_samples_without_counterpart": n,
        "frames": len(unmatched),
        "frames_inside_a_reference_gap": len(in_gap),
        "content_found_elsewhere": sum(1 for m in unmatched if m.content_row is not None),
    }
    if n == 0:
        st, msg = Status.PASS, "every BrainOS sample in the reference's range has a counterpart"
    elif len(in_gap) == len(unmatched):
        st = Status.INCONCLUSIVE
        msg = (
            f"{n} BrainOS sample(s) fall inside gaps of the reference recording: the reference "
            "is incomplete there, so they cannot be verified"
        )
    else:
        st = Status.FAIL
        msg = (
            f"{n} BrainOS sample(s) inside the reference's range match no reference sample "
            "(timestamps/indices that do not exist in the source)"
        )
    return Check(
        "EXTRA",
        "No BrainOS samples without a reference counterpart",
        Category.INTEGRITY,
        True,
        st,
        msg,
        "BrainOS frames whose first-sample key lies within the reference's range but matches "
        "no reference sample.",
        ev,
    )


def order(frames: Sequence[Frame], comp: Comparison) -> Check:
    """Frames must follow the source order.

    Where both frames map onto the reference, the reference rows decide (a sample-number reset
    in the source is followed by BrainOS's index too, and is not a BrainOS reordering); where
    a frame could not be mapped, its first_sample_index must not go backwards.
    """
    rows = {m.frame: m.row for m in comp.maps}
    back = overlap_n = idx_back = 0
    ex: list[dict[str, Any]] = []
    for i in range(1, len(frames)):
        a, b = frames[i - 1], frames[i]
        ra, rb = rows.get(i - 1), rows.get(i)
        if ra is not None and rb is not None:
            if rb < ra:
                back += 1
                if len(ex) < 5:
                    ex.append({"frame_seq": b.seq, "row": rb, "previous_row": ra})
            elif rb < ra + a.n:
                overlap_n += 1
        elif b.index < a.index + a.n:
            idx_back += 1
            if len(ex) < 5:
                ex.append({"frame_seq": b.seq, "index": b.index, "previous_index": a.index})
    ev = {
        "frames_mapped_before_their_predecessor": back,
        "frames_overlapping_predecessor": overlap_n,
        "unmapped_frames_with_index_regression": idx_back,
        "examples": ex,
    }
    st = Status.FAIL if back or idx_back else Status.PASS
    return Check(
        "ORDER",
        "BrainOS frames are in source order",
        Category.INTEGRITY,
        True,
        st,
        "frames out of order" if st is Status.FAIL else "frames in source order",
        "Successive frames (in recording order) must map to increasing reference rows; a frame "
        "that cannot be mapped must not have a smaller first_sample_index than its predecessor.",
        ev,
    )


def content(comp: Comparison) -> Check:
    c = comp.content
    ev = dict(c)
    if not c.get("probed"):
        st, msg = Status.NOT_TESTED, "no frames to probe"
    elif c.get("disagree"):
        st = Status.FAIL
        msg = (
            f"{c['disagree']} of {c['probed']} probed frames carry data found at a different "
            "position than their timestamp/index says"
        )
    elif c.get("agree", 0) == 0:
        st = Status.INCONCLUSIVE
        msg = (
            "the data could not be located by content (signal too uniform or values differ): "
            "alignment rests on timestamps/indices alone"
        )
    else:
        st = Status.PASS
        msg = (
            f"{c['agree']} probed frame(s) found by content exactly where their "
            f"timestamps/indices place them"
            + (f"; {c['ambiguous']} ambiguous" if c.get("ambiguous") else "")
        )
    return Check(
        "ALIGN-CONTENT",
        "Alignment confirmed by signal content (independent of timestamps)",
        Category.INTEGRITY,
        True,
        st,
        msg,
        "For evenly spaced frames (and every frame the key could not place), search the "
        "reference values for the frame's first 16 samples on all channels; compare the row "
        "found with the row given by the frame's timestamp / sample number.",
        ev,
    )


def values(comp: Comparison, tolerance_text: str, labels: Sequence[str]) -> Check:
    chans = [
        c.to_json() | {"channel": labels[i] if i < len(labels) else str(i)}
        for i, c in enumerate(comp.channels)
    ]
    n = comp.compared_samples
    bad = sum(c.n - c.within for c in comp.channels)
    exact = sum(c.exact for c in comp.channels)
    total = sum(c.n for c in comp.channels)
    f32_only = sum(c.within_f32 - c.exact for c in comp.channels)
    ev = {
        "tolerance": tolerance_text,
        "values_compared": total,
        "values_exactly_equal": exact,
        "values_out_of_tolerance": bad,
        "max_abs_diff": max((c.max_abs for c in comp.channels), default=None),
        "per_channel": chans,
        "examples": comp.examples,
    }
    clipped = sum(c.excluded_clipped for c in comp.channels)
    ev["values_excluded_clipped_in_reference"] = clipped
    if n == 0:
        st, msg = Status.NOT_TESTED, "no samples compared"
    elif bad:
        st = Status.FAIL
        msg = f"{bad} of {total} values differ beyond the expected tolerance"
    elif clipped > 0.01 * (total + clipped):
        st = Status.INCONCLUSIVE
        msg = (
            f"{clipped} of {total + clipped} reference values are clipped at the int16 "
            "limits and cannot be compared (reduce the gain or the input amplitude)"
        )
    else:
        st = Status.PASS
        msg = (
            f"all {total} values agree ({exact} bit-exact"
            + (f", {f32_only} within single precision" if f32_only > 0 else "")
            + ")"
        )
    return Check(
        "VALUES",
        "Signal values agree within the expected numerical tolerance",
        Category.INTEGRITY,
        True,
        st,
        msg,
        "Every BrainOS sample is compared with the reference sample it maps to, channel by "
        "channel: |brainos - reference| <= tolerance. " + tolerance_text,
        ev,
    )


def channel_order(
    comp: Comparison, diag: Diagnosis, labels_b: Sequence[str], labels_r: Sequence[str]
) -> Check:
    bad = sum(c.n - c.within for c in comp.channels)
    ev: dict[str, Any] = {"best_matches": diag.match_matrix_best}
    if diag.permutation:
        pairs = []
        for i, j in sorted(diag.permutation.items()):
            pairs.append(
                {
                    "brainos_channel": i,
                    "brainos_label": labels_b[i] if i < len(labels_b) else None,
                    "carries_reference_channel": j,
                    "reference_label": labels_r[j] if j < len(labels_r) else None,
                }
            )
        ev["permutation"] = pairs
        follows = all(
            p["brainos_label"] == p["reference_label"]
            for p in pairs
            if p["brainos_label"] is not None
        )
        ev["labels_follow_data"] = follows
        return Check(
            "CHANNEL-ORDER",
            "Channels are in the reference order",
            Category.INTEGRITY,
            True,
            Status.FAIL,
            f"{len(pairs)} BrainOS channel(s) carry another reference channel's data"
            + (" (labels follow the data)" if follows else " (labels do NOT follow the data)"),
            "Every BrainOS channel is matched against every reference channel on a thin, evenly "
            "spaced sample (fraction of values within tolerance); a channel that matches "
            "another reference channel >= 99 % and its own < 50 % is reported as swapped.",
            ev,
        )
    if comp.compared_samples == 0:
        st, msg = Status.NOT_TESTED, "no samples compared"
    elif bad == 0:
        st, msg = Status.PASS, "every channel matches its reference channel"
    else:
        st, msg = Status.INCONCLUSIVE, "values differ, but not as a channel permutation"
    return Check(
        "CHANNEL-ORDER",
        "Channels are in the reference order",
        Category.INTEGRITY,
        True,
        st,
        msg,
        "Every BrainOS channel is matched against every reference channel on a thin sample.",
        ev,
    )


def scale(comp: Comparison, diag: Diagnosis, unit_text: str) -> Check:
    bad = sum(c.n - c.within for c in comp.channels)
    ev: dict[str, Any] = {"unit_interpretation": unit_text}
    if diag.scale or diag.offset:
        ev["scale_factors"] = {str(k): v for k, v in diag.scale.items()}
        ev["offsets"] = {str(k): v for k, v in diag.offset.items()}
        if diag.unit_factor:
            msg = (
                f"BrainOS values are {diag.unit_factor:g} x the reference on "
                f"{len(diag.scale)} channel(s): a unit conversion error"
            )
        elif diag.scale:
            msg = f"{len(diag.scale)} channel(s) scaled by a factor other than 1"
        else:
            msg = f"{len(diag.offset)} channel(s) offset by a constant"
        ev["unit_factor"] = diag.unit_factor
        return Check(
            "SCALE",
            "Scaling and units are correct",
            Category.INTEGRITY,
            True,
            Status.FAIL,
            msg,
            "Per channel, least-squares factor through the origin between BrainOS "
            "and reference values on a thin sample; exact proportionality with a "
            "factor != 1 is a scaling error (a power of ten: a unit error); a constant "
            "difference is an offset.",
            ev,
        )
    if comp.compared_samples == 0:
        st, msg = Status.NOT_TESTED, "no samples compared"
    elif bad == 0:
        st, msg = Status.PASS, "values equal the reference in the stated unit (factor 1)"
    else:
        st, msg = Status.INCONCLUSIVE, "values differ, but not by a constant factor or offset"
    return Check(
        "SCALE",
        "Scaling and units are correct",
        Category.INTEGRITY,
        True,
        st,
        msg,
        "Least-squares factor per channel on a thin sample.",
        ev,
    )


def loss_reporting(
    frames: Sequence[Frame], comp: Comparison, statuses: Sequence[dict[str, Any]] = ()
) -> Check:
    """Did BrainOS report every loss it suffered?

    A loss counts as reported if the first frame after it carries the quality flag
    dropped_samples, or if BrainOS published a device.status event (e.g. reconnecting) between
    the frames before and after it.
    """
    miss = comp.missing_rows
    runs = _runs(miss)
    mapped = sorted((m.row, m.frame) for m in comp.maps if m.row is not None)
    rows = np.asarray([r for r, _ in mapped], dtype=np.int64)
    status_seqs = sorted(int(s["seq"]) for s in statuses)
    silent = []
    by_status = by_flag = 0
    for r, n in runs:
        k = int(np.searchsorted(rows, r + n, side="left"))
        if k >= len(mapped):
            continue
        f = frames[mapped[k][1]]
        prev_seq = frames[mapped[k - 1][1]].seq if k > 0 else -1
        between = [q for q in status_seqs if prev_seq < q < f.seq]
        if "dropped_samples" in f.flags:
            by_flag += 1
        elif between:
            by_status += 1
        else:
            silent.append({"reference_row": r, "length": n, "next_frame_seq": f.seq})
    flagged = sum("dropped_samples" in f.flags for f in frames)
    ev = {
        "loss_runs": len(runs),
        "reported_by_frame_flag": by_flag,
        "reported_by_device_status": by_status,
        "unreported_runs": len(silent),
        "unreported_examples": silent[:10],
        "frames_flagged_dropped_samples": flagged,
        "device_status_events": [
            {"seq": s["seq"], **{k: s["payload"].get(k) for k in ("state", "detail")}}
            for s in list(statuses)[:20]
        ],
    }
    if not runs:
        st = Status.PASS
        msg = "no loss to report" + (f" ({flagged} frame(s) flagged anyway)" if flagged else "")
    elif silent:
        st = Status.FAIL
        msg = f"{len(silent)} of {len(runs)} loss run(s) were not reported by BrainOS (silent loss)"
    else:
        st = Status.PASS
        msg = (
            f"all {len(runs)} loss run(s) were reported ({by_flag} by the dropped_samples flag, "
            f"{by_status} by a device.status event)"
        )
    return Check(
        "LOSS-FLAGGED",
        "BrainOS reported every loss it suffered",
        Category.INTEGRITY,
        True,
        st,
        msg,
        "For each run of samples missing in BrainOS, the next BrainOS frame must carry the "
        "quality flag dropped_samples, or a device.status event (reconnecting, ...) must lie "
        "between the frames around the gap.",
        ev,
    )


def delay(relation: dict[str, Any], th: Thresholds, absolute: bool) -> Check:
    if relation.get("frames", 0) < 3:
        return Check(
            "DELAY",
            "Data was not delayed beyond the threshold",
            Category.TIMING,
            True,
            Status.NOT_TESTED,
            "no frames with device timestamps",
            "—",
            relation,
        )
    ex = float(relation["excess_delay_max_s"])
    st = Status.FAIL if ex > th.max_excess_delay_s else Status.PASS
    msg = (
        f"worst excess ingest delay {ex * 1000:.1f} ms (median "
        f"{relation['excess_delay_median_s'] * 1000:.1f} ms) vs threshold "
        f"{th.max_excess_delay_s * 1000:.0f} ms"
    )
    if absolute and "latency_median_s" in relation:
        msg += f"; absolute latency median {relation['latency_median_s'] * 1000:.1f} ms"
    return Check(
        "DELAY",
        "Data was not delayed beyond the threshold",
        Category.TIMING,
        True,
        st,
        msg,
        "BrainOS ingest wall clock minus the source time of each frame's last sample; the "
        "excess over the smallest observed value is the variable delay (buffering, "
        "transport, stalls)."
        + (
            " Absolute latency uses the clock pair measured by `brainos-hwval capture`."
            if absolute
            else " Without a measured clock pair, absolute latency is unknown."
        ),
        relation,
    )
