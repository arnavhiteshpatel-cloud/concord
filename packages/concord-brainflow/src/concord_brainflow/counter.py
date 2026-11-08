"""Sample-loss inference from BrainFlow's ``package_num`` row.

BrainFlow writes a package counter into every sample row. Its range is board-specific and
not described by ``get_board_descr``; BrainFlow's synthetic board uses an 8-bit counter
(``unsigned char counter`` in ``src/board_controller/synthetic_board.cpp``, wrapping at
256), so the default modulus is 256. Step ``k`` between consecutive samples (modulo the
counter range) means ``k - 1`` samples were lost. A repeated number is counted but treated
as the next sample. If a counter value is not an integer in ``[0, modulus)`` the counter is
not usable for this board: inference is switched off (``package_num_unusable``) instead of
inventing gaps. A gap of a whole multiple of the modulus cannot be detected.
"""

from __future__ import annotations

import logging
from typing import Any

import numpy as np
from numpy.typing import NDArray

log = logging.getLogger(__name__)


class PackageCounter:
    def __init__(self, modulus: int) -> None:
        if modulus < 0:
            raise ValueError("modulus must be >= 0")
        self.modulus = modulus
        self.enabled = modulus > 0
        self.unusable = False
        self.next_index = 0
        self.dropped = 0
        self.repeats = 0
        self._prev: int | None = None

    def assign(self, package_nums: NDArray[np.floating[Any]]) -> NDArray[np.int64]:
        """Return the sample index (since open) of each new sample."""
        n = int(package_nums.shape[0])
        if n == 0:
            return np.zeros(0, dtype=np.int64)
        if self.enabled:
            ok = bool(np.all(np.isfinite(package_nums)))
            if ok:
                ints = package_nums.astype(np.int64)
                ok = bool(np.all(ints == package_nums)) and bool(
                    np.all((ints >= 0) & (ints < self.modulus))
                )
            if not ok:
                log.warning(
                    "package_num values outside [0, %d): loss inference disabled", self.modulus
                )
                self.enabled = False
                self.unusable = True
        if not self.enabled:
            idx = self.next_index + np.arange(n, dtype=np.int64)
            self.next_index += n
            return idx
        ints = package_nums.astype(np.int64)
        prev = int(ints[0]) - 1 if self._prev is None else self._prev
        steps = np.diff(np.concatenate(([prev], ints))) % self.modulus
        repeats = steps == 0
        self.repeats += int(np.count_nonzero(repeats))
        steps[repeats] = 1
        self.dropped += int(np.sum(steps - 1))
        idx = self.next_index - 1 + np.cumsum(steps)
        self.next_index = int(idx[-1]) + 1
        self._prev = int(ints[-1])
        return idx.astype(np.int64)
