"""Care-partner time valuation with guardrails.

What this module does
---------------------
Puts a dollar value on *care-partner time* (hours of informal care per day) using either
(a) replacement cost: the wage of a market substitute (BLS home health and personal care aides), or
(b) opportunity cost: a forgone-wage proxy (BLS all-occupations mean wage), optionally discounted
    for caregivers outside paid work.

What it refuses to do (guardrails)
----------------------------------
1. It never labels a result as anything but a **hypothetical scenario** unless it is given an
   :class:`ObservedEffect` from a study, with a confidence interval, measured as care-partner time.
2. It never converts a reduction in *participant task time* (e.g., a faster digital task) into
   care-partner hours. Such inputs raise :class:`GuardrailError`.
3. It never converts care-partner time into **healthcare cost savings**, payer savings, budget
   impact or ROI. Informal care time is not a healthcare expenditure; a value of time is not a cash
   saving to any payer. Any attempt raises :class:`GuardrailError`.

Wage sources (accessed 2026-11-27)
----------------------------------
- BLS Occupational Outlook Handbook, Home Health and Personal Care Aides: median pay $17.21 per hour
  ("2025 Median Pay"); median annual wage $35,800 in May 2025.
  https://www.bls.gov/ooh/healthcare/home-health-aides-and-personal-care-aides.htm  [V]
- BLS OEWS news release "Occupational Employment and Wages - May 2025": U.S. average (mean) wage
  $69,770 per year. https://www.bls.gov/news.release/ocwage.nr0.htm  [V]; hourly figure derived as
  69,770 / 2,080 h = $33.54 [INF]. This is a mean, not a median, and overstates a typical wage.
- Agency charge for a home health aide (what families pay, ~2x wage) is prior knowledge only:
  Genworth/CareScout medians in the low-to-mid $30s per hour around 2023-2024 [PK, not re-verified].
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Sequence

HYPOTHETICAL = "HYPOTHETICAL SCENARIO"
OBSERVED = "OBSERVED-EFFECT ESTIMATE (study-specific; not generalisable without replication)"

NOT_SAVINGS_NOTICE = (
    "This is a valuation of care-partner time. It is NOT healthcare cost savings, NOT payer savings, "
    "NOT a budget impact and NOT a return on investment. No money changes hands because informal care "
    "time is valued."
)

#: Measures accepted as care-partner time. Participant task-time measures are refused.
CARE_TIME_MEASURES = frozenset({
    "care_partner_time_diary",
    "care_partner_time_ema",
    "care_partner_time_recall",
    "paid_care_hours_records",
})
REFUSED_MEASURES = frozenset({
    "participant_task_time",
    "task_completion_time",
    "selection_time",
    "typing_speed",
    "device_performance",
})


class GuardrailError(ValueError):
    """Raised when a request would overstate what care-time valuation can show."""


@dataclass(frozen=True)
class WageBasis:
    name: str
    method: str  # "replacement" or "opportunity"
    hourly: float
    label: str
    source: str
    reference_period: str
    note: str = ""

    def __post_init__(self) -> None:
        if self.method not in ("replacement", "opportunity"):
            raise ValueError("method must be 'replacement' or 'opportunity'")
        if self.hourly <= 0:
            raise ValueError("hourly value must be positive")


BLS_HHA_PCA_URL = "https://www.bls.gov/ooh/healthcare/home-health-aides-and-personal-care-aides.htm"
BLS_OEWS_URL = "https://www.bls.gov/news.release/ocwage.nr0.htm"

BLS_HOME_HEALTH_AIDE_MEDIAN = WageBasis(
    name="BLS median wage, home health and personal care aides",
    method="replacement",
    hourly=17.21,
    label="V",
    source=BLS_HHA_PCA_URL + " (accessed 2026-11-27)",
    reference_period="2025 median pay (median annual wage $35,800, May 2025)",
)
AGENCY_CHARGE_PK = WageBasis(
    name="Home health aide agency charge (order of magnitude)",
    method="replacement",
    hourly=34.0,
    label="PK",
    source="Genworth/CareScout Cost of Care surveys, prior cycle; not re-verified",
    reference_period="~2023-2024",
    note="Use only as an upper replacement-cost bound; re-verify before external use.",
)
BLS_ALL_OCCUPATIONS_MEAN = WageBasis(
    name="BLS all-occupations mean wage (opportunity cost)",
    method="opportunity",
    hourly=round(69_770 / 2_080, 2),
    label="INF",
    source=BLS_OEWS_URL + " (mean annual $69,770, May 2025 [V]; /2,080 h [INF]; accessed 2026-11-27)",
    reference_period="May 2025",
    note="Mean, not median; overstates a typical forgone wage.",
)


def opportunity_cost_basis(employed_share: float, leisure_value_fraction: float = 0.5,
                           wage: WageBasis = BLS_ALL_OCCUPATIONS_MEAN) -> WageBasis:
    """Blend forgone wage for employed caregivers with a discounted value for non-employed ones."""
    if not 0 <= employed_share <= 1 or not 0 <= leisure_value_fraction <= 1:
        raise ValueError("shares must be in [0, 1]")
    hourly = wage.hourly * (employed_share + (1 - employed_share) * leisure_value_fraction)
    return WageBasis(
        name=f"Opportunity cost ({employed_share:.0%} employed; leisure at {leisure_value_fraction:.0%} of wage)",
        method="opportunity", hourly=round(hourly, 2), label="HYP",
        source=f"derived from {wage.name}: {wage.source}", reference_period=wage.reference_period,
        note="Employment share and leisure valuation are hypotheses for the caregiver population.")


@dataclass(frozen=True)
class ObservedEffect:
    """A measured change in care-partner time from a study, with a confidence interval.

    ``hours_per_day`` is the reduction (positive) or increase (negative) in care-partner hours per day.
    """

    hours_per_day: float
    ci_low: float
    ci_high: float
    ci_level: float
    n: int
    measure: str
    study: str
    design: str

    def __post_init__(self) -> None:
        if self.measure in REFUSED_MEASURES or self.measure not in CARE_TIME_MEASURES:
            raise GuardrailError(
                f"measure {self.measure!r} is not a care-partner time measure. Participant task-time or "
                f"device-performance gains cannot be converted into care-partner hours. Accepted: "
                f"{sorted(CARE_TIME_MEASURES)}")
        if not (self.ci_low <= self.hours_per_day <= self.ci_high):
            raise ValueError("estimate must lie within its confidence interval")
        if not 0 < self.ci_level < 1:
            raise ValueError("ci_level must be in (0, 1), e.g. 0.95")
        if self.n <= 0:
            raise ValueError("n must be positive")
        if not self.study.strip() or not self.design.strip():
            raise ValueError("study identifier and design are required")
        for v in (self.hours_per_day, self.ci_low, self.ci_high):
            if abs(v) > 24:
                raise ValueError("hours per day cannot exceed 24")


@dataclass(frozen=True)
class CareTimeValuation:
    status: str
    hours_per_day: float
    days_per_year: float
    wage: WageBasis
    annual_value: float
    annual_value_ci: tuple[float, float] | None = None
    ci_level: float | None = None
    study: str | None = None
    caveats: tuple[str, ...] = field(default_factory=tuple)
    notice: str = NOT_SAVINGS_NOTICE
    is_healthcare_cost_saving: bool = False  # always False; kept explicit for downstream code

    @property
    def is_hypothetical(self) -> bool:
        return self.status == HYPOTHETICAL

    def as_healthcare_savings(self) -> None:
        """Always refuses. Present so that misuse fails loudly instead of silently."""
        raise GuardrailError(NOT_SAVINGS_NOTICE)

    def render(self) -> str:
        lines = [f"**{self.status}** - care-partner time valuation ({self.wage.method} cost)"]
        if self.annual_value_ci is not None:
            lo, hi = self.annual_value_ci
            lines.append(f"- {self.hours_per_day:+.2f} h/day (study {self.study}; {self.ci_level:.0%} CI) x "
                         f"{self.days_per_year:g} days x ${self.wage.hourly:.2f}/h = ${self.annual_value:,.0f}/yr "
                         f"(CI ${lo:,.0f} to ${hi:,.0f})")
        else:
            lines.append(f"- {self.hours_per_day:+.2f} h/day (assumed, not observed) x {self.days_per_year:g} days x "
                         f"${self.wage.hourly:.2f}/h = ${self.annual_value:,.0f}/yr")
        lines.append(f"- Wage basis: {self.wage.name} [{self.wage.label}], {self.wage.reference_period}; "
                     f"{self.wage.source}")
        for c in self.caveats:
            lines.append(f"- Caveat: {c}")
        lines.append(f"- {self.notice}")
        return "\n".join(lines)


_FORBIDDEN_KWARGS = {"as_cost_savings", "as_healthcare_savings", "payer_savings", "budget_impact", "roi"}


def value_care_time(effect: float | ObservedEffect, wage: WageBasis = BLS_HOME_HEALTH_AIDE_MEDIAN,
                    days_per_year: float = 365.0, **kwargs) -> CareTimeValuation:
    """Value a change in care-partner hours per day.

    A bare number is treated as an *assumed* change and the result is labelled HYPOTHETICAL SCENARIO.
    Only an :class:`ObservedEffect` (with CI, from a study, measured as care-partner time) yields an
    observed-effect estimate.
    """
    bad = _FORBIDDEN_KWARGS & set(kwargs)
    if bad:
        raise GuardrailError(f"{sorted(bad)} requested. {NOT_SAVINGS_NOTICE}")
    if kwargs:
        raise TypeError(f"unexpected arguments {sorted(kwargs)}")
    if not 0 < days_per_year <= 366:
        raise ValueError("days_per_year must be in (0, 366]")

    caveats = [
        "Care needs change over time (e.g., ALS progression increases care); a benefit may appear as a slower "
        "increase, not a reduction.",
        "Valuing time does not imply any caregiver will be paid less or any service will be purchased less.",
    ]
    if isinstance(effect, ObservedEffect):
        annual = effect.hours_per_day * days_per_year * wage.hourly
        lo = effect.ci_low * days_per_year * wage.hourly
        hi = effect.ci_high * days_per_year * wage.hourly
        if effect.ci_low <= 0 <= effect.ci_high:
            caveats.insert(0, "The confidence interval includes zero: the study does not show a change in "
                              "care-partner time.")
        caveats.append(f"Applies to the studied population and design ({effect.design}, n={effect.n}) only.")
        return CareTimeValuation(OBSERVED, effect.hours_per_day, days_per_year, wage, annual, (lo, hi),
                                 effect.ci_level, effect.study, tuple(caveats))

    if isinstance(effect, bool) or not isinstance(effect, (int, float)):
        raise TypeError("effect must be a number (assumed hours/day) or an ObservedEffect")
    if abs(effect) > 24:
        raise ValueError("hours per day cannot exceed 24")
    caveats.insert(0, "The hours/day value is an assumption, not a measurement. No NeuroMetric or BCI study has "
                      "measured care-partner time to date.")
    return CareTimeValuation(HYPOTHETICAL, float(effect), days_per_year, wage,
                             float(effect) * days_per_year * wage.hourly, caveats=tuple(caveats))


def sensitivity_table(hours_grid: Sequence[float] = (0.25, 0.5, 1.0, 2.0),
                      wages: Iterable[WageBasis] = (BLS_HOME_HEALTH_AIDE_MEDIAN, AGENCY_CHARGE_PK,
                                                    BLS_ALL_OCCUPATIONS_MEAN),
                      days_per_year: float = 365.0) -> list[CareTimeValuation]:
    """Grid of hypothetical valuations. Every cell is labelled HYPOTHETICAL SCENARIO."""
    return [value_care_time(h, w, days_per_year) for w in wages for h in hours_grid]


def render_sensitivity_markdown(rows: Sequence[CareTimeValuation]) -> str:
    if any(not r.is_hypothetical for r in rows):
        raise GuardrailError("sensitivity tables are for hypothetical scenarios only; report observed "
                             "effects separately with their CI")
    hours = sorted({r.hours_per_day for r in rows})
    wages: list[WageBasis] = []
    for r in rows:
        if r.wage not in wages:
            wages.append(r.wage)
    out = [f"**{HYPOTHETICAL}: annual value of care-partner time per participant (USD/yr).** "
           "Hours/day are assumptions, not results.", "",
           "| Wage basis | Label | $/h | " + " | ".join(f"{h:g} h/day" for h in hours) + " |",
           "|---|---|---:|" + "---:|" * len(hours)]
    for w in wages:
        cells = []
        for h in hours:
            match = [r for r in rows if r.wage == w and r.hours_per_day == h]
            cells.append(f"${match[0].annual_value:,.0f}" if match else "")
        out.append(f"| {w.name} ({w.method}) | [{w.label}] | {w.hourly:.2f} | " + " | ".join(cells) + " |")
    out += ["", NOT_SAVINGS_NOTICE]
    return "\n".join(out)


def __getattr__(name: str):  # pragma: no cover - defensive: block likely misuse names
    if "saving" in name.lower() or "budget_impact" in name.lower() or name.lower() == "roi":
        raise GuardrailError(f"{name}: {NOT_SAVINGS_NOTICE}")
    raise AttributeError(name)
