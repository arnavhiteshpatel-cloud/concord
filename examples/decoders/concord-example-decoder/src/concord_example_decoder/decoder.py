"""Example Concord decoder plugin: motor-imagery lateralization (hand-set, NOT trained).

This is a teaching example for the decoder SDK, written against
``concord_decoder_sdk`` only. It decodes rest / left / right from 8-13 Hz (mu) log band power
at C3 and C4 — the classic contralateral desynchronization: imagining a LEFT hand movement
lowers mu power over the RIGHT hemisphere (C4), and vice versa.

How it works (causal, bin by bin):

1. each channel's log power is compared with its own slow running baseline (exponential,
   ``BASELINE_S``), so there is no per-participant calibration — and no claim that this works
   on real EEG: the rule's constants were set by hand on the declared-SYNTHETIC example
   source, nothing was fitted;
2. the lateralization index ``d = (C3 - base_C3) - (C4 - base_C4)`` (log10 units) is smoothed
   (``SMOOTH_S``);
3. class scores ``left = GAIN * (d - MARGIN)``, ``right = GAIN * (-d - MARGIN)``, ``rest = 0``
   become posteriors through a softmax.

The manifest declares exactly what the rule needs: EEG, ``log_band_power`` in the 8-13 Hz
band at 100 ms bins, channels labelled C3 and C4 (Concord selects them from a larger montage
only if the operator enables mapping by label), and that it is not participant-specific.
"""

from __future__ import annotations

import math

import numpy as np
from concord_decoder_sdk import (
    API_VERSION,
    CalibrationSpec,
    Confidence,
    DecodeOutput,
    Decoder,
    InputSpec,
    Modality,
    ModelManifest,
    ModelProvenance,
    OutputKind,
    OutputSpec,
    ParticipantCompat,
    Preprocessing,
    check_features,
)
from numpy.typing import NDArray

BIN_MS = 100.0
BAND_HZ = (8.0, 13.0)
BASELINE_S = 20.0  # running baseline per channel
SMOOTH_S = 0.6  # smoothing of the lateralization index
GAIN = 12.0
MARGIN = 0.2  # log10 units of lateralization before left / right beat rest


def _alpha(tau_s: float) -> float:
    return 1.0 - math.exp(-(BIN_MS / 1000.0) / tau_s)


class LateralizationDecoder(Decoder):
    manifest = ModelManifest(
        model_id="example-mi-lateralization-0.1.0",
        name="Example: motor-imagery lateralization",
        version="0.1.0",
        api_version=API_VERSION,
        family="example-lateralization",
        description=(
            "Hand-set rule (NOT trained): mu (8-13 Hz) power at C3 vs C4, each against its "
            "own running baseline -> rest / left / right posteriors. A decoder-SDK example "
            "for the declared-synthetic example source; not validated on real EEG."
        ),
        author="Concord example",
        license="Proprietary (internal preview)",
        modalities=frozenset({Modality.EEG}),
        inputs=(
            InputSpec(
                event_type="features.vector",
                feature="log_band_power",
                bin_ms=BIN_MS,
                channel_count=2,
                channel_labels=("C3", "C4"),
                unit="log10(uV^2)",
                band_hz=BAND_HZ,
            ),
        ),
        output=OutputSpec(
            kind=OutputKind.CLASSES,
            quantity="class_posterior",
            dims=("rest", "left", "right"),
            unit="probability",
            space="motor_imagery_3class",
        ),
        confidence=Confidence.POSTERIOR,
        preprocessing=Preprocessing(
            preset="band_power",
            params={"band_low_hz": BAND_HZ[0], "band_high_hz": BAND_HZ[1]},
            description=(
                f"inside the decoder: per-channel running baseline ({BASELINE_S:g} s), "
                f"lateralization index smoothed over {SMOOTH_S:g} s"
            ),
        ),
        compatibility=ParticipantCompat(participant_specific=False),
        calibration=CalibrationSpec(
            required=False, task="none: the rule is hand-set and adapts its baseline online"
        ),
        provenance=ModelProvenance(
            code_version="concord-example-decoder 0.1.0",
            trained_by="nobody: hand-set constants",
            notes="constants chosen by hand on the declared-synthetic example source",
        ),
    )

    def load(self) -> None:
        self._a_base = _alpha(BASELINE_S)
        self._a_smooth = _alpha(SMOOTH_S)
        self.reset()

    def reset(self) -> None:
        self._base: NDArray[np.float64] | None = None
        self._d = 0.0

    def step(self, features: NDArray[np.float64], timestamp_s: float) -> DecodeOutput:
        x = check_features(self.manifest, features)  # [C3, C4] log10 power
        if self._base is None:
            self._base = x.copy()
        rel = x - self._base
        self._base = self._base + self._a_base * (x - self._base)
        d = float(rel[0] - rel[1])
        self._d += self._a_smooth * (d - self._d)
        scores = np.array([0.0, GAIN * (self._d - MARGIN), GAIN * (-self._d - MARGIN)])
        e = np.exp(scores - scores.max())
        return DecodeOutput(e / e.sum())
