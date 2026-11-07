"""Decoder plugins for runtime tests (run in decoder-host subprocesses, never imported by
the runtime). They use only the public decoder SDK."""

from __future__ import annotations

import dataclasses
import os
import time

import numpy as np
from brainos_decoder_sdk import (
    API_VERSION,
    Confidence,
    DecodeOutput,
    Decoder,
    InputSpec,
    Modality,
    ModelManifest,
    OutputKind,
    OutputSpec,
    ParticipantCompat,
    check_features,
)

LABELS = ("e1", "e2", "e3", "e4")
W = np.array([[0.5, -0.25], [0.125, 0.75], [-0.5, 0.0625], [0.25, 0.25]])

MANIFEST = ModelManifest(
    model_id="test-plugin-linear",
    name="Test plugin linear decoder",
    version="0.1.0",
    api_version=API_VERSION,
    family="test-linear",
    description="vx, vy = features @ W (fixed weights, for tests)",
    author="BrainOS tests",
    license="CC0",
    modalities=frozenset({Modality.INTRACORTICAL}),
    inputs=(InputSpec("features.binned", "threshold_crossing_count", 20.0, 4, LABELS, "count"),),
    output=OutputSpec(
        OutputKind.CONTINUOUS, "velocity", ("vx", "vy"), "workspace/s", "screen", scale=(1.0, 1.0)
    ),
    compatibility=ParticipantCompat(source_identity="test:feature-source"),
)


class LabelledLinear(Decoder):
    manifest = MANIFEST

    def reset(self) -> None:
        self.n = 0

    def step(self, features: np.ndarray, timestamp_s: float) -> DecodeOutput:
        x = check_features(self.manifest, features)
        self.n += 1
        return DecodeOutput(x @ W)


class CrashAfter(LabelledLinear):
    manifest = dataclasses.replace(MANIFEST, model_id="test-plugin-crash")

    def step(self, features: np.ndarray, timestamp_s: float) -> DecodeOutput:
        if getattr(self, "n", 0) >= 10:
            os._exit(9)
        return super().step(features, timestamp_s)


class HangAfter(LabelledLinear):
    manifest = dataclasses.replace(MANIFEST, model_id="test-plugin-hang")

    def step(self, features: np.ndarray, timestamp_s: float) -> DecodeOutput:
        if getattr(self, "n", 0) >= 10:
            time.sleep(3600)
        return super().step(features, timestamp_s)


class NaNAfter(LabelledLinear):
    manifest = dataclasses.replace(MANIFEST, model_id="test-plugin-nan")

    def step(self, features: np.ndarray, timestamp_s: float) -> DecodeOutput:
        out = super().step(features, timestamp_s)
        if self.n > 10:
            return DecodeOutput(np.array([np.nan, 0.0]))
        return out


class WithVariance(LabelledLinear):
    manifest = dataclasses.replace(
        MANIFEST, model_id="test-plugin-variance", confidence=Confidence.VARIANCE
    )

    def step(self, features: np.ndarray, timestamp_s: float) -> DecodeOutput:
        return DecodeOutput(super().step(features, timestamp_s).values, np.array([0.1, 0.2]))


class EEGOnly(LabelledLinear):
    manifest = dataclasses.replace(
        MANIFEST, model_id="test-plugin-eeg", modalities=frozenset({Modality.EEG})
    )
