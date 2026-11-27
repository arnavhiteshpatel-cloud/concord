"""Text-entry metrics (Soukoreff & MacKenzie 2003 taxonomy; MacKenzie & Soukoreff 2002) [PK].

Inputs are the presented string P, the final transcribed string T, the input stream (sequence of
keystrokes, where BACKSPACE is the editing key) and the elapsed time. Text *content* is only
processed for copy-typing tasks with predefined phrases; free text is never stored by default
(see DATA_GOVERNANCE.md).
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

BACKSPACE = "\b"


def msd(a: str, b: str) -> int:
    """Minimum string distance (Levenshtein) between a and b."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def apply_stream(stream: list[str]) -> str:
    out: list[str] = []
    for k in stream:
        if k == BACKSPACE:
            if out:
                out.pop()
        else:
            out.append(k)
    return "".join(out)


@dataclass
class TextEntryResult:
    presented_len: int
    transcribed_len: int
    keystrokes: int
    seconds: float
    msd: int
    msd_error_rate: float
    wpm: float
    ccpm: float  # correct characters per minute
    kspc: float
    C: int
    INF: int
    IF: int
    F: int
    corrected_error_rate: float
    uncorrected_error_rate: float
    total_error_rate: float
    correction_burden: float  # editing keystrokes per transcribed character

    def to_dict(self):
        return asdict(self)


def text_entry_metrics(presented: str, stream: list[str], seconds: float) -> TextEntryResult:
    """Compute text-entry metrics from a keystroke stream.

    WPM = (|T| - 1) / S * 60 / 5 (the first character starts the clock).
    CCPM = max(|T| - MSD(P, T), 0) / minutes.
    Soukoreff & MacKenzie (2003): C = correct, INF = incorrect not fixed (= MSD), IF = incorrect
    fixed (non-editing keystrokes later erased), F = editing keystrokes (backspaces).
    """
    T = apply_stream(stream)
    d = msd(presented, T)
    n_max = max(len(presented), len(T))
    C = max(n_max - d, 0)
    INF = d
    F = sum(1 for k in stream if k == BACKSPACE)
    non_edit = len(stream) - F
    IF = max(non_edit - len(T), 0)
    denom = C + INF + IF
    minutes = seconds / 60.0 if seconds > 0 else float("nan")
    return TextEntryResult(
        presented_len=len(presented), transcribed_len=len(T), keystrokes=len(stream),
        seconds=seconds, msd=d, msd_error_rate=d / n_max if n_max else 0.0,
        wpm=((len(T) - 1) / seconds * 60 / 5) if seconds > 0 and len(T) > 0 else float("nan"),
        ccpm=max(len(T) - d, 0) / minutes if seconds > 0 else float("nan"),
        kspc=len(stream) / len(T) if T else float("nan"),
        C=C, INF=INF, IF=IF, F=F,
        corrected_error_rate=IF / denom if denom else 0.0,
        uncorrected_error_rate=INF / denom if denom else 0.0,
        total_error_rate=(INF + IF) / denom if denom else 0.0,
        correction_burden=F / len(T) if T else float("nan"),
    )
