"""Model manifests: validation, JSON (de)serialization, and output validation.

Pure (no I/O apart from :func:`read_manifest`, no Concord import). Used by the decoder host
before anything leaves the decoder process, again by Concord on receipt, and by
``concord-decoder check``. Findings are :class:`Problem` objects (shared with the adapter
SDK): ``error`` rejects the manifest / output, ``warning`` is shown to the operator.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np
from concord_adapter_sdk.validate import (
    API_VERSION_PATTERN,
    SEMVER_PATTERN,
    Problem,
    errors,
    has_errors,
    summarize,
)

from concord_decoder_sdk.api import (
    API_VERSION,
    BINNED_FEATURES,
    FEATURE_EVENTS,
    MANIFEST_SCHEMA,
    MODEL_ID_PATTERN,
    Artifact,
    CalibrationSpec,
    Confidence,
    FloatArray,
    InputSpec,
    Modality,
    ModelManifest,
    ModelProvenance,
    OutputKind,
    OutputSpec,
    ParticipantCompat,
    Preprocessing,
)

__all__ = [
    "FORMATS",
    "UNSAFE_FORMATS",
    "ManifestError",
    "OutputValidator",
    "Problem",
    "api_compatible",
    "errors",
    "has_errors",
    "manifest_from_dict",
    "manifest_to_dict",
    "read_manifest",
    "summarize",
    "validate_manifest",
]

FAMILY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.\-]{0,47}$")
DIM_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,31}$")
FEATURE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]{0,47}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
FILE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.\-]{0,127}$")
FORMATS = frozenset(
    {"onnx", "skops", "torchscript", "safetensors", "concord-json", "pickle", "joblib"}
)
# formats whose loading executes code from the file: refused unless explicitly trusted
UNSAFE_FORMATS = frozenset({"pickle", "joblib"})
MAX_INPUTS = 8
MAX_CHANNELS = 4096
MAX_INPUT_WIDTH = 16384
MAX_DIMS = 64
MAX_TEXT = 500
PROB_TOL = 1e-6
SUM_TOL = 1e-3


class ManifestError(ValueError):
    """A manifest could not be parsed (shape errors; content rules are Problems)."""


def api_compatible(model_api: str, host_api: str = API_VERSION) -> tuple[bool, str]:
    """A decoder written for API ``M.m`` runs on a host with API ``M.n`` where ``m <= n``."""
    m = API_VERSION_PATTERN.match(model_api) if isinstance(model_api, str) else None
    h = API_VERSION_PATTERN.match(host_api)
    if m is None:
        return False, f"api_version {model_api!r} is not 'major.minor'"
    assert h is not None
    if m.group(1) != h.group(1):
        return False, (
            f"written for decoder SDK API {model_api}; this Concord supports API {host_api} "
            "(major versions differ)"
        )
    if int(m.group(2)) > int(h.group(2)):
        return False, (
            f"written for decoder SDK API {model_api}, newer than this Concord ({host_api}); "
            "update Concord"
        )
    return True, f"compatible with API {host_api}"


# ----------------------------------------------------------------------------- validation


def _err(out: list[Problem], code: str, message: str, where: str = "") -> None:
    out.append(Problem(code, message, "error", where))


def _warn(out: list[Problem], code: str, message: str, where: str = "") -> None:
    out.append(Problem(code, message, "warning", where))


def _text(out: list[Problem], value: object, code: str, where: str, *, required: bool) -> None:
    if not isinstance(value, str):
        _err(out, code, f"must be a string, got {type(value).__name__}", where)
    elif required and not value.strip():
        _err(out, code, "must not be empty", where)
    elif len(value) > MAX_TEXT:
        _err(out, code, f"is {len(value)} characters long (max {MAX_TEXT})", where)


def _finite(x: object) -> bool:
    return isinstance(x, int | float) and not isinstance(x, bool) and math.isfinite(x)


def _validate_input(i: int, spec: object, out: list[Problem]) -> None:
    w = f"inputs[{i}]"
    if not isinstance(spec, InputSpec):
        _err(out, "input.type", "must be an InputSpec", w)
        return
    if spec.event_type not in FEATURE_EVENTS:
        _err(out, "input.event_type", f"{spec.event_type!r} is not one of {FEATURE_EVENTS}", w)
    if not isinstance(spec.feature, str) or not FEATURE_PATTERN.match(spec.feature):
        _err(out, "input.feature", f"feature {spec.feature!r} is not a feature name", w)
    elif spec.event_type == "features.binned" and spec.feature not in BINNED_FEATURES:
        _err(
            out,
            "input.feature",
            f"features.binned carries {sorted(BINNED_FEATURES)}, not {spec.feature!r}",
            w,
        )
    if not _finite(spec.bin_ms) or not 0 < float(spec.bin_ms) <= 10_000:
        _err(out, "input.bin_ms", f"bin_ms must be in (0, 10000], got {spec.bin_ms!r}", w)
    n = spec.channel_count
    if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= MAX_CHANNELS:
        _err(out, "input.channel_count", f"must be an int in [1, {MAX_CHANNELS}], got {n!r}", w)
        return
    labels = spec.channel_labels
    if labels is not None:
        if not isinstance(labels, tuple) or not all(
            isinstance(x, str) and 0 < len(x) <= 64 for x in labels
        ):
            _err(out, "input.labels", "channel_labels must be a tuple of 1-64 char strings", w)
        elif len(labels) != n:
            _err(
                out,
                "input.labels",
                f"{len(labels)} channel labels for {n} channels",
                w,
            )
        elif len(set(labels)) != len(labels):
            _warn(
                out,
                "input.labels.duplicate",
                "channel labels are not unique: Concord can check order only by position and "
                "cannot offer mapping by label",
                w,
            )
    if spec.unit is not None and (not isinstance(spec.unit, str) or not 0 < len(spec.unit) <= 32):
        _err(out, "input.unit", "unit must be None or a 1-32 character string", w)
    if spec.band_hz is not None and (
        not isinstance(spec.band_hz, tuple)
        or len(spec.band_hz) != 2
        or not all(_finite(x) for x in spec.band_hz)
        or not 0 <= spec.band_hz[0] < spec.band_hz[1]
    ):
        _err(
            out, "input.band_hz", f"band_hz must be (low, high) with low < high: {spec.band_hz}", w
        )


def _validate_output(o: object, out: list[Problem]) -> None:
    w = "output"
    if not isinstance(o, OutputSpec):
        _err(out, "output.type", "must be an OutputSpec", w)
        return
    if not isinstance(o.kind, OutputKind):
        _err(out, "output.kind", f"unknown output kind {o.kind!r}", w)
    dims = o.dims
    if not isinstance(dims, tuple) or not 1 <= len(dims) <= MAX_DIMS:
        _err(out, "output.dims", f"1-{MAX_DIMS} dims required", w)
        return
    bad = [d for d in dims if not isinstance(d, str) or not DIM_PATTERN.match(d)]
    if bad:
        _err(out, "output.dims", f"dim names must be 1-32 chars [A-Za-z0-9_.-]: {bad}", w)
    if len(set(dims)) != len(dims):
        _err(out, "output.dims", f"dim names must be unique: {list(dims)}", w)
    if o.kind is OutputKind.CLASSES and len(dims) < 2:
        _err(out, "output.classes", "a classifier needs at least two classes", w)
    for key, val in (("quantity", o.quantity), ("unit", o.unit), ("space", o.space)):
        if not isinstance(val, str) or not 0 < len(val) <= 64:
            _err(out, f"output.{key}", f"{key} must be a 1-64 character string", w)
    if o.kind in (OutputKind.CLASSES, OutputKind.EVENT) and o.unit != "probability":
        _err(out, "output.unit", f"{o.kind} outputs are probabilities (unit 'probability')", w)
    if o.y_axis not in (None, "up", "down"):
        _err(out, "output.y_axis", f"y_axis must be 'up', 'down' or None, got {o.y_axis!r}", w)
    if o.scale is not None:
        if o.kind is not OutputKind.CONTINUOUS:
            _err(out, "output.scale", "scale applies to continuous outputs only", w)
        elif len(o.scale) != len(dims) or not all(_finite(s) and s > 0 for s in o.scale):
            _err(out, "output.scale", "scale needs one positive finite value per dim", w)


def validate_manifest(m: object) -> list[Problem]:
    out: list[Problem] = []
    if not isinstance(m, ModelManifest):
        _err(out, "manifest.type", f"expected a ModelManifest, got {type(m).__name__}")
        return out
    if not isinstance(m.model_id, str) or not MODEL_ID_PATTERN.match(m.model_id):
        _err(
            out,
            "manifest.model_id",
            f"model_id {m.model_id!r}: 1-96 chars [A-Za-z0-9_.:-], starting alphanumeric",
            "model_id",
        )
    _text(out, m.name, "manifest.name", "name", required=True)
    if isinstance(m.name, str) and len(m.name) > 96:
        _err(out, "manifest.name", "name is longer than 96 characters", "name")
    if not isinstance(m.version, str) or not SEMVER_PATTERN.match(m.version):
        _err(out, "manifest.version", f"version {m.version!r} is not semantic", "version")
    ok, why = api_compatible(m.api_version)
    if not ok:
        _err(out, "manifest.api_version", why, "api_version")
    if not isinstance(m.family, str) or not FAMILY_PATTERN.match(m.family):
        _err(out, "manifest.family", f"family {m.family!r}: lower-case [a-z0-9_.-]", "family")
    _text(out, m.description, "manifest.description", "description", required=True)
    _text(out, m.author, "manifest.author", "author", required=True)
    _text(out, m.license, "manifest.license", "license", required=True)
    if (
        not isinstance(m.modalities, frozenset)
        or not m.modalities
        or not all(isinstance(x, Modality) for x in m.modalities)
    ):
        _err(
            out,
            "manifest.modalities",
            "declare the modalities the model may run on (non-empty set of Modality)",
            "modalities",
        )
    if not isinstance(m.inputs, tuple) or not 1 <= len(m.inputs) <= MAX_INPUTS:
        _err(out, "manifest.inputs", f"1-{MAX_INPUTS} inputs required", "inputs")
    else:
        for i, spec in enumerate(m.inputs):
            _validate_input(i, spec, out)
        keys = [(s.event_type, s.feature) for s in m.inputs if isinstance(s, InputSpec)]
        if len(set(keys)) != len(keys):
            _err(out, "manifest.inputs", "two inputs with the same event type and feature")
        bins = {float(s.bin_ms) for s in m.inputs if isinstance(s, InputSpec)}
        if len(bins) > 1:
            _err(out, "manifest.inputs", f"all inputs must share one bin size, got {bins}")
        width = sum(
            s.channel_count
            for s in m.inputs
            if isinstance(s, InputSpec) and isinstance(s.channel_count, int)
        )
        if width > MAX_INPUT_WIDTH:
            _err(out, "manifest.inputs", f"{width} input features (max {MAX_INPUT_WIDTH})")
    _validate_output(m.output, out)
    if not isinstance(m.confidence, Confidence):
        _err(out, "manifest.confidence", f"unknown confidence {m.confidence!r}", "confidence")
    elif isinstance(m.output, OutputSpec):
        probs = m.output.kind in (OutputKind.CLASSES, OutputKind.EVENT)
        if m.confidence is Confidence.POSTERIOR and not probs:
            _err(out, "manifest.confidence", "posterior confidence needs classes or event output")
        if m.confidence in (Confidence.VARIANCE, Confidence.COVARIANCE) and probs:
            _err(out, "manifest.confidence", f"{m.confidence} needs a continuous output")
    c = m.compatibility
    if not isinstance(c, ParticipantCompat):
        _err(out, "manifest.compatibility", "must be a ParticipantCompat", "compatibility")
    else:
        if c.participant_specific and not c.source_identity:
            _warn(
                out,
                "compatibility.source_unknown",
                "participant-specific model without source_identity: Concord will require the "
                "operator's cross-source override to run it",
                "compatibility",
            )
        if not all(isinstance(s, str) and s for s in c.sessions):
            _err(out, "compatibility.sessions", "sessions must be non-empty strings")
    if not isinstance(m.preprocessing, Preprocessing):
        _err(out, "manifest.preprocessing", "must be a Preprocessing", "preprocessing")
    elif not all(
        isinstance(v, str | int | float | bool) and (not isinstance(v, float) or math.isfinite(v))
        for v in m.preprocessing.params.values()
    ):
        _err(out, "preprocessing.params", "parameters must be finite scalars", "preprocessing")
    a = m.artifact
    if a is not None:
        if not isinstance(a, Artifact):
            _err(out, "manifest.artifact", "must be an Artifact", "artifact")
        else:
            if a.format not in FORMATS:
                _err(out, "artifact.format", f"unknown format {a.format!r}", "artifact")
            if not isinstance(a.file, str) or not FILE_PATTERN.match(a.file) or ".." in a.file:
                _err(out, "artifact.file", f"file {a.file!r} must be a plain file name", "artifact")
            if not isinstance(a.sha256, str) or not SHA256_PATTERN.match(a.sha256):
                _err(out, "artifact.sha256", "sha256 must be 64 lower-case hex digits", "artifact")
            if a.format in UNSAFE_FORMATS:
                _warn(
                    out,
                    "artifact.unsafe_format",
                    f"{a.format} files run code when loaded; Concord refuses them unless the "
                    "operator marks this exact file trusted. Prefer skops, ONNX or safetensors.",
                    "artifact",
                )
    return out


# ----------------------------------------------------------------------------- JSON


def _tuple_or_none(v: object) -> tuple[Any, ...] | None:
    return None if v is None else tuple(v) if isinstance(v, list | tuple) else (v,)


def manifest_to_dict(m: ModelManifest) -> dict[str, Any]:
    def inp(s: InputSpec) -> dict[str, Any]:
        return {
            "event_type": s.event_type,
            "feature": s.feature,
            "bin_ms": float(s.bin_ms),
            "channel_count": s.channel_count,
            "channel_labels": list(s.channel_labels) if s.channel_labels is not None else None,
            "unit": s.unit,
            "band_hz": list(s.band_hz) if s.band_hz is not None else None,
        }

    o = m.output
    return {
        "schema": MANIFEST_SCHEMA,
        "model_id": m.model_id,
        "name": m.name,
        "version": m.version,
        "api_version": m.api_version,
        "family": m.family,
        "description": m.description,
        "author": m.author,
        "license": m.license,
        "modalities": sorted(str(x) for x in m.modalities),
        "inputs": [inp(s) for s in m.inputs],
        "output": {
            "kind": str(o.kind),
            "quantity": o.quantity,
            "dims": list(o.dims),
            "unit": o.unit,
            "space": o.space,
            "scale": list(o.scale) if o.scale is not None else None,
            "y_axis": o.y_axis,
        },
        "confidence": str(m.confidence),
        "preprocessing": {
            "preset": m.preprocessing.preset,
            "params": dict(m.preprocessing.params),
            "description": m.preprocessing.description,
        },
        "compatibility": {
            "participant_specific": m.compatibility.participant_specific,
            "source_identity": m.compatibility.source_identity,
            "sessions": list(m.compatibility.sessions),
            "calibration_profile": m.compatibility.calibration_profile,
        },
        "calibration": {
            "required": m.calibration.required,
            "task": m.calibration.task,
            "label_quantity": m.calibration.label_quantity,
            "label_dims": list(m.calibration.label_dims),
            "min_labelled_bins": m.calibration.min_labelled_bins,
        },
        "provenance": {
            "training_data_sha256": list(m.provenance.training_data_sha256),
            "code_version": m.provenance.code_version,
            "created_at": m.provenance.created_at,
            "trained_by": m.provenance.trained_by,
            "notes": m.provenance.notes,
        },
        "artifact": None
        if m.artifact is None
        else {
            "format": m.artifact.format,
            "file": m.artifact.file,
            "sha256": m.artifact.sha256,
            "io": dict(m.artifact.io),
        },
    }


def _obj(d: Mapping[str, Any], key: str, *, required: bool = True) -> dict[str, Any]:
    v = d.get(key)
    if v is None and not required:
        return {}
    if not isinstance(v, dict):
        raise ManifestError(f"'{key}' must be an object")
    return v


def _req(d: Mapping[str, Any], key: str) -> Any:
    if key not in d:
        raise ManifestError(f"missing field '{key}'")
    return d[key]


def manifest_from_dict(d: Mapping[str, Any]) -> ModelManifest:
    """Parse a manifest. Raises :class:`ManifestError` on structural problems; content
    rules are left to :func:`validate_manifest`."""
    if not isinstance(d, Mapping):
        raise ManifestError("a manifest must be a JSON object")
    if d.get("schema", MANIFEST_SCHEMA) != MANIFEST_SCHEMA:
        raise ManifestError(f"unsupported manifest schema {d.get('schema')!r}")
    try:
        inputs = []
        for s in _req(d, "inputs"):
            if not isinstance(s, dict):
                raise ManifestError("each input must be an object")
            labels = s.get("channel_labels")
            band = s.get("band_hz")
            inputs.append(
                InputSpec(
                    event_type=str(_req(s, "event_type")),
                    feature=str(_req(s, "feature")),
                    bin_ms=float(_req(s, "bin_ms")),
                    channel_count=_req(s, "channel_count"),
                    channel_labels=None if labels is None else tuple(str(x) for x in labels),
                    unit=s.get("unit"),
                    band_hz=None if band is None else (float(band[0]), float(band[1])),
                )
            )
        o = _obj(d, "output")
        scale = o.get("scale")
        mods = _req(d, "modalities")
        if not isinstance(mods, list):
            raise ManifestError("'modalities' must be a list")
        unknown = [x for x in mods if x not in Modality._value2member_map_]
        if unknown:
            raise ManifestError(f"unknown modalities {unknown}")
        kind = str(_req(o, "kind"))
        if kind not in OutputKind._value2member_map_:
            raise ManifestError(f"unknown output kind {kind!r}")
        conf = str(d.get("confidence", "none"))
        if conf not in Confidence._value2member_map_:
            raise ManifestError(f"unknown confidence {conf!r}")
        pre = _obj(d, "preprocessing", required=False)
        comp = _obj(d, "compatibility", required=False)
        cal = _obj(d, "calibration", required=False)
        prov = _obj(d, "provenance", required=False)
        art = d.get("artifact")
        if art is not None and not isinstance(art, dict):
            raise ManifestError("'artifact' must be an object or null")
        return ModelManifest(
            model_id=str(_req(d, "model_id")),
            name=str(_req(d, "name")),
            version=str(_req(d, "version")),
            api_version=str(_req(d, "api_version")),
            family=str(_req(d, "family")),
            description=str(d.get("description", "")),
            author=str(d.get("author", "")),
            license=str(d.get("license", "")),
            modalities=frozenset(Modality(x) for x in mods),
            inputs=tuple(inputs),
            output=OutputSpec(
                kind=OutputKind(kind),
                quantity=str(_req(o, "quantity")),
                dims=tuple(str(x) for x in _req(o, "dims")),
                unit=str(_req(o, "unit")),
                space=str(_req(o, "space")),
                scale=None if scale is None else tuple(float(x) for x in scale),
                y_axis=o.get("y_axis"),
            ),
            confidence=Confidence(conf),
            preprocessing=Preprocessing(
                preset=pre.get("preset"),
                params=dict(pre.get("params") or {}),
                description=str(pre.get("description", "")),
            ),
            compatibility=ParticipantCompat(
                participant_specific=bool(comp.get("participant_specific", True)),
                source_identity=comp.get("source_identity"),
                sessions=tuple(str(x) for x in comp.get("sessions") or ()),
                calibration_profile=comp.get("calibration_profile"),
            ),
            calibration=CalibrationSpec(
                required=bool(cal.get("required", True)),
                task=str(cal.get("task", "")),
                label_quantity=cal.get("label_quantity"),
                label_dims=tuple(str(x) for x in cal.get("label_dims") or ()),
                min_labelled_bins=int(cal.get("min_labelled_bins", 0)),
            ),
            provenance=ModelProvenance(
                training_data_sha256=tuple(str(x) for x in prov.get("training_data_sha256") or ()),
                code_version=str(prov.get("code_version", "")),
                created_at=str(prov.get("created_at", "")),
                trained_by=str(prov.get("trained_by", "")),
                notes=str(prov.get("notes", "")),
            ),
            artifact=None
            if art is None
            else Artifact(
                format=str(_req(art, "format")),
                file=str(_req(art, "file")),
                sha256=str(_req(art, "sha256")),
                io=dict(art.get("io") or {}),
            ),
        )
    except ManifestError:
        raise
    except (TypeError, ValueError, KeyError, IndexError) as exc:
        raise ManifestError(f"malformed manifest: {exc}") from None


def read_manifest(path: Path) -> ModelManifest:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ManifestError(f"{path.name}: cannot read manifest: {exc}") from None
    return manifest_from_dict(data)


# ----------------------------------------------------------------------------- outputs


class OutputValidator:
    """Checks every decoder output against the manifest (host side and runtime side)."""

    def __init__(self, manifest: ModelManifest) -> None:
        self.kind = manifest.output.kind
        self.dims = len(manifest.output.dims)
        self.confidence = manifest.confidence

    def check(self, values: object, confidence: object = None) -> list[Problem]:
        out: list[Problem] = []
        v = np.asarray(values) if isinstance(values, np.ndarray | list | tuple) else None
        if v is None or v.dtype.kind not in "fiu":
            _err(out, "output.values.type", f"values must be a numeric array, got {type(values)}")
            return out
        if v.shape != (self.dims,):
            _err(
                out, "output.values.shape", f"values have shape {v.shape}, expected ({self.dims},)"
            )
            return out
        v = v.astype(np.float64)
        if not np.all(np.isfinite(v)):
            _err(out, "output.values.finite", "values contain NaN or infinity")
            return out
        if self.kind in (OutputKind.CLASSES, OutputKind.EVENT) and (
            np.any(v < -PROB_TOL) or np.any(v > 1 + PROB_TOL)
        ):
            _err(out, "output.values.probability", f"probabilities outside [0, 1]: {v.tolist()}")
        if self.kind is OutputKind.CLASSES and abs(float(v.sum()) - 1.0) > SUM_TOL:
            _err(out, "output.values.sum", f"class posteriors sum to {float(v.sum()):.6f}, not 1")
        self._check_confidence(confidence, out)
        return out

    def _check_confidence(self, confidence: object, out: list[Problem]) -> None:
        want = self.confidence
        if want in (Confidence.NONE, Confidence.POSTERIOR):
            if confidence is not None:
                _err(out, "output.confidence", f"confidence '{want}' reports no confidence array")
            return
        if confidence is None:
            _err(out, "output.confidence.missing", f"manifest declares '{want}' confidence")
            return
        c = np.asarray(confidence, dtype=np.float64)
        shape = (self.dims,) if want is Confidence.VARIANCE else (self.dims, self.dims)
        if c.shape != shape:
            _err(out, "output.confidence.shape", f"confidence shape {c.shape}, expected {shape}")
            return
        if not np.all(np.isfinite(c)):
            _err(out, "output.confidence.finite", "confidence contains NaN or infinity")
            return
        diag = c if want is Confidence.VARIANCE else np.diag(c)
        if np.any(diag < 0):
            _err(out, "output.confidence.negative", "variances must be non-negative")
        if want is Confidence.COVARIANCE:
            scale = max(1.0, float(np.max(np.abs(c))))
            if not np.allclose(c, c.T, atol=1e-9 * scale, rtol=1e-6):
                _err(out, "output.confidence.symmetric", "covariance must be symmetric")

    def check_batch(
        self, values: FloatArray, confidence: FloatArray | None
    ) -> tuple[int, list[Problem]]:
        """Check (n, dims) values (+ (n, ...) confidence). Returns (first bad row, problems);
        row -1 if all rows pass."""
        for i in range(values.shape[0]):
            conf = None if confidence is None else confidence[i]
            problems = self.check(values[i], conf)
            if has_errors(problems):
                return i, problems
        return -1, []


def check_inputs_unique(specs: Sequence[InputSpec]) -> bool:
    """True if every input declares unique channel labels (mapping by label is possible)."""
    return all(
        s.channel_labels is not None and len(set(s.channel_labels)) == len(s.channel_labels)
        for s in specs
    )
