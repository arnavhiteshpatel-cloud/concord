"""Reproducible neural-to-communication test: helpers for ``e2e/communication.cjs``.

    python -m brainos.evaluation.board_e2e prepare --out DIR
    python -m brainos.evaluation.board_e2e compare --plan DIR/plan.json --mode historical \\
        --observed obs.json --position-s 1.23 --out reports/communication_e2e.json

``prepare`` builds a BrainOS data directory for the test server: the T15 demo blocks (symlinked,
verified on open), and BrainOS Kalman + click models fitted on calibration blocks 0-2 only
(the settings ``run_cursorclick`` selects), plus ``plan.json`` with the router settings of the
two chains.

``compare`` predicts, offline, exactly what the communication board must select from the
replayed grid block -- the router's mapping (native velocity x gain, y inverted, rounded to
1e-6), its click rule, and the board's integration (centre start, the first event only starts
the clock, 10 ms steps, clamped to the unit square, tile = row * n + col) -- and compares it with
the board's own record of what it selected (``window.__brainosBoard``). It also scores the
selections against the cued task targets, i.e. the words the participant was asked to reach.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from brainos.adapters.cursorclick.reader import BIN_S, T15Block, load
from brainos.adapters.cursorclick.source import device_id_for, neural_streams
from brainos.datasets.dryad import manifest
from brainos.decoding import click as clickdec
from brainos.decoding import kalman
from brainos.evaluation.cursorclick import board_cells, intention_labels, trials
from brainos.evaluation.run_cursorclick import click_labels
from brainos.server.settings import REPO_ROOT

FloatArray = NDArray[np.float64]
DAY, TRAIN_BLOCKS, GRID_BLOCK = 468, (0, 1, 2), 3
N = 14
GAIN = 1 / 0.92  # board workspace (unit square) = the task grid (0.92 screen heights)
IDENTITY = "dryad:10.5061/dryad.prr4xgxzq:t15"
# settings selected by run_cursorclick (CV on blocks 0-2; docs/CURSOR_CLICK.md)
KALMAN = {"smoothing_tau_ms": 0.0, "shrinkage": 0.1}
CLICK = {"smoothing_tau_ms": 50.0, "l2": 1000.0, "threshold": 0.7, "hold_bins": 10}
HISTORICAL_CLICK_RULE = {"output": "click", "threshold": 0.5, "refractory_ms": 300.0}


def _files(data: Path) -> dict[int, Path]:
    m = manifest("t15-cursor-click")
    return {f.block: data / f.filename for f in m.blocks(DAY) if f.block is not None}


def router(click: dict[str, Any]) -> dict[str, Any]:
    return {
        "enabled": True,
        "x_dim": "vx",
        "y_dim": "vy",
        "pointer_scale": "native",
        "gain": GAIN,
        "deadzone": 0.0,
        "invert_y": True,
        "max_speed": 10.0,
        "click": click,
    }


def prepare(data: Path, out: Path) -> dict[str, Any]:
    files = _files(data)
    need = [files[k] for k in (*TRAIN_BLOCKS, GRID_BLOCK)]
    missing = [p.name for p in need if not p.exists()]
    if missing:
        raise SystemExit(f"missing {missing}; run `python -m brainos.datasets.dryad`")
    (out / "datasets").mkdir(parents=True, exist_ok=True)
    (out / "models").mkdir(parents=True, exist_ok=True)
    for p in need:
        link = out / "datasets" / p.name
        if not link.exists():
            link.symlink_to(p.resolve())
    cal = [load(files[k]) for k in TRAIN_BLOCKS]
    inputs = neural_streams(cal[0])
    feats = [np.hstack([b.tx, b.sbp]).astype(np.float64) for b in cal]
    training = {
        "dataset": "Dryad doi:10.5061/dryad.prr4xgxzq",
        "files": [files[k].name for k in TRAIN_BLOCKS],
        "sessions": [f"t15-day{DAY:05d}-block{k:02d}" for k in TRAIN_BLOCKS],
    }
    source = {"identity": IDENTITY, "description": "T15 (Singer-Clark et al., Dryad), day 468"}
    kal = kalman.fit(
        feats,
        [intention_labels(b) for b in cal],
        inputs=inputs,
        transforms=["identity", "log1p"],
        dims=["vx", "vy"],
        unit="screen_height/s",
        space="t15_screen",
        model_id_prefix="t15",
        y_axis="up",
        training=training,
        source=source,
        smoothing_tau_ms=KALMAN["smoothing_tau_ms"],
        shrinkage=KALMAN["shrinkage"],
    )
    lab = [click_labels(b) for b in cal]
    clk = clickdec.fit(
        feats,
        [y for y, _ in lab],
        [w for _, w in lab],
        inputs=inputs,
        transforms=["identity", "log1p"],
        smoothing_tau_ms=CLICK["smoothing_tau_ms"],
        l2=CLICK["l2"],
        space="t15_screen",
        model_id_prefix="t15",
        training={**training, "labels": "on_target_settled"},
        source=source,
    )
    clk.decision = {
        "threshold": CLICK["threshold"],
        "hold_bins": CLICK["hold_bins"],
        "refractory_ms": 1000.0,
    }
    kal.save(out / "models" / f"{kal.model_id}.json")
    clk.save(out / "models" / f"{clk.model_id}.json")
    grid = load(files[GRID_BLOCK])
    plan = {
        "device_id": device_id_for(grid),
        "grid_file": str(files[GRID_BLOCK].resolve()),
        "models_dir": str(out / "models"),
        "n": N,
        "modes": {
            "historical": {
                "processing": {"preset": "decoded_passthrough"},
                "router": router(HISTORICAL_CLICK_RULE),
            },
            "brainos": {
                "processing": {"preset": "features_passthrough"},
                "model_id": kal.model_id,
                "model_ids": [clk.model_id],
                "router": router(clickdec.router_click_rule(clk.decision)),
            },
        },
    }
    (out / "plan.json").write_text(json.dumps(plan, indent=1))
    return plan


# ----------------------------------------------------------------------------- expected
def _router_click_bins(p: FloatArray, rule: dict[str, Any]) -> NDArray[np.int64]:
    hold = round(float(rule.get("debounce_ms", 0.0)) / (BIN_S * 1000)) + 1
    refr = round(float(rule["refractory_ms"]) / (BIN_S * 1000))
    return clickdec.decision_events(p, float(rule["threshold"]), hold, refr, rule.get("release"))


def expected(plan: dict[str, Any], mode: str, k0: int, n: int | None = None) -> dict[str, Any]:
    """What the board must do if the chain starts at bin ``k0`` (first pointer event)."""
    b = load(Path(plan["grid_file"]))
    spec = plan["modes"][mode]
    if mode == "historical":
        vel = b.cursor_decoder[k0:]
        assert b.click_decoder is not None
        p = b.click_decoder[k0:].astype(np.float64)
    else:
        mdir = Path(plan["models_dir"])
        kal = kalman.KalmanDecoder.load(mdir / f"{spec['model_id']}.json")
        clk = clickdec.ClickDecoder.load(mdir / f"{spec['model_ids'][0]}.json")
        x = np.hstack([b.tx, b.sbp]).astype(np.float64)[k0:]
        vel = kal.predict(x)  # decoder state starts with the pipeline, at k0
        p = clk.predict(x)[:, 0]
    r = spec["router"]
    vx = np.round(np.clip(r["gain"] * vel[:, 0], -r["max_speed"], r["max_speed"]), 6)
    vy = np.round(np.clip(r["gain"] * vel[:, 1], -r["max_speed"], r["max_speed"]), 6)
    vy = -vy  # invert_y: +y up (task) -> +y down (board)
    pos = np.empty((len(vel), 2))
    x_b, y_b = 0.5, 0.5
    for t in range(len(vel)):
        if t > 0:  # the first pointer event only starts the board's clock
            x_b = min(1.0, max(0.0, x_b + vx[t] * BIN_S))
            y_b = min(1.0, max(0.0, y_b + vy[t] * BIN_S))
        pos[t] = (x_b, y_b)
    clicks = _router_click_bins(p, r["click"]) + k0
    n = int(n or plan["n"])
    sel = []
    for c in clicks.tolist():
        cx, cy = pos[c - k0]
        col = min(n - 1, max(0, int(np.floor(cx * n))))
        row = min(n - 1, max(0, int(np.floor(cy * n))))
        sel.append({"bin": c, "tile": row * n + col, "cursor": [float(cx), float(cy)]})
    return {"selections": sel, "block": b}


def cued_tile(b: T15Block, bin_: int, n: int) -> int | None:
    """The task's cued target during the trial containing ``bin_`` (row 0 at the top)."""
    for s, e in trials(b):
        if s <= bin_ <= e + 25:
            col, row_up = board_cells(b.target[e][None, :], b, n)[0]
            return int((n - 1 - row_up) * n + col)
    return None


def compare(
    plan: dict[str, Any],
    mode: str,
    observed: dict[str, Any],
    position_s: float,
    n: int | None = None,
) -> dict[str, Any]:
    obs = [
        {
            "bin": round(int(s["event"]["deviceTimestampNs"]) / 1e7) - 1,
            "tile": int(s["tile"]),
            "label": s.get("label"),
            "cursor": [float(s["cursor"]["x"]), float(s["cursor"]["y"])],
        }
        for s in observed["selections"]
        if s.get("via") == "click" and s.get("event", {}).get("deviceTimestampNs") is not None
    ]
    if not obs:
        raise SystemExit("the board recorded no click selections")
    last_emitted = round(position_s / BIN_S) - 1
    # the chain started with the first bin the pipeline saw after the pause: try the few
    # candidates around the playback position; the board's own cursor at its selections
    # identifies it (reported, never tuned on the outcome)
    best: tuple[float, int, dict[str, Any]] | None = None
    for k0 in range(max(0, last_emitted - 2), last_emitted + 4):
        exp = expected(plan, mode, k0, n)
        by_bin = {s["bin"]: s for s in exp["selections"]}
        errs = [
            float(np.max(np.abs(np.subtract(o["cursor"], by_bin[o["bin"]]["cursor"]))))
            for o in obs[:5]
            if o["bin"] in by_bin
        ]
        err = max(errs) if errs else float("inf")
        if best is None or err < best[0]:
            best = (err, k0, exp)
    assert best is not None
    first_err, k0, exp = best
    b: T15Block = exp["block"]
    n = int(n or plan["n"])
    last_obs = max(o["bin"] for o in obs)
    expected_sel = [s for s in exp["selections"] if s["bin"] <= last_obs]
    e_by_bin = {s["bin"]: s for s in expected_sel}
    o_by_bin = {o["bin"]: o for o in obs}
    common = sorted(set(e_by_bin) & set(o_by_bin))
    same_tile = sum(e_by_bin[t]["tile"] == o_by_bin[t]["tile"] for t in common)
    max_cursor_err = max(
        float(np.max(np.abs(np.subtract(e_by_bin[t]["cursor"], o_by_bin[t]["cursor"]))))
        for t in common
    )
    cued = [cued_tile(b, o["bin"], n) for o in obs]
    correct = sum(c is not None and c == o["tile"] for c, o in zip(cued, obs, strict=True))
    trials_seen = sum(1 for s, _ in trials(b) if k0 <= s <= last_obs)
    return {
        "mode": mode,
        "device_id": plan["device_id"],
        "start_bin": k0,
        "start_bin_cursor_residual": first_err,
        "board": f"{n}x{n}",
        "board_selections": len(obs),
        "predicted_selections": len(expected_sel),
        "selections_at_the_same_bins": len(common),
        "same_tile": same_tile,
        "max_cursor_difference": max_cursor_err,
        "agreement": same_tile / max(len(obs), len(expected_sel)),
        "selections_on_the_cued_word": correct,
        "trials_in_window": trials_seen,
        "accuracy_per_selection": correct / len(obs),
        "chance_per_selection": 1 / n**2,
        "selected_words": [o["label"] for o in obs][:40],
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--data", type=Path, default=REPO_ROOT / "data" / "datasets" / "dryad-prr4xgxzq")
    c = sub.add_parser("compare")
    c.add_argument("--plan", type=Path, required=True)
    c.add_argument("--mode", choices=("historical", "brainos"), required=True)
    c.add_argument("--observed", type=Path, required=True)
    c.add_argument("--position-s", type=float, required=True)
    c.add_argument("--n", type=int, default=None, help="board size (default: the plan's)")
    c.add_argument("--out", type=Path, required=True)
    args = ap.parse_args(argv)
    if args.cmd == "prepare":
        plan = prepare(args.data, args.out)
        print(json.dumps({"plan": str(args.out / "plan.json"), "device_id": plan["device_id"]}))
        return 0
    res = compare(
        json.loads(args.plan.read_text()),
        args.mode,
        json.loads(args.observed.read_text()),
        args.position_s,
        args.n,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(res, indent=1))
    print(json.dumps(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
