"""Concord source plugin for BCI2000's App Connector (ConnectorOutput) protocol. Receive-only."""

from concord_bci2000.plugin import PLUGIN_VERSION, BCI2000AppConnectorPlugin

__all__ = ["PLUGIN_VERSION", "BCI2000AppConnectorPlugin"]
__version__ = PLUGIN_VERSION
