"""Simulated neural-interface profiles. Synthetic; not models of commercial devices."""

from brainos.adapters.simulated.base import Fault, SimulatedAdapter
from brainos.adapters.simulated.intent_source import OperatorIntentSource
from brainos.adapters.simulated.profile_a import ProfileAAdapter
from brainos.adapters.simulated.profile_b import ProfileBAdapter

__all__ = [
    "Fault",
    "OperatorIntentSource",
    "ProfileAAdapter",
    "ProfileBAdapter",
    "SimulatedAdapter",
]
