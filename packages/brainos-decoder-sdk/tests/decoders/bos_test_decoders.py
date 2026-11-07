"""Decoders for host / isolation tests (good ones and deliberately broken ones)."""

from __future__ import annotations

import dataclasses
import os
import sys
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

BASE = ModelManifest(
    model_id="test-linear",
    name="Test linear",
    version="1.0.0",
    api_version=API_VERSION,
    family="test-linear",
    description="sum of features per output dim",
    author="tests",
    license="CC0",
    modalities=frozenset({Modality.INTRACORTICAL}),
    inputs=(
        InputSpec(
            "features.binned",
            "threshold_crossing_count",
            20.0,
            4,
            ("e1", "e2", "e3", "e4"),
            "count",
        ),
    ),
    output=OutputSpec(OutputKind.CONTINUOUS, "velocity", ("vx", "vy"), "workspace/s", "screen"),
    compatibility=ParticipantCompat(source_identity="lsl:test"),
)


class GoodDecoder(Decoder):
    """vx = running sum of feature 0, vy = feature 1 (stateful, so reset is observable)."""

    manifest = BASE

    def load(self) -> None:
        self.total = 0.0

    def reset(self) -> None:
        self.total = 0.0

    def step(self, features: np.ndarray, timestamp_s: float) -> DecodeOutput:
        x = check_features(self.manifest, features)
        self.total += float(x[0])
        return DecodeOutput(np.array([self.total, float(x[1])]))


class PrintingDecoder(GoodDecoder):
    """Writes to stdout from Python and from the C level on every step."""

    def step(self, features: np.ndarray, timestamp_s: float) -> DecodeOutput:
        print("hello from a decoder")
        os.write(1, b"raw bytes on fd 1\n")
        sys.stdout.flush()
        return super().step(features, timestamp_s)


class CrashDecoder(GoodDecoder):
    def step(self, features: np.ndarray, timestamp_s: float) -> DecodeOutput:
        os._exit(7)


class HangDecoder(GoodDecoder):
    def step(self, features: np.ndarray, timestamp_s: float) -> DecodeOutput:
        time.sleep(3600)
        raise AssertionError("unreachable")


class RaisingDecoder(GoodDecoder):
    def step(self, features: np.ndarray, timestamp_s: float) -> DecodeOutput:
        raise ZeroDivisionError("bug in decoder code")


class WrongShapeDecoder(GoodDecoder):
    def step(self, features: np.ndarray, timestamp_s: float) -> DecodeOutput:
        return DecodeOutput(np.array([1.0, 2.0, 3.0]))


class NaNDecoder(GoodDecoder):
    def step(self, features: np.ndarray, timestamp_s: float) -> DecodeOutput:
        return DecodeOutput(np.array([np.nan, 0.0]))


class BadPosteriorDecoder(GoodDecoder):
    manifest = dataclasses.replace(
        BASE,
        model_id="test-bad-posterior",
        output=OutputSpec(
            OutputKind.CLASSES, "class_posterior", ("rest", "go"), "probability", "classes"
        ),
        confidence=Confidence.POSTERIOR,
    )

    def step(self, features: np.ndarray, timestamp_s: float) -> DecodeOutput:
        return DecodeOutput(np.array([0.7, 0.7]))


class VarianceDecoder(GoodDecoder):
    manifest = dataclasses.replace(BASE, model_id="test-variance", confidence=Confidence.VARIANCE)

    def step(self, features: np.ndarray, timestamp_s: float) -> DecodeOutput:
        out = super().step(features, timestamp_s)
        return DecodeOutput(out.values, np.array([0.5, 0.25]))


class MissingVarianceDecoder(VarianceDecoder):
    def step(self, features: np.ndarray, timestamp_s: float) -> DecodeOutput:
        return GoodDecoder.step(self, features, timestamp_s)


class BadManifestDecoder(GoodDecoder):
    manifest = dataclasses.replace(BASE, api_version="2.0", modalities=frozenset())


class LoadFailsDecoder(GoodDecoder):
    def load(self) -> None:
        from brainos_decoder_sdk import ModelLoadError

        raise ModelLoadError("parameter file missing: weights.npz")


class NotADecoder:
    manifest = BASE
