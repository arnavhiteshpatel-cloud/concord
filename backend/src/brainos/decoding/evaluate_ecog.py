"""Offline movement-vs-rest decoding from human ECoG high gamma (AJILE12, DANDI 000055).

    python -m brainos.decoding.evaluate_ecog                         # needs: fetch ajile12 --all
    python -m brainos.decoding.evaluate_ecog --write docs/ECOG_DECODING.md

Data: the pinned slices of participant sub-07 (``brainos/datasets/ajile12.json``). Day 5 is
the TRAINING session; days 6 and 7 are HELD-OUT sessions. No sample of a held-out session is
used for any fitting, normalization or parameter choice, and a model is refused on its own
training session (``training.session``), here and in the runtime.

Features: exactly the runtime pipeline's ``ecog_high_gamma`` chain (``SignalChain``): 60 Hz
notch + harmonics (the dataset's mains), common average reference over the electrodes the file
marks good, 70-150 Hz band-pass, log10 mean power per 100 ms bin. Causal and chunk-invariant.

Labels (from the dataset's own annotations and pose; fixed before looking at held-out days):
  * move: the bin ends inside a curated reach interval (``intervals/reaches``, contralateral
    wrist movement events identified by the dataset authors);
  * rest: no reach interval within 2 s, both wrists tracked on every pose frame within +-1 s,
    and both wrists' pose speed below 20 px/s (median) and 60 px/s (max) in that window;
  * everything else is unlabelled (not used); bins within 0.5 s of a "data break" epoch and
    the first 2 s of every slice (filter warm-up) are excluded.
The 20/60 px/s thresholds were set by inspecting pose speed on the training day only (wrist
jitter at rest: median ~8-11 px/s).

Classifier: the existing BrainOS LDA (``decoding/lda.py``: causal exponential smoothing
tau 300 ms, z-score with training statistics, Ledoit-Wolf shrinkage, class priors from the
training labels) fitted on the good electrodes; electrodes the training file marks bad get zero
weight (recorded in ``input.excluded_channels``).

Metrics on labelled held-out bins: balanced accuracy (chance 0.5) and accuracy (with the
majority-class rate), per-class recall, confusion matrix, AUC of P(move); controls: the same
model on features circularly shifted against the labels at 20 offsets (time-shift null) for
balanced accuracy and AUC. Event level: fraction of held-out reaches with P(move) > 0.5 in at
least one bin, and P(move) > 0.5 onsets per minute of labelled rest.
"""

from __future__ import annotations

import argparse
import json
import platform
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from brainos.adapters.nwb.ecog import NWBElectricalRecording, NWBElectricalSource
from brainos.adapters.nwb.source import DecoderLeakageError
from brainos.datasets import manifest
from brainos.decoding.lda import SHIFTS, LDAClassifier, evaluate_lda, fit_lda
from brainos.processing import ProcessingSpec, SignalChain

DATASET = "ajile12"
BIN_MS = 100.0
TAU_MS = 300.0
BAND_HZ = (70.0, 150.0)
WARMUP_S = 2.0
REST_MARGIN_S = 2.0
REST_HALF_WINDOW_S = 1.0
REST_MEDIAN_PX_S = 20.0
REST_MAX_PX_S = 60.0
BREAK_MARGIN_S = 0.5
WRISTS = ("L_Wrist", "R_Wrist")
REST, MOVE = 0.0, 1.0
CLASSES = ["rest", "move"]
SPACE = "move_vs_rest"
DETECT_P = 0.5

F64 = NDArray[np.float64]


@dataclass
class SliceData:
    source: NWBElectricalSource
    features: F64  # (bins, channels)
    t_end: F64  # bin end times, seconds since session start
    labels: F64  # -1 unlabelled, 0 rest, 1 move
    valid: NDArray[np.bool_]
    reaches: list[tuple[float, float]]
    stages: list[str]
    info: dict[str, Any] = field(default_factory=dict)

    @property
    def session(self) -> str:
        s = self.source.verification.slice
        return s.session if s and s.session else "unknown"

    @property
    def slice_id(self) -> str:
        s = self.source.verification.slice
        return s.id if s else self.source.path.name


def processing_spec(line_hz: int | None) -> ProcessingSpec:
    return ProcessingSpec(preset="ecog_high_gamma", bin_ms=BIN_MS, line_hz=line_hz)


def compute_features(src: NWBElectricalSource) -> tuple[F64, F64, list[str]]:
    """The runtime pipeline's chain, streamed over the file block by block."""
    rec = src.rec
    labels = rec.channel_labels
    bad = [labels.index(b) for b in rec.bad_channels]
    line = int(src.line_hz) if src.line_hz in (50, 60) else None
    chain = SignalChain(
        processing_spec(line),
        rec.fs,
        rec.channel_count,
        rec.unit,
        car_exclude=bad,
        channel_labels=labels,
    )
    frames = []
    for _, block in rec.iter_samples():
        frames += chain.push(block)
    feats = np.array([f.values for f in frames], dtype=np.float64)
    t_end = np.array([rec.t0_s + f.end_sample / rec.fs for f in frames])
    return feats, t_end, chain.stages


def _speed(rec: NWBElectricalRecording, name: str) -> tuple[F64, NDArray[np.bool_]]:
    pose = rec.pose
    assert pose is not None
    ix, iy = pose.dims.index(f"{name}.x"), pose.dims.index(f"{name}.y")
    xy = pose.values[:, [ix, iy]]
    v = np.r_[np.nan, np.linalg.norm(np.diff(xy, axis=0), axis=1) * pose.rate]
    ok = pose.valid & np.r_[False, pose.valid[:-1]]
    return v, ok


def label_bins(
    rec: NWBElectricalRecording, t_end: F64
) -> tuple[F64, NDArray[np.bool_], dict[str, int]]:
    lab = np.full(t_end.shape, -1.0)
    reaches = [(iv.start_s, iv.stop_s) for iv in rec.intervals if iv.table == "reaches"]
    for a, b in reaches:
        lab[(t_end > a) & (t_end <= b)] = MOVE
    if rec.pose is None:
        raise ValueError(f"{rec.path.name}: no pose; rest cannot be labelled")
    pose = rec.pose
    t_pose = pose.start_s + np.arange(pose.values.shape[0]) / pose.rate
    speeds = [_speed(rec, w) for w in WRISTS]
    near_reach = np.zeros(t_end.shape, dtype=bool)
    for a, b in reaches:
        near_reach |= (t_end > a - REST_MARGIN_S) & (t_end < b + REST_MARGIN_S)
    lo = np.searchsorted(t_pose, t_end - REST_HALF_WINDOW_S, side="left")
    hi = np.searchsorted(t_pose, t_end + REST_HALF_WINDOW_S, side="right")
    min_frames = int(2 * REST_HALF_WINDOW_S * pose.rate * 0.9)
    for i in np.flatnonzero((lab < 0) & ~near_reach):
        a, b = lo[i], hi[i]
        if b - a < min_frames:
            continue
        still = True
        for v, ok in speeds:
            if not ok[a:b].all():
                still = False
                break
            w = v[a:b]
            if np.median(w) >= REST_MEDIAN_PX_S or w.max() >= REST_MAX_PX_S:
                still = False
                break
        if still:
            lab[i] = REST
    excluded = t_end < t_end[0] + WARMUP_S if t_end.size else np.zeros(0, dtype=bool)
    for a, b in rec.data_breaks():
        excluded |= (t_end > a - BREAK_MARGIN_S) & (t_end < b + BREAK_MARGIN_S + BIN_MS / 1000)
    valid = (lab >= 0) & ~excluded
    info = {
        "bins": int(t_end.size),
        "move_bins": int(np.sum(valid & (lab == MOVE))),
        "rest_bins": int(np.sum(valid & (lab == REST))),
        "unlabelled_bins": int(np.sum(lab < 0)),
        "excluded_bins": int(np.sum(excluded)),
        "reaches": len(reaches),
    }
    return lab, valid, info


def load_slice(path: Path) -> SliceData:
    src = NWBElectricalSource(path)
    feats, t_end, stages = compute_features(src)
    lab, valid, info = label_bins(src.rec, t_end)
    t0, t1 = src.rec.t0_s + WARMUP_S, src.rec.t0_s + src.rec.duration_s
    reaches = [
        (iv.start_s, iv.stop_s)
        for iv in src.rec.intervals
        if iv.table == "reaches" and iv.start_s >= t0 and iv.stop_s <= t1
    ]
    return SliceData(src, feats, t_end, lab, valid, reaches, stages, info)


def _expand(model: LDAClassifier, good: NDArray[np.bool_]) -> LDAClassifier:
    """Embed a model fitted on the good channels into the full channel set (zero weight)."""
    n = good.size

    def put(vals: list[float], fill: float) -> list[float]:
        out = np.full(n, fill)
        out[good] = vals
        return [float(v) for v in out]

    model.x_mean = put(model.x_mean, 0.0)
    model.x_std = put(model.x_std, 1.0)
    model.coef = [put(row, 0.0) for row in model.coef]
    return model


def train(slices: list[SliceData], *, tau_ms: float = TAU_MS) -> LDAClassifier:
    if not slices:
        raise ValueError("no training slices")
    sessions = {s.session for s in slices}
    if len(sessions) != 1:
        raise ValueError(f"training slices span sessions {sorted(sessions)}; train per session")
    src0 = slices[0].source
    labels = src0.rec.channel_labels
    if any(s.source.rec.channel_labels != labels for s in slices):
        raise ValueError("training slices have different electrode tables")
    bad = sorted({b for s in slices for b in s.source.rec.bad_channels})
    good = np.array([lbl not in bad for lbl in labels])
    X = np.concatenate([s.features for s in slices])
    Y = np.concatenate([s.labels for s in slices])
    V = np.concatenate([s.valid for s in slices])
    m = src0.verification.manifest
    model = fit_lda(
        X[:, good],
        Y,
        V,
        class_values=[REST, MOVE],
        class_names=CLASSES,
        bin_ms=BIN_MS,
        tau_ms=tau_ms,
        space=SPACE,
        training={
            "dataset": f"DANDI:{m.dandiset}" if m else None,
            "dandiset_version": m.version if m else None,
            "participant": src0.rec.subject_id,
            "session": slices[0].session,
            "sessions": [slices[0].session],
            "slices": [s.slice_id for s in slices],
            "files": [s.source.path.name for s in slices],
            "end_s": max(s.source.rec.t0_s + s.source.rec.duration_s for s in slices),
            "data_sha256": [
                s.source.verification.slice.data_sha256 if s.source.verification.slice else None
                for s in slices
            ],
            "label_definition": {
                "move": "bin end inside a curated reach interval (intervals/reaches)",
                "rest": (
                    f"no reach within {REST_MARGIN_S:g} s; both wrists tracked and pose speed "
                    f"median < {REST_MEDIAN_PX_S:g} px/s and max < {REST_MAX_PX_S:g} px/s within "
                    f"+-{REST_HALF_WINDOW_S:g} s"
                ),
                "excluded": f"first {WARMUP_S:g} s of each slice; +-{BREAK_MARGIN_S:g} s around "
                "data-break epochs",
            },
        },
        input_spec={
            "event_type": "features.vector",
            "feature": "log_band_power",
            "unit": "log10(uV^2)",
            "bin_ms": BIN_MS,
            "band_hz": list(BAND_HZ),
            "channel_count": len(labels),
            "channel_labels": labels,
            "excluded_channels": bad,
            "modality": src0.modality.value if src0.modality else None,
            "preprocessing": {
                "preset": "ecog_high_gamma",
                "line_hz": src0.line_hz,
                "car": "common average over electrodes the source marks good",
                "stages": slices[0].stages,
            },
        },
        source={
            "identity": _identity(src0),
            "description": f"AJILE12 participant {src0.rec.subject_id} (DANDI 000055), ECoG",
        },
    )
    model = _expand(model, good)
    model.method = (
        "LDA move-vs-rest on ECoG high-gamma log power: causal exponential smoothing "
        f"(tau {tau_ms:g} ms), z-score (train stats), Ledoit-Wolf shrinkage, softmax posteriors; "
        "electrodes marked bad in the training file have zero weight"
    )
    return model


def _identity(src: NWBElectricalSource) -> str | None:
    from brainos.decoding.model import source_identity

    return source_identity(src.origin)


def _auc(score: F64, y: NDArray[np.bool_]) -> float:
    from scipy.stats import rankdata

    pos, neg = int(y.sum()), int((~y).sum())
    if pos == 0 or neg == 0:
        return float("nan")
    r = rankdata(score)
    return float((r[y].sum() - pos * (pos + 1) / 2) / (pos * neg))


def check_held_out(
    model: LDAClassifier, slices: list[SliceData], *, later_same_session: bool = False
) -> None:
    """Refuse to score a model on its training data.

    Default: every scored slice must come from a session the model was not trained on.
    ``later_same_session`` (context analysis only): a slice of the training session is allowed
    if it is not a training slice and starts after every training slice ended.
    """
    trained = {str(model.training.get("session"))} | set(model.training.get("sessions") or [])
    train_ids = set(model.training.get("slices") or [])
    train_end = float(model.training.get("end_s") or 0.0)
    for s in slices:
        if s.slice_id in train_ids:
            raise DecoderLeakageError(f"{s.slice_id} is a training slice of {model.model_id}")
        if s.session in trained and not (later_same_session and s.source.rec.t0_s >= train_end > 0):
            raise DecoderLeakageError(
                f"{s.slice_id} is from training session {s.session}; refusing to score on it"
            )


def evaluate(
    model: LDAClassifier, slices: list[SliceData], *, later_same_session: bool = False
) -> dict[str, Any]:
    """Score held-out slices (concatenated; each slice's warm-up bins are already invalid)."""
    check_held_out(model, slices, later_same_session=later_same_session)
    X = np.concatenate([s.features for s in slices])
    Y = np.concatenate([s.labels for s in slices])
    V = np.concatenate([s.valid for s in slices])
    res = evaluate_lda(model, X, Y, V, skip_first=len(model.kernel))
    p = model.predict_proba(X)[:, CLASSES.index("move")]
    rows = V & (Y >= 0)
    rows[: len(model.kernel)] = False
    y = Y[rows] == MOVE
    res["auc"] = _auc(p[rows], y)
    null = []
    n = X.shape[0]
    for k in range(1, SHIFTS + 1):
        ps = model.predict_proba(np.roll(X, (k * n) // (SHIFTS + 1), axis=0))[:, 1]
        null.append(_auc(ps[rows], y))
    res["control_time_shift_auc"] = float(np.mean(null))
    res["control_time_shift_max_auc"] = float(np.max(null))
    res["auc_beats_all_shifts"] = bool(res["auc"] > max(null))
    # event level: per-slice, from the slice's own posterior sequence (causal from its start)
    detected = total = onsets = 0
    rest_bins = above_all = all_bins = 0
    for s in slices:
        ps = model.predict_proba(s.features)[:, 1]
        live = s.t_end >= s.t_end[0] + WARMUP_S  # every bin after warm-up, labelled or not
        above_all += int(np.sum(ps[live] > DETECT_P))
        all_bins += int(live.sum())
        for a, b in s.reaches:
            total += 1
            detected += bool(np.any(ps[(s.t_end > a) & (s.t_end <= b)] > DETECT_P))
        rest = s.valid & (s.labels == REST)
        above = ps > DETECT_P
        onset = above & ~np.r_[False, above[:-1]]
        onsets += int(np.sum(onset & rest))
        rest_bins += int(rest.sum())
    res["reaches_scored"] = total
    res["reaches_detected"] = detected
    res["reach_detection_rate"] = detected / total if total else float("nan")
    rest_min = rest_bins * BIN_MS / 60000
    res["rest_minutes"] = rest_min
    res["false_onsets_per_rest_minute"] = onsets / rest_min if rest_min else float("nan")
    # how the detector behaves on ALL data, including the ~70 % of unlabelled bins (other
    # movements, talking, eating...): fraction of time with P(move) > 0.5
    res["fraction_all_bins_p_move_above"] = above_all / all_bins if all_bins else float("nan")
    res["slices"] = [s.slice_id for s in slices]
    res["sessions"] = sorted({s.session for s in slices})
    res["data_sha256"] = [
        s.source.verification.slice.data_sha256 if s.source.verification.slice else None
        for s in slices
    ]
    return res


def discover(data_dir: Path) -> dict[str, list[Path]]:
    """Present, verified extracts of the pinned slices, by role."""
    m = manifest(DATASET)
    out: dict[str, list[Path]] = {"train": [], "test": []}
    for s in m.slices:
        p = data_dir / s.filename
        if p.exists():
            out[s.role].append(p)
    return out


def run(data_dir: Path, models_dir: Path | None) -> dict[str, Any]:
    found = discover(data_dir)
    if not found["train"] or not found["test"]:
        raise SystemExit(
            f"pinned AJILE12 slices missing in {data_dir}; run: "
            "python -m brainos.datasets.fetch ajile12 --all"
        )
    loaded = {p: load_slice(p) for p in found["train"] + found["test"]}
    for p, s in loaded.items():
        if not s.source.verification.verified:
            raise SystemExit(f"{p.name}: does not match the pinned slice (unverified)")
    train_slices = [loaded[p] for p in found["train"]]
    test_slices = [loaded[p] for p in found["test"]]
    model = train(train_slices)
    by_session: dict[str, list[SliceData]] = defaultdict(list)
    for s in test_slices:
        by_session[s.session].append(s)
    held_out = []
    for sess, group in sorted(by_session.items()):
        res = evaluate(model, group)
        held_out.append({"train_session": model.training["session"], "test_session": sess, **res})
        model.evaluations.append(
            {
                "split": f"held-out session {sess} (trained on session {model.training['session']})",
                **res,
            }
        )
    within = None
    if len(train_slices) >= 2:  # context: same day, chronological, the latest slice held out
        ordered = sorted(train_slices, key=lambda s: s.source.rec.t0_s)
        m_within = train(ordered[:-1])
        within = {
            "train_slices": [s.slice_id for s in ordered[:-1]],
            **evaluate(m_within, ordered[-1:], later_same_session=True),
        }
    saved = None
    if models_dir is not None:
        saved = str(model.save(models_dir / f"{model.model_id}.json"))
    return {
        "model_id": model.model_id,
        "model_path": saved,
        "train": {
            "session": model.training["session"],
            "slices": [s.slice_id for s in train_slices],
            "class_counts": dict(zip(CLASSES, model.training["class_counts"], strict=True)),
            "shrinkage": model.shrinkage,
            "excluded_channels": model.input.get("excluded_channels"),
            "per_slice": {s.slice_id: s.info for s in train_slices},
            "effect_sizes": effect_sizes(train_slices),
        },
        "test_per_slice": {s.slice_id: s.info for s in test_slices},
        "held_out_sessions": held_out,
        "within_day_context": within,
        "stages": train_slices[0].stages,
        "params": {
            "bin_ms": BIN_MS,
            "tau_ms": TAU_MS,
            "band_hz": list(BAND_HZ),
            "rest_median_px_s": REST_MEDIAN_PX_S,
            "rest_max_px_s": REST_MAX_PX_S,
            "rest_margin_s": REST_MARGIN_S,
            "warmup_s": WARMUP_S,
            "break_margin_s": BREAK_MARGIN_S,
            "detect_p": DETECT_P,
        },
    }


def _row(r: dict[str, Any]) -> str:
    return (
        f"| {', '.join(r['sessions'])} | {len(r['slices'])} | {r['samples']} "
        f"({r['support'][1]} move / {r['support'][0]} rest) | **{r['balanced_accuracy']:.3f}** "
        f"| {r['control_time_shift_balanced_accuracy']:.3f} / {r['control_time_shift_max_balanced_accuracy']:.3f} "
        f"| **{r['auc']:.3f}** | {r['control_time_shift_auc']:.3f} / {r['control_time_shift_max_auc']:.3f} "
        f"| {r['per_class_recall'][0]:.2f} / {r['per_class_recall'][1]:.2f} "
        f"| {r['accuracy']:.3f} ({r['chance_majority_accuracy']:.3f}) "
        f"| {r['reaches_detected']}/{r['reaches_scored']} | {r['false_onsets_per_rest_minute']:.2f} "
        f"| {100 * r['fraction_all_bins_p_move_above']:.1f} % |"
    )


def effect_sizes(slices: list[SliceData]) -> dict[str, Any]:
    """Training-data sanity check: where on the grid does high gamma differ (move - rest)?"""
    X = np.concatenate([s.features for s in slices])
    Y = np.concatenate([s.labels for s in slices])
    V = np.concatenate([s.valid for s in slices])
    mv, rs = X[V & (Y == MOVE)], X[V & (Y == REST)]
    d = (mv.mean(0) - rs.mean(0)) / np.sqrt(0.5 * (mv.var(0) + rs.var(0)) + 1e-12)
    el = slices[0].source.rec.electrodes
    top = [
        {"label": el[i].label, "d": float(d[i]), "xyz": [el[i].x, el[i].y, el[i].z]}
        for i in np.argsort(d)[::-1][:5]
    ]
    good = np.array([not e.bad for e in el])
    z = np.array([e.z if e.z is not None else np.nan for e in el])
    ok = good & np.isfinite(z)
    return {
        "median_d": float(np.median(d[good])),
        "n_d_above_1": int(np.sum(d[good] > 1)),
        "n_d_below_0": int(np.sum(d[good] < 0)),
        "n_good": int(good.sum()),
        "top": top,
        "corr_d_z": float(np.corrcoef(d[ok], z[ok])[0, 1]) if ok.sum() > 2 else float("nan"),
    }


def to_markdown(res: dict[str, Any], seconds: float) -> str:
    tr = res["train"]
    head = (
        "| test session | slices | scored bins | balanced acc. | shift null mean / max "
        "| AUC P(move) | AUC shift null mean / max | recall rest / move | accuracy (majority rate) "
        "| reaches with P(move) > 0.5 | P(move) > 0.5 onsets per rest minute "
        "| all bins with P(move) > 0.5 |"
    )
    sep = "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    lines = [
        "# Offline ECoG decoding results — AJILE12 (DANDI 000055), participant sub-07",
        "",
        "> Generated by `python -m brainos.decoding.evaluate_ecog` on "
        f"{time.strftime('%Y-%m-%d')} ({platform.machine()}, Python {sys.version.split()[0]}, "
        f"{seconds:.1f} s). Do not edit by hand; re-run to regenerate. Method and caveats: "
        "docs/ECOG.md.",
        "",
        "**What this is:** offline classification of *movement vs rest* of the arm, from high-gamma "
        "power of a subdural ECoG grid, in recordings made during clinical epilepsy monitoring "
        "(naturalistic, unscripted behavior). Trained on one day, scored on other days. **What "
        "this is not:** closed-loop control, a BCI user study, or intention decoding — the "
        "participant was not trying to control anything.",
        "",
        "Features (the runtime pipeline's chain): " + "; ".join(res["stages"]) + ".",
        "",
        f"Classifier `{res['model_id']}`: LDA, tau {res['params']['tau_ms']:g} ms, Ledoit-Wolf "
        f"shrinkage {tr['shrinkage']:.3f}, trained on session {tr['session']} slices "
        f"{', '.join(tr['slices'])} ({tr['class_counts']['move']} move / {tr['class_counts']['rest']} "
        f"rest labelled bins); electrodes excluded (marked bad in the training file): "
        f"{', '.join(tr['excluded_channels'] or []) or 'none'}.",
        "",
        "## Held-out sessions (train day 5 → test other days)",
        "",
        head,
        sep,
    ]
    for r in res["held_out_sessions"]:
        lines.append(_row(r))
    w = res["within_day_context"]
    if w:
        lines += [
            "",
            "## Context: same day, chronological (train on the earlier day-5 slices, score the "
            "latest one)",
            "",
            "Not a held-out session; shown only to separate day-to-day drift from the "
            "classifier itself.",
            "",
            head,
            sep,
            _row(w),
        ]
    es = tr["effect_sizes"]
    lines += [
        "",
        "## Sanity check: where the effect is (training day only)",
        "",
        f"Effect size d' of high-gamma log power (move minus rest, pooled SD) per good electrode: "
        f"median {es['median_d']:.2f}; {es['n_d_above_1']} of {es['n_good']} electrodes above 1, "
        f"{es['n_d_below_0']} below 0; correlation of d' with the electrode z coordinate "
        f"{es['corr_d_z']:.2f}. Largest: "
        + ", ".join(
            f"{t['label']} {t['d']:.2f} (x {t['xyz'][0]:.0f}, y {t['xyz'][1]:.0f}, z {t['xyz'][2]:.0f})"
            for t in es["top"]
        )
        + ". A focal effect (not uniform across the grid) argues against a grid-wide artifact; "
        "the file does not state the coordinate space, so no anatomical claim is made.",
        "",
        "## Labelled bins per slice",
        "",
        "| slice | role | bins | move | rest | unlabelled | excluded (warm-up / data breaks) | reaches |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for role, per in (("train", tr["per_slice"]), ("test", res["test_per_slice"])):
        for sid, i in per.items():
            lines.append(
                f"| {sid} | {role} | {i['bins']} | {i['move_bins']} | {i['rest_bins']} "
                f"| {i['unlabelled_bins']} | {i['excluded_bins']} | {i['reaches']} |"
            )
    lines += [
        "",
        "Controls: *chance* balanced accuracy is 0.5 and chance AUC is 0.5. The *time-shift "
        f"null* runs the same model on features circularly shifted against the labels at "
        f"{SHIFTS} offsets (keeps the signal's statistics, destroys alignment). Accuracy is "
        "dominated by the majority class (rest) and is shown only with the majority rate.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from brainos.server.settings import REPO_ROOT

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--data", type=Path, default=REPO_ROOT / "data" / "datasets" / "dandi-000055")
    ap.add_argument("--models-dir", type=Path, default=REPO_ROOT / "data" / "models")
    ap.add_argument("--write", type=Path, default=None)
    ap.add_argument("--json", type=Path, default=REPO_ROOT / "reports" / "ecog_decoding.json")
    args = ap.parse_args(argv)
    t0 = time.perf_counter()
    res = run(args.data, args.models_dir)
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
