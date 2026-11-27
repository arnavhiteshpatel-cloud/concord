from datetime import datetime, timedelta, timezone

import pytest

from neurometric.adapters.probes.contract import Aggregator, ProbeSample
from neurometric.study.telemetry import validate_payload

T0 = datetime(2027, 1, 5, 9, 0, tzinfo=timezone.utc)


def samples(n, active=True, assisted=True):
    return [ProbeSample(T0 + timedelta(minutes=i), active, {"pointer": 10, "select": 1}, assisted)
            for i in range(n)]


def test_aggregate_payload_passes_server_allowlist():
    ag = Aggregator("NM-ABCDEFGHIJ", "devsess_0001", "windows")
    for s in samples(30) + samples(10, active=False, assisted=False)[0:0]:
        ag.add(s)
    p = ag.flush(T0, T0 + timedelta(hours=1), fatigue=3)
    assert p["active_minutes"] == 30 and p["interaction_counts"]["pointer"] == 300
    assert p["device_assisted_sessions"] == 1
    assert validate_payload(p) == []


def test_pause_and_consent_drop_at_source():
    ag = Aggregator("NM-ABCDEFGHIJ", "devsess_0001", "android")
    ag.paused = True
    for s in samples(5):
        ag.add(s)
    ag.paused = False
    assert ag.flush(T0, T0 + timedelta(hours=1))["active_minutes"] == 0
    ag.consent_active = False
    ag.add(samples(1)[0])
    assert ag.flush(T0, T0 + timedelta(hours=1)) is None


def test_probe_cannot_report_content():
    ag = Aggregator("NM-ABCDEFGHIJ", "devsess_0001", "macos")
    with pytest.raises(ValueError):
        ag.add(ProbeSample(T0, True, {"keystrokes": 5}))
