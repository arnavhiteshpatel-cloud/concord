"""Verification reports: machine-readable JSON and human-readable Markdown.

The JSON report is self-describing and traceable: every input is identified by size and
SHA-256, the thresholds and tool/library versions are recorded, and each check carries the
method used and the evidence. ``schemas/report.schema.json`` describes it.
"""

from __future__ import annotations

import hashlib
import importlib.metadata as md
import json
import platform
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

from concord_hwval import __version__
from concord_hwval.model import Check, Status, Thresholds, overall

REPORT_FORMAT = "concord-hwval.report/1"
SCHEMA_PATH = Path(__file__).parent / "schemas" / "report.schema.json"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def file_entry(role: str, path: Path) -> dict[str, Any]:
    path = Path(path)
    if path.is_dir():
        files = sorted(p for p in path.rglob("*") if p.is_file())
        h = hashlib.sha256()
        total = 0
        for p in files:
            rel = p.relative_to(path).as_posix()
            digest = sha256(p)
            total += p.stat().st_size
            h.update(f"{rel}\0{digest}\n".encode())
        return {
            "role": role,
            "path": str(path),
            "kind": "directory",
            "files": len(files),
            "bytes": total,
            "sha256": h.hexdigest(),
            "sha256_method": "sha256 over sorted lines '<relative path>\\0<file sha256>\\n'",
        }
    return {
        "role": role,
        "path": str(path),
        "kind": "file",
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def _version(dist: str) -> str | None:
    try:
        return md.version(dist)
    except md.PackageNotFoundError:
        return None


def environment() -> dict[str, Any]:
    return {
        "concord_hwval": __version__,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pyxdf": _version("pyxdf"),
        "open_ephys_python_tools": _version("open-ephys-python-tools"),
        "concord": _version("concordos"),
    }


def _jsonable(x: Any) -> Any:
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    if isinstance(x, list | tuple):
        return [_jsonable(v) for v in x]
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating):
        v = float(x)
        return v if np.isfinite(v) else None
    if isinstance(x, float):
        return x if np.isfinite(x) else None
    if isinstance(x, np.ndarray):
        return _jsonable(x.tolist())
    if isinstance(x, Path):
        return str(x)
    return x


def build(
    *,
    protocol: str,
    inputs: list[dict[str, Any]],
    acquisition: dict[str, Any],
    summary: dict[str, Any],
    checks: list[Check],
    thresholds: Thresholds,
    limitations: list[str],
    scope: dict[str, Any],
    command: list[str] | None = None,
) -> dict[str, Any]:
    verdict = overall(checks)
    by = {s.value: [c.id for c in checks if c.required and c.status is s] for s in Status}
    rep = {
        "format": REPORT_FORMAT,
        "tool": f"concord-hwval {__version__}",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "protocol": protocol,
        "result": verdict.value,
        "result_explanation": _explain(verdict, checks),
        "required_checks_by_status": by,
        "evidence_scope": scope,
        "inputs": inputs,
        "acquisition": acquisition,
        "summary": summary,
        "checks": [c.to_json() for c in checks],
        "thresholds": thresholds.to_json(),
        "limitations": limitations,
        "environment": environment(),
        "command": command,
    }
    out: dict[str, Any] = _jsonable(rep)
    return out


def _explain(verdict: Status, checks: list[Check]) -> str:
    req = [c for c in checks if c.required]
    if verdict is Status.FAIL:
        bad = [c for c in req if c.status is Status.FAIL]
        return "FAIL: " + "; ".join(f"{c.id}: {c.summary}" for c in bad)
    if verdict is Status.INCONCLUSIVE:
        und = [c for c in req if c.status in (Status.INCONCLUSIVE, Status.NOT_TESTED)]
        return "INCONCLUSIVE: " + "; ".join(f"{c.id}: {c.summary}" for c in und)
    return f"PASS: all {len(req)} required checks passed."


ICON = {
    "pass": "PASS",
    "fail": "**FAIL**",
    "inconclusive": "INCONCLUSIVE",
    "not_tested": "not tested",
}


def _fmt(v: Any) -> str:
    if v is None:
        return "—"
    if isinstance(v, float):
        if v == 0:
            return "0"
        if abs(v) >= 1e5 or abs(v) < 1e-3:
            return f"{v:.4g}"
        return f"{v:.6g}"
    if isinstance(v, list | dict):
        s = json.dumps(v)
        return s if len(s) <= 160 else s[:157] + "..."
    return str(v)


def to_markdown(rep: dict[str, Any]) -> str:
    L: list[str] = []
    res = rep["result"].upper()
    L.append(f"# Concord acquisition verification — {rep['protocol']}")
    L.append("")
    L.append(f"**Result: {res}**")
    L.append("")
    L.append(f"> {rep['result_explanation']}")
    L.append("")
    sc = rep["evidence_scope"]
    L.append("## What this result means")
    L.append("")
    L.append(f"- Evidence level of this run: **{sc['level']}**")
    L.append(f"- {sc['statement']}")
    L.append("- Hardware verified: **no** (never set by this tool). Human validated: **no**.")
    if sc.get("not_a_hardware_run_because"):
        L.append(
            "- Not a hardware-validation run because: "
            + "; ".join(sc["not_a_hardware_run_because"])
            + "."
        )
    L.append("")
    L.append("## Summary")
    L.append("")
    L.append("| Quantity | Value |")
    L.append("| --- | --- |")
    for k, v in rep["summary"].items():
        L.append(f"| {k.replace('_', ' ')} | {_fmt(v)} |")
    L.append("")
    L.append("## Checks")
    L.append("")
    L.append("| Check | Status | Required | Finding |")
    L.append("| --- | --- | --- | --- |")
    for c in rep["checks"]:
        finding = str(c["summary"]).replace("|", "\\|")
        L.append(
            f"| `{c['id']}` {c['title']} | {ICON[c['status']]} | "
            f"{'yes' if c['required'] else 'advisory'} | {finding} |"
        )
    L.append("")
    L.append("## Acquisition source")
    L.append("")
    for k, v in rep["acquisition"].items():
        L.append(f"- **{k.replace('_', ' ')}**: {_fmt(v)}")
    L.append("")
    L.append("## Inputs")
    L.append("")
    L.append("| Role | Path | Bytes | SHA-256 |")
    L.append("| --- | --- | --- | --- |")
    for i in rep["inputs"]:
        L.append(f"| {i['role']} | `{i['path']}` | {i['bytes']} | `{i['sha256']}` |")
    L.append("")
    L.append("## Tests performed and evidence")
    L.append("")
    for c in rep["checks"]:
        L.append(f"### `{c['id']}` — {c['title']}: {ICON[c['status']]}")
        L.append("")
        L.append(f"*Method:* {c['method']}")
        L.append("")
        L.append(f"*Finding:* {c['summary']}")
        L.append("")
        ev = c.get("evidence") or {}
        flat = {k: v for k, v in ev.items() if not isinstance(v, list | dict)}
        nested = {k: v for k, v in ev.items() if isinstance(v, list | dict)}
        if flat:
            L.append("| Evidence | Value |")
            L.append("| --- | --- |")
            for k, v in flat.items():
                L.append(f"| {k} | {_fmt(v)} |")
            L.append("")
        for k, v in nested.items():
            if v in ({}, []):
                continue
            text = json.dumps(v, indent=1)
            if len(text) > 2500:
                text = text[:2500] + "\n... (truncated; full evidence in the JSON report)"
            L.append(f"<details><summary>{k}</summary>\n\n```json\n{text}\n```\n</details>")
            L.append("")
    L.append("## Limitations")
    L.append("")
    for x in rep["limitations"]:
        L.append(f"- {x}")
    L.append("")
    L.append("## Parameters and environment")
    L.append("")
    L.append("```json")
    L.append(
        json.dumps(
            {
                "thresholds": rep["thresholds"],
                "environment": rep["environment"],
                "command": rep.get("command"),
                "tool": rep["tool"],
                "created_at": rep["created_at"],
            },
            indent=1,
        )
    )
    L.append("```")
    L.append("")
    return "\n".join(L)


def write(rep: dict[str, Any], out_dir: Path, stem: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    j = out_dir / f"{stem}.hwval.json"
    m = out_dir / f"{stem}.hwval.md"
    j.write_text(json.dumps(rep, indent=1, allow_nan=False) + "\n", encoding="utf-8")
    m.write_text(to_markdown(rep), encoding="utf-8")
    return j, m
