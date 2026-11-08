"""Concord source plugin for BrainFlow (official ``BoardShim`` API). Read-only."""

from concord_brainflow.plugin import PLUGIN_VERSION, BrainFlowPlugin

__all__ = ["PLUGIN_VERSION", "BrainFlowPlugin"]
__version__ = PLUGIN_VERSION
