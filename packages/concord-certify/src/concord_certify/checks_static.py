"""Checks on what the plugin declares: manifest, identity, session metadata."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from concord_adapter_sdk import API_VERSION, PluginManifest, SessionInfo, StreamRole, ipc
from concord_adapter_sdk import __version__ as SDK_VERSION
from concord_adapter_sdk import validate as v

from concord_certify.model import Results

# Exact-factor voltage units Concord converts to µV (concord/adapters/lsl/metadata.py
# UNIT_TO_UV, used for plugin SIGNAL streams too). Anything else is shown as "arbitrary".
VOLTAGE_UNITS = frozenset(
    {
        "microvolts",
        "microvolt",
        "uv",
        "µv",
        "μv",
        "millivolts",
        "millivolt",
        "mv",
        "volts",
        "volt",
        "v",
        "nanovolts",
        "nanovolt",
        "nv",
    }
)
NEURAL_ROLES = (StreamRole.SIGNAL, StreamRole.SPIKE_COUNTS)


def problems_evidence(problems: list[v.Problem]) -> list[dict[str, str]]:
    return [p.to_dict() for p in problems[:30]]


def manifest_summary(m: PluginManifest) -> dict[str, Any]:
    return {
        "name": m.name,
        "version": m.version,
        "api_version": m.api_version,
        "display_name": m.display_name,
        "author": m.author,
        "license": m.license,
        "homepage": m.homepage,
        "ecosystem": m.ecosystem,
        "network": m.network,
        "roles": sorted(str(r) for r in m.roles),
        "options": {k: {"type": o.type, "required": o.required} for k, o in m.options.items()},
    }


def stream_summary(info: SessionInfo) -> list[dict[str, Any]]:
    out = []
    for s in info.streams:
        out.append(
            {
                "stream_id": s.stream_id,
                "role": str(s.role),
                "channels": len(s.channels),
                "nominal_rate_hz": s.nominal_rate_hz,
                "clock": s.clock.domain,
                "clock_description": s.clock.description,
                "modality": str(s.modality) if s.modality is not None else None,
                "invasive": s.invasive,
                "units": sorted({str(c.unit) for c in s.channels}),
                "bin_ms": s.bin_ms,
                "quantity": s.quantity,
                "model_id": s.model_id,
            }
        )
    return out


def check_manifest(
    results: Results,
    manifest_reply: Mapping[str, Any],
    hello: Mapping[str, Any],
) -> PluginManifest | None:
    """``manifest.valid`` and ``manifest.api_compat`` from the host's answer + local
    re-validation. Returns the parsed manifest (None if unusable)."""
    host_problems = [v.Problem.from_dict(p) for p in manifest_reply.get("problems") or []]
    try:
        manifest = ipc.manifest_from_dict(manifest_reply.get("manifest") or {})
    except ipc.WireError as exc:
        results.set(
            "manifest.valid",
            "fail",
            f"manifest malformed on the wire: {exc}",
            {"host_problems": problems_evidence(host_problems)},
        )
        results.set("manifest.api_compat", "not_run", "no usable manifest")
        return None
    local = v.validate_manifest(manifest)
    api_codes = ("manifest.api_version.incompatible",)
    seen: set[tuple[str, str]] = set()
    merged: list[v.Problem] = []
    for p in [*host_problems, *local]:
        if (p.code, p.where) not in seen and not p.code.startswith("entry_point"):
            seen.add((p.code, p.where))
            merged.append(p)
    other = [p for p in merged if p.code not in api_codes]
    ev = {
        "manifest": manifest_summary(manifest),
        "problems": problems_evidence(merged),
        "host_says_compatible": bool(manifest_reply.get("compatible")),
    }
    if v.has_errors(other):
        results.set("manifest.valid", "fail", v.summarize(other), ev)
    elif other:
        w = other[0]
        results.set("manifest.valid", "warn", f"{len(other)} warning(s): {w.code}: {w.message}", ev)
    else:
        results.set("manifest.valid", "pass", "manifest valid (host and local validation)", ev)

    host_api = str(hello.get("api_version") or API_VERSION)
    ok, msg = v.api_compatible(manifest.api_version, host_api)
    ok_local, _ = v.api_compatible(manifest.api_version, API_VERSION)
    ev_api = {
        "plugin_api_version": manifest.api_version,
        "host_api_version": host_api,
        "host_sdk_version": hello.get("sdk_version"),
        "certify_sdk_api_version": API_VERSION,
        "certify_sdk_version": SDK_VERSION,
    }
    if not ok or not ok_local:
        results.set(
            "manifest.api_compat",
            "fail",
            msg if not ok else f"incompatible with the certifier's SDK API {API_VERSION}",
            ev_api,
        )
    elif hello.get("sdk_version") != SDK_VERSION:
        results.set(
            "manifest.api_compat",
            "warn",
            f"API {manifest.api_version} compatible, but the host's SDK "
            f"{hello.get('sdk_version')} differs from the certifier's {SDK_VERSION}",
            ev_api,
        )
    else:
        results.set(
            "manifest.api_compat",
            "pass",
            f"plugin API {manifest.api_version} runs on SDK API {host_api} (SDK {SDK_VERSION})",
            ev_api,
        )
    return manifest


def check_entry_point(results: Results, identity: Mapping[str, Any], ref: str) -> str | None:
    """Returns the entry-point name when the plugin was referenced by one."""
    if identity.get("error"):
        results.set("manifest.entry_point", "warn", str(identity["error"]), {"ref": ref})
        return None if ":" in ref else ref
    ep = identity.get("entry_point")
    if identity.get("kind") == "module" or ep is None:
        results.set(
            "manifest.entry_point",
            "warn",
            "referenced as module:Class, so the 'concord.sources' entry point was not "
            "verified (Concord discovers plugins only through it)",
            {"ref": ref},
        )
        return None
    ev = {"entry_point": ep}
    if ep.get("count", 0) == 0:
        results.set("manifest.entry_point", "fail", f"no 'concord.sources' entry point {ref!r}", ev)
    elif ep.get("count", 0) > 1:
        results.set(
            "manifest.entry_point",
            "fail",
            f"entry point {ref!r} is provided by several distributions: {ep.get('providers')}",
            ev,
        )
    elif v.validate_entry_point_name(ref):
        results.set("manifest.entry_point", "fail", v.validate_entry_point_name(ref)[0].message, ev)
    else:
        results.set(
            "manifest.entry_point",
            "pass",
            f"entry point {ref} = {ep.get('value')} ({', '.join(ep.get('providers') or [])})",
            ev,
        )
    return ref


def identity_summary(identity: Mapping[str, Any]) -> dict[str, Any]:
    dist = identity.get("distribution") or {}
    mod = identity.get("module") or {}
    return {
        "distribution": {k: dist.get(k) for k in ("name", "version", "editable", "direct_url")}
        if dist
        else None,
        "record": dist.get("record"),
        "module": {k: mod.get(k) for k in ("name", "path", "file_count", "tree_sha256")}
        if mod
        else None,
        "git": identity.get("git"),
    }


def check_distribution(
    results: Results, identity: Mapping[str, Any], manifest: PluginManifest | None
) -> None:
    ev = identity_summary(identity)
    if identity.get("error"):
        results.set("manifest.distribution", "warn", str(identity["error"]), ev)
        return
    dist = identity.get("distribution")
    mod = identity.get("module") or {}
    if not dist:
        results.set(
            "manifest.distribution",
            "warn",
            "not an installed distribution; identified by module file hashes only "
            f"(tree sha256 {str(mod.get('tree_sha256'))[:12]}…)",
            ev,
        )
        return
    warns: list[str] = []
    if manifest is not None:
        if _norm(manifest.name) != _norm(str(dist.get("name"))):
            warns.append(f"manifest name {manifest.name!r} != distribution {dist.get('name')!r}")
        if manifest.version != dist.get("version"):
            warns.append(
                f"manifest version {manifest.version!r} != distribution {dist.get('version')!r}"
            )
    rec = dist.get("record") or {}
    if not rec:
        warns.append("distribution has no RECORD file")
    else:
        if rec.get("mismatched"):
            warns.append(f"{len(rec['mismatched'])} installed file(s) differ from RECORD")
        if rec.get("missing"):
            warns.append(f"{len(rec['missing'])} RECORD file(s) missing")
    edit = (
        " (editable install: RECORD covers the .pth only; source files hashed)"
        if dist.get("editable")
        else ""
    )
    if warns:
        results.set("manifest.distribution", "warn", "; ".join(warns), ev)
    else:
        results.set(
            "manifest.distribution",
            "pass",
            f"{dist.get('name')} {dist.get('version')}: {rec.get('verified')} of "
            f"{int(rec.get('files') or 0) - int(rec.get('unhashed') or 0)} hashed RECORD entries "
            f"verified; module tree sha256 {str(mod.get('tree_sha256'))[:12]}…" + edit,
            ev,
        )


def _norm(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


# ----------------------------------------------------------------------------- session


def check_session_metadata(
    results: Results,
    opened: Mapping[str, Any],
    manifest: PluginManifest,
    *,
    redacted_options: Mapping[str, Any],
    open_s: float,
) -> SessionInfo | None:
    """``metadata.session_valid``, ``metadata.units``, ``metadata.modality``."""
    host_problems = [v.Problem.from_dict(p) for p in opened.get("problems") or []]
    try:
        info = ipc.session_info_from_dict(opened.get("info") or {})
    except ipc.WireError as exc:
        results.set("metadata.session_valid", "fail", f"session info malformed: {exc}")
        return None
    local = v.validate_session_info(info, manifest)
    seen: set[tuple[str, str]] = set()
    merged = []
    for p in [*host_problems, *local]:
        if (p.code, p.where) not in seen:
            seen.add((p.code, p.where))
            merged.append(p)
    ev = {
        "open_s": round(open_s, 3),
        "primary_stream": info.primary_stream,
        "synthetic": info.synthetic,
        "prerecorded": info.prerecorded,
        "origin": info.origin,
        "streams": stream_summary(info),
        "options_resolved": dict(redacted_options),
        "problems": problems_evidence(merged),
    }
    if v.has_errors(merged):
        results.set("metadata.session_valid", "fail", v.summarize(merged), ev)
        return None
    if merged:
        results.set("metadata.session_valid", "warn", f"{merged[0].code}: {merged[0].message}", ev)
    else:
        results.set(
            "metadata.session_valid",
            "pass",
            f"{len(info.streams)} stream(s), primary {info.primary_stream!r}, "
            f"synthetic={info.synthetic} prerecorded={info.prerecorded}, opened in {open_s:.2f} s",
            ev,
        )
    check_units(results, info)
    check_modality(results, info)
    return info


def check_units(results: Results, info: SessionInfo) -> None:
    per: dict[str, Any] = {}
    unknown_total = 0
    notes: list[str] = []
    channels_total = 0
    for s in info.streams:
        if StreamRole(s.role) is StreamRole.MARKERS:
            continue
        units = [c.unit for c in s.channels]
        unknown = sum(1 for u in units if u is None)
        channels_total += len(units)
        unknown_total += unknown
        rec: dict[str, Any] = {
            "role": str(s.role),
            "channels": len(units),
            "unknown": unknown,
            "declared": sorted({u for u in units if u is not None}),
        }
        if StreamRole(s.role) is StreamRole.SIGNAL:
            nonvolt = sorted(
                {u for u in units if u is not None and u.strip().lower() not in VOLTAGE_UNITS}
            )
            scaled = not unknown and not nonvolt
            rec["concord_unit"] = "uV" if scaled else "arbitrary"
            if nonvolt:
                notes.append(f"{s.stream_id}: {nonvolt} not a voltage unit Concord converts")
        per[s.stream_id] = rec
    ev = {"streams": per, "unknown_channels": unknown_total, "notes": notes}
    if unknown_total:
        results.set(
            "metadata.units",
            "warn",
            f"{unknown_total} of {channels_total} channel(s) declare no unit (shown as "
            "'arbitrary'; correct when the source does not state units)",
            ev,
        )
    elif notes:
        results.set("metadata.units", "warn", notes[0], ev)
    else:
        results.set("metadata.units", "pass", f"all {channels_total} channel(s) declare a unit", ev)


def check_modality(results: Results, info: SessionInfo) -> None:
    neural = [s for s in info.streams if StreamRole(s.role) in NEURAL_ROLES]
    ev: dict[str, Any] = {
        s.stream_id: {
            "role": str(s.role),
            "modality": str(s.modality) if s.modality is not None else None,
            "invasive": s.invasive,
        }
        for s in neural
    }
    # The host refuses inconsistent declarations (stream.invasive.inconsistent); re-checked
    # here because the certifier does not trust the host.
    bad = [
        f"{s.stream_id}: {s.modality} with invasive={s.invasive}"
        for s in neural
        if s.modality is not None
        and s.invasive is not None
        and ((str(s.modality) in v.INVASIVE) != s.invasive)
        and str(s.modality) in (v.INVASIVE | v.NONINVASIVE)
    ]
    if bad:
        results.set("metadata.modality", "fail", f"inconsistent declaration: {bad[0]}", ev)
        return
    if not neural:
        results.set(
            "metadata.modality",
            "pass",
            "no signal / spike-count stream: modality not applicable (Concord shows "
            "'modality not declared')",
            ev,
        )
        return
    undeclared = [s.stream_id for s in neural if s.modality is None]
    no_inv = [s.stream_id for s in neural if s.invasive is None and s.modality is None]
    if undeclared:
        results.set(
            "metadata.modality",
            "warn",
            f"modality not declared for {undeclared}"
            + (f"; invasiveness unknown for {no_inv}" if no_inv else "")
            + " (shown as 'not declared'; correct when the source cannot tell)",
            ev,
        )
    else:
        desc = ", ".join(f"{s.stream_id}={s.modality}/invasive={s.invasive}" for s in neural)
        results.set("metadata.modality", "pass", f"declared and consistent: {desc}", ev)


# ----------------------------------------------------------------------------- identity


def session_identity(info: SessionInfo) -> dict[str, Any]:
    """Everything that must be identical across opens of the same device + options."""
    return {
        "primary_stream": info.primary_stream,
        "synthetic": info.synthetic,
        "prerecorded": info.prerecorded,
        "origin": info.origin,
        "streams": [
            {
                "stream_id": s.stream_id,
                "role": str(s.role),
                "labels": [c.label for c in s.channels],
                "units": [c.unit for c in s.channels],
                "types": [c.type for c in s.channels],
                "nominal_rate_hz": s.nominal_rate_hz,
                "clock": s.clock.domain,
                "modality": str(s.modality) if s.modality is not None else None,
                "invasive": s.invasive,
                "bin_ms": s.bin_ms,
                "quantity": s.quantity,
                "model_id": s.model_id,
            }
            for s in info.streams
        ],
    }


def identity_diff(a: Mapping[str, Any], b: Mapping[str, Any]) -> list[str]:
    diffs: list[str] = []
    for key in ("primary_stream", "synthetic", "prerecorded", "origin"):
        if a.get(key) != b.get(key):
            diffs.append(f"{key}: {a.get(key)!r} -> {b.get(key)!r}")
    sa = [s["stream_id"] for s in a["streams"]]
    sb = [s["stream_id"] for s in b["streams"]]
    if sa != sb:
        diffs.append(f"stream ids/order: {sa} -> {sb}")
    for x, y in zip(a["streams"], b["streams"], strict=False):
        if x["stream_id"] != y["stream_id"]:
            continue
        for key in x:
            if x[key] != y[key]:
                diffs.append(f"{x['stream_id']}.{key}: {_short(x[key])} -> {_short(y[key])}")
    return diffs


def _short(value: object) -> str:
    text = repr(value)
    return text if len(text) <= 120 else text[:117] + "..."


def check_channel_identity(results: Results, snapshots: Mapping[str, dict[str, Any]]) -> None:
    names = list(snapshots)
    if len(names) < 2:
        results.set(
            "metadata.channel_identity",
            "not_run",
            f"needs at least two successful opens (got {len(names)})",
        )
        return
    base = snapshots[names[0]]
    diffs: dict[str, list[str]] = {}
    for name in names[1:]:
        d = identity_diff(base, snapshots[name])
        if d:
            diffs[name] = d
    n_ch = sum(len(s["labels"]) for s in base["streams"])
    ev = {"opens_compared": names, "differences": diffs, "reference": names[0], "channels": n_ch}
    if diffs:
        first = next(iter(diffs))
        results.set(
            "metadata.channel_identity",
            "fail",
            f"{first} differs from {names[0]}: {diffs[first][0]}",
            ev,
        )
    else:
        results.set(
            "metadata.channel_identity",
            "pass",
            f"{len(names)} opens ({', '.join(names)}): identical stream ids, labels, order, "
            f"units, rates ({n_ch} channels)",
            ev,
        )


def redact(options: Mapping[str, Any]) -> dict[str, Any]:
    """Values of options whose name contains secret / token / password are replaced."""
    out: dict[str, Any] = {}
    for k, val in options.items():
        low = str(k).lower()
        sensitive = any(w in low for w in ("secret", "token", "password", "passwd"))
        out[str(k)] = "<redacted>" if sensitive else val
    return out
