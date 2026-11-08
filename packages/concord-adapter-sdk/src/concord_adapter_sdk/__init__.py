"""Concord adapter SDK: integrate a neural-data source without modifying Concord.

See ``concord_adapter_sdk.api`` for the interface, ``concord_adapter_sdk.validate`` for the
rules Concord checks, ``python -m concord_adapter_sdk.host --check <plugin>`` to try a
plugin exactly as Concord runs it, and docs/ADAPTER_SDK.md for the guide.
"""

from concord_adapter_sdk.api import (
    API_VERSION,
    ENTRY_POINT_GROUP,
    KEY_PATTERN,
    PRIMARY_ROLES,
    Channel,
    Chunk,
    ClockInfo,
    ConfigurationChanged,
    DeviceInfo,
    InvalidOptions,
    LinkLost,
    MarkerChunk,
    Modality,
    OpenFailed,
    OptionSpec,
    PluginError,
    PluginManifest,
    SessionInfo,
    SourcePlugin,
    SourceSession,
    StreamRole,
    StreamSpec,
)

__all__ = [
    "API_VERSION",
    "ENTRY_POINT_GROUP",
    "KEY_PATTERN",
    "PRIMARY_ROLES",
    "Channel",
    "Chunk",
    "ClockInfo",
    "ConfigurationChanged",
    "DeviceInfo",
    "InvalidOptions",
    "LinkLost",
    "MarkerChunk",
    "Modality",
    "OpenFailed",
    "OptionSpec",
    "PluginError",
    "PluginManifest",
    "SessionInfo",
    "SourcePlugin",
    "SourceSession",
    "StreamRole",
    "StreamSpec",
]
__version__ = "1.0.0"
