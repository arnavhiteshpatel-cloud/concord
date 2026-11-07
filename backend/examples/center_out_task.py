"""Center-out calibration task that publishes its cues over LSL.

Run it on the machine that shows the task to the participant. It publishes two LSL streams,
which BrainOS (or any LSL recorder, e.g. LabRecorder) attaches to the neural stream as
behavior + markers; liblsl ``time_correction`` maps them onto the neural stream's clock:

* ``Behavior`` (2 ch, ``cue_vx``/``cue_vy``, 50 Hz): the cued cursor velocity, the label the
  decoder is calibrated against (the participant is asked to attempt/imagine the movement).
* ``Markers`` (string): ``trial N target K``, ``go``, ``hold``, ``return``, ``rest``.

Each trial: rest at center -> go: the cue moves to one of 8 targets at constant speed ->
hold -> return to center. Target order is a seeded random permutation per block of 8.

    python backend/examples/center_out_task.py              # with a window (tkinter)
    python backend/examples/center_out_task.py --headless --trials 16

Then, in BrainOS: discover LSL streams, attach this task's ``-behavior`` and ``-markers``
streams to the neural stream, start the pipeline, record, calibrate (docs/LAB_GUIDE.md).

The streams are declared neither synthetic nor prerecorded: they are live cues. They are
*labels*, never intents. This is a research tool, not a clinical procedure.
"""

from __future__ import annotations

import argparse
import math
import random
import threading
import time
from dataclasses import dataclass

RATE_HZ = 50.0


@dataclass(frozen=True)
class Phase:
    name: str
    seconds: float


PHASES = (Phase("rest", 1.0), Phase("go", 1.0), Phase("hold", 0.5), Phase("return", 1.0))
RADIUS = 0.7


class CueSchedule:
    """Deterministic cue trajectory; ``at(t)`` -> (phase, trial, target, x, y, vx, vy)."""

    def __init__(self, trials: int, seed: int = 0) -> None:
        rng = random.Random(seed)
        self.targets: list[int] = []
        while len(self.targets) < trials:
            block = list(range(8))
            rng.shuffle(block)
            self.targets += block
        self.targets = self.targets[:trials]
        self.trial_s = sum(p.seconds for p in PHASES)
        self.duration_s = trials * self.trial_s

    def at(self, t: float) -> tuple[str, int, int, float, float, float, float]:
        trial = min(int(t // self.trial_s), len(self.targets) - 1)
        k = self.targets[trial]
        ux, uy = math.cos(2 * math.pi * k / 8), math.sin(2 * math.pi * k / 8)
        local = t - trial * self.trial_s
        for p in PHASES:
            if local < p.seconds or p is PHASES[-1]:
                frac = min(1.0, max(0.0, local / p.seconds))
                speed = RADIUS / p.seconds
                if p.name == "go":
                    return (
                        p.name,
                        trial,
                        k,
                        ux * RADIUS * frac,
                        uy * RADIUS * frac,
                        ux * speed,
                        uy * speed,
                    )
                if p.name == "hold":
                    return p.name, trial, k, ux * RADIUS, uy * RADIUS, 0.0, 0.0
                if p.name == "return":
                    r = RADIUS * (1 - frac)
                    return p.name, trial, k, ux * r, uy * r, -ux * speed, -uy * speed
                return p.name, trial, k, 0.0, 0.0, 0.0, 0.0
            local -= p.seconds
        raise AssertionError("unreachable")


class CueTask:
    def __init__(self, schedule: CueSchedule, source_id: str = "brainos-center-out") -> None:
        import pylsl

        self.pylsl = pylsl
        self.schedule = schedule
        self.source_id = source_id
        self.stop = threading.Event()
        self.state = schedule.at(0.0)
        self.samples = 0
        self.markers: list[str] = []
        b = pylsl.StreamInfo(
            "BrainOS center-out cues",
            "Behavior",
            2,
            RATE_HZ,
            pylsl.cf_float32,
            source_id + "-behavior",
        )
        self._describe(b, quantity="cue_velocity")
        chans = b.desc().append_child("channels")
        for label in ("cue_vx", "cue_vy"):
            c = chans.append_child("channel")
            c.append_child_value("label", label)
            c.append_child_value("unit", "workspace/s")
            c.append_child_value("type", "Velocity")
        m = pylsl.StreamInfo(
            "BrainOS center-out markers", "Markers", 1, 0.0, pylsl.cf_string, source_id + "-markers"
        )
        self._describe(m)
        self.beh_out = pylsl.StreamOutlet(b)
        self.mk_out = pylsl.StreamOutlet(m)

    @staticmethod
    def _describe(info: object, **extra: str) -> None:
        d = info.desc().append_child("brainos")  # type: ignore[attr-defined]
        d.append_child_value("synthetic", "false")
        d.append_child_value("prerecorded", "false")
        d.append_child_value("origin", "brainos:center-out-task")
        for k, v in extra.items():
            d.append_child_value(k, v)

    def run(self) -> None:
        clock = self.pylsl.local_clock
        t0 = clock() + 0.5
        last: tuple[str, int] | None = None
        i = 0
        while not self.stop.is_set():
            stamp = t0 + i / RATE_HZ
            t = stamp - t0
            if t >= self.schedule.duration_s:
                break
            now = clock()
            if stamp > now:
                time.sleep(stamp - now)
            self.state = phase, trial, k, _, _, vx, vy = self.schedule.at(t)
            if (phase, trial) != last:
                text = f"trial {trial} target {k}" if phase == "rest" else phase
                self.mk_out.push_sample([text], stamp)
                self.markers.append(text)
                last = (phase, trial)
            self.beh_out.push_sample([vx, vy], stamp)
            self.samples += 1
            i += 1
        self.stop.set()


def _window(task: CueTask) -> None:  # pragma: no cover - needs a display
    import tkinter as tk

    size = 600
    root = tk.Tk()
    root.title("BrainOS center-out cues")
    cv = tk.Canvas(root, width=size, height=size, bg="black")
    cv.pack()

    def px(x: float, y: float) -> tuple[float, float]:
        return size / 2 + x * size / 2.4, size / 2 - y * size / 2.4

    def draw() -> None:
        cv.delete("all")
        phase, trial, k, x, y, _, _ = task.state
        tx, ty = px(RADIUS * math.cos(2 * math.pi * k / 8), RADIUS * math.sin(2 * math.pi * k / 8))
        cv.create_oval(tx - 30, ty - 30, tx + 30, ty + 30, outline="#4a8", width=3)
        cx, cy = px(x, y)
        cv.create_oval(cx - 14, cy - 14, cx + 14, cy + 14, fill="#fc3")
        cv.create_text(10, 10, anchor="nw", fill="#aaa", text=f"trial {trial + 1}  {phase}")
        if task.stop.is_set():
            root.after(500, root.destroy)
        else:
            root.after(16, draw)

    draw()

    def close() -> None:
        task.stop.set()
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    root.mainloop()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--trials", type=int, default=40)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--source-id", default="brainos-center-out")
    ap.add_argument("--headless", action="store_true", help="publish cues without a window")
    args = ap.parse_args(argv)
    task = CueTask(CueSchedule(args.trials, args.seed), args.source_id)
    th = threading.Thread(target=task.run, daemon=True)
    th.start()
    print(f"publishing {args.source_id}-behavior / -markers for {task.schedule.duration_s:.0f} s")
    try:
        if args.headless:
            while th.is_alive():
                th.join(0.2)
        else:
            _window(task)
    except KeyboardInterrupt:
        pass
    task.stop.set()
    th.join(2)
    print(f"done: {task.samples} cue samples, {len(task.markers)} markers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
