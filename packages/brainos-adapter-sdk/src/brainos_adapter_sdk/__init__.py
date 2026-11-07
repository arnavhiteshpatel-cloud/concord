"""BrainOS adapter SDK: integrate a neural-data source without modifying BrainOS.

See ``brainos_adapter_sdk.api`` for the interface and docs/ADAPTER_SDK.md for the guide.
"""

from brainos_adapter_sdk.api import (
    API_VERSION,
    ENTRY_POINT_GROUP,
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
