"""Make the test helpers (synth, refsoft, helpers) importable."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
