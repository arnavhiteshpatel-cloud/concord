"""Third-party source plugins (adapter SDK API 1.x), run out of process.

Concord never imports plugin code into the runtime process: discovery and every session
run in ``python -m concord_adapter_sdk.host`` subprocesses (see docs/ADAPTER_SDK.md).
"""

from concord.adapters.plugin.adapter import PluginAdapter, PluginSpec, PluginStopped, probe_plugin
from concord.adapters.plugin.mapping import PLUGIN_PREFIX, device_id

__all__ = [
    "PLUGIN_PREFIX",
    "PluginAdapter",
    "PluginSpec",
    "PluginStopped",
    "device_id",
    "probe_plugin",
]
