"""Decoder model registry and input-compatibility rules.

A decoder is only run on a stream whose features match what it was trained on. Mismatches
are refused with explicit reasons; a model trained on a *different source* (participant,
implant, dataset) is refused unless the operator explicitly overrides, in which case the
override is recorded and shown wherever the model's output is shown.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from brainos.decoding.ridge import RidgeDecoder

log = logging.getLogger(__name__)

_DANDI = re.compile(r"dandi:(\d+)/sub-([A-Za-z0-9]+)")


def source_identity(origin: str | None) -> str | None:
    """Participant/source identity from a provenance origin, as precisely as it is known.

    ``dandi:000954/sub-HumanPitt-held-in-calib/...`` -> ``dandi:000954:HumanPitt``.
    Other origins are used verbatim (e.g. ``lsl:EEG@labpc``); unknown -> None.
    """
    if not origin:
        return None
    m = _DANDI.search(origin)
    if m:
        return f"dandi:{m.group(1)}:{m.group(2)}"
    return origin


def model_input(model: RidgeDecoder) -> dict[str, Any]:
    """The model's declared input; older model files get a conservative inferred spec."""
    if model.input:
        return model.input
    return {
        "event_type": "features.binned",
        "feature": "spike_count",
        "bin_ms": model.bin_ms,
        "channel_count": model.channel_count,
        "channel_labels": None,
        "inferred": True,
    }


def model_source(model: RidgeDecoder) -> str | None:
    if model.source.get("identity"):
        return str(model.source["identity"])
    ds = str(model.training.get("dataset", ""))
    if ds.upper().startswith("DANDI:000954"):
        return "dandi:000954:HumanPitt"
    return None


@dataclass
class Compatibility:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cross_source: bool = False

    @property
    def ok(self) -> bool:
        return not self.errors


def check(
    model: RidgeDecoder,
    *,
    event_type: str,
    feature: str,
    bin_ms: float,
    channel_count: int,
    channel_labels: list[str] | None,
    stream_identity: str | None,
    stream_session: str | None = None,
    allow_cross_source: bool = False,
) -> Compatibility:
    c = Compatibility()
    want = model_input(model)
    if want["event_type"] != event_type or want["feature"] != feature:
        c.errors.append(
            f"model expects {want['event_type']}/{want['feature']}, "
            f"pipeline produces {event_type}/{feature}"
        )
    if abs(float(want["bin_ms"]) - bin_ms) > 1e-6:
        c.errors.append(
            f"model expects {want['bin_ms']:g} ms bins, pipeline produces {bin_ms:g} ms"
        )
    if int(want["channel_count"]) != channel_count:
        c.errors.append(
            f"model expects {want['channel_count']} channels, source has {channel_count}"
        )
    labels = want.get("channel_labels")
    if labels and channel_labels and list(labels) != list(channel_labels):
        c.errors.append(
            "channel labels differ from the model's training channels (order or identity)"
        )
    elif not labels:
        c.warnings.append(
            "model does not record channel identities; channels are assumed to be in training order"
        )
    trained_on = model_source(model)
    if trained_on is None or stream_identity is None or trained_on != stream_identity:
        c.cross_source = True
        msg = (
            f"model was trained on source {trained_on or 'unknown'}; this stream is "
            f"{stream_identity or 'unknown'}. Decoders do not transfer across participants, "
            "implants or sessions without recalibration."
        )
        if allow_cross_source:
            c.warnings.append("CROSS-SOURCE OVERRIDE: " + msg)
        else:
            c.errors.append(msg + " (explicit override required)")
    trained_session = model.training.get("session")
    if stream_session and trained_session and stream_session == trained_session:
        c.errors.append(
            f"stream is from the model's training session {trained_session}; decoding it would "
            "score the model on its own training data"
        )
    return c


def list_models(models_dir: Path) -> list[RidgeDecoder]:
    out = []
    if models_dir.exists():
        for p in sorted(models_dir.glob("*.json")):
            try:
                out.append(RidgeDecoder.load(p))
            except (ValueError, TypeError, KeyError, OSError) as exc:
                log.warning("ignoring model %s: %s", p.name, exc)
    return out


def summary(model: RidgeDecoder) -> dict[str, Any]:
    ev = model.evaluations[-1] if model.evaluations else {}
    return {
        "model_id": model.model_id,
        "schema": model.schema,
        "version": model.version,
        "created_at": model.created_at,
        "method": model.method,
        "space": model.space,
        "dims": model.dims,
        "unit": model.unit,
        "input": model_input(model),
        "source_identity": model_source(model),
        "trained_on": model.training.get("file") or model.training.get("recording"),
        "training_session": model.training.get("session"),
        "held_out_r2": ev.get("r2"),
        "held_out_samples": ev.get("samples"),
        "control_mean_predictor_r2": ev.get("control_mean_predictor_r2"),
    }
