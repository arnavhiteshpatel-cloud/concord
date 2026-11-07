"""Optional phase: the plugin through BrainOS's real ``PluginAdapter`` and ``Runtime``.

Runs only when ``brainos`` is importable (``pip install brainos-certify[runtime]``). The
plugin is registered and connected in an in-process ``Runtime`` (no server), test
applications negotiate capabilities, and every event BrainOS publishes is checked against
the BrainOS contracts and against what the plugin declared:

* ``runtime.descriptor``  - kind / synthetic / modality / invasive / integration / capabilities
* ``runtime.negotiation`` - grants and rejections follow the plugin's roles; command
  capabilities are never granted (the command router is off)
* ``runtime.envelopes``   - pydantic contract (``parse_envelope``) AND the published JSON Schema
* ``runtime.provenance``  - provenance kind per role, synthetic / replayed flags, decoder
  model_id; no command event types

The expectations are derived from the plugin's own ``SessionInfo`` and manifest (via the
adapter SDK), not from BrainOS, so a BrainOS mapping bug would show up here too.
"""

from __future__ import annotations

import asyncio
import json
import logging
import tempfile
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from brainos_adapter_sdk import PluginManifest, SessionInfo, StreamRole, StreamSpec

from brainos_certify.model import Results

log = logging.getLogger(__name__)

RUNTIME_CHECKS = (
    "runtime.descriptor",
    "runtime.negotiation",
    "runtime.envelopes",
    "runtime.provenance",
)
ROLE_CAPABILITY = {
    StreamRole.SIGNAL: "recording",
    StreamRole.MARKERS: "recording",
    StreamRole.SPIKE_COUNTS: "neural_features",
    StreamRole.BEHAVIOR: "behavior",
    StreamRole.DECODER_OUTPUT: "kinematic_intent",
}
ROLE_EVENT = {
    StreamRole.SIGNAL: "recording.frame",
    StreamRole.MARKERS: "recording.annotation",
    StreamRole.SPIKE_COUNTS: "features.binned",
    StreamRole.BEHAVIOR: "behavior.sample",
    StreamRole.DECODER_OUTPUT: "intent.kinematics",
}
ROLE_PROVENANCE = {
    StreamRole.SIGNAL: "raw_signal",
    StreamRole.SPIKE_COUNTS: "processed_feature",
    StreamRole.BEHAVIOR: "behavioral_label",
    StreamRole.MARKERS: "behavioral_label",
    StreamRole.DECODER_OUTPUT: "decoded_intent",
}
COMMAND_CAPABILITIES = frozenset({"pointer_intent", "selection", "text_intent"})
COMMAND_EVENTS = frozenset({"intent.pointer", "intent.selection", "intent.text"})
INVASIVE = frozenset({"ecog", "seeg", "intracortical"})
NONINVASIVE = frozenset({"eeg", "meg", "emg"})
MAX_VALIDATED_EVENTS = 5000


def brainos_available() -> tuple[bool, str]:
    try:
        import brainos.runtime  # noqa: F401
    except Exception as exc:  # not installed, or broken install
        return False, f"BrainOS is not importable ({type(exc).__name__}: {exc})"[:300]
    return True, ""


# ----------------------------------------------------------------------------- expectations


def delivered_streams(info: SessionInfo) -> dict[StreamRole, StreamSpec]:
    """One stream per role: the primary for its role, else the first declared."""
    order = sorted(info.streams, key=lambda s: s.stream_id != info.primary_stream)
    out: dict[StreamRole, StreamSpec] = {}
    for s in order:
        out.setdefault(StreamRole(s.role), s)
    return out


def expected_capabilities(info: SessionInfo) -> set[str]:
    return {ROLE_CAPABILITY[r] for r in delivered_streams(info)} | {"device_status"}


def expected_descriptor(info: SessionInfo, manifest: PluginManifest) -> dict[str, Any]:
    primary = next(s for s in info.streams if s.stream_id == info.primary_stream)
    modality: str | None = None
    invasive: bool | None = None
    if StreamRole(primary.role) in (StreamRole.SIGNAL, StreamRole.SPIKE_COUNTS):
        modality = str(primary.modality) if primary.modality is not None else None
        invasive = primary.invasive
        if invasive is None and modality in INVASIVE:
            invasive = True
        elif invasive is None and modality in NONINVASIVE:
            invasive = False
    kind = "simulated" if info.synthetic else "replay" if info.prerecorded else "stream"
    return {
        "kind": kind,
        "synthetic": info.synthetic,
        "modality": modality,
        "invasive": invasive,
        "integration": {
            "kind": "plugin",
            "package": manifest.name,
            "version": manifest.version,
            "api_version": manifest.api_version,
            "isolated": True,
            "ecosystem": manifest.ecosystem,
        },
        "capabilities": sorted(expected_capabilities(info)),
    }


def compare_descriptor(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> list[str]:
    """Differences between the expected and the actual descriptor (as JSON dicts)."""
    diffs: list[str] = []
    for key in ("kind", "synthetic", "modality", "invasive"):
        if expected[key] != actual.get(key):
            diffs.append(f"{key}: expected {expected[key]!r}, BrainOS has {actual.get(key)!r}")
    integ = actual.get("integration") or {}
    for key, want in expected["integration"].items():
        if integ.get(key) != want:
            diffs.append(f"integration.{key}: expected {want!r}, BrainOS has {integ.get(key)!r}")
    caps = sorted(str(c.get("capability")) for c in actual.get("capabilities") or [])
    if caps != expected["capabilities"]:
        diffs.append(f"capabilities: expected {expected['capabilities']}, BrainOS has {caps}")
    if COMMAND_CAPABILITIES & set(caps):
        diffs.append(
            f"descriptor claims command capabilities {sorted(COMMAND_CAPABILITIES & set(caps))}"
        )
    return diffs


def check_negotiations(
    expected_caps: set[str], all_caps: Sequence[str], results: Mapping[str, Mapping[str, Any]]
) -> list[str]:
    """``results``: app name -> NegotiationResult as JSON. Returns the problems."""
    problems: list[str] = []
    want_rejected = sorted(set(all_caps) - expected_caps)
    every = results.get("all_optional")
    if every is not None:
        granted = sorted(every.get("granted") or [])
        if granted != sorted(expected_caps):
            problems.append(
                f"all-optional app: granted {granted}, expected {sorted(expected_caps)}"
            )
        rej = {str(r["capability"]): r for r in every.get("rejected") or []}
        if sorted(rej) != want_rejected:
            problems.append(f"all-optional app: rejected {sorted(rej)}, expected {want_rejected}")
        bad = [c for c, r in rej.items() if r.get("reason") != "unsupported_by_device"]
        if bad:
            problems.append(f"all-optional app: unexpected rejection reasons for {sorted(bad)}")
        if every.get("status") != "active":
            problems.append(f"all-optional app: status {every.get('status')!r}, expected 'active'")
    req = results.get("roles_required")
    if req is not None:
        if req.get("status") != "active":
            problems.append(f"roles-required app: status {req.get('status')!r}, expected 'active'")
        if sorted(req.get("granted") or []) != sorted(expected_caps):
            problems.append(f"roles-required app: granted {sorted(req.get('granted') or [])}")
    cmd = results.get("command_required")
    if cmd is not None:
        if cmd.get("status") != "suspended":
            problems.append(f"command app: status {cmd.get('status')!r}, expected 'suspended'")
        if cmd.get("granted"):
            problems.append(f"command app was granted {cmd.get('granted')}")
        for r in cmd.get("rejected") or []:
            if r.get("reason") not in ("unsupported_by_device", "not_authorized"):
                problems.append(f"command app: {r.get('capability')} rejected as {r.get('reason')}")
    return problems


def check_event_provenance(
    event: Mapping[str, Any],
    info: SessionInfo,
    manifest: PluginManifest,
    stream_by_event: Mapping[str, StreamSpec],
) -> list[str]:
    """Problems with one published event's provenance / quality."""
    et = str(event.get("event_type"))
    prov = event.get("provenance") or {}
    if et in COMMAND_EVENTS:
        return [f"{et}: a command event reached the bus"]
    if et == "device.status":
        return (
            []
            if prov.get("kind") == "runtime"
            else [f"device.status provenance {prov.get('kind')!r}"]
        )
    spec = stream_by_event.get(et)
    if spec is None:
        return [f"{et}: event type not expected from the declared roles"]
    out: list[str] = []
    role = StreamRole(spec.role)
    if prov.get("kind") != ROLE_PROVENANCE[role]:
        out.append(
            f"{et}: provenance kind {prov.get('kind')!r}, expected {ROLE_PROVENANCE[role]!r}"
        )
    if prov.get("synthetic") is not info.synthetic:
        out.append(
            f"{et}: provenance.synthetic {prov.get('synthetic')!r}, declared {info.synthetic}"
        )
    replayed = info.prerecorded and not info.synthetic
    if bool(prov.get("replayed")) is not replayed:
        out.append(f"{et}: provenance.replayed {prov.get('replayed')!r}, expected {replayed}")
    if prov.get("origin") != info.origin[:128]:
        out.append(f"{et}: provenance.origin {prov.get('origin')!r} != declared origin")
    if role is StreamRole.DECODER_OUTPUT:
        want = f"{manifest.name}:{spec.model_id}"[:128]
        if prov.get("model_id") != want:
            out.append(f"{et}: model_id {prov.get('model_id')!r}, expected {want!r}")
    elif prov.get("model_id") is not None:
        out.append(f"{et}: model_id set on a {role.value} stream")
    flags = set((event.get("quality") or {}).get("flags") or [])
    if info.synthetic and "synthetic" not in flags:
        out.append(f"{et}: quality flag 'synthetic' missing")
    if replayed and "replayed" not in flags:
        out.append(f"{et}: quality flag 'replayed' missing")
    return out


# ----------------------------------------------------------------------------- run


def run_runtime_phase(
    results: Results,
    *,
    plugin_ref: str,
    entry_point_name: str | None,
    device_key: str,
    options: Mapping[str, Any],
    manifest: PluginManifest,
    info: SessionInfo,
    python: str | None,
    extra_path: Sequence[str],
    seconds: float,
    start_timeout_s: float,
    open_timeout_s: float,
    read_grace_s: float,
) -> dict[str, Any]:
    """Run the phase; sets the four ``runtime.*`` results. Returns phase facts (schema
    version, BrainOS session info, the runtime's SessionInfo for the identity check)."""
    ok, why = brainos_available()
    if not ok:
        for cid in RUNTIME_CHECKS:
            results.set(cid, "not_run", f"runtime phase not run: {why}", applicable=False)
        return {"ran": False, "reason": why}
    try:
        return asyncio.run(
            _run(
                results,
                plugin_ref=plugin_ref,
                entry_point_name=entry_point_name,
                device_key=device_key,
                options=options,
                manifest=manifest,
                info=info,
                python=python,
                extra_path=extra_path,
                seconds=seconds,
                start_timeout_s=start_timeout_s,
                open_timeout_s=open_timeout_s,
                read_grace_s=read_grace_s,
            )
        )
    except Exception as exc:
        log.exception("runtime phase failed")
        msg = f"runtime phase failed: {type(exc).__name__}: {exc}"[:300]
        for cid in RUNTIME_CHECKS:
            if not results.has(cid):
                results.set(cid, "fail", msg)
        return {"ran": True, "error": msg}


async def _run(
    results: Results,
    *,
    plugin_ref: str,
    entry_point_name: str | None,
    device_key: str,
    options: Mapping[str, Any],
    manifest: PluginManifest,
    info: SessionInfo,
    python: str | None,
    extra_path: Sequence[str],
    seconds: float,
    start_timeout_s: float,
    open_timeout_s: float,
    read_grace_s: float,
) -> dict[str, Any]:
    import jsonschema
    from brainos.adapters.plugin import PluginAdapter, PluginSpec
    from brainos.adapters.plugin.mapping import device_id as make_device_id
    from brainos.adapters.simulated import OperatorIntentSource
    from brainos.contracts import SCHEMA_VERSION, Capability, envelope_json_schema, parse_envelope
    from brainos.contracts.events import EventEnvelope
    from brainos.contracts.protocol import AppInfo
    from brainos.runtime import DeviceRegistry, Recorder, Runtime
    from brainos_adapter_sdk import ipc

    facts: dict[str, Any] = {"ran": True, "schema_version": SCHEMA_VERSION}
    did = (
        make_device_id(entry_point_name, device_key)
        if entry_point_name
        else f"plugin:certify:{device_key}"[:64]
    )
    spec = PluginSpec(
        device_id=did,
        entry_point=plugin_ref,
        device_key=device_key,
        options=dict(options),
        manifest=manifest,
        python=python,
        extra_path=tuple(extra_path),
        start_timeout_s=start_timeout_s,
        open_timeout_s=open_timeout_s,
        read_grace_s=read_grace_s,
    )
    expected = expected_descriptor(info, manifest)
    expected_caps = expected_capabilities(info)
    all_caps = [c.value for c in Capability]
    collected: list[str] = []
    counts: Counter[str] = Counter()

    def tap(envelope: EventEnvelope, event_json: str) -> None:
        counts[envelope.event_type.value] += 1
        if len(collected) < MAX_VALIDATED_EVENTS:
            collected.append(event_json)

    with tempfile.TemporaryDirectory(prefix="brainos-certify-") as tmp:
        rec_dir = Path(tmp) / "recordings"
        registry = DeviceRegistry(OperatorIntentSource(), rec_dir, seed=1)
        rt = Runtime(registry, Recorder(rec_dir))
        rt.bus.add_tap(tap)
        try:
            descriptor = await registry.plugins.register(spec, probe=True)
            desc_json = json.loads(descriptor.model_dump_json())
            await rt.connect(did)
            apps = {
                "all_optional": rt.register_app(
                    AppInfo(id="certify-all", name="certify: every capability optional"),
                    [],
                    list(Capability),
                ),
                "roles_required": rt.register_app(
                    AppInfo(id="certify-roles", name="certify: role capabilities required"),
                    [Capability(c) for c in sorted(expected_caps)],
                    [],
                ),
                "command_required": rt.register_app(
                    AppInfo(id="certify-cmd", name="certify: pointer commands required"),
                    [Capability.POINTER_INTENT],
                    [Capability.SELECTION, Capability.TEXT_INTENT],
                ),
            }
            await asyncio.sleep(seconds)
            negotiations = {
                name: json.loads(sub.negotiation.model_dump_json()) for name, sub in apps.items()
            }
            cmd_sub = apps["command_required"]
            cmd_received = cmd_sub.delivered + cmd_sub.queue_depth
            diag = rt.diagnostics
            diag_counts = {
                "validation_errors": diag.validation_errors,
                "undeclared_capability": diag.undeclared_capability,
                "decode_errors": diag.decode_errors,
                "link_errors": diag.link_errors,
                "timestamp_regressions": diag.timestamp_regressions,
            }
            state = rt.state.value
            last_error = rt.snapshot().last_error
            adapter = rt.adapter
            rt_info = adapter.session_info if isinstance(adapter, PluginAdapter) else None
            if rt_info is not None:
                facts["session_info"] = ipc.session_info_to_dict(rt_info)
            await rt.disconnect()
        finally:
            await rt.shutdown()

    # --- runtime.descriptor
    diffs = compare_descriptor(expected, desc_json)
    ev_desc = {
        "device_id": did,
        "expected": expected,
        "brainos": {
            k: desc_json.get(k)
            for k in ("kind", "synthetic", "modality", "invasive", "integration", "adapter")
        },
        "brainos_capabilities": [c.get("capability") for c in desc_json.get("capabilities", [])],
    }
    if diffs:
        results.set("runtime.descriptor", "fail", diffs[0], {**ev_desc, "differences": diffs})
    else:
        results.set(
            "runtime.descriptor",
            "pass",
            f"descriptor kind={expected['kind']} modality={expected['modality']} "
            f"invasive={expected['invasive']} integration=plugin matches the declarations",
            ev_desc,
        )

    # --- runtime.negotiation
    neg_problems = check_negotiations(expected_caps, all_caps, negotiations)
    if cmd_received:
        neg_problems.append(f"the command app received {cmd_received} message(s) while suspended")
    ev_neg = {"expected_granted": sorted(expected_caps), "negotiations": negotiations}
    if neg_problems:
        results.set(
            "runtime.negotiation", "fail", neg_problems[0], {**ev_neg, "problems": neg_problems}
        )
    else:
        results.set(
            "runtime.negotiation",
            "pass",
            f"granted {sorted(expected_caps)}; every other capability rejected "
            "(unsupported_by_device); command app suspended",
            ev_neg,
        )

    # --- runtime.envelopes
    schema = envelope_json_schema()
    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)
    invalid: list[str] = []
    events: list[dict[str, Any]] = []
    versions: Counter[str] = Counter()
    for raw in collected:
        doc = json.loads(raw)
        events.append(doc)
        versions[str(doc.get("schema_version"))] += 1
        try:
            parse_envelope(doc)
        except Exception as exc:
            invalid.append(f"pydantic: {doc.get('event_type')}: {str(exc).splitlines()[0]}")
        err = next(iter(validator.iter_errors(doc)), None)
        if err is not None:
            invalid.append(f"json-schema: {doc.get('event_type')}: {err.message[:200]}")
    total = sum(counts.values())
    data_events = total - counts.get("device.status", 0)
    ev_env = {
        "schema_version": SCHEMA_VERSION,
        "event_schema_versions": dict(versions),
        "events_published": total,
        "events_validated": len(collected),
        "event_types": dict(counts),
        "invalid": invalid[:20],
        "runtime_diagnostics": diag_counts,
        "runtime_state_at_end": state,
        "runtime_last_error": last_error,
        "seconds": seconds,
    }
    env_problems = list(invalid)
    for key in ("validation_errors", "undeclared_capability", "decode_errors"):
        if diag_counts[key]:
            env_problems.append(f"BrainOS diagnostics: {key} = {diag_counts[key]}")
    if state != "streaming":
        env_problems.append(f"runtime ended in state {state!r}: {last_error}")
    if data_events == 0:
        env_problems.append(f"no data events published in {seconds:g} s")
    if env_problems:
        results.set("runtime.envelopes", "fail", env_problems[0], ev_env)
    else:
        results.set(
            "runtime.envelopes",
            "pass",
            f"{len(collected)} of {total} events validated against contract {SCHEMA_VERSION} "
            "(pydantic + JSON Schema); 0 invalid, 0 undeclared, 0 decode errors",
            ev_env,
        )

    # --- runtime.provenance
    delivered = delivered_streams(info)
    stream_by_event = {ROLE_EVENT[r]: s for r, s in delivered.items()}
    prov_problems: list[str] = []
    for doc in events:
        for p in check_event_provenance(doc, info, manifest, stream_by_event):
            if p not in prov_problems:
                prov_problems.append(p)
    commands = {e: n for e, n in counts.items() if e in COMMAND_EVENTS}
    if commands:
        prov_problems.insert(0, f"command events published: {commands}")
    silent = sorted(
        ROLE_EVENT[r]
        for r, s in delivered.items()
        if ROLE_EVENT[r] not in counts and s.nominal_rate_hz > 0
    )
    ev_prov = {
        "declared": {
            "synthetic": info.synthetic,
            "prerecorded": info.prerecorded,
            "origin": info.origin,
        },
        "expected_provenance": {ROLE_EVENT[r]: ROLE_PROVENANCE[r] for r in delivered},
        "decoder_model_id": next(
            (
                f"{manifest.name}:{s.model_id}"
                for r, s in delivered.items()
                if r is StreamRole.DECODER_OUTPUT
            ),
            None,
        ),
        "command_events": commands,
        "regular_streams_without_events": silent,
        "problems": prov_problems[:20],
    }
    if prov_problems:
        results.set("runtime.provenance", "fail", prov_problems[0], ev_prov)
    elif silent:
        results.set(
            "runtime.provenance",
            "warn",
            f"no events from regular stream(s) {silent} in {seconds:g} s",
            ev_prov,
        )
    else:
        results.set(
            "runtime.provenance",
            "pass",
            "provenance kinds, synthetic/replayed flags, origin and model ids as declared; "
            "no command events",
            ev_prov,
        )
    return facts
