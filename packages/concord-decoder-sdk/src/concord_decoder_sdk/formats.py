"""Loaders for model files, with the trust policy (runs inside the decoder host process).

=============== ============================================ ===========================
format          loader                                       code execution on load
=============== ============================================ ===========================
``onnx``        onnxruntime ``InferenceSession`` (CPU)       none (graph of standard ops;
                                                             no custom-op libraries)
``skops``       ``skops.io.load`` with skops' type allow-     none for trusted types;
                list; unknown types refused unless trusted    refused otherwise
``safetensors`` ``safetensors.torch.load_file`` into a       none (tensors only)
                built-in architecture (``linear``, ``gru``)
``torchscript`` ``torch.jit.load`` (TorchScript IR,          TorchScript only (a
                ``map_location="cpu"``)                       restricted language, not
                                                             arbitrary Python)
``pickle`` /    ``pickle.load`` / ``joblib.load``            ARBITRARY CODE: refused
``joblib``                                                   unless the operator marked
                                                             this exact file trusted
=============== ============================================ ===========================

Every artifact's SHA-256 must match the manifest before anything is parsed; a trust decision
names that hash, so a modified file is never covered by an earlier decision.

Declared I/O (``artifact.io``) is checked against the file before inference:

* ONNX: ``{"input": {"name", "shape"}, "output": {"name", "shape"}, "state": [{"input",
  "output", "shape"}], "history_bins": k}``; names must exist, shapes must agree (a symbolic
  or -1 dimension is a wildcard), the feature width must equal the manifest's inputs.
* skops / pickle / joblib (scikit-learn estimators): ``{"method": "predict" |
  "predict_proba", "class_labels": [...], "history_bins": k}``; ``n_features_in_`` must equal
  the input width (x history), ``classes_`` must contain the declared labels.
* TorchScript: ``{"state_shape": [...] | null, "history_bins": k}``: ``forward(x)`` or, with
  state, ``forward(x, h) -> (y, h)``.
* safetensors: ``{"architecture": "linear" | "gru", "hidden_size": n}``; the state_dict must
  match the architecture exactly (``strict=True``).

``history_bins`` (default 1) gives a stateless model the last k bins, oldest first,
concatenated: a causal temporal context without recurrent state.
"""

from __future__ import annotations

import hashlib
import importlib
from collections import deque
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from concord_decoder_sdk.api import (
    DecodeOutput,
    Decoder,
    FloatArray,
    ModelLoadError,
    ModelManifest,
    OutputKind,
    UntrustedModelError,
    check_features,
)
from concord_decoder_sdk.manifest import UNSAFE_FORMATS

MAX_HISTORY = 64


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while b := fh.read(1 << 20):
            h.update(b)
    return h.hexdigest()


def _optional(module: str, extra: str) -> Any:
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        raise ModelLoadError(
            f"{module} is not installed; pip install 'concord-decoder-sdk[{extra}]' ({exc})"
        ) from None


def artifact_path(manifest: ModelManifest, manifest_dir: Path) -> Path:
    a = manifest.artifact
    if a is None:
        raise ModelLoadError(f"{manifest.model_id}: the manifest names no model file")
    path = manifest_dir / a.file
    if path.parent.resolve() != manifest_dir.resolve():
        raise ModelLoadError(f"{a.file!r} is not a file next to the manifest")
    if not path.is_file():
        raise ModelLoadError(f"model file {a.file} not found next to the manifest")
    return path


def verify_artifact(manifest: ModelManifest, manifest_dir: Path) -> Path:
    """The artifact's path, after checking its SHA-256 against the manifest."""
    path = artifact_path(manifest, manifest_dir)
    assert manifest.artifact is not None
    actual = sha256_file(path)
    if actual != manifest.artifact.sha256:
        raise ModelLoadError(
            f"{path.name} changed since its manifest was written (SHA-256 {actual[:12]}…, "
            f"manifest says {manifest.artifact.sha256[:12]}…); refusing to load it"
        )
    return path


def _history(io: Mapping[str, Any]) -> int:
    k = io.get("history_bins", 1)
    if isinstance(k, bool) or not isinstance(k, int) or not 1 <= k <= MAX_HISTORY:
        raise ModelLoadError(f"history_bins must be an int in [1, {MAX_HISTORY}], got {k!r}")
    return k


class _History:
    """Last k feature vectors, oldest first, zeros before the first bin (causal)."""

    def __init__(self, width: int, k: int) -> None:
        self.width, self.k = width, k
        self._buf: deque[FloatArray] = deque(maxlen=k)
        self.reset()

    def reset(self) -> None:
        self._buf.clear()
        for _ in range(self.k):
            self._buf.append(np.zeros(self.width))

    def push(self, x: FloatArray) -> FloatArray:
        self._buf.append(x)
        return np.concatenate(list(self._buf)) if self.k > 1 else x


def _shape_ok(declared: Sequence[Any], actual: Sequence[Any]) -> bool:
    if len(declared) != len(actual):
        return False
    for d, a in zip(declared, actual, strict=True):
        wild = isinstance(d, str) or d in (None, -1) or isinstance(a, str) or a is None
        if not wild and int(d) != int(a):
            return False
    return True


def _decl(io: Mapping[str, Any], key: str) -> dict[str, Any]:
    v = io.get(key)
    if not isinstance(v, dict) or not isinstance(v.get("name"), str):
        raise ModelLoadError(f"artifact.io.{key} must declare a tensor name and shape")
    shape = v.get("shape")
    if not isinstance(shape, list):
        raise ModelLoadError(f"artifact.io.{key}.shape must be a list")
    return v


# ----------------------------------------------------------------------------- ONNX


class OnnxDecoder(Decoder):
    """A model exported to ONNX; recurrent state, if declared, is carried between steps."""

    def __init__(self, manifest: ModelManifest, path: Path) -> None:
        self.manifest = manifest
        self.path = path
        self._session: Any = None
        io = manifest.artifact.io if manifest.artifact else {}
        self._io = io
        self._hist = _History(manifest.input_width, _history(io))
        self._state: dict[str, FloatArray] = {}
        self._state_map: list[tuple[str, str, list[int]]] = []

    def load(self) -> None:
        ort = _optional("onnxruntime", "onnx")
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = 1
        opts.inter_op_num_threads = 1
        try:
            sess = ort.InferenceSession(
                str(self.path), sess_options=opts, providers=["CPUExecutionProvider"]
            )
        except Exception as exc:  # onnxruntime raises its own exception types
            raise ModelLoadError(f"onnxruntime cannot load {self.path.name}: {exc}") from None
        inp, out = _decl(self._io, "input"), _decl(self._io, "output")
        have_in = {i.name: i for i in sess.get_inputs()}
        have_out = {o.name: o for o in sess.get_outputs()}
        state = self._io.get("state") or []
        if not isinstance(state, list):
            raise ModelLoadError("artifact.io.state must be a list")
        want_in = {inp["name"], *(str(s.get("input")) for s in state)}
        want_out = {out["name"], *(str(s.get("output")) for s in state)}
        if set(have_in) != want_in:
            raise ModelLoadError(
                f"ONNX inputs are {sorted(have_in)}; the manifest declares {sorted(want_in)}"
            )
        missing = want_out - set(have_out)
        if missing:
            raise ModelLoadError(f"ONNX outputs {sorted(have_out)} lack declared {sorted(missing)}")
        width = self.manifest.input_width * self._hist.k
        if not _shape_ok(inp["shape"], [1, width]):
            raise ModelLoadError(
                f"declared input shape {inp['shape']} does not take one bin of {width} features"
            )
        if not _shape_ok(have_in[inp["name"]].shape, inp["shape"]):
            raise ModelLoadError(
                f"ONNX input {inp['name']!r} has shape {have_in[inp['name']].shape}; the "
                f"manifest declares {inp['shape']}"
            )
        dims = len(self.manifest.output.dims)
        if not _shape_ok(out["shape"], [1, dims]):
            raise ModelLoadError(f"declared output shape {out['shape']} is not [1, {dims}]")
        if not _shape_ok(have_out[out["name"]].shape, out["shape"]):
            raise ModelLoadError(
                f"ONNX output {out['name']!r} has shape {have_out[out['name']].shape}; the "
                f"manifest declares {out['shape']}"
            )
        for node in (*sess.get_inputs(), *sess.get_outputs()):
            if node.type not in ("tensor(float)", "tensor(double)"):
                raise ModelLoadError(f"ONNX tensor {node.name!r} is {node.type}; expected float")
        self._dtype = np.float64 if have_in[inp["name"]].type == "tensor(double)" else np.float32
        self._state_map = []
        for s in state:
            shape = s.get("shape")
            if not isinstance(shape, list) or not all(isinstance(x, int) and x > 0 for x in shape):
                raise ModelLoadError("each state needs a concrete shape (positive ints)")
            if not _shape_ok(have_in[str(s["input"])].shape, shape):
                raise ModelLoadError(f"state input {s['input']!r} shape differs from {shape}")
            self._state_map.append((str(s["input"]), str(s["output"]), shape))
        self._in_name, self._out_name = str(inp["name"]), str(out["name"])
        self._session = sess
        self.reset()

    def reset(self) -> None:
        self._hist.reset()
        self._state = {
            i: np.zeros(shape, dtype=getattr(self, "_dtype", np.float32))
            for i, _, shape in self._state_map
        }

    def step(self, features: FloatArray, timestamp_s: float) -> DecodeOutput:
        x = self._hist.push(check_features(self.manifest, features))
        feeds: dict[str, Any] = {self._in_name: x[None, :].astype(self._dtype)}
        feeds.update(self._state)
        names = [self._out_name, *(o for _, o, _ in self._state_map)]
        res = self._session.run(names, feeds)
        for (i, _, _), val in zip(self._state_map, res[1:], strict=True):
            self._state[i] = val
        return DecodeOutput(np.asarray(res[0], dtype=np.float64).reshape(-1))

    def close(self) -> None:
        self._session = None


# ----------------------------------------------------------------------------- scikit-learn


def _estimator_io(manifest: ModelManifest, est: Any) -> tuple[str, list[int] | None, int]:
    io = manifest.artifact.io if manifest.artifact else {}
    k = _history(io)
    method = io.get("method", "predict")
    if method not in ("predict", "predict_proba"):
        raise ModelLoadError(f"artifact.io.method must be predict or predict_proba: {method!r}")
    if not callable(getattr(est, method, None)):
        raise ModelLoadError(f"the estimator ({type(est).__name__}) has no {method}()")
    width = manifest.input_width * k
    n_in = getattr(est, "n_features_in_", None)
    if n_in is not None and int(n_in) != width:
        raise ModelLoadError(
            f"the estimator was fitted on {n_in} features; the manifest declares {width} "
            f"({manifest.input_width} per bin x {k} bins)"
        )
    kind = manifest.output.kind
    index: list[int] | None = None
    if method == "predict_proba":
        if kind is OutputKind.CONTINUOUS:
            raise ModelLoadError("predict_proba gives probabilities; declare classes or event")
        labels = io.get("class_labels")
        classes = [c.item() if hasattr(c, "item") else c for c in getattr(est, "classes_", [])]
        if not isinstance(labels, list) or not labels:
            raise ModelLoadError("predict_proba needs artifact.io.class_labels (one per dim)")
        if len(labels) != len(manifest.output.dims):
            raise ModelLoadError(
                f"{len(labels)} class_labels for {len(manifest.output.dims)} output dims"
            )
        missing = [x for x in labels if x not in classes]
        if missing:
            raise ModelLoadError(f"estimator classes {classes} lack declared labels {missing}")
        if kind is OutputKind.CLASSES and len(labels) != len(classes):
            raise ModelLoadError(
                f"a classes output must cover every estimator class {classes}; got {labels}"
            )
        index = [classes.index(x) for x in labels]
    elif kind is not OutputKind.CONTINUOUS:
        raise ModelLoadError(f"{kind} outputs need method predict_proba")
    return method, index, k


class EstimatorDecoder(Decoder):
    """A fitted scikit-learn-style estimator, applied to each bin (stateless)."""

    def __init__(self, manifest: ModelManifest, est: Any) -> None:
        self.manifest = manifest
        self.est = est
        self.method, self.index, k = _estimator_io(manifest, est)
        self._hist = _History(manifest.input_width, k)

    def reset(self) -> None:
        self._hist.reset()

    def step(self, features: FloatArray, timestamp_s: float) -> DecodeOutput:
        x = self._hist.push(check_features(self.manifest, features))
        y = np.asarray(getattr(self.est, self.method)(x[None, :]), dtype=np.float64)
        y = y.reshape(1, -1)[0]
        if self.index is not None:
            y = y[self.index]
        return DecodeOutput(y)


def load_skops(manifest: ModelManifest, path: Path, trusted: bool) -> EstimatorDecoder:
    sio = _optional("skops.io", "sklearn")
    try:
        unknown = [str(t) for t in sio.get_untrusted_types(file=str(path))]
    except Exception as exc:
        raise ModelLoadError(f"{path.name} is not a readable skops file: {exc}") from None
    if unknown and not trusted:
        raise UntrustedModelError(
            f"{path.name} contains types skops does not trust by default: {unknown}. Loading "
            "them may run their code. Mark this exact file trusted only if you know its origin."
        )
    try:
        est = sio.load(str(path), trusted=unknown or None)
    except Exception as exc:
        raise ModelLoadError(f"skops cannot load {path.name}: {exc}") from None
    return EstimatorDecoder(manifest, est)


def load_unsafe(manifest: ModelManifest, path: Path, fmt: str, trusted: bool) -> Decoder:
    if not trusted:
        raise UntrustedModelError(
            f"{path.name} is a {fmt} file: loading it runs arbitrary code from the file. "
            "Concord refuses it unless the operator marks this exact file (SHA-256) trusted; "
            "convert it to skops or ONNX instead."
        )
    if fmt == "joblib":
        est = _optional("joblib", "sklearn").load(str(path))
    else:
        import pickle

        with path.open("rb") as fh:
            est = pickle.load(fh)  # explicit operator trust decision above
    if isinstance(est, Decoder):
        raise ModelLoadError("pickled Decoder objects are not supported; use a plugin")
    return EstimatorDecoder(manifest, est)


# ----------------------------------------------------------------------------- PyTorch


class TorchDecoder(Decoder):
    """TorchScript module or a built-in architecture with safetensors weights (CPU, no grad)."""

    def __init__(self, manifest: ModelManifest, module: Any, state_shape: list[int] | None):
        self.manifest = manifest
        self.module = module
        io = manifest.artifact.io if manifest.artifact else {}
        self._hist = _History(manifest.input_width, _history(io))
        self._state_shape = state_shape
        self._torch = _optional("torch", "torch")
        self._h: Any = None
        self.reset()

    def reset(self) -> None:
        self._hist.reset()
        t = self._torch
        self._h = None if self._state_shape is None else t.zeros(*self._state_shape)

    def step(self, features: FloatArray, timestamp_s: float) -> DecodeOutput:
        t = self._torch
        x = self._hist.push(check_features(self.manifest, features))
        xt = t.as_tensor(x[None, :], dtype=t.float32)
        with t.no_grad():
            if self._h is None:
                y = self.module(xt)
            else:
                y, self._h = self.module(xt, self._h)
        return DecodeOutput(np.asarray(y.detach().cpu().numpy(), dtype=np.float64).reshape(-1))


def _state_shape(io: Mapping[str, Any]) -> list[int] | None:
    s = io.get("state_shape")
    if s is None:
        return None
    if not isinstance(s, list) or not all(isinstance(x, int) and x > 0 for x in s):
        raise ModelLoadError("artifact.io.state_shape must be a list of positive ints")
    return s


def load_torchscript(manifest: ModelManifest, path: Path) -> TorchDecoder:
    torch = _optional("torch", "torch")
    try:
        module = torch.jit.load(str(path), map_location="cpu")
    except Exception as exc:
        raise ModelLoadError(f"{path.name} is not a TorchScript archive: {exc}") from None
    module.eval()
    io = manifest.artifact.io if manifest.artifact else {}
    dec = TorchDecoder(manifest, module, _state_shape(io))
    _probe(dec)
    return dec


def load_safetensors(manifest: ModelManifest, path: Path) -> TorchDecoder:
    _optional("torch", "torch")
    st = _optional("safetensors.torch", "torch")
    from concord_decoder_sdk import architectures

    io = manifest.artifact.io if manifest.artifact else {}
    width = manifest.input_width * _history(io)
    module, state_shape = architectures.build(io, width, len(manifest.output.dims))
    try:
        weights = st.load_file(str(path), device="cpu")
    except Exception as exc:
        raise ModelLoadError(f"{path.name} is not a safetensors file: {exc}") from None
    try:
        module.load_state_dict(weights, strict=True)
    except RuntimeError as exc:
        raise ModelLoadError(
            f"weights do not match the declared architecture: {str(exc)[:400]}"
        ) from None
    module.eval()
    dec = TorchDecoder(manifest, module, state_shape)
    _probe(dec)
    return dec


def _probe(dec: TorchDecoder) -> None:
    """One step on zeros to check the declared I/O, then reset."""
    try:
        out = dec.step(np.zeros(dec.manifest.input_width), 0.0)
    except Exception as exc:
        raise ModelLoadError(f"the model does not accept the declared input: {exc}") from None
    if out.values.shape != (len(dec.manifest.output.dims),):
        raise ModelLoadError(
            f"the model outputs {out.values.shape[0]} values; the manifest declares "
            f"{len(dec.manifest.output.dims)} dims"
        )
    dec.reset()


# ----------------------------------------------------------------------------- bundles

EXTENSIONS = {
    "onnx": ".onnx",
    "skops": ".skops",
    "torchscript": ".pt",
    "safetensors": ".safetensors",
    "pickle": ".pkl",
    "joblib": ".joblib",
}


def write_bundle(
    models_dir: Path,
    manifest: ModelManifest,
    model_file: Path,
    fmt: str,
    io: Mapping[str, Any] | None = None,
) -> Path:
    """Copy ``model_file`` into ``models_dir`` as ``<model_id><ext>`` and write
    ``<model_id>.manifest.json`` declaring it (format, SHA-256, I/O). Returns the manifest
    path. The manifest is validated first; a manifest with errors is not written."""
    import dataclasses
    import json
    import shutil

    from concord_decoder_sdk.api import Artifact
    from concord_decoder_sdk.manifest import has_errors, manifest_to_dict, summarize
    from concord_decoder_sdk.manifest import validate_manifest as _validate

    if fmt not in EXTENSIONS:
        raise ValueError(f"unknown format {fmt!r}")
    models_dir.mkdir(parents=True, exist_ok=True)
    name = f"{manifest.model_id.replace(':', '_')}{EXTENSIONS[fmt]}"
    dest = models_dir / name
    if model_file.resolve() != dest.resolve():
        shutil.copyfile(model_file, dest)
    full = dataclasses.replace(
        manifest, artifact=Artifact(fmt, name, sha256_file(dest), dict(io or {}))
    )
    problems = _validate(full)
    if has_errors(problems):
        dest.unlink(missing_ok=True)
        raise ValueError(f"invalid manifest: {summarize(problems)}")
    path = models_dir / f"{manifest.model_id.replace(':', '_')}.manifest.json"
    path.write_text(json.dumps(manifest_to_dict(full), indent=1), encoding="utf-8")
    return path


# ----------------------------------------------------------------------------- dispatch


def load_file_model(
    manifest: ModelManifest, manifest_dir: Path, trusted_sha256: str | None
) -> Decoder:
    """Load the manifest's artifact with the loader for its format.

    ``trusted_sha256``: the SHA-256 the operator marked trusted for this model (or None).
    Trust applies only if it equals the file's actual hash.
    """
    a = manifest.artifact
    if a is None:
        raise ModelLoadError(f"{manifest.model_id}: the manifest names no model file")
    path = verify_artifact(manifest, manifest_dir)
    trusted = trusted_sha256 is not None and trusted_sha256 == a.sha256
    fmt = a.format
    dec: Decoder
    if fmt == "onnx":
        dec = OnnxDecoder(manifest, path)
    elif fmt == "skops":
        dec = load_skops(manifest, path, trusted)
    elif fmt in UNSAFE_FORMATS:
        dec = load_unsafe(manifest, path, fmt, trusted)
    elif fmt == "torchscript":
        dec = load_torchscript(manifest, path)
    elif fmt == "safetensors":
        dec = load_safetensors(manifest, path)
    elif fmt == "concord-json":
        raise ModelLoadError("concord-json models are Concord built-ins; Concord runs them itself")
    else:
        raise ModelLoadError(f"unsupported model format {fmt!r}")
    return dec
