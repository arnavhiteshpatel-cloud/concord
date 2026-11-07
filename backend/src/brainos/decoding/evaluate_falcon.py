"""Offline evaluation of the baseline decoder on FALCON H1 (DANDI 000954) + demo model.

    python -m brainos.decoding.evaluate_falcon [--data data/datasets/dandi-000954]
                                               [--write docs/DECODING.md]

Evaluations (no sample is ever in both training and scoring):
  A. within-block: each calibration block split in time at a trial boundary (~80/20);
     train on the first part, score the second part.
  B. cross-block, same day: train on one block, score the next block recorded that day.
Each score is reported with two controls computed on the same scored samples:
  - mean predictor: always predict the training-set mean velocity,
  - time-shift: the same model fed neural data circularly shifted by half the test
    length (destroys the neural/behavior alignment while keeping firing statistics).

Note: FALCON's "held-in-minival" files are a subset (the first bins) of the matching
"held-in-calib" files, so calib->minival is NOT a valid held-out evaluation and is not
used here.

Also writes the demo model (train: block 19250108T110520, scored on 19250108T111022) to
data/models/, which the runtime attaches only to the block it was evaluated on.
"""

from __future__ import annotations

import argparse
import itertools
import json
import platform
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from brainos.adapters.nwb.reader import NWBUnitsRecording, load
from brainos.datasets import manifest, session_of, sha256_file
from brainos.decoding.ridge import RidgeDecoder, evaluate, fit
from brainos.server.settings import REPO_ROOT

SPACE = "falcon_h1_7dof"
DEMO_TRAIN = "sub-HumanPitt-held-in-calib_ses-19250108T110520.nwb"
DEMO_EVAL = "sub-HumanPitt-held-in-calib_ses-19250108T111022.nwb"


def _counts(rec: NWBUnitsRecording) -> np.ndarray:
    return np.concatenate([c for _, c in rec.iter_counts()]).astype(np.float64)


def _split_at_trial(rec: NWBUnitsRecording, frac: float = 0.8) -> int:
    n = rec.n_bins
    target = int(frac * n)
    assert rec.behavior is not None
    trial = rec.behavior.trial
    if trial is None:
        return target
    changes = np.flatnonzero(np.diff(trial) != 0) + 1
    after = changes[changes >= target]
    return int(after[0]) if after.size else target


def _train(rec: NWBUnitsRecording, counts: np.ndarray, stop: int, sha: str) -> RidgeDecoder:
    assert rec.behavior is not None
    b = rec.behavior
    return fit(
        counts[:stop],
        b.values[:stop],
        b.valid[:stop],
        dims=b.dims,
        unit=b.unit,
        bin_ms=rec.bin_s * 1000,
        space=SPACE,
        training={
            "dataset": "DANDI:000954",
            "file": rec.path.name,
            "sha256": sha,
            "session": session_of(rec.path.name),
            "bins": [0, int(stop)],
        },
    )


def run(data_dir: Path) -> dict[str, Any]:
    m = manifest("falcon-h1")
    calib = sorted(p for p in data_dir.glob("*held-in-calib*.nwb"))
    if not calib:
        raise SystemExit(
            f"no calibration files in {data_dir}; run: python -m brainos.datasets.fetch --all-calib"
        )
    recs: dict[str, tuple[NWBUnitsRecording, np.ndarray, str]] = {}
    for p in calib:
        sha = sha256_file(p)
        if m.find(sha) is None:
            raise SystemExit(f"{p.name}: checksum does not match the pinned DANDI manifest")
        rec = load(p)
        recs[p.name] = (rec, _counts(rec), sha)

    within = []
    for name, (rec, counts, sha) in recs.items():
        split = _split_at_trial(rec)
        model = _train(rec, counts, split, sha)
        assert rec.behavior is not None
        res = evaluate(
            model,
            counts[split:],
            rec.behavior.values[split:],
            rec.behavior.valid[split:],
            skip_first=len(model.kernel),
        )
        within.append(
            {
                "block": session_of(name),
                "train_bins": split,
                "test_bins": rec.n_bins - split,
                "alpha": model.alpha,
                **res,
            }
        )

    by_day: dict[str, list[str]] = defaultdict(list)
    for name in recs:
        by_day[(session_of(name) or "")[:8]].append(name)
    cross = []
    for _, names in sorted(by_day.items()):
        names.sort()
        for a, b in itertools.pairwise(names):
            ra, ca, sa = recs[a]
            rb, cb, _ = recs[b]
            model = _train(ra, ca, ra.n_bins, sa)
            assert rb.behavior is not None
            res = evaluate(
                model, cb, rb.behavior.values, rb.behavior.valid, skip_first=len(model.kernel)
            )
            cross.append(
                {"train": session_of(a), "test": session_of(b), "alpha": model.alpha, **res}
            )

    # demo model, attached by the runtime to DEMO_EVAL replay only
    demo = None
    if DEMO_TRAIN in recs and DEMO_EVAL in recs:
        ra, ca, sa = recs[DEMO_TRAIN]
        rb, cb, sb = recs[DEMO_EVAL]
        model = _train(ra, ca, ra.n_bins, sa)
        assert rb.behavior is not None
        res = evaluate(
            model, cb, rb.behavior.values, rb.behavior.valid, skip_first=len(model.kernel)
        )
        model.evaluations.append(
            {"file": DEMO_EVAL, "sha256": sb, "session": session_of(DEMO_EVAL), **res}
        )
        path = model.save(REPO_ROOT / "data" / "models" / f"{model.model_id}.json")
        demo = {"model_id": model.model_id, "path": str(path.relative_to(REPO_ROOT)), **res}
    return {"within_block": within, "cross_block": cross, "demo_model": demo}


def _summary(rows: list[dict[str, Any]], key: str) -> str:
    v = np.array([r[key] for r in rows], dtype=float)
    return f"{v.mean():.3f} ± {v.std():.3f} (min {v.min():.3f}, max {v.max():.3f})"


def to_markdown(res: dict[str, Any], seconds: float) -> str:
    w, c, d = res["within_block"], res["cross_block"], res["demo_model"]
    lines = [
        "# Offline decoding results — FALCON H1 (DANDI 000954)",
        "",
        "> Generated by `python -m brainos.decoding.evaluate_falcon` "
        f"on {time.strftime('%Y-%m-%d')} ({platform.machine()}, Python {sys.version.split()[0]}, "
        f"{seconds:.1f} s). Do not edit by hand; re-run to regenerate.",
        "",
        "**What this is:** offline, open-loop decoding of *attempted* 7-DoF arm/hand velocity "
        "(cued kinematics recorded during calibration) from binned multi-unit spike counts of "
        "one human participant. **What this is not:** closed-loop BCI control. Offline R² does "
        "not establish that a user could control a device in real time.",
        "",
        "Metric: variance-weighted R² over `eval_mask` samples (FALCON metric). Model: causal "
        "exponential filter (τ 240 ms) → z-score (train stats) → ridge (alpha by blocked 5-fold CV "
        "inside training data). The first 12 bins of each scored segment are excluded (filter warm-up).",
        "",
        "## A. Within-block (chronological ~80/20 split at a trial boundary)",
        "",
        f"Blocks: {len(w)}. **R² {_summary(w, 'r2')}** · mean-predictor control "
        f"{_summary(w, 'control_mean_predictor_r2')} · time-shift control {_summary(w, 'control_time_shift_r2')}",
        "",
        "| block | train bins | test bins | scored | alpha | R² | mean ctrl | shift ctrl |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in w:
        lines.append(
            f"| {r['block']} | {r['train_bins']} | {r['test_bins']} | {r['samples']} | {r['alpha']:g} "
            f"| {r['r2']:.3f} | {r['control_mean_predictor_r2']:.3f} | {r['control_time_shift_r2']:.3f} |"
        )
    lines += [
        "",
        "## B. Cross-block, same day (train on one block, score the next block that day)",
        "",
        f"Pairs: {len(c)}. **R² {_summary(c, 'r2')}** · mean-predictor control "
        f"{_summary(c, 'control_mean_predictor_r2')} · time-shift control {_summary(c, 'control_time_shift_r2')}",
        "",
        "| train block | test block | scored | alpha | R² | mean ctrl | shift ctrl |",
        "|---|---|---:|---:|---:|---:|---:|",
    ]
    for r in c:
        lines.append(
            f"| {r['train']} | {r['test']} | {r['samples']} | {r['alpha']:g} | {r['r2']:.3f} "
            f"| {r['control_mean_predictor_r2']:.3f} | {r['control_time_shift_r2']:.3f} |"
        )
    if d:
        lines += [
            "",
            "## Demo model used by the runtime",
            "",
            f"`{d['model_id']}` — trained on block 19250108T110520 (all bins), scored on block "
            f"19250108T111022: **R² {d['r2']:.3f}** (mean-predictor {d['control_mean_predictor_r2']:.3f}, "
            f"time-shift {d['control_time_shift_r2']:.3f}, {d['samples']} samples).",
            "",
            "Per-dimension R²: " + ", ".join(f"{k} {v:.2f}" for k, v in d["r2_per_dim"].items()),
            "",
            "The runtime attaches this model only when replaying the block it was scored on, and "
            "refuses to attach it to any file from its training session.",
        ]
    lines += [
        "",
        "## Limitations",
        "",
        "- One participant, one task (cued open-loop reach/grasp), ~4 minutes per block.",
        "- Kinematics are *cued* (the participant attempted to follow), in arbitrary units.",
        "- Within-day only. Cross-day decoding (FALCON held-out sessions) is not evaluated "
        "here; performance is expected to drop without recalibration.",
        "- Linear baseline only; no claim of state-of-the-art performance.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data", type=Path, default=REPO_ROOT / "data" / "datasets" / "dandi-000954")
    ap.add_argument("--write", type=Path, default=None)
    ap.add_argument("--json", type=Path, default=REPO_ROOT / "reports" / "decoding.json")
    args = ap.parse_args(argv)
    t0 = time.perf_counter()
    res = run(args.data)
    seconds = time.perf_counter() - t0
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(res, indent=1, default=float))
    md = to_markdown(res, seconds)
    print(md)
    if args.write:
        args.write.write_text(md)
        print(f"wrote {args.write}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
