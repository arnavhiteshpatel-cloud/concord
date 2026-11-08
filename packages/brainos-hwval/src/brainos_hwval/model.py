"""Check results, thresholds and the overall verdict (no I/O).

Every check has one of four statuses. There is no score: the overall result is FAIL if any
required check failed, INCONCLUSIVE if a required check could not decide (or was not run),
and PASS only if every required check passed. Advisory checks (properties of the source or
of the reference recording, not of BrainOS) are reported but never change the verdict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Status(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"
    NOT_TESTED = "not_tested"


class Category(StrEnum):
    INPUT = "input"  # the files themselves (loadable, internally consistent)
    IDENTITY = "identity"  # same stream / same source in both recordings
    METADATA = "metadata"  # channels, rates, units, formats
    INTEGRITY = "integrity"  # samples: loss, duplication, order, values
    TIMING = "timing"  # timestamps, clocks, delay
    SOURCE = "source"  # properties of the source or the reference (advisory)
    SCOPE = "scope"  # what the evidence can support


class InputError(Exception):
    """A file is missing, unreadable or not in the documented format (exit code 2)."""


@dataclass
class Check:
    id: str
    title: str
    category: Category
    required: bool
    status: Status
    summary: str
    method: str  # the exact test performed, in words
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "category": self.category.value,
            "required": self.required,
            "status": self.status.value,
            "summary": self.summary,
            "method": self.method,
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class Thresholds:
    """Decision thresholds. Every value used is written into the report."""

    # LSL: a BrainOS frame timestamp and a reference sample timestamp denote the same
    # sample if they differ by at most this fraction of a sample period.
    match_fraction_of_period: float = 0.25
    # Timestamps are copies of the same source timestamps: anything above this is reported.
    timestamp_exact_s: float = 2e-6
    # LSL values: relative tolerance. BrainOS converts in float64, so values are normally
    # bit-exact (counted separately); differences at single-precision level (a float32 stage
    # anywhere) are an expected numerical tolerance, not corruption. --value-rtol 0 demands
    # bit-exact values.
    value_rtol: float = 2.5e-7
    value_atol: float = 0.0
    float32_rtol: float = 2.5e-7
    # Open Ephys: the Record Node stores round(µV / bit_volts) as int16, so the expected
    # difference is at most half a quantisation step (+ float32 rounding of the scale).
    quantisation_steps: float = 0.51
    # Fraction of reference samples (within the overlap) BrainOS may miss. Default: none.
    max_loss_fraction: float = 0.0
    # Minimum overlap of the two recordings for the comparison to be conclusive.
    min_overlap_s: float = 5.0
    # Excess ingest delay (above the best observed) tolerated before data counts as delayed.
    max_excess_delay_s: float = 1.0
    # Effective vs nominal sampling rate (advisory, a property of the source clock).
    rate_ppm_advisory: float = 500.0
    # Content alignment: number of frames verified independently of timestamps.
    content_probe_frames: int = 24

    def to_json(self) -> dict[str, Any]:
        return dict(self.__dict__)


def overall(checks: list[Check]) -> Status:
    required = [c for c in checks if c.required]
    if any(c.status is Status.FAIL for c in required):
        return Status.FAIL
    if any(c.status in (Status.INCONCLUSIVE, Status.NOT_TESTED) for c in required):
        return Status.INCONCLUSIVE
    return Status.PASS if required else Status.INCONCLUSIVE


EXIT_CODES: dict[Status, int] = {
    Status.PASS: 0,
    Status.FAIL: 1,
    Status.INCONCLUSIVE: 3,
    Status.NOT_TESTED: 3,
}
EXIT_INPUT_ERROR = 2
