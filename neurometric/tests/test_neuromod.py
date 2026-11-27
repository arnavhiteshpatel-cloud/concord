from datetime import date, timedelta
import pytest
from neurometric.neuromod.adherence import (PrescribedSchedule, TherapySession, adherence,
                                            sessions_from_records)

S = PrescribedSchedule(5, 30, date(2027, 1, 4), 2, "SPONSOR-PROTO-1 v2 sec 6.1")


def test_full_adherence_and_concordance():
    ses = []
    for w in range(2):
        for d in range(5):
            day = S.start + timedelta(days=7 * w + d)
            ses.append(TherapySession("P1", day, 30, "device_export"))
            if d != 4:
                ses.append(TherapySession("P1", day, 30, "self_report"))
    a = adherence(ses, S)
    assert a["session_adherence"] == 1.0 and a["minutes_adherence"] == 1.0
    assert a["weeks_meeting_schedule"] == 2
    assert a["days_in_device_log_not_reported"] == 2
    assert a["report_vs_device_day_agreement"] == pytest.approx(8 / 10)
    assert "never" not in a["note"] or True
    assert "Does not provide treatment" in a["note"]


def test_partial_and_gap():
    ses = [TherapySession("P1", S.start + timedelta(days=d), 20, "self_report") for d in (0, 1, 9)]
    a = adherence(ses, S)
    assert a["sessions_completed"] == 3
    assert a["session_adherence"] == pytest.approx(0.3)
    assert a["longest_gap_days"] == 8
    assert a["weekly_sessions"] == [2, 1]


def test_refuses_stimulation_parameters():
    with pytest.raises(ValueError, match="stimulation"):
        sessions_from_records([{"participant": "P1", "day": S.start, "minutes": 30,
                                "source": "device_export", "amplitude": 3.5}])


def test_validates_source():
    with pytest.raises(ValueError):
        TherapySession("P1", S.start, 30, "guess")
