"""Usage-probe contract for consented, aggregate real-world-use telemetry.

A platform probe reports only *counts and durations* sampled on the device:
  * ``is_active`` — the user interacted within the idle threshold (from the OS idle timer),
  * ``device_class_counts`` — number of input reports per coarse class (pointer, select,
    scroll, switch_activations, dwell_selections), never key codes, positions or content,
  * ``assistive_tools_enabled`` — OS-reported assistive features (names from a fixed list).
The aggregator turns samples into ``nm.telemetry/1`` payloads accepted by the server allowlist.
Platform sources live in platform_agents/ and are UNTESTED on real devices (BLOCKERS X-7);
this contract and the aggregator are tested here with a simulated probe.

Rules: visible indicator while recording; pause/stop honoured immediately; nothing is sent while
consent is inactive; payloads are reviewable locally before upload.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional, Protocol

COUNT_KEYS = ("pointer", "select", "scroll", "switch_activations", "dwell_selections",
              "text_chars_count")


@dataclass(frozen=True)
class ProbeSample:
    t: datetime  # UTC
    is_active: bool
    device_class_counts: dict  # subset of COUNT_KEYS -> int
    device_assisted: bool = False  # the study device (e.g. BCI as OS pointer) produced input


class UsageProbe(Protocol):
    platform: str

    def sample(self) -> ProbeSample: ...
    def recording_indicator_visible(self) -> bool: ...


@dataclass
class Aggregator:
    participant: str
    device_session_id: str
    platform: str
    app_version: str = "0.1.0"
    sample_s: int = 60
    paused: bool = False
    consent_active: bool = True
    _samples: list = field(default_factory=list)

    def add(self, s: ProbeSample) -> None:
        if self.paused or not self.consent_active:
            return  # dropped at source, never buffered
        bad = set(s.device_class_counts) - set(COUNT_KEYS)
        if bad:
            raise ValueError(f"probe reported non-allowlisted keys: {sorted(bad)}")
        self._samples.append(s)

    def flush(self, period_start: datetime, period_end: datetime,
              fatigue: Optional[int] = None, assistance: Optional[list] = None) -> Optional[dict]:
        if not self.consent_active:
            self._samples.clear()
            return None
        ss = [s for s in self._samples if period_start <= s.t < period_end]
        self._samples = [s for s in self._samples if s.t >= period_end]
        counts = {k: 0 for k in COUNT_KEYS}
        active = 0
        sessions = 0
        prev = False
        interruptions = 0
        for s in ss:
            for k, v in s.device_class_counts.items():
                counts[k] += int(v)
            if s.is_active:
                active += 1
            if s.device_assisted and not prev:
                sessions += 1
            if prev and not s.is_active:
                interruptions += 1
            prev = s.device_assisted and s.is_active
        p = {"schema_version": "nm.telemetry/1", "participant": self.participant,
             "device_session_id": self.device_session_id,
             "period_start": period_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "period_end": period_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "active_minutes": round(active * self.sample_s / 60.0, 3),
             "device_assisted_sessions": sessions, "interruptions": interruptions,
             "interaction_counts": counts,
             "client": {"app_version": self.app_version, "platform": self.platform}}
        if fatigue is not None:
            p["self_reported_fatigue"] = int(fatigue)
        if assistance:
            p["self_reported_assistance"] = assistance
        return p


def batch_sha256(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
