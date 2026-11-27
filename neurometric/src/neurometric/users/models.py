"""Virtual users: simulated task participants.

These are *synthetic control policies* used to stress-test measurement properties under known,
controlled input conditions. They are not models of any patient population and must never be
described as patients or as clinical data. See docs/science/VIRTUAL_USERS.md.

All models are batched: each instance controls B independent simulated participants/trials, with
per-element parameter arrays, so large experiments run as vectorised numpy code.

Models
------
FeedbackUser      Closed-loop proportional controller with sensorimotor feedback delay, speed
                  limit and signal-dependent noise. Produces a velocity intent. The standard way
                  BCI cursor control has been modelled for decoder design (feedback-control
                  models of the BCI user, e.g. Willett et al. 2019, Sci Rep) [PK].
SubmovementUser   Position-control user that plans minimum-jerk submovements (Flash & Hogan 1985)
                  with endpoint noise proportional to movement speed (stochastic optimised
                  submovement idea, Meyer et al. 1988) and corrective submovements [PK].
GazeUser          Position-control eye-gaze-like pointer: saccade latency, saccade, fixational
                  jitter, partial compensation of a visible calibration offset [PK/INF].
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Literal, Optional

import numpy as np


def _arr(v, B, dtype=float):
    a = np.asarray(v, dtype=dtype)
    if a.ndim == 0:
        a = np.full(B, a, dtype=dtype)
    if a.shape != (B,):
        raise ValueError(f"parameter shape {a.shape} != ({B},)")
    return a.copy()


@dataclass
class UserParams:
    """Per-participant parameters (scalars, or arrays of length B)."""

    feedback_delay_ms: float | np.ndarray = 150.0  # visual feedback + processing delay
    reaction_ms: float | np.ndarray = 250.0  # time to start moving after stimulus onset
    kp: float | np.ndarray = 4.0  # 1/s, feedback gain (velocity users)
    vmax: float | np.ndarray = 900.0  # px/s, speed limit (velocity users)
    motor_noise: float | np.ndarray = 0.08  # signal-dependent noise (fraction of commanded speed)
    const_noise: float | np.ndarray = 5.0  # px/s or px, signal-independent noise
    aim_sd_frac: float | np.ndarray = 0.15  # aim-point SD as a fraction of target half-size
    select_margin: float | np.ndarray = 0.8  # user selects when within margin * half-size
    select_speed: float | np.ndarray = 150.0  # px/s, must be slower than this to click
    select_rt_ms: float | np.ndarray = 120.0  # delay from decision to click intent
    settle_ms: float | np.ndarray = 0.0  # must perceive the cursor inside this long before clicking
    no_verify_prob: float | np.ndarray = 0.0  # P(click at the end of a submovement without
    #   waiting for visual confirmation) - position users; produces realistic ISO errors
    # submovement users
    sub_tmin_ms: float | np.ndarray = 120.0
    sub_c: float | np.ndarray = 22.0  # ms per sqrt(px)
    sub_k: float | np.ndarray = 0.05  # endpoint SD = k * D / T(s)  (px with D in px, T in s)
    # gaze users
    saccade_ms: float | np.ndarray = 45.0
    fixation_jitter: float | np.ndarray = 6.0  # px SD
    offset_compensation: float | np.ndarray = 0.6  # 0 = never compensates offset, 1 = fully
    # simulated (not observed) state changes
    fatigue_per_min: float | np.ndarray = 0.0  # speed falls by 1/(1+f*min); noise rises
    def batch(self, B: int) -> "UserParams":
        return UserParams(**{f.name: _arr(getattr(self, f.name), B) for f in fields(self)})

    def subset(self, idx) -> "UserParams":
        return UserParams(**{f.name: np.asarray(getattr(self, f.name))[idx] for f in fields(self)})


class BaseUser:
    mode: Literal["velocity", "position"] = "velocity"

    def __init__(self, params: UserParams, B: int, dt_ms: float, rng: np.random.Generator):
        self.p = params.batch(B)
        self.B, self.dt, self.rng = B, dt_ms, rng
        self.fb_ticks = np.maximum(0, np.round(self.p.feedback_delay_ms / dt_ms)).astype(np.int64)
        self.max_fb = int(self.fb_ticks.max()) if B else 0
        self.hand = None  # position users keep a hand/gaze position

    # Called by the engine at the start of each acquisition step.
    def begin(self, target_c: np.ndarray, target_h: np.ndarray, cursor: np.ndarray,
              mask: np.ndarray, dwell: bool) -> None:
        raise NotImplementedError

    def act(self, perceived: np.ndarray, perceived_prev: np.ndarray, t_min: np.ndarray,
            active: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        raise NotImplementedError

    def _inside(self, p, c, h, margin):
        return (np.abs(p[:, 0] - c[:, 0]) <= h[:, 0] * margin) & \
               (np.abs(p[:, 1] - c[:, 1]) <= h[:, 1] * margin)


class FeedbackUser(BaseUser):
    mode = "velocity"

    def __init__(self, params, B, dt_ms, rng):
        super().__init__(params, B, dt_ms, rng)
        self.aim = np.zeros((B, 2))
        self.c = np.zeros((B, 2))
        self.h = np.ones((B, 2))
        self.wait = np.zeros(B)
        self.sel_count = np.full(B, -1.0)
        self.sel_hold = np.zeros(B)
        self.inside_ms = np.zeros(B)
        self.dwell = False

    def begin(self, target_c, target_h, cursor, mask, dwell):
        r = self.rng.standard_normal((self.B, 2)) * (self.p.aim_sd_frac[:, None] * target_h)
        self.aim[mask] = (target_c + r)[mask]
        self.inside_ms[mask] = 0
        self.c[mask] = target_c[mask]
        self.h[mask] = target_h[mask]
        rt = self.p.reaction_ms * np.exp(0.2 * self.rng.standard_normal(self.B) - 0.02)
        self.wait[mask] = rt[mask]
        self.sel_count[mask] = -1
        self.sel_hold[mask] = 0
        self.dwell = dwell

    def act(self, perceived, perceived_prev, t_min, active):
        p, B = self.p, self.B
        fat = 1.0 + p.fatigue_per_min * t_min
        err = self.aim - perceived
        u = p.kp[:, None] * err
        sp = np.hypot(u[:, 0], u[:, 1])
        vmax = p.vmax / fat
        scale = np.where(sp > vmax, vmax / np.maximum(sp, 1e-9), 1.0)
        u = u * scale[:, None]
        sp = np.minimum(sp, vmax)
        noise_sd = p.motor_noise * fat * sp + p.const_noise
        u = u + self.rng.standard_normal((B, 2)) * noise_sd[:, None]
        waiting = self.wait > 0
        u[waiting] = 0.0
        self.wait = np.maximum(0, self.wait - self.dt)
        # selection decision (click mode)
        sel = np.zeros(B, bool)
        if not self.dwell:
            pspeed = np.hypot(*(perceived - perceived_prev).T) * (1000.0 / self.dt)
            inside = self._inside(perceived, self.c, self.h, p.select_margin)
            self.inside_ms = np.where(inside, self.inside_ms + self.dt, 0.0)
            ready = inside & (pspeed < p.select_speed) & ~waiting & (self.inside_ms >= p.settle_ms)
            start = ready & (self.sel_count < 0) & (self.sel_hold <= 0)
            self.sel_count[start] = p.select_rt_ms[start]
            cancel = (~inside) & (self.sel_count > 0)
            self.sel_count[cancel] = -1
            fire = (self.sel_count >= 0) & (self.sel_count <= self.dt)
            self.sel_count = np.where(self.sel_count > 0, self.sel_count - self.dt, self.sel_count)
            self.sel_hold[fire] = 100.0  # hold the select intent 100 ms
            self.sel_count[fire] = -1
            sel = self.sel_hold > 0
            self.sel_hold = np.maximum(0, self.sel_hold - self.dt)
            # after a click attempt, re-aim slightly (in case it was not registered)
        return u * active[:, None], sel & active


def _minjerk(s):
    s = np.clip(s, 0, 1)
    return 10 * s ** 3 - 15 * s ** 4 + 6 * s ** 5


class SubmovementUser(BaseUser):
    """Position-control user (mouse / head pointer style)."""

    mode = "position"

    def __init__(self, params, B, dt_ms, rng):
        super().__init__(params, B, dt_ms, rng)
        self.hand = None
        self.phase = np.zeros(B, np.int8)  # 0 wait-then-plan, 1 moving, 2 selecting, 3 done
        self.timer = np.zeros(B)
        self.p0 = np.zeros((B, 2))
        self.p1 = np.zeros((B, 2))
        self.T = np.ones(B)
        self.s_elapsed = np.zeros(B)
        self.c = np.zeros((B, 2))
        self.h = np.ones((B, 2))
        self.aim = np.zeros((B, 2))
        self.sel_hold = np.zeros(B)
        self.dwell = False

    def begin(self, target_c, target_h, cursor, mask, dwell):
        if self.hand is None:
            self.hand = cursor.copy()
        r = self.rng.standard_normal((self.B, 2)) * (self.p.aim_sd_frac[:, None] * target_h)
        self.aim[mask] = (target_c + r)[mask]
        self.c[mask], self.h[mask] = target_c[mask], target_h[mask]
        rt = self.p.reaction_ms * np.exp(0.2 * self.rng.standard_normal(self.B) - 0.02)
        self.timer[mask] = rt[mask]
        self.phase[mask] = 0
        self.sel_hold[mask] = 0
        self.dwell = dwell

    def _plan(self, idx, perceived, t_min):
        p = self.p
        fat = (1.0 + p.fatigue_per_min * t_min)[idx]
        dvec = self.aim[idx] - perceived[idx]
        D = np.hypot(dvec[:, 0], dvec[:, 1])
        T_ms = (p.sub_tmin_ms[idx] + p.sub_c[idx] * np.sqrt(D)) * fat
        T_s = T_ms / 1000.0
        sd = p.sub_k[idx] * fat * D / np.maximum(T_s, 1e-3) / 10.0 + p.const_noise[idx]
        u = np.where(D[:, None] > 1e-6, dvec / np.maximum(D, 1e-9)[:, None], 0)
        perp = np.stack([-u[:, 1], u[:, 0]], 1)
        e_par = self.rng.standard_normal(len(idx)) * sd
        e_perp = self.rng.standard_normal(len(idx)) * sd * 0.5
        self.p0[idx] = self.hand[idx]
        self.p1[idx] = self.hand[idx] + dvec + u * e_par[:, None] + perp * e_perp[:, None]
        self.T[idx] = T_ms
        self.s_elapsed[idx] = 0
        self.phase[idx] = 1

    def act(self, perceived, perceived_prev, t_min, active):
        p, B = self.p, self.B
        sel = np.zeros(B, bool)
        # phase 0: waiting, then evaluate / plan
        ev = (self.phase == 0) & (self.timer <= 0) & active
        if ev.any():
            inside = self._inside(perceived, self.c, self.h, p.select_margin)
            go_sel = ev & inside & ~np.bool_(self.dwell)
            if go_sel.any():
                self.phase[go_sel] = 2
                self.timer[go_sel] = p.select_rt_ms[go_sel]
            plan = ev & ~inside
            if self.dwell:
                plan = ev & ~inside
                hold = ev & inside
                self.timer[hold] = p.feedback_delay_ms[hold]  # keep checking
            idx = np.nonzero(plan)[0]
            if idx.size:
                self._plan(idx, perceived, t_min)
        mv = self.phase == 1
        if mv.any():
            self.s_elapsed[mv] += self.dt
            s = self.s_elapsed[mv] / self.T[mv]
            self.hand[mv] = self.p0[mv] + (self.p1[mv] - self.p0[mv]) * _minjerk(s)[:, None]
            fin = np.zeros(B, bool)
            fin[mv] = s >= 1
            self.phase[fin] = 0
            self.timer[fin] = p.feedback_delay_ms[fin]  # wait to see where the cursor landed
            if not self.dwell:
                # some clicks are issued at the end of the movement, before visual verification,
                # trusting that the planned endpoint is on target (speed-accuracy trade-off)
                blind = fin & (self.rng.random(B) < p.no_verify_prob)
                self.phase[blind] = 2
                self.timer[blind] = p.select_rt_ms[blind] * 0.5
        sl = self.phase == 2
        if sl.any():
            fire = sl & (self.timer <= self.dt)
            self.sel_hold[fire] = 100.0
            self.phase[fire] = 3
        sel = self.sel_hold > 0
        self.sel_hold = np.maximum(0, self.sel_hold - self.dt)
        done_sel = (self.phase == 3) & (self.sel_hold <= 0)
        # if a click did not end the step (e.g. missed by the selection channel), re-evaluate
        self.phase[done_sel] = 0
        self.timer[done_sel] = p.feedback_delay_ms[done_sel] + 150.0
        self.timer = np.maximum(0, self.timer - self.dt)
        tremor = self.rng.standard_normal((B, 2)) * (p.const_noise * 0.05)[:, None]
        return self.hand + tremor, sel & active


class GazeUser(BaseUser):
    """Eye-gaze-like position pointer (simulated)."""

    mode = "position"

    def __init__(self, params, B, dt_ms, rng):
        super().__init__(params, B, dt_ms, rng)
        self.hand = None  # gaze point
        self.phase = np.zeros(B, np.int8)  # 0 latency, 1 saccade, 2 fixate, 3 selecting
        self.timer = np.zeros(B)
        self.g0 = np.zeros((B, 2))
        self.g1 = np.zeros((B, 2))
        self.fix_t = np.zeros(B)
        self.c = np.zeros((B, 2))
        self.h = np.ones((B, 2))
        self.aim = np.zeros((B, 2))
        self.sel_hold = np.zeros(B)
        self.dwell = True

    def begin(self, target_c, target_h, cursor, mask, dwell):
        if self.hand is None:
            self.hand = cursor.copy()
        r = self.rng.standard_normal((self.B, 2)) * (self.p.aim_sd_frac[:, None] * target_h)
        self.aim[mask] = (target_c + r)[mask]
        self.c[mask], self.h[mask] = target_c[mask], target_h[mask]
        lat = self.p.reaction_ms * np.exp(0.15 * self.rng.standard_normal(self.B) - 0.01)
        self.timer[mask] = lat[mask]
        self.phase[mask] = 0
        self.sel_hold[mask] = 0
        self.dwell = dwell

    def act(self, perceived, perceived_prev, t_min, active):
        p, B = self.p, self.B
        start = (self.phase == 0) & (self.timer <= 0) & active
        if start.any():
            self.g0[start] = self.hand[start]
            self.g1[start] = self.aim[start]
            self.timer[start] = p.saccade_ms[start]
            self.phase[start] = 1
        sac = (self.phase == 1)
        if sac.any():
            frac = 1 - np.clip(self.timer[sac] / np.maximum(p.saccade_ms[sac], 1), 0, 1)
            self.hand[sac] = self.g0[sac] + (self.g1[sac] - self.g0[sac]) * frac[:, None]
            land = sac & (self.timer <= self.dt)
            self.hand[land] = self.g1[land]
            self.phase[land] = 2
            self.fix_t[land] = 0
        fx = self.phase == 2
        if fx.any():
            self.fix_t[fx] += self.dt
            inside = self._inside(perceived, self.c, self.h, p.select_margin)
            check = fx & (self.fix_t >= p.feedback_delay_ms + 250.0)
            # compensate a visible offset by looking beside the target
            fix = check & ~inside
            if fix.any():
                comp = p.offset_compensation[fix][:, None]
                self.aim[fix] = self.aim[fix] + comp * (self.c[fix] - perceived[fix])
                self.phase[fix] = 0
                self.timer[fix] = 120.0
            if not self.dwell:
                go = fx & inside & (self.fix_t >= p.feedback_delay_ms)
                self.phase[go] = 3
                self.timer[go] = p.select_rt_ms[go]
        sl = self.phase == 3
        if sl.any():
            fire = sl & (self.timer <= self.dt)
            self.sel_hold[fire] = 100.0
            self.phase[fire] = 2
            self.fix_t[fire] = -400.0  # wait before re-evaluating after a click
        sel = self.sel_hold > 0
        self.sel_hold = np.maximum(0, self.sel_hold - self.dt)
        self.timer = np.maximum(0, self.timer - self.dt)
        jitter = self.rng.standard_normal((B, 2)) * p.fixation_jitter[:, None]
        return self.hand + jitter, sel & active


USER_MODELS = {"feedback": FeedbackUser, "submovement": SubmovementUser, "gaze": GazeUser}
