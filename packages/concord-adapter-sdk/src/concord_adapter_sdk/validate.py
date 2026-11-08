"""Validation of everything a plugin declares and emits (pure; no I/O, no Concord import).

Used by the plugin host (before anything leaves the plugin process), by the Concord runtime
(again, on receipt: the host runs third-party code and is not trusted) and by certification
tooling. Every check returns structured :class:`Problem` objects; nothing raises.

Severity:
  * ``error``   — a contract violation. A manifest with errors is rejected (the plugin
    cannot be used); a session with errors is not opened; a chunk with errors stops the
    session.
  * ``warning`` — allowed but worth fixing or worth telling the operator (e.g. sample loss).
  * ``info``    — facts recorded for the operator.

Rules are documented in docs/ADAPTER_SDK.md ("Validation rules"); the codes are stable.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import numpy as np

from concord_adapter_sdk.api import (
    API_VERSION,
    KEY_PATTERN,
    PRIMARY_ROLES,
    Channel,
    Chunk,
    ClockInfo,
    DeviceInfo,
    MarkerChunk,
    Modality,
    OptionSpec,
    PluginManifest,
    SessionInfo,
    StreamRole,
    StreamSpec,
)

Severity = Literal["error", "warning", "info"]

# Distribution names (PEP 508 / packaging "name"), versions (semantic versioning core plus
# optional pre-release / build), API versions ("major.minor").
NAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,62}[A-Za-z0-9])?$")
SEMVER_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$"
)
API_VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)$")
ECOSYSTEM_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.\-]{0,63}$")
# Entry-point names become part of Concord device ids: plugin:<entry point>:<device key>
ENTRY_POINT_NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_.\-]{0,23}$")
MODEL_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:\-]{0,63}$")
CLOCK_DOMAINS = frozenset({"source", "unix", "lsl", "sample_counter"})
OPTION_TYPES = frozenset({"str", "int", "float", "bool", "choice"})

NONINVASIVE = frozenset({Modality.EEG, Modality.MEG, Modality.EMG})
INVASIVE = frozenset({Modality.ECOG, Modality.SEEG, Modality.INTRACORTICAL})

# Limits that follow from the Concord event contract (schema 1.3).
MAX_STREAMS = 16
MAX_CHANNELS: dict[StreamRole, int] = {
    StreamRole.SIGNAL: 1024,  # recording.frame channel_count <= 1024
    StreamRole.SPIKE_COUNTS: 4096,  # features.binned channel_count <= 4096
    StreamRole.BEHAVIOR: 64,  # behavior.sample dims <= 64
    StreamRole.DECODER_OUTPUT: 64,  # intent.kinematics dims <= 64
    StreamRole.MARKERS: 1,
}
MAX_LABEL = {StreamRole.BEHAVIOR: 32, StreamRole.DECODER_OUTPUT: 32}  # dims: <= 32 chars
DEFAULT_MAX_LABEL = 64
MAX_SIGNAL_RATE_HZ = 100_000.0
MAX_BIN_MS = 10_000.0
IRREGULAR_OK = frozenset({StreamRole.MARKERS, StreamRole.BEHAVIOR, StreamRole.DECODER_OUTPUT})
NEURAL_ROLES = frozenset({StreamRole.SIGNAL, StreamRole.SPIKE_COUNTS})
MAX_CHUNK_SAMPLES = 1_000_000
MAX_CHUNK_BYTES = 64 * 1024 * 1024
MAX_MARKER_LABEL = 128
MAX_OPTIONS = 32
MAX_DEVICES = 64
MAX_TEXT = 500


@dataclass(frozen=True, slots=True)
class Problem:
    """One finding. ``code`` is stable and machine-readable; ``message`` is for people."""

    code: str
    message: str
    severity: Severity = "error"
    where: str = ""

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "severity": self.severity,
            "where": self.where,
        }

    @classmethod
    def from_dict(cls, d: Mapping[str, Any]) -> Problem:
        sev = d.get("severity", "error")
        return cls(
            code=str(d.get("code", "unknown")),
            message=str(d.get("message", "")),
            severity=sev if sev in ("error", "warning", "info") else "error",
            where=str(d.get("where", "")),
        )


def errors(problems: Iterable[Problem]) -> list[Problem]:
    return [p for p in problems if p.severity == "error"]


def has_errors(problems: Iterable[Problem]) -> bool:
    return any(p.severity == "error" for p in problems)


def summarize(problems: Iterable[Problem], limit: int = 3) -> str:
    """The first few errors as one operator-readable sentence."""
    errs = errors(problems)
    if not errs:
        return "no errors"
    head = "; ".join(f"{p.where + ': ' if p.where else ''}{p.message}" for p in errs[:limit])
    more = f" (+{len(errs) - limit} more)" if len(errs) > limit else ""
    return head + more


def _err(out: list[Problem], code: str, message: str, where: str = "") -> None:
    out.append(Problem(code, message, "error", where))


def _warn(out: list[Problem], code: str, message: str, where: str = "") -> None:
    out.append(Problem(code, message, "warning", where))


def _text(
    out: list[Problem], value: object, code: str, where: str, *, limit: int, required: bool
) -> None:
    if not isinstance(value, str):
        _err(out, code, f"must be a string, got {type(value).__name__}", where)
    elif required and not value.strip():
        _err(out, code, "must not be empty", where)
    elif len(value) > limit:
        _err(out, code, f"is {len(value)} characters long (max {limit})", where)


# ----------------------------------------------------------------------------- versions


def parse_api_version(v: str) -> tuple[int, int] | None:
    m = API_VERSION_PATTERN.match(v) if isinstance(v, str) else None
    return (int(m.group(1)), int(m.group(2))) if m else None


def api_compatible(plugin_api: str, host_api: str = API_VERSION) -> tuple[bool, str]:
    """A plugin written for API ``M.m`` runs on a host with API ``M.n`` where ``m <= n``."""
    p, h = parse_api_version(plugin_api), parse_api_version(host_api)
    if p is None:
        return False, f"api_version {plugin_api!r} is not 'major.minor'"
    if h is None:  # pragma: no cover - host constant
        return False, f"host API version {host_api!r} is malformed"
    if p[0] != h[0]:
        return False, (
            f"written for adapter SDK API {plugin_api}; this Concord supports API {host_api} "
            f"(major versions differ)"
        )
    if p[1] > h[1]:
        return False, (
            f"written for adapter SDK API {plugin_api}, newer than this Concord ({host_api}); "
            "update Concord"
        )
    return True, f"compatible with API {host_api}"


def version_core(version: str) -> str:
    """'1.2.3-rc.1+build' -> '1.2.3' (for Concord adapter names)."""
    m = SEMVER_PATTERN.match(version)
    return f"{m.group(1)}.{m.group(2)}.{m.group(3)}" if m else "0.0.0"


# ----------------------------------------------------------------------------- manifest


def _role(value: object) -> StreamRole | None:
    if isinstance(value, StreamRole):
        return value
    if isinstance(value, str) and value in StreamRole._value2member_map_:
        return StreamRole(value)
    return None


def validate_option_spec(name: object, spec: object) -> list[Problem]:
    out: list[Problem] = []
    where = f"options.{name}"
    if not isinstance(name, str) or not KEY_PATTERN.match(name):
        _err(out, "option.name", f"option name {name!r} must match {KEY_PATTERN.pattern}", where)
    if not isinstance(spec, OptionSpec):
        _err(out, "option.type", f"must be an OptionSpec, got {type(spec).__name__}", where)
        return out
    if spec.type not in OPTION_TYPES:
        _err(out, "option.type", f"type {spec.type!r} not in {sorted(OPTION_TYPES)}", where)
        return out
    _text(out, spec.description, "option.description", where, limit=MAX_TEXT, required=True)
    choices = spec.choices
    if spec.type == "choice":
        if not isinstance(choices, tuple) or not choices:
            _err(out, "option.choices", "a 'choice' option needs a non-empty choices tuple", where)
        elif not all(isinstance(c, str) and c for c in choices):
            _err(out, "option.choices", "choices must be non-empty strings", where)
        elif len(set(choices)) != len(choices):
            _err(out, "option.choices", "choices must be unique", where)
    elif choices:
        _err(
            out, "option.choices", f"choices are only valid for type 'choice' ({spec.type})", where
        )
    if spec.default is not None:
        ok, msg = _coerce(spec, spec.default)
        if ok is None:
            _err(out, "option.default", f"default {spec.default!r}: {msg}", where)
        if spec.required:
            _warn(out, "option.required_with_default", "a required option has a default", where)
    return out


def validate_manifest(manifest: object, host_api_version: str = API_VERSION) -> list[Problem]:
    """Check a plugin's manifest, including API-version compatibility with the host."""
    out: list[Problem] = []
    if not isinstance(manifest, PluginManifest):
        _err(out, "manifest.type", f"must be a PluginManifest, got {type(manifest).__name__}")
        return out
    m = manifest
    if not isinstance(m.name, str) or not NAME_PATTERN.match(m.name):
        _err(out, "manifest.name", f"{m.name!r} is not a valid distribution name", "name")
    if not isinstance(m.version, str) or not SEMVER_PATTERN.match(m.version):
        _err(
            out,
            "manifest.version",
            f"{m.version!r} is not a semantic version (e.g. '0.1.0')",
            "version",
        )
    if not isinstance(m.api_version, str) or parse_api_version(m.api_version) is None:
        _err(
            out,
            "manifest.api_version.format",
            f"{m.api_version!r} is not 'major.minor'",
            "api_version",
        )
    else:
        ok, msg = api_compatible(m.api_version, host_api_version)
        if not ok:
            _err(out, "manifest.api_version.incompatible", msg, "api_version")
    _text(out, m.display_name, "manifest.display_name", "display_name", limit=80, required=True)
    _text(out, m.description, "manifest.description", "description", limit=MAX_TEXT, required=True)
    _text(out, m.author, "manifest.author", "author", limit=128, required=True)
    _text(out, m.license, "manifest.license", "license", limit=64, required=True)
    _text(out, m.homepage, "manifest.homepage", "homepage", limit=256, required=False)
    if m.ecosystem is not None and (
        not isinstance(m.ecosystem, str) or not ECOSYSTEM_PATTERN.match(m.ecosystem)
    ):
        _err(
            out,
            "manifest.ecosystem",
            f"{m.ecosystem!r} must match {ECOSYSTEM_PATTERN.pattern}",
            "ecosystem",
        )
    if not isinstance(m.network, bool):
        _err(out, "manifest.network", "must be a bool", "network")
    roles = m.roles
    if not isinstance(roles, frozenset | set) or not roles:
        _err(out, "manifest.roles.empty", "must be a non-empty frozenset of StreamRole", "roles")
    else:
        parsed = {_role(r) for r in roles}
        unknown = sorted(str(r) for r in roles if _role(r) is None)
        if unknown:
            _err(
                out,
                "manifest.roles.unknown",
                f"unknown role(s) {unknown}; valid: {[r.value for r in StreamRole]}",
                "roles",
            )
        if not parsed & PRIMARY_ROLES:
            _err(
                out,
                "manifest.roles.no_primary",
                f"must include a primary role ({sorted(r.value for r in PRIMARY_ROLES)})",
                "roles",
            )
    if not isinstance(m.options, Mapping):
        _err(out, "manifest.options", "must be a mapping of name -> OptionSpec", "options")
    else:
        if len(m.options) > MAX_OPTIONS:
            _err(out, "manifest.options", f"at most {MAX_OPTIONS} options", "options")
        for name, spec in m.options.items():
            out.extend(validate_option_spec(name, spec))
    return out


def validate_entry_point_name(name: str) -> list[Problem]:
    if ENTRY_POINT_NAME_PATTERN.match(name):
        return []
    return [
        Problem(
            "entry_point.name",
            f"entry-point name {name!r} must match {ENTRY_POINT_NAME_PATTERN.pattern} "
            "(lower case, at most 24 characters; it becomes part of Concord device ids)",
            "error",
            "entry point",
        )
    ]


# ----------------------------------------------------------------------------- options


def _coerce(spec: OptionSpec, value: object) -> tuple[object | None, str]:
    """Return (coerced value, '') or (None, reason). Strings from forms are accepted."""
    t = spec.type
    if t == "bool":
        if isinstance(value, bool):
            return value, ""
        if isinstance(value, str) and value.strip().lower() in {"true", "false", "1", "0"}:
            return value.strip().lower() in {"true", "1"}, ""
        return None, "expected a boolean"
    if t == "int":
        if isinstance(value, bool):
            return None, "expected an integer"
        if isinstance(value, int):
            return value, ""
        if isinstance(value, float) and value.is_integer():
            return int(value), ""
        if isinstance(value, str):
            try:
                return int(value.strip()), ""
            except ValueError:
                pass
        return None, "expected an integer"
    if t == "float":
        if isinstance(value, bool):
            return None, "expected a number"
        v: float | None = None
        if isinstance(value, int | float):
            v = float(value)
        elif isinstance(value, str):
            try:
                v = float(value.strip())
            except ValueError:
                v = None
        if v is None or not math.isfinite(v):
            return None, "expected a finite number"
        return v, ""
    if t == "str":
        if isinstance(value, str) and len(value) <= 512:
            return value, ""
        return None, "expected a string (max 512 characters)"
    if t == "choice":
        if isinstance(value, str) and value in spec.choices:
            return value, ""
        return None, f"expected one of {list(spec.choices)}"
    return None, f"unknown option type {t!r}"


def validate_options(
    specs: Mapping[str, OptionSpec], values: Mapping[str, object]
) -> tuple[dict[str, object], list[Problem]]:
    """Validate operator-supplied options against the manifest; apply defaults.

    Returns the options to pass to ``open()`` (defaults filled in, values coerced from form
    strings) and the problems. Unknown names are errors (never silently ignored).
    """
    out: list[Problem] = []
    resolved: dict[str, object] = {}
    if not isinstance(values, Mapping):
        _err(out, "options.type", "options must be an object of name -> value")
        return resolved, out
    for name in values:
        if name not in specs:
            _err(
                out,
                "options.unknown",
                f"unknown option {name!r} (known: {sorted(specs)})",
                f"options.{name}",
            )
    for name, spec in specs.items():
        if name in values and values[name] is not None:
            v, reason = _coerce(spec, values[name])
            if v is None:
                _err(out, "options.invalid", f"{values[name]!r}: {reason}", f"options.{name}")
            else:
                resolved[name] = v
        elif spec.required:
            _err(out, "options.missing", "required option not given", f"options.{name}")
        elif spec.default is not None:
            resolved[name] = spec.default
    return resolved, out


# ----------------------------------------------------------------------------- devices


def validate_devices(devices: object) -> list[Problem]:
    out: list[Problem] = []
    if not isinstance(devices, Sequence) or isinstance(devices, str | bytes):
        _err(out, "devices.type", "discover() must return a sequence of DeviceInfo")
        return out
    if len(devices) > MAX_DEVICES:
        _err(
            out, "devices.count", f"discover() returned {len(devices)} devices (max {MAX_DEVICES})"
        )
    seen: set[str] = set()
    for i, d in enumerate(devices):
        where = f"devices[{i}]"
        if not isinstance(d, DeviceInfo):
            _err(out, "device.type", f"must be a DeviceInfo, got {type(d).__name__}", where)
            continue
        if not isinstance(d.device_key, str) or not KEY_PATTERN.match(d.device_key):
            _err(
                out,
                "device.key",
                f"device_key {d.device_key!r} must match {KEY_PATTERN.pattern}",
                where,
            )
        elif d.device_key in seen:
            _err(out, "device.key.duplicate", f"duplicate device_key {d.device_key!r}", where)
        else:
            seen.add(d.device_key)
        _text(out, d.display_name, "device.display_name", where, limit=80, required=True)
        _text(out, d.description, "device.description", where, limit=MAX_TEXT, required=False)
        if not isinstance(d.details, Mapping) or not all(
            isinstance(k, str) and isinstance(v, str) and len(k) <= 64 and len(v) <= 256
            for k, v in d.details.items()
        ):
            _err(out, "device.details", "details must map short strings to strings", where)
    return out


# ----------------------------------------------------------------------------- session


def _validate_stream(s: StreamSpec, manifest_roles: frozenset[StreamRole]) -> list[Problem]:
    out: list[Problem] = []
    where = f"streams[{s.stream_id!r}]" if isinstance(s.stream_id, str) else "streams[?]"
    if not isinstance(s.stream_id, str) or not KEY_PATTERN.match(s.stream_id):
        _err(out, "stream.id", f"stream_id {s.stream_id!r} must match {KEY_PATTERN.pattern}", where)
    role = _role(s.role)
    if role is None:
        _err(out, "stream.role.unknown", f"unknown role {s.role!r}", where)
        return out
    if role not in manifest_roles:
        _err(
            out,
            "stream.role.undeclared",
            f"role {role.value!r} is not declared in the manifest's roles "
            f"({sorted(r.value for r in manifest_roles)})",
            where,
        )
    # channels
    chans = s.channels
    if not isinstance(chans, tuple | list) or not chans:
        _err(out, "stream.channels.empty", "a stream needs at least one channel", where)
    else:
        limit = MAX_CHANNELS[role]
        if len(chans) > limit:
            _err(
                out,
                "stream.channels.count",
                f"{len(chans)} channels; at most {limit} for role {role.value!r}",
                where,
            )
        labels: list[str] = []
        max_label = MAX_LABEL.get(role, DEFAULT_MAX_LABEL)
        for i, c in enumerate(chans):
            cw = f"{where}.channels[{i}]"
            if not isinstance(c, Channel):
                _err(out, "channel.type", f"must be a Channel, got {type(c).__name__}", cw)
                continue
            if not isinstance(c.label, str) or not c.label.strip():
                _err(out, "channel.label.empty", "channel label must be a non-empty string", cw)
                continue
            if len(c.label) > max_label:
                _err(out, "channel.label.length", f"label longer than {max_label} chars", cw)
            labels.append(c.label)
            for attr in ("unit", "type"):
                v = getattr(c, attr)
                if v is not None and (not isinstance(v, str) or not v.strip() or len(v) > 32):
                    _err(out, f"channel.{attr}", f"{attr} must be None or a short string", cw)
        dupes = sorted({x for x in labels if labels.count(x) > 1})
        if dupes:
            _err(out, "stream.channels.duplicate", f"duplicate channel labels {dupes}", where)
    # rate
    rate = s.nominal_rate_hz
    if isinstance(rate, bool) or not isinstance(rate, int | float) or not math.isfinite(rate):
        _err(out, "stream.rate", f"nominal_rate_hz {rate!r} must be a finite number", where)
    elif rate < 0:
        _err(out, "stream.rate", f"nominal_rate_hz {rate} must be >= 0", where)
    elif rate == 0 and role not in IRREGULAR_OK:
        _err(
            out,
            "stream.rate.irregular",
            f"an irregular rate (0) is only allowed for "
            f"{sorted(r.value for r in IRREGULAR_OK)}, not {role.value!r}",
            where,
        )
    elif role is StreamRole.SIGNAL and rate > MAX_SIGNAL_RATE_HZ:
        _err(out, "stream.rate", f"{rate} Hz exceeds {MAX_SIGNAL_RATE_HZ:g} Hz", where)
    # clock
    if not isinstance(s.clock, ClockInfo) or s.clock.domain not in CLOCK_DOMAINS:
        _err(
            out,
            "stream.clock",
            f"clock must be a ClockInfo with domain in {sorted(CLOCK_DOMAINS)}",
            where,
        )
    # modality / invasive
    if s.modality is not None:
        mod = s.modality if isinstance(s.modality, Modality) else None
        if (
            mod is None
            and isinstance(s.modality, str)
            and s.modality in Modality._value2member_map_
        ):
            mod = Modality(s.modality)
        if mod is None:
            _err(out, "stream.modality", f"unknown modality {s.modality!r}", where)
        elif role not in NEURAL_ROLES:
            _err(
                out,
                "stream.modality.not_applicable",
                f"modality is only valid for signal / spike_counts streams, not {role.value!r}",
                where,
            )
        elif s.invasive is not None:
            if mod in NONINVASIVE and s.invasive:
                _err(
                    out,
                    "stream.invasive.inconsistent",
                    f"{mod.value} is noninvasive but invasive=True",
                    where,
                )
            if mod in INVASIVE and not s.invasive:
                _err(
                    out,
                    "stream.invasive.inconsistent",
                    f"{mod.value} is implanted but invasive=False",
                    where,
                )
    if s.invasive is not None:
        if not isinstance(s.invasive, bool):
            _err(out, "stream.invasive", "invasive must be None or a bool", where)
        elif role not in NEURAL_ROLES:
            _err(
                out,
                "stream.invasive.not_applicable",
                f"invasive is only valid for signal / spike_counts streams, not {role.value!r}",
                where,
            )
    # role-specific fields
    if role is StreamRole.SPIKE_COUNTS:
        b = s.bin_ms
        if b is None or isinstance(b, bool) or not isinstance(b, int | float):
            _err(out, "stream.bin_ms.missing", "spike_counts streams require bin_ms", where)
        elif not math.isfinite(b) or not 0 < b <= MAX_BIN_MS:
            _err(out, "stream.bin_ms", f"bin_ms {b} must be in (0, {MAX_BIN_MS:g}]", where)
        elif isinstance(rate, int | float) and rate > 0 and abs(1000.0 / rate - b) > 0.01 * b:
            _warn(
                out,
                "stream.bin_ms.rate_mismatch",
                f"bin_ms {b} does not match 1000 / nominal_rate_hz ({1000.0 / rate:.4g} ms)",
                where,
            )
    elif s.bin_ms is not None:
        _err(out, "stream.bin_ms.not_applicable", "bin_ms is only valid for spike_counts", where)
    if role is StreamRole.DECODER_OUTPUT:
        if not isinstance(s.model_id, str) or not MODEL_ID_PATTERN.match(s.model_id):
            _err(
                out,
                "stream.model_id.missing",
                f"decoder_output streams require model_id matching {MODEL_ID_PATTERN.pattern}",
                where,
            )
    elif s.model_id is not None:
        _err(
            out,
            "stream.model_id.not_applicable",
            "model_id is only valid for decoder_output",
            where,
        )
    if role in (StreamRole.BEHAVIOR, StreamRole.DECODER_OUTPUT):
        if s.quantity is not None:
            _text(out, s.quantity, "stream.quantity", where, limit=64, required=True)
    elif s.quantity is not None:
        _err(
            out,
            "stream.quantity.not_applicable",
            "quantity is only valid for behavior / decoder_output",
            where,
        )
    return out


def validate_session_info(info: object, manifest: PluginManifest) -> list[Problem]:
    """Check what an open session declares, against the plugin's manifest.

    Concord rule on clocks: every stream must use the primary stream's clock domain. Streams
    on different clocks cannot be aligned without a measured offset, which the API does not
    carry, so mixing them is rejected rather than silently merged.
    """
    out: list[Problem] = []
    if not isinstance(info, SessionInfo):
        _err(out, "session.type", f"info must be a SessionInfo, got {type(info).__name__}")
        return out
    roles = frozenset(r for r in (_role(x) for x in manifest.roles) if r is not None)
    streams = info.streams
    if not isinstance(streams, tuple | list) or not streams:
        _err(out, "session.streams.empty", "a session must declare at least one stream")
        return out
    if len(streams) > MAX_STREAMS:
        _err(out, "session.streams.count", f"{len(streams)} streams (max {MAX_STREAMS})")
    ids: list[str] = []
    for s in streams:
        if not isinstance(s, StreamSpec):
            _err(out, "stream.type", f"must be a StreamSpec, got {type(s).__name__}")
            continue
        out.extend(_validate_stream(s, roles))
        ids.append(s.stream_id)
    dupes = sorted({x for x in ids if ids.count(x) > 1})
    if dupes:
        _err(out, "session.streams.duplicate", f"duplicate stream ids {dupes}")
    by_id = {s.stream_id: s for s in streams if isinstance(s, StreamSpec)}
    primary = by_id.get(info.primary_stream) if isinstance(info.primary_stream, str) else None
    if primary is None:
        _err(
            out,
            "session.primary.missing",
            f"primary_stream {info.primary_stream!r} is not one of the streams {sorted(by_id)}",
        )
    elif _role(primary.role) not in PRIMARY_ROLES:
        _err(
            out,
            "session.primary.role",
            f"primary stream {primary.stream_id!r} has role {primary.role!r}; the primary "
            f"must be one of {sorted(r.value for r in PRIMARY_ROLES)}",
        )
    elif isinstance(primary.clock, ClockInfo):
        for s in by_id.values():
            if isinstance(s.clock, ClockInfo) and s.clock.domain != primary.clock.domain:
                _err(
                    out,
                    "session.clock.mixed",
                    f"stream {s.stream_id!r} uses clock domain {s.clock.domain!r} but the "
                    f"primary stream uses {primary.clock.domain!r}; all streams must share the "
                    "primary's clock domain (convert timestamps in the plugin)",
                    f"streams[{s.stream_id!r}]",
                )
    for attr in ("synthetic", "prerecorded"):
        if not isinstance(getattr(info, attr), bool):
            _err(out, f"session.{attr}", f"{attr} must be a bool")
    if info.synthetic is True and info.prerecorded is True:
        out.append(
            Problem(
                "session.synthetic_and_prerecorded",
                "both synthetic and prerecorded are set; Concord treats the source as synthetic",
                "warning",
            )
        )
    _text(out, info.origin, "session.origin", "origin", limit=128, required=True)
    return out


# ----------------------------------------------------------------------------- chunks


@dataclass
class _StreamState:
    next_index: int = 0
    last_ts: float | None = None


@dataclass
class ChunkValidator:
    """Stateful per-session chunk checks (timestamps and sample indices across calls).

    State only advances for chunks without errors, so the caller can stop the session at
    the first error and report exactly what was wrong.
    """

    info: SessionInfo
    _streams: dict[str, StreamSpec] = field(init=False)
    _state: dict[str, _StreamState] = field(init=False)

    def __post_init__(self) -> None:
        self._streams = {s.stream_id: s for s in self.info.streams}
        self._state = {sid: _StreamState() for sid in self._streams}

    def next_index(self, stream_id: str) -> int:
        return self._state[stream_id].next_index

    def check(self, chunk: object) -> list[Problem]:
        out: list[Problem] = []
        if isinstance(chunk, Chunk):
            self._numeric(chunk, out)
        elif isinstance(chunk, MarkerChunk):
            self._markers(chunk, out)
        else:
            _err(
                out,
                "chunk.type",
                f"read() must return Chunk or MarkerChunk items, got {type(chunk).__name__}",
            )
        return out

    def check_all(self, items: object) -> list[Problem]:
        if not isinstance(items, Sequence) or isinstance(items, str | bytes):
            return [
                Problem(
                    "read.type",
                    f"read() must return a sequence, got {type(items).__name__}",
                )
            ]
        out: list[Problem] = []
        for item in items:
            found = self.check(item)
            out.extend(found)
            if has_errors(found):
                break
        return out

    def _stream(self, stream_id: object, out: list[Problem]) -> StreamSpec | None:
        spec = self._streams.get(stream_id) if isinstance(stream_id, str) else None
        if spec is None:
            _err(
                out,
                "chunk.stream.unknown",
                f"chunk for stream {stream_id!r}, which the session did not declare "
                f"(declared: {sorted(self._streams)})",
            )
        return spec

    def _timestamps(
        self, ts: object, n: int, state: _StreamState, where: str, out: list[Problem]
    ) -> np.ndarray[Any, np.dtype[np.float64]] | None:
        if not isinstance(ts, np.ndarray) or ts.ndim != 1:
            _err(out, "chunk.timestamps.type", "timestamps must be a 1-D numpy array", where)
            return None
        if ts.dtype.kind not in "fiu":
            _err(out, "chunk.timestamps.type", f"timestamps dtype {ts.dtype} is not numeric", where)
            return None
        if ts.shape[0] != n:
            _err(
                out,
                "chunk.timestamps.length",
                f"{ts.shape[0]} timestamps for {n} samples",
                where,
            )
            return None
        t = ts.astype(np.float64, copy=False)
        if n == 0:
            return t
        if not bool(np.all(np.isfinite(t))):
            _err(out, "chunk.timestamps.finite", "timestamps contain NaN or infinity", where)
            return None
        if float(t.min()) < 0:
            _err(out, "chunk.timestamps.negative", "timestamps must be >= 0 seconds", where)
            return None
        if n > 1 and bool(np.any(np.diff(t) < 0)):
            k = int(np.argmax(np.diff(t) < 0))
            _err(
                out,
                "chunk.timestamps.decreasing",
                f"timestamps decrease within the chunk ({t[k]!r} -> {t[k + 1]!r})",
                where,
            )
            return None
        if state.last_ts is not None and float(t[0]) < state.last_ts:
            _err(
                out,
                "chunk.timestamps.decreasing",
                f"first timestamp {float(t[0])!r} is before the previous chunk's last "
                f"timestamp {state.last_ts!r}",
                where,
            )
            return None
        return t

    def _numeric(self, c: Chunk, out: list[Problem]) -> None:
        spec = self._stream(c.stream_id, out)
        if spec is None:
            return
        where = f"chunk[{spec.stream_id!r}]"
        if _role(spec.role) is StreamRole.MARKERS:
            _err(out, "chunk.kind_mismatch", "markers streams take MarkerChunk, not Chunk", where)
            return
        d = c.data
        if not isinstance(d, np.ndarray):
            _err(
                out, "chunk.data.type", f"data must be a numpy array, got {type(d).__name__}", where
            )
            return
        if d.dtype.kind not in "fiu" or d.dtype.itemsize > 8:
            _err(out, "chunk.data.dtype", f"dtype {d.dtype} is not a real numeric type", where)
            return
        if d.ndim != 2:
            _err(
                out,
                "chunk.data.shape",
                f"data must be 2-D (n_samples, n_channels), got shape {d.shape}",
                where,
            )
            return
        n, ch = d.shape
        if ch != len(spec.channels):
            _err(
                out,
                "chunk.data.channels",
                f"data has {ch} channels; stream declares {len(spec.channels)}",
                where,
            )
            return
        if n > MAX_CHUNK_SAMPLES or d.nbytes > MAX_CHUNK_BYTES:
            _err(
                out,
                "chunk.too_large",
                f"{n} samples / {d.nbytes} bytes in one chunk (max {MAX_CHUNK_SAMPLES} samples, "
                f"{MAX_CHUNK_BYTES} bytes); return smaller chunks",
                where,
            )
            return
        state = self._state[spec.stream_id]
        idx = c.first_index
        if isinstance(idx, bool) or not isinstance(idx, int | np.integer) or idx < 0:
            _err(out, "chunk.index", f"first_index {idx!r} must be an int >= 0", where)
            return
        idx = int(idx)
        t = self._timestamps(c.timestamps, n, state, where, out)
        if t is None:
            return
        if n == 0:
            _warn(out, "chunk.empty", "empty chunk ignored (return no chunk instead)", where)
            return
        if d.dtype.kind == "f" and not bool(np.all(np.isfinite(d))):
            _err(out, "chunk.data.finite", "data contains NaN or infinity", where)
            return
        if _role(spec.role) is StreamRole.SPIKE_COUNTS:
            if d.dtype.kind == "f":
                bad = bool(np.any(d < 0) or np.any(d != np.floor(d)))
            else:
                bad = bool(np.any(d < 0))
            if bad:
                _err(
                    out,
                    "chunk.counts.invalid",
                    "spike_counts values must be non-negative integers",
                    where,
                )
                return
        if idx < state.next_index:
            _err(
                out,
                "chunk.index.overlap",
                f"first_index {idx} overlaps samples already delivered "
                f"(next expected index {state.next_index})",
                where,
            )
            return
        if idx > state.next_index:
            _warn(
                out,
                "chunk.index.gap",
                f"{idx - state.next_index} sample(s) lost before index {idx}",
                where,
            )
        state.next_index = idx + n
        state.last_ts = float(t[-1])

    def _markers(self, c: MarkerChunk, out: list[Problem]) -> None:
        spec = self._stream(c.stream_id, out)
        if spec is None:
            return
        where = f"chunk[{spec.stream_id!r}]"
        if _role(spec.role) is not StreamRole.MARKERS:
            _err(
                out,
                "chunk.kind_mismatch",
                f"MarkerChunk sent to a {spec.role!r} stream; use Chunk",
                where,
            )
            return
        labels = c.labels
        if not isinstance(labels, tuple | list):
            _err(out, "chunk.labels.type", "labels must be a tuple of strings", where)
            return
        for lab in labels:
            if not isinstance(lab, str) or not lab.strip():
                _err(
                    out, "chunk.labels.empty", f"marker label {lab!r} must be non-empty text", where
                )
                return
            if len(lab) > MAX_MARKER_LABEL:
                _err(
                    out,
                    "chunk.labels.length",
                    f"marker label longer than {MAX_MARKER_LABEL} characters",
                    where,
                )
                return
        state = self._state[spec.stream_id]
        t = self._timestamps(c.timestamps, len(labels), state, where, out)
        if t is None:
            return
        if len(labels) == 0:
            _warn(out, "chunk.empty", "empty marker chunk ignored", where)
            return
        state.next_index += len(labels)
        state.last_ts = float(t[-1])
