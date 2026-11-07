"""Decoder model registry and input-compatibility rules.

A decoder is only run on a stream whose features match what it was trained on. Mismatches
are refused with explicit reasons; a model trained on a *different source* (participant,
implant, dataset) is refused unless the operator explicitly overrides, in which case the
override is recorded and shown wherever the model's output is shown.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from brainos.decoding.lda import LDAClassifier
from brainos.decoding.ridge import RidgeDecoder

log = logging.getLogger(__name__)

# Every model file is ``brainos.model/1``: a continuous regression decoder (ridge) or a
# classifier (``outputs: {"type": "classes"}``, LDA). Both expose model_id, dims, quantity,
# unit, space, input, source, training, evaluations and ``streaming().step(features)``.
Decoder = RidgeDecoder | LDAClassifier


def load_model(path: Path) -> Decoder:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: not a model object")
    outputs = data.get("outputs")
    if data.get("kind") == "lda" or (
        isinstance(outputs, dict) and outputs.get("type") == "classes"
    ):
        return LDAClassifier.from_dict(data, path.name)
    model = RidgeDecoder(**data)
    if len(model.weights) != model.channel_count or any(
        len(r) != len(model.dims) for r in model.weights
    ):
        raise ValueError(f"{path.name}: weight matrix shape does not match channels/dims")
    return model


def output_classes(model: Decoder) -> list[str] | None:
    """Class names if the model is a classifier, else None (continuous outputs)."""
    return list(model.classes) if isinstance(model, LDAClassifier) else None


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


def model_input(model: Decoder) -> dict[str, Any]:
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


def model_source(model: Decoder) -> str | None:
    if model.source.get("identity"):
        return str(model.source["identity"])
    ds = str(model.training.get("dataset", ""))
    if ds.upper().startswith("DANDI:000954"):
        return "dandi:000954:HumanPitt"
    return None


_DANDISET = re.compile(r"^dandi:(\d+):")


def model_modality(model: Decoder) -> str | None:
    """Recording modality of the model's training data (a contract ``Modality`` value).

    Declared in ``input.modality`` (M5). Models without it inherit the modality that the
    pinned manifest of their training dataset declares (e.g. FALCON H1 -> intracortical);
    otherwise unknown. Never guessed from features or channel counts.
    """
    declared = model.input.get("modality") if model.input else None
    if isinstance(declared, str) and declared:
        return declared
    m = _DANDISET.match(model_source(model) or "")
    if m:
        from brainos.datasets import manifests

        for man in manifests():
            if man.dandiset == m.group(1) and man.modality:
                return man.modality
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
    model: Decoder,
    *,
    event_type: str,
    feature: str,
    bin_ms: float,
    channel_count: int,
    channel_labels: list[str] | None,
    stream_identity: str | None,
    stream_session: str | None = None,
    allow_cross_source: bool = False,
    stream_modality: str | None = None,
    stream_bad_channels: list[str] | None = None,
) -> Compatibility:
    c = Compatibility()
    want = model_input(model)
    # M5: a model is never run on a different recording modality (ECoG high gamma, intracortical
    # spike counts and scalp EEG band power are not interchangeable). Not overridable.
    trained_modality = model_modality(model)
    if trained_modality and stream_modality and trained_modality != stream_modality:
        c.errors.append(
            f"model was trained on {trained_modality} recordings; this source is "
            f"{stream_modality}. Features from different recording modalities are not "
            "interchangeable (refused; no override)"
        )
    elif trained_modality and not stream_modality:
        c.warnings.append(
            f"model was trained on {trained_modality} recordings; this source does not declare "
            "its modality"
        )
    elif stream_modality and not trained_modality:
        c.warnings.append("model does not declare the recording modality of its training data")
    excluded = set(want.get("excluded_channels") or [])
    labels_in = want.get("channel_labels") or []
    used_bad = [b for b in stream_bad_channels or [] if b in labels_in and b not in excluded]
    if used_bad:
        c.warnings.append(f"the model uses channel(s) this source marks bad: {', '.join(used_bad)}")
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
    trained = {str(x) for x in model.training.get("sessions") or [] if x}
    if model.training.get("session"):
        trained.add(str(model.training["session"]))
    if stream_session and stream_session in trained:
        c.errors.append(
            f"stream is from the model's training session {stream_session}; decoding it would "
            "score the model on its own training data"
        )
    return c


def list_models(models_dir: Path) -> list[Decoder]:
    out: list[Decoder] = []
    if models_dir.exists():
        for p in sorted(models_dir.glob("*.json")):
            try:
                out.append(load_model(p))
            except (ValueError, TypeError, KeyError, OSError) as exc:
                log.warning("ignoring model %s: %s", p.name, exc)
    return out


def summary(model: Decoder) -> dict[str, Any]:
    ev = model.evaluations[-1] if model.evaluations else {}
    classes = output_classes(model)
    extra: dict[str, Any] = {}
    if classes is not None:
        extra = {
            "held_out_balanced_accuracy": ev.get("balanced_accuracy"),
            "held_out_accuracy": ev.get("accuracy"),
            "chance_balanced_accuracy": ev.get("chance_balanced_accuracy"),
        }
    return {
        **extra,
        "outputs": {"type": "classes", "classes": classes}
        if classes is not None
        else {"type": "continuous"},
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
        "modality": model_modality(model),
        "trained_on": model.training.get("file") or model.training.get("recording"),
        "training_session": model.training.get("session"),
        "held_out_r2": ev.get("r2"),
        "held_out_samples": ev.get("samples"),
        "control_mean_predictor_r2": ev.get("control_mean_predictor_r2"),
    }
