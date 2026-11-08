"""Neural-to-communication evaluation on the T15 cursor + click dataset (offline, open loop).

    python -m concord.evaluation.run_cursorclick [--data data/datasets/dryad-prr4xgxzq]
        [--json reports/cursorclick.json] [--write docs/CURSOR_CLICK.md] [--models data/models]

Needs all 18 blocks of day 468 (``python -m concord.datasets.dryad --subset day468``).

Protocol (no recorded bin is ever used for both fitting and scoring; time only runs forward):

1. **Selection** -- every hyper-parameter (features, smoothing, regularization, click decision
   threshold and hold) is chosen by leave-one-block-out CV on the first three calibration
   blocks (0-2) only, then frozen.
2. **Recent** models -- for each grid block g, refit on all calibration blocks recorded
   before g (what an online system recalibrating between blocks would have).
3. **Fixed** models -- fitted once on blocks 0-2 and applied to every later grid block
   (within-day stability without recalibration). These are the saved demo models.
4. Controls on the scored bins: neural features circularly shifted by half a block (keeps
   their statistics, destroys alignment with the task); chance levels; the original online
   decoders' outputs (historical, recorded) as the reference.

Everything is open loop: the participant was correcting the original cursor, not Concord's.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from concord.adapters.cursorclick.reader import T15Block, load
from concord.adapters.cursorclick.source import (
    SPACE,
    VEL_UNIT,
    neural_streams,
)
from concord.datasets.dryad import manifest, sha256_file
from concord.decoding import click as clickdec
from concord.decoding import kalman
from concord.evaluation.cursorclick import (
    REFRACTORY_BINS,
    angle_error_deg,
    click_events,
    click_metrics,
    endpoint_summary,
    intention_labels,
    r2,
    select_words,
    selection_summary,
    summarize_clicks,
)
from concord.server.settings import REPO_ROOT

FloatArray = NDArray[np.float64]
DAY = 468
SELECTION_BLOCKS = (0, 1, 2)
BOARDS = (14, 7, 2)  # board sizes that divide the 14 x 14 task grid (cells nest exactly)
IDENTITY = "dryad:10.5061/dryad.prr4xgxzq:t15"
SETTLE_BINS = 20  # click labels: first 200 ms on target excluded (reaction time)
POST_CLICK_BINS = 50  # and the 500 ms after each click (trial transition)


# ------------------------------------------------------------------------- features
@dataclass(frozen=True)
class FeatureSet:
    name: str  # "sbp" | "both"

    def inputs(self, b: T15Block) -> list[dict[str, Any]]:
        tx, sbp = neural_streams(b)
        return [sbp] if self.name == "sbp" else [tx, sbp]

    def transforms(self) -> list[str]:
        return ["log1p"] if self.name == "sbp" else ["identity", "log1p"]

    def x(self, b: T15Block) -> FloatArray:
        if self.name == "sbp":
            return b.sbp.astype(np.float64)
        return np.hstack([b.tx, b.sbp]).astype(np.float64)


def shifted(x: FloatArray) -> FloatArray:
    return np.roll(x, len(x) // 2, axis=0)


# --------------------------------------------------------------- ridge (baseline only)
@dataclass
class RidgeBaseline:
    """Evaluation-only baseline: per-input transform, causal smoothing, z-score, ridge."""

    widths: list[int]
    transforms: list[str]
    tau_ms: float
    mean: FloatArray
    std: FloatArray
    w: FloatArray
    b: FloatArray

    def predict(self, x: FloatArray) -> FloatArray:
        z = kalman.exp_smooth(
            kalman.apply_transforms(x, self.widths, self.transforms),
            kalman.smoothing_coefficient(self.tau_ms, 10.0),
        )
        out: FloatArray = ((z - self.mean) / self.std) @ self.w + self.b
        return out


def fit_ridge(
    xs: Sequence[FloatArray],
    ys: Sequence[FloatArray],
    fs: FeatureSet,
    b0: T15Block,
    p: dict[str, Any],
) -> RidgeBaseline:
    widths = [int(i["channel_count"]) for i in fs.inputs(b0)]
    a = kalman.smoothing_coefficient(p["tau_ms"], 10.0)
    z = np.vstack(
        [kalman.exp_smooth(kalman.apply_transforms(x, widths, fs.transforms()), a) for x in xs]
    )
    y = np.vstack(ys)
    mean, std = z.mean(0), z.std(0)
    std[std == 0] = 1.0
    zz = (z - mean) / std
    ym = y.mean(0)
    w = np.linalg.solve(zz.T @ zz + p["alpha"] * np.eye(zz.shape[1]), zz.T @ (y - ym))
    return RidgeBaseline(widths, fs.transforms(), p["tau_ms"], mean, std, w, ym)


# --------------------------------------------------------------------- click labels
def click_labels(b: T15Block) -> tuple[FloatArray, FloatArray]:
    """Task-defined click-attempt labels: cursor on target (the instruction), excluding the
    first 200 ms on target (reaction time) and 500 ms after each click (trial transition)."""
    on = b.on_target()
    w = np.ones(b.n_bins)
    run = 0
    for t, v in enumerate(on):
        run = run + 1 if v else 0
        if v and run <= SETTLE_BINS:
            w[t] = 0.0
    for c in b.click_bins():
        w[c + 1 : c + 1 + POST_CLICK_BINS] = 0.0
    return on.astype(np.float64), w


DECISION_GRID = [
    (th, h) for th in (0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9) for h in (5, 10, 20, 30, 40, 60, 80)
]


def decision_score(
    probs: dict[int, FloatArray], blocks: dict[int, T15Block], th: float, h: int
) -> float:
    """Task objective: clicks while the recorded cursor is on target minus clicks off target."""
    good = bad = 0
    for k, p in probs.items():
        ev = click_events(p, th, h)
        on = blocks[k].on_target()
        g = int(on[ev].sum()) if len(ev) else 0
        good += g
        bad += len(ev) - g
    return float(good - bad)


# --------------------------------------------------------------------------- runner
class Run:
    def __init__(self, data: Path) -> None:
        m = manifest("t15-cursor-click")
        self.files: dict[int, Path] = {
            f.block: data / f.filename for f in m.blocks(DAY) if f.block is not None
        }
        missing = [p.name for p in self.files.values() if not p.exists()]
        if missing:
            raise SystemExit(
                f"missing {len(missing)} day-{DAY} files in {data} (e.g. {missing[0]}); run "
                "`python -m concord.datasets.dryad --subset day468`"
            )
        self.blocks = {k: load(p) for k, p in sorted(self.files.items())}
        self.cal = [k for k, b in self.blocks.items() if b.task == "radial8_calibration"]
        self.grid = [k for k, b in self.blocks.items() if b.task == "grid_evaluation"]
        self.y = {k: intention_labels(b) for k, b in self.blocks.items()}
        self.sha = {k: sha256_file(p) for k, p in self.files.items()}

    def b(self, k: int) -> T15Block:
        return self.blocks[k]

    # ------------------------------------------------------------- model fitting
    def fit_kalman(
        self, train: Sequence[int], fs: FeatureSet, p: dict[str, Any]
    ) -> kalman.KalmanDecoder:
        b0 = self.b(train[0])
        return kalman.fit(
            [fs.x(self.b(k)) for k in train],
            [self.y[k] for k in train],
            inputs=fs.inputs(b0),
            transforms=fs.transforms(),
            smoothing_tau_ms=p["tau_ms"],
            shrinkage=p["shrink"],
            dims=["vx", "vy"],
            unit=VEL_UNIT,
            space=SPACE,
            model_id_prefix="t15",
            y_axis="up",
            training=self.training(train),
            source={
                "identity": IDENTITY,
                "description": "T15 (Singer-Clark et al., Dryad), day 468",
            },
        )

    def fit_click(
        self, train: Sequence[int], fs: FeatureSet, p: dict[str, Any]
    ) -> clickdec.ClickDecoder:
        lab = [click_labels(self.b(k)) for k in train]
        return clickdec.fit(
            [fs.x(self.b(k)) for k in train],
            [y for y, _ in lab],
            [w for _, w in lab],
            inputs=fs.inputs(self.b(train[0])),
            transforms=fs.transforms(),
            smoothing_tau_ms=p["tau_ms"],
            l2=p["l2"],
            space=SPACE,
            model_id_prefix="t15",
            training={**self.training(train), "labels": "on_target_settled"},
            source={
                "identity": IDENTITY,
                "description": "T15 (Singer-Clark et al., Dryad), day 468",
            },
        )

    def training(self, train: Sequence[int]) -> dict[str, Any]:
        return {
            "dataset": "Dryad doi:10.5061/dryad.prr4xgxzq",
            "files": [self.files[k].name for k in train],
            "sha256": [self.sha[k] for k in train],
            # block-level sessions: decoding any of these blocks is refused (leakage guard)
            "sessions": [f"t15-day{DAY:05d}-block{k:02d}" for k in train],
            "labels": "ReFIT-style intention: original decoder speed toward the cued target, "
            "zero on target",
        }

    # ------------------------------------------------------------- selection
    def select_cursor(self, family: str) -> tuple[FeatureSet, dict[str, Any], dict[str, float]]:
        sel = list(SELECTION_BLOCKS)
        if family == "kalman":
            grid = [
                (FeatureSet(f), {"tau_ms": t, "shrink": s})
                for f in ("sbp", "both")
                for t in (0.0, 30.0)
                for s in (0.1, 0.5, 0.9)
            ]
        else:
            grid = [
                (FeatureSet(f), {"tau_ms": t, "alpha": a})
                for f in ("sbp", "both")
                for t in (50.0, 100.0, 200.0)
                for a in (1e4, 1e5, 1e6)
            ]
        scores: dict[str, float] = {}
        for fs, p in grid:
            r2s = []
            for hold in sel:
                tr = [k for k in sel if k != hold]
                pred = self.predict_cursor(family, tr, fs, p, hold)
                r2s.append(r2(pred, self.y[hold]))
            scores[json.dumps([fs.name, p])] = float(np.mean(r2s))
        best = max(grid, key=lambda g: scores[json.dumps([g[0].name, g[1]])])
        return best[0], best[1], scores

    def predict_cursor(
        self,
        family: str,
        train: Sequence[int],
        fs: FeatureSet,
        p: dict[str, Any],
        k: int,
        transform: Callable[[FloatArray], FloatArray] | None = None,
    ) -> FloatArray:
        x = fs.x(self.b(k))
        x = transform(x) if transform else x
        if family == "kalman":
            return self.fit_kalman(train, fs, p).predict(x)
        ridge = fit_ridge(
            [fs.x(self.b(j)) for j in train], [self.y[j] for j in train], fs, self.b(train[0]), p
        )
        return ridge.predict(x)

    def select_click(
        self,
    ) -> tuple[FeatureSet, dict[str, Any], tuple[float, int], dict[str, float]]:
        sel = list(SELECTION_BLOCKS)
        grid = [
            (FeatureSet("both"), {"tau_ms": t, "l2": l2})
            for t in (50.0, 100.0, 200.0)
            for l2 in (1e2, 1e3, 1e4)
        ]
        scores: dict[str, float] = {}
        best: tuple[float, FeatureSet, dict[str, Any], tuple[float, int]] | None = None
        for fs, p in grid:
            probs = {}
            for hold in sel:
                if self.b(hold).assist.max() > 0:
                    continue  # clicks there were partly the computer's: not a tuning target
                tr = [k for k in sel if k != hold]
                probs[hold] = self.fit_click(tr, fs, p).predict(fs.x(self.b(hold)))[:, 0]
            dec = max(DECISION_GRID, key=lambda d: decision_score(probs, self.blocks, *d))
            s = decision_score(probs, self.blocks, *dec)
            scores[json.dumps([fs.name, p, dec])] = s
            if best is None or s > best[0]:
                best = (s, fs, p, dec)
        assert best is not None
        return best[1], best[2], best[3], scores


def _mean(rows: list[dict[str, Any]], key: str) -> float:
    vals = [r[key] for r in rows if r.get(key) is not None]
    return float(np.mean(vals)) if vals else float("nan")


def run(data: Path, models_dir: Path | None) -> dict[str, Any]:
    t0 = time.time()
    R = Run(data)
    print(f"loaded {len(R.blocks)} blocks: calibration {R.cal}, grid {R.grid}", flush=True)
    k_fs, k_p, k_scores = R.select_cursor("kalman")
    print(f"kalman selected: {k_fs.name} {k_p}", flush=True)
    r_fs, r_p, r_scores = R.select_cursor("ridge")
    print(f"ridge selected: {r_fs.name} {r_p}", flush=True)
    c_fs, c_p, (c_th, c_hold), c_scores = R.select_click()
    print(f"click selected: {c_fs.name} {c_p} threshold {c_th} hold {c_hold}", flush=True)

    fixed_train = [k for k in R.cal if k in SELECTION_BLOCKS]
    fixed_kalman = R.fit_kalman(fixed_train, k_fs, k_p)
    fixed_click = R.fit_click(fixed_train, c_fs, c_p)
    fixed_click.decision = {
        "threshold": c_th,
        "hold_bins": c_hold,
        "bin_ms": 10.0,
        "refractory_ms": REFRACTORY_BINS * 10,
        "release": max(0.0, c_th - clickdec.RELEASE_GAP),
        "router_click_rule": clickdec.router_click_rule(
            {"threshold": c_th, "hold_bins": c_hold, "refractory_ms": REFRACTORY_BINS * 10}
        ),
        "chosen_on": "leave-one-block-out out-of-fold probabilities, calibration blocks 0-2",
    }

    rows: list[dict[str, Any]] = []
    sel_rows: dict[str, list[dict[str, Any]]] = {}
    clicks: dict[str, list[dict[str, Any]]] = {
        "recent": [],
        "fixed": [],
        "original": [],
        "shifted": [],
    }
    for g in R.grid:
        b = R.b(g)
        train = [k for k in R.cal if k < g]
        y = R.y[g]
        kal = R.fit_kalman(train, k_fs, k_p)
        xk = k_fs.x(b)
        pk = kal.predict(xk)
        pk_fixed = fixed_kalman.predict(xk)
        pk_shift = kal.predict(shifted(xk))
        pr = R.predict_cursor("ridge", train, r_fs, r_p, g)
        clk = R.fit_click(train, c_fs, c_p)
        xc = c_fs.x(b)
        ev = click_events(clk.predict(xc)[:, 0], c_th, c_hold)
        ev_fixed = click_events(fixed_click.predict(xc)[:, 0], c_th, c_hold)
        ev_shift = click_events(clk.predict(shifted(xc))[:, 0], c_th, c_hold)
        orig_ev = b.click_bins()
        clicks["recent"].append(click_metrics(ev, b))
        clicks["fixed"].append(click_metrics(ev_fixed, b))
        clicks["original"].append(click_metrics(orig_ev, b))
        clicks["shifted"].append(click_metrics(ev_shift, b))
        row: dict[str, Any] = {"block": g, "train_blocks": train, "file": R.files[g].name}
        for name, pred in (
            ("kalman", pk),
            ("kalman_fixed", pk_fixed),
            ("ridge", pr),
            ("original", b.cursor_decoder),
            ("kalman_shifted", pk_shift),
        ):
            ep = endpoint_summary(pred, b, BOARDS)
            row[name] = {
                "angle_error_deg": angle_error_deg(pred, b),
                "r2_vs_intention": r2(pred, y),
                "corr_with_original": float(
                    np.mean([np.corrcoef(pred[:, i], b.cursor_decoder[:, i])[0, 1] for i in (0, 1)])
                ),
                **ep,
            }
        rows.append(row)
        secs = b.duration_s
        combos = {
            "historical (original cursor + original click), board integration": (
                b.cursor_decoder,
                orig_ev,
                "board",
            ),
            "historical (original cursor + original click), whole block": (
                b.cursor_decoder,
                orig_ev,
                "whole_block",
            ),
            "historical (original cursor + original click), anchored per trial": (
                b.cursor_decoder,
                orig_ev,
                "anchored",
            ),
            "Concord (Kalman + click), board integration": (pk, ev, "board"),
            "Concord (Kalman + click), anchored per trial": (pk, ev, "anchored"),
            "Concord (fixed Kalman + fixed click), board integration": (
                pk_fixed,
                ev_fixed,
                "board",
            ),
            "Concord Kalman + original click times, anchored": (pk, orig_ev, "anchored"),
            "original cursor + Concord clicks, anchored": (b.cursor_decoder, ev, "anchored"),
            "control: shifted features (Kalman + click), anchored": (
                pk_shift,
                ev_shift,
                "anchored",
            ),
        }
        for label, (vel, cl, mode) in combos.items():
            for n in BOARDS:
                s = selection_summary(select_words(vel, cl, b, n, mode=mode), n, secs)
                sel_rows.setdefault(f"{label}|{n}", []).append(s)
        print(
            f"grid block {g:02d} (train {train}): kalman R2 {row['kalman']['r2_vs_intention']:.3f} "
            f"angle {row['kalman']['angle_error_deg']:.1f}; ridge R2 {row['ridge']['r2_vs_intention']:.3f}; "
            f"clicks {len(ev)} vs original {len(orig_ev)}",
            flush=True,
        )

    def agg(name: str) -> dict[str, float]:
        keys = (
            "angle_error_deg",
            "r2_vs_intention",
            "corr_with_original",
            "endpoint_error_median",
            "progress_median",
        )
        out = {k: _mean([r[name] for r in rows], k) for k in keys}
        for n in BOARDS:
            out[f"board_{n}x{n}"] = float(
                np.mean([r[name]["board_accuracy"][f"{n}x{n}"] for r in rows])
            )
        return out

    selections: dict[str, dict[str, Any]] = {}
    for key, ss in sel_rows.items():
        label, size = key.rsplit("|", 1)
        tot = {k: sum(s[k] for s in ss) for k in ("trials", "selections", "correct")}
        selections.setdefault(label, {})[f"{size}x{size}"] = {
            **tot,
            "accuracy_per_trial": tot["correct"] / tot["trials"],
            "accuracy_per_selection": tot["correct"] / tot["selections"]
            if tot["selections"]
            else None,
            "chance": 1 / int(size) ** 2,
            "bitrate_bps": float(np.mean([s["bitrate_bps"] for s in ss])),
        }

    # saved demo models: trained on blocks 0-2, evaluated on every later grid block
    saved: dict[str, Any] = {}
    for r in rows:
        g = r["block"]
        fixed_kalman.evaluations.append(
            {
                "file": r["file"],
                "sha256": R.sha[g],
                "session": f"t15-day{DAY:05d}-block{g:02d}",
                "r2": r["kalman_fixed"]["r2_vs_intention"],
                "angle_error_deg": r["kalman_fixed"]["angle_error_deg"],
                "control_time_shift_r2": None,
            }
        )
    fixed_click.evaluations = [
        {
            "file": R.files[g].name,
            "sha256": R.sha[g],
            "session": f"t15-day{DAY:05d}-block{g:02d}",
            **{k: v for k, v in summarize_clicks([m]).items() if k != "lag_iqr_ms"},
        }
        for g, m in zip(R.grid, clicks["fixed"], strict=True)
    ]
    if models_dir is not None:
        for m in (fixed_kalman, fixed_click):
            p = m.save(models_dir / f"{m.model_id}.json")
            saved[m.kind] = {"model_id": m.model_id, "path": str(p)}

    return {
        "dataset": "Singer-Clark et al., Dryad doi:10.5061/dryad.prr4xgxzq (CC0), participant T15, day 468",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "runtime_s": round(time.time() - t0, 1),
        "platform": platform.platform(),
        "blocks": {"calibration": R.cal, "grid": R.grid},
        "selection": {
            "blocks": list(SELECTION_BLOCKS),
            "kalman": {"features": k_fs.name, **k_p, "cv_r2": k_scores},
            "ridge": {"features": r_fs.name, **r_p, "cv_r2": r_scores},
            "click": {
                "features": c_fs.name,
                **c_p,
                "threshold": c_th,
                "hold_bins": c_hold,
                "cv_score": c_scores,
            },
        },
        "cursor": {
            name: agg(name)
            for name in ("kalman", "kalman_fixed", "ridge", "original", "kalman_shifted")
        },
        "cursor_per_block": rows,
        "click": {k: summarize_clicks(v) for k, v in clicks.items()},
        "click_per_block": {k: [summarize_clicks([m]) for m in v] for k, v in clicks.items()},
        "selections": selections,
        "models": saved,
    }


# -------------------------------------------------------------------------- report
def _f(v: Any, nd: int = 3) -> str:
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "—"
    return f"{v:.{nd}f}" if isinstance(v, float) else str(v)


def markdown(res: dict[str, Any]) -> str:
    c = res["cursor"]
    sel = res["selection"]
    lines = [
        "# Cursor + click decoding and neural-to-communication (T15, offline)",
        "",
        "Generated by `python -m concord.evaluation.run_cursorclick` "
        f"({res['generated_at']}, {res['runtime_s']} s). Do not edit by hand.",
        "",
        f"**Data:** {res['dataset']}. Calibration (Radial8) blocks {res['blocks']['calibration']}, "
        f"grid-evaluation blocks {res['blocks']['grid']}; 256 electrodes, 10 ms bins, threshold "
        "crossings and spike band power as published (no raw signal is published).",
        "",
        "**What this is:** offline, open-loop decoding of recorded closed-loop sessions. During "
        "recording the participant controlled the *original* research decoder and corrected *its* "
        "cursor. Concord's decoders here never had a person in the loop. These numbers say how well "
        "Concord recovers the recorded intention; they do **not** say how well a person would "
        "communicate with Concord (that needs a closed-loop study under an approved protocol).",
        "",
        "## Protocol",
        "",
        "- Hyper-parameters are chosen by leave-one-block-out CV on calibration blocks "
        f"{sel['blocks']} only, then frozen. Grid block *g* is decoded by a model refitted on the "
        'calibration blocks recorded **before** *g* ("recent"), and by the model fitted once on '
        'blocks 0-2 ("fixed", the saved demo models). No grid block is ever used for fitting or '
        "selection.",
        "- Cursor labels: ReFIT-style intended velocity (the original decoder's speed, pointed at the "
        "cued target; zero while the cursor touches it).",
        "- Click labels: the task instruction (attempt a click while the cursor touches the target): "
        "on-target bins positive, excluding the first 200 ms on target and the 500 ms after each "
        "click; the decision (the command router's click rule: threshold + hold + 1 s refractory + "
        "hysteresis) is chosen on out-of-fold probabilities of blocks 0-2.",
        "- Controls: features circularly shifted by half a block against the task; chance levels; the "
        "original online decoders' recorded outputs as the reference (historical, not Concord).",
        "",
        "## Selected models",
        "",
        f"- Kalman: features `{sel['kalman']['features']}`, smoothing {sel['kalman']['tau_ms']:g} ms, "
        f"noise shrinkage {sel['kalman']['shrink']:g}.",
        f"- Ridge (baseline): features `{sel['ridge']['features']}`, smoothing {sel['ridge']['tau_ms']:g} ms, "
        f"alpha {sel['ridge']['alpha']:g}.",
        f"- Click: features `{sel['click']['features']}`, smoothing {sel['click']['tau_ms']:g} ms, "
        f"L2 {sel['click']['l2']:g}; decision P >= {sel['click']['threshold']:g} for "
        f"{sel['click']['hold_bins']} bins ({(sel['click']['hold_bins'] - 1) * 10} ms router "
        "debounce), 1 s refractory, re-armed when P falls 0.15 below the threshold (the command "
        "router's click rule).",
        "",
        "## Cursor decoding (mean over grid blocks)",
        "",
        "| Decoder | Angle error (°) | R² vs intention | Corr. with original | "
        "Endpoint error (screen h.) | Progress to target | 14×14 | 7×7 | 2×2 |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    names = {
        "original": "Original online decoder (historical, recorded)",
        "kalman": "Concord Kalman (recent)",
        "kalman_fixed": "Concord Kalman (fixed, blocks 0-2)",
        "ridge": "Concord ridge baseline (recent)",
        "kalman_shifted": "Control: Kalman on shifted features",
    }
    for k, label in names.items():
        r = c[k]
        lines.append(
            f"| {label} | {_f(r['angle_error_deg'], 1)} | {_f(r['r2_vs_intention'])} | "
            f"{_f(r['corr_with_original'])} | {_f(r['endpoint_error_median'])} | "
            f"{_f(r['progress_median'], 2)} | {_f(r['board_14x14'], 2)} | {_f(r['board_7x7'], 2)} | "
            f"{_f(r['board_2x2'], 2)} |"
        )
    lines += [
        "",
        "Angle error: chance 90°. Board columns: fraction of trials whose open-loop endpoint (cursor "
        "anchored at the recorded trial-start position, decoded velocity integrated to the trial's "
        "click) lies in the cued cell of an n×n board over the task grid (chance 1/n²). Progress: "
        "fraction of the start-to-target distance covered.",
        "",
        "## Click decoding (all grid blocks)",
        "",
        "| Clicks from | Clicks/min | Precision vs original | Recall vs original | Median lag (ms) | "
        "On target at click | False activations/min | Trials with an on-target click |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    cn = {
        "original": "Original online click decoder (historical)",
        "recent": "Concord click (recent)",
        "fixed": "Concord click (fixed, blocks 0-2)",
        "shifted": "Control: shifted features",
    }
    for k, label in cn.items():
        r = res["click"][k]
        lines.append(
            f"| {label} | {_f(r['clicks_per_min'], 1)} | {_f(r['precision_vs_original'])} | "
            f"{_f(r['recall_vs_original'])} | {_f(r['lag_median_ms'], 0)} | "
            f"{_f(r['task_correct_fraction'])} | {_f(r['false_activations_per_min'], 2)} | "
            f"{_f(r['trials_completed_fraction'])} |"
        )
    lines += [
        "",
        "Matching tolerance ±250 ms. *On target at click*: the recorded cursor touched the cued "
        "target when the click fired. *Trials with an on-target click*: a click fired while the "
        "recorded cursor was on the target, no later than 250 ms after the original click ended "
        "the trial. Dwell selection is not a neural click and is not reported here.",
        "",
        "## Word selection on a board (all grid blocks)",
        "",
        "One word per board cell; the cued grid target defines the intended word. Per trial, the "
        "first click (between the trial start and 250 ms after the original click) selects the cell "
        "under the integrated cursor.",
        "",
        "| Chain | Board | Trials | Correct | Accuracy | Chance | Bitrate (bits/s) |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for label, by_board in res["selections"].items():
        for board, s in by_board.items():
            lines.append(
                f"| {label} | {board} | {s['trials']} | {s['correct']} | {_f(s['accuracy_per_trial'], 3)} | "
                f"{_f(s['chance'], 4)} | {_f(s['bitrate_bps'], 2)} |"
            )
    lines += [
        "",
        "*Board integration*: exactly what the communication board does with the stream (cursor "
        "starts at the centre, integrated per event, clamped to the grid); this is the chain the "
        "end-to-end test drives. *Whole block*: integrated from the block's first recorded "
        "position. *Anchored per trial*: the cursor restarts each "
        "trial at the recorded position the participant saw (analysis only; recorded positions are "
        "never fed to an application). Even the original decoder's own outputs drift when integrated "
        "open loop over a whole block (the display loop updated the cursor about every 20 ms and is "
        "not exactly reproducible from the published fields); anchored, they reproduce the session.",
        "",
        "## Limits",
        "",
        "- One participant, one day, open loop. No closed-loop evaluation of Concord decoders exists.",
        "- Labels are inferred from the task (intention, click attempt), not observed.",
        "- The original click decoder's timing shaped the trial structure (a click ended the trial), "
        "so recall against it is biased against any different decoder.",
        "- Bitrate uses the authors' grid formula on open-loop selections; it is not a communication "
        "rate a person achieved with Concord.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument(
        "--data", type=Path, default=REPO_ROOT / "data" / "datasets" / "dryad-prr4xgxzq"
    )
    ap.add_argument("--json", type=Path, default=REPO_ROOT / "reports" / "cursorclick.json")
    ap.add_argument("--write", type=Path, default=None, help="write the markdown report here")
    ap.add_argument("--models", type=Path, default=REPO_ROOT / "data" / "models")
    ap.add_argument("--no-models", action="store_true")
    args = ap.parse_args(argv)
    res = run(args.data, None if args.no_models else args.models)
    args.json.parent.mkdir(parents=True, exist_ok=True)
    args.json.write_text(json.dumps(res, indent=1, default=float))
    print(f"wrote {args.json}")
    if args.write:
        args.write.write_text(markdown(res))
        print(f"wrote {args.write}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
