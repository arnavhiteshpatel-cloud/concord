"""Simulated decoder degradation harness.

This is an *experimental model of input degradation*, not a model of neural physiology. It maps
an intended control signal (what a simulated user means to do) to a degraded output signal (what
the cursor or selection channel actually does). It never sees the task, the target or the score:
it is a pure transform of the intent stream, exactly as a real decoder would be from the point of
view of a downstream measurement system.

Two control modes are supported:

* ``velocity`` - the intent is a cursor velocity (px/s); the output velocity is integrated into a
  cursor position by the task. This is how most intracortical BCI cursor decoders are used
  (velocity Kalman / ReFIT-style decoders) [PK].
* ``position`` - the intent is a pointer position (px); the output is a position. Used for mouse,
  head pointer and eye gaze style inputs.

Selection is a separate binary channel (click / "select" intent) with miss probability, detection
latency and false activations.

All parameters are explicit, documented, and default to *no degradation* (identity transform).
Plausible ranges are documented in docs/science/SIMULATOR_PARAMETERS.md with evidence labels.
All randomness comes from a ``numpy.random.Generator`` supplied by the caller (deterministic).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Literal, Optional

import numpy as np

ControlMode = Literal["velocity", "position"]


@dataclass(frozen=True)
class DegradationConfig:
    """Parameters of the input degradation model. Defaults = identity (no degradation)."""

    # --- continuous channel -------------------------------------------------------------
    gain: float = 1.0  # multiplicative gain; >1 overshoot tendency, <1 undershoot
    bias_deg: float = 0.0  # systematic rotation of the decoded direction (degrees)
    asymmetry: float = 0.0  # +a: rightward components scaled (1+a), leftward (1-a)
    white_noise: float = 0.0  # SD of white Gaussian noise per axis (px/s or px)
    correlated_noise: float = 0.0  # SD of AR(1) noise per axis (px/s or px)
    correlated_tau_ms: float = 300.0  # time constant of the AR(1) noise
    drift: float = 0.0  # constant drift magnitude (px/s in velocity mode, px offset in position)
    drift_rate_per_min: float = 0.0  # drift growth per minute of session time
    smoothing_tau_ms: float = 0.0  # exponential smoothing time constant (decoder smoothing)
    quantization: float = 0.0  # if >0, output rounded to multiples of this (px/s or px)
    direction_bins: int = 0  # if >0, output direction snapped to this many directions
    update_hz: float = 0.0  # if >0, output updated only at this rate (sample and hold)
    latency_ms: float = 0.0  # fixed output latency
    latency_jitter_ms: float = 0.0  # mean of exponential extra latency (variable latency)
    dropout_enter_per_s: float = 0.0  # hazard of entering a dropout episode
    dropout_mean_ms: float = 0.0  # mean dropout duration
    # calibration deterioration over session time
    gain_decay_per_min: float = 0.0  # fractional loss of gain per minute
    noise_growth_per_min: float = 0.0  # fractional growth of noise SD per minute
    # temporary loss of control + recovery
    loss_of_control_per_min: float = 0.0
    loss_of_control_mean_ms: float = 0.0
    recovery_ms: float = 0.0  # gain ramps linearly from 0 back to 1 after a loss of control
    # --- selection channel -----------------------------------------------------------
    select_miss_prob: float = 0.0  # probability an intended selection is not produced
    select_latency_ms: float = 0.0
    false_select_per_min: float = 0.0  # unintended selections per minute of active use
    dims: tuple[bool, bool] = (True, True)  # which axes are active (scrolling uses (False, True))

    def to_dict(self) -> dict:
        return asdict(self)

    def with_(self, **kw) -> "DegradationConfig":
        return replace(self, **kw)

    @property
    def is_identity(self) -> bool:
        return self == DegradationConfig(dims=self.dims)


@dataclass
class DecoderTrace:
    """Ground-truth bookkeeping only available in simulation."""

    dropout_ticks: np.ndarray
    loc_ticks: np.ndarray
    false_selects: np.ndarray
    missed_selects: np.ndarray


class DegradedChannel:
    """Batched, stateful degradation of B independent input streams.

    State persists across calls (so a sequence of task steps sees continuous decoder behaviour).
    """

    def __init__(self, cfg: DegradationConfig, batch: int, dt_ms: float, mode: ControlMode,
                 rng: np.random.Generator, session_minutes: Optional[np.ndarray] = None):
        self.cfg = cfg
        self.B = batch
        self.dt = dt_ms
        self.mode = mode
        self.rng = rng
        self.t_min = (np.zeros(batch) if session_minutes is None
                      else np.asarray(session_minutes, float).copy())
        c = cfg
        self.ar = np.zeros((batch, 2))
        self.rho = float(np.exp(-dt_ms / c.correlated_tau_ms)) if c.correlated_tau_ms > 0 else 0.0
        self.smooth = np.zeros((batch, 2))
        self.smooth_init = np.zeros(batch, bool)
        self.alpha = (float(np.exp(-dt_ms / c.smoothing_tau_ms)) if c.smoothing_tau_ms > 0
                      else 0.0)
        th = np.deg2rad(c.bias_deg)
        self.R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
        ang = rng.uniform(0, 2 * np.pi, batch)
        self.drift_dir = np.stack([np.cos(ang), np.sin(ang)], 1)
        self.hold_every = max(1, int(round(1000.0 / c.update_hz / dt_ms))) if c.update_hz > 0 else 1
        self.tick = np.zeros(batch, np.int64)
        self.held = np.zeros((batch, 2))
        self.lat_ticks = int(round(c.latency_ms / dt_ms))
        self.buf_len = self.lat_ticks + int(np.ceil(max(c.latency_jitter_ms, 0) * 8 / dt_ms)) + 2
        self.buf = np.zeros((batch, self.buf_len, 2))
        self.buf_filled = 0
        self.last_read = np.full(batch, -1, np.int64)
        self.global_tick = 0
        self.in_dropout = np.zeros(batch, bool)
        self.in_loc = np.zeros(batch, bool)
        self.recover_left = np.zeros(batch)
        self.last_out = np.zeros((batch, 2))
        self.pos_track = None  # noiseless position track (position mode)
        self.prev_intent = None
        self.prev_sel_intent = np.zeros(batch, bool)
        sl = int(round(c.select_latency_ms / dt_ms))
        self.sel_lat = sl
        self.sel_buf = np.zeros((batch, sl + 1), bool)
        self.dims = np.array(cfg.dims, float)
        self.dropout_ticks = np.zeros(batch, np.int64)
        self.loc_ticks = np.zeros(batch, np.int64)
        self.false_selects = np.zeros(batch, np.int64)
        self.missed_selects = np.zeros(batch, np.int64)

    # ------------------------------------------------------------------ helpers
    def _hazard(self, per_s: float) -> float:
        return 1.0 - np.exp(-per_s * self.dt / 1000.0) if per_s > 0 else 0.0

    def step(self, intent: np.ndarray, select_intent: np.ndarray,
             active: Optional[np.ndarray] = None) -> tuple[np.ndarray, np.ndarray]:
        """Advance one tick.

        intent: (B,2) intended velocity (px/s) or position (px).
        select_intent: (B,) bool - the user is currently trying to select (level, not edge).
        active: (B,) bool - elements still running; inactive elements are left untouched.
        Returns (output (B,2), select_out (B,) bool edge events).
        """
        c, rng, B = self.cfg, self.rng, self.B
        if active is None:
            active = np.ones(B, bool)
        intent = np.asarray(intent, float) * self.dims
        tmin = self.t_min
        # --- episodes: dropout and loss of control --------------------------------
        if c.dropout_enter_per_s > 0 and c.dropout_mean_ms > 0:
            enter = (~self.in_dropout) & (rng.random(B) < self._hazard(c.dropout_enter_per_s))
            leave = self.in_dropout & (rng.random(B) < 1 - np.exp(-self.dt / c.dropout_mean_ms))
            self.in_dropout = (self.in_dropout | enter) & ~leave
        if c.loss_of_control_per_min > 0 and c.loss_of_control_mean_ms > 0:
            enter = (~self.in_loc) & (rng.random(B) < self._hazard(c.loss_of_control_per_min / 60))
            leave = self.in_loc & (rng.random(B) < 1 - np.exp(-self.dt / c.loss_of_control_mean_ms))
            self.recover_left = np.where(leave, c.recovery_ms, self.recover_left)
            self.in_loc = (self.in_loc | enter) & ~leave
        rec = np.ones(B)
        if c.recovery_ms > 0:
            rec = np.where(self.recover_left > 0, 1 - self.recover_left / c.recovery_ms, 1.0)
            self.recover_left = np.maximum(0, self.recover_left - self.dt)
        # --- deterministic transform ---------------------------------------------
        g = c.gain * np.maximum(0.0, 1 - c.gain_decay_per_min * tmin)
        v = intent.copy()
        if self.mode == "velocity":
            if c.asymmetry:
                v[:, 0] = np.where(v[:, 0] > 0, v[:, 0] * (1 + c.asymmetry), v[:, 0] * (1 - c.asymmetry))
            if c.bias_deg:
                v = v @ self.R.T
            v = v * (g * rec)[:, None]
            v = np.where(self.in_loc[:, None], 0.0, v)
        else:
            # position mode: gain mismatch scales *displacements* (relative pointing, like a
            # control-display gain error); the bias/asymmetry act on displacements too.
            if self.pos_track is None:
                self.pos_track = intent.copy()
                self.prev_intent = intent.copy()
                self.last_out = intent.copy()
            d = intent - self.prev_intent
            if c.asymmetry:
                d[:, 0] = np.where(d[:, 0] > 0, d[:, 0] * (1 + c.asymmetry), d[:, 0] * (1 - c.asymmetry))
            if c.bias_deg:
                d = d @ self.R.T
            d = d * (g * rec)[:, None]
            d = np.where(self.in_loc[:, None], 0.0, d)
            self.pos_track = np.where(active[:, None], self.pos_track + d, self.pos_track)
            self.prev_intent = intent.copy()
            v = self.pos_track.copy()
        # --- noise ---------------------------------------------------------------
        growth = 1 + c.noise_growth_per_min * tmin
        if c.white_noise:
            v = v + rng.standard_normal((B, 2)) * (c.white_noise * growth)[:, None]
        if c.correlated_noise:
            self.ar = self.rho * self.ar + np.sqrt(1 - self.rho ** 2) * rng.standard_normal((B, 2)) \
                * (c.correlated_noise * growth)[:, None]
            v = v + self.ar
        if c.drift or c.drift_rate_per_min:
            v = v + self.drift_dir * (c.drift + c.drift_rate_per_min * tmin)[:, None]
        v = v * self.dims
        # --- smoothing -----------------------------------------------------------
        if self.alpha > 0:
            init = ~self.smooth_init
            self.smooth[init] = v[init]
            self.smooth_init |= True
            self.smooth = self.alpha * self.smooth + (1 - self.alpha) * v
            v = self.smooth.copy()
        # --- quantisation --------------------------------------------------------
        if c.direction_bins > 0:
            mag = np.hypot(v[:, 0], v[:, 1])
            ang = np.arctan2(v[:, 1], v[:, 0])
            step = 2 * np.pi / c.direction_bins
            ang = np.round(ang / step) * step
            v = np.stack([mag * np.cos(ang), mag * np.sin(ang)], 1)
        if c.quantization > 0:
            v = np.round(v / c.quantization) * c.quantization
        # --- update rate (sample and hold) ---------------------------------------
        if self.hold_every > 1:
            upd = (self.tick % self.hold_every) == 0
            self.held[upd] = v[upd]
            v = self.held.copy()
        # --- latency -------------------------------------------------------------
        if self.buf_len > 2 or self.lat_ticks:
            pos = self.global_tick % self.buf_len
            self.buf[:, pos] = v
            self.buf_filled = min(self.buf_filled + 1, self.buf_len)
            delay = np.full(B, self.lat_ticks, np.int64)
            if c.latency_jitter_ms > 0:
                delay = delay + np.round(rng.exponential(c.latency_jitter_ms, B) / self.dt).astype(np.int64)
            delay = np.minimum(delay, self.buf_filled - 1)
            read = self.global_tick - delay
            read = np.maximum(read, self.last_read)  # outputs never go back in time
            self.last_read = read
            if self.global_tick - self.lat_ticks < 0:
                v = np.zeros_like(v) if self.mode == "velocity" else self.last_out.copy()
                if self.mode == "position" and self.global_tick == 0:
                    v = intent.copy()
            else:
                v = self.buf[np.arange(B), read % self.buf_len]
        # --- dropout -------------------------------------------------------------
        if self.mode == "velocity":
            v = np.where(self.in_dropout[:, None], 0.0, v)
        else:
            v = np.where(self.in_dropout[:, None], self.last_out, v)
        # --- selection channel ---------------------------------------------------
        sel_edge = select_intent & ~self.prev_sel_intent
        self.prev_sel_intent = select_intent.copy()
        produced = sel_edge.copy()
        if c.select_miss_prob > 0:
            miss = produced & (rng.random(B) < c.select_miss_prob)
            self.missed_selects += (miss & active)
            produced &= ~miss
        blocked = self.in_dropout | self.in_loc
        self.missed_selects += (produced & blocked & active)
        produced &= ~blocked
        if c.false_select_per_min > 0:
            fa = rng.random(B) < self._hazard(c.false_select_per_min / 60.0)
            fa &= ~select_intent & active
            self.false_selects += fa
            produced |= fa
        if self.sel_lat > 0:
            self.sel_buf = np.roll(self.sel_buf, -1, axis=1)
            self.sel_buf[:, -1] = produced
            sel_out = self.sel_buf[:, 0].copy()
        else:
            sel_out = produced
        # --- bookkeeping ---------------------------------------------------------
        self.dropout_ticks += self.in_dropout & active
        self.loc_ticks += self.in_loc & active
        self.last_out = np.where(active[:, None], v, self.last_out)
        self.tick += 1
        self.global_tick += 1
        self.t_min = self.t_min + active * (self.dt / 60000.0)
        return v, sel_out & active

    def trace(self) -> DecoderTrace:
        return DecoderTrace(self.dropout_ticks.copy(), self.loc_ticks.copy(),
                            self.false_selects.copy(), self.missed_selects.copy())


#: Named, documented profiles. These are *illustrative stress profiles*, not models of any
#: particular commercial or research BCI. See docs/science/SIMULATOR_PARAMETERS.md.
#: Calibration (experiments/results/calibration): with the default BCI-like feedback user,
#: bci_good gives ISO effective throughput ~1.2 bit/s and grid achieved bitrate ~2.4 bit/s, inside
#: the broad range reported for intracortical BCI cursor control [PK, approximate]; bci_moderate
#: ~0.5 bit/s and bci_poor ~0.25 bit/s are deliberately degraded stress conditions.
PROFILES: dict[str, DegradationConfig] = {
    "identity": DegradationConfig(),
    "bci_good": DegradationConfig(white_noise=30, correlated_noise=40, correlated_tau_ms=400,
                                  smoothing_tau_ms=60, latency_ms=60, update_hz=50,
                                  false_select_per_min=0.3, select_miss_prob=0.05,
                                  select_latency_ms=60),
    "bci_moderate": DegradationConfig(white_noise=60, correlated_noise=80, correlated_tau_ms=500,
                                      smoothing_tau_ms=80, latency_ms=100, update_hz=50,
                                      bias_deg=10, gain=0.85, false_select_per_min=1.0,
                                      select_miss_prob=0.10, select_latency_ms=100,
                                      dropout_enter_per_s=0.02, dropout_mean_ms=400),
    "bci_poor": DegradationConfig(white_noise=100, correlated_noise=130, correlated_tau_ms=600,
                                  smoothing_tau_ms=100, latency_ms=150, update_hz=20,
                                  bias_deg=20, gain=0.7, drift=20, false_select_per_min=3.0,
                                  select_miss_prob=0.2, select_latency_ms=150,
                                  dropout_enter_per_s=0.05, dropout_mean_ms=800,
                                  loss_of_control_per_min=0.5, loss_of_control_mean_ms=1500,
                                  recovery_ms=1000),
}
