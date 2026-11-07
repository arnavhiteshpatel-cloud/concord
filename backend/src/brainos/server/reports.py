"""Reads test reports produced by `make test` / `make e2e` so the console can show them.

Nothing here runs tests; it only reports what the last real run produced.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

Status = Literal["passed", "failed", "skipped"]


class TestCaseResult(BaseModel):
    suite: str
    name: str
    status: Status
    time_s: float
    message: str | None = None


class TestReport(BaseModel):
    name: str
    source: str
    available: bool
    generated_at_ns: int | None = None
    total: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    duration_s: float = 0.0
    cases: list[TestCaseResult] = []
    error: str | None = None


REPORTS: dict[str, str] = {
    "backend (pytest)": "pytest-junit.xml",
    "frontend (vitest)": "vitest-junit.xml",
}
E2E_REPORT = "e2e.json"


def _parse_junit(name: str, path: Path) -> TestReport:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        return TestReport(name=name, source=path.name, available=False, error=str(exc))
    cases: list[TestCaseResult] = []
    for tc in root.iter("testcase"):
        status: Status = "passed"
        message = None
        for child in tc:
            if child.tag in ("failure", "error"):
                status = "failed"
                message = (child.get("message") or child.text or "")[:500]
            elif child.tag == "skipped":
                status = "skipped"
                message = child.get("message")
        cases.append(
            TestCaseResult(
                suite=tc.get("classname") or "",
                name=tc.get("name") or "",
                status=status,
                time_s=float(tc.get("time") or 0.0),
                message=message,
            )
        )
    return TestReport(
        name=name,
        source=path.name,
        available=True,
        generated_at_ns=path.stat().st_mtime_ns,
        total=len(cases),
        passed=sum(c.status == "passed" for c in cases),
        failed=sum(c.status == "failed" for c in cases),
        skipped=sum(c.status == "skipped" for c in cases),
        duration_s=round(sum(c.time_s for c in cases), 3),
        cases=cases,
    )


def _parse_e2e(path: Path) -> TestReport:
    name = "end-to-end demo (playwright)"
    try:
        data = json.loads(path.read_text())
        steps = data["steps"]
        cases = [
            TestCaseResult(
                suite="e2e",
                name=str(s["name"]),
                status="passed" if s["ok"] else "failed",
                time_s=float(s.get("time_s", 0.0)),
                message=s.get("detail"),
            )
            for s in steps
        ]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return TestReport(name=name, source=path.name, available=False, error=str(exc))
    return TestReport(
        name=name,
        source=path.name,
        available=True,
        generated_at_ns=path.stat().st_mtime_ns,
        total=len(cases),
        passed=sum(c.status == "passed" for c in cases),
        failed=sum(c.status == "failed" for c in cases),
        duration_s=round(sum(c.time_s for c in cases), 3),
        cases=cases,
    )


def load_reports(directory: Path) -> list[TestReport]:
    out: list[TestReport] = []
    for name, filename in REPORTS.items():
        path = directory / filename
        if path.exists():
            out.append(_parse_junit(name, path))
        else:
            out.append(TestReport(name=name, source=filename, available=False))
    e2e = directory / E2E_REPORT
    out.append(
        _parse_e2e(e2e)
        if e2e.exists()
        else TestReport(name="end-to-end demo (playwright)", source=E2E_REPORT, available=False)
    )
    return out
