"""Small accessors for reports."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any


def by_id(rep: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {c["id"]: c for c in rep["checks"]}


def status(rep: dict[str, Any]) -> dict[str, str]:
    return {c["id"]: c["status"] for c in rep["checks"]}


def failed(rep: dict[str, Any]) -> set[str]:
    return {c["id"] for c in rep["checks"] if c["status"] == "fail"}


def mutate_recording(
    src: Path, dst: Path, fn: Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
) -> Path:
    """Copy a Concord recording, letting ``fn`` edit its envelopes; seq is renumbered so the
    file stays internally consistent (as if Concord itself had produced it)."""
    lines = src.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    envs = [json.loads(x) for x in lines[1:] if x.strip()]
    envs = fn(envs)
    seq0 = envs[0]["seq"] if envs else 0
    for i, e in enumerate(envs):
        e["seq"] = seq0 + i
    dst.write_text(
        "\n".join([json.dumps(header)] + [json.dumps(e) for e in envs]) + "\n", encoding="utf-8"
    )
    return dst


def mutate_header(src: Path, dst: Path, fn: Callable[[dict[str, Any]], None]) -> Path:
    lines = src.read_text(encoding="utf-8").splitlines()
    header = json.loads(lines[0])
    fn(header)
    dst.write_text("\n".join([json.dumps(header), *lines[1:]]) + "\n", encoding="utf-8")
    return dst


def frames_of(envs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in envs if e["event_type"] == "recording.frame"]
