"""``concord reproduce BUNDLE.zip``: verify a session export and re-run its evaluation.

1. **Integrity**: every file in the bundle must be listed in ``manifest.json`` with a matching
   SHA-256 and size, and every listed file must be present.
2. **Calibration**: each decoder calibrated during the session is fitted again from the
   bundled recordings with the recorded parameters; weights and held-out metrics are compared
   with the bundled model and the recorded report.
3. **Decoded output**: where a recording contains decoder output (``intent.kinematics``) of a
   bundled linear (ridge) model, that output is recomputed from the recorded features and
   compared value by value. The first ``len(kernel)`` bins after a discontinuity (recording
   start, a feature without output) are not compared: the decoder's history before them is
   not in the recording.

Tolerances: metrics and decoded values must agree to 1e-6 (relative to max(1, |value|)).
Identical software on the same CPU architecture reproduces them exactly (the model id, a hash
of the weights, is then identical too); other BLAS builds may differ in the last digits.

Exit status: 0 everything checked was reproduced; 1 a check failed; 2 integrity verified but
nothing could be re-run from the bundle (e.g. recordings not included).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import tempfile
import zipfile
from collections import deque
from pathlib import Path, PurePosixPath
from typing import Any

TOL = 1e-6
BUNDLE_FORMAT = "concord.session-bundle/1"


class BundleError(Exception):
    pass


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= TOL * max(1.0, abs(a), abs(b))


def _safe_member(name: str) -> bool:
    p = PurePosixPath(name)
    return not p.is_absolute() and ".." not in p.parts and name == p.as_posix() and bool(name)


def verify_and_extract(bundle: Path, dest: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    """Integrity check; extracts listed files into ``dest``. Returns (manifest, check)."""
    with zipfile.ZipFile(bundle) as zf:
        names = zf.namelist()
        if "manifest.json" not in names:
            raise BundleError("not a Concord session bundle (no manifest.json)")
        manifest = json.loads(zf.read("manifest.json"))
        if manifest.get("format") != BUNDLE_FORMAT:
            raise BundleError(f"unsupported bundle format {manifest.get('format')!r}")
        listed = {f["path"]: f for f in manifest.get("files", [])}
        problems: list[str] = []
        for name in names:
            if name == "manifest.json":
                continue
            if not _safe_member(name):
                problems.append(f"unsafe path {name!r}")
            elif name not in listed:
                problems.append(f"{name}: not listed in the manifest")
        for path, f in listed.items():
            if path not in names:
                problems.append(f"{path}: listed but missing")
                continue
            if not _safe_member(path):
                continue
            h = hashlib.sha256()
            size = 0
            target = dest / path
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(path) as src, target.open("wb") as out:
                while chunk := src.read(1 << 20):
                    h.update(chunk)
                    size += len(chunk)
                    out.write(chunk)
            if h.hexdigest() != f.get("sha256") or size != f.get("size"):
                problems.append(f"{path}: SHA-256/size differ from the manifest")
    check = {
        "check": "integrity",
        "ok": not problems,
        "detail": f"{len(listed)} files verified against manifest.json"
        if not problems
        else "; ".join(problems[:20]),
    }
    return manifest, check


def _metrics(report: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for k in ("r2", "control_mean_predictor_r2", "balanced_accuracy", "accuracy"):
        v = report.get(k)
        if isinstance(v, int | float) and not isinstance(v, bool):
            out[k] = float(v)
    for dim, v in (report.get("r2_per_dim") or {}).items():
        if isinstance(v, int | float):
            out[f"r2[{dim}]"] = float(v)
    return out


def _max_diff(a: Any, b: Any) -> float:
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return math.inf
        return max((_max_diff(x, y) for x, y in zip(a, b, strict=True)), default=0.0)
    if isinstance(a, int | float) and isinstance(b, int | float):
        return abs(float(a) - float(b))
    return 0.0 if a == b else math.inf


def check_calibration(root: Path, cal: dict[str, Any], work: Path) -> dict[str, Any]:
    from concord.decoding.calibrate import calibrate, calibrate_classifier
    from concord.decoding.lda import DEFAULT_TAU_MS

    mid = cal.get("model_id")
    req = cal.get("request") or {}
    paths = [root / "recordings" / f"{r}.concord.jsonl" for r in req.get("recordings", [])]
    base = {"check": "calibration", "model_id": mid}
    missing = [p.name for p in paths if not p.exists()]
    if not paths or missing:
        return {
            **base,
            "ok": None,
            "detail": f"recordings not in the bundle: {', '.join(missing) or '-'}",
        }
    out_dir = work / "reproduced-models"
    if req.get("kind") == "classifier":
        model, report = calibrate_classifier(
            paths,
            label_dim=req.get("label_dim"),
            class_names=req.get("class_names"),
            train_fraction=req.get("train_fraction", 0.8),
            gap_bins=req.get("gap_bins", 12),
            tau_ms=float(req["tau_ms"]) if req.get("tau_ms") is not None else DEFAULT_TAU_MS,
            models_dir=out_dir,
            feature_source=req.get("feature_source"),
        )
    else:
        model, report = calibrate(  # type: ignore[assignment]
            paths,
            train_fraction=req.get("train_fraction", 0.8),
            gap_bins=req.get("gap_bins", 12),
            models_dir=out_dir,
            feature_source=req.get("feature_source"),
        )
    expected = _metrics(cal.get("report") or {})
    got = _metrics(report)
    metric_rows = [
        {"metric": k, "original": v, "reproduced": got.get(k), "ok": k in got and _close(v, got[k])}
        for k, v in sorted(expected.items())
    ]
    bundled = root / "models" / f"{mid}.json"
    weights_diff: float | None = None
    if bundled.exists():
        orig = json.loads(bundled.read_text())
        new = json.loads((out_dir / f"{model.model_id}.json").read_text())
        keys = [
            k for k in ("weights", "intercept", "x_mean", "x_std", "means", "coef") if k in orig
        ]
        weights_diff = max((_max_diff(orig[k], new.get(k)) for k in keys), default=0.0)
    ok = (
        bool(metric_rows)
        and all(r["ok"] for r in metric_rows)
        and (weights_diff is None or weights_diff <= TOL)
    )
    return {
        **base,
        "ok": ok,
        "reproduced_model_id": model.model_id,
        "identical_model_id": model.model_id == mid,
        "max_parameter_difference": weights_diff,
        "metrics": metric_rows,
        "detail": (
            f"re-fitted from {len(paths)} recording(s): "
            + ", ".join(
                f"{r['metric']} {r['original']:.6g} -> {r['reproduced']:.6g}"
                for r in metric_rows
                if r["reproduced"] is not None
            )
        ),
    }


def check_decoded_output(root: Path, recording: Path) -> list[dict[str, Any]]:
    """Recompute recorded ridge-decoder output from recorded features."""
    from concord.decoding.model import load_model
    from concord.decoding.ridge import RidgeDecoder

    models: dict[str, Any] = {}
    stats: dict[str, dict[str, Any]] = {}
    feats: deque[tuple[int, list[float]]] = deque(maxlen=256)
    decoders: dict[str, Any] = {}
    since: dict[str, int] = {}
    with recording.open(encoding="utf-8") as fh:
        fh.readline()
        for line in fh:
            try:
                ev = json.loads(line)
            except ValueError:
                continue
            et = ev.get("event_type")
            ts = ev.get("device_timestamp_ns")
            if et in ("features.binned", "features.vector") and ts is not None:
                p = ev["payload"]
                feats.append((int(ts), p["counts"] if et == "features.binned" else p["values"]))
                continue
            if et != "intent.kinematics" or ts is None:
                continue
            mid = (ev.get("provenance") or {}).get("model_id")
            if not mid:
                continue
            if mid not in models:
                path = root / "models" / f"{mid}.json"
                models[mid] = load_model(path) if path.exists() else None
                stats[mid] = {"compared": 0, "warmup": 0, "unmatched": 0, "max_abs_diff": 0.0}
            model = models[mid]
            st = stats[mid]
            if model is None or not isinstance(model, RidgeDecoder):
                st["unmatched"] += 1
                continue
            # the input bin: the oldest pending feature event with the same device timestamp
            idx = next((i for i, (t, _) in enumerate(feats) if t == int(ts)), None)
            if idx is None:
                st["unmatched"] += 1
                continue
            if idx > 0 or mid not in decoders:  # features without output: discontinuity
                decoders[mid] = model.streaming()
                since[mid] = 0
            for _ in range(idx):
                feats.popleft()
            _, values = feats.popleft()
            pred = decoders[mid].step(values)
            since[mid] += 1
            if since[mid] <= len(model.kernel):
                st["warmup"] += 1
                continue
            recorded = ev["payload"]["values"]
            diff = max(
                abs(float(a) - float(b)) / max(1.0, abs(float(a)))
                for a, b in zip(recorded, pred, strict=True)
            )
            st["max_abs_diff"] = max(st["max_abs_diff"], diff)
            st["compared"] += 1
    out = []
    for mid, st in stats.items():
        model = models.get(mid)
        if model is None or not isinstance(model, RidgeDecoder):
            why = (
                "model not in the bundle"
                if model is None
                else "classifier output is not recomputed (only linear decoders)"
            )
            out.append(
                {
                    "check": "decoded_output",
                    "recording": recording.name,
                    "model_id": mid,
                    "ok": None,
                    "detail": why,
                }
            )
            continue
        ok = st["compared"] > 0 and st["max_abs_diff"] <= TOL
        out.append(
            {
                "check": "decoded_output",
                "recording": recording.name,
                "model_id": mid,
                "ok": ok if st["compared"] else None,
                **st,
                "detail": f"{st['compared']} decoded outputs recomputed from recorded features, "
                f"max relative difference {st['max_abs_diff']:.3g} ({st['warmup']} warm-up bins "
                f"not compared, {st['unmatched']} without a matching feature bin)",
            }
        )
    return out


def reproduce(bundle: Path) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="concord-reproduce-") as tmp:
        root = Path(tmp) / "bundle"
        root.mkdir()
        manifest, integrity = verify_and_extract(bundle, root)
        checks: list[dict[str, Any]] = [integrity]
        if integrity["ok"]:
            for cal in manifest.get("results", {}).get("calibrations", []):
                try:
                    checks.append(check_calibration(root, cal, Path(tmp)))
                except Exception as exc:
                    checks.append(
                        {
                            "check": "calibration",
                            "model_id": cal.get("model_id"),
                            "ok": False,
                            "detail": f"re-fit failed: {type(exc).__name__}: {exc}",
                        }
                    )
            rec_dir = root / "recordings"
            for rec in sorted(rec_dir.glob("*.concord.jsonl")) if rec_dir.is_dir() else []:
                checks.extend(check_decoded_output(root, rec))
    reran = [c for c in checks[1:] if c.get("ok") is not None]
    failed = [c for c in checks if c.get("ok") is False]
    status = "failed" if failed else ("reproduced" if reran else "nothing_to_reproduce")
    return {
        "bundle": bundle.name,
        "session": manifest.get("session", {}).get("id"),
        "original_concord": manifest.get("concord_version"),
        "status": status,
        "checks": checks,
        "not_in_bundle": manifest.get("excluded", []),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("bundle", type=Path)
    ap.add_argument("--json", type=Path, default=None)
    args = ap.parse_args(argv)
    try:
        result = reproduce(args.bundle)
    except (BundleError, zipfile.BadZipFile, OSError, ValueError) as exc:
        print(f"concord reproduce: {exc}", file=sys.stderr)
        return 1
    for c in result["checks"]:
        mark = {True: "OK  ", False: "FAIL", None: "skip"}[c.get("ok")]
        what = c["check"] + (f" {c['model_id']}" if c.get("model_id") else "")
        print(f"[{mark}] {what}: {c['detail']}")
    print(f"result: {result['status']}")
    if args.json:
        args.json.write_text(json.dumps(result, indent=1, default=str) + "\n")
    return {"reproduced": 0, "failed": 1}.get(result["status"], 2)


if __name__ == "__main__":
    raise SystemExit(main())
