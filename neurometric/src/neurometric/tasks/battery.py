"""The NeuroMetric digital functional task battery (v1, experimental).

Each task has a formal specification (construct, stimuli, timing, scoring, errors, completion,
assistance recording, accessibility notes, version). Stimuli are generated deterministically from
a seed in Python and exported as concrete JSON, so the browser and the simulator present exactly
the same stimuli (no cross-language random number generator is needed).

These tasks are ORIGINAL experimental tasks built from general HCI and rehabilitation principles.
They are not implementations of the Shirley Ryan AbilityLab Digital Assessment Interface or of any
licensed clinical instrument, and are not validated clinical outcome assessments.

Task space: 1280 x 800 CSS px canvas (origin top-left). Browsers scale the canvas to the viewport
but record events in task-space coordinates, so stimuli are geometrically identical everywhere.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

import numpy as np

BATTERY_VERSION = "1.0.0"
CANVAS = (1280, 800)


@dataclass
class TaskSpec:
    id: str
    family: str
    name: str
    version: str
    construct: str
    rationale: str
    stimuli: str
    timing: str
    scoring: list[str]
    errors: str
    completion: str
    assistance: str
    accessibility: str
    defaults: dict[str, Any] = field(default_factory=dict)
    simulated: bool = True  # has a simulation runner
    keep: bool = True
    keep_reason: str = ""


ASSIST_NOTE = ("Assistance is recorded as ASSIST events (setup, physical, verbal, troubleshooting, "
               "calibration, task_completion) by the participant, care partner or staff via the "
               "assistance panel; any assistance during a trial marks it 'assisted', never 'failed'.")

TASKS: list[TaskSpec] = [
    TaskSpec("A1", "target_acquisition", "Single target selection", "1.0.0",
             "Basic pointing and selection: can the user move to and select one target.",
             "Lowest-demand primitive; floor task for severe impairment; reaction and movement onset.",
             "Start button at canvas centre, then one circular target at random direction, "
             "distance D in {200, 350} px, width W in {80, 120} px.",
             "Stimulus onset = target shown (marker stimulus_on). MT = onset to terminating "
             "selection. Max 20 s per trial (configurable).",
             ["success", "movement_time_ms", "onset_ms", "path_efficiency", "endpoint_error_px"],
             "Selection outside the target = error (ends trial). Timeout = no selection by max time.",
             "12 trials or 6 minutes, whichever first; participant may pause at any time.",
             ASSIST_NOTE, "Large targets; no time pressure by default; works with click, dwell, "
             "switch-activated click; keyboard alternative Space/Enter at the cursor.",
             {"D": [200, 350], "W": [80, 120], "n": 12, "max_ms": 20000}),
    TaskSpec("A2", "target_acquisition", "Multidirectional target acquisition (ISO-style ring)",
             "1.0.0", "Speed-accuracy of aimed pointing (Fitts throughput).",
             "Follows the ISO 9241-411 multidirectional tapping paradigm so throughput is "
             "comparable to the HCI literature; varying D and W gives a range of difficulty.",
             "13 circular targets equally spaced on a circle of diameter D; the highlighted "
             "target alternates across the circle. D in {256, 512} px, W in {32, 64, 96} px "
             "(IDs 1.9-4.1 bits); conditions counterbalanced by seed.",
             "Sequential: MT = time between successive selections (first selection of each "
             "sequence starts the clock and is not scored). Max 15 s per selection.",
             ["fitts_throughput_bps (effective, per condition then averaged)", "error_rate",
              "movement_time_ms", "path_efficiency", "target_reentries", "overshoot_px",
              "movement_variability_px", "dial_in_ms"],
             "Selection outside the highlighted target = miss (counts in We; trial ends).",
             "6 conditions x 13 selections; ~3-6 min with mouse.",
             ASSIST_NOTE, "Smallest W (32 px) can be excluded via the accessibility profile "
             "(target_min_px); throughput then computed only over administered conditions.",
             {"D": [256, 512], "W": [32, 64, 96], "n_per_condition": 13, "max_ms": 15000}),
    TaskSpec("A3", "target_acquisition", "Dwell selection", "1.0.0",
             "Selection by holding the pointer still (gaze / head-pointer style).",
             "Dwell is the dominant selection method for eye-gaze and many head-pointer users; "
             "isolates stability (holding still) from clicking.",
             "Same geometry as A2 with D=384, W in {64, 96}; dwell threshold configurable "
             "(default 800 ms).", "MT includes the dwell time; dwell resets when the pointer "
             "leaves the item.", ["success", "movement_time_ms", "dwell_resets",
                                  "unintended_dwell_selections"],
             "Dwell completed on a non-target item = unintended selection (Midas-touch error).",
             "2 conditions x 13 selections.", ASSIST_NOTE,
             "Dwell threshold and visual dwell-progress indicator configurable.",
             {"D": [384], "W": [64, 96], "n_per_condition": 13, "dwell_ms": 800, "max_ms": 15000}),
    TaskSpec("A4", "target_acquisition", "Selection among distractors (grid)", "1.0.0",
             "Choosing one item among many: the core of on-screen keyboards, menus and "
             "communication boards.",
             "Allows achieved-bitrate (penalised for errors) comparable to BCI grid tasks.",
             "Grid of R x C square items (default 4 x 6, 120 px cells, 100 px items); one cued "
             "item per trial; cue sequence from seed.",
             "MT = cue onset to selection; max 20 s.",
             ["success", "movement_time_ms", "achieved_bitrate_bps", "wolpaw_itr_bpm (flagged)",
              "wrong_item_selections"],
             "Selecting a non-cued item = wrong selection (ends trial). Empty-space clicks are "
             "counted but do not end the trial.",
             "24 trials.", ASSIST_NOTE, "Cell size configurable; scanning order for switch users.",
             {"rows": 4, "cols": 6, "cell": 120, "item": 100, "n": 24, "max_ms": 20000}),
    TaskSpec("A5", "target_acquisition", "Time-constrained acquisition", "1.0.0",
             "Ability to act within a deadline (e.g. answering a prompt in time).",
             "Real interfaces impose time limits (call answer, dialog timeout); success-within-"
             "deadline is interpretable for function.",
             "As A1 with deadline in {2000, 4000} ms.", "Trial ends at deadline.",
             ["success_within_deadline", "movement_time_ms"],
             "No selection by deadline = timeout error.", "16 trials.", ASSIST_NOTE,
             "Off by default for participants whose profile sets 'no time pressure' "
             "(WCAG 2.2.1 adjustable timing).",
             {"D": [250], "W": [100], "deadline_ms": [2000, 4000], "n": 16}),
    TaskSpec("B1", "cursor_control", "Straight-line steering (tunnel)", "1.0.0",
             "Constrained movement along a path (steering law).",
             "Captures path control that aimed pointing does not (e.g. dragging along menus).",
             "Horizontal tunnel of length 600 px, width in {40, 80} px; start and end zones.",
             "MT = leaving the start zone to entering the end zone.",
             ["success", "movement_time_ms", "tunnel_exits", "rms_path_deviation_px"],
             "Leaving the tunnel = exit error (trial continues; count reported).",
             "8 trials.", ASSIST_NOTE, "Tunnel width configurable.",
             {"L": 600, "W": [40, 80], "n": 8}),
    TaskSpec("B2", "cursor_control", "Continuous tracking", "1.0.0",
             "Continuous closed-loop control; sensitive to latency and smoothing.",
             "Discrete selections can hide latency; tracking exposes it directly (lag).",
             "Target moves on a sum-of-sines path (0.1-0.4 Hz components), 30 s per trial; "
             "target radius 40 px.", "Sampled at display rate; first 3 s excluded.",
             ["rms_error_px", "time_on_target", "lag_ms"], "None (continuous).",
             "3 trials of 30 s.", ASSIST_NOTE, "Speed scale configurable; reduced-motion "
             "profiles substitute a slower path.", {"duration_ms": 30000, "radius": 40, "n": 3}),
    TaskSpec("C1", "scrolling", "Scroll to target", "1.0.0",
             "Navigating long content by scrolling.",
             "Scrolling is one of the commonest real digital actions and uses a different control "
             "mapping (rate control) from pointing.",
             "Vertical list of 60 items (60 px rows) in a 400 px viewport; cued item must be "
             "brought into the highlighted band and selected; direction up or down.",
             "Time from cue to selection; max 30 s.", ["success", "time_to_select_ms",
                                                      "band_passes", "reversals"],
             "Selecting while the cued item is outside the band = error.", "10 trials.",
             ASSIST_NOTE, "Scroll by wheel, scroll buttons (for switch / dwell), or keys.",
             {"rows": 60, "row_px": 60, "viewport_px": 400, "n": 10, "max_ms": 30000}),
    TaskSpec("D1", "drag_and_drop", "Drag object to zone", "1.0.0",
             "Selecting, holding and relocating an object (hold-state reliability).",
             "Dragging requires sustained selection; BCI click decoders and dwell systems "
             "often struggle with holds.",
             "Object (60 px) at start; drop zone width in {80, 160} px at D=400 px.",
             "Time from cue to successful drop; max 30 s.",
             ["success", "time_ms", "unintended_drops", "placement_error_px"],
             "Release outside the zone = drop error (object stays; participant re-grabs).",
             "10 trials.", ASSIST_NOTE, "Drag-lock mode (click to pick up, click to drop) "
             "available for users who cannot hold.", {"D": 400, "zone": [80, 160], "n": 10}),
    TaskSpec("E1", "text_communication", "Copy typing (on-screen keyboard)", "1.0.0",
             "Written communication rate and accuracy.",
             "Communication is the highest-value outcome for people with paralysis; copy "
             "typing gives a controlled, content-free measure (no private text).",
             "Presented phrases from NeuroMetric's original phrase set (short, common, "
             "lowercase); on-screen QWERTY keyboard with space and backspace; pointer or scanning.",
             "Clock starts at first keystroke; ends at the Done key or time limit (3 min/phrase).",
             ["wpm", "ccpm", "msd_error_rate", "total_error_rate", "kspc", "correction_burden"],
             "Uncorrected errors (MSD) and corrected errors (IF) reported separately.",
             "5 phrases.", ASSIST_NOTE, "Key size, scanning rate and dwell configurable; no "
             "free text is stored.", {"n_phrases": 5, "key": 90}),
    TaskSpec("E2", "text_communication", "Structured phrase selection", "1.0.0",
             "Message selection from a set (AAC-style communication).",
             "Many AAC users communicate via phrase/word selection rather than spelling.",
             "Board of 12 phrases; spoken/written cue names the phrase to select.",
             "MT = cue to selection.", ["success", "movement_time_ms", "achieved_bitrate_bps"],
             "Wrong phrase = error.", "12 trials.", ASSIST_NOTE, "Large tiles; scanning order.",
             {"n": 12}),
    TaskSpec("F1", "digital_adl", "Select a contact (simulated)", "1.0.0",
             "Simulated digital activity: find and open a contact.",
             "Ecological composite of scroll + select; in-app only, no real contacts.",
             "Simulated contact list (fictional names) with 20 entries; target named in cue.",
             "Time to complete; steps logged.", ["completed", "time_to_complete_ms",
                                                 "wrong_selections", "assisted"],
             "Opening the wrong contact = error; 'back' returns.", "1 trial per session.",
             ASSIST_NOTE, "All controls reachable by keyboard / scanning.", {}),
    TaskSpec("F2", "digital_adl", "Compose a predefined message (simulated)", "1.0.0",
             "Communication activity: open a conversation and send a predefined message "
             "composed from tiles.", "In-app only; nothing is sent.",
             "Open messages -> choose recipient -> select 3 message tiles -> press send.",
             "Time to complete.", ["completed", "time_to_complete_ms", "wrong_selections",
                                   "assisted"], "Wrong tile/recipient = error.",
             "1 trial per session.", ASSIST_NOTE, "", {}),
    TaskSpec("F3", "digital_adl", "Menu navigation (simulated)", "1.0.0",
             "Navigate a two-level application menu.", "Common desktop interaction.",
             "Menu bar with 5 menus x 6 items; target named in cue.", "Time to complete.",
             ["completed", "time_to_complete_ms", "wrong_selections", "assisted"],
             "Wrong menu or item = error.", "4 trials.", ASSIST_NOTE, "", {}),
    TaskSpec("F4", "digital_adl", "Calendar booking (simulated)", "1.0.0",
             "Schedule an appointment: pick a date, a time slot, confirm.",
             "Multi-step goal-directed activity.", "Month grid + time-slot list + confirm.",
             "Time to complete.", ["completed", "time_to_complete_ms", "wrong_selections",
                                   "assisted"], "Wrong date/slot = error.", "1 trial.",
             ASSIST_NOTE, "", {}),
    TaskSpec("F5", "digital_adl", "Form completion (simulated)", "1.0.0",
             "Fill a short form with predefined choices (no personal data).",
             "Forms are ubiquitous in health portals and daily admin.",
             "4 fields with choice buttons + submit.", "Time to complete.",
             ["completed", "time_to_complete_ms", "wrong_selections", "assisted"],
             "Wrong choice = error.", "1 trial.", ASSIST_NOTE, "", {}),
    TaskSpec("F6", "digital_adl", "Communication board (simulated)", "1.0.0",
             "Express a predefined need using a symbol/word board (AAC).",
             "Core AAC interaction.", "4 x 5 board of words; build a 3-word message.",
             "Time to complete.", ["completed", "time_to_complete_ms", "wrong_selections",
                                   "assisted"], "Wrong word = error (delete key available).",
             "2 trials.", ASSIST_NOTE, "", {}),
    TaskSpec("F7", "digital_adl", "Simulated browser navigation", "1.0.0",
             "Follow a link on a simulated web page and find a named item.",
             "Web use is a key participation activity.", "Static simulated page with links.",
             "Time to complete.", ["completed", "time_to_complete_ms", "wrong_selections",
                                   "assisted"], "Wrong link = error ('back' available).",
             "1 trial.", ASSIST_NOTE, "No external network access.", {}),
]

EXCLUDED = [
    {"id": "B-obstacle", "name": "Obstacle navigation",
     "reason": "Overlaps with B1 steering and A4 selection among distractors; adds layout "
               "complexity without a distinct construct. Kept as a web demo only."},
    {"id": "E-free", "name": "Free text entry",
     "reason": "Requires storing personal text; offered only with explicit consent and never "
               "stored by default (character counts and timing only)."},
]


# --------------------------------------------------------------------------- stimuli

def _seed(*parts) -> int:
    h = hashlib.sha256("|".join(map(str, parts)).encode()).hexdigest()
    return int(h[:16], 16)


def iso_ring(D: float, W: float, n: int = 13, center=(640, 400)) -> list[dict]:
    """ISO 9241-411 ordering: target i, then the one roughly opposite (i + (n+1)//2) mod n."""
    cx, cy = center
    order, k = [], 0
    for _ in range(n):
        order.append(k)
        k = (k + (n + 1) // 2) % n
    pts = []
    for idx in order:
        a = 2 * np.pi * idx / n - np.pi / 2
        pts.append({"x": round(cx + D / 2 * np.cos(a), 2), "y": round(cy + D / 2 * np.sin(a), 2),
                    "w": W, "idx": idx})
    return pts


def grid_items(rows: int, cols: int, cell: float, item: float, center=(640, 400)) -> list[dict]:
    x0 = center[0] - cols * cell / 2 + cell / 2
    y0 = center[1] - rows * cell / 2 + cell / 2
    return [{"id": r * cols + c, "x": x0 + c * cell, "y": y0 + r * cell, "w": item, "h": item}
            for r in range(rows) for c in range(cols)]


KEY_ROWS = ["qwertyuiop", "asdfghjkl", "zxcvbnm"]


def keyboard_layout(key: float = 90, gap: float = 8, top: float = 430) -> list[dict]:
    """On-screen QWERTY keyboard in task space. Special keys: ' ' (space), '\\b' backspace."""
    keys = []
    pitch = key + gap
    for r, row in enumerate(KEY_ROWS):
        width = len(row) * pitch
        x0 = 640 - width / 2 + pitch / 2 + (r * pitch / 4)
        for i, ch in enumerate(row):
            keys.append({"key": ch, "x": x0 + i * pitch, "y": top + r * pitch, "w": key, "h": key})
    y = top + 3 * pitch
    keys.append({"key": " ", "x": 640 - pitch, "y": y, "w": 5 * pitch - gap, "h": key})
    keys.append({"key": "\b", "x": 640 + 2.5 * pitch, "y": y, "w": 2 * pitch - gap, "h": key})
    return keys


# Original phrase set written for NeuroMetric (no third-party phrase set is reproduced).
PHRASES = [
    "the kettle is on", "please open the window", "i would like some water",
    "call me after lunch", "the game starts at seven", "turn the music down",
    "my feet are cold", "thank you for coming", "see you next week", "can you help me",
    "the book is on the table", "it is sunny outside", "i am a little tired",
    "let us watch a movie", "where are my glasses", "please close the door",
    "i need a short break", "good morning to you", "how was your day", "the bus was late",
]


def stimuli(task_id: str, seed: int = 0, overrides: Optional[dict] = None) -> dict:
    """Concrete, reproducible stimuli for a task (identical for browser and simulator)."""
    spec = next(t for t in TASKS if t.id == task_id)
    p = {**spec.defaults, **(overrides or {})}
    rng = np.random.default_rng(_seed(task_id, BATTERY_VERSION, seed))
    out: dict[str, Any] = {"task_id": task_id, "battery_version": BATTERY_VERSION,
                           "seed": seed, "params": p, "canvas": CANVAS}
    if task_id in ("A2", "A3"):
        conds = [(D, W) for D in p["D"] for W in p["W"]]
        rng.shuffle(conds)
        out["blocks"] = [{"D": D, "W": W, "targets": iso_ring(D, W, p["n_per_condition"])}
                         for D, W in conds]
    elif task_id in ("A1", "A5"):
        trials = []
        n = p["n"]
        Ds, Ws = p["D"], p["W"]
        dls = p.get("deadline_ms", [p.get("max_ms", 20000)])
        for i in range(n):
            a = rng.uniform(0, 2 * np.pi)
            D, W, dl = Ds[i % len(Ds)], Ws[(i // len(Ds)) % len(Ws)], dls[i % len(dls)]
            trials.append({"start": {"x": 640, "y": 400}, "x": round(640 + D * np.cos(a), 2),
                           "y": round(400 + D * np.sin(a) * 0.9, 2), "w": W, "D": D,
                           "deadline_ms": dl})
        out["trials"] = trials
    elif task_id == "A4":
        items = grid_items(p["rows"], p["cols"], p["cell"], p["item"])
        cues = rng.integers(0, len(items), p["n"]).tolist()
        out.update(items=items, cues=cues)
    elif task_id == "E1":
        idx = rng.choice(len(PHRASES), p["n_phrases"], replace=False).tolist()
        out.update(phrases=[PHRASES[i] for i in idx], keys=keyboard_layout(p["key"]))
    elif task_id == "C1":
        cues = []
        for i in range(p["n"]):
            cues.append(int(rng.integers(8, p["rows"] - 8)))
        out["cues"] = cues
    elif task_id == "D1":
        out["trials"] = [{"zone": p["zone"][i % len(p["zone"])],
                          "angle": float(rng.uniform(0, 2 * np.pi))} for i in range(p["n"])]
    elif task_id == "B2":
        comps = [{"f": f, "ax": float(rng.uniform(80, 220)), "ay": float(rng.uniform(60, 160)),
                  "px": float(rng.uniform(0, 6.28)), "py": float(rng.uniform(0, 6.28))}
                 for f in (0.1, 0.17, 0.27, 0.4)]
        out["path"] = comps
    out["stimulus_hash"] = hashlib.sha256(json.dumps(out, sort_keys=True, default=float)
                                          .encode()).hexdigest()[:16]
    return out


def battery_manifest() -> dict:
    return {"battery_version": BATTERY_VERSION, "canvas": CANVAS,
            "status": "experimental - not a validated clinical outcome assessment",
            "tasks": [asdict(t) for t in TASKS], "excluded": EXCLUDED}
