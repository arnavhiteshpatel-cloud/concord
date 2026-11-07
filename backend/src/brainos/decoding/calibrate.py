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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, cast

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
    # Milestone 5: every feature input (several when streams are joined, concatenated in
    # this order), the source's declared modality, the behavior's declared +y direction
    inputs: list[dict[str, Any]] = field(default_factory=list)
    modality: str | None = None
    y_axis: str | None = None


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while b := fh.read(1 << 20):
            h.update(b)
    return h.hexdigest()


_BINNED = ("spike_count", "threshold_crossing_count")


def _stream_key(meta: dict[str, Any]) -> tuple[str, str]:
    return (str(meta["et"]), str(meta["p"]["feature"]))


def _declared_stream_labels(caps: list[dict[str, Any]]) -> dict[tuple[str, str], list[str]]:
    """Channel labels per feature stream from a ``neural_features`` ``streams`` declaration."""
    out: dict[tuple[str, str], list[str]] = {}
    for cap in caps:
        for st in cap.get("params", {}).get("streams") or []:
            if not isinstance(st, dict) or not st.get("feature"):
                continue
            lbl = st.get("channel_labels")
            if isinstance(lbl, list):
                feat = str(st["feature"])
                et = str(
                    st.get("event_type")
                    or ("features.binned" if feat in _BINNED else "features.vector")
                )
                out[(et, feat)] = [str(x) for x in lbl]
    return out


def load_session(
    path: Path, *, feature_source: str | None = None, join_features: bool = False
) -> SessionData:
    """Read one recording and align features with behavioral targets.

    ``join_features``: a recording with several feature streams of the same bins (e.g.
    threshold crossings + spike-band power) is used whole: the streams are joined by bin end
    time (bins missing in any stream are dropped) and concatenated, features.binned first,
    then by feature name. Without it, mixed streams are refused (choose one with
    ``feature_source``)."""
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
    by_key = {(str(k[0]), str(k[1])): (k[2], k[3]) for k in kinds}
    if len(kinds) > 1 and (not join_features or len(by_key) != len(kinds)):
        raise CalibrationError(
            f"{path.name}: mixed feature streams {sorted(kinds)}; "
            "pass --feature-source to choose one"
            + (", or join them (--join-features)" if len(by_key) == len(kinds) else "")
        )
    if len({b for b, _ in by_key.values()}) > 1:
        raise CalibrationError(f"{path.name}: feature streams have different bin sizes")
    keys = sorted(by_key, key=lambda k: (k[0] != "features.binned", k[1]))
    first_meta = {k: next(m for _, _, m in feats if _stream_key(m) == k) for k in keys}
    if len(keys) > 1:
        per: dict[tuple[str, str], dict[int, list[float]]] = {k: {} for k in keys}
        for ts_, vals_, m_ in feats:
            per[_stream_key(m_)][ts_] = vals_
        common = sorted(set.intersection(*(set(d) for d in per.values())))
        if not common:
            raise CalibrationError(f"{path.name}: the feature streams share no bin end times")
        feats = [(t, [v for k in keys for v in per[k][t]], first_meta[keys[0]]) for t in common]
    et, feature = keys[0]
    bin_ms, n_ch = by_key[keys[0]]
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
    device = header.get("device", {})
    caps = device.get("capabilities", [])
    ch_labels = None
    declared_classes = None
    y_axis = None
    for cap in caps:
        params = cap.get("params", {})
        lbl = params.get("channel_labels")
        if isinstance(lbl, list) and len(lbl) == n_ch:
            ch_labels = [str(x) for x in lbl]
        names = params.get("class_names")
        if cap.get("capability") == "behavior" and isinstance(names, list) and names:
            declared_classes = [str(x) for x in names]
        if cap.get("capability") == "behavior" and params.get("y_axis") in ("up", "down"):
            y_axis = str(params["y_axis"])
    declared = _declared_stream_labels(caps)
    inputs: list[dict[str, Any]] = []
    for k in keys:
        width = by_key[k][1]
        lbl = declared.get(k)
        if lbl is None and len(keys) == 1:
            lbl = ch_labels
        p0 = first_meta[k]["p"]
        band = p0.get("band_hz")
        inputs.append(
            {
                "event_type": k[0],
                "feature": k[1],
                "bin_ms": float(bin_ms),
                "channel_count": int(width),
                "channel_labels": lbl if lbl is not None and len(lbl) == width else None,
                "unit": str(p0["unit"]) if p0.get("unit") else None,
                "band_hz": [float(x) for x in band] if isinstance(band, list) else None,
            }
        )
    if len(keys) == 1:
        ch_labels = cast(list[str] | None, inputs[0]["channel_labels"])
    bunit = str(beh[0][3]["unit"])
    modality = device.get("modality")
    return SessionData(
        path=path,
        sha256=_sha(path),
        device_id=str(device.get("device_id", "")),
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
        inputs=inputs,
        modality=str(modality) if modality else None,
        y_axis=y_axis,
    )


def chronological_split(n: int, frac: float, trial_starts: list[int]) -> int:
    target = int(frac * n)
    after = [t for t in trial_starts if t >= target]
    return after[0] if after and after[0] < n - 50 else target


Loaded = tuple[
    list[SessionData], NDArray[np.float64], NDArray[np.float64], NDArray[np.bool_], list[int]
]


def _load_sessions(
    paths: list[Path], feature_source: str | None, join_features: bool = False
) -> Loaded:
    sessions = [
        load_session(p, feature_source=feature_source, join_features=join_features) for p in paths
    ]
    s0 = sessions[0]
    layout0 = [(i["event_type"], i["feature"], i["channel_count"]) for i in s0.inputs]
    for s in sessions[1:]:
        layout = [(i["event_type"], i["feature"], i["channel_count"]) for i in s.inputs]
        if (s.bin_ms, s.features.shape[1], s.dims, layout) != (
            s0.bin_ms,
            s0.features.shape[1],
            s0.dims,
            layout0,
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


def _with_modality(spec: dict[str, Any], s0: SessionData) -> dict[str, Any]:
    if s0.modality:  # M5: declared by the recorded device; checked when the model is loaded
        spec["modality"] = s0.modality
    return spec


def _input_spec(s0: SessionData, channels: int) -> dict[str, Any]:
    if s0.inputs and len(s0.inputs) == 1:
        return _with_modality(dict(s0.inputs[0]), s0)
    return _with_modality(
        {
            "event_type": s0.feature_event,
            "feature": s0.feature,
            "bin_ms": s0.bin_ms,
            "channel_count": channels,
            "channel_labels": s0.channel_labels,
        },
        s0,
    )


def _multi_inputs(s0: SessionData) -> list[dict[str, Any]]:
    """The inputs list for a model fitted on joined streams (empty for one stream)."""
    return [_with_modality(dict(i), s0) for i in s0.inputs] if len(s0.inputs) > 1 else []


def calibrate(
    paths: list[Path],
    *,
    train_fraction: float = 0.8,
    gap_bins: int = 12,
    models_dir: Path | None = None,
    feature_source: str | None = None,
    join_features: bool = False,
    loaded: Loaded | None = None,
) -> tuple[RidgeDecoder, dict[str, Any]]:
    sessions, X, Y, V, starts = loaded or _load_sessions(paths, feature_source, join_features)
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
    model.inputs = _multi_inputs(s0)
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
    join_features: bool = False,
    loaded: Loaded | None = None,
) -> tuple[LDAClassifier, dict[str, Any]]:
    """Fit an LDA classifier on recordings whose behavior stream carries a class label.

    Same alignment and chronological split (+ gap) as :func:`calibrate`; only training bins
    are used for smoothing statistics, z-scoring, class means, covariance and shrinkage.
    """
    sessions, X, Y, V, starts = loaded or _load_sessions(paths, feature_source, join_features)
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
    model.inputs = _multi_inputs(s0)
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


# ----------------------------------------------------------------------------- Milestone 5
# Capability-driven calibration: the operator chooses WHAT the decoder should output
# (continuous movement, discrete classes, click); BrainOS checks that the recordings carry
# the labels that output needs, fits a family that can produce it, scores it with metrics
# appropriate to that output, and saves the model with a full decoder manifest.

CAPABILITIES: dict[str, dict[str, str]] = {
    "continuous": {
        "label": "Continuous movement",
        "needs": "a behavior stream with continuous targets (e.g. cued cursor velocity)",
        "metrics": "held-out R², per-dimension R², velocity error",
    },
    "classes": {
        "label": "Discrete classes",
        "needs": "a behavior dimension with a small-integer class code per bin (e.g. a cue)",
        "metrics": "held-out balanced accuracy, per-class recall, confusion matrix",
    },
    "click": {
        "label": "Click",
        "needs": "a behavior dimension that is 1 while a click is attempted and 0 otherwise",
        "metrics": "event precision / recall / F1, false positives per minute, per-bin AUC",
    },
}
DEFAULT_FAMILY = {"continuous": "ridge", "classes": "lda", "click": "lda"}
MIN_CLICK_EVENTS = 5
CLICK_CLASSES = ["no_click", "click"]


@dataclass
class LabelCheck:
    capability: str
    ok: bool
    problems: list[str]
    notes: list[str]
    label_dims: list[str]
    bins: int
    labelled_bins: int
    classes: list[str] | None = None
    events: int | None = None
    inputs: list[dict[str, Any]] = field(default_factory=list)
    modality: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: getattr(self, k) for k in self.__dataclass_fields__}


def _click_dim(dims: list[str], label_dim: str | None) -> str | None:
    if label_dim is not None:
        return label_dim if label_dim in dims else None
    if "click" in dims:
        return "click"
    return dims[0] if len(dims) == 1 else None


def check_labels(
    loaded: Loaded,
    capability: str,
    *,
    label_dim: str | None = None,
    class_names: list[str] | None = None,
) -> LabelCheck:
    """Do these recordings provide what ``capability`` needs? Actionable problems if not."""
    sessions, _X, Y, V, _starts = loaded
    s0 = sessions[0]
    dims = s0.dims
    problems: list[str] = []
    notes: list[str] = []
    out = LabelCheck(
        capability,
        False,
        problems,
        notes,
        [],
        len(V),
        int(V.sum()),
        inputs=s0.inputs,
        modality=s0.modality,
    )
    if capability not in CAPABILITIES:
        problems.append(f"unknown capability {capability!r}; choose {sorted(CAPABILITIES)}")
        return out
    if capability == "continuous":
        out.label_dims = list(dims)
        if V.sum() < 200:
            problems.append(f"only {int(V.sum())} labelled bins; record a longer session (>= 200)")
        vals = Y[V]
        if len(vals):
            codes = all(
                len(np.unique(vals[:, j])) <= MAX_CLASSES
                and np.all(vals[:, j] == np.round(vals[:, j]))
                for j in range(vals.shape[1])
            )
            if codes:
                problems.append(
                    f"the behavior dims {dims} hold small integer codes, not continuous targets: "
                    "choose 'discrete classes' or 'click' instead"
                )
            for j, d in enumerate(dims):
                if np.ptp(vals[:, j]) == 0:
                    notes.append(f"dimension {d} is constant in the labelled bins")
        notes.append(f"targets: {s0.quantity} {dims} in {s0.unit}")
    else:
        if capability == "click":
            ld = _click_dim(dims, label_dim)
            if ld is None:
                problems.append(
                    f"behavior has dimensions {dims}; choose the click label with label_dim"
                )
                return out
        else:
            if label_dim is None and len(dims) != 1:
                problems.append(
                    f"behavior has dimensions {dims}; choose the class label with label_dim"
                )
                return out
            ld = label_dim or dims[0]
            if ld not in dims:
                problems.append(f"behavior has no dimension {ld!r} ({dims})")
                return out
        out.label_dims = [ld]
        labels = Y[:, dims.index(ld)]
        valid = V & np.isfinite(labels)
        out.labelled_bins = int(valid.sum())
        if capability == "click":
            vals = np.unique(labels[valid])
            if not set(vals.tolist()) <= {0.0, 1.0} or len(vals) < 2:
                problems.append(
                    f"a click label must be 0 (no click) / 1 (click); {ld!r} has values "
                    f"{vals[:8].tolist()}{'…' if len(vals) > 8 else ''}"
                )
            else:
                onsets = int(np.sum(np.diff(np.concatenate([[0.0], labels * valid])) > 0.5))
                out.events = onsets
                out.classes = list(CLICK_CLASSES)
                if onsets < MIN_CLICK_EVENTS:
                    problems.append(
                        f"only {onsets} click events; record at least {MIN_CLICK_EVENTS}"
                    )
                per = [int(np.sum(valid & (labels == v))) for v in (0.0, 1.0)]
                if min(per) < MIN_PER_CLASS_BINS:
                    problems.append(f"too few bins per class (no click {per[0]}, click {per[1]})")
        else:
            if valid.sum() < 100:
                problems.append(f"only {int(valid.sum())} labelled bins; record longer (>= 100)")
            try:
                _values, names = class_layout(labels, valid, class_names, s0.declared_classes)
                out.classes = names
            except CalibrationError as exc:
                problems.append(str(exc))
    out.ok = not problems
    return out


MIN_PER_CLASS_BINS = 10


def check_recordings(
    paths: list[Path],
    capability: str,
    *,
    label_dim: str | None = None,
    class_names: list[str] | None = None,
    feature_source: str | None = None,
    join_features: bool = False,
) -> LabelCheck:
    try:
        loaded = _load_sessions(paths, feature_source, join_features)
    except CalibrationError as exc:
        return LabelCheck(capability, False, [str(exc)], [], [], 0, 0)
    return check_labels(loaded, capability, label_dim=label_dim, class_names=class_names)


def _stream_predict(model: Any, X: NDArray[np.float64]) -> NDArray[np.float64]:
    st = model.streaming()
    st.reset()
    return np.array([np.asarray(st.step(row), dtype=np.float64) for row in X])


def _skip_bins(model: Any, bin_ms: float) -> int:
    kernel = getattr(model, "kernel", None)
    return len(kernel) if isinstance(kernel, list) and kernel else max(1, round(500 / bin_ms))


def _fit_family(
    fam: Any,
    capability: str,
    loaded: Loaded,
    check: LabelCheck,
    *,
    train_fraction: float,
    gap_bins: int,
    class_names: list[str] | None,
    tau_ms: float | None,
    event_tolerance_ms: float,
) -> tuple[Any, dict[str, Any]]:
    """A registered family's ``fit`` + held-out evaluation through ``streaming()``."""
    from brainos.decoding.families import CalibrationData
    from brainos.decoding.lda import class_metrics
    from brainos.decoding.ridge import r2_per_dim, r2_variance_weighted

    sessions, X, Y, V, starts = loaded
    s0 = sessions[0]
    n = len(X)
    split = chronological_split(n, train_fraction, starts)
    test_start = min(n, split + gap_bins)
    if test_start >= n - 20:
        raise CalibrationError("not enough data after the split to evaluate; record longer")
    options: dict[str, Any] = {}
    if capability == "continuous":
        targets, dims = Y, list(s0.dims)
        valid = V
    else:
        j = s0.dims.index(check.label_dims[0])
        targets, dims = Y[:, [j]], [check.label_dims[0]]
        valid = V & np.isfinite(Y[:, j])
        if capability == "classes":
            values, names = class_layout(Y[:, j], valid, class_names, s0.declared_classes)
        else:
            values, names = [0.0, 1.0], list(CLICK_CLASSES)
            options["positive_value"] = 1.0
        options.update(class_values=values, class_names=names)
    if tau_ms is not None:
        options["tau_ms"] = tau_ms
    data = CalibrationData(
        features=X,
        targets=targets,
        valid=valid,
        train=slice(0, split),
        target_dims=dims,
        target_unit=s0.unit,
        target_quantity=s0.quantity,
        bin_ms=s0.bin_ms,
        inputs=[dict(i) for i in s0.inputs],
        training=_training_info(sessions, split),
        source={
            "identity": source_identity(s0.origin),
            "description": f"device {s0.device_id}; origin {s0.origin}",
        },
        space=f"{s0.quantity}_{'_'.join(dims)}"[:60],
        options=options,
    )
    try:
        model = fam.fit(data)
    except ValueError as exc:
        raise CalibrationError(f"{fam.name}: {exc}") from None
    skip = _skip_bins(model, s0.bin_ms)
    P = _stream_predict(model, X[test_start:])
    rows = valid[test_start:].copy()
    rows[:skip] = False
    res: dict[str, Any] = {"samples": int(rows.sum())}
    if capability == "continuous":
        y, p = targets[test_start:][rows], P[rows]
        res.update(
            r2=r2_variance_weighted(y, p),
            r2_per_dim=dict(zip(dims, r2_per_dim(y, p), strict=True)),
            control_mean_predictor_r2=r2_variance_weighted(
                y, np.broadcast_to(targets[:split][valid[:split]].mean(axis=0), y.shape)
            ),
        )
    elif capability == "classes":
        vals = options["class_values"]
        index = {v: i for i, v in enumerate(vals)}
        lab = targets[test_start:, 0]
        keep = rows & np.isin(lab, vals)
        true = np.array([index[float(v)] for v in lab[keep]], dtype=np.int64)
        m = class_metrics(true, np.argmax(P[keep], axis=1), len(vals))
        res.update(m, classes=list(options["class_names"]), chance_balanced_accuracy=1 / len(vals))
        res["per_class_accuracy"] = dict(
            zip(options["class_names"], m["per_class_recall"], strict=True)
        )
    model.evaluations.append(
        {
            "file": sessions[-1].path.name,
            "split": "chronological tail",
            "bins": [int(test_start), int(n)],
            **res,
        }
    )
    report = {
        "model_id": model.model_id,
        "recordings": [s.path.name for s in sessions],
        "source_identity": model.source.get("identity"),
        "prerecorded_source": model.training.get("prerecorded_source"),
        "synthetic_source": model.training.get("synthetic_source"),
        "bins_total": n,
        "labelled_bins": int(valid.sum()),
        "train_bins": int(split),
        "gap_bins": gap_bins,
        "test_bins": int(n - test_start),
        **res,
    }
    if capability == "classes":
        report["kind"] = "classifier"
    report["_heldout"] = (test_start, skip, P)
    return model, report


def _heldout_predictions(
    model: Any, X: NDArray[np.float64], test_start: int
) -> NDArray[np.float64]:
    """Held-out predictions of a built-in model, exactly as the pipeline computes them."""
    if hasattr(model, "predict_counts"):
        out: NDArray[np.float64] = model.predict_counts(X[test_start:])
        return out
    if hasattr(model, "predict_proba"):
        out = model.predict_proba(X[test_start:])
        return out
    return _stream_predict(model, X[test_start:])


def _manifest(model: Any, capability: str, check: LabelCheck, s0: SessionData) -> dict[str, Any]:
    from brainos.decoding.model import manifest_for

    m = dict(manifest_for(model))
    m.pop("derived", None)
    m["name"] = f"{CAPABILITIES[capability]['label']} decoder ({m['family']})"
    m["description"] = f"Calibrated by BrainOS from recordings: {model.method}"
    m["modalities"] = [s0.modality] if s0.modality else []
    m["calibration"] = {
        "required": True,
        "task": f"{CAPABILITIES[capability]['label']}: {CAPABILITIES[capability]['needs']}",
        "label_quantity": s0.quantity,
        "label_dims": list(check.label_dims),
        "min_labelled_bins": 200 if capability == "continuous" else 100,
    }
    m["provenance"] = {
        **m["provenance"],
        "trained_by": "BrainOS calibration workflow (decoding/calibrate.py)",
        "notes": f"capability {capability}; recordings "
        + ", ".join(model.training.get("recordings") or []),
    }
    return m


def calibrate_capability(
    paths: list[Path],
    capability: str,
    *,
    family: str | None = None,
    label_dim: str | None = None,
    class_names: list[str] | None = None,
    train_fraction: float = 0.8,
    gap_bins: int = 12,
    tau_ms: float | None = None,
    models_dir: Path | None = None,
    feature_source: str | None = None,
    join_features: bool = False,
    event_tolerance_ms: float = 300.0,
) -> tuple[Any, dict[str, Any]]:
    """Calibrate a decoder for one output capability (see CAPABILITIES)."""
    from brainos.decoding.families import calibration_families
    from brainos.decoding.metrics import event_metrics, velocity_error

    loaded = _load_sessions(paths, feature_source, join_features)
    check = check_labels(loaded, capability, label_dim=label_dim, class_names=class_names)
    if not check.ok:
        raise CalibrationError("; ".join(check.problems))
    sessions, X, Y, V, _starts = loaded
    s0 = sessions[0]
    name = family or DEFAULT_FAMILY[capability]
    fams = {f.name: f for f in calibration_families(capability)}  # type: ignore[arg-type]
    if name not in fams:
        raise CalibrationError(
            f"family {name!r} cannot be calibrated for {capability}; available: {sorted(fams)}"
        )
    model: Any
    if name == "ridge":
        model, report = calibrate(
            paths, train_fraction=train_fraction, gap_bins=gap_bins, loaded=loaded
        )
        test_start = report["train_bins"] + report["gap_bins"]
        skip = len(model.kernel)
        P = _heldout_predictions(model, X, test_start)
    elif name == "lda":
        model, report = calibrate_classifier(
            paths,
            label_dim=check.label_dims[0],
            class_names=class_names if capability == "classes" else CLICK_CLASSES,
            train_fraction=train_fraction,
            gap_bins=gap_bins,
            tau_ms=tau_ms if tau_ms is not None else DEFAULT_TAU_MS,
            loaded=loaded,
        )
        test_start = report["train_bins"] + report["gap_bins"]
        skip = len(model.kernel)
        P = _heldout_predictions(model, X, test_start)
    else:
        model, report = _fit_family(
            fams[name],
            capability,
            loaded,
            check,
            train_fraction=train_fraction,
            gap_bins=gap_bins,
            class_names=class_names,
            tau_ms=tau_ms,
            event_tolerance_ms=event_tolerance_ms,
        )
        test_start, skip, P = report.pop("_heldout")
    split = int(report["train_bins"])
    rows = V[test_start:].copy()
    rows[:skip] = False
    if capability == "continuous":
        report["velocity_error"] = velocity_error(Y[test_start:][rows], P[rows], list(s0.dims))
    elif capability == "click":
        j = s0.dims.index(check.label_dims[0])
        dims = list(model.dims)
        col = dims.index("click") if "click" in dims else len(dims) - 1
        report["events"] = event_metrics(
            P[:, col],
            Y[test_start:, j],
            rows & np.isfinite(Y[test_start:, j]),
            bin_ms=s0.bin_ms,
            tolerance_ms=event_tolerance_ms,
        )
        if model.evaluations:
            model.evaluations[-1]["event_precision"] = report["events"]["event_precision"]
            model.evaluations[-1]["event_recall"] = report["events"]["event_recall"]
    # statistics for online drift monitoring (decoding/monitor.py), training bins only
    tr = model.training
    if not tr.get("feature_stats"):
        tr["feature_stats"] = {
            "mean": X[:split].mean(axis=0).tolist(),
            "std": X[:split].std(axis=0).tolist(),
            "bins": split,
        }
    if capability == "continuous" and not tr.get("output_stats"):
        train_pred = _heldout_predictions(model, X[:split], 0)
        ok = V[:split]
        tr["output_stats"] = {
            "mean": train_pred[ok].mean(axis=0).tolist(),
            "std": train_pred[ok].std(axis=0).tolist(),
        }
    tr["capability"] = capability
    if s0.modality:
        tr["modalities"] = [s0.modality]
    if s0.y_axis and capability == "continuous":
        tr["y_axis"] = s0.y_axis
    if hasattr(model, "manifest"):
        model.manifest = _manifest(model, capability, check, s0)
    if models_dir is not None:
        model.save(models_dir / f"{model.model_id}.json")
    report.update(
        capability=capability,
        family=name,
        label_dims=check.label_dims,
        modality=s0.modality,
        inputs=s0.inputs,
        notes=check.notes,
    )
    return model, report


def capability_report_markdown(report: dict[str, Any]) -> str:
    cap = report.get("capability", "continuous")
    fam = report.get("family")
    if fam == "ridge":
        md = report_markdown(report)
    elif fam == "lda":
        md = classifier_report_markdown(report)
    else:
        lines = [
            f"# Calibration report — `{report['model_id']}` ({fam})",
            "",
            f"- Recordings: {', '.join(report['recordings'])}",
            f"- Source: `{report['source_identity']}`"
            + (" — **prerecorded data streamed live**" if report.get("prerecorded_source") else "")
            + (" — **synthetic data**" if report.get("synthetic_source") else ""),
            f"- Bins: {report['bins_total']} ({report['labelled_bins']} labelled); train "
            f"{report['train_bins']}, gap {report['gap_bins']}, held-out {report['test_bins']}",
        ]
        if "r2" in report:
            lines.append(
                f"- Held-out R² (variance-weighted): **{report['r2']:.3f}** · mean-predictor "
                f"control {report['control_mean_predictor_r2']:.3f}"
            )
        if "balanced_accuracy" in report:
            lines.append(
                f"- Held-out balanced accuracy **{report['balanced_accuracy']:.3f}** (chance "
                f"{report['chance_balanced_accuracy']:.3f})"
            )
        lines += [
            "",
            "Offline held-out scores on a recorded session do not establish closed-loop "
            "control performance.",
            "",
        ]
        md = "\n".join(lines)
    extra: list[str] = [
        f"- Capability: **{CAPABILITIES[cap]['label']}** · family {report.get('family')}"
    ]
    ve = report.get("velocity_error")
    if ve:
        extra.append(
            "- Velocity error (held-out): mean error-vector length "
            f"{ve['mean_vector_error']:.4g} (mean target speed "
            f"{ve['mean_target_speed']:.4g}) · RMSE "
            + ", ".join(f"{k} {v:.3g}" for k, v in ve["rmse_per_dim"].items())
        )
    ev = report.get("events")
    if ev:
        extra.append(
            f"- Click events (held-out, threshold {ev['threshold']}, ±{ev['tolerance_ms']:g} ms): "
            f"precision {_fmt(ev['event_precision'])}, recall {_fmt(ev['event_recall'])}, "
            f"F1 {_fmt(ev['event_f1'])}, {ev['true_events']} true / {ev['detected_events']} "
            f"detected, {_fmt(ev['false_positives_per_min'])} false positives per minute · "
            f"per-bin ROC AUC {_fmt(ev['roc_auc'])}"
        )
    return md.rstrip("\n") + "\n" + "\n".join(extra) + "\n"


def _fmt(v: object) -> str:
    return f"{v:.3f}" if isinstance(v, int | float) and np.isfinite(v) else "—"


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
    ap.add_argument(
        "--capability",
        choices=sorted(CAPABILITIES),
        default=None,
        help="the output to calibrate (Milestone 5 workflow): continuous, classes or click",
    )
    ap.add_argument("--family", default=None, help="decoder family (default per capability)")
    ap.add_argument(
        "--join-features", action="store_true", help="use every feature stream, joined by bin"
    )
    ap.add_argument("--label-dim", default=None, help="behavior dimension holding the class")
    ap.add_argument("--class-names", default=None, help="comma-separated, index = label value")
    args = ap.parse_args(argv)
    try:
        if args.capability:
            cm, report = calibrate_capability(
                args.recordings,
                args.capability,
                family=args.family,
                label_dim=args.label_dim,
                class_names=args.class_names.split(",") if args.class_names else None,
                train_fraction=args.train_fraction,
                gap_bins=args.gap_bins,
                models_dir=args.models_dir,
                feature_source=args.feature_source,
                join_features=args.join_features,
            )
            model_id = cm.model_id
            md = capability_report_markdown(report)
        elif args.classes:
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
