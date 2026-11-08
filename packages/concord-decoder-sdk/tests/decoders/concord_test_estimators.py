"""A custom scikit-learn estimator: skops does not trust it by default (tests the policy)."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin


class TimesTwo(RegressorMixin, BaseEstimator):  # type: ignore[misc]
    def fit(self, x: np.ndarray, y: Any = None) -> TimesTwo:
        self.n_features_in_ = x.shape[1]
        return self

    def predict(self, x: np.ndarray) -> np.ndarray:
        return np.asarray(x[:, :2] * 2.0)
