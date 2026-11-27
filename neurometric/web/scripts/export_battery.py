"""Export the NeuroMetric battery stimuli (Python is the source of truth) for the web app.

Writes web/public/battery/<TASK>.json (stimuli(task_id, seed=0)), manifest.json
(battery_manifest()), phrases.json (the original phrase set, used by E2) and adl_layouts.json
(the digital-ADL screen geometry shared with the simulator). Run from anywhere:

    python web/scripts/export_battery.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT / "src"))

from neurometric.tasks.battery import PHRASES, TASKS, battery_manifest, stimuli  # noqa: E402
from neurometric.simulator.tasks import adl_layouts  # noqa: E402

OUT = HERE.parent / "public" / "battery"


def main(seed: int = 0) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    index = []
    for t in TASKS:
        s = stimuli(t.id, seed)
        (OUT / f"{t.id}.json").write_text(json.dumps(s, indent=1, default=float) + "\n")
        index.append({"id": t.id, "stimulus_hash": s["stimulus_hash"], "seed": seed})
    man = battery_manifest()
    man["exported"] = index
    (OUT / "manifest.json").write_text(json.dumps(man, indent=1, default=float) + "\n")
    (OUT / "phrases.json").write_text(json.dumps({"phrases": PHRASES}, indent=1) + "\n")
    (OUT / "adl_layouts.json").write_text(json.dumps(adl_layouts(), indent=1, default=float) + "\n")
    print(f"wrote {len(index)} task stimuli to {OUT}")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 0)
