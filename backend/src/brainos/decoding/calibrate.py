"""Calibrate a decoder from recorded BrainOS sessions (neural features + behavioral targets).

Input: one or more BrainOS recordings (``data/recordings/*.brainos.jsonl``) of a *live*
session that contains neural features (``features.binned`` or ``features.vector``, from the
device or from the BrainOS pipeline) and behavioral targets (``behavior.sample``).

Alignment (on the device clock): each feature bin is labelled with the behavior sample
nearest to the bin's end, if one lies within half a bin of it (sources that stamp counts and
behavior with the same clock tick, as FALCON-over-LSL does, may still differ by microseconds
after clock correction). Bins without such a label, or with an invalid label, are excluded
from fitting and scoring. Labels are never interpolated; features are never shifted, so the
decoder itself stays causal.

Split: chronological. Training = the first ``train_fraction`` of labelled bins (moved to the
next trial boundary when trial markers exist); a gap of ``gap_bins`` follows; evaluation =
the rest. Only training data is used for fitting, z-scoring and alpha selection.

    python -m brainos.decoding.calibrate data/recordings/<name>.brainos.jsonl [...]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from brainos.datasets import session_of
from brainos.decoding.lda import DEFAULT_TAU_MS, LDAClassifier, evaluate_lda, fit_lda
from brainos.decoding.model import source_identity
from brainos.decoding.ridge import RidgeDecoder, evaluate, fit

FEATURE_TYPES = ("features.binned", "features.vector")


class CalibrationError(ValueError):
    pass


@dataclass
class SessionData:
    path: Path
    sha256: str
    device_id: str
    origin: str | None
    replayed: bool
    synthetic: bool
    feature_event: str
    feature: str
    bin_ms: float
    channel_labels: list[str] | None
    dims: list[str]
    unit: str
    quantity: str
    features: NDArray[np.float64]  # (bins, channels)
    targets: NDArray[np.float64]  # (bins, dims)
    valid: NDArray[np.bool_]  # (bins,)
    bin_end_ns: NDArray[np.int64]
    trial_starts: list[int]  # bin indices where a marker/annotation occurs
    sources: set[str]
    # class names declared by the source for a class-label behavior stream (capability param
    # ``class_names`` of ``behavior``), if any
    declared_classes: list[str] | None = None
    # M5: the recorded device's declared modality (contract ``Modality`` value), if any
    modality: str | None = None


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while b := fh.read(1 << 20):
            h.update(b)
    return h.hexdigest()


def load_session(path: Path, *, feature_source: str | None = None) -> SessionData:
    """Read one recording and align features with behavioral targets."""
    header: dict[str, Any] | None = None
    feats: list[tuple[int, list[float], dict[str, Any]]] = []
    beh: list[tuple[int, list[float], bool, dict[str, Any]]] = []
    marks: list[int] = []
    with path.open(encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if not line.strip():
                continue
            obj = json.loads(line)
            if i == 0:
                header = obj
                continue
            et = obj.get("event_type")
            ts = obj.get("device_timestamp_ns")
            if ts is None:
                continue
            if et in FEATURE_TYPES:
                prov = obj["provenance"]
                if feature_source and prov.get("adapter", "").split("@")[0] != feature_source:
                    continue
                p = obj["payload"]
                vals = p["counts"] if et == "features.binned" else p["values"]
                feats.append((int(ts), [float(v) for v in vals], {"et": et, "p": p, "prov": prov}))
            elif et == "behavior.sample":
                p = obj["payload"]
                beh.append((int(ts), [float(v) for v in p["values"]], bool(p["valid"]), p))
            elif et == "recording.annotation":
                marks.append(int(ts))
    if header is None:
        raise CalibrationError(f"{path.name}: empty recording")
    if not feats:
        raise CalibrationError(
            f"{path.name}: no neural features (features.binned / features.vector)"
        )
    if not beh:
        raise CalibrationError(f"{path.name}: no behavioral targets (behavior.sample)")
    kinds = {(m["et"], m["p"]["feature"], float(m["p"]["bin_ms"]), len(v)) for _, v, m in feats}
    if len(kinds) > 1:
        raise CalibrationError(
            f"{path.name}: mixed feature streams {sorted(kinds)}; "
            "pass --feature-source to choose one"
        )
    et, feature, bin_ms, n_ch = next(iter(kinds))
    feats.sort(key=lambda r: r[0])
    beh.sort(key=lambda r: r[0])
    b_ts = np.array([b[0] for b in beh], dtype=np.int64)
    dims = list(beh[0][3]["dims"])
    if any(list(b[3]["dims"]) != dims for b in beh):
        raise CalibrationError(f"{path.name}: behavior dimensions change within the session")
    bin_ns = round(bin_ms * 1e6)
    X = np.array([f[1] for f in feats], dtype=np.float64)
    ends = np.array([f[0] for f in feats], dtype=np.int64)
    Y = np.zeros((len(feats), len(dims)))
    valid = np.zeros(len(feats), dtype=bool)
    # nearest behavior sample to the bin end, within half a bin
    right = np.searchsorted(b_ts, ends, side="left")
    for i, r in enumerate(right):
        cands = [j for j in (r - 1, r) if 0 <= j < len(b_ts)]
        j = min(cands, key=lambda k: abs(int(ends[i]) - int(b_ts[k])))
        if abs(int(ends[i]) - int(b_ts[j])) <= bin_ns // 2:
            Y[i] = beh[j][1]
            valid[i] = beh[j][2] and bool(np.all(np.isfinite(beh[j][1])))
    trial_starts = sorted({int(k) for k in np.searchsorted(ends, np.array(marks, dtype=np.int64))})
    prov0 = feats[0][2]["prov"]
    labels = header.get("device", {}).get("capabilities", [])
    ch_labels = None
    declared_classes = None
    for cap in labels:
        lbl = cap.get("params", {}).get("channel_labels")
        if isinstance(lbl, list) and len(lbl) == n_ch:
            ch_labels = [str(x) for x in lbl]
        names = cap.get("params", {}).get("class_names")
        if cap.get("capability") == "behavior" and isinstance(names, list) and names:
            declared_classes = [str(x) for x in names]
    bunit = str(beh[0][3]["unit"])
    modality = header.get("device", {}).get("modality")
    return SessionData(
        modality=str(modality) if modality else None,
        path=path,
        sha256=_sha(path),
        device_id=str(header.get("device", {}).get("device_id", "")),
        origin=prov0.get("origin"),
        replayed=bool(prov0.get("replayed")),
        synthetic=bool(prov0.get("synthetic")),
        feature_event=et,
        feature=feature,
        bin_ms=bin_ms,
        channel_labels=ch_labels,
        dims=dims,
        unit=bunit,
        quantity=str(beh[0][3]["quantity"]),
        features=X,
        targets=Y,
        valid=valid,
        bin_end_ns=ends,
        trial_starts=trial_starts,
        sources={str(f[2]["prov"].get("adapter")) for f in feats},
        declared_classes=declared_classes,
    )


def chronological_split(n: int, frac: float, trial_starts: list[int]) -> int:
    target = int(frac * n)
    after = [t for t in trial_starts if t >= target]
    return after[0] if after and after[0] < n - 50 else target


def _load_sessions(
    paths: list[Path], feature_source: str | None
) -> tuple[
    list[SessionData], NDArray[np.float64], NDArray[np.float64], NDArray[np.bool_], list[int]
]:
    sessions = [load_session(p, feature_source=feature_source) for p in paths]
    s0 = sessions[0]
    for s in sessions[1:]:
        if (s.feature_event, s.feature, s.bin_ms, s.features.shape[1], s.dims) != (
            s0.feature_event,
            s0.feature,
            s0.bin_ms,
            s0.features.shape[1],
            s0.dims,
        ):
            raise CalibrationError("recordings have different feature or behavior layouts")
        if source_identity(s.origin) != source_identity(s0.origin):
            raise CalibrationError("recordings come from different sources; calibrate per source")
    X = np.concatenate([s.features for s in sessions])
    Y = np.concatenate([s.targets for s in sessions])
    V = np.concatenate([s.valid for s in sessions])
    starts: list[int] = []
    off = 0
    for s in sessions:
        starts += [t + off for t in s.trial_starts]
        off += len(s.features)
    return sessions, X, Y, V, starts


def _training_info(sessions: list[SessionData], split: int) -> dict[str, Any]:
    s0 = sessions[0]
    return {
        "recordings": [s.path.name for s in sessions],
        "recording_sha256": [s.sha256 for s in sessions],
        "recording": sessions[0].path.name,
        "bins": [0, int(split)],
        "session": session_of(s0.origin or ""),
        "sessions": sorted({x for s in sessions if (x := session_of(s.origin or ""))}),
        "prerecorded_source": any(s.replayed for s in sessions),
        "synthetic_source": any(s.synthetic for s in sessions),
        "feature_sources": sorted(set().union(*[s.sources for s in sessions])),
    }


def _input_spec(s0: SessionData, channels: int) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "event_type": s0.feature_event,
        "feature": s0.feature,
        "bin_ms": s0.bin_ms,
        "channel_count": channels,
        "channel_labels": s0.channel_labels,
    }
    if s0.modality:  # M5: declared by the recorded device; checked when the model is loaded
        spec["modality"] = s0.modality
    return spec


def calibrate(
    paths: list[Path],
    *,
    train_fraction: float = 0.8,
    gap_bins: int = 12,
    models_dir: Path | None = None,
    feature_source: str | None = None,
) -> tuple[RidgeDecoder, dict[str, Any]]:
    sessions, X, Y, V, starts = _load_sessions(paths, feature_source)
    s0 = sessions[0]
    n = len(X)
    if V.sum() < 200:
        raise CalibrationError(
            f"only {int(V.sum())} labelled bins; record a longer calibration session"
        )
    split = chronological_split(n, train_fraction, starts)
    test_start = min(n, split + gap_bins)
    space = f"{s0.quantity}_{'_'.join(s0.dims)}"[:60]
    model = fit(
        X[:split],
        Y[:split],
        V[:split],
        dims=s0.dims,
        unit=s0.unit,
        bin_ms=s0.bin_ms,
        space=space,
        training=_training_info(sessions, split),
        input_spec=_input_spec(s0, int(X.shape[1])),
        source={
            "identity": source_identity(s0.origin),
            "description": f"device {s0.device_id}; origin {s0.origin}",
        },
    )
    if test_start >= n - 20:
        raise CalibrationError("not enough data after the split to evaluate; record longer")
    res = evaluate(
        model, X[test_start:], Y[test_start:], V[test_start:], skip_first=len(model.kernel)
    )
    model.evaluations.append(
        {
            "file": sessions[-1].path.name,
            "split": "chronological tail",
            "bins": [int(test_start), int(n)],
            **res,
        }
    )
    if models_dir is not None:
        model.save(models_dir / f"{model.model_id}.json")
    report = {
        "model_id": model.model_id,
        "recordings": [s.path.name for s in sessions],
        "source_identity": model.source.get("identity"),
        "prerecorded_source": model.training["prerecorded_source"],
        "synthetic_source": model.training["synthetic_source"],
        "bins_total": n,
        "labelled_bins": int(V.sum()),
        "train_bins": int(split),
        "gap_bins": gap_bins,
        "test_bins": int(n - test_start),
        "alpha": model.alpha,
        **res,
    }
    return model, report


MAX_CLASSES = 16
CLASS_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,31}$")


def class_layout(
    labels: NDArray[np.float64],
    valid: NDArray[np.bool_],
    class_names: list[str] | None,
    declared: list[str] | None,
) -> tuple[list[float], list[str]]:
    """Class values present in the (valid) labels and a name for each.

    Labels must be small non-negative integers (a class code per bin, e.g. a cue stream's
    ``cue_class`` 0/1/2). ``class_names[i]`` names label value ``i``; without names the
    source's declared names are used, else ``class_<i>``.
    """
    vals = np.unique(labels[valid])
    if len(vals) < 2:
        raise CalibrationError(f"the label stream has {len(vals)} distinct value(s); need >= 2")
    if len(vals) > MAX_CLASSES or not np.all((vals >= 0) & (vals == np.round(vals))):
        raise CalibrationError(
            "the label stream is not a class label (expected small non-negative integers, "
            f"got {len(vals)} distinct values)"
        )
    names = class_names or declared
    out: list[str] = []
    for v in vals:
        i = int(v)
        if names is not None:
            if i >= len(names):
                raise CalibrationError(f"no class name for label value {i} (names: {names})")
            out.append(str(names[i]))
        else:
            out.append(f"class_{i}")
    bad = [n for n in out if not CLASS_NAME.match(n)]
    if bad or len(set(out)) != len(out):
        raise CalibrationError(
            f"class names must be unique, 1-32 characters [A-Za-z0-9_.-] (got {out})"
        )
    return [float(v) for v in vals], out


def calibrate_classifier(
    paths: list[Path],
    *,
    label_dim: str | None = None,
    class_names: list[str] | None = None,
    train_fraction: float = 0.8,
    gap_bins: int = 12,
    tau_ms: float = DEFAULT_TAU_MS,
    models_dir: Path | None = None,
    feature_source: str | None = None,
) -> tuple[LDAClassifier, dict[str, Any]]:
    """Fit an LDA classifier on recordings whose behavior stream carries a class label.

    Same alignment and chronological split (+ gap) as :func:`calibrate`; only training bins
    are used for smoothing statistics, z-scoring, class means, covariance and shrinkage.
    """
    sessions, X, Y, V, starts = _load_sessions(paths, feature_source)
    s0 = sessions[0]
    if label_dim is None:
        if len(s0.dims) != 1:
            raise CalibrationError(
                f"behavior has dimensions {s0.dims}; choose the class label with label_dim"
            )
        label_dim = s0.dims[0]
    if label_dim not in s0.dims:
        raise CalibrationError(f"behavior has no dimension {label_dim!r} ({s0.dims})")
    labels = Y[:, s0.dims.index(label_dim)]
    valid = V & np.isfinite(labels)
    n = len(X)
    if valid.sum() < 100:
        raise CalibrationError(
            f"only {int(valid.sum())} labelled bins; record a longer calibration session"
        )
    values, names = class_layout(labels, valid, class_names, s0.declared_classes)
    split = chronological_split(n, train_fraction, starts)
    test_start = min(n, split + gap_bins)
    if test_start >= n - 20:
        raise CalibrationError("not enough data after the split to evaluate; record longer")
    try:
        model = fit_lda(
            X[:split],
            labels[:split],
            valid[:split],
            class_values=values,
            class_names=names,
            bin_ms=s0.bin_ms,
            tau_ms=tau_ms,
            space=f"classes_{label_dim}"[:60],
            training={**_training_info(sessions, split), "label_dim": label_dim},
            input_spec=_input_spec(s0, int(X.shape[1])),
            source={
                "identity": source_identity(s0.origin),
                "description": f"device {s0.device_id}; origin {s0.origin}",
            },
        )
    except ValueError as exc:
        raise CalibrationError(str(exc)) from None
    res = evaluate_lda(
        model, X[test_start:], labels[test_start:], valid[test_start:], skip_first=len(model.kernel)
    )
    model.evaluations.append(
        {
            "file": sessions[-1].path.name,
            "split": "chronological tail",
            "bins": [int(test_start), int(n)],
            **res,
        }
    )
    if models_dir is not None:
        model.save(models_dir / f"{model.model_id}.json")
    report = {
        "kind": "classifier",
        "model_id": model.model_id,
        "recordings": [s.path.name for s in sessions],
        "source_identity": model.source.get("identity"),
        "prerecorded_source": model.training["prerecorded_source"],
        "synthetic_source": model.training["synthetic_source"],
        "bins_total": n,
        "labelled_bins": int(valid.sum()),
        "train_bins": int(split),
        "gap_bins": gap_bins,
        "test_bins": int(n - test_start),
        "label_dim": label_dim,
        "train_class_counts": dict(zip(names, model.training["class_counts"], strict=True)),
        "tau_ms": tau_ms,
        "shrinkage": model.shrinkage,
        **res,
    }
    return model, report


def classifier_report_markdown(report: dict[str, Any]) -> str:
    classes: list[str] = report["classes"]
    head = "| true \\ predicted | " + " | ".join(classes) + " |"
    rows = [head, "| --- " * (len(classes) + 1) + "|"]
    for name, row in zip(classes, report["confusion"], strict=True):
        rows.append(f"| {name} | " + " | ".join(str(v) for v in row) + " |")
    lines = [
        f"# Calibration report — `{report['model_id']}` (classifier)",
        "",
        f"- Recordings: {', '.join(report['recordings'])}",
        f"- Source: `{report['source_identity']}`"
        + (" — **prerecorded data streamed live**" if report["prerecorded_source"] else "")
        + (" — **synthetic data**" if report["synthetic_source"] else ""),
        f"- Bins: {report['bins_total']} ({report['labelled_bins']} labelled); "
        f"train {report['train_bins']}, gap {report['gap_bins']}, held-out {report['test_bins']}"
        f" ({report['samples']} scored)",
        f"- Held-out balanced accuracy: **{report['balanced_accuracy']:.3f}** "
        f"(chance {report['chance_balanced_accuracy']:.3f}) · accuracy {report['accuracy']:.3f} "
        f"(majority-class rate {report['chance_majority_accuracy']:.3f})",
        "- Per-class accuracy (recall): "
        + ", ".join(f"{k} {v:.2f}" for k, v in report["per_class_accuracy"].items()),
        "- Time-shift control: balanced accuracy "
        f"{report['control_time_shift_balanced_accuracy']:.3f} mean, "
        f"{report['control_time_shift_max_balanced_accuracy']:.3f} max over "
        f"{report['control_time_shift_n']} shifts",
        f"- Smoothing tau {report['tau_ms']:g} ms · Ledoit-Wolf shrinkage "
        f"{report['shrinkage']:.3f}",
        "",
        "Confusion matrix (held-out bins):",
        "",
        *rows,
        "",
        "Offline held-out accuracy on a recorded session does not establish closed-loop "
        "control performance.",
        "",
    ]
    return "\n".join(lines)


def report_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# Calibration report — `{report['model_id']}`",
        "",
        f"- Recordings: {', '.join(report['recordings'])}",
        f"- Source: `{report['source_identity']}`"
        + (" — **prerecorded data streamed live**" if report["prerecorded_source"] else "")
        + (" — **synthetic data**" if report["synthetic_source"] else ""),
        f"- Bins: {report['bins_total']} ({report['labelled_bins']} labelled); "
        f"train {report['train_bins']}, gap {report['gap_bins']}, held-out {report['test_bins']}",
        f"- Held-out R² (variance-weighted): **{report['r2']:.3f}** · mean-predictor control "
        f"{report['control_mean_predictor_r2']:.3f} · alpha {report['alpha']:g}",
        "- Per-dimension R²: " + ", ".join(f"{k} {v:.2f}" for k, v in report["r2_per_dim"].items()),
        "",
        "Offline held-out R² on a recorded session does not establish closed-loop "
        "control performance.",
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from brainos.server.settings import REPO_ROOT

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("recordings", nargs="+", type=Path)
    ap.add_argument("--train-fraction", type=float, default=0.8)
    ap.add_argument("--gap-bins", type=int, default=12)
    ap.add_argument("--feature-source", default=None, help="adapter name, e.g. brainos.pipeline")
    ap.add_argument("--models-dir", type=Path, default=REPO_ROOT / "data" / "models")
    ap.add_argument(
        "--classes",
        action="store_true",
        help="fit an LDA classifier on a class-label behavior stream (discrete decoding)",
    )
    ap.add_argument("--label-dim", default=None, help="behavior dimension holding the class")
    ap.add_argument("--class-names", default=None, help="comma-separated, index = label value")
    args = ap.parse_args(argv)
    try:
        if args.classes:
            clf, report = calibrate_classifier(
                args.recordings,
                label_dim=args.label_dim,
                class_names=args.class_names.split(",") if args.class_names else None,
                train_fraction=args.train_fraction,
                gap_bins=args.gap_bins,
                models_dir=args.models_dir,
                feature_source=args.feature_source,
            )
            model_id = clf.model_id
            md = classifier_report_markdown(report)
        else:
            model, report = calibrate(
                args.recordings,
                train_fraction=args.train_fraction,
                gap_bins=args.gap_bins,
                models_dir=args.models_dir,
                feature_source=args.feature_source,
            )
            model_id = model.model_id
            md = report_markdown(report)
    except CalibrationError as exc:
        print(f"calibration failed: {exc}", file=sys.stderr)
        return 1
    out = REPO_ROOT / "reports" / "calibration" / f"{model_id}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md)
    print(md)
    print(f"model saved to {args.models_dir / (model_id + '.json')}; report {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
