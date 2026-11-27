"""Experiment S (server side): event processing throughput/latency and export integrity.

Measures, on this machine: canonical-event validation rate, stream integrity check rate,
segmentation + scoring time for a realistic session, JSON serialisation round-trip integrity
(SHA-256 identical after re-export), and peak memory of the scoring step.
"""
from __future__ import annotations

import hashlib
import json
import platform
import time
import tracemalloc

import numpy as np
import pandas as pd

from ..adapters.sessions import events_to_pointing_trials, step_to_events
from ..events.model import InputEvent, check_stream, validate_event
from ..metrics.pointing import trial_metrics
from ..simulator.decoder import PROFILES
from ..simulator.engine import Simulation
from ..users.models import UserParams
from .core import save, write_summary


def make_session(n_trials=60, seed=0):
    rng = np.random.default_rng(seed)
    sim = Simulation("feedback", UserParams(), PROFILES["bci_good"], 1, rng)
    evs = []
    t = 0.0
    for k in range(n_trials):
        a = rng.uniform(0, 2 * np.pi)
        items = np.array([[[640 + 300 * np.cos(a), 400 + 250 * np.sin(a), 40, 40]]])
        st = sim.acquire(items, max_ms=8000)
        e = step_to_events(st, "ses_perf", t_offset_ms=t, trial_offset=k)[0]
        evs.extend(e)
        t = evs[-1].t_ms + 500
    # re-sequence into one stream
    return [InputEvent(**{**e.__dict__, "seq": i}) for i, e in enumerate(evs)]


def main():
    rows = []
    evs = make_session()
    n = len(evs)
    for rep in range(5):
        t0 = time.perf_counter()
        for e in evs:
            validate_event(e)
        t1 = time.perf_counter()
        rep_chk = check_stream(evs)
        t2 = time.perf_counter()
        tracemalloc.start()
        tr = events_to_pointing_trials(evs)
        m = trial_metrics(tr)
        _, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        t3 = time.perf_counter()
        blob = json.dumps([e.to_dict() for e in evs], sort_keys=True).encode()
        h1 = hashlib.sha256(blob).hexdigest()
        back = [InputEvent.from_dict(d) for d in json.loads(blob)]
        h2 = hashlib.sha256(json.dumps([e.to_dict() for e in back], sort_keys=True).encode()).hexdigest()
        t4 = time.perf_counter()
        rows.append({"rep": rep, "n_events": n, "n_trials": len(tr),
                     "validate_events_per_s": n / (t1 - t0), "check_stream_events_per_s": n / (t2 - t1),
                     "segment_and_score_ms": (t3 - t2) * 1000, "score_peak_mem_mb": peak / 1e6,
                     "json_roundtrip_ms": (t4 - t3) * 1000, "roundtrip_hash_identical": h1 == h2,
                     "json_bytes": len(blob)})
    df = pd.DataFrame(rows)
    save("S_event_latency", "python_pipeline", df)
    # incremental per-event latency: validate + append (what a live recorder does per event)
    lat = []
    for e in evs[:5000]:
        a = time.perf_counter_ns()
        validate_event(e)
        lat.append((time.perf_counter_ns() - a) / 1000)
    lat = np.array(lat)
    summ = {"machine": {"python": platform.python_version(), "processor": platform.processor() or platform.machine()},
            "session": {"events": n, "trials": int(rows[0]["n_trials"])},
            "median": df.drop(columns=["rep"]).median(numeric_only=True).to_dict(),
            "all_roundtrips_identical": bool(df.roundtrip_hash_identical.all()),
            "per_event_validate_us": {"p50": float(np.percentile(lat, 50)), "p99": float(np.percentile(lat, 99)),
                                      "max": float(lat.max())},
            "stream_check": {k: v for k, v in rep_chk.items() if k != "streams"},
            "synthetic": True,
            "note": "Server-side processing cost only. Browser-side timing is in browser_*.json from the web test suite."}
    write_summary("S_event_latency", summ)
    print(json.dumps(summ["median"], indent=1))


if __name__ == "__main__":
    main()
