"""Session export: a reproducibility bundle (zip) for one research session.

Contents (every file listed in ``manifest.json`` with its SHA-256 and size)::

    manifest.json         format, session, versions (+ fingerprints), plugins, files, results,
                          what is included and what is not
    session.json          the session (operator and notes only with include_personal)
    session-log.jsonl     device status, operator actions with their configuration
    environment.json      platform, packages, plugins
    devices/*.json        descriptors of the sources used
    pipeline/*.json       each pipeline start: request (processing, model, router) + status
    models/<id>.json      decoder model files used or calibrated in the session
    models/<id>.manifest.json  summary, SHA-256 and size of each model file
    calibration/<id>.json calibration request + report (and .md if one was written)
    recordings/…          only with include_recordings (explicit; may be large and sensitive)
    REPRODUCE.md          exact commands; `concord reproduce <bundle>` re-runs the evaluation

Public datasets are referenced by SHA-256, never copied (DANDI terms forbid redistribution).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import re
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from concord import __version__
from concord.environment import packages, platform_info, plugins
from concord.oscompat import replace
from concord.runtime.recorder import Recorder
from concord.runtime.sessions import SessionError, SessionInfo, SessionManager
from concord.security import ensure_private_dir, open_private

log = logging.getLogger(__name__)

BUNDLE_FORMAT = "concord.session-bundle/1"
EXPORT_NAME = re.compile(r"^concord-session-[0-9a-f\-]+\.zip$")
EXCLUDED_ALWAYS = [
    "public dataset files (referenced by SHA-256; DANDI terms forbid redistribution)",
    "the application log and support reports",
    "data from other sessions",
]


class ExportOptions(BaseModel):
    include_recordings: bool = False  # explicit: recordings can be large and identifying
    include_personal: bool = False  # operator name and free-text notes


class ExportInfo(BaseModel):
    session_id: str
    file: str
    size_bytes: int
    sha256: str
    created_at_ns: int
    files: int
    included_recordings: list[str]
    omitted_recordings: list[str]
    missing_recordings: list[str]
    models: list[str]
    missing_models: list[str]
    options: ExportOptions


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.\-]+", "_", name)[:120]


@dataclass
class _Bundle:
    files: list[dict[str, Any]] = field(default_factory=list)
    data: dict[str, bytes] = field(default_factory=dict)
    paths: dict[str, Path] = field(default_factory=dict)

    def add_bytes(self, arc: str, data: bytes, kind: str) -> None:
        self.data[arc] = data
        self.files.append(
            {
                "path": arc,
                "kind": kind,
                "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
            }
        )

    def add_json(self, arc: str, obj: Any, kind: str) -> None:
        self.add_bytes(arc, (json.dumps(obj, indent=1, default=str) + "\n").encode(), kind)

    def add_file(self, arc: str, path: Path, kind: str) -> None:
        self.paths[arc] = path
        self.files.append(
            {"path": arc, "kind": kind, "size": path.stat().st_size, "sha256": sha256_file(path)}
        )


def _session_record(info: SessionInfo, personal: bool) -> dict[str, Any]:
    d = info.model_dump()
    if not personal:
        d["operator"] = None
        d["notes"] = None
    d["personal_data_included"] = personal
    return d


def _ok(entry: dict[str, Any]) -> bool:
    return 200 <= int(entry.get("status", 0)) < 300


def collect(entries: list[dict[str, Any]]) -> dict[str, Any]:
    """What the session used, from its log: devices, pipeline starts, calibrations, models."""
    devices: dict[str, Any] = {}
    pipelines: list[dict[str, Any]] = []
    calibrations: list[dict[str, Any]] = []
    models: list[str] = []
    for e in entries:
        kind = e.get("kind")
        if kind == "operator_action" and _ok(e):
            action = e.get("action")
            dev = e.get("device")
            if isinstance(dev, dict) and dev.get("device_id"):
                devices[str(dev["device_id"])] = dev
            if action == "pipeline_start":
                pipelines.append(
                    {
                        "at_ns": e.get("at_ns"),
                        "request": e.get("request"),
                        "status": e.get("pipeline"),
                    }
                )
                mid = (e.get("request") or {}).get("model_id")
                if mid and mid not in models:
                    models.append(str(mid))
        elif kind == "calibration" and _ok(e):
            calibrations.append(e)
            mid = e.get("model_id")
            if mid and mid not in models:
                models.append(str(mid))
    return {
        "devices": devices,
        "pipelines": pipelines,
        "calibrations": calibrations,
        "models": models,
    }


def export_session(
    sessions: SessionManager,
    session_id: str,
    *,
    recorder: Recorder,
    models_dir: Path,
    reports_dir: Path,
    options: ExportOptions,
) -> ExportInfo:
    info = sessions.get(session_id)
    entries = sessions.entries(session_id)
    used = collect(entries)
    model_ids = list(dict.fromkeys([*info.models, *used["models"]]))
    b = _Bundle()
    now = time.time_ns()

    b.add_json("session.json", _session_record(info, options.include_personal), "session")
    log_bytes = b"".join(
        (json.dumps(e, separators=(",", ":"), default=str) + "\n").encode() for e in entries
    )
    b.add_bytes("session-log.jsonl", log_bytes, "session_log")
    env = {"platform": platform_info(), "packages": packages(), "plugins": plugins()}
    b.add_json("environment.json", env, "environment")
    for did, desc in sorted(used["devices"].items()):
        b.add_json(f"devices/{_safe(did)}.json", desc, "device")
    for i, p in enumerate(used["pipelines"], start=1):
        b.add_json(f"pipeline/{i:02d}-start.json", p, "pipeline")

    models_in: list[str] = []
    models_missing: list[str] = []
    datasets: list[dict[str, Any]] = []
    for mid in model_ids:
        path = models_dir / f"{mid}.json"
        if not path.is_file():
            models_missing.append(mid)
            continue
        b.add_file(f"models/{_safe(mid)}.json", path, "model")
        models_in.append(mid)
        manifest: dict[str, Any] = {
            "model_id": mid,
            "file": f"models/{_safe(mid)}.json",
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
        }
        with contextlib.suppress(Exception):  # numpy-free installs: hash and size only
            from concord.decoding.model import load_model, summary

            model = load_model(path)
            manifest["summary"] = summary(model)
            for ev in model.evaluations:
                if isinstance(ev, dict) and ev.get("sha256"):
                    datasets.append(
                        {"model_id": mid, "file": ev.get("file"), "sha256": ev["sha256"]}
                    )
        b.add_json(f"models/{_safe(mid)}.manifest.json", manifest, "model_manifest")

    calib_results: list[dict[str, Any]] = []
    for c in used["calibrations"]:
        mid = str(c.get("model_id"))
        b.add_json(f"calibration/{_safe(mid)}.json", c, "calibration")
        md = reports_dir / "calibration" / f"{mid}.md"
        if md.is_file():
            b.add_file(f"calibration/{_safe(mid)}.md", md, "calibration_report")
        calib_results.append(
            {"model_id": mid, "request": c.get("request"), "report": c.get("report")}
        )

    included: list[str] = []
    omitted: list[dict[str, Any]] = []
    missing: list[str] = []
    for name in info.recordings:
        files = recorder.files(name)
        main = next((p for p in files if p.name.endswith(".concord.jsonl")), None)
        if main is None:
            missing.append(name)
            continue
        if name == recorder.active_name:
            omitted.append({"name": name, "reason": "still being written"})
            continue
        if options.include_recordings:
            for p in files:
                b.add_file(f"recordings/{p.name}", p, "recording")
            included.append(name)
        else:
            omitted.append(
                {
                    "name": name,
                    "sha256": sha256_file(main),
                    "size": main.stat().st_size,
                    "reason": "recordings not included (export option)",
                }
            )

    reproduce = _reproduce_md(info, calib_results, included, omitted, missing, datasets, options)
    b.add_bytes("REPRODUCE.md", reproduce.encode(), "instructions")

    excluded = list(EXCLUDED_ALWAYS)
    if not options.include_personal:
        excluded.insert(0, "operator name and session notes (export option)")
    if not options.include_recordings and info.recordings:
        excluded.insert(0, "recordings (export option; listed with SHA-256)")
    manifest_doc = {
        "format": BUNDLE_FORMAT,
        "created_at_ns": now,
        "concord_version": __version__,
        "session": {
            "id": info.id,
            "status": info.status,
            "created_at_ns": info.created_at_ns,
            "closed_at_ns": info.closed_at_ns,
        },
        "options": options.model_dump(),
        "environment": env,
        "files": b.files,
        "results": {
            "calibrations": calib_results,
            "pipelines": used["pipelines"],
        },
        "recordings": {"included": included, "omitted": omitted, "missing": missing},
        "models": {"included": models_in, "missing": models_missing},
        "datasets": datasets,
        "excluded": excluded,
    }

    exports = ensure_private_dir(sessions.folder(session_id) / "exports")
    stamp = time.strftime("%Y%m%d-%H%M%S", time.localtime(now / 1e9))
    final = exports / f"concord-session-{session_id}-{stamp}.zip"
    tmp = exports / f".{final.name}.part"
    fd = open_private(tmp)
    try:
        with os.fdopen(fd, "wb") as raw, zipfile.ZipFile(raw, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in b.files:
                arc = f["path"]
                if arc in b.data:
                    zf.writestr(arc, b.data[arc])
                else:
                    zf.write(b.paths[arc], arc)
            zf.writestr("manifest.json", json.dumps(manifest_doc, indent=1, default=str) + "\n")
        replace(tmp, final)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    result = ExportInfo(
        session_id=session_id,
        file=final.name,
        size_bytes=final.stat().st_size,
        sha256=sha256_file(final),
        created_at_ns=now,
        files=len(b.files) + 1,
        included_recordings=included,
        omitted_recordings=[o["name"] for o in omitted],
        missing_recordings=missing,
        models=models_in,
        missing_models=models_missing,
        options=options,
    )
    if sessions.active is not None and sessions.active.id == session_id:
        sessions.record(
            "export",
            file=final.name,
            sha256=result.sha256,
            include_recordings=options.include_recordings,
            include_personal=options.include_personal,
        )
    log.info(
        "session %s exported (%d files, %d bytes)", session_id, result.files, result.size_bytes
    )
    return result


def list_exports(sessions: SessionManager, session_id: str) -> list[dict[str, Any]]:
    folder = sessions.folder(session_id) / "exports"
    if not folder.is_dir():
        return []
    return [
        {"file": p.name, "size_bytes": p.stat().st_size, "created_at_ns": p.stat().st_mtime_ns}
        for p in sorted(folder.glob("concord-session-*.zip"), reverse=True)
    ]


def export_path(sessions: SessionManager, session_id: str, file: str) -> Path:
    if not EXPORT_NAME.match(file):
        raise SessionError(f"invalid export file name {file!r}", not_found=True)
    path = sessions.folder(session_id) / "exports" / file
    if not path.is_file():
        raise SessionError(f"no export {file!r}", not_found=True)
    return path


def _reproduce_md(
    info: SessionInfo,
    calibrations: list[dict[str, Any]],
    included: list[str],
    omitted: list[dict[str, Any]],
    missing: list[str],
    datasets: list[dict[str, Any]],
    options: ExportOptions,
) -> str:
    lines = [
        f"# Reproducing Concord session {info.id}",
        "",
        f"Exported by Concord {__version__}. Every file in this bundle is listed in "
        "`manifest.json` with its SHA-256; `environment.json` lists the exact package versions "
        "and fingerprints, the platform and the plugins of the original run.",
        "",
        "## 1. Install the same Concord version",
        "",
        "Download the wheels of this version from the project's release page (Concord's "
        "packages are not on PyPI), put them in one folder, then:",
        "",
        "```bash",
        f'pip install --find-links <folder> "concordos[lab]=={__version__}"',
        "```",
        "",
        "(The desktop app of the same version works too: its program accepts `reproduce`. "
        "From a source checkout: `make setup`. Package versions that differ from "
        "`environment.json` can change numerical results in the last digits.)",
        "",
        "## 2. Verify the bundle and re-run its evaluation",
        "",
        "```bash",
        "concord reproduce <this-file>.zip",
        "```",
        "",
        "This checks every file against `manifest.json`, re-fits each calibrated decoder from the "
        "bundled recordings with the recorded parameters and compares weights and held-out "
        "metrics, and recomputes the decoded output recorded during the session from the "
        "recorded features with the bundled model. It exits 0 only if everything that can be "
        "reproduced from the bundle was reproduced.",
        "",
    ]
    if calibrations:
        lines += ["## 3. The same, step by step", ""]
        for c in calibrations:
            req = c.get("request") or {}
            rep = c.get("report") or {}
            recs = " ".join(f"recordings/{r}.concord.jsonl" for r in req.get("recordings", []))
            cmd = f"python -m concord.decoding.calibrate {recs}"
            if req.get("feature_source"):
                cmd += f" --feature-source {req['feature_source']}"
            if req.get("train_fraction") is not None:
                cmd += f" --train-fraction {req['train_fraction']}"
            if req.get("gap_bins") is not None:
                cmd += f" --gap-bins {req['gap_bins']}"
            if req.get("kind") == "classifier":
                cmd += " --classes"
                if req.get("label_dim"):
                    cmd += f" --label-dim {req['label_dim']}"
                if req.get("class_names"):
                    cmd += f" --class-names {','.join(req['class_names'])}"
            cmd += " --models-dir reproduced-models"
            metric = (
                f"held-out R² {rep['r2']:.6f}"
                if isinstance(rep.get("r2"), int | float)
                else f"held-out balanced accuracy {rep.get('balanced_accuracy')}"
            )
            lines += [
                f"Model `{c.get('model_id')}` ({metric}):",
                "",
                "```bash",
                cmd,
                "```",
                "",
            ]
    lines += ["## Not in this bundle", ""]
    if not options.include_recordings and omitted:
        lines.append(
            "Recordings (not included by the export options); place them in "
            "`recordings/` and they can be checked against these hashes:"
        )
        lines.append("")
        for o in omitted:
            lines.append(f"- `{o['name']}` — {o.get('reason')}; SHA-256 `{o.get('sha256', '?')}`")
        lines.append("")
    if missing:
        lines.append(
            "Recordings that were deleted before the export: "
            + ", ".join(f"`{m}`" for m in missing)
        )
        lines.append("")
    if datasets:
        lines.append(
            "Public dataset files the bundled models were evaluated on (download "
            "with `concord dataset`, verified by SHA-256):"
        )
        lines.append("")
        for d in datasets:
            lines.append(
                f"- `{d.get('file')}` SHA-256 `{d.get('sha256')}` (model `{d['model_id']}`)"
            )
        lines.append("")
    if not options.include_personal:
        lines.append("The operator's name and the session notes (export option).")
        lines.append("")
    lines += [
        "Offline reproduction re-runs the computation on the recorded data; it does not "
        "re-create the live session, the participant's behaviour, or closed-loop performance.",
        "",
    ]
    _ = included
    return "\n".join(lines)
