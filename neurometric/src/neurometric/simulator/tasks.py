"""Task runners: execute battery tasks with simulated participants and score them with the same
metric functions used for recorded sessions. Outputs are pandas DataFrames (one row per trial,
phrase or task attempt) with an explicit ``synthetic=True`` column.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from ..metrics.pointing import PointingTrials, achieved_bitrate, fitts_throughput, trial_metrics
from ..metrics.text import BACKSPACE, text_entry_metrics
from ..tasks.battery import grid_items, iso_ring, keyboard_layout
from .engine import Simulation, WORKSPACE
from .modalities import Modality
from .scanning import scan_select
from ..users.models import UserParams


def _sim(mod: Modality, users: UserParams, n: int, rng, start=None, session_minutes=None,
         degradation=None, workspace=WORKSPACE) -> Simulation:
    return Simulation(mod.user_model, users, degradation or mod.degradation, n, rng, start=start,
                      session_minutes=session_minutes, workspace=workspace)


def _rects(pts, h=None):
    """list of dicts with x,y,w[,h] -> (K,4) array of [cx,cy,hw,hh]."""
    return np.array([[p["x"], p["y"], p["w"] / 2, (p.get("h", p["w"])) / 2] for p in pts], float)


# ----------------------------------------------------------------------------- A2 / A3
def run_iso(mod: Modality, users: UserParams, n: int, rng: np.random.Generator, D: float,
            W: float, n_targets: int = 13, max_ms: float = 15000.0,
            session_minutes: Optional[np.ndarray] = None, degradation=None,
            dwell_ms: Optional[float] = None,
            n_selections: Optional[int] = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """ISO multidirectional sequence for n participants. Returns (trials_df, throughput_df).

    The ring always has ``n_targets`` (13) positions so inter-target distance is fixed
    (D*sin(7*pi/13) = 0.993 D); ``n_selections`` scored selections continue around the ring."""
    if mod.kind != "pointer":
        raise ValueError("ISO pointing requires a pointer modality")
    ring = iso_ring(D, W, n_targets)
    first = np.array([ring[0]["x"], ring[0]["y"]])
    start = np.tile(first, (n, 1))
    sim = _sim(mod, users, n, rng, start=start, session_minutes=session_minutes,
               degradation=degradation)
    dwell = dwell_ms if dwell_ms is not None else (mod.dwell_ms if mod.selection == "dwell" else None)
    rows = []
    tp_rows = []
    trials_all = []
    n_sel = n_selections if n_selections is not None else n_targets - 1
    for k in range(1, n_sel + 1):
        tg = ring[k % n_targets]
        items = np.tile(np.array([[tg["x"], tg["y"], W / 2, W / 2]]), (n, 1, 1))
        st = sim.acquire(items, dwell_ms=dwell, max_ms=max_ms, end_on_empty=True)
        # ISO: after a timeout the next target is still presented from wherever the cursor is
        tr = PointingTrials.from_step(st)
        trials_all.append(tr)
        tm = trial_metrics(tr)
        df = pd.DataFrame(tm)
        df["participant"] = np.arange(n)
        df["selection_index"] = k
        df["gt_false_selects"] = st.gt_false_selects
        df["gt_missed_selects"] = st.gt_missed_selects
        df["gt_dropout_ms"] = st.gt_dropout_ms
        rows.append(df)
    trials = pd.concat(rows, ignore_index=True)
    trials["D"], trials["W"], trials["modality"], trials["synthetic"] = D, W, mod.name, True
    # throughput per participant (per condition)
    for i in range(n):
        tr_i = _concat_trials([t.subset([i]) for t in trials_all])
        r = fitts_throughput(tr_i, D, W, dwell=dwell is not None)
        tp_rows.append({"participant": i, "D": D, "W": W, "tp_bps": r.tp_effective_bps,
                        "tp_nominal_bps": r.tp_nominal_bps, "we_px": r.we_px,
                        "error_rate": r.error_rate, "mt_ms": r.mt_ms, "n_selections": r.n,
                        "tp_valid": r.valid, "tp_flags": "; ".join(r.flags),
                        "modality": mod.name, "synthetic": True})
    return trials, pd.DataFrame(tp_rows)


def _concat_trials(ts: list[PointingTrials]) -> PointingTrials:
    T = max(t.traj.shape[1] for t in ts)

    def pad(a, fill=np.nan):
        if a.shape[1] == T:
            return a
        shp = list(a.shape)
        shp[1] = T - a.shape[1]
        return np.concatenate([a, np.full(shp, fill)], 1)

    return PointingTrials(
        np.concatenate([pad(t.traj) for t in ts]), np.concatenate([pad(t.t_ms) for t in ts]),
        np.concatenate([t.start for t in ts]), np.concatenate([t.target_c for t in ts]),
        np.concatenate([t.target_h for t in ts]), np.concatenate([t.sel_t for t in ts]),
        np.concatenate([t.sel_pos for t in ts]), np.concatenate([t.sel_item for t in ts]),
        np.concatenate([t.n_empty_selects for t in ts]))


# ----------------------------------------------------------------------------- A4 grid
def run_grid(mod: Modality, users: UserParams, n: int, rng, rows=4, cols=6, cell=120, item=100,
             n_trials=24, max_ms=20000.0, session_minutes=None, degradation=None,
             rt_scale=None) -> pd.DataFrame:
    """Selection among distractors. Returns per-trial DataFrame (success, time)."""
    items = grid_items(rows, cols, cell, item)
    rect = _rects(items)
    K = len(items)
    out = []
    if mod.kind == "scan":
        cfg = mod.scan if degradation is None else degradation
        for k in range(n_trials):
            cue = rng.integers(0, K, n)
            r = scan_select(rng, n, cue, rows, cols, cfg, 1.0 if rt_scale is None else rt_scale)
            out.append(pd.DataFrame({"participant": np.arange(n), "trial": k,
                                     "success": r["selected"] == cue,
                                     "timeout": r["selected"] < 0,
                                     "movement_time_ms": r["time_ms"],
                                     # unintended switch activations are not observable as such
                                     # (they look like selections); the observable proxy is wrong selections
                                     "false_activations": np.full(n, np.nan),
                                     "gt_false_selects": r["false"]}))
    else:
        sim = _sim(mod, users, n, rng, session_minutes=session_minutes, degradation=degradation)
        dwell = mod.dwell_ms if mod.selection == "dwell" else None
        for k in range(n_trials):
            cue = rng.integers(0, K, n)
            # put the cued item first (index 0 = target) keeping all others as distractors
            order = np.array([np.r_[c, np.delete(np.arange(K), c)] for c in cue])
            its = rect[order]
            st = sim.acquire(its, dwell_ms=dwell, max_ms=max_ms, end_on_empty=False)
            out.append(pd.DataFrame({"participant": np.arange(n), "trial": k,
                                     "success": st.sel_item == 0, "timeout": st.timed_out,
                                     "movement_time_ms": np.where(st.timed_out, max_ms, st.sel_t),
                                     "false_activations": st.n_empty_selects,
                                     "gt_false_selects": st.gt_false_selects}))
    df = pd.concat(out, ignore_index=True)
    df["modality"], df["synthetic"], df["n_items"] = mod.name, True, K
    return df


def grid_summary(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("participant")
    res = []
    for pid, d in g:
        secs = d["movement_time_ms"].sum() / 1000
        nc = int(d["success"].sum())
        ni = int((~d["success"] & ~d["timeout"]).sum())
        res.append({"participant": pid, "accuracy": nc / len(d),
                    "mean_time_ms": d["movement_time_ms"].mean(),
                    "achieved_bitrate_bps": achieved_bitrate(nc, ni, int(d["n_items"].iloc[0]), secs),
                    "selections_per_min": len(d) / (secs / 60) if secs > 0 else np.nan})
    return pd.DataFrame(res)


# ----------------------------------------------------------------------------- E1 typing
def run_typing(mod: Modality, users: UserParams, n: int, rng, phrases: list[str],
               key: float = 90, notice_prob: float = 0.9, max_ms_per_key: float = 20000.0,
               session_minutes=None, degradation=None, rt_scale=None,
               max_keys_factor: float = 3.0) -> pd.DataFrame:
    """Copy typing with error correction. One row per participant x phrase."""
    keys = keyboard_layout(key)
    rect = _rects(keys)
    labels = [k["key"] for k in keys]
    K = len(keys)
    idx_of = {c: i for i, c in enumerate(labels)}
    rows_out = []
    sim = None
    if mod.kind == "pointer":
        sim = _sim(mod, users, n, rng, session_minutes=session_minutes, degradation=degradation)
    dwell = mod.dwell_ms if mod.selection == "dwell" else None
    # scanning layout: 4 rows x 7 columns, frequency ordered, no empty cells (common AAC design)
    scan_cells = [" ", "e", "t", "a", "o", "i", "n", "s", "h", "r", "d", "l", "u", "c", "m", "f",
                  "w", "y", "p", "v", "b", "g", "k", "j", "q", "x", "z", "\b"]
    SR, SC = 4, 7
    scan_pos = {c: i for i, c in enumerate(scan_cells)}
    scan_lab = {i: c for i, c in enumerate(scan_cells)}
    for ph in phrases:
        buf = [[] for _ in range(n)]
        stream = [[] for _ in range(n)]
        accepted = [set() for _ in range(n)]
        t = np.zeros(n)
        t_first = np.full(n, np.nan)
        attempts = np.zeros(n, int)
        aborted = np.zeros(n, bool)
        max_attempts = int(max_keys_factor * len(ph)) + 5
        active = np.ones(n, bool)
        while active.any():
            want = np.full(n, -1)
            for i in np.nonzero(active)[0]:
                b = buf[i]
                L = len(b)
                last_wrong = L > 0 and (L > len(ph) or b[-1] != ph[L - 1]) and (L - 1) not in accepted[i]
                if last_wrong:
                    if rng.random() < notice_prob:
                        want[i] = idx_of["\b"]
                        continue
                    accepted[i].add(L - 1)
                if L >= len(ph) or len(stream[i]) > max_keys_factor * len(ph):
                    active[i] = False
                    continue
                if attempts[i] >= max_attempts:  # e.g. no keystroke can be produced at all
                    active[i] = False
                    aborted[i] = True
                    continue
                want[i] = idx_of[ph[L]]
            if not active.any():
                break
            if mod.kind == "pointer":
                order = np.array([np.r_[w, np.delete(np.arange(K), w)] if w >= 0 else np.arange(K)
                                  for w in want])
                st = sim.acquire(rect[order], dwell_ms=dwell, max_ms=max_ms_per_key,
                                 end_on_empty=False, mask=active)
                hit = np.where(st.sel_item >= 0, order[np.arange(n), np.maximum(st.sel_item, 0)], -1)
                typed = [labels[h] if h >= 0 else None for h in hit]
                dt = np.where(st.timed_out, max_ms_per_key, np.nan_to_num(st.sel_t))
            else:
                tgt = np.array([scan_pos[labels[w]] if w >= 0 else 0 for w in want])
                r = scan_select(rng, n, tgt, SR, SC, mod.scan if degradation is None else degradation,
                                1.0 if rt_scale is None else rt_scale)
                typed = [scan_lab.get(int(s)) if s >= 0 else None for s in r["selected"]]
                dt = r["time_ms"]
            for i in np.nonzero(active)[0]:
                t[i] += dt[i]
                attempts[i] += 1
                ch = typed[i]
                if ch is None:
                    continue
                if np.isnan(t_first[i]):
                    t_first[i] = t[i]
                stream[i].append(ch)
                if ch == "\b":
                    if buf[i]:
                        buf[i].pop()
                        accepted[i].discard(len(buf[i]))
                else:
                    buf[i].append(ch)
        for i in range(n):
            # S is timed from the first keystroke to the last (METRICS.md; review C5)
            secs = (t[i] - t_first[i]) / 1000.0 if np.isfinite(t_first[i]) else 0.0
            res = text_entry_metrics(ph, stream[i], secs)
            d = res.to_dict()
            d.update(participant=i, phrase=ph, aborted=bool(aborted[i]),
                     phrase_time_s=t[i] / 1000.0)
            rows_out.append(d)
    df = pd.DataFrame(rows_out)
    df["modality"], df["synthetic"] = mod.name, True
    return df


# ----------------------------------------------------------------------------- B2 tracking
def run_tracking(mod: Modality, users: UserParams, n: int, rng, duration_ms=30000.0,
                 radius=40.0, degradation=None, exclude_ms=3000.0,
                 session_minutes=None) -> pd.DataFrame:
    """Continuous tracking of a sum-of-sines target (velocity/feedback users only)."""
    from ..metrics.session import tracking_metrics
    from .decoder import DegradedChannel
    from ..users.models import FeedbackUser
    dt = 10.0
    user = FeedbackUser(users, n, dt, rng)
    ch = DegradedChannel(degradation or mod.degradation, n, dt, "velocity", rng, session_minutes)
    comps = [(0.1, 180, 120), (0.17, 120, 90), (0.27, 80, 60), (0.4, 50, 40)]
    ph = rng.uniform(0, 2 * np.pi, (n, len(comps), 2))
    T = int(duration_ms / dt)
    tt = np.arange(T) * dt / 1000

    def target(k):
        x = 640 + sum(a * np.sin(2 * np.pi * f * tt[k] + ph[:, j, 0]) for j, (f, a, _) in enumerate(comps))
        y = 400 + sum(b * np.sin(2 * np.pi * f * tt[k] + ph[:, j, 1]) for j, (f, _, b) in enumerate(comps))
        return np.stack([x, y], 1)

    cur = target(0)
    hist = [cur.copy() for _ in range(user.max_fb + 2)]
    C = np.zeros((n, T, 2))
    G = np.zeros((n, T, 2))
    user.begin(target(0), np.full((n, 2), radius), cur, np.ones(n, bool), dwell=True)
    user.wait[:] = 0
    for k in range(T):
        g = target(k)
        # the user aims at where they perceive the target to be (target seen with the same delay)
        gk = target(max(0, k - int(np.median(user.fb_ticks))))
        user.aim = gk
        perceived = np.stack([hist[-1 - user.fb_ticks[i]][i] for i in range(n)])
        u, _ = user.act(perceived, perceived, ch.t_min, np.ones(n, bool))
        out, _ = ch.step(u, np.zeros(n, bool))
        cur = np.clip(cur + out * dt / 1000, 0, WORKSPACE)
        hist.append(cur.copy())
        hist.pop(0)
        C[:, k], G[:, k] = cur, g
    k0 = int(exclude_ms / dt)
    rows = []
    for i in range(n):
        m = tracking_metrics(np.arange(T - k0) * dt, C[i, k0:], G[i, k0:], radius)
        m["participant"] = i
        rows.append(m)
    df = pd.DataFrame(rows)
    df["modality"], df["synthetic"] = mod.name, True
    return df


# ----------------------------------------------------------------------------- F tasks
def adl_layouts() -> dict[str, list[dict]]:
    """Simulated digital-ADL task flows: each step = screen items + index of the correct item.
    Item 0 on every screen after the first is a 'back' button used for recovery."""
    def screen(items, target):
        return {"items": items, "target": target}

    def col(xs, y0, n, w=360, h=56, gap=10, x=640):
        return [{"x": x, "y": y0 + i * (h + gap), "w": w, "h": h} for i in range(n)]

    back = {"x": 80, "y": 50, "w": 110, "h": 60}
    flows = {}
    # F1 contact selection: list of 10 visible contacts, pick #7
    flows["F1"] = [screen([back] + col(None, 120, 10), 7)]
    # F2 compose: open messages (one of 4 app tiles), recipient (of 6), 3 tiles (of 9), send
    apps = [{"x": 340 + i * 200, "y": 400, "w": 160, "h": 160} for i in range(4)]
    tiles = [{"x": 400 + (i % 3) * 240, "y": 250 + (i // 3) * 130, "w": 220, "h": 110} for i in range(9)]
    send = {"x": 1100, "y": 700, "w": 180, "h": 80}
    flows["F2"] = [screen([back] + apps, 2), screen([back] + col(None, 150, 6), 3),
                   screen([back] + tiles + [send], 2), screen([back] + tiles + [send], 6),
                   screen([back] + tiles + [send], 9), screen([back] + tiles + [send], 10)]
    menus = [{"x": 120 + i * 150, "y": 40, "w": 140, "h": 50} for i in range(5)]
    flows["F3"] = [screen([back] + menus, 3),
                   screen([back] + menus + col(None, 100, 6, w=220, h=48, x=420), 5 + 4)]
    days = [{"x": 300 + (i % 7) * 100, "y": 200 + (i // 7) * 90, "w": 90, "h": 80} for i in range(35)]
    slots = col(None, 150, 8, w=260, h=60, x=1000)
    confirm = {"x": 1000, "y": 720, "w": 220, "h": 70}
    flows["F4"] = [screen([back] + days, 18), screen([back] + slots, 4), screen([back, confirm], 1)]
    opts = lambda y: [{"x": 400 + j * 170, "y": y, "w": 150, "h": 70} for j in range(4)]
    flows["F5"] = [screen([back] + opts(200), 2), screen([back] + opts(320), 4),
                   screen([back] + opts(440), 1), screen([back] + opts(560), 3),
                   screen([back, {"x": 640, "y": 700, "w": 240, "h": 80}], 1)]
    board = [{"x": 260 + (i % 5) * 190, "y": 180 + (i // 5) * 140, "w": 170, "h": 120} for i in range(20)]
    flows["F6"] = [screen([back] + board, 3), screen([back] + board, 12), screen([back] + board, 18)]
    links = col(None, 160, 8, w=500, h=40, gap=24)
    flows["F7"] = [screen([back] + links, 5), screen([back] + col(None, 160, 8, w=500, h=40, gap=24), 2)]
    return flows


def run_adl(mod: Modality, users: UserParams, n: int, rng, task_id: str, max_ms=120000.0,
            step_max_ms=20000.0, max_errors=6, session_minutes=None, degradation=None,
            rt_scale=None) -> pd.DataFrame:
    """Simulated digital ADL flow. Wrong selection -> 'back' (item 0) then retry the step."""
    flow = adl_layouts()[task_id]
    sim = None
    if mod.kind == "pointer":
        sim = _sim(mod, users, n, rng, session_minutes=session_minutes, degradation=degradation)
    dwell = mod.dwell_ms if mod.selection == "dwell" else None
    step = np.zeros(n, np.int64)
    need_back = np.zeros(n, bool)
    t = np.zeros(n)
    errors = np.zeros(n, np.int64)
    done = np.zeros(n, bool)
    failed = np.zeros(n, bool)
    S = len(flow)
    for _ in range(S * (max_errors + 2) * 2):
        active = ~done & ~failed
        if not active.any():
            break
        # group by (step, need_back) so each acquisition shares a screen
        for s in range(S):
            for nb in (False, True):
                m = active & (step == s) & (need_back == nb)
                if not m.any():
                    continue
                sc = flow[s]
                rect = _rects(sc["items"])
                K = len(rect)
                tgt = 0 if nb else sc["target"]
                order = np.r_[tgt, np.delete(np.arange(K), tgt)]
                if mod.kind == "pointer":
                    its = np.tile(rect[order], (n, 1, 1))
                    st = sim.acquire(its, dwell_ms=dwell, max_ms=step_max_ms, end_on_empty=False, mask=m)
                    got = np.where(st.sel_item >= 0, order[np.maximum(st.sel_item, 0)], -1)
                    dt = np.where(st.timed_out, step_max_ms, np.nan_to_num(st.sel_t))
                else:
                    cols = min(K, 6)
                    rows = int(np.ceil(K / cols))
                    r = scan_select(rng, n, np.full(n, tgt), rows, cols,
                                    mod.scan if degradation is None else degradation,
                                    1.0 if rt_scale is None else rt_scale)
                    got = np.where(r["selected"] < K, r["selected"], -1)
                    dt = r["time_ms"]
                t = np.where(m, t + dt, t)
                ok = m & (got == tgt)
                wrong = m & (got != tgt) & (got >= 0)
                if nb:
                    need_back = np.where(ok, False, need_back)
                    errors += wrong  # wrong selections during recovery also count (review M9)
                else:
                    step = np.where(ok, step + 1, step)
                    errors += wrong
                    # pressing 'back' by mistake returns to the previous screen
                    went_back = wrong & (got == 0)
                    step = np.where(went_back, np.maximum(step - 1, 0), step)
                    need_back = np.where(wrong & (got != 0), True, need_back)
        done = step >= S
        failed = ~done & ((errors > max_errors) | (t > max_ms))
    df = pd.DataFrame({"participant": np.arange(n), "completed": done,
                       "time_to_complete_ms": np.where(done, t, np.nan),
                       "time_spent_ms": t, "wrong_selections": errors})
    df["task"], df["modality"], df["synthetic"] = task_id, mod.name, True
    return df
