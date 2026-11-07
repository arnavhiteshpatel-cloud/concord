"""Report construction, JSON Schema validation and Markdown rendering."""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING, Any

import jsonschema
import numpy as np

from brainos_certify import REPORT_VERSION, __version__
from brainos_certify import checks_static as cs
from brainos_certify.identity import environment
from brainos_certify.levels import LEVELS
from brainos_certify.model import GROUPS, CheckResult

if TYPE_CHECKING:
    from brainos_certify.runner import CertifyConfig, RunState

NOTICE = (
    "SOFTWARE CERTIFICATION ONLY - this report is not hardware certification and not "
    "human-participant validation. A pass means the plugin satisfied the BrainOS adapter "
    "SDK contract, through the real plugin host, with the data source used in this run, on "
    "this machine. It does not show that any physical device, amplifier or implant works with "
    "BrainOS, and it says nothing about safety, clinical use or decoding performance. "
    "'hardware_tested' appears only as an operator's signed attestation, which this toolkit "
    "does not verify; 'human_participant_validated' is never set by this toolkit."
)
STATUS_WORD = {"pass": "PASS", "fail": "FAIL", "warn": "WARN", "not_run": "NOT RUN"}


def report_schema() -> dict[str, Any]:
    text = resources.files("brainos_certify").joinpath("schemas/report.schema.json")
    doc: dict[str, Any] = json.loads(text.read_text(encoding="utf-8"))
    return doc


def validate_report(report: dict[str, Any]) -> list[str]:
    """Schema violations (empty list = valid)."""
    v = jsonschema.Draft202012Validator(report_schema())
    return [
        f"{'/'.join(str(p) for p in e.absolute_path) or '(root)'}: {e.message[:200]}"
        for e in v.iter_errors(report)
    ]


def _default(obj: object) -> object:
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, set | frozenset):
        return sorted(str(x) for x in obj)
    return str(obj)


def jsonable(doc: Any) -> Any:
    return json.loads(json.dumps(doc, default=_default, allow_nan=False))


def _iso(t: dt.datetime) -> str:
    return t.astimezone(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def build_report(
    *,
    cfg: CertifyConfig,
    st: RunState,
    checks: list[CheckResult],
    levels: dict[str, Any],
    rules: list[dict[str, Any]],
    attestation: dict[str, Any] | None,
    started: dt.datetime,
    elapsed_s: float,
) -> dict[str, Any]:
    counts = Counter(c.status for c in checks)
    highest = levels["highest"]
    l1 = levels["levels"]["adapter_implementation"]
    statement = levels["levels"][highest]["statement"] if highest else "no level achieved"
    session = None
    if st.info is not None:
        session = {
            "origin": st.info.origin,
            "synthetic": st.info.synthetic,
            "prerecorded": st.info.prerecorded,
            "primary_stream": st.info.primary_stream,
            "streams": cs.stream_summary(st.info),
        }
    run_opts = cs.redact(cfg.to_dict())
    report: dict[str, Any] = {
        "notice": NOTICE,
        "report_version": REPORT_VERSION,
        "tool": {"name": "brainos-certify", "version": __version__},
        "generated_at": _iso(dt.datetime.now(dt.UTC)),
        "started_at": _iso(started),
        "elapsed_s": round(elapsed_s, 2),
        "environment": environment(st.hello),
        "plugin": {
            "ref": cfg.plugin,
            "entry_point": st.entry_point_name,
            "device_key": st.device_key,
            "manifest": cs.manifest_summary(st.manifest) if st.manifest else None,
            "identity": st.identity,
            "session": session,
        },
        "options": {
            "plugin_options_requested": cs.redact(cfg.options),
            "plugin_options_resolved": cs.redact(st.resolved_options),
            "run": run_opts,
        },
        "summary": {
            "counts": {s: counts.get(s, 0) for s in ("pass", "fail", "warn", "not_run")},
            "level": highest,
            "level_statement": statement,
            "exit_code": 0 if l1["achieved"] else 1,
            "blocking": list(l1["missing"]),
        },
        "levels": levels,
        "protocol_reference": {"statement": cfg.protocol_reference, "consistency": rules}
        if cfg.protocol_reference
        else None,
        "attestation": attestation,
        "checks": [c.to_dict() for c in checks],
        "host_log_tail": [line[:300] for line in st.host_log[-40:]],
    }
    report = jsonable(report)
    problems = validate_report(report)
    if problems:  # a certifier bug: never write a report that breaks its own schema
        raise ValueError("report does not match its schema: " + "; ".join(problems[:5]))
    return report


# ----------------------------------------------------------------------------- Markdown


def _cell(text: object) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def _plugin_title(report: dict[str, Any]) -> str:
    m = report["plugin"].get("manifest") or {}
    if m:
        return f"{m.get('name')} {m.get('version')}"
    return str(report["plugin"]["ref"])


def to_markdown(report: dict[str, Any]) -> str:
    s = report["summary"]
    lv = report["levels"]["levels"]
    p = report["plugin"]
    env = report["environment"]
    lines: list[str] = []
    add = lines.append
    add(f"# BrainOS integration certification: {_plugin_title(report)}")
    add("")
    add(f"> **{report['notice']}**")
    add("")
    level = s["level"] or "none"
    add(f"**Level achieved: `{level}`** - {s['level_statement']}  ")
    add(
        f"Checks: {s['counts']['pass']} pass, {s['counts']['warn']} warn, "
        f"{s['counts']['fail']} fail, {s['counts']['not_run']} not run. "
        f"Exit code {s['exit_code']}.  "
    )
    sess = p.get("session") or {}
    add(
        f"Plugin `{p['ref']}`, device `{p.get('device_key')}`; origin `{sess.get('origin')}` "
        f"(synthetic={sess.get('synthetic')}, prerecorded={sess.get('prerecorded')}).  "
    )
    add(
        f"Run {report['started_at']} on {env.get('os')} {env.get('machine')} "
        f"({env.get('cpu_model')}, {env.get('cpu_count')} CPUs), Python {env.get('python')}, "
        f"adapter SDK {env.get('sdk_version')} (API {env.get('sdk_api_version')}), "
        f"BrainOS {env.get('brainos_version') or 'not installed'}, "
        f"brainos-certify {report['tool']['version']}."
    )
    add("")
    add("## Summary")
    add("")
    add("| Check | Status | Reason |")
    add("| --- | --- | --- |")
    for c in report["checks"]:
        req = "" if c["required"] else " (optional)"
        add(f"| `{c['id']}`{req} | {STATUS_WORD[c['status']]} | {_cell(c['reason'])} |")
    add("")
    add("## Validation levels")
    add("")
    add("| Level | Achieved | Statement / what is missing |")
    add("| --- | --- | --- |")
    for name in LEVELS:
        d = lv[name]
        text = d["statement"] if d["achieved"] else "; ".join(d["missing"][:4])
        add(f"| `{name}` | {'yes' if d['achieved'] else 'no'} | {_cell(text)} |")
    add("")
    for note in lv["adapter_implementation"].get("notes") or []:
        add(f"- Note: {note}")
    rules = lv["protocol_tested"].get("consistency") or []
    if report.get("protocol_reference"):
        add("")
        ref = report["protocol_reference"]["statement"]
        add(f'Protocol reference (operator statement): "{ref}"')
        add("")
        for r in rules:
            ok = {True: "consistent", False: "INCONSISTENT", None: "not checkable"}[r["ok"]]
            add(f"- `{r['rule']}`: {ok} - {r['detail']}")
    att = report.get("attestation")
    if att:
        add("")
        add(
            f"Attestation `{att['file']}` (sha256 {att.get('file_sha256')}): "
            f"{'accepted' if att['accepted'] else 'REJECTED'} - {att['reason']}. "
            f"Verified by the toolkit: {att['verified_by_toolkit']}."
        )
    add("")
    add(
        "Level definitions: docs/CERTIFICATION.md. `adapter_implementation` is the only level "
        "this toolkit grants by itself."
    )
    add("")
    add("## Plugin identity")
    add("")
    m = p.get("manifest") or {}
    ident = p.get("identity") or {}
    dist = ident.get("distribution") or {}
    mod = ident.get("module") or {}
    rec = dist.get("record") or {}
    git = ident.get("git") or {}
    rows = [
        ("Reference", p["ref"]),
        ("Entry point", p.get("entry_point") or "not verified (module:Class)"),
        (
            "Manifest",
            f"{m.get('name')} {m.get('version')}, API {m.get('api_version')}, "
            f"ecosystem {m.get('ecosystem')}, roles {m.get('roles')}",
        ),
        (
            "Distribution",
            f"{dist.get('name')} {dist.get('version')}"
            + (" (editable)" if dist.get("editable") else "")
            if dist
            else "none",
        ),
        (
            "RECORD",
            f"{rec.get('verified')} of {int(rec.get('files') or 0) - int(rec.get('unhashed') or 0)}"
            f" hashed entries verified ({rec.get('files')} files), sha256 {rec.get('sha256')}"
            if rec
            else "none",
        ),
        (
            "Module files",
            f"{mod.get('file_count')} files under {mod.get('path')}, tree sha256 "
            f"{mod.get('tree_sha256')}"
            if mod
            else "unknown",
        ),
        (
            "Git",
            f"{git.get('commit')} ({'dirty' if git.get('dirty') else 'clean'})"
            if git
            else "not a git checkout",
        ),
    ]
    add("| | |")
    add("| --- | --- |")
    for k, val in rows:
        add(f"| {k} | {_cell(val)} |")
    if sess.get("streams"):
        add("")
        add("| Stream | Role | Channels | Rate (Hz) | Clock | Modality | Invasive | Units |")
        add("| --- | --- | --- | --- | --- | --- | --- | --- |")
        for st in sess["streams"]:
            add(
                f"| `{st['stream_id']}` | {st['role']} | {st['channels']} | "
                f"{st['nominal_rate_hz']:g} | {st['clock']} | {st['modality']} | "
                f"{st['invasive']} | {_cell(', '.join(st['units']))} |"
            )
    add("")
    add("## Options")
    add("")
    add(
        f"- Plugin options requested: `{json.dumps(report['options']['plugin_options_requested'])}`"
    )
    add(
        f"- Plugin options resolved by the host: "
        f"`{json.dumps(report['options']['plugin_options_resolved'])}`"
    )
    run = report["options"]["run"]
    add(
        f"- Run: duration {run['duration_s']} s, reopen {run['reopen_s']} s, rate tolerance "
        f"±{100 * run['rate_tolerance']:g} %, runtime phase "
        f"{'on' if run['runtime'] else 'off'} ({run['runtime_s']} s)"
    )
    add("")
    add("## Details")
    for group, title in GROUPS.items():
        items = [c for c in report["checks"] if c["group"] == group]
        if not items:
            continue
        add("")
        add(f"### {title}")
        for c in items:
            add("")
            add(f"**`{c['id']}` - {STATUS_WORD[c['status']]}** - {c['title']}  ")
            add(_cell(c["reason"]))
            if c["evidence"]:
                add("")
                add("<details><summary>evidence</summary>")
                add("")
                add("```json")
                add(json.dumps(c["evidence"], indent=1, sort_keys=True)[:6000])
                add("```")
                add("")
                add("</details>")
    env_rows = {k: env.get(k) for k in sorted(env)}
    add("")
    add("## Environment")
    add("")
    add("```json")
    add(json.dumps(env_rows, indent=1))
    add("```")
    add("")
    return "\n".join(lines)


def write(report: dict[str, Any], json_path: Path, md_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    md_path.write_text(to_markdown(report), encoding="utf-8")
