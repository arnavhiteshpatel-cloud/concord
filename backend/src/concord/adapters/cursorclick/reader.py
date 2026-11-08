"""Reader for the Singer-Clark et al. cursor + click blocks (Dryad doi:10.5061/dryad.prr4xgxzq).

One ``.mat`` file = one block of one day for participant T15, 10 ms bins. Field meanings follow
the dataset README (shipped with the download):

* ``threshold_crossings`` (bins x 256, counts) and ``spike_band_power`` (bins x 256, mean squared
  filtered signal; the README does not state the signal unit, so Concord declares it unknown).
* ``cursor_position`` / ``target_position``: screen coordinates, origin at the centre, +x right,
  **+y up**, 1.0 = screen height.
* ``cursor_decoder_output`` (units/s) and ``click_decoder_output`` (0/1): what the *original*
  online decoders produced during the session. They are historical decoder outputs, never
  Concord's.
* ``assist_amount`` (0 = fully neural cursor) and ``click_assist`` (true = selection by the
  computer after dwell, not by the click decoder).

Only processed features are published; there is no raw voltage in this dataset.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

BIN_S = 0.01
NAME_RE = re.compile(r"^(t\d+)_day(\d+)_block(\d+)_(.+?)(?:_task)?\.mat$")
REQUIRED = (
    "timestamp_sec",
    "threshold_crossings",
    "spike_band_power",
    "assist_amount",
    "cursor_position",
    "target_position",
    "trial_idx",
    "cursor_decoder_output",
    "trial_start_bin",
    "cursor_radius",
    "array_label_by_electrode",
)


class T15FormatError(ValueError):
    """The file is not a block of the cursor + click dataset in the expected layout."""


@dataclass(frozen=True)
class T15Block:
    path: Path
    participant: str
    day: int
    block: int
    task: str  # radial8_calibration | grid_evaluation | simultaneous_speech_and_cursor
    tx: NDArray[np.int16]  # bins x channels
    sbp: NDArray[np.float32]  # bins x channels
    array_labels: tuple[str, ...]
    cursor: NDArray[np.float64]  # bins x 2, +y up
    target: NDArray[np.float64]  # bins x 2, +y up
    assist: NDArray[np.float64]  # bins
    click_assist: NDArray[np.bool_] | None  # bins; None when the session had no click
    trial_idx: NDArray[np.int64]  # bins
    trial_start_bin: NDArray[np.int64]  # trials
    cursor_decoder: NDArray[np.float64]  # bins x 2, units/s, +y up
    click_decoder: NDArray[np.int8] | None  # bins (0/1); None when the session had no click
    cursor_radius: float
    target_radius: float | None  # circular-target tasks
    grid_rows: int | None  # grid task
    grid_height: float | None  # grid task
    dwell_s: float | None  # sessions without click

    @property
    def n_bins(self) -> int:
        return int(self.tx.shape[0])

    @property
    def channel_count(self) -> int:
        return int(self.tx.shape[1])

    @property
    def duration_s(self) -> float:
        return self.n_bins * BIN_S

    @property
    def has_click(self) -> bool:
        return self.click_decoder is not None

    @property
    def fully_neural(self) -> bool:
        """No cursor assist and no click assist anywhere in the block."""
        no_click_assist = self.click_assist is None or not bool(self.click_assist.any())
        return bool(np.all(self.assist == 0)) and no_click_assist

    @property
    def session(self) -> str:
        return f"{self.participant}-day{self.day:05d}"

    @property
    def name(self) -> str:
        return f"{self.participant}_day{self.day:05d}_block{self.block:02d}_{self.task}"

    def bin_end_s(self, i: int) -> float:
        return (i + 1) * BIN_S

    def cell_half(self) -> float | None:
        if self.grid_rows is None or self.grid_height is None:
            return None
        return self.grid_height / self.grid_rows / 2

    def on_target(self) -> NDArray[np.bool_]:
        """Whether the cursor touches the cued target, by the task's own rule (README)."""
        half = self.cell_half()
        if half is not None:
            out: NDArray[np.bool_] = np.all(np.abs(self.target - self.cursor) < half, axis=1)
            return out
        if self.target_radius is None:
            raise T15FormatError(f"{self.path.name}: no target geometry")
        d = np.linalg.norm(self.target - self.cursor, axis=1)
        within: NDArray[np.bool_] = d < (self.target_radius + self.cursor_radius)
        return within

    def click_bins(self) -> NDArray[np.int64]:
        """Bins where the original click decoder output rose to 1."""
        if self.click_decoder is None:
            return np.zeros(0, dtype=np.int64)
        c = self.click_decoder.astype(np.int8)
        return np.flatnonzero(np.diff(np.concatenate([[0], c])) > 0).astype(np.int64)


def parse_name(path: Path) -> tuple[str, int, int, str]:
    m = NAME_RE.match(path.name)
    if not m:
        raise T15FormatError(
            f"{path.name}: not a cursor+click block file (t15_dayNNNNN_blockNN_<task>.mat)"
        )
    return m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)


def _scalar(m: dict[str, object], key: str) -> float | None:
    v = m.get(key)
    if v is None:
        return None
    arr = np.asarray(v, dtype=np.float64).ravel()
    return float(arr[0]) if arr.size else None


def load(path: Path) -> T15Block:
    import scipy.io

    path = Path(path)
    participant, day, block, task = parse_name(path)
    try:
        m = scipy.io.loadmat(str(path))
    except (ValueError, OSError, NotImplementedError) as exc:
        raise T15FormatError(f"{path.name}: cannot read MATLAB file: {exc}") from exc
    missing = [k for k in REQUIRED if k not in m]
    if missing:
        raise T15FormatError(f"{path.name}: missing fields {missing}")
    tx = np.asarray(m["threshold_crossings"])
    sbp = np.asarray(m["spike_band_power"], dtype=np.float32)
    n = tx.shape[0]
    if tx.ndim != 2 or sbp.shape != tx.shape:
        raise T15FormatError(
            f"{path.name}: threshold_crossings {tx.shape} and spike_band_power {sbp.shape} differ"
        )
    if np.any(tx < 0) or not np.all(np.isfinite(sbp)) or np.any(sbp < 0):
        raise T15FormatError(f"{path.name}: negative counts or non-finite/negative power")

    def per_bin(key: str, cols: int | None = None) -> NDArray[np.float64]:
        a = np.asarray(m[key], dtype=np.float64)
        if a.size != n * (cols or 1):
            raise T15FormatError(
                f"{path.name}: {key} has {a.size} values, expected {n} bins x {cols or 1}"
            )
        return a.reshape(n, cols) if cols else a.ravel()

    ts = per_bin("timestamp_sec")
    if not np.allclose(np.diff(ts), BIN_S, atol=1e-6):
        raise T15FormatError(f"{path.name}: bins are not contiguous 10 ms bins")
    labels = tuple(str(x).strip() for x in np.ravel(m["array_label_by_electrode"]))
    if len(labels) != tx.shape[1]:
        raise T15FormatError(f"{path.name}: {len(labels)} array labels for {tx.shape[1]} channels")
    click = m.get("click_decoder_output")
    click_assist = m.get("click_assist")
    grid_rows = _scalar(m, "grid_num_rows")
    return T15Block(
        path=path,
        participant=participant,
        day=day,
        block=block,
        task=task,
        tx=tx.astype(np.int16),
        sbp=sbp,
        array_labels=labels,
        cursor=per_bin("cursor_position", 2),
        target=per_bin("target_position", 2),
        assist=per_bin("assist_amount"),
        click_assist=per_bin("click_assist").astype(bool) if click_assist is not None else None,
        trial_idx=per_bin("trial_idx").astype(np.int64),
        trial_start_bin=np.asarray(m["trial_start_bin"]).ravel().astype(np.int64),
        cursor_decoder=per_bin("cursor_decoder_output", 2),
        click_decoder=per_bin("click_decoder_output").astype(np.int8)
        if click is not None
        else None,
        cursor_radius=float(_scalar(m, "cursor_radius") or 0.0),
        target_radius=_scalar(m, "target_radius"),
        grid_rows=int(grid_rows) if grid_rows is not None else None,
        grid_height=_scalar(m, "grid_total_height"),
        dwell_s=_scalar(m, "dwell_requirement_sec"),
    )
