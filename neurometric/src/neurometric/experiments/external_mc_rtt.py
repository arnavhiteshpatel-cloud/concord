"""Experiment X1: run the NeuroMetric metric pipeline on REAL cursor-control behaviour.

Dataset: NLB MC_RTT (DANDI:000129, CC-BY-4.0; O'Doherty et al.; Makin et al. 2018). One
able-bodied rhesus macaque moving a cursor by hand to random targets on an 8x8 grid. This is not
BCI control and not a clinical population. Purpose: show the pipeline ingests real behavioural
data as canonical events and produces sane, reproducible metrics; NOT to set norms.

Reach segmentation: a reach starts when ``target_pos`` changes and ends at the next change
(the task advanced = target acquired). Target width and hold rules are not in the file, so
throughput uses effective width only and success/error rates are not computable.
Run: python -I -m neurometric.experiments.external_mc_rtt   (reads the file read-only)
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from ..events.model import EventKind, InputEvent, Modality, check_stream
from ..adapters.sessions import events_to_pointing_trials
from ..metrics.pointing import WE_FACTOR, trial_metrics
from .core import RESULTS, save, write_summary

DATA = (Path(__file__).resolve().parents[3] / "experiments" / "external_data" /
        "nlb_mc_rtt_dandi000129" / "sub-Indy_desc-train_behavior+ecephys.nwb")
SHA256 = "2f78db62bd4d68b9bc737444f72bc2dfe475d7390dd7a54848aaf6a6a6ba8da5"


def load(path=DATA, decimate: int = 10):
    import h5py
    with h5py.File(path, "r") as f:
        b = f["processing/behavior"]
        cur = b["cursor_pos/data"][::decimate]
        tgt = b["target_pos/data"][::decimate]
        t0 = float(b["cursor_pos/starting_time"][()])
    t_ms = t0 * 1000 + np.arange(len(cur)) * decimate
    return t_ms, cur, tgt


def to_events(t_ms, cur, tgt, min_ms=150, max_ms=5000):
    """Canonical events with stimulus_on / trial_end markers; y flipped to screen-down."""
    events = []
    seq = 0
    ok = ~np.isnan(tgt).any(1) & ~np.isnan(cur).any(1)
    change = np.nonzero(ok[1:] & ok[:-1] & np.any(np.abs(np.diff(tgt, axis=0)) > 1e-9, axis=1))[0] + 1
    n_reach = 0
    for a, b in zip(change[:-1], change[1:]):
        dur = t_ms[b] - t_ms[a]
        if dur < min_ms or dur > max_ms or not ok[a:b + 1].all():
            continue
        tx, ty = tgt[a]
        start = cur[a]

        def mk(t, kind, **kw):
            nonlocal seq
            e = InputEvent(t_ms=float(t - t_ms[0]), kind=kind, session_id="ses_mcrtt_indy",
                           stream_id="hand_cursor", modality=Modality.OTHER, seq=seq, **kw)
            seq += 1
            events.append(e)

        mk(t_ms[a], EventKind.MARKER, meta={"marker": "stimulus_on", "trial": n_reach,
                                             "target": [float(tx), float(-ty), 1e9, 1e9],
                                             "start": [float(start[0]), float(-start[1])]})
        for k in range(a, b + 1):
            mk(t_ms[k], EventKind.POINTER_MOVE, x=float(cur[k, 0]), y=float(-cur[k, 1]))
        mk(t_ms[b], EventKind.SELECT if False else EventKind.CLICK, x=float(cur[b, 0]), y=float(-cur[b, 1]),
           meta={"inferred": "target change = acquisition"})
        mk(t_ms[b], EventKind.MARKER, meta={"marker": "trial_end", "trial": n_reach})
        n_reach += 1
    return events


def main():
    if not DATA.exists():
        raise SystemExit(f"dataset not present: {DATA} (see experiments/external_data README)")
    import hashlib
    h = hashlib.sha256(DATA.read_bytes()).hexdigest()
    assert h == SHA256, "dataset checksum mismatch"
    t_ms, cur, tgt = load()
    evs = to_events(t_ms, cur, tgt)
    integ = check_stream(evs)
    tr = events_to_pointing_trials(evs)
    m = trial_metrics(tr)
    df = pd.DataFrame({k: v for k, v in m.items()})
    df = df.drop(columns=["success", "error", "timeout"])  # target size unknown: not computable
    df["reach"] = np.arange(len(df))
    # effective throughput by distance bin (pooled reaches)
    df["dist_bin"] = pd.qcut(df["distance_px"], 5)
    rows = []
    for bin_, d in df.groupby("dist_bin", observed=True):
        sd = d["endpoint_dx_px"].std(ddof=1)
        We = WE_FACTOR * sd
        De = d["amplitude_px"].mean()
        ide = np.log2(De / We + 1)
        mt = d["movement_time_ms"].mean() / 1000
        rows.append({"distance_bin_mm": str(bin_), "n": len(d), "De_mm": De, "We_mm": We,
                     "IDe_bits": ide, "MT_ms": mt * 1000, "TPe_bps": ide / mt})
    tp = pd.DataFrame(rows)
    save("X1_external_mc_rtt", "reaches", df.drop(columns=["dist_bin"]))
    save("X1_external_mc_rtt", "throughput_by_distance", tp)
    from .analysis import style, PALETTE
    plt = style()
    fig, axes = plt.subplots(1, 3, figsize=(10, 3))
    axes[0].hist(df["movement_time_ms"], bins=40, color=PALETTE[0])
    axes[0].set_xlabel("reach time (ms)")
    axes[1].hist(df["path_efficiency"].dropna(), bins=40, color=PALETTE[0])
    axes[1].set_xlabel("path efficiency")
    axes[2].plot(tp["IDe_bits"], tp["MT_ms"], marker="o", color=PALETTE[0])
    axes[2].set_xlabel("effective ID (bits)")
    axes[2].set_ylabel("mean reach time (ms)")
    fig.suptitle("Real data (NLB MC_RTT, macaque hand cursor): NeuroMetric metrics on canonical events")
    fig.tight_layout()
    fig.savefig(RESULTS / "X1_external_mc_rtt" / "mc_rtt_metrics.png")
    plt.close(fig)
    summ = {"dataset": "NLB MC_RTT DANDI:000129 (CC-BY-4.0), sha256 verified",
            "n_events": len(evs), "stream_integrity": {k: v for k, v in integ.items() if k != "streams"},
            "n_reaches": int(len(df)),
            "median_reach_time_ms": float(df["movement_time_ms"].median()),
            "median_path_efficiency": float(df["path_efficiency"].median()),
            "median_target_reentries_note": "not computable (target width unknown)",
            "throughput_by_distance": tp.to_dict("records"),
            "pooled_TPe_bps_mean_of_bins": float(tp["TPe_bps"].mean()),
            "synthetic": False,
            "caveats": ["able-bodied macaque hand control, not BCI, not a clinical population",
                        "acquisition time inferred from target change (includes any hold time)",
                        "effective-width throughput only; nominal ID/error rate unavailable",
                        "1 session; decimated to 100 Hz"]}
    write_summary("X1_external_mc_rtt", summ)
    print({k: summ[k] for k in ("n_reaches", "median_reach_time_ms", "median_path_efficiency",
                                "pooled_TPe_bps_mean_of_bins")})


if __name__ == "__main__":
    main()
