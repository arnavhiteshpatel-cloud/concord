"""Certify Concord's deliberately broken test plugins and tabulate which check catches what.

The plugins live in ``backend/tests/plugins/concord_test_plugins`` (adapter SDK only, never
installed); each is referenced as ``module:Class`` with that directory on the host's path.

Usage::

    python packages/concord-certify/scripts/certify_broken_plugins.py [--out DIR] [--markdown]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from concord_certify.report import write
from concord_certify.runner import CertifyConfig, run

REPO = Path(__file__).resolve().parents[3]
PLUGINS = REPO / "backend" / "tests" / "plugins"
# class -> the defect it was written to exhibit (backend/tests/plugins/concord_test_plugins)
CASES: dict[str, str] = {
    "GoodPlugin": "none (control)",
    "OpenFailsPlugin": "open() raises OpenFailed (device unplugged)",
    "OpenCrashPlugin": "open() raises an unexpected exception",
    "HangPlugin": "read() blocks forever",
    "GarbagePlugin": "writes garbage to stdout / fd 1",
    "ExitPlugin": "process exits (os._exit) mid-stream",
    "SysExitPlugin": "read() calls sys.exit",
    "UndeclaredRolePlugin": "session declares a role missing from the manifest",
    "UndeclaredStreamPlugin": "chunk for an undeclared stream",
    "WrongChannelsPlugin": "chunk with the wrong channel count",
    "DecreasingTimestampsPlugin": "timestamps jump backwards",
    "NaNPlugin": "NaN in the data",
    "SlowReadPlugin": "each read takes 0.3 s (cannot keep up)",
    "HangDiscoverPlugin": "discover() blocks forever",
    "Api2Plugin": "manifest written for adapter SDK API 2.0",
    "NotAPlugin": "class is not a SourcePlugin",
    "FastPlugin": "unpaced: delivers far faster than its nominal rate",
}
EXTRA = {"concord_test_plugins.import_error:Anything": "module raises ImportError on import"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=None, help="also write each report here")
    ap.add_argument("--duration", type=float, default=3.0)
    ap.add_argument("--markdown", action="store_true", help="print a Markdown table")
    a = ap.parse_args()
    rows = []
    refs = {f"concord_test_plugins:{k}": v for k, v in CASES.items()} | EXTRA
    for ref, defect in refs.items():
        cfg = CertifyConfig(
            plugin=ref,
            options={},
            duration_s=a.duration,
            reopen_s=1.0,
            runtime_s=2.0,
            read_grace_s=2.0,
            extra_path=(str(PLUGINS),),
        )
        report = run(cfg)
        if a.out is not None:
            stem = ref.split(":")[-1] if ":" in ref else ref
            write(report, a.out / f"{stem}.certify.json", a.out / f"{stem}.certify.md")
        failed = [c for c in report["checks"] if c["status"] == "fail"]
        # integrity.read reports that the session stopped; prefer the check naming the cause
        failed.sort(key=lambda c: c["id"] == "integrity.read")
        rows.append(
            {
                "plugin": ref.split(":", 1)[1] if ref.startswith("concord_test_plugins:") else ref,
                "defect": defect,
                "level": report["summary"]["level"],
                "exit_code": report["summary"]["exit_code"],
                "first_failing_check": failed[0]["id"] if failed else None,
                "reason": failed[0]["reason"] if failed else None,
                "failing_checks": [c["id"] for c in failed],
            }
        )
        print(json.dumps(rows[-1]), flush=True)
    if a.markdown:
        print()
        print("| Test plugin | Defect | Level | Caught by (first failing check) | Reason |")
        print("| --- | --- | --- | --- | --- |")
        for r in rows:
            reason = (r["reason"] or "").replace("|", "\\|")
            print(
                f"| `{r['plugin']}` | {r['defect']} | {r['level'] or 'none'} | "
                f"`{r['first_failing_check'] or '-'}` | {reason} |"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
