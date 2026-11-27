"""Transparent, driver-based financial model for NeuroMetric (2027-2031).

Every number that enters the model is an :class:`Assumption` carrying an evidence label
(see ``docs/research/CONVENTIONS.md``) and a source. Prices, willingness to pay, customer counts
and market sizes are hypotheses ([HYP]) unless a source is given. Nothing in this module is a
forecast of what *will* happen; it shows what follows arithmetically from stated assumptions.

Scenarios
---------
A  Small independent evidence software company (lean, academic + AAC/AT makers first).
B  Sponsor-funded clinical research infrastructure (study contracts, Part 11, clinical ops).
C  Broader neurotech evidence platform (all segments, pivotal iBCI, rehab providers, Series A).
D  Rehab & AT expansion (home neuromodulation/rehab makers, AAC makers, rehab providers).

Arithmetic (per segment s, year t; all transparent, no hidden fitting)
--------------------------------------------------------------------------
retained_t   = min(N_t, N_{t-1} * retention)
new_t        = N_t - retained_t                     (each new customer starts with a paid pilot)
revenue_t    = new_t * pilot_price + retained_t * studies_per_customer * contract_value
participants = retained_t * studies * participants_per_study + new_t * pilot_participants
COGS_t       = labour hours x rates (x delivery_efficiency_t) + hosting + instrument licences
Opex_t       = headcount (FTE x salary x overhead) + CAC x new + procurement hours x BD rate
               + hosting base + SOC 2 + Part 11 validation + insurance + R&D + G&A
Operating income = revenue - COGS - opex
Net income (pre-tax) = operating income + grant income - grant subawards (STTR research partner)
Cash_t = Cash_{t-1} + net income - change in accounts receivable + equity raised
         + additional equity required (model plug that keeps a minimum cash buffer; = funding gap)
ARR (year-end run-rate) = (retained + new * retention) * studies * contract_value

Delivery labour is costed by the hour inside COGS (contractors or delivery staff). The headcount
plan covers only R&D, quality/regulatory, sales and G&A, so delivery is not double counted.

Run ``python -m neurometric.economics.financial_model --markdown <path>`` to regenerate the
output tables in ``docs/commercial/financial_model_outputs.md``.
"""
from __future__ import annotations

import argparse
import copy
import json
from dataclasses import dataclass, field
from typing import Any

YEARS: tuple[int, ...] = (2027, 2028, 2029, 2030, 2031)
N_YEARS = len(YEARS)
LABELS = frozenset({"V", "CC", "RF", "AE", "INF", "HYP", "PK", "UNR"})

#: Founder-playbook hypotheses used for comparison only (never as model inputs).
PLAYBOOK_YEAR3_ARR = {"conservative": 230_000, "base": 1_100_000, "upside": 2_800_000}
PLAYBOOK_CAPITAL = {"months_0_12": (150_000, 400_000), "months_12_30": (1_500_000, 3_000_000)}


class ModelError(ValueError):
    """Raised for inconsistent model inputs."""


@dataclass(frozen=True)
class Assumption:
    """One model input with its evidence label and source."""

    value: Any
    label: str
    source: str
    unit: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if self.label not in LABELS:
            raise ModelError(f"unknown evidence label {self.label!r}; use one of {sorted(LABELS)}")
        if not str(self.source).strip():
            raise ModelError("every assumption needs a non-empty source")


def A(value: Any, label: str, source: str, unit: str = "", note: str = "") -> Assumption:
    """Shorthand constructor."""
    return Assumption(value, label, source, unit, note)


def _yr(values: list[float]) -> list[float]:
    if len(values) != N_YEARS:
        raise ModelError(f"per-year lists need {N_YEARS} values ({YEARS}); got {len(values)}")
    return list(values)


# ---------------------------------------------------------------------------------------------
# Segments and plausible initial-customer universe (organisations, NOT patients)
# ---------------------------------------------------------------------------------------------
SEGMENTS: tuple[str, ...] = (
    "ibci_sponsor",
    "nibci_aac_maker",
    "home_neuromod_maker",
    "academic_program",
    "rehab_provider",
)
SEGMENT_NAMES = {
    "ibci_sponsor": "Implantable BCI sponsors (US motor/communication, excl. Neuralink)",
    "nibci_aac_maker": "Non-invasive BCI and AAC/AT makers",
    "home_neuromod_maker": "Home neuromodulation and rehab-device makers",
    "academic_program": "Academic BCI / rehab research programs",
    "rehab_provider": "Rehab hospitals and AT/AAC clinics (SGD/AT justification)",
}

MARKET_UNIVERSE: dict[str, Assumption] = {
    "ibci_sponsor": A(
        _yr([3, 5, 6, 6, 7]), "INF",
        "docs/research/competitors.md S5: 3 US sponsors with active motor/communication IDE studies "
        "(Neuralink, Synchron, Paradromics; CT.gov [V]) and ~5-8 plausible by 2028. Neuralink "
        "removed as likely non-buyer; Precision, Blackrock, Echo, CorTec added as they register.",
        "organisations"),
    "nibci_aac_maker": A(
        _yr([5, 7, 9, 10, 11]), "INF",
        "docs/research/prospects.md section 3: AAC/AT makers 3 Tier-2 + 6 Tier-3, plus Cognixion "
        "and g.tec (non-invasive BCI); ramp assumes Tier-3 firms become reachable over time.",
        "organisations"),
    "home_neuromod_maker": A(
        _yr([5, 7, 9, 11, 12]), "INF",
        "docs/research/prospects.md section 3: neuromodulation/rehab devices 4 Tier-1 + 2 Tier-2 + "
        "9 Tier-3 (ONWARD, Kandu, Bioness, Mobia, Myomo, Cala, Phantom, BrainQ, ...).",
        "organisations"),
    "academic_program": A(
        _yr([14, 16, 18, 19, 20]), "INF",
        "docs/research/prospects.md: 14 Tier-2 academic programs; competitors.md S5: ~10-12 "
        "academic/VA iBCI programs; plus rehab labs (e.g., JNERL) as grants allow.",
        "programs"),
    "rehab_provider": A(
        _yr([15, 18, 22, 26, 30]), "PK",
        "Early-adopter pool = NIDILRR SCI and TBI Model Systems centres plus AT/AAC clinics at "
        "top rehab hospitals (order of 15-30); counts are prior knowledge, not re-verified.",
        "organisations"),
}


# ---------------------------------------------------------------------------------------------
# Default parameters (scenario B is closest to these). Scenarios override selected leaves.
# ---------------------------------------------------------------------------------------------
_PRICING_SRC = ("docs/research/comparable_pricing.md (founder playbook H1-H3 tested against "
                "OpenClinica $36-45K/study-yr [V], EDC Phase II $50-150K [AE], Veeva median "
                "$188K/yr [AE], Compass $179 [V])")


def _segment_defaults() -> dict[str, dict[str, Assumption]]:
    H = "HYP"
    ops = "NeuroMetric delivery estimate; no time-and-motion data yet"
    return {
        "ibci_sponsor": {
            "pilot_price": A(50_000, H, _PRICING_SRC + "; playbook pilot $25-75K", "USD/pilot"),
            "contract_value": A(125_000, H, _PRICING_SRC + "; recommended EFS test point $100-150K",
                                "USD/study-year"),
            "studies_per_customer": A(1.0, H, "EFS sponsors run 1 US study at a time (CT.gov, competitors.md B1-B3)",
                                      "studies/yr"),
            "participants_per_study": A(5, "INF", "iBCI EFS registrations n=2-15 (CT.gov via competitors.md)",
                                        "participants"),
            "pilot_participants": A(3, H, ops, "participants"),
            "retention": A(0.70, H, "no data; small sponsor base, trial pauses (Synchron Nov 2026 [AE])"),
            "setup_hours_per_study": A(200, H, ops, "h"),
            "deploy_hours_per_participant": A(20, H, ops + "; home installs + travel", "h/participant-yr"),
            "clinical_hours_per_participant": A(24, H, ops, "h/participant-yr"),
            "psychometric_hours_per_study": A(120, H, ops, "h"),
            "report_hours_per_study": A(120, H, ops + "; Part 11-ready evidence package", "h"),
            "hosting_per_participant_year": A(600, H, "cloud storage/compute estimate; high-frequency telemetry",
                                              "USD"),
            "licence_cost_per_study": A(3_000, "UNR", "COA licence fees (e.g., ZBI, PIADS) not published; placeholder",
                                        "USD/study"),
            "cac_per_new_customer": A(25_000, H, "conference travel, demos, BD time; no data", "USD"),
            "procurement_hours_per_new_customer": A(80, H, "vendor qualification, security questionnaire, audit "
                                                    "(regulatory_landscape.md s4: sponsors must oversee IT providers [V])",
                                                    "h"),
            "dso_days": A(60, H, "typical net-45/60 terms; no data", "days"),
        },
        "nibci_aac_maker": {
            "pilot_price": A(40_000, H, _PRICING_SRC, "USD/pilot"),
            "contract_value": A(100_000, H, _PRICING_SRC + "; maker contracts $100-300K/yr (low end)", "USD/yr"),
            "studies_per_customer": A(1.0, H, "one evidence program per maker", "programs/yr"),
            "participants_per_study": A(20, "INF", "Cognixion NCT07871071 n=30 [V]; AAC evidence cohorts smaller",
                                        "participants"),
            "pilot_participants": A(8, H, ops, "participants"),
            "retention": A(0.75, H, "no data"),
            "setup_hours_per_study": A(120, H, ops, "h"),
            "deploy_hours_per_participant": A(6, H, ops + "; remote kit", "h/participant-yr"),
            "clinical_hours_per_participant": A(8, H, ops, "h/participant-yr"),
            "psychometric_hours_per_study": A(100, H, ops, "h"),
            "report_hours_per_study": A(80, H, ops + "; SGD funding / FDA evidence package", "h"),
            "hosting_per_participant_year": A(200, H, "cloud estimate", "USD"),
            "licence_cost_per_study": A(2_000, "UNR", "COA licence fees not published; placeholder", "USD/study"),
            "cac_per_new_customer": A(15_000, H, "no data", "USD"),
            "procurement_hours_per_new_customer": A(40, H, "lighter than iBCI sponsors", "h"),
            "dso_days": A(45, H, "no data", "days"),
        },
        "home_neuromod_maker": {
            "pilot_price": A(50_000, H, _PRICING_SRC, "USD/pilot"),
            "contract_value": A(150_000, H, _PRICING_SRC + "; registry/RWE add-on per year", "USD/yr"),
            "studies_per_customer": A(1.0, H, "one RWE/registry add-on per maker", "programs/yr"),
            "participants_per_study": A(40, "INF", "Kandu RWE n=100 (NCT07147881) and Mobia At-Home n=50 "
                                        "(NCT05691023) [V]; NeuroMetric would cover a subset", "participants"),
            "pilot_participants": A(10, H, ops, "participants"),
            "retention": A(0.75, H, "no data"),
            "setup_hours_per_study": A(160, H, ops, "h"),
            "deploy_hours_per_participant": A(4, H, ops + "; wearable shipped", "h/participant-yr"),
            "clinical_hours_per_participant": A(6, H, ops, "h/participant-yr"),
            "psychometric_hours_per_study": A(120, H, ops, "h"),
            "report_hours_per_study": A(100, H, ops + "; payer-facing package", "h"),
            "hosting_per_participant_year": A(150, H, "cloud estimate", "USD"),
            "licence_cost_per_study": A(3_000, "UNR", "COA licence fees not published; placeholder", "USD/study"),
            "cac_per_new_customer": A(20_000, H, "no data", "USD"),
            "procurement_hours_per_new_customer": A(60, H, "no data", "h"),
            "dso_days": A(60, H, "no data", "days"),
        },
        "academic_program": {
            "pilot_price": A(15_000, H, _PRICING_SRC + "; Castor free tier [CC] and REDCap [PK] set floor",
                             "USD/pilot"),
            "contract_value": A(35_000, H, _PRICING_SRC + "; grant-budget subcontract/licence", "USD/yr"),
            "studies_per_customer": A(1.0, H, "one funded study per program", "studies/yr"),
            "participants_per_study": A(10, "INF", "academic iBCI/home BCI n=1-30 (prospects.md)", "participants"),
            "pilot_participants": A(5, H, ops, "participants"),
            "retention": A(0.80, H, "grant cycles 3-5 yr; no data"),
            "setup_hours_per_study": A(60, H, ops + "; lab staff deploy", "h"),
            "deploy_hours_per_participant": A(4, H, ops, "h/participant-yr"),
            "clinical_hours_per_participant": A(2, H, ops, "h/participant-yr"),
            "psychometric_hours_per_study": A(40, H, ops, "h"),
            "report_hours_per_study": A(20, H, ops, "h"),
            "hosting_per_participant_year": A(150, H, "cloud estimate", "USD"),
            "licence_cost_per_study": A(0, H, "academic sites hold their own instrument licences", "USD/study"),
            "cac_per_new_customer": A(5_000, H, "conference + collaborator network; no data", "USD"),
            "procurement_hours_per_new_customer": A(20, H, "subcontract/DUA paperwork", "h"),
            "dso_days": A(90, H, "university/VA payment cycles; no data", "days"),
        },
        "rehab_provider": {
            "pilot_price": A(5_000, H, "no comparable; onboarding pilot", "USD/pilot"),
            "contract_value": A(18_000, H, "no public comparable; Compass $179 licence [V] is a floor for clinic "
                                "tools; priced on documentation value, not seats", "USD/yr"),
            "studies_per_customer": A(1.0, H, "one site subscription", "subscriptions/yr"),
            "participants_per_study": A(60, H, "patients documented per site-year", "patients"),
            "pilot_participants": A(15, H, ops, "patients"),
            "retention": A(0.80, H, "no data"),
            "setup_hours_per_study": A(16, H, ops, "h"),
            "deploy_hours_per_participant": A(0.25, H, ops + "; clinician-run", "h/patient"),
            "clinical_hours_per_participant": A(0.25, H, ops, "h/patient"),
            "psychometric_hours_per_study": A(4, H, ops, "h"),
            "report_hours_per_study": A(4, H, ops, "h"),
            "hosting_per_participant_year": A(20, H, "cloud estimate", "USD"),
            "licence_cost_per_study": A(500, "UNR", "instrument licences per site; placeholder", "USD/site"),
            "cac_per_new_customer": A(8_000, H, "no data", "USD"),
            "procurement_hours_per_new_customer": A(30, H, "hospital IT/security review + BAA (45 CFR 160.103 [V])",
                                                    "h"),
            "dso_days": A(60, H, "no data", "days"),
        },
    }


def _default_params() -> dict[str, Any]:
    H = "HYP"
    return {
        "segments": _segment_defaults(),
        "customers": {  # active paying customers per segment per year (scenario B defaults)
            "ibci_sponsor": A(_yr([1, 2, 3, 3, 4]), H, "scenario B customer plan; must stay <= MARKET_UNIVERSE"),
            "nibci_aac_maker": A(_yr([1, 1, 2, 2, 3]), H, "scenario B customer plan"),
            "home_neuromod_maker": A(_yr([1, 2, 4, 5, 6]), H, "scenario B customer plan"),
            "academic_program": A(_yr([2, 3, 4, 5, 5]), H, "scenario B customer plan"),
            "rehab_provider": A(_yr([0, 0, 0, 1, 2]), H, "scenario B customer plan"),
        },
        "rates": {
            "engineering": A(95, H, "loaded delivery cost per hour (not a price); OpenClinica bills $275-350/h [V] "
                             "as a price ceiling reference", "USD/h"),
            "clinical": A(85, H, "loaded clinical research specialist cost per hour; no data", "USD/h"),
            "psychometric": A(120, H, "loaded psychometrician/biostatistician cost per hour; no data", "USD/h"),
            "bd": A(100, H, "loaded BD/QA time for vendor qualification", "USD/h"),
        },
        "pilot_scope_fraction": A(0.5, H, "pilot uses half the psychometric/report effort of a study-year"),
        "delivery_efficiency": A(_yr([1.0, 0.95, 0.85, 0.75, 0.70]), H,
                                 "labour-hour multiplier as tooling matures; no data"),
        "delivery_hours_factor": A(1.0, H, "service-delivery model: NeuroMetric staff deploy and support"),
        "min_cash_buffer_months": A(3, H, "keep >= 3 months of current-year spend in the bank; below this the "
                                    "model adds 'additional equity required' (funding need)", "months"),
        "target_gross_margin": A(0.60, H, "software+services benchmark for comparison only; not an input to P&L"),
        "headcount": {
            # role: (FTE per year, annual salary)
            "founder_ceo": {"fte": A(_yr([0.25, 1, 1, 1, 1]), H, "founder is a UIUC undergraduate; part-time in 2027"),
                            "salary": A(90_000, H, "modest founder salary; no data", "USD/yr")},
            "software_engineer": {"fte": A(_yr([0.5, 1.5, 2, 3, 3]), H, "R&D plan"),
                                  "salary": A(140_000, "PK", "US software engineer salary order of magnitude; "
                                              "not re-verified", "USD/yr")},
            "clinical_science_lead": {"fte": A(_yr([0, 0.5, 1, 1, 1]), H, "protocols, IRB support, SOPs (non-billable)"),
                                      "salary": A(120_000, "PK", "order of magnitude; not re-verified", "USD/yr")},
            "psychometrics_lead": {"fte": A(_yr([0.1, 0.25, 0.5, 0.5, 0.5]), H, "advisor contract then part-time hire"),
                                   "salary": A(150_000, "PK", "order of magnitude; not re-verified", "USD/yr")},
            "quality_regulatory": {"fte": A(_yr([0, 0.5, 0.5, 1, 1]), H, "Part 11 / QMS-lite owner"),
                                   "salary": A(150_000, "PK", "order of magnitude; not re-verified", "USD/yr")},
            "bd_sales": {"fte": A(_yr([0, 0, 0.5, 1, 1]), H, "founder-led sales until 2029"),
                         "salary": A(150_000, "PK", "order of magnitude; not re-verified", "USD/yr")},
            "ops_ga": {"fte": A(_yr([0, 0, 0.25, 0.5, 0.5]), H, "finance/ops"),
                       "salary": A(100_000, "PK", "order of magnitude; not re-verified", "USD/yr")},
        },
        "overhead_multiplier": A(1.25, "PK", "benefits + payroll tax ~20-30% of salary; not re-verified"),
        "fixed": {
            "hosting_base": A(_yr([3_000, 12_000, 24_000, 36_000, 48_000]), H, "environments, backups, monitoring",
                              "USD/yr"),
            "soc2": A(_yr([0, 45_000, 50_000, 50_000, 55_000]), "PK",
                      "SOC 2 readiness + Type I then annual Type II incl. tooling; industry order of magnitude, "
                      "not re-verified [UNR exact]", "USD/yr"),
            "part11_validation": A(_yr([10_000, 60_000, 25_000, 30_000, 30_000]), H,
                                   "Part 11 computerised-system validation package then per-release revalidation "
                                   "(21 CFR 11.10(a) [V]; eSystems Q&A Oct 2024 [V]); cost is a hypothesis",
                                   "USD/yr"),
            "insurance": A(_yr([3_000, 15_000, 25_000, 30_000, 35_000]), H,
                           "E&O + cyber (+ clinical-trial-related liability via contracts); no quotes obtained",
                           "USD/yr"),
            "rnd_nonheadcount": A(_yr([15_000, 40_000, 50_000, 60_000, 70_000]), H,
                                  "test devices (eye tracker, EEG headset, switches), cloud dev, tools", "USD/yr"),
            "ga_other": A(_yr([20_000, 50_000, 70_000, 90_000, 100_000]), H,
                          "incorporation, legal, contracts/DUAs, accounting, IP", "USD/yr"),
        },
        "grants": [
            {"name": "NIH STTR Phase I (PA-27-102; NICHD/NCMRR cap $400K)", "sttr": True,
             "income": A(_yr([0, 400_000, 0, 0, 0]), "INF",
                         "funding.md: submit 5 Apr 2027 [V date]; earliest start ~Dec 2027 [INF]; cap $400K NICHD [V]; "
                         "award itself is a hypothesis (success rates not verified)"),
             "subaward_fraction": A(0.35, "INF", "STTR requires >=30% to partner research institution [V funding.md]; "
                                    "35% planned")},
            {"name": "Illinois DCEO SBIR/STTR Phase I match",
             "income": A(_yr([0, 75_000, 0, 0, 0]), "INF",
                         "funding.md: up to $75K after a federal Phase I [V]; NOFO window to 30 Jun 2027, renewal [UNR]"),
             "subaward_fraction": A(0.0, "INF", "state match is not subawarded")},
            {"name": "NIH STTR Phase II (NICHD cap $2.5M; planned $2.0M)", "sttr": True,
             "income": A(_yr([0, 0, 300_000, 1_000_000, 700_000]), "HYP",
                         "funding.md: Phase II submission M18-24 (Jun-Nov 2028) [INF]; award is a hypothesis; "
                         "SBIR/STTR authorised to 30 Sep 2031 (P.L. 119-83 [V])"),
             "subaward_fraction": A(0.30, "INF", "STTR Phase II >=30% research-institution minimum [V funding.md]")},
        ],
        "equity": A(_yr([300_000, 2_000_000, 0, 0, 0]), H,
                    "playbook capital need $150-400K (M0-12) and $1.5-3M (M12-30); funding.md: Illinois Ventures "
                    "pre-seed $100-300K [V], Cozad SAFE prizes [V]; raise itself is a hypothesis", "USD"),
        "starting_cash": A(0, "INF", "pre-incorporation; no company bank account (funding.md s3.2)", "USD"),
    }


# ---------------------------------------------------------------------------------------------
# Scenarios
# ---------------------------------------------------------------------------------------------
@dataclass
class Scenario:
    key: str
    title: str
    description: str
    params: dict[str, Any]
    overrides: list[str] = field(default_factory=list)


def _set(params: dict[str, Any], path: str, value: Any) -> None:
    node: Any = params
    parts = path.split(".")
    for p in parts[:-1]:
        node = node[int(p)] if isinstance(node, list) else node[p]
    last = parts[-1]
    if isinstance(node, list):
        idx = int(last)
        if idx == len(node):
            node.append(value)  # add a grant/funding line
        else:
            node[idx] = value
    else:
        if last not in node and not path.startswith("grants"):
            raise ModelError(f"unknown parameter path {path}")
        node[last] = value


def make_scenario(key: str, title: str, description: str, overrides: dict[str, Any]) -> Scenario:
    params = _default_params()
    for path, value in overrides.items():
        _set(params, path, value)
    return Scenario(key, title, description, params, sorted(overrides))


def _fte(values: list[float], note: str) -> Assumption:
    return A(_yr(values), "HYP", note)


def build_scenarios() -> dict[str, Scenario]:
    H = "HYP"
    s: dict[str, Scenario] = {}

    s["A"] = make_scenario(
        "A", "Small independent evidence software company",
        "Lean, software-first: research licences and small evidence pilots for academic programs and "
        "AAC/non-invasive BCI makers; Part 11-ready but sponsor-validated; minimal clinical operations.",
        {
            "customers.ibci_sponsor": A(_yr([0, 0, 1, 1, 1]), H, "scenario A plan"),
            "customers.nibci_aac_maker": A(_yr([1, 2, 3, 3, 4]), H, "scenario A plan"),
            "customers.home_neuromod_maker": A(_yr([0, 1, 1, 2, 2]), H, "scenario A plan"),
            "customers.academic_program": A(_yr([2, 4, 6, 7, 8]), H, "scenario A plan"),
            "customers.rehab_provider": A(_yr([0, 1, 3, 5, 7]), H, "scenario A plan"),
            "segments.ibci_sponsor.pilot_price": A(35_000, H, _PRICING_SRC, "USD/pilot"),
            "segments.ibci_sponsor.contract_value": A(100_000, H, _PRICING_SRC, "USD/study-year"),
            "segments.nibci_aac_maker.pilot_price": A(25_000, H, _PRICING_SRC + "; playbook pilot low end", "USD/pilot"),
            "segments.nibci_aac_maker.contract_value": A(60_000, H, _PRICING_SRC + "; below playbook maker range",
                                                         "USD/yr"),
            "segments.home_neuromod_maker.pilot_price": A(25_000, H, _PRICING_SRC, "USD/pilot"),
            "segments.home_neuromod_maker.contract_value": A(90_000, H, _PRICING_SRC, "USD/yr"),
            "segments.academic_program.contract_value": A(25_000, H, _PRICING_SRC, "USD/yr"),
            "segments.rehab_provider.contract_value": A(12_000, H, "no comparable; lean pricing", "USD/yr"),
            "headcount.founder_ceo.fte": _fte([0.25, 1, 1, 1, 1], "scenario A"),
            "headcount.software_engineer.fte": _fte([0.5, 1, 1.5, 2, 2], "scenario A"),
            "headcount.clinical_science_lead.fte": _fte([0, 0, 0.25, 0.5, 0.5], "scenario A"),
            "headcount.psychometrics_lead.fte": _fte([0.1, 0.1, 0.2, 0.25, 0.25], "scenario A"),
            "headcount.quality_regulatory.fte": _fte([0, 0, 0.25, 0.25, 0.5], "scenario A"),
            "headcount.bd_sales.fte": _fte([0, 0, 0, 0.5, 0.5], "scenario A"),
            "headcount.ops_ga.fte": _fte([0, 0, 0, 0.25, 0.5], "scenario A"),
            "delivery_hours_factor": A(0.6, H, "licence model: customer staff run deployment and sessions; "
                                       "NeuroMetric supports remotely (no data)"),
            "fixed.hosting_base": A(_yr([2_000, 6_000, 10_000, 14_000, 18_000]), H, "lean hosting", "USD/yr"),
            "fixed.soc2": A(_yr([0, 0, 25_000, 30_000, 30_000]), "PK",
                            "SOC 2 deferred to 2029; lean readiness; not re-verified", "USD/yr"),
            "fixed.part11_validation": A(_yr([5_000, 15_000, 20_000, 15_000, 15_000]), H,
                                         "Part 11-ready documentation; per-study validation left to sponsor", "USD/yr"),
            "fixed.insurance": A(_yr([2_000, 6_000, 10_000, 12_000, 14_000]), H, "E&O + cyber; no quotes", "USD/yr"),
            "fixed.rnd_nonheadcount": A(_yr([10_000, 20_000, 25_000, 30_000, 30_000]), H, "lean R&D", "USD/yr"),
            "fixed.ga_other": A(_yr([15_000, 30_000, 40_000, 45_000, 50_000]), H, "lean G&A", "USD/yr"),
            "grants.2.income": A(_yr([0, 0, 200_000, 700_000, 600_000]), H,
                                 "smaller Phase II ($1.5M) assumed; award is a hypothesis"),
            "grants.3": {"name": "NIDILRR SBIR Phase I (~$100K, ~Dec 2027 cycle)",
                         "income": A(_yr([0, 50_000, 50_000, 0, 0]), "INF",
                                     "funding.md: FY27 forecast $95-100K, due 16 Dec 2026 [V]; next cycle ~Dec 2027 "
                                     "[INF]; award is a hypothesis"),
                         "subaward_fraction": A(0.0, "INF", "SBIR; no required research subaward")},
            "equity": A(_yr([150_000, 250_000, 0, 0, 0]), H,
                        "pre-seed/SAFE (Illinois Ventures pre-seed $100-300K [V]; Cozad prizes [V]); hypothesis", "USD"),
        },
    )

    s["B"] = make_scenario(
        "B", "Sponsor-funded clinical research infrastructure",
        "Study contracts with non-dominant iBCI sponsors and home-neuromodulation makers; validated Part 11 "
        "platform, SOC 2, clinical operations and psychometric analysis delivered as a service.",
        {},
    )

    s["C"] = make_scenario(
        "C", "Broader neurotech evidence platform",
        "All segments including pivotal iBCI studies, payer-evidence packages, rehab-provider subscriptions "
        "and manufacturer SDK integrations; seed then Series A.",
        {
            "customers.ibci_sponsor": A(_yr([1, 2, 4, 5, 6]), H, "scenario C plan (aggressive penetration)"),
            "customers.nibci_aac_maker": A(_yr([1, 2, 4, 6, 7]), H, "scenario C plan"),
            "customers.home_neuromod_maker": A(_yr([1, 2, 5, 7, 8]), H, "scenario C plan"),
            "customers.academic_program": A(_yr([3, 5, 8, 10, 12]), H, "scenario C plan"),
            "customers.rehab_provider": A(_yr([0, 2, 5, 9, 14]), H, "scenario C plan"),
            "segments.ibci_sponsor.contract_value": A(175_000, H, _PRICING_SRC + "; blend of EFS $125K and pivotal "
                                                      "$250-400K", "USD/study-year"),
            "segments.ibci_sponsor.studies_per_customer": A(1.3, H, "some sponsors run EFS + pivotal", "studies/yr"),
            "segments.nibci_aac_maker.contract_value": A(120_000, H, _PRICING_SRC, "USD/yr"),
            "segments.home_neuromod_maker.contract_value": A(175_000, H, _PRICING_SRC + "; incl. payer package",
                                                             "USD/yr"),
            "segments.academic_program.contract_value": A(40_000, H, _PRICING_SRC, "USD/yr"),
            "segments.rehab_provider.contract_value": A(20_000, H, "no comparable", "USD/yr"),
            "headcount.founder_ceo.fte": _fte([0.5, 1, 1, 1, 1], "scenario C"),
            "headcount.software_engineer.fte": _fte([1, 2, 4, 5, 6], "scenario C"),
            "headcount.clinical_science_lead.fte": _fte([0, 1, 1, 2, 2], "scenario C"),
            "headcount.psychometrics_lead.fte": _fte([0.1, 0.5, 1, 1, 1.5], "scenario C"),
            "headcount.quality_regulatory.fte": _fte([0, 0.5, 1, 1, 1.5], "scenario C"),
            "headcount.bd_sales.fte": _fte([0, 1, 1.5, 2, 3], "scenario C"),
            "headcount.ops_ga.fte": _fte([0, 0.5, 1, 1, 1.5], "scenario C"),
            "fixed.hosting_base": A(_yr([5_000, 20_000, 40_000, 60_000, 80_000]), H, "platform scale", "USD/yr"),
            "fixed.soc2": A(_yr([0, 50_000, 60_000, 70_000, 80_000]), "PK", "SOC 2 Type I then II; not re-verified",
                            "USD/yr"),
            "fixed.part11_validation": A(_yr([15_000, 80_000, 40_000, 40_000, 50_000]), H, "validated platform",
                                         "USD/yr"),
            "fixed.insurance": A(_yr([5_000, 20_000, 35_000, 45_000, 55_000]), H, "E&O + cyber; no quotes", "USD/yr"),
            "fixed.rnd_nonheadcount": A(_yr([25_000, 80_000, 120_000, 150_000, 180_000]), H, "SDKs, devices, cloud",
                                        "USD/yr"),
            "fixed.ga_other": A(_yr([25_000, 80_000, 120_000, 160_000, 200_000]), H, "G&A at scale", "USD/yr"),
            "grants.3": {"name": "Illinois DCEO Phase II match (up to $250K)",
                         "income": A(_yr([0, 0, 0, 250_000, 0]), "INF",
                                     "funding.md: DCEO Phase II match up to $250K [V]; requires Phase II award"),
                         "subaward_fraction": A(0.0, "INF", "state match")},
            "equity": A(_yr([400_000, 3_000_000, 0, 8_000_000, 0]), H,
                        "pre-seed, seed (top of playbook range) and a 2030 Series A; all hypotheses", "USD"),
        },
    )

    s["D"] = make_scenario(
        "D", "Rehab & AT expansion",
        "Lead with home-neuromodulation/rehab makers and AAC makers (payer-documented gaps), add rehab-provider "
        "subscriptions for SGD/AT justification; iBCI kept as a small credibility anchor.",
        {
            "customers.ibci_sponsor": A(_yr([0, 1, 1, 1, 1]), H, "scenario D plan"),
            "customers.nibci_aac_maker": A(_yr([1, 2, 4, 5, 6]), H, "scenario D plan"),
            "customers.home_neuromod_maker": A(_yr([1, 3, 5, 6, 7]), H, "scenario D plan"),
            "customers.academic_program": A(_yr([2, 3, 5, 6, 6]), H, "scenario D plan"),
            "customers.rehab_provider": A(_yr([0, 2, 5, 9, 12]), H, "scenario D plan"),
            "headcount.software_engineer.fte": _fte([0.5, 1.5, 2, 3, 3.5], "scenario D"),
            "headcount.clinical_science_lead.fte": _fte([0, 0.5, 1, 1, 1.5], "scenario D"),
            "headcount.psychometrics_lead.fte": _fte([0.1, 0.25, 0.5, 0.5, 0.75], "scenario D"),
            "headcount.quality_regulatory.fte": _fte([0, 0.5, 0.5, 1, 1], "scenario D"),
            "headcount.bd_sales.fte": _fte([0, 0.5, 1, 1.5, 1.5], "scenario D"),
            "headcount.ops_ga.fte": _fte([0, 0, 0.25, 0.5, 0.5], "scenario D"),
            "grants.3": {"name": "NIDILRR SBIR Phase I (~$100K, ~Dec 2027 cycle)",
                         "income": A(_yr([0, 50_000, 50_000, 0, 0]), "INF",
                                     "funding.md: $95-100K, next cycle ~Dec 2027 [INF]; award is a hypothesis"),
                         "subaward_fraction": A(0.0, "INF", "SBIR")},
            "equity": A(_yr([300_000, 1_500_000, 0, 3_000_000, 0]), H,
                        "pre-seed, seed (playbook low end), 2030 growth round; hypotheses", "USD"),
        },
    )
    return s


# ---------------------------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------------------------
def _v(a: Assumption) -> Any:
    return a.value


@dataclass
class ModelResult:
    scenario: Scenario
    lines: dict[str, list[float]]
    segment_revenue: dict[str, list[float]]
    segment_new: dict[str, list[float]]
    penetration: dict[str, list[float]]
    summary: dict[str, Any]


def validate_params(params: dict[str, Any]) -> None:
    for seg in SEGMENTS:
        counts = _v(params["customers"][seg])
        _yr(counts)
        universe = _v(MARKET_UNIVERSE[seg])
        for i, (n, u) in enumerate(zip(counts, universe)):
            if n < 0:
                raise ModelError(f"{seg} {YEARS[i]}: negative customer count")
            if n > u:
                raise ModelError(f"{seg} {YEARS[i]}: {n} customers exceeds plausible universe {u}")
        sp = params["segments"][seg]
        if not 0 <= _v(sp["retention"]) <= 1:
            raise ModelError(f"{seg}: retention must be in [0, 1]")
    for g in params["grants"]:
        if g.get("sttr") and _v(g["subaward_fraction"]) < 0.30:
            raise ModelError(f"{g['name']}: STTR requires >= 30% to the research institution")


def run_model(scenario: Scenario) -> ModelResult:
    p = scenario.params
    validate_params(p)
    z = lambda: [0.0] * N_YEARS  # noqa: E731
    rates = {k: _v(v) for k, v in p["rates"].items()}
    eff = [e * _v(p["delivery_hours_factor"]) for e in _v(p["delivery_efficiency"])]
    pilot_frac = _v(p["pilot_scope_fraction"])

    seg_rev = {s: z() for s in SEGMENTS}
    seg_new = {s: z() for s in SEGMENTS}
    pen = {s: z() for s in SEGMENTS}
    L = {k: z() for k in (
        "revenue_pilots", "revenue_contracts", "revenue", "cogs_labour", "cogs_hosting", "cogs_licences",
        "cogs", "gross_profit", "headcount_cost", "cac", "procurement", "hosting_base", "soc2",
        "part11_validation", "insurance", "rnd_nonheadcount", "ga_other", "opex", "operating_income",
        "grant_income", "grant_subawards", "net_income", "accounts_receivable", "change_in_ar",
        "cash_flow_pre_financing", "equity", "cash_end", "arr_year_end", "participants",
        "delivery_hours", "delivery_fte", "headcount_fte", "customers", "new_customers",
        "additional_equity_required")}

    for i in range(N_YEARS):
        ar = 0.0
        for seg in SEGMENTS:
            sp = {k: _v(v) for k, v in p["segments"][seg].items()}
            n = _v(p["customers"][seg])[i]
            n_prev = _v(p["customers"][seg])[i - 1] if i > 0 else 0
            retained = min(n, n_prev * sp["retention"])
            new = n - retained
            studies = retained * sp["studies_per_customer"]
            rev_p = new * sp["pilot_price"]
            rev_c = studies * sp["contract_value"]
            rev = rev_p + rev_c
            parts = studies * sp["participants_per_study"] + new * sp["pilot_participants"]
            eng_h = (studies + new) * sp["setup_hours_per_study"] + parts * sp["deploy_hours_per_participant"]
            clin_h = parts * sp["clinical_hours_per_participant"] + (
                studies + new * pilot_frac) * sp["report_hours_per_study"]
            psy_h = (studies + new * pilot_frac) * sp["psychometric_hours_per_study"]
            eng_h, clin_h, psy_h = eng_h * eff[i], clin_h * eff[i], psy_h * eff[i]
            labour = eng_h * rates["engineering"] + clin_h * rates["clinical"] + psy_h * rates["psychometric"]
            L["cogs_labour"][i] += labour
            L["cogs_hosting"][i] += parts * sp["hosting_per_participant_year"]
            L["cogs_licences"][i] += (studies + new) * sp["licence_cost_per_study"]
            L["revenue_pilots"][i] += rev_p
            L["revenue_contracts"][i] += rev_c
            L["participants"][i] += parts
            L["delivery_hours"][i] += eng_h + clin_h + psy_h
            L["cac"][i] += new * sp["cac_per_new_customer"]
            L["procurement"][i] += new * sp["procurement_hours_per_new_customer"] * rates["bd"]
            L["arr_year_end"][i] += (retained + new * sp["retention"]) * sp["studies_per_customer"] * sp[
                "contract_value"]
            L["customers"][i] += n
            L["new_customers"][i] += new
            ar += rev * sp["dso_days"] / 365.0
            seg_rev[seg][i] = rev
            seg_new[seg][i] = new
            u = _v(MARKET_UNIVERSE[seg])[i]
            pen[seg][i] = n / u if u else 0.0

        L["revenue"][i] = L["revenue_pilots"][i] + L["revenue_contracts"][i]
        L["cogs"][i] = L["cogs_labour"][i] + L["cogs_hosting"][i] + L["cogs_licences"][i]
        L["gross_profit"][i] = L["revenue"][i] - L["cogs"][i]
        L["delivery_fte"][i] = L["delivery_hours"][i] / 1_600.0

        oh = _v(p["overhead_multiplier"])
        for role in p["headcount"].values():
            fte = _v(role["fte"])[i]
            L["headcount_fte"][i] += fte
            L["headcount_cost"][i] += fte * _v(role["salary"]) * oh
        for k in ("hosting_base", "soc2", "part11_validation", "insurance", "rnd_nonheadcount", "ga_other"):
            L[k][i] = _v(p["fixed"][k])[i]
        L["opex"][i] = sum(L[k][i] for k in (
            "headcount_cost", "cac", "procurement", "hosting_base", "soc2", "part11_validation", "insurance",
            "rnd_nonheadcount", "ga_other"))
        L["operating_income"][i] = L["gross_profit"][i] - L["opex"][i]
        for g in p["grants"]:
            amt = _v(g["income"])[i]
            L["grant_income"][i] += amt
            L["grant_subawards"][i] += amt * _v(g["subaward_fraction"])
        L["net_income"][i] = L["operating_income"][i] + L["grant_income"][i] - L["grant_subawards"][i]
        L["accounts_receivable"][i] = ar
        prev_ar = L["accounts_receivable"][i - 1] if i > 0 else 0.0
        L["change_in_ar"][i] = ar - prev_ar
        L["cash_flow_pre_financing"][i] = L["net_income"][i] - L["change_in_ar"][i]
        L["equity"][i] = _v(p["equity"])[i]
        prev_cash = L["cash_end"][i - 1] if i > 0 else _v(p["starting_cash"])
        cash = prev_cash + L["cash_flow_pre_financing"][i] + L["equity"][i]
        buffer = _v(p["min_cash_buffer_months"]) / 12.0 * (L["cogs"][i] + L["opex"][i])
        plug = max(0.0, buffer - cash)
        L["additional_equity_required"][i] = plug
        L["cash_end"][i] = cash + plug

    return ModelResult(scenario, L, seg_rev, seg_new, pen, _summarise(scenario, L))


def _first_year(values: list[float], pred) -> int | None:
    for y, v in zip(YEARS, values):
        if pred(v):
            return y
    return None


def _summarise(scenario: Scenario, L: dict[str, list[float]]) -> dict[str, Any]:
    cum, cum_min = _v(scenario.params["starting_cash"]), float("inf")
    for cf in L["cash_flow_pre_financing"]:
        cum += cf
        cum_min = min(cum_min, cum)
    runway = []
    for i in range(N_YEARS):
        nxt = L["cash_flow_pre_financing"][i + 1] if i + 1 < N_YEARS else L["cash_flow_pre_financing"][i]
        burn = max(0.0, -nxt) / 12.0
        runway.append(float("inf") if burn == 0 else max(0.0, L["cash_end"][i]) / burn)
    gm = [(gp / r if r else 0.0) for gp, r in zip(L["gross_profit"], L["revenue"])]
    y3 = YEARS.index(2029)
    return {
        "year3_revenue": L["revenue"][y3],
        "year3_arr": L["arr_year_end"][y3],
        "revenue_2031": L["revenue"][-1],
        "gross_margin": gm,
        "breakeven_year_operating": _first_year(L["operating_income"], lambda v: v >= 0),
        "breakeven_year_incl_grants": _first_year(L["net_income"], lambda v: v >= 0),
        "min_cash_end": min(L["cash_end"]),
        "cumulative_pre_financing_trough": cum_min,
        "funding_need": max(0.0, -cum_min),
        "total_equity": sum(L["equity"]),
        "cash_2031": L["cash_end"][-1],
        "runway_months": runway,
        "breakeven_revenue_2031_cost_base": (L["opex"][-1] / gm[-1]) if gm[-1] > 0 else float("inf"),
        "additional_equity_required": sum(L["additional_equity_required"]),
        "total_capital_required": sum(L["equity"]) + sum(L["additional_equity_required"]),
        "funded_by_assumed_equity": sum(L["additional_equity_required"]) == 0,
        "capital_2027": L["equity"][0],
        "capital_2028_2029": L["equity"][1] + L["equity"][2],
    }


# ---------------------------------------------------------------------------------------------
# Variants for sensitivity
# ---------------------------------------------------------------------------------------------
def variant(scenario: Scenario, suffix: str, *, price_factor: float = 1.0, hours_factor: float = 1.0,
            drop_grants: bool = False, customer_shift: int = 0) -> Scenario:
    """Return a copy of ``scenario`` with simple, labelled sensitivity changes."""
    sc = copy.deepcopy(scenario)
    sc.key = f"{scenario.key}{suffix}"
    p = sc.params
    note = f"sensitivity variant {suffix} of scenario {scenario.key}"
    for seg in SEGMENTS:
        sp = p["segments"][seg]
        for k in ("pilot_price", "contract_value"):
            a = sp[k]
            sp[k] = A(a.value * price_factor, a.label, a.source, a.unit, note)
        for k in ("setup_hours_per_study", "deploy_hours_per_participant", "clinical_hours_per_participant",
                  "psychometric_hours_per_study", "report_hours_per_study"):
            a = sp[k]
            sp[k] = A(a.value * hours_factor, a.label, a.source, a.unit, note)
        c = p["customers"][seg]
        p["customers"][seg] = A([max(0, n + customer_shift) if n > 0 else 0 for n in c.value], c.label, c.source,
                                c.unit, note)
    if drop_grants:
        for g in p["grants"]:
            g["income"] = A([0] * N_YEARS, "INF", "no grant awarded (sensitivity)")
    return sc


# ---------------------------------------------------------------------------------------------
# Assumption register and rendering
# ---------------------------------------------------------------------------------------------
def assumption_register(params: dict[str, Any], prefix: str = "") -> list[tuple[str, Assumption]]:
    out: list[tuple[str, Assumption]] = []
    if isinstance(params, Assumption):
        return [(prefix, params)]
    if isinstance(params, dict):
        for k, v in params.items():
            if k == "name":
                continue
            out += assumption_register(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(params, list):
        for i, v in enumerate(params):
            label = v.get("name", str(i)) if isinstance(v, dict) else str(i)
            out += assumption_register(v, f"{prefix}[{label}]")
    return out


def _m(x: float) -> str:
    if x == float("inf"):
        return "n/a (no burn)"
    sign = "-" if x < 0 else ""
    x = abs(x)
    return f"{sign}${x / 1e6:.2f}M" if x >= 1e6 else f"{sign}${x / 1e3:.0f}K"


def _fmt_value(v: Any) -> str:
    if isinstance(v, list):
        return "[" + ", ".join(f"{x:,.2f}".rstrip("0").rstrip(".") for x in v) + "]"
    if isinstance(v, float):
        return f"{v:,.2f}".rstrip("0").rstrip(".")
    if isinstance(v, int):
        return f"{v:,}"
    return str(v)


_PL_ROWS = [
    ("customers", "Active customers (count)", "n"),
    ("new_customers", "  of which new (pilot year)", "n"),
    ("participants", "Participants / patients supported", "n"),
    ("revenue_pilots", "Revenue: pilots", "$"),
    ("revenue_contracts", "Revenue: contracts/subscriptions", "$"),
    ("revenue", "**Commercial revenue**", "$"),
    ("cogs", "COGS (delivery labour, hosting, licences)", "$"),
    ("gross_profit", "**Gross profit**", "$"),
    ("headcount_cost", "Headcount (R&D, QA/RA, sales, G&A)", "$"),
    ("cac", "CAC (new customers)", "$"),
    ("procurement", "Procurement / vendor qualification", "$"),
    ("soc2", "SOC 2", "$"),
    ("part11_validation", "Part 11 CSV validation", "$"),
    ("insurance", "Insurance (E&O / cyber)", "$"),
    ("hosting_base", "Hosting base", "$"),
    ("rnd_nonheadcount", "R&D non-headcount", "$"),
    ("ga_other", "G&A other", "$"),
    ("opex", "**Total opex**", "$"),
    ("operating_income", "**Operating income (excl. grants)**", "$"),
    ("grant_income", "Grant income", "$"),
    ("grant_subawards", "Grant subawards (STTR research partner)", "$"),
    ("net_income", "**Net income incl. grants (pre-tax)**", "$"),
    ("change_in_ar", "Change in receivables", "$"),
    ("equity", "Equity raised (assumed)", "$"),
    ("additional_equity_required", "Additional equity required (funding gap)", "$"),
    ("cash_end", "**Cash, year end**", "$"),
    ("arr_year_end", "ARR run-rate, year end", "$"),
    ("headcount_fte", "Headcount FTE (non-delivery)", "n"),
    ("delivery_fte", "Delivery FTE equivalent (1,600 h/FTE)", "n"),
]


def render_scenario(res: ModelResult, register: bool = True) -> str:
    sc, L, S = res.scenario, res.lines, res.summary
    out = [f"### Scenario {sc.key}: {sc.title} [HYP]", "", sc.description, ""]
    out.append("| Line | " + " | ".join(str(y) for y in YEARS) + " |")
    out.append("|---|" + "---:|" * N_YEARS)
    for key, name, kind in _PL_ROWS:
        vals = L[key]
        cells = [(_m(v) if kind == "$" else f"{v:,.1f}".rstrip("0").rstrip(".")) for v in vals]
        out.append(f"| {name} | " + " | ".join(cells) + " |")
    out.append("| Gross margin | " + " | ".join(f"{g:.0%}" for g in S["gross_margin"]) + " |")
    out.append("| Runway at year end (months, next-year burn) | " + " | ".join(
        "n/a" if r == float("inf") else f"{r:.0f}" for r in S["runway_months"]) + " |")
    out.append("")
    out.append("Revenue by segment:")
    out.append("")
    out.append("| Segment | " + " | ".join(str(y) for y in YEARS) + " | Penetration 2031 |")
    out.append("|---|" + "---:|" * (N_YEARS + 1))
    for seg in SEGMENTS:
        out.append(f"| {SEGMENT_NAMES[seg]} | " + " | ".join(_m(v) for v in res.segment_revenue[seg]) +
                   f" | {res.penetration[seg][-1]:.0%} |")
    out.append("")
    be_op = S["breakeven_year_operating"] or "not within 2027-2031"
    be_g = S["breakeven_year_incl_grants"] or "not within 2027-2031"
    out += [
        f"- Year-3 (2029) commercial revenue: **{_m(S['year3_revenue'])}**; year-end ARR run-rate "
        f"**{_m(S['year3_arr'])}** [HYP].",
        f"- Operating break-even (excl. grants): **{be_op}**; incl. grants: **{be_g}** [HYP]. Revenue needed "
        f"to cover the 2031 opex at the 2031 gross margin: **{_m(S['breakeven_revenue_2031_cost_base'])}** "
        f"(vs modelled 2031 revenue {_m(S['revenue_2031'])}).",
        f"- Pre-financing cumulative cash trough: **{_m(S['cumulative_pre_financing_trough'])}**; equity "
        f"assumed {_m(S['total_equity'])}; additional equity required to hold a "
        f"{_v(sc.params['min_cash_buffer_months'])}-month cash buffer: **{_m(S['additional_equity_required'])}** "
        f"(total capital required 2027-2031: {_m(S['total_capital_required'])}) [HYP].",
        "",
    ]
    if register:
        out.append("<details><summary>Assumption register for scenario " + sc.key +
                   " (value, label, source)</summary>")
        out.append("")
        out.append("| Parameter | Value | Label | Source / note |")
        out.append("|---|---|---|---|")
        for path, a in assumption_register(sc.params):
            src = (a.source + (f" ({a.note})" if a.note else "")).replace("|", "/")
            unit = f" {a.unit}" if a.unit else ""
            out.append(f"| {path} | {_fmt_value(a.value)}{unit} | [{a.label}] | {src} |")
        out.append("")
        out.append("</details>")
        out.append("")
    return "\n".join(out)


def run_all() -> dict[str, ModelResult]:
    return {k: run_model(s) for k, s in build_scenarios().items()}


def render_markdown() -> str:
    results = run_all()
    scen = build_scenarios()
    lines = [
        "# NeuroMetric financial model outputs (2027-2031)",
        "",
        "**Status: every number on this page is a hypothesis [HYP] computed from labelled assumptions.** "
        "No customer, price, grant or investment has been secured. NeuroMetric is pre-incorporation, has "
        "simulation-only technical results, no clinical validation and no partners. Generated by "
        "`src/neurometric/economics/financial_model.py`; do not edit tables by hand.",
        "",
        "Regenerate:",
        "",
        "```bash",
        "cd /home/user/concord/neurometric",
        "python -m neurometric.economics.financial_model --markdown docs/commercial/financial_model_outputs.md",
        "python -m pytest tests/test_economics.py -q",
        "```",
        "",
        "## 1. Headline comparison [HYP]",
        "",
        "| Scenario | 2029 revenue | 2029 ARR run-rate | 2031 revenue | Gross margin 2029 | Operating break-even "
        "| Break-even incl. grants | Pre-financing trough | Equity assumed | Additional equity required "
        "| Total capital 2027-31 |",
        "|---|---:|---:|---:|---:|---|---|---:|---:|---:|---:|",
    ]
    for k, r in results.items():
        S = r.summary
        lines.append(
            f"| {k}: {r.scenario.title} | {_m(S['year3_revenue'])} | {_m(S['year3_arr'])} | {_m(S['revenue_2031'])} "
            f"| {S['gross_margin'][2]:.0%} | {S['breakeven_year_operating'] or 'after 2031'} "
            f"| {S['breakeven_year_incl_grants'] or 'after 2031'} | {_m(S['cumulative_pre_financing_trough'])} "
            f"| {_m(S['total_equity'])} | {_m(S['additional_equity_required'])} "
            f"| {_m(S['total_capital_required'])} |")
    lines += [
        "",
        "Founder-playbook Year-3 ARR hypotheses for comparison (not inputs): conservative "
        f"{_m(PLAYBOOK_YEAR3_ARR['conservative'])}, base {_m(PLAYBOOK_YEAR3_ARR['base'])}, upside "
        f"{_m(PLAYBOOK_YEAR3_ARR['upside'])}. Playbook capital: $150-400K in months 0-12 and $1.5-3M in "
        "months 12-30.",
        "",
        "## 2. Sensitivity (scenario B and C) [HYP]",
        "",
        "| Variant | 2029 revenue | 2029 ARR | Operating break-even | Pre-financing trough | Total capital "
        "required |",
        "|---|---:|---:|---|---:|---:|",
    ]
    for base in ("B", "C"):
        for suffix, kw, label in (
            ("", {}, "as modelled"),
            ("-p30", {"price_factor": 0.7}, "prices -30%"),
            ("+p50", {"price_factor": 1.5}, "prices +50% (playbook upper range validated)"),
            ("-h30", {"hours_factor": 1.3}, "delivery hours +30%"),
            ("-ng", {"drop_grants": True}, "no grants awarded"),
            ("-c1", {"customer_shift": -1}, "one fewer customer in every active segment-year"),
        ):
            sc = variant(scen[base], suffix, **kw) if suffix else scen[base]
            S = run_model(sc).summary
            lines.append(
                f"| {base} {label} | {_m(S['year3_revenue'])} | {_m(S['year3_arr'])} | "
                f"{S['breakeven_year_operating'] or 'after 2031'} | {_m(S['cumulative_pre_financing_trough'])} | "
                f"{_m(S['total_capital_required'])} |")
    lines += [
        "",
        "## 3. Market universe used as a ceiling (organisations, not patients) [INF]",
        "",
        "| Segment | " + " | ".join(str(y) for y in YEARS) + " | Label | Source |",
        "|---|" + "---:|" * N_YEARS + "---|---|",
    ]
    for seg in SEGMENTS:
        a = MARKET_UNIVERSE[seg]
        lines.append(f"| {SEGMENT_NAMES[seg]} | " + " | ".join(str(v) for v in a.value) +
                     f" | [{a.label}] | {a.source} |")
    lines += ["", "The model refuses any scenario whose customer count exceeds this universe.", "",
              "## 4. Scenario detail", ""]
    for r in results.values():
        lines.append(render_scenario(r))
    lines += [
        "## 5. How to read and challenge this model",
        "",
        "- Commercial revenue excludes grants. Grants appear below operating income; STTR subawards to the "
        "research partner (>=30%) are deducted.",
        "- Delivery labour sits in COGS by the hour; the headcount plan excludes delivery staff. The "
        "'Delivery FTE equivalent' row shows how many people delivery implies.",
        "- New customers pay for a pilot in their first year; retained customers pay contract value. ARR "
        "run-rate assumes pilots convert at the segment retention rate.",
        "- Taxes, depreciation, interest, founder equity dilution and FX are ignored.",
        "- The decisive unknowns are willingness to pay (pricing test in PRICING_HYPOTHESES.md), the number of "
        "sponsors that buy third-party evidence at all, and STTR award timing.",
        "",
    ]
    return "\n".join(lines)


def to_json() -> dict[str, Any]:
    out = {}
    for k, r in run_all().items():
        out[k] = {"title": r.scenario.title, "lines": r.lines, "segment_revenue": r.segment_revenue,
                  "summary": {kk: vv for kk, vv in r.summary.items()}}
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--markdown", help="write markdown tables to this path")
    ap.add_argument("--json", help="write JSON results to this path")
    args = ap.parse_args(argv)
    md = render_markdown()
    if args.markdown:
        with open(args.markdown, "w", encoding="utf-8") as fh:
            fh.write(md)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(to_json(), fh, indent=1, default=str)
    if not args.markdown and not args.json:
        print(md)


if __name__ == "__main__":
    main()
