"""Simulated neural-interface profiles. Synthetic; not models of commercial devices."""

from concord.adapters.simulated.base import Fault, SimulatedAdapter
from concord.adapters.simulated.intent_source import OperatorIntentSource
from concord.adapters.simulated.profile_a import ProfileAAdapter
from concord.adapters.simulated.profile_b import ProfileBAdapter

__all__ = [
    "Fault",
    "OperatorIntentSource",
    "ProfileAAdapter",
    "ProfileBAdapter",
    "SimulatedAdapter",
]
