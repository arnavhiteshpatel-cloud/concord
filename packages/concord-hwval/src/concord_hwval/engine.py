"""Protocol-independent sample comparison between a reference recording and Concord frames.

The reference is an array of rows (one row per sample, all channels) with a *key* per row:
the source timestamp in seconds (LSL / XDF) or the acquisition sample number (Open Ephys).
Each Concord frame carries the key of its first sample and ``n`` contiguous samples.

1. **Key mapping.** Each frame's first-sample key is looked up in the reference (exact for
   sample numbers, within a tolerance for timestamps); the frame then claims reference rows
   ``r .. r+n-1``.
2. **Content mapping** (independent of keys). For a spread of frames, and for every frame the
   key could not place, the frame's first samples are searched for in the reference values.
   Agreement of both mappings shows that keys and data belong together; disagreement shows
   where Concord's timestamps/indices are wrong even when the data itself is intact.
3. **Coverage.** Counting how often each reference row is claimed gives samples missing in
   Concord (count 0 inside the overlap), duplicated (count > 1) and Concord samples with no
   counterpart in the reference.
4. **Values.** Claimed rows are compared channel by channel with an explicit tolerance;
   mismatches are diagnosed as channel permutation, scale/unit error, offset, or corruption.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from numpy.typing import NDArray

from concord_hwval.concord_rec import Frame

RefRows = Callable[[int, int], NDArray[np.float64]]  # rows [a, b) of all reference channels
MAX_EXAMPLES = 10
SAMPLE_ROWS = 4000  # rows kept for permutation / scale diagnosis


@dataclass
class FrameMap:
    frame: int  # index into frames
    row: int | None  # reference row of the frame's first sample (key mapping)
    key_diff: float | None  # frame key minus reference key at ``row``
    outside: bool = False  # key outside the reference's range (not an error)
    in_reference_gap: bool = False  # key falls in a discontinuity of the reference itself
    content_row: int | None = None
    content_checked: bool = False
    content_ambiguous: bool = False


@dataclass
class ChannelStats:
    n: int = 0
    exact: int = 0
    within: int = 0
    within_f32: int = 0
    excluded_clipped: int = 0
    max_abs: float = 0.0
    sumsq: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            "compared": self.n,
            "exact": self.exact,
            "within_tolerance": self.within,
            "within_float32": self.within_f32,
            "out_of_tolerance": self.n - self.within,
            "excluded_clipped_in_reference": self.excluded_clipped,
            "max_abs_diff": self.max_abs,
            "rms_diff": math.sqrt(self.sumsq / self.n) if self.n else None,
        }


@dataclass
class Comparison:
    ref_rows: int
    frames: int
    concord_samples: int
    maps: list[FrameMap]
    counts: NDArray[np.int32]
    span: tuple[int, int] | None  # reference rows [lo, hi) between first and last Concord sample
    outside_samples: int  # Concord samples before/after the reference
    unmatched_samples: int  # Concord samples inside the reference range with no counterpart
    beyond_end_samples: int  # mapped frames that run past the reference's last row
    channels: list[ChannelStats]
    examples: list[dict[str, Any]]
    sample_concord: NDArray[np.float64]  # (rows, concord channels)
    sample_ref: NDArray[np.float64]  # (rows, all reference channels)
    content: dict[str, Any] = field(default_factory=dict)

    @property
    def missing_rows(self) -> NDArray[np.intp]:
        if self.span is None:
            return np.zeros(0, dtype=np.intp)
        lo, hi = self.span
        return np.flatnonzero(self.counts[lo:hi] == 0) + lo

    @property
    def duplicated_samples(self) -> int:
        return int(np.sum(np.clip(self.counts.astype(np.int64) - 1, 0, None)))

    @property
    def compared_samples(self) -> int:
        return max((c.n for c in self.channels), default=0)

    def overlap_rows(self) -> int:
        return 0 if self.span is None else self.span[1] - self.span[0]


def map_by_key(
    frames: Sequence[Frame],
    frame_keys: Sequence[float | int | None],
    ref_keys: NDArray[Any],
    tol: float,
) -> list[FrameMap]:
    """Map each frame's first sample to a reference row whose key is within ``tol``.

    Reference keys need not be monotonic (e.g. a sample-number reset): candidates are taken
    from a sorted view and the one at or after the previous frame's end is preferred.
    """
    order = np.argsort(ref_keys, kind="stable")
    sorted_keys = ref_keys[order]
    lo_key = sorted_keys[0] if len(sorted_keys) else None
    hi_key = sorted_keys[-1] if len(sorted_keys) else None
    out: list[FrameMap] = []
    cursor = 0
    for i, (f, k) in enumerate(zip(frames, frame_keys, strict=True)):
        if k is None or lo_key is None or hi_key is None:
            out.append(FrameMap(i, None, None))
            continue
        a = int(np.searchsorted(sorted_keys, k - tol, side="left"))
        b = int(np.searchsorted(sorted_keys, k + tol, side="right"))
        cands = order[a:b]
        if len(cands) == 0:
            outside = bool(k < lo_key - tol or k > hi_key + tol)
            out.append(FrameMap(i, None, None, outside=outside))
            continue
        diffs = np.abs(ref_keys[cands].astype(np.float64) - float(k))
        best = float(diffs.min())
        tied = cands[diffs <= best + 1e-12]
        after = tied[tied >= cursor]
        row = int(after.min() if len(after) else tied.min())
        cursor = row + f.n
        out.append(FrameMap(i, row, float(k) - float(ref_keys[row])))
    return out


def _within(
    ours: NDArray[np.float64], ref: NDArray[np.float64], atol: NDArray[np.float64], rtol: float
) -> NDArray[np.bool_]:
    return np.abs(ours - ref) <= atol + rtol * np.abs(ref)


def locate_by_content(
    block: NDArray[np.float64],
    ref_rows: RefRows,
    n_rows: int,
    atol: NDArray[np.float64],
    rtol: float,
    chmap: NDArray[np.intp],
    hint: int | None,
    window: int,
    probe: int = 16,
    chunk: int = 1_000_000,
) -> list[int]:
    """Reference rows where the first ``probe`` samples of ``block`` occur (all channels)."""
    probe = min(probe, block.shape[0])
    head = block[:probe]

    def search(lo: int, hi: int) -> list[int]:
        found: list[int] = []
        start = max(lo, 0)
        stop = min(hi, n_rows)
        while start < stop and len(found) < 50:
            end = min(stop, start + chunk)
            ref = ref_rows(start, min(end + probe, n_rows))[:, chmap]
            if ref.shape[0] == 0:
                break
            first = np.all(_within(head[0][None, :], ref[: end - start], atol, rtol), axis=1)
            for c in np.flatnonzero(first)[:200]:
                seg = ref[c : c + probe]
                if seg.shape[0] == probe and np.all(_within(head, seg, atol, rtol)):
                    found.append(start + int(c))
            start = end
        return found

    if hint is not None:
        near = search(hint - window, hint + window)
        if near:
            return near
    return search(0, n_rows)


def compare(
    frames: Sequence[Frame],
    maps: list[FrameMap],
    ref_rows: RefRows,
    n_rows: int,
    chmap: Sequence[int],
    atol: Sequence[float],
    rtol: float,
    float32_rtol: float,
    clipped: Callable[[int, int], NDArray[np.bool_]] | None = None,
    content_probes: int = 24,
    content_window: int = 200_000,
) -> Comparison:
    cm = np.asarray(chmap, dtype=np.intp)
    at = np.asarray(atol, dtype=np.float64)
    nb = len(cm)
    counts = np.zeros(n_rows, dtype=np.int32)
    stats = [ChannelStats() for _ in range(nb)]
    examples: list[dict[str, Any]] = []
    total = sum(f.n for f in frames)
    step = max(1, total // SAMPLE_ROWS)
    sb: list[NDArray[np.float64]] = []
    sr: list[NDArray[np.float64]] = []
    outside = unmatched = beyond = 0
    first_row: int | None = None
    last_row: int | None = None
    seen = 0
    for m in maps:
        f = frames[m.frame]
        if m.row is None:
            if m.outside:
                outside += f.n
            else:
                unmatched += f.n
            seen += f.n
            continue
        a = m.row
        b = min(a + f.n, n_rows)
        beyond += a + f.n - b
        if b <= a:
            seen += f.n
            continue
        counts[a:b] += 1
        first_row = a if first_row is None else min(first_row, a)
        last_row = b if last_row is None else max(last_row, b)
        ref_all = ref_rows(a, b)
        ref = ref_all[:, cm]
        ours = f.data[: b - a]
        if ours.shape[1] != nb:
            unmatched += f.n
            continue
        clip = clipped(a, b)[:, cm] if clipped is not None else None
        diff = np.abs(ours - ref)
        tol = at + rtol * np.abs(ref)
        ok = diff <= tol
        f32 = diff <= at + float32_rtol * np.abs(ref)
        exact = diff == 0
        for c in range(nb):
            keep = slice(None) if clip is None else ~clip[:, c]
            d = diff[keep, c]
            st = stats[c]
            if clip is not None:
                st.excluded_clipped += int(clip[:, c].sum())
            st.n += int(d.size)
            st.exact += int(exact[keep, c].sum())
            st.within += int(ok[keep, c].sum())
            st.within_f32 += int(f32[keep, c].sum())
            if d.size:
                st.max_abs = max(st.max_abs, float(d.max()))
                st.sumsq += float(np.dot(d, d))
        bad = ~ok if clip is None else (~ok & ~clip)
        if bad.any() and len(examples) < MAX_EXAMPLES:
            rows, cols = np.nonzero(bad)
            for r, c in zip(rows[:MAX_EXAMPLES], cols[:MAX_EXAMPLES], strict=True):
                if len(examples) >= MAX_EXAMPLES:
                    break
                examples.append(
                    {
                        "frame_seq": f.seq,
                        "concord_sample_index": f.index + int(r),
                        "reference_row": a + int(r),
                        "channel": int(c),
                        "reference_channel": int(cm[c]),
                        "reference_value": float(ref[r, c]),
                        "concord_value": float(ours[r, c]),
                    }
                )
        # keep a thin, evenly spaced sample for permutation / scale diagnosis
        idx = np.arange((-seen) % step, b - a, step)
        if idx.size:
            sb.append(ours[idx])
            sr.append(ref_all[idx])
        seen += f.n
    span = None if first_row is None or last_row is None else (first_row, last_row)
    ref_ch = ref_rows(0, min(1, n_rows)).shape[1] if n_rows else nb
    comp = Comparison(
        ref_rows=n_rows,
        frames=len(frames),
        concord_samples=total,
        maps=maps,
        counts=counts,
        span=span,
        outside_samples=outside,
        unmatched_samples=unmatched,
        beyond_end_samples=beyond,
        channels=stats,
        examples=examples,
        sample_concord=np.vstack(sb) if sb else np.zeros((0, nb)),
        sample_ref=np.vstack(sr) if sr else np.zeros((0, ref_ch)),
    )
    comp.content = _content_mapping(
        frames, maps, ref_rows, n_rows, cm, at, rtol, content_probes, content_window
    )
    return comp


def _content_mapping(
    frames: Sequence[Frame],
    maps: list[FrameMap],
    ref_rows: RefRows,
    n_rows: int,
    cm: NDArray[np.intp],
    at: NDArray[np.float64],
    rtol: float,
    probes: int,
    window: int,
) -> dict[str, Any]:
    if not frames or n_rows == 0:
        return {"probed": 0}
    mapped = [m for m in maps if m.row is not None]
    unmapped = [m for m in maps if m.row is None and not m.outside]
    chosen: list[FrameMap] = []
    if mapped:
        idx = np.unique(np.linspace(0, len(mapped) - 1, num=min(probes, len(mapped))).astype(int))
        chosen = [mapped[i] for i in idx]
    chosen += unmapped[:50]
    agree = disagree = absent = ambiguous = 0
    disagreements: list[dict[str, Any]] = []
    last_hint: int | None = None
    for m in chosen:
        f = frames[m.frame]
        if f.data.shape[1] != len(cm):
            continue
        hint = m.row if m.row is not None else last_hint
        rows = locate_by_content(f.data, ref_rows, n_rows, at, rtol, cm, hint, window)
        m.content_checked = True
        if not rows:
            absent += 1
            continue
        if len(rows) > 1:
            m.content_ambiguous = True
            ambiguous += 1
            if m.row is not None and m.row in rows:
                m.content_row = m.row
                agree += 1
            continue
        m.content_row = rows[0]
        last_hint = rows[0]
        if m.row == rows[0]:
            agree += 1
        else:
            disagree += 1
            if len(disagreements) < MAX_EXAMPLES:
                disagreements.append(
                    {
                        "frame_seq": f.seq,
                        "concord_sample_index": f.index,
                        "row_by_key": m.row,
                        "row_by_content": rows[0],
                        "offset_rows": None if m.row is None else rows[0] - m.row,
                    }
                )
    return {
        "probed": len(chosen),
        "probed_mapped_by_key": min(len(mapped), probes),
        "probed_unmapped": min(len(unmapped), 50),
        "agree": agree,
        "disagree": disagree,
        "not_found": absent,
        "ambiguous": ambiguous,
        "disagreements": disagreements,
    }


@dataclass
class Diagnosis:
    permutation: dict[int, int]  # Concord channel -> reference channel (where not as mapped)
    scale: dict[int, float]  # Concord channel -> fitted factor (where not 1)
    unit_factor: float | None  # common power-of-ten factor, if all scaled channels share it
    offset: dict[int, float]
    match_matrix_best: list[dict[str, Any]]


def diagnose(
    comp: Comparison, chmap: Sequence[int], ref_atol: Sequence[float], rtol: float
) -> Diagnosis:
    """Explain out-of-tolerance channels from the thin sample kept by :func:`compare`.

    ``ref_atol`` is the absolute tolerance of each *reference* channel.
    """
    b = comp.sample_concord
    r = comp.sample_ref
    nb = b.shape[1]
    perm: dict[int, int] = {}
    scale: dict[int, float] = {}
    offset: dict[int, float] = {}
    best_list: list[dict[str, Any]] = []
    if b.shape[0] < 8 or r.shape[1] != len(ref_atol):
        return Diagnosis(perm, scale, None, offset, best_list)
    ra = np.asarray(ref_atol, dtype=np.float64)
    for i in range(nb):
        j0 = int(chmap[i])
        tol_i = float(ra[j0])
        fr = np.mean(np.abs(b[:, [i]] - r) <= ra[None, :] + rtol * np.abs(r), axis=0)
        jbest = int(np.argmax(fr))
        best_list.append(
            {
                "channel": i,
                "expected_ref": j0,
                "best_ref": jbest,
                "match_best": float(fr[jbest]),
                "match_expected": float(fr[j0]),
            }
        )
        if jbest != j0 and fr[jbest] >= 0.99 and fr[j0] < 0.5:
            perm[i] = jbest
            continue
        if fr[j0] >= 0.999:
            continue
        x = r[:, j0]
        y = b[:, i]
        if np.ptp(x) == 0:
            continue
        xx = float(np.dot(x, x))
        k = float(np.dot(x, y) / xx) if xx > 0 else float("nan")
        slack = tol_i + max(rtol, 1e-6) * np.abs(x)
        if math.isfinite(k) and k != 0 and np.all(np.abs(y / k - x) <= 1.05 * slack + 1e-12):
            if abs(k - 1.0) > 1e-6:
                scale[i] = k
            continue
        d = y - x
        med = float(np.median(d))
        if np.all(np.abs(d - med) <= 2.1 * slack + 1e-12) and abs(med) > tol_i:
            offset[i] = med
    unit_factor = None
    if scale:
        logs = {round(math.log10(abs(v))) for v in scale.values() if v != 0}
        if len(logs) == 1:
            p = logs.pop()
            if p != 0 and all(abs(v / 10.0**p - 1) < 1e-3 for v in scale.values()):
                unit_factor = 10.0**p
    return Diagnosis(perm, scale, unit_factor, offset, best_list)
