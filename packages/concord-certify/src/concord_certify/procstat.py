"""CPU time and memory of a process from Linux ``/proc`` (no psutil)."""

from __future__ import annotations

import contextlib
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CLK_TCK = os.sysconf("SC_CLK_TCK") if hasattr(os, "sysconf") else 100


def available(pid: int) -> bool:
    return Path(f"/proc/{pid}/stat").exists()


def cpu_seconds(pid: int) -> float | None:
    """utime + stime of the process, in seconds (children not included)."""
    try:
        raw = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return None
    # the command name (field 2) may contain spaces / parentheses: split after the last ')'
    fields = raw[raw.rfind(")") + 2 :].split()
    try:
        utime, stime = int(fields[11]), int(fields[12])
    except (IndexError, ValueError):
        return None
    return (utime + stime) / CLK_TCK


def memory_kib(pid: int) -> dict[str, int]:
    """VmRSS (current resident set) and VmHWM (peak resident set) in KiB."""
    out: dict[str, int] = {}
    try:
        text = Path(f"/proc/{pid}/status").read_text(encoding="utf-8")
    except OSError:
        return out
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        if key in ("VmRSS", "VmHWM"):
            with contextlib.suppress(IndexError, ValueError):
                out[key] = int(rest.split()[0])
    return out


@dataclass
class ProcSampler:
    """Samples a process's RSS every ``period_s`` and its CPU time at start / stop."""

    pid: int
    period_s: float = 0.25
    t0: float = 0.0
    cpu0: float | None = None
    t1: float = 0.0
    cpu1: float | None = None
    rss_kib: list[int] = field(default_factory=list)
    hwm_kib: int | None = None
    _stop: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None

    def start(self) -> ProcSampler:
        self.t0 = time.monotonic()
        self.cpu0 = cpu_seconds(self.pid)
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def _run(self) -> None:
        while not self._stop.wait(self.period_s):
            mem = memory_kib(self.pid)
            if "VmRSS" in mem:
                self.rss_kib.append(mem["VmRSS"])

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
        self.t1 = time.monotonic()
        self.cpu1 = cpu_seconds(self.pid)
        mem = memory_kib(self.pid)
        if "VmRSS" in mem:
            self.rss_kib.append(mem["VmRSS"])
        self.hwm_kib = mem.get("VmHWM")
        return self.summary()

    def summary(self) -> dict[str, Any]:
        wall = self.t1 - self.t0
        cpu = (
            self.cpu1 - self.cpu0
            if self.cpu0 is not None and self.cpu1 is not None and self.cpu1 >= self.cpu0
            else None
        )
        return {
            "pid": self.pid,
            "wall_s": round(wall, 3),
            "cpu_s": round(cpu, 3) if cpu is not None else None,
            "cpu_percent_of_one_core": round(100.0 * cpu / wall, 1)
            if cpu is not None and wall > 0
            else None,
            "rss_mib_median": round(sorted(self.rss_kib)[len(self.rss_kib) // 2] / 1024, 1)
            if self.rss_kib
            else None,
            "rss_mib_max_sampled": round(max(self.rss_kib) / 1024, 1) if self.rss_kib else None,
            "rss_mib_peak": round(self.hwm_kib / 1024, 1) if self.hwm_kib is not None else None,
            "rss_samples": len(self.rss_kib),
            "clock_ticks_per_s": CLK_TCK,
        }
