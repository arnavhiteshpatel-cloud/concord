"""Simulated input modalities and simulated participant populations.

Every modality here is SIMULATED and labelled as such in all outputs. A modality couples a virtual
user model, a control mode, a degradation profile and a selection method. Populations add
between-participant variability so that reliability and responsiveness can be studied.
"""
from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Optional

import numpy as np

from .decoder import DegradationConfig, PROFILES
from .scanning import ScanConfig
from ..users.models import UserParams


@dataclass(frozen=True)
class Modality:
    name: str
    kind: str  # "pointer" or "scan"
    user_model: str = "feedback"
    user: UserParams = field(default_factory=UserParams)
    degradation: DegradationConfig = field(default_factory=DegradationConfig)
    selection: str = "click"  # click | dwell
    dwell_ms: Optional[float] = None
    scan: Optional[ScanConfig] = None
    label: str = "simulated"
    note: str = ""

    def with_degradation(self, d: DegradationConfig) -> "Modality":
        return replace(self, degradation=d)


MOUSE_USER = UserParams(reaction_ms=220, feedback_delay_ms=110, sub_tmin_ms=90, sub_c=15,
                        sub_k=0.10, const_noise=1.5, select_margin=0.85, select_rt_ms=80,
                        aim_sd_frac=0.12)
HEAD_USER = UserParams(reaction_ms=300, feedback_delay_ms=160, sub_tmin_ms=180, sub_c=30,
                       sub_k=0.16, const_noise=4.0, select_margin=0.8, select_rt_ms=150,
                       aim_sd_frac=0.15)
GAZE_USER = UserParams(reaction_ms=220, feedback_delay_ms=120, saccade_ms=45,
                       fixation_jitter=7.0, aim_sd_frac=0.12, offset_compensation=0.6,
                       select_margin=0.9)
BCI_USER = UserParams(reaction_ms=300, feedback_delay_ms=150, kp=3.0, settle_ms=300, vmax=700,
                      motor_noise=0.05, const_noise=3.0, aim_sd_frac=0.1, select_margin=0.75,
                      select_speed=200, select_rt_ms=150)

MODALITIES: dict[str, Modality] = {
    "mouse_sim": Modality("mouse_sim", "pointer", "submovement", MOUSE_USER,
                          note="Idealised position-control pointer (minimum-jerk submovements)."),
    "head_pointer_sim": Modality("head_pointer_sim", "pointer", "submovement", HEAD_USER,
                                 DegradationConfig(white_noise=2.0, latency_ms=40,
                                                   smoothing_tau_ms=40),
                                 selection="dwell", dwell_ms=1000,
                                 note="Slower, noisier position pointer with dwell selection."),
    "eye_gaze_sim": Modality("eye_gaze_sim", "pointer", "gaze", GAZE_USER,
                             DegradationConfig(white_noise=6.0, smoothing_tau_ms=30,
                                               latency_ms=30, drift=0.0),
                             selection="dwell", dwell_ms=800,
                             note="Gaze-like pointer: saccades, fixation jitter, dwell selection."),
    "bci_cursor_good_sim": Modality("bci_cursor_good_sim", "pointer", "feedback", BCI_USER,
                                    PROFILES["bci_good"], note="Velocity BCI-like cursor, mild degradation."),
    "bci_cursor_moderate_sim": Modality("bci_cursor_moderate_sim", "pointer", "feedback",
                                        BCI_USER, PROFILES["bci_moderate"]),
    "bci_cursor_poor_sim": Modality("bci_cursor_poor_sim", "pointer", "feedback", BCI_USER,
                                    PROFILES["bci_poor"]),
    "switch_scan_sim": Modality("switch_scan_sim", "scan", scan=ScanConfig(scan_ms=1000),
                                note="Single-switch row-column scanning (1 s scan rate)."),
    "switch_scan_fast_sim": Modality("switch_scan_fast_sim", "scan", scan=ScanConfig(scan_ms=600),
                                     note="Row-column scanning at 0.6 s."),
}


def sample_population(base: UserParams, n: int, rng: np.random.Generator,
                      ability_sd: float = 0.25, ability: Optional[np.ndarray] = None) -> tuple[UserParams, np.ndarray]:
    """Sample n simulated participants around a base parameter set.

    A single latent 'ability' z ~ N(0,1) (or supplied) scales speed parameters by exp(sd*z) and
    noise parameters by exp(-sd*z); independent idiosyncratic variation (sd/2) is added per
    parameter. Returns the batched UserParams and the latent ability (ground truth).
    """
    z = rng.standard_normal(n) if ability is None else np.asarray(ability, float)
    s = ability_sd

    def ln(sd):
        return np.exp(sd * rng.standard_normal(n))

    up = base.batch(n)
    speed = np.exp(s * z)
    noise = np.exp(-s * z)
    return UserParams(
        feedback_delay_ms=up.feedback_delay_ms * noise ** 0.5 * ln(s / 3),
        reaction_ms=up.reaction_ms * noise ** 0.5 * ln(s / 3),
        kp=up.kp * speed * ln(s / 2), vmax=up.vmax * speed * ln(s / 2),
        motor_noise=up.motor_noise * noise * ln(s / 2), const_noise=up.const_noise * noise * ln(s / 2),
        aim_sd_frac=up.aim_sd_frac * noise * ln(s / 2), select_margin=up.select_margin,
        select_speed=up.select_speed, select_rt_ms=up.select_rt_ms * noise ** 0.5 * ln(s / 3),
        settle_ms=up.settle_ms,
        sub_tmin_ms=up.sub_tmin_ms * noise ** 0.5, sub_c=up.sub_c * noise * ln(s / 2),
        sub_k=up.sub_k * noise * ln(s / 2), saccade_ms=up.saccade_ms,
        fixation_jitter=up.fixation_jitter * noise * ln(s / 2),
        offset_compensation=np.clip(up.offset_compensation * speed, 0, 1),
        fatigue_per_min=up.fatigue_per_min,
    ), z
