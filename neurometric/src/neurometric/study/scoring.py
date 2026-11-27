"""Server-side scoring of uploaded canonical event streams.

The authoritative scores of a functional testing session are computed here, in Python, from the
canonical events (DECISIONS D-003), with the metric functions of :mod:`neurometric.metrics`.

Event protocol expected from task engines (browser or simulator)
----------------------------------------------------------------
Trials are delimited by ``marker`` events (``meta.marker``):

* ``stimulus_on`` starts a scored trial. ``meta`` may carry ``trial`` (index into the task's
  stimuli), ``block`` (A2/A3 condition index), ``target`` = ``{x, y, w[, h]}`` (task-space
  geometry; if absent it is looked up from the stimuli), ``n_items`` (selection tasks).
  For ISO sequences (A2/A3) the unscored first selection of a sequence has no ``stimulus_on``.
* ``trial_end`` closes a trial; optional ``meta.outcome`` (``hit``/``miss``/``timeout``/
  ``completed``/``abandoned``) and ``meta.item`` (index of a wrongly selected item).
* ``phrase_start`` / ``phrase_end`` delimit copy-typing phrases (E1); ``meta.phrase`` is the
  index into the stimulus phrase list (only predefined phrases are ever scored or stored).

Selections are events whose kind is in ``SELECTION_KINDS``; a selection with ``meta.empty`` =
true is a non-terminating empty-space selection. ``meta.correct = false`` on a selection marks a
wrong selection in multi-step digital-ADL tasks. ``assist`` events inside a trial mark it
assisted (never failed).
"""
from __future__ import annotations

import math
from typing import Any, Optional

import numpy as np

from ..events.model import EventKind, InputEvent
from ..metrics.pointing import PointingTrials, achieved_bitrate, fitts_throughput, trial_metrics
from ..metrics.session import session_summary
from ..metrics.text import BACKSPACE, text_entry_metrics
from ..tasks.battery import PHRASES, TASKS, stimuli as battery_stimuli

SCORER_VERSION = "neurometric.study.scoring/1.0"
POINTING_TASKS = {"A1", "A2", "A3", "A4", "A5", "E2"}
TEXT_TASKS = {"E1"}
TASK_IDS = {t.id for t in TASKS}


def clean(v: Any) -> Any:
    """JSON-safe: NaN/inf -> None, numpy scalars -> Python."""
    if isinstance(v, dict):
        return {str(k): clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [clean(x) for x in v]
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        return f if math.isfinite(f) else None
    if isinstance(v, np.ndarray):
        return clean(v.tolist())
    return v


def _nanmean(a) -> float:
    a = np.asarray(a, float)
    a = a[~np.isnan(a)]
    return float(a.mean()) if a.size else float("nan")


def _marker(ev: InputEvent) -> Optional[str]:
    return ev.meta.get("marker") if ev.kind == EventKind.MARKER else None


def _split_trials(events: list[InputEvent], start="stimulus_on", end="trial_end"):
    """Yield (onset_event, [events in trial], end_event_or_None, prior_events)."""
    trials = []
    cur = None
    for i, ev in enumerate(events):
        m = _marker(ev)
        if m == start:
            if cur is not None:
                trials.append(cur)
            cur = {"onset": ev, "events": [], "end": None, "index": i}
        elif cur is not None:
            if m == end:
                cur["end"] = ev
                trials.append(cur)
                cur = None
            else:
                cur["events"].append(ev)
    if cur is not None:
        trials.append(cur)
    return trials


def _target_from_stimuli(task_id: str, stim: dict, meta: dict) -> Optional[dict]:
    try:
        if task_id in ("A1", "A5"):
            return stim["trials"][int(meta["trial"])]
        if task_id in ("A2", "A3"):
            b = stim["blocks"][int(meta["block"])]
            return b["targets"][int(meta["trial"])]
        if task_id == "A4":
            return stim["items"][stim["cues"][int(meta["trial"])]]
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return None


def _score_pointing(task_id: str, events: list[InputEvent], stim: dict) -> dict[str, Any]:
    trials = _split_trials(events)
    flags: list[str] = []
    rows = []
    last_pos = None
    # positions known before each trial (ISO: start = previous selection point)
    pos_before: list[Optional[tuple]] = []
    idx_iter = iter(trials)
    nxt = next(idx_iter, None)
    for i, ev in enumerate(events):
        while nxt is not None and nxt["index"] == i:
            pos_before.append(last_pos)
            nxt = next(idx_iter, None)
        if ev.x is not None and ev.y is not None:
            last_pos = (ev.x, ev.y)
    for tr, before in zip(trials, pos_before):
        on = tr["onset"]
        meta = on.meta
        tgt = meta.get("target") or _target_from_stimuli(task_id, stim, meta)
        if not tgt:
            flags.append(f"trial at t={on.t_ms} has no target geometry; skipped")
            continue
        w = float(tgt["w"])
        h = float(tgt.get("h", w))
        samples_t, samples_xy = [], []
        start = meta.get("start")
        start = (float(start["x"]), float(start["y"])) if start else before
        sel = None
        n_empty = 0
        assisted = False
        cur_pos = start
        for ev in tr["events"]:
            if ev.kind == EventKind.ASSIST:
                assisted = True
            if ev.x is not None and ev.y is not None:
                cur_pos = (ev.x, ev.y)
                samples_t.append(ev.t_ms - on.t_ms)
                samples_xy.append(cur_pos)
            if ev.is_selection:
                if ev.meta.get("empty"):
                    n_empty += 1
                    continue
                if sel is None:
                    sel = (ev.t_ms - on.t_ms, cur_pos, ev)
                    break
        if start is None:
            start = samples_xy[0] if samples_xy else (float(tgt["x"]), float(tgt["y"]))
        if not samples_xy:
            samples_t, samples_xy = [0.0], [start]
        outcome = (tr["end"].meta.get("outcome") if tr["end"] is not None else None)
        if sel is None or outcome == "timeout" or sel[1] is None:
            sel_item, sel_t = -2, float("nan")
            sel_pos = samples_xy[-1]
        else:
            sel_t, sel_pos = float(sel[0]), sel[1]
            inside = (abs(sel_pos[0] - tgt["x"]) <= w / 2) and (abs(sel_pos[1] - tgt["y"]) <= h / 2)
            if inside:
                sel_item = 0
            else:
                item = tr["end"].meta.get("item") if tr["end"] is not None else None
                item = sel[2].meta.get("item", item)
                sel_item = int(item) if isinstance(item, int) and item > 0 else -1
        rows.append({"t": samples_t, "xy": samples_xy, "start": start,
                     "target": (float(tgt["x"]), float(tgt["y"])), "half": (w / 2, h / 2),
                     "sel_t": sel_t, "sel_pos": sel_pos, "sel_item": sel_item,
                     "n_empty": n_empty, "assisted": assisted, "block": meta.get("block"),
                     "D": meta.get("D", tgt.get("D")), "W": meta.get("W", w),
                     "n_items": meta.get("n_items")})
    if not rows:
        return {"n_trials": 0, "flags": flags + ["no scorable trials"]}
    N = len(rows)
    T = max(len(r["t"]) for r in rows)
    traj = np.full((N, T, 2), np.nan)
    tms = np.full((N, T), np.nan)
    for i, r in enumerate(rows):
        k = len(r["t"])
        traj[i, :k] = np.asarray(r["xy"], float)
        tms[i, :k] = np.asarray(r["t"], float)
    pt = PointingTrials(
        traj=traj, t_ms=tms, start=np.array([r["start"] for r in rows], float),
        target_c=np.array([r["target"] for r in rows], float),
        target_h=np.array([r["half"] for r in rows], float),
        sel_t=np.array([r["sel_t"] for r in rows], float),
        sel_pos=np.array([r["sel_pos"] for r in rows], float),
        sel_item=np.array([r["sel_item"] for r in rows], np.int64),
        n_empty_selects=np.array([r["n_empty"] for r in rows], np.int64))
    tm = trial_metrics(pt)
    succ = tm["success"]
    out: dict[str, Any] = {
        "n_trials": N,
        "n_success": int(succ.sum()),
        "success_rate": float(succ.mean()),
        "error_rate": float(tm["error"].mean()),
        "timeout_rate": float(tm["timeout"].mean()),
        "movement_time_ms_mean": _nanmean(np.where(succ, tm["movement_time_ms"], np.nan)),
        "movement_time_ms_median": float(np.nanmedian(np.where(succ, tm["movement_time_ms"], np.nan)))
        if succ.any() else float("nan"),
        "onset_ms_mean": _nanmean(tm["onset_ms"]),
        "path_efficiency_mean": _nanmean(tm["path_efficiency"]),
        "endpoint_error_px_mean": _nanmean(tm["endpoint_error_px"]),
        "target_reentries_mean": _nanmean(tm["target_reentries"]),
        "overshoot_px_mean": _nanmean(tm["overshoot_px"]),
        "empty_selections": float(tm["empty_selections"].sum()),
        "assisted_trials": int(sum(r["assisted"] for r in rows)),
    }
    if task_id in ("A2", "A3"):
        tps, valid_all = [], True
        conds = []
        keys = sorted({(r["D"], r["W"]) for r in rows}, key=lambda k: (str(k[0]), str(k[1])))
        for D, W in keys:
            idx = [i for i, r in enumerate(rows) if (r["D"], r["W"]) == (D, W)]
            if D is None:
                flags.append("condition without D: throughput not computed")
                continue
            res = fitts_throughput(pt.subset(np.array(idx)), float(D), float(W),
                                   dwell=task_id == "A3")
            conds.append({"D": D, "W": W, "tp_effective_bps": res.tp_effective_bps,
                          "valid": res.valid, "n": res.n, "flags": res.flags})
            if math.isfinite(res.tp_effective_bps):
                tps.append(res.tp_effective_bps)
            valid_all = valid_all and res.valid
        out["fitts_throughput_bps"] = float(np.mean(tps)) if tps else float("nan")
        out["throughput_valid"] = bool(valid_all and tps)
        out["conditions"] = conds
    if task_id in ("A4", "E2"):
        n_items = rows[0]["n_items"] or (len(stim.get("items", [])) if stim else None) or (
            12 if task_id == "E2" else None)
        mt = np.where(tm["timeout"], np.nan, tm["movement_time_ms"])
        secs = float(np.nansum(mt)) / 1000.0
        nc = int(succ.sum())
        ni = int(tm["error"].sum())
        out["achieved_bitrate_bps"] = achieved_bitrate(nc, ni, int(n_items), secs) if n_items else float("nan")
        out["wrong_item_selections"] = ni
    out["flags"] = flags
    return out


def _score_text(events: list[InputEvent], stim: dict) -> dict[str, Any]:
    phrases = _split_trials(events, "phrase_start", "phrase_end")
    flags: list[str] = []
    per = []
    for ph in phrases:
        meta = ph["onset"].meta
        presented = None
        if "phrase" in meta and stim.get("phrases"):
            try:
                presented = stim["phrases"][int(meta["phrase"])]
            except (IndexError, ValueError, TypeError):
                presented = None
        if presented is None and isinstance(meta.get("presented"), str) and meta["presented"] in PHRASES:
            presented = meta["presented"]
        if presented is None:
            flags.append("phrase without a predefined presented string; skipped")
            continue
        stream: list[str] = []
        times: list[float] = []
        for ev in ph["events"]:
            if ev.kind == EventKind.TEXT_INPUT and ev.text is not None:
                for ch in ev.text:
                    stream.append(ch)
                    times.append(ev.t_ms)
            elif ev.kind == EventKind.KEY and ev.key:
                if ev.key in ("Backspace", "\b"):
                    stream.append(BACKSPACE)
                    times.append(ev.t_ms)
                elif len(ev.key) == 1:
                    stream.append(ev.key)
                    times.append(ev.t_ms)
        if not stream:
            flags.append("phrase with no keystrokes")
            continue
        end_t = ph["end"].t_ms if ph["end"] is not None else times[-1]
        seconds = max(end_t - times[0], 0.0) / 1000.0
        r = text_entry_metrics(presented, stream, seconds).to_dict()
        per.append(r)
    if not per:
        return {"n_phrases": 0, "flags": flags + ["no scorable phrases"]}
    keys = ["wpm", "ccpm", "msd_error_rate", "total_error_rate", "corrected_error_rate",
            "uncorrected_error_rate", "kspc", "correction_burden"]
    out = {"n_phrases": len(per)}
    for k in keys:
        out[f"{k}_mean"] = _nanmean([p[k] for p in per])
    out["phrases"] = [{k: p[k] for k in keys + ["msd", "keystrokes", "seconds"]} for p in per]
    out["flags"] = flags
    return out


def _score_generic(events: list[InputEvent]) -> dict[str, Any]:
    trials = _split_trials(events)
    rows = []
    for tr in trials:
        end = tr["end"]
        outcome = end.meta.get("outcome") if end is not None else None
        t = (end.t_ms - tr["onset"].t_ms) if end is not None else float("nan")
        wrong = sum(1 for e in tr["events"] if e.is_selection and e.meta.get("correct") is False)
        rows.append({"completed": outcome in ("completed", "hit"), "time_ms": t,
                     "wrong_selections": wrong,
                     "assisted": any(e.kind == EventKind.ASSIST for e in tr["events"])})
    if not rows:
        return {"n_trials": 0, "flags": ["no scorable trials"]}
    comp = np.array([r["completed"] for r in rows])
    times = np.array([r["time_ms"] for r in rows], float)
    return {"n_trials": len(rows), "completion_rate": float(comp.mean()),
            "time_to_complete_ms_mean": _nanmean(np.where(comp, times, np.nan)),
            "wrong_selections": int(sum(r["wrong_selections"] for r in rows)),
            "assisted_trials": int(sum(r["assisted"] for r in rows)), "flags": []}


def score_session(task_id: str, events: list[InputEvent], stimulus_seed: int = 0,
                  stim: Optional[dict] = None) -> dict[str, Any]:
    """Score one task session. Returns a JSON-safe dict of summary metrics."""
    if task_id not in TASK_IDS:
        raise ValueError(f"unknown task {task_id!r}")
    stim = stim if stim is not None else battery_stimuli(task_id, stimulus_seed)
    if task_id in POINTING_TASKS:
        res = _score_pointing(task_id, events, stim)
        n_planned = res.get("n_trials", 0)
        n_done = res.get("n_success", 0)
    elif task_id in TEXT_TASKS:
        res = _score_text(events, stim)
        n_planned = len(stim.get("phrases", [])) or res.get("n_phrases", 0)
        n_done = res.get("n_phrases", 0)
    else:
        res = _score_generic(events)
        n_planned = res.get("n_trials", 0)
        n_done = int(round(res.get("completion_rate", 0) * n_planned)) if n_planned else 0
        res.setdefault("flags", []).append(
            "generic trial scoring (completion/time); task-specific kinematics not computed "
            "server-side in scorer v1")
    res["session"] = session_summary(events, n_planned, n_done)
    res["task_id"] = task_id
    res["scorer_version"] = SCORER_VERSION
    return clean(res)


#: Primary metric per task used by dashboards / analysis datasets.
PRIMARY_METRICS = {
    "A1": "movement_time_ms_mean", "A2": "fitts_throughput_bps", "A3": "fitts_throughput_bps",
    "A4": "achieved_bitrate_bps", "A5": "success_rate", "E1": "wpm_mean",
    "E2": "achieved_bitrate_bps",
}


def flat_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    """Scalar numeric metrics only (for analysis datasets)."""
    out = {}
    for k, v in metrics.items():
        if isinstance(v, bool):
            out[k] = float(v)
        elif isinstance(v, (int, float)) and v is not None:
            out[k] = float(v)
    for k, v in (metrics.get("session") or {}).items():
        if isinstance(v, (int, float)) and v is not None and not isinstance(v, bool):
            out[f"session_{k}"] = float(v)
    return out
