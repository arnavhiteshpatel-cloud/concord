"""Validate browser-exported NeuroMetric sessions with the Python reference implementation.

Usage: python tests/web/validate_runs.py <runs.json>
Prints one JSON object: per run, the validation errors (validate_event), the check_stream report
of the merged timeline, and the authoritative server-side scores (score_session).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from neurometric.events.model import (EventValidationError, InputEvent, check_stream,  # noqa: E402
                                      merge_streams, validate_event)
from neurometric.study.scoring import score_session  # noqa: E402
from neurometric.tasks.battery import stimuli  # noqa: E402


def main(path: str) -> None:
    runs = json.loads(Path(path).read_text())
    out = []
    for run in runs:
        errors, events = [], []
        for i, d in enumerate(run["events"]):
            try:
                ev = InputEvent.from_dict(d)
                validate_event(ev)
                events.append(ev)
            except (EventValidationError, KeyError, TypeError, ValueError) as e:
                errors.append(f"event {i}: {e}")
        by_stream: dict[str, list] = {}
        for e in events:
            by_stream.setdefault(e.stream_id, []).append(e)
        merged = merge_streams(*by_stream.values())
        key = lambda e: (e.t_ms, e.stream_id, e.seq)  # noqa: E731
        order_ok = [key(e) for e in merged] == [key(e) for e in events]
        stim = stimuli(run["task_id"], int(run["stimulus_seed"]))
        out.append({
            "task_id": run["task_id"],
            "n_events": len(run["events"]),
            "validation_errors": errors[:20],
            "n_validation_errors": len(errors),
            "stream_report": check_stream(events),
            "merge_order_matches_python": order_ok,
            "stimulus_hash_matches": stim["stimulus_hash"] == run["stimulus_hash"],
            "kinds": sorted({e.kind.value for e in events}),
            "assist_types": sorted({e.meta.get("assist_type") for e in events if e.kind.value == "assist"}),
            "scores": score_session(run["task_id"], events, int(run["stimulus_seed"])),
        })
    print(json.dumps(out, default=str))


if __name__ == "__main__":
    main(sys.argv[1])
