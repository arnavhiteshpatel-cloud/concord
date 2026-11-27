"""NeuroMetric command line.

  neurometric battery export DIR            write battery manifest + seeded stimuli JSON
  neurometric score EVENTS.json             score a recorded pointing session (canonical events)
  neurometric import-concord FILE.jsonl     convert a Concord recording to canonical events JSON
  neurometric experiments [IDS...]          run computational experiments
  neurometric report demo DIR               build the 7 evidence report types on SYNTHETIC demo data
  neurometric serve [--db PATH] [--port N]  run the local research server (API + web app)
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _battery(a):
    from .tasks.battery import TASKS, battery_manifest, stimuli
    d = Path(a.dir)
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps(battery_manifest(), indent=1))
    for t in TASKS:
        (d / f"{t.id}.json").write_text(json.dumps(stimuli(t.id, a.seed), default=float))
    print(f"wrote {len(TASKS) + 1} files to {d}")


def _score(a):
    import numpy as np
    from .adapters.sessions import events_to_pointing_trials
    from .events.model import InputEvent, check_stream, validate_event
    from .metrics.pointing import trial_metrics
    evs = [InputEvent.from_dict(d) for d in json.loads(Path(a.events).read_text())]
    for e in evs:
        validate_event(e)
    tr = events_to_pointing_trials(evs)
    m = trial_metrics(tr)
    out = {"integrity": {k: v for k, v in check_stream(evs).items() if k != "streams"},
           "n_trials": len(tr),
           "summary": {k: float(np.nanmean(v.astype(float))) for k, v in m.items()}}
    print(json.dumps(out, indent=1))


def _concord(a):
    from .adapters.concord import import_recording
    evs = import_recording(a.file)
    out = Path(a.out or Path(a.file).with_suffix(".neurometric.json"))
    out.write_text(json.dumps([e.to_dict() for e in evs]))
    print(f"{len(evs)} events -> {out}")


def _experiments(a):
    from .experiments.registry import main as run
    run(a.ids + (["--processes", str(a.processes)]))


def _report(a):
    from .reports.evidence import REPORT_TYPES, build_report, demo_psychometrics, demo_study
    sd = demo_study(n=a.n)
    psy = demo_psychometrics(n=a.n)
    for r in REPORT_TYPES:
        build_report(sd, r, a.dir, psychometrics=psy if r in ("psychometric_validation", "evidence_package") else None)
    print(f"wrote {len(REPORT_TYPES)} SYNTHETIC demo reports to {a.dir}")


def _serve(a):
    try:
        from .api.app import create_app
    except ImportError as e:  # pragma: no cover
        sys.exit(f"API not available: {e}")
    import uvicorn
    uvicorn.run(create_app(a.db), host=a.host, port=a.port)


def main(argv=None):
    p = argparse.ArgumentParser(prog="neurometric", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("battery")
    b.add_argument("action", choices=["export"])
    b.add_argument("dir")
    b.add_argument("--seed", type=int, default=0)
    b.set_defaults(f=_battery)
    s = sub.add_parser("score")
    s.add_argument("events")
    s.set_defaults(f=_score)
    c = sub.add_parser("import-concord")
    c.add_argument("file")
    c.add_argument("--out")
    c.set_defaults(f=_concord)
    e = sub.add_parser("experiments")
    e.add_argument("ids", nargs="*")
    e.add_argument("--processes", type=int, default=4)
    e.set_defaults(f=_experiments)
    r = sub.add_parser("report")
    r.add_argument("action", choices=["demo"])
    r.add_argument("dir")
    r.add_argument("--n", type=int, default=24)
    r.set_defaults(f=_report)
    v = sub.add_parser("serve")
    v.add_argument("--db", default="neurometric.db")
    v.add_argument("--host", default="127.0.0.1")
    v.add_argument("--port", type=int, default=8000)
    v.set_defaults(f=_serve)
    a = p.parse_args(argv)
    a.f(a)


if __name__ == "__main__":
    main()
