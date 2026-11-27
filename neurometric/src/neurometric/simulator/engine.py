"""Closed-loop simulation engine.

virtual user --intent--> DegradedChannel --output--> cursor --(delayed perception)--> user

The engine runs a batch of B independent "acquisition steps": move to an item and select it,
by click or by dwell. Every task family that can be decomposed into acquisitions (target
acquisition, keyboard text entry, menu / form / communication board activities, drag and drop,
scrolling as 1-D acquisition) is simulated with this one primitive, so the same scoring code
applies to simulated and to recorded sessions.

The engine records both the degraded output (what a real measurement system would observe) and
ground truth that only a simulation knows (the intended selection times, dropout ticks, false
activations injected by the channel). Metrics computed for evaluation of the *measurement* must
use only the observable part; ground truth is used to validate them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from .decoder import DegradationConfig, DegradedChannel
from ..users.models import BaseUser, USER_MODELS, UserParams

DT_MS = 10.0
WORKSPACE = (1280.0, 800.0)


@dataclass
class StepResult:
    """Result of one batched acquisition step. Arrays have leading dimension B."""

    t_ms: np.ndarray  # (T,) tick times relative to step start
    traj: np.ndarray  # (B, T, 2) cursor positions (NaN after the element finished)
    sel_t: np.ndarray  # (B,) time of the terminating selection (NaN if none)
    sel_pos: np.ndarray  # (B, 2)
    sel_item: np.ndarray  # (B,) index of item selected, -1 = empty space, -2 = none (timeout)
    timed_out: np.ndarray  # (B,) bool
    n_empty_selects: np.ndarray  # (B,) selections on empty space that did not end the step
    entries: np.ndarray  # (B,) number of entries into the target item
    first_entry_t: np.ndarray  # (B,)
    start: np.ndarray  # (B, 2)
    target_c: np.ndarray  # (B, 2)
    target_h: np.ndarray  # (B, 2)
    n_ticks: np.ndarray  # (B,) ticks used
    # ground truth (simulation only)
    gt_intended_selects: np.ndarray  # (B,) number of selection intents issued by the user
    gt_false_selects: np.ndarray
    gt_missed_selects: np.ndarray
    gt_dropout_ms: np.ndarray
    gt_loc_ms: np.ndarray

    @property
    def success(self) -> np.ndarray:
        return self.sel_item == 0

    @property
    def end_pos(self) -> np.ndarray:
        """Final cursor position of each element (selection point or last sample)."""
        return self.sel_pos


class Simulation:
    """Holds persistent user + channel state for a batch across a sequence of steps."""

    def __init__(self, user_model: str, user_params: UserParams, degradation: DegradationConfig,
                 B: int, rng: np.random.Generator, start: Optional[np.ndarray] = None,
                 session_minutes: Optional[np.ndarray] = None, dt_ms: float = DT_MS,
                 workspace=WORKSPACE, control_mode: Optional[str] = None):
        cls = USER_MODELS[user_model]
        self.user: BaseUser = cls(user_params, B, dt_ms, rng)
        mode = control_mode or cls.mode
        self.mode = mode
        self.channel = DegradedChannel(degradation, B, dt_ms, mode, rng, session_minutes)
        self.B, self.dt, self.rng = B, dt_ms, rng
        self.ws = np.array(workspace, float)
        self.cursor = (np.tile(self.ws / 2, (B, 1)) if start is None
                       else np.asarray(start, float).copy())
        if self.user.mode == "position":
            self.user.hand = self.cursor.copy()
        self.hist_len = self.user.max_fb + 2
        self.hist = np.repeat(self.cursor[None], self.hist_len, 0)  # ring of past cursor positions
        self.hpos = 0
        self.clock_ms = np.zeros(B)

    def _perceived(self, ticks_back: np.ndarray) -> np.ndarray:
        idx = (self.hpos - ticks_back) % self.hist_len
        return self.hist[idx, np.arange(self.B)]

    def acquire(self, items: np.ndarray, target_index: Optional[np.ndarray] = None,
                dwell_ms: Optional[float] = None, max_ms: float = 15000.0,
                end_on_empty: bool = False, mask: Optional[np.ndarray] = None,
                record: bool = True) -> StepResult:
        """Run one acquisition step for all (masked) elements.

        items: (B, K, 4) rectangles [cx, cy, half_w, half_h]; item ``target_index`` is the target.
        dwell_ms: if set, selection happens when the cursor stays on one item for dwell_ms.
        end_on_empty: if True a selection on empty space ends the step (ISO sequence style).
        """
        B, dt = self.B, self.dt
        items = np.asarray(items, float)
        K = items.shape[1]
        tgt = np.zeros(B, np.int64) if target_index is None else np.asarray(target_index)
        active = np.ones(B, bool) if mask is None else np.asarray(mask, bool).copy()
        run_mask = active.copy()
        ar = np.arange(B)
        tc = items[ar, tgt, :2]
        th = items[ar, tgt, 2:]
        start = self.cursor.copy()
        self.user.begin(tc, th, self.cursor, active, dwell=dwell_ms is not None)
        T = int(np.ceil(max_ms / dt)) + 1
        traj = np.full((B, T, 2), np.nan) if record else None
        sel_t = np.full(B, np.nan)
        sel_pos = np.full((B, 2), np.nan)
        sel_item = np.full(B, -2, np.int64)
        n_empty = np.zeros(B, np.int64)
        entries = np.zeros(B, np.int64)
        first_entry = np.full(B, np.nan)
        was_in = np.zeros(B, bool)
        dwell_item = np.full(B, -1, np.int64)
        dwell_t = np.zeros(B)
        n_ticks = np.zeros(B, np.int64)
        intents = np.zeros(B, np.int64)
        prev_sel = np.zeros(B, bool)
        fs0 = self.channel.false_selects.copy()
        ms0 = self.channel.missed_selects.copy()
        do0 = self.channel.dropout_ticks.copy()
        lo0 = self.channel.loc_ticks.copy()

        def which_item(pos):
            dx = np.abs(pos[:, None, 0] - items[:, :, 0]) <= items[:, :, 2]
            dy = np.abs(pos[:, None, 1] - items[:, :, 1]) <= items[:, :, 3]
            inside = dx & dy
            any_in = inside.any(1)
            first = np.argmax(inside, 1)
            return np.where(any_in, first, -1)

        for k in range(T):
            if not active.any():
                break
            if record:
                traj[active, k] = self.cursor[active]
            perceived = self._perceived(self.user.fb_ticks)
            perceived_prev = self._perceived(self.user.fb_ticks + 1)
            intent, sel_int = self.user.act(perceived, perceived_prev, self.channel.t_min, active)
            intents += (sel_int & ~prev_sel & active)
            prev_sel = sel_int
            out, sel = self.channel.step(intent, sel_int, active)
            if self.mode == "velocity":
                newc = self.cursor + out * (dt / 1000.0)
            else:
                newc = out
            newc = np.clip(newc, 0, self.ws)
            self.cursor = np.where(active[:, None], newc, self.cursor)
            self.hpos = (self.hpos + 1) % self.hist_len
            self.hist[self.hpos] = self.cursor
            self.clock_ms += active * dt
            n_ticks += active
            cur_item = which_item(self.cursor)
            in_tgt = cur_item == tgt
            new_entry = in_tgt & ~was_in & active
            entries += new_entry
            first_entry = np.where(new_entry & np.isnan(first_entry), (k + 1) * dt, first_entry)
            was_in = np.where(active, in_tgt, was_in)
            if dwell_ms is not None:
                same = cur_item == dwell_item
                dwell_t = np.where(same & (cur_item >= 0), dwell_t + dt, 0.0)
                dwell_item = np.where(active, cur_item, dwell_item)
                fire = active & (cur_item >= 0) & (dwell_t >= dwell_ms)
            else:
                fire = active & sel
                empty = fire & (cur_item < 0)
                if not end_on_empty:
                    n_empty += empty
                    fire = fire & ~empty
            if fire.any():
                sel_t[fire] = (k + 1) * dt
                sel_pos[fire] = self.cursor[fire]
                sel_item[fire] = cur_item[fire]
                active &= ~fire
        timed_out = run_mask & (sel_item == -2)
        sel_pos[timed_out] = self.cursor[timed_out]
        if record:
            traj = traj[:, : int(n_ticks.max()) + 1] if n_ticks.max() > 0 else traj[:, :1]
        return StepResult(
            t_ms=np.arange(traj.shape[1]) * dt if record else np.array([]),
            traj=traj if record else np.empty((B, 0, 2)), sel_t=sel_t, sel_pos=sel_pos,
            sel_item=sel_item, timed_out=timed_out, n_empty_selects=n_empty, entries=entries,
            first_entry_t=first_entry, start=start, target_c=tc, target_h=th, n_ticks=n_ticks,
            gt_intended_selects=intents,
            gt_false_selects=self.channel.false_selects - fs0,
            gt_missed_selects=self.channel.missed_selects - ms0,
            gt_dropout_ms=(self.channel.dropout_ticks - do0) * dt,
            gt_loc_ms=(self.channel.loc_ticks - lo0) * dt,
        )

    def rest(self, ms: float) -> None:
        """Advance session time without task activity (rest between trials)."""
        self.channel.t_min = self.channel.t_min + ms / 60000.0
        self.clock_ms += ms
