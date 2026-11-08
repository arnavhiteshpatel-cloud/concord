"""Built-in decoder families: JSON models Concord runs in-process.

A *family* is a model class serialized as JSON (``concord.model/1``), dispatched on the
file's ``kind`` field (files without ``kind`` are ridge, or LDA when they declare
``outputs: {"type": "classes"}`` — the Milestone 2-4 formats load unchanged). Built-in
families run in the Concord process; every other decoder (plugins, ONNX, scikit-learn,
PyTorch files) runs in an isolated decoder host (``concord_decoder_sdk.host``).

Registering a family (stable API; e.g. at the bottom of ``decoding/kalman.py``)::

    from concord.decoding.families import BuiltinFamily, register_family

    register_family(
        BuiltinFamily(
            name="kalman",
            kinds=frozenset({"kalman"}),
            output="continuous",
            from_dict=KalmanDecoder.from_dict,
            description="Velocity Kalman filter (Wu/Gilja)",
            confidence="covariance",
            capabilities=frozenset({"continuous"}),
            fit=fit_kalman_for_calibration,  # optional: (CalibrationData) -> model
        )
    )

and add the module to ``_BUILTIN_MODULES`` below so it is imported (and registered) before
any model is loaded.

What a family's model object provides (:class:`JsonModel`): ``model_id``, ``dims``,
``quantity``, ``unit``, ``space``, ``input`` (one input) or ``inputs`` (several, concatenated
in order), ``source``, ``training`` (``behavior_std`` for the command router's pointer
z-scoring, ``feature_stats {mean, std}`` for drift monitoring), ``evaluations``, ``schema``,
``version``, ``created_at``, ``method``, ``save(path)``, and ``streaming()`` returning an
object with ``step(features) -> ndarray`` and ``reset()`` (plus ``covariance() -> (dims,
dims)`` for ``confidence="covariance"``, ``variance() -> (dims,)`` for ``"variance"``).
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable

import numpy as np
from numpy.typing import NDArray

log = logging.getLogger(__name__)

OutputKindName = Literal["continuous", "classes", "event"]
ConfidenceName = Literal["none", "posterior", "variance", "covariance"]
CalibrationCapability = Literal["continuous", "classes", "click"]


@runtime_checkable
class StreamingModel(Protocol):
    def step(self, features: Any) -> NDArray[np.float64]: ...

    def reset(self) -> None: ...


@runtime_checkable
class JsonModel(Protocol):
    """What every built-in family's model object provides (duck-typed)."""

    model_id: str
    space: str
    training: dict[str, Any]
    source: dict[str, Any]
    evaluations: list[dict[str, Any]]
    created_at: str
    method: str
    schema: str
    version: int

    @property
    def dims(self) -> list[str]: ...

    @property
    def quantity(self) -> str: ...

    @property
    def unit(self) -> str: ...

    def streaming(self) -> Any: ...

    def save(self, path: Any) -> Any: ...


@dataclass
class CalibrationData:
    """Aligned training data handed to a family's ``fit`` by the calibration workflow.

    ``fit`` must use only ``features[train]`` / ``targets[train]`` / ``valid[train]``; the
    workflow evaluates the returned model on the held-out tail itself (through the same
    ``streaming()`` path the pipeline uses) and adds ``feature_stats`` / ``output_stats``
    to ``model.training`` if the family did not.
    """

    features: NDArray[np.float64]  # (bins, width): all inputs concatenated in `inputs` order
    targets: NDArray[np.float64]  # (bins, len(target_dims)) labels aligned to bin ends
    valid: NDArray[np.bool_]  # bins with a usable label
    train: slice  # training bins
    target_dims: list[str]
    target_unit: str
    target_quantity: str
    bin_ms: float
    inputs: list[dict[str, Any]]  # input specs to store in the model ("inputs")
    training: dict[str, Any]  # provenance to merge into model.training
    source: dict[str, Any]  # {"identity", "description"} for model.source
    space: str
    # capability options: classes -> class_values / class_names; click -> positive value
    options: dict[str, Any] = field(default_factory=dict)


FitFn = Callable[[CalibrationData], Any]


@dataclass(frozen=True)
class BuiltinFamily:
    name: str  # shown to the operator, e.g. "ridge", "lda", "kalman"
    kinds: frozenset[str]  # values of the model file's "kind" field this family loads
    output: OutputKindName
    from_dict: Callable[[dict[str, Any], str], Any]  # (json dict, file name) -> model
    description: str = ""
    confidence: ConfidenceName = "none"
    capabilities: frozenset[CalibrationCapability] = frozenset()  # what calibration can fit
    fit: FitFn | None = None


_FAMILIES: dict[str, BuiltinFamily] = {}
# modules that register families when imported (the lead's kalman / click modules go here)
_BUILTIN_MODULES = (
    "concord.decoding.kalman",
    "concord.decoding.click",
)
_loaded_builtins = False


def register_family(family: BuiltinFamily, *, replace: bool = False) -> None:
    """Make a family loadable (by ``kind``) and, with ``fit``, calibratable."""
    if family.name in _FAMILIES and not replace:
        if _FAMILIES[family.name] is family:
            return
        raise ValueError(f"decoder family {family.name!r} is already registered")
    for other in _FAMILIES.values():
        if other.name != family.name and other.kinds & family.kinds:
            raise ValueError(
                f"family {family.name!r} claims kinds {sorted(other.kinds & family.kinds)} "
                f"of {other.name!r}"
            )
    _FAMILIES[family.name] = family


def _ensure_builtins() -> None:
    global _loaded_builtins
    if _loaded_builtins:
        return
    _loaded_builtins = True
    from concord.decoding import lda, ridge

    register_family(
        BuiltinFamily(
            name="ridge",
            kinds=frozenset({"ridge"}),
            output="continuous",
            from_dict=ridge.RidgeDecoder.from_dict,
            description="Causal exponential filter, z-score, ridge regression (FALCON baseline)",
            capabilities=frozenset({"continuous"}),
        )
    )
    register_family(
        BuiltinFamily(
            name="lda",
            kinds=frozenset({"lda"}),
            output="classes",
            from_dict=lda.LDAClassifier.from_dict,
            description="Shrinkage LDA on smoothed, z-scored features (class posteriors)",
            confidence="posterior",
            capabilities=frozenset({"classes", "click"}),
        )
    )
    for mod in _BUILTIN_MODULES:
        try:
            importlib.import_module(mod)
        except ModuleNotFoundError as exc:
            if exc.name != mod:  # the module exists but one of its imports is missing
                log.warning("decoder family module %s not loaded: %s", mod, exc)


def families() -> list[BuiltinFamily]:
    _ensure_builtins()
    return list(_FAMILIES.values())


def get_family(name: str) -> BuiltinFamily | None:
    _ensure_builtins()
    return _FAMILIES.get(name)


def family_for(data: dict[str, Any]) -> BuiltinFamily:
    """The family that loads a model JSON dict (legacy files: ridge, or LDA for classes)."""
    _ensure_builtins()
    kind = data.get("kind")
    if kind is None:
        outputs = data.get("outputs")
        classes = isinstance(outputs, dict) and outputs.get("type") == "classes"
        kind = "lda" if classes else "ridge"
    if not isinstance(kind, str):
        raise ValueError(f"model 'kind' must be a string, got {type(kind).__name__}")
    for fam in _FAMILIES.values():
        if kind in fam.kinds:
            return fam
    raise ValueError(
        f"unknown model kind {kind!r} (built-in families: "
        f"{sorted(k for f in _FAMILIES.values() for k in f.kinds)})"
    )


def family_of(model: Any) -> BuiltinFamily:
    """The family of a loaded model object (by its ``kind`` attribute; ridge by default)."""
    _ensure_builtins()
    kind = getattr(model, "kind", None) or "ridge"
    for fam in _FAMILIES.values():
        if kind in fam.kinds:
            return fam
    raise ValueError(f"no registered family for model kind {kind!r}")


def calibration_families(capability: CalibrationCapability) -> list[BuiltinFamily]:
    """Families that can be fitted for a calibration capability (ridge / lda are fitted by
    calibrate.py itself; others through their ``fit``)."""
    _ensure_builtins()
    return [
        f
        for f in _FAMILIES.values()
        if capability in f.capabilities and (f.fit is not None or f.name in ("ridge", "lda"))
    ]
