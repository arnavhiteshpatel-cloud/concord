"""Small accessors for reports."""

from __future__ import annotations

from typing import Any


def by_id(rep: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in rep["checks"]}


def status(rep: dict[str, Any]) -> dict[str, str]:
    return {c["id"]: c["status"] for c in rep["checks"]}


def failed(rep: dict[str, Any]) -> set[str]:
    return {c["id"] for c in rep["checks"] if c["status"] == "fail"}
