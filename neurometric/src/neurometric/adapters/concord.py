"""Importer: Concord recordings (``concord.recording/1``) -> NeuroMetric canonical events.

Spec: docs/research/concord_reuse_audit.md section 5. Clean-room implementation (Concord code is
not copied). Concord pointer intents carry *velocity* in workspace units/s; NeuroMetric
reconstructs the cursor position exactly as Concord's participant board integrates it:
start (0.5, 0.5), dt capped at 0.1 s, clamp to [0, 1], y down. Positions are then scaled to the
NeuroMetric task space (default 1280 x 800 px).

Confidence: Concord's *simulated* sources emit random "confidence" numbers. They are NOT carried
over. A confidence is kept only for ``decoded_intent`` provenance, with
``meta.confidence_source = "concord:<model_id>"``.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

from ..events.model import EventKind, InputEvent, Modality

CANVAS = (1280.0, 800.0)


class ConcordImportError(ValueError):
    pass


def _clamp01(v: float) -> float:
    return 0.0 if v < 0 else 1.0 if v > 1 else v


def read_recording(path: str | Path) -> tuple[dict, list[dict], str]:
    raw = Path(path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    lines = raw.decode("utf-8").splitlines()
    if not lines:
        raise ConcordImportError("empty file")
    header = json.loads(lines[0])
    if header.get("format") != "concord.recording/1":
        raise ConcordImportError(f"not a concord.recording/1 file: {header.get('format')!r}")
    if not str(header.get("schema_version", "")).startswith("1."):
        raise ConcordImportError("unsupported Concord schema major version")
    envs = []
    for i, ln in enumerate(lines[1:], 2):
        if not ln.strip():
            continue
        try:
            envs.append(json.loads(ln))
        except json.JSONDecodeError:
            if i == len(lines):  # truncated last line after a crash: skip, as Concord does
                continue
            raise
    return header, envs, sha


def import_recording(path: str | Path, canvas=CANVAS) -> list[InputEvent]:
    header, envs, sha = read_recording(path)
    dev = header.get("device", {})
    synthetic = bool(header.get("synthetic") or dev.get("synthetic"))
    intents = [e for e in envs if str(e.get("event_type", "")).startswith("intent.")
               and e.get("event_type") != "intent.kinematics"]
    status = [e for e in envs if e.get("event_type") == "device.status"]
    use_dev = all(e.get("device_timestamp_ns") is not None for e in intents) and intents
    keyf = "device_timestamp_ns" if use_dev else "timestamp_ns"
    if not intents:
        return []
    t0 = min(e[keyf] for e in intents)
    out: list[InputEvent] = []
    x, y = 0.5, 0.5
    last_ptr_t = None
    last_t: dict[str, float] = {}
    seq: dict[str, int] = {}
    has_pointer = any(e["event_type"] == "intent.pointer" for e in intents)
    for e in sorted(intents + status, key=lambda e: e.get("seq", 0)):
        et = e["event_type"]
        prov = e.get("provenance", {})
        pk = prov.get("kind")
        stream = f"concord:{e.get('device_id')}:{et.split('.')[-1]}"
        tv = e.get(keyf) if e.get(keyf) is not None else e.get("timestamp_ns")
        t_ms = (tv - t0) / 1e6
        flags = []
        if stream in last_t and t_ms < last_t[stream]:
            t_ms = last_t[stream]
            flags.append("timestamp_regression_clamped")
        last_t[stream] = t_ms
        s = seq.get(stream, 0)
        seq[stream] = s + 1
        modality = (Modality.SIMULATED if pk == "simulated_intent" or prov.get("synthetic") and pk != "decoded_intent"
                    else Modality.BCI_CURSOR if et == "intent.pointer" else
                    Modality.BCI_SELECT if pk == "decoded_intent" else Modality.REPLAY)
        if prov.get("replayed"):
            flags.append("replayed")
        meta = {"source": {"format": "concord.recording/1", "sha256": sha, "seq": e.get("seq"),
                           "event_type": et, "provenance": prov, "quality": e.get("quality"),
                           "wall_ns": e.get("timestamp_ns")}}
        if flags:
            meta["flags"] = flags
        if dev.get("modality"):
            meta["neural_modality"] = dev["modality"]
        p = e.get("payload", {})
        conf = None
        if pk == "decoded_intent" and p.get("confidence") is not None:
            conf = float(p["confidence"])
            meta["confidence_source"] = f"concord:{prov.get('model_id')}"
        common = dict(session_id=e.get("session_id", "ses_unknown"), stream_id=stream,
                      modality=modality, seq=s, synthetic=synthetic, meta=meta)
        if et == "intent.pointer":
            tsec = tv / 1e9
            dt = 0.0 if last_ptr_t is None else min(max(tsec - last_ptr_t, 0.0), 0.1)
            last_ptr_t = tsec
            vx, vy = float(p.get("vx", 0.0)), float(p.get("vy", 0.0))
            x, y = _clamp01(x + vx * dt), _clamp01(y + vy * dt)
            meta["vx"], meta["vy"] = vx, vy
            out.append(InputEvent(t_ms=t_ms, kind=EventKind.POINTER_MOVE, x=x * canvas[0],
                                  y=y * canvas[1], **common))
        elif et == "intent.selection":
            action = p.get("action", "primary")
            if action == "cancel":
                out.append(InputEvent(t_ms=t_ms, kind=EventKind.CANCEL, confidence=conf, **common))
            elif has_pointer:
                out.append(InputEvent(t_ms=t_ms, kind=EventKind.CLICK, x=x * canvas[0], y=y * canvas[1],
                                      button=0 if action == "primary" else 1, confidence=conf, **common))
            else:
                out.append(InputEvent(t_ms=t_ms, kind=EventKind.SELECT, confidence=conf,
                                      switch_id=action, **common))
        elif et == "intent.text":
            out.append(InputEvent(t_ms=t_ms, kind=EventKind.TEXT_INPUT, text=p.get("text", ""),
                                  confidence=conf, **common))
        elif et == "intent.navigate":
            out.append(InputEvent(t_ms=t_ms, kind=EventKind.SWITCH,
                                  switch_id=str(p.get("direction", "navigate")), confidence=conf, **common))
        elif et == "device.status":
            st = p.get("state") or p.get("status")
            if st == "paused":
                out.append(InputEvent(t_ms=t_ms, kind=EventKind.PAUSE, **common))
            elif st == "streaming" and any(o.kind == EventKind.PAUSE for o in out):
                out.append(InputEvent(t_ms=t_ms, kind=EventKind.RESUME, **common))
    return out
