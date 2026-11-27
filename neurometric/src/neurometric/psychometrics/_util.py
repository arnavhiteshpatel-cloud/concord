"""Small shared helpers for :mod:`neurometric.psychometrics` (not public API)."""
from __future__ import annotations

import math
from typing import Any, Iterable

import numpy as np
import pandas as pd


def as_1d(x: Iterable[float], name: str = "x", dropna: bool = True) -> np.ndarray:
    """Convert to a float 1-D array, optionally dropping NaNs."""
    a = np.asarray(x, dtype=float).ravel()
    if dropna:
        a = a[~np.isnan(a)]
    return a


def paired_arrays(x, y) -> tuple[np.ndarray, np.ndarray, int]:
    """Return x, y with pairs containing a NaN removed, and the number removed."""
    x = np.asarray(x, dtype=float).ravel()
    y = np.asarray(y, dtype=float).ravel()
    if x.shape != y.shape:
        raise ValueError("paired inputs must have the same length")
    ok = ~(np.isnan(x) | np.isnan(y))
    return x[ok], y[ok], int((~ok).sum())


def jsonable(obj: Any) -> Any:
    """Recursively convert numpy / pandas objects to JSON-serialisable Python objects.

    NaN and +-inf become ``None`` (JSON has no NaN).
    """
    if isinstance(obj, dict):
        return {str(k): jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    if isinstance(obj, pd.DataFrame):
        return [jsonable(r) for r in obj.to_dict(orient="records")]
    if isinstance(obj, pd.Series):
        return jsonable(obj.to_dict())
    if isinstance(obj, np.ndarray):
        return [jsonable(v) for v in obj.tolist()]
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if obj is None or isinstance(obj, (str, int)):
        return obj
    return str(obj)
