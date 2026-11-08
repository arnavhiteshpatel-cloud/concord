from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from brainflow.board_shim import BoardShim

sys.path.insert(0, str(Path(__file__).parent))


@pytest.fixture(autouse=True, scope="session")
def _quiet_brainflow() -> Iterator[None]:
    BoardShim.disable_board_logger()
    yield
    BoardShim.enable_board_logger()
