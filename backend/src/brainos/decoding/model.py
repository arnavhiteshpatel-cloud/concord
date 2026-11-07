"""Decoder models, their manifests, and the compatibility rules checked before inference.

A decoder only runs on a stream whose features match what it was trained on. Every decoder
(built-in JSON family, model file, plugin) is described by a manifest
(``brainos_decoder_sdk`` schema ``brainos.decoder-manifest/1``); :func:`check_manifest`
compares it with what the connected source and the pipeline provide and refuses mismatches
with actionable reasons:

* modality (when both sides declare it);
* every declared input: event type + feature, bin size, unit, band, channel count, channel
  identities AND order (when both sides declare labels);
* preprocessing (pipeline preset and parameters the model was trained with);
* participant / source identity (cross-source use needs the operator's explicit override,
  which is shown and lowers event quality), the training sessions (never decoded: leakage),
  and the calibration profile.

The only transformation BrainOS ever applies is an EXPLICIT, operator-enabled channel
mapping by label (``allow_channel_mapping``): when both sides declare unique labels and the
source has every label the model needs, each model input is fed the source channels with its
labels, in the model's order. The mapping is returned, logged and shown. Nothing is ever
reordered, rescaled or taken across participants silently.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from brainos.decoding.families import JsonModel, family_for, family_of
from brainos.decoding.lda import LDAClassifier

log = logging.getLogger(__name__)

# Any built-in JSON model (ridge, LDA, and families registered in decoding/families.py).
Decoder = JsonModel
MANIFEST_SCHEMA = "brainos.decoder-manifest/1"


def load_model(path: Path) -> Any:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: not a model object")
    return family_for(data).from_dict(data, path.name)


def output_kind(model: Any) -> str:
    """ "continuous", "classes" or "event" for a built-in JSON model."""
    return family_of(model).output


def output_classes(model: Any) -> list[str] | None:
    """Names the router's discrete rules may use: class names of a classifier, event names
    of an event model (e.g. ``click``); None for continuous outputs."""
    if isinstance(model, LDAClassifier):
        return list(model.classes)
    return list(model.dims) if output_kind(model) in ("classes", "event") else None


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


def model_inputs(model: Any) -> list[dict[str, Any]]:
    """The model's declared inputs (several are concatenated in this order)."""
    many = getattr(model, "inputs", None)
    if isinstance(many, list) and many:
        return [dict(i) for i in many]
    return [model_input(model)]


def model_input(model: Any) -> dict[str, Any]:
    """The model's (first) declared input; older model files get a conservative inferred spec."""
    many = getattr(model, "inputs", None)
    if isinstance(many, list) and many:
        return dict(many[0])
    if model.input:
        return dict(model.input)
    return {
        "event_type": "features.binned",
        "feature": "spike_count",
        "bin_ms": model.bin_ms,
        "channel_count": model.channel_count,
        "channel_labels": None,
        "inferred": True,
    }


def model_source(model: Any) -> str | None:
    if model.source.get("identity"):
        return str(model.source["identity"])
    ds = str(model.training.get("dataset", ""))
    if ds.upper().startswith("DANDI:000954"):
        return "dandi:000954:HumanPitt"
    return None


_DANDISET = re.compile(r"^dandi:(\d+):")


def model_modality(model: Any) -> str | None:
    """Recording modality of the model's training data (a contract ``Modality`` value).

    Declared in ``input.modality`` (M5, workstream B) or in a stored manifest. Models without
    it inherit the modality that the pinned manifest of their training dataset declares (e.g.
    FALCON H1 -> intracortical); otherwise unknown. Never guessed from features or channel
    counts.
    """
    inp = model_input(model)
    declared = inp.get("modality") if inp else None
    if isinstance(declared, str) and declared:
        return declared
    stored = getattr(model, "manifest", None)
    if isinstance(stored, dict) and len(stored.get("modalities") or []) == 1:
        return str(stored["modalities"][0])
    m = _DANDISET.match(model_source(model) or "")
    if m:
        from brainos.datasets import manifests

        for man in manifests():
            if man.dandiset == m.group(1) and man.modality:
                return str(man.modality)
    mods = model.training.get("modalities")
    return str(mods[0]) if isinstance(mods, list) and len(mods) == 1 else None


def _sessions(model: Any) -> list[str]:
    trained = {str(x) for x in model.training.get("sessions") or [] if x}
    if model.training.get("session"):
        trained.add(str(model.training["session"]))
    return sorted(trained)


_UNIT_BY_FEATURE = {"spike_count": "count", "threshold_crossing_count": "count"}


def manifest_for(model: Any) -> dict[str, Any]:
    """The decoder manifest of a built-in JSON model: the stored one, or one derived from
    the model's fields (models trained before Milestone 5). Derived manifests only state
    what the file records; unknown modality stays unknown (``modalities: []``)."""
    stored = getattr(model, "manifest", None)
    if isinstance(stored, dict) and stored.get("schema") == MANIFEST_SCHEMA:
        return stored
    fam = family_of(model)
    inputs = []
    for i in model_inputs(model):
        inputs.append(
            {
                "event_type": i.get("event_type", "features.binned"),
                "feature": i.get("feature", "spike_count"),
                "bin_ms": float(i.get("bin_ms", model.bin_ms)),
                "channel_count": int(i.get("channel_count", 0)),
                "channel_labels": i.get("channel_labels"),
                "unit": i.get("unit") or _UNIT_BY_FEATURE.get(str(i.get("feature"))),
                "band_hz": i.get("band_hz"),
                **({"excluded_channels": i["excluded_channels"]} if i.get("excluded_channels") else {}),
            }
        )
    probs = fam.output in ("classes", "event")
    std = model.training.get("behavior_std")
    sha = model.training.get("recording_sha256") or []
    return {
        "schema": MANIFEST_SCHEMA,
        "model_id": model.model_id,
        "name": model.model_id,
        "version": f"{int(getattr(model, 'version', 1))}.0.0",
        "api_version": "1.0",
        "family": fam.name,
        "description": model.method,
        "author": "BrainOS",
        "license": "same as the training data",
        "modalities": [mod] if (mod := model_modality(model)) else [],
        "inputs": inputs,
        "output": {
            "kind": fam.output,
            "quantity": model.quantity,
            "dims": list(model.dims),
            "unit": model.unit,
            "space": model.space,
            "scale": [float(v) for v in std]
            if isinstance(std, list) and not probs and len(std) == len(model.dims)
            else None,
            "y_axis": getattr(model, "y_axis", None) or model.training.get("y_axis"),
        },
        "confidence": fam.confidence,
        "preprocessing": {
            "preset": model.training.get("preset"),
            "params": dict(model.training.get("preset_params") or {}),
            "description": model.method,
        },
        "compatibility": {
            "participant_specific": True,
            "source_identity": model_source(model),
            "sessions": _sessions(model),
            "calibration_profile": model.training.get("calibration_profile"),
        },
        "calibration": {
            "required": True,
            "task": "",
            "label_quantity": None if probs else model.quantity,
            "label_dims": list(model.dims),
            "min_labelled_bins": 0,
        },
        "provenance": {
            "training_data_sha256": [str(s) for s in sha],
            "code_version": f"brainos {model.schema}",
            "created_at": model.created_at,
            "trained_by": "BrainOS",
            "notes": "derived from the model file's fields",
        },
        "artifact": None,
        "derived": True,
    }


# ----------------------------------------------------------------------------- compatibility


@dataclass
class Compatibility:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    cross_source: bool = False
    # per model input: index into the available streams feeding it
    streams: list[int] = field(default_factory=list)
    # per model input: source channel index for each model channel (None = identity order)
    mapping: list[list[int] | None] = field(default_factory=list)
    # True when labels differ but an explicit mapping by label would resolve it
    mapping_available: bool = False
    mapping_applied: bool = False
    mapping_notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def _labels(v: object) -> list[str] | None:
    return [str(x) for x in v] if isinstance(v, list | tuple) and v else None


def _describe(labels: list[str] | None, n: int) -> str:
    if not labels:
        return f"{n} channels (positional, no labels)"
    head = ", ".join(labels[:3]) + (", …" if n > 3 else "")
    return f"{n} channels labelled {head}"


def _find_stream(want: dict[str, Any], streams: list[dict[str, Any]]) -> int | None:
    for i, s in enumerate(streams):
        if s.get("event_type") == want.get("event_type") and s.get("feature") == want.get(
            "feature"
        ):
            return i
    return None


def _check_input(
    k: int,
    want: dict[str, Any],
    streams: list[dict[str, Any]],
    allow_mapping: bool,
    c: Compatibility,
) -> None:
    where = f"input {k + 1} ({want.get('feature')})"
    idx = _find_stream(want, streams)
    if idx is None:
        avail = ", ".join(f"{s.get('event_type')}/{s.get('feature')}" for s in streams) or "none"
        c.errors.append(
            f"model expects {want.get('event_type')}/{want.get('feature')}"
            + (f" (input {k + 1})" if k else "")
            + f", pipeline produces {avail}"
        )
        if not streams:
            c.streams.append(-1)
            c.mapping.append(None)
            return
        # keep comparing against the closest stream, so every mismatch is reported at once
        idx = next(
            (i for i, s in enumerate(streams) if s.get("event_type") == want.get("event_type")),
            0,
        )
    c.streams.append(idx)
    have = streams[idx]
    if abs(float(want.get("bin_ms", 0)) - float(have.get("bin_ms") or 0)) > 1e-6:
        c.errors.append(
            f"model expects {float(want['bin_ms']):g} ms bins, pipeline produces "
            f"{float(have.get('bin_ms') or 0):g} ms"
        )
    wu, hu = want.get("unit"), have.get("unit")
    if wu and hu and wu != hu:
        c.errors.append(
            f"{where}: model expects features in {wu}, pipeline produces {hu} "
            "(BrainOS never rescales features)"
        )
    wb, hb = want.get("band_hz"), have.get("band_hz")
    if wb and hb and [float(x) for x in wb] != [float(x) for x in hb]:
        c.errors.append(
            f"{where}: model was trained on the {wb[0]:g}-{wb[1]:g} Hz band, pipeline computes "
            f"{hb[0]:g}-{hb[1]:g} Hz"
        )
    n_want, n_have = int(want.get("channel_count", 0)), int(have.get("channel_count") or 0)
    lw, lh = _labels(want.get("channel_labels")), _labels(have.get("channel_labels"))
    unique = bool(lw and lh and len(set(lw)) == len(lw) and len(set(lh)) == len(lh))
    same = lw is not None and lh is not None and lw == lh
    if same or (n_want == n_have and not (lw and lh)):
        c.mapping.append(None)
        if not lw:
            c.warnings.append(
                "model does not record channel identities; channels are assumed to be in "
                "training order"
            )
        elif not lh:
            c.warnings.append(
                f"{where}: the source does not label its channels; the model's channel order "
                "cannot be verified"
            )
        return
    # labels differ, or the counts differ
    missing = [x for x in lw or [] if x not in (lh or [])]
    mappable = unique and not missing
    if mappable:
        assert lw is not None and lh is not None
        index = [lh.index(x) for x in lw]
        c.mapping_available = True
        if allow_mapping:
            c.mapping.append(index)
            c.mapping_applied = True
            moved = sum(1 for i, j in enumerate(index) if i != j)
            dropped = n_have - n_want
            c.mapping_notes.append(
                f"{where}: channels mapped by label as enabled by the operator: "
                f"{n_want} model channels taken from {n_have} source channels "
                f"({moved} moved{f', {dropped} unused' if dropped else ''})"
            )
            return
        c.mapping.append(None)
        reason = (
            "channel labels are the same set in a different order"
            if n_want == n_have
            else f"the source has these {n_want} labels among {n_have} channels"
        )
        c.errors.append(
            f"{where}: model expects {_describe(lw, n_want)}; source provides "
            f"{_describe(lh, n_have)}. {reason}: enable explicit channel mapping by label "
            "to use it"
        )
        return
    c.mapping.append(None)
    if n_want != n_have:
        detail = ""
        if lw and lh and missing:
            detail = f"; {len(missing)} model labels are not in the source (e.g. {missing[0]})"
        elif lw and lh:
            detail = "; labels are not unique, so they cannot be mapped"
        c.errors.append(
            f"model expects {n_want} channels"
            + (f" ({_describe(lw, n_want)})" if lw else "")
            + f", source has {n_have}"
            + (f" ({_describe(lh, n_have)})" if lh else "")
            + detail
        )
    else:
        c.errors.append(
            "channel labels differ from the model's training channels (order or identity)"
            + (
                f": {len(missing)} model labels are not in the source (e.g. {missing[0]})"
                if missing
                else "; labels are not unique, so they cannot be mapped"
            )
        )


def check_manifest(
    manifest: dict[str, Any],
    *,
    streams: list[dict[str, Any]],
    stream_identity: str | None,
    stream_session: str | None = None,
    modality: str | None = None,
    preset: str | None = None,
    preset_params: dict[str, Any] | None = None,
    calibration_profile: str | None = None,
    allow_cross_source: bool = False,
    allow_channel_mapping: bool = False,
    bad_channels: list[str] | None = None,
) -> Compatibility:
    """Compare a decoder manifest with what the pipeline provides (``streams``: the feature
    streams the pipeline outputs, each ``{event_type, feature, bin_ms, channel_count,
    channel_labels, unit, band_hz}``) and the source."""
    c = Compatibility()
    for k, want in enumerate(manifest.get("inputs") or []):
        _check_input(k, want, streams, allow_channel_mapping, c)
    mods = [str(m) for m in manifest.get("modalities") or []]
    if mods and modality and modality not in mods:
        c.errors.append(
            f"model was trained on {'/'.join(mods)} recordings; this source is {modality}. "
            "Features from different recording modalities are not interchangeable (refused; "
            "no override)"
        )
    elif mods and not modality:
        c.warnings.append(
            f"model was trained on {'/'.join(mods)} recordings; this source does not declare "
            "its modality"
        )
    elif modality and not mods:
        c.warnings.append("model does not declare the recording modality of its training data")
    if bad_channels:
        used: list[str] = []
        for inp in manifest.get("inputs") or []:
            excluded = set(inp.get("excluded_channels") or [])
            labels_in = inp.get("channel_labels") or []
            used += [b for b in bad_channels if b in labels_in and b not in excluded]
        if used:
            c.warnings.append(
                f"the model uses channel(s) this source marks bad: {', '.join(dict.fromkeys(used))}"
            )
    pre = manifest.get("preprocessing") or {}
    want_preset = pre.get("preset")
    if want_preset and preset and want_preset != preset:
        c.errors.append(
            f"model was trained on features from the {want_preset} preset; the pipeline runs "
            f"{preset}"
        )
    elif want_preset and preset == want_preset:
        have_params = preset_params or {}
        for key, val in (pre.get("params") or {}).items():
            if key in have_params and have_params[key] != val:
                c.errors.append(
                    f"model was trained with {want_preset} {key}={val}; the pipeline uses "
                    f"{key}={have_params[key]}"
                )
    comp = manifest.get("compatibility") or {}
    trained_on = comp.get("source_identity")
    if comp.get("participant_specific", True):
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
    else:
        c.warnings.append(
            "the model declares itself not participant-specific (it was not calibrated on this "
            "participant)"
        )
    if stream_session and stream_session in (comp.get("sessions") or []):
        c.errors.append(
            f"stream is from the model's training session {stream_session}; decoding it would "
            "score the model on its own training data"
        )
    profile = comp.get("calibration_profile")
    if profile and calibration_profile and profile != calibration_profile:
        c.errors.append(
            f"model belongs to calibration profile {profile}; the selected profile is "
            f"{calibration_profile}"
        )
    return c


def check(
    model: Any,
    *,
    event_type: str,
    feature: str,
    bin_ms: float,
    channel_count: int,
    channel_labels: list[str] | None,
    stream_identity: str | None,
    stream_session: str | None = None,
    allow_cross_source: bool = False,
    unit: str | None = None,
    stream_modality: str | None = None,
    stream_bad_channels: list[str] | None = None,
    allow_channel_mapping: bool = False,
) -> Compatibility:
    """Single-stream form of :func:`check_manifest` for a built-in JSON model."""
    stream = {
        "event_type": event_type,
        "feature": feature,
        "bin_ms": bin_ms,
        "channel_count": channel_count,
        "channel_labels": channel_labels,
        "unit": unit,
    }
    man = manifest_for(model)
    if model_input(model).get("inferred"):
        man = {**man, "inputs": [{**man["inputs"][0], "inferred": True}]}
    return check_manifest(
        man,
        streams=[stream],
        stream_identity=stream_identity,
        stream_session=stream_session,
        modality=stream_modality,
        allow_cross_source=allow_cross_source,
        allow_channel_mapping=allow_channel_mapping,
        bad_channels=stream_bad_channels,
    )


def list_models(models_dir: Path) -> list[Any]:
    """Built-in JSON models in ``models_dir`` (decoder manifests are listed by the registry)."""
    out: list[Any] = []
    if models_dir.exists():
        for p in sorted(models_dir.glob("*.json")):
            if p.name.endswith(".manifest.json") or p.name.startswith("_"):
                continue
            try:
                out.append(load_model(p))
            except (ValueError, TypeError, KeyError, OSError) as exc:
                log.warning("ignoring model %s: %s", p.name, exc)
    return out


def summary(model: Any) -> dict[str, Any]:
    ev = model.evaluations[-1] if model.evaluations else {}
    classes = output_classes(model)
    kind = output_kind(model)
    extra: dict[str, Any] = {}
    if kind == "classes":
        extra = {
            "held_out_balanced_accuracy": ev.get("balanced_accuracy"),
            "held_out_accuracy": ev.get("accuracy"),
            "chance_balanced_accuracy": ev.get("chance_balanced_accuracy"),
        }
    elif kind == "event":
        extra = {
            "held_out_event_precision": ev.get("event_precision"),
            "held_out_event_recall": ev.get("event_recall"),
        }
    outputs: dict[str, Any]
    if kind == "classes":
        outputs = {"type": "classes", "classes": classes}
    elif kind == "event":
        outputs = {"type": "event", "events": classes}
    else:
        outputs = {"type": "continuous"}
    return {
        **extra,
        "outputs": outputs,
        "model_id": model.model_id,
        "schema": model.schema,
        "version": model.version,
        "created_at": model.created_at,
        "method": model.method,
        "space": model.space,
        "dims": model.dims,
        "unit": model.unit,
        "quantity": model.quantity,
        "input": model_input(model),
        "inputs": model_inputs(model),
        "source_identity": model_source(model),
        "modality": model_modality(model),
        "trained_on": model.training.get("file") or model.training.get("recording"),
        "training_session": model.training.get("session"),
        "held_out_r2": ev.get("r2"),
        "held_out_samples": ev.get("samples"),
        "control_mean_predictor_r2": ev.get("control_mean_predictor_r2"),
        "family": family_of(model).name,
        "origin": "brainos-trained",
        "execution": "in_process",
    }
