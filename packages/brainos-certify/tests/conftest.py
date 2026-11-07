from __future__ import annotations

from typing import Any

import pytest
from certify_helpers import certify


@pytest.fixture(scope="session")
def good_report() -> dict[str, Any]:
    """A full run of the well-behaved plugin, including the BrainOS runtime phase."""
    return certify(runtime=True, options={"api_token": "s3cr3t-value"})
