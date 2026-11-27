"""Pre-computed SIMULATED trajectories for the web demo's "watch a virtual user" mode.

Uses neurometric.simulator.engine.Simulation (closed-loop virtual users, D-005) with mouse_sim and
the BCI-like stress profiles (bci_good / bci_moderate / bci_poor). Small n so the file stays small.
These are simulated input-degradation traces, not recordings of any person or any specific BCI.

    python web/scripts/export_demo_traces.py   ->  web/public/demo/traces.json
"""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from neurometric.metrics.pointing import (PointingTrials, achieved_bitrate,  # noqa: E402
                                          fitts_throughput, trial_metrics)
from neurometric.simulator.decoder import PROFILES  # noqa: E402
from neurometric.simulator.engine import Simulation  # noqa: E402
from neurometric.simulator.modalities import MODALITIES  # noqa: E402
from neurometric.tasks.battery import grid_items, iso_ring, stimuli  # noqa: E402

OUT = HERE.parent / "public" / "demo" / "traces.json"
CONDITIONS = [("mouse_sim", "mouse_sim", "identity"),
              ("bci_good", "bci_cursor_good_sim", "bci_good"),
              ("bci_moderate", "bci_cursor_moderate_sim", "bci_moderate"),
              ("bci_poor", "bci_cursor_poor_sim", "bci_poor")]
D, W = 512, 64
SUB = 2  # keep every 2nd 10 ms sample (20 ms) to keep the file small


def num(v):
    v = float(v)
    return round(v, 2) if math.isfinite(v) else None


def steps_json(st, b):
    k = int(np.sum(~np.isnan(st.traj[b, :, 0])))
    xy = st.traj[b, :k:SUB]
    return {"xy": [[num(x), num(y)] for x, y in xy], "dt_ms": 10.0 * SUB,
            "sel_t": num(st.sel_t[b]), "sel_pos": [num(v) for v in st.sel_pos[b]],
            "sel_item": int(st.sel_item[b]), "target": [num(v) for v in st.target_c[b]],
            "half": [num(v) for v in st.target_h[b]], "start": [num(v) for v in st.start[b]]}


def main(seed: int = 3) -> None:
    rng = np.random.default_rng(seed)
    ring = iso_ring(D, W, 13)
    a4 = stimuli("A4", 0)
    gitems = grid_items(4, 6, 120, 100)
    rect = np.array([[g["x"], g["y"], g["w"] / 2, g["h"] / 2] for g in gitems])
    out = {"generator": "web/scripts/export_demo_traces.py", "label": "SIMULATED input degradation - not a model of any specific BCI",
           "iso": {"D": D, "W": W, "ring": ring}, "grid": {"items": gitems, "cues": a4["cues"][:10]}, "conditions": []}
    for name, mod_name, profile in CONDITIONS:
        mod = MODALITIES[mod_name]
        deg = PROFILES[profile] if profile != "identity" else mod.degradation
        # ISO ring, 2 virtual users
        B = 2
        start = np.tile([ring[0]["x"], ring[0]["y"]], (B, 1))
        sim = Simulation(mod.user_model, mod.user, deg, B, rng, start=start)
        iso_steps, trials = [], []
        for k in range(1, 13):
            tg = ring[k]
            st = sim.acquire(np.tile([[tg["x"], tg["y"], W / 2, W / 2]], (B, 1, 1)), max_ms=8000, end_on_empty=True)
            iso_steps.append([steps_json(st, b) for b in range(B)])
            trials.append(PointingTrials.from_step(st))
        tp = []
        for b in range(B):
            pts = [t.subset(np.array([b])) for t in trials]
            T = max(p.traj.shape[1] for p in pts)

            def pad(a, fill=np.nan, T=T):
                shp = list(a.shape)
                shp[1] = T
                o = np.full(shp, fill)
                o[:, : a.shape[1]] = a
                return o
            cat = PointingTrials(np.concatenate([pad(p.traj) for p in pts]), np.concatenate([pad(p.t_ms) for p in pts]),
                                 np.concatenate([p.start for p in pts]), np.concatenate([p.target_c for p in pts]),
                                 np.concatenate([p.target_h for p in pts]), np.concatenate([p.sel_t for p in pts]),
                                 np.concatenate([p.sel_pos for p in pts]), np.concatenate([p.sel_item for p in pts]),
                                 np.concatenate([p.n_empty_selects for p in pts]))
            r = fitts_throughput(cat, D, W)
            tm = trial_metrics(cat)
            tp.append({"tp_effective_bps": num(r.tp_effective_bps), "error_rate": num(r.error_rate),
                       "mt_ms": num(r.mt_ms), "path_efficiency": num(np.nanmean(tm["path_efficiency"]))})
        # grid, 1 virtual user
        gsim = Simulation(mod.user_model, mod.user, deg, 1, rng)
        gsteps, nc, ni, secs = [], 0, 0, 0.0
        for c in out["grid"]["cues"]:
            order = np.r_[c, np.delete(np.arange(len(gitems)), c)]
            st = gsim.acquire(rect[order][None], max_ms=8000, end_on_empty=False)
            js = steps_json(st, 0)
            js["cue"] = int(c)
            si = int(st.sel_item[0])
            js["sel_item_id"] = int(order[si]) if si >= 0 else si
            gsteps.append(js)
            if si == 0:
                nc += 1
            elif si > 0:
                ni += 1
            if not st.timed_out[0]:
                secs += float(st.sel_t[0]) / 1000
        out["conditions"].append({
            "name": name, "modality": mod_name, "profile": profile, "control_mode": sim.mode,
            "iso_steps": iso_steps, "grid_steps": gsteps,
            "python_metrics": {"iso": tp, "grid": {"n_correct": nc, "n_incorrect": ni,
                                                   "achieved_bitrate_bps": num(achieved_bitrate(nc, ni, len(gitems), secs))}}})
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":")) + "\n")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KiB)")


if __name__ == "__main__":
    main()
