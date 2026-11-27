"""Arithmetic and guardrail tests for neurometric.economics."""
import copy
import math

import pytest

from neurometric.economics import care_economics as ce
from neurometric.economics import financial_model as fm


# ----------------------------------------------------------------------------- financial model
@pytest.fixture(scope="module")
def results():
    return fm.run_all()


def _tiny_scenario():
    """One academic customer in 2027 only, everything else zero: hand-checkable."""
    sc = fm.make_scenario("T", "test", "hand-check", {})
    p = sc.params
    for seg in fm.SEGMENTS:
        p["customers"][seg] = fm.A([0] * 5, "HYP", "test")
    p["customers"]["academic_program"] = fm.A([1, 1, 0, 0, 0], "HYP", "test")
    for role in p["headcount"].values():
        role["fte"] = fm.A([0] * 5, "HYP", "test")
    for k in p["fixed"]:
        p["fixed"][k] = fm.A([0] * 5, "HYP", "test")
    for g in p["grants"]:
        g["income"] = fm.A([0] * 5, "HYP", "test")
    p["equity"] = fm.A([100_000, 0, 0, 0, 0], "HYP", "test")
    p["delivery_efficiency"] = fm.A([1.0] * 5, "HYP", "test")
    p["min_cash_buffer_months"] = fm.A(0, "HYP", "test")
    return sc


def test_scenarios_A_to_D_exist(results):
    assert set(results) == {"A", "B", "C", "D"}


def test_hand_checked_arithmetic():
    sc = _tiny_scenario()
    r = fm.run_model(sc)
    sp = {k: v.value for k, v in sc.params["segments"]["academic_program"].items()}
    rates = {k: v.value for k, v in sc.params["rates"].items()}
    # 2027: one new customer -> pilot
    assert r.lines["revenue"][0] == pytest.approx(sp["pilot_price"])
    parts = sp["pilot_participants"]
    eng = sp["setup_hours_per_study"] + parts * sp["deploy_hours_per_participant"]
    clin = parts * sp["clinical_hours_per_participant"] + 0.5 * sp["report_hours_per_study"]
    psy = 0.5 * sp["psychometric_hours_per_study"]
    cogs = (eng * rates["engineering"] + clin * rates["clinical"] + psy * rates["psychometric"]
            + parts * sp["hosting_per_participant_year"] + sp["licence_cost_per_study"])
    assert r.lines["cogs"][0] == pytest.approx(cogs)
    opex = sp["cac_per_new_customer"] + sp["procurement_hours_per_new_customer"] * rates["bd"]
    assert r.lines["opex"][0] == pytest.approx(opex)
    # 2028: retained = min(1, 1*retention) -> contract revenue + residual new pilot share
    ret = sp["retention"]
    exp_rev = ret * sp["contract_value"] + (1 - ret) * sp["pilot_price"]
    assert r.lines["revenue"][1] == pytest.approx(exp_rev)
    # receivables and cash
    assert r.lines["accounts_receivable"][0] == pytest.approx(sp["pilot_price"] * sp["dso_days"] / 365)
    cash0 = 100_000 + r.lines["net_income"][0] - r.lines["accounts_receivable"][0]
    assert r.lines["cash_end"][0] == pytest.approx(cash0)


def test_pl_identities(results):
    for r in results.values():
        L = r.lines
        for i in range(fm.N_YEARS):
            assert L["revenue"][i] == pytest.approx(L["revenue_pilots"][i] + L["revenue_contracts"][i])
            assert L["revenue"][i] == pytest.approx(sum(r.segment_revenue[s][i] for s in fm.SEGMENTS))
            assert L["gross_profit"][i] == pytest.approx(L["revenue"][i] - L["cogs"][i])
            assert L["operating_income"][i] == pytest.approx(L["gross_profit"][i] - L["opex"][i])
            assert L["net_income"][i] == pytest.approx(
                L["operating_income"][i] + L["grant_income"][i] - L["grant_subawards"][i])
            prev = L["cash_end"][i - 1] if i else 0.0
            assert L["cash_end"][i] == pytest.approx(
                prev + L["net_income"][i] - L["change_in_ar"][i] + L["equity"][i]
                + L["additional_equity_required"][i])


def test_cash_buffer_respected(results):
    for r in results.values():
        p = r.scenario.params
        for i in range(fm.N_YEARS):
            buffer = p["min_cash_buffer_months"].value / 12 * (r.lines["cogs"][i] + r.lines["opex"][i])
            assert r.lines["cash_end"][i] >= buffer - 1e-6


def test_customer_counts_within_market_universe(results):
    for r in results.values():
        for seg in fm.SEGMENTS:
            assert all(0 <= x <= 1 for x in r.penetration[seg])


def test_universe_violation_rejected():
    sc = fm.make_scenario("X", "x", "x", {"customers.ibci_sponsor": fm.A([9, 9, 9, 9, 9], "HYP", "x")})
    with pytest.raises(fm.ModelError):
        fm.run_model(sc)


def test_sttr_subaward_minimum_enforced():
    sc = fm.make_scenario("X", "x", "x", {})
    sc.params["grants"][0]["subaward_fraction"] = fm.A(0.1, "HYP", "x")
    with pytest.raises(fm.ModelError):
        fm.run_model(sc)


def test_every_assumption_labelled_and_sourced(results):
    for r in results.values():
        reg = fm.assumption_register(r.scenario.params)
        assert len(reg) > 60
        for path, a in reg:
            assert a.label in fm.LABELS, path
            assert a.source.strip(), path
    for a in fm.MARKET_UNIVERSE.values():
        assert a.label in fm.LABELS and a.source


def test_prices_are_never_verified_facts(results):
    for r in results.values():
        for seg in fm.SEGMENTS:
            for k in ("pilot_price", "contract_value"):
                assert r.scenario.params["segments"][seg][k].label == "HYP"


def test_bad_label_rejected():
    with pytest.raises(fm.ModelError):
        fm.A(1, "FACT", "somewhere")
    with pytest.raises(fm.ModelError):
        fm.A(1, "HYP", "  ")


def test_sensitivity_directions(results):
    base = fm.build_scenarios()["B"]
    b = results["B"].summary
    cheaper = fm.run_model(fm.variant(base, "-p", price_factor=0.7)).summary
    slower = fm.run_model(fm.variant(base, "-h", hours_factor=1.3)).summary
    nogrant = fm.run_model(fm.variant(base, "-g", drop_grants=True)).summary
    assert cheaper["year3_revenue"] < b["year3_revenue"]
    assert slower["cumulative_pre_financing_trough"] < b["cumulative_pre_financing_trough"]
    assert nogrant["total_capital_required"] > b["total_capital_required"]


def test_deterministic_and_renders():
    md1, md2 = fm.render_markdown(), fm.render_markdown()
    assert md1 == md2
    assert "HYP" in md1 and "Scenario D" in md1


def test_summary_fields(results):
    for r in results.values():
        S = r.summary
        assert S["year3_revenue"] == pytest.approx(r.lines["revenue"][2])
        assert S["total_capital_required"] == pytest.approx(
            S["total_equity"] + S["additional_equity_required"])
        assert S["breakeven_year_operating"] in (None, *fm.YEARS)


# ----------------------------------------------------------------------------- care economics
def test_bls_wage_is_sourced():
    w = ce.BLS_HOME_HEALTH_AIDE_MEDIAN
    assert w.hourly == 17.21 and w.label == "V"
    assert "bls.gov" in w.source and "2025" in w.reference_period


def test_replacement_cost_arithmetic():
    v = ce.value_care_time(1.0)
    assert v.annual_value == pytest.approx(1.0 * 365 * 17.21)  # 6,281.65
    assert v.status == ce.HYPOTHETICAL and v.is_hypothetical


def test_opportunity_cost_option():
    w = ce.opportunity_cost_basis(employed_share=0.5, leisure_value_fraction=0.5)
    assert w.method == "opportunity"
    assert w.hourly == pytest.approx(round(ce.BLS_ALL_OCCUPATIONS_MEAN.hourly * 0.75, 2))
    assert ce.BLS_ALL_OCCUPATIONS_MEAN.hourly == pytest.approx(69_770 / 2_080, abs=0.01)
    v = ce.value_care_time(2.0, w, days_per_year=250)
    assert v.annual_value == pytest.approx(2.0 * 250 * w.hourly)
    assert v.is_hypothetical


def test_bare_numbers_are_always_hypothetical():
    for h in (-1.0, 0.0, 0.5, 3):
        assert ce.value_care_time(h).status == ce.HYPOTHETICAL


def test_observed_effect_requires_ci_and_care_measure():
    eff = ce.ObservedEffect(0.8, 0.3, 1.3, 0.95, 24, "care_partner_time_diary", "TEST-001", "within-subject")
    v = ce.value_care_time(eff)
    assert v.status == ce.OBSERVED and not v.is_hypothetical
    lo, hi = v.annual_value_ci
    assert lo == pytest.approx(0.3 * 365 * 17.21) and hi == pytest.approx(1.3 * 365 * 17.21)
    with pytest.raises(ValueError):  # estimate outside CI
        ce.ObservedEffect(2.0, 0.3, 1.3, 0.95, 24, "care_partner_time_diary", "T", "d")
    with pytest.raises(ValueError):  # no study id
        ce.ObservedEffect(0.8, 0.3, 1.3, 0.95, 24, "care_partner_time_diary", " ", "d")


def test_ci_crossing_zero_flagged():
    eff = ce.ObservedEffect(0.2, -0.4, 0.8, 0.95, 12, "care_partner_time_ema", "T", "RCT")
    v = ce.value_care_time(eff)
    assert any("includes zero" in c for c in v.caveats)


def test_task_time_never_converted_to_care_time():
    for m in ("participant_task_time", "typing_speed", "device_performance", "made_up"):
        with pytest.raises(ce.GuardrailError):
            ce.ObservedEffect(0.5, 0.1, 0.9, 0.95, 10, m, "T", "d")


def test_never_healthcare_savings():
    v = ce.value_care_time(1.0)
    assert v.is_healthcare_cost_saving is False
    assert "NOT healthcare cost savings" in v.render()
    with pytest.raises(ce.GuardrailError):
        v.as_healthcare_savings()
    for kw in ("as_cost_savings", "payer_savings", "budget_impact", "roi"):
        with pytest.raises(ce.GuardrailError):
            ce.value_care_time(1.0, **{kw: True})
    with pytest.raises(ce.GuardrailError):
        ce.healthcare_cost_savings  # noqa: B018
    rendered = v.render().lower()
    assert "hypothetical scenario" in rendered


def test_input_bounds():
    with pytest.raises(ValueError):
        ce.value_care_time(25)
    with pytest.raises(ValueError):
        ce.value_care_time(1, days_per_year=0)
    with pytest.raises(TypeError):
        ce.value_care_time("1")


def test_sensitivity_table_all_hypothetical():
    rows = ce.sensitivity_table((0.5, 1.0), (ce.BLS_HOME_HEALTH_AIDE_MEDIAN, ce.AGENCY_CHARGE_PK))
    assert len(rows) == 4 and all(r.is_hypothetical for r in rows)
    md = ce.render_sensitivity_markdown(rows)
    assert ce.HYPOTHETICAL in md and "$6,282" in md  # 1 h/day at $17.21
    obs = ce.value_care_time(ce.ObservedEffect(0.5, 0.1, 0.9, 0.95, 10, "care_partner_time_diary", "T", "d"))
    with pytest.raises(ce.GuardrailError):
        ce.render_sensitivity_markdown(rows + [obs])
    assert math.isclose(rows[1].annual_value, 1.0 * 365 * 17.21)
