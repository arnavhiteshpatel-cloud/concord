import numpy as np
import pytest

from neurometric.chain.chain import (e_value_rr, mediation_bootstrap, synthetic_chain,
                                     within_between, wide)
from neurometric.chain.independence import (AttemptContext, classify_attempt,
                                            independence_summary)
from neurometric.events.model import EventKind, InputEvent, Modality


def _e(kind, stream="bci", **kw):
    base = dict(t_ms=1.0, kind=kind, session_id="ses_1", stream_id=stream, modality=Modality.BCI_CURSOR)
    if kind in (EventKind.POINTER_MOVE, EventKind.CLICK):
        base.update(x=1.0, y=1.0)
    base.update(kw)
    return InputEvent(**base)


def test_independence_states():
    move = [_e(EventKind.POINTER_MOVE), _e(EventKind.CLICK)]
    assist = [_e(EventKind.ASSIST, meta={"assist_type": "physical"})]
    other = [_e(EventKind.CLICK, stream="mouse")]
    ctx = lambda **k: AttemptContext(planned_stream="bci", **k)
    assert classify_attempt([], ctx(device_available=False)).state == "device_unavailable"
    assert classify_attempt([], ctx(device_connected=False)).state == "device_not_connected"
    assert classify_attempt([], ctx(completed=False)).state == "not_used"
    assert classify_attempt(move, ctx(completed=False)).state == "abandoned"
    assert classify_attempt(move, ctx(completed=True)).state == "completed_independently"
    r = classify_attempt(move + assist, ctx(completed=True))
    assert r.state == "completed_with_assistance" and r.assist_severity == 0.7
    assert classify_attempt(other, ctx(completed=True)).state == "completed_other_input"
    s = independence_summary([classify_attempt(move, ctx(completed=True)), r])
    assert s["prop_completed_independently"] == 0.5
    assert s["assistance_weighted_completion"] == pytest.approx((1 + 0.3) / 2)
    assert "EXPERIMENTAL" in s["label"]


def test_within_between_recovers_known_within_slope_despite_confounding():
    obs = synthetic_chain(n=80, waves=8, seed=1, within_slope=0.5, confound=1.0)
    w = wide(obs)
    res = within_between(w, "L2:grid_bitrate", "L5:assist_minutes")
    # within-person slope of assist minutes on L2 = -10 * 0.5 = -5 by construction
    assert res["within"].estimate == pytest.approx(-5.0, abs=1.0)
    assert res["within"].ci[0] < -5.0 < res["within"].ci[1]
    # between-person association is much stronger (confounded by the stable person factor)
    assert res["between"].estimate < -0.8
    assert "causal" not in res["within"].claim_type


def test_mediation_is_labelled_associational():
    rng = np.random.default_rng(0)
    import pandas as pd
    x = rng.standard_normal(300)
    m = 0.5 * x + rng.standard_normal(300)
    y = 0.4 * m + rng.standard_normal(300)
    r = mediation_bootstrap(pd.DataFrame({"x": x, "m": m, "y": y}), "x", "m", "y", n_boot=300)
    assert r.ci[0] < 0.2 < r.ci[1]
    assert "NOT a causal" in r.claim_type


def test_e_value():
    assert e_value_rr(2.0)["e_value_point"] == pytest.approx(2 + np.sqrt(2))
    assert e_value_rr(2.0, lo=0.9)["e_value_ci"] == 1.0
