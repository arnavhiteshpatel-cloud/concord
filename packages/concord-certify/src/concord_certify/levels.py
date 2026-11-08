"""Validation levels: what a certification run can and cannot claim.

Exactly four levels (docs/CERTIFICATION.md):

``adapter_implementation``
    Every required automated check passed (or warned). The ONLY level this toolkit grants by
    itself.
``protocol_tested``
    Additionally the operator states which external reference software produced the data
    (``--protocol-reference``) and the session's ecosystem / origin is consistent with that
    statement. Reported as "protocol-tested against <reference> (operator statement)".
``hardware_tested``
    Only recorded from an operator-signed attestation (``--attestation``) whose signature
    verifies against the public key the operator supplies and which names the plugin under
    test. Reported as "operator-attested, not verified by this toolkit". Never without it.
``human_participant_validated``
    Never set by this toolkit: out of scope for software.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
from importlib import resources
from pathlib import Path
from typing import Any

import jsonschema
from concord_adapter_sdk import PluginManifest, SessionInfo

from concord_certify.model import CheckResult

LEVELS: tuple[str, ...] = (
    "adapter_implementation",
    "protocol_tested",
    "hardware_tested",
    "human_participant_validated",
)
OPENSSL_TIMEOUT_S = 20.0
VERSION_TOKEN = re.compile(r"(?<![\w.])(\d+\.\d+(?:\.\d+)?)(?![\w.])")


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


# ----------------------------------------------------------------------------- level 1


def adapter_implementation(checks: list[CheckResult]) -> dict[str, Any]:
    missing: list[str] = []
    for c in checks:
        d = c.definition
        if c.status == "fail":
            missing.append(f"{c.id} failed: {c.reason}")
        elif d.required and c.status == "not_run" and c.applicable:
            missing.append(f"{c.id} not run: {c.reason}")
    runtime_not_run = [
        c.id for c in checks if c.id.startswith("runtime.") and c.status == "not_run"
    ]
    notes: list[str] = []
    if runtime_not_run:
        notes.append(
            "Concord runtime phase not run: event-contract compliance and negotiation were not "
            "verified by this report"
        )
    achieved = not missing
    return {
        "achieved": achieved,
        "statement": "adapter implementation: every required automated check passed"
        if achieved
        else "not achieved",
        "why": "all required checks passed or warned; no check failed"
        if achieved
        else f"{len(missing)} blocking check result(s)",
        "missing": missing,
        "notes": notes,
    }


# ----------------------------------------------------------------------------- level 2


def protocol_consistency(
    reference: str | None,
    manifest: PluginManifest | None,
    info: SessionInfo | None,
    installed_versions: dict[str, str | None],
) -> list[dict[str, Any]]:
    """Rules relating the operator's reference statement to the session. ``ok`` is True,
    False, or None (not checkable; does not block)."""
    rules: list[dict[str, Any]] = []
    ref = (reference or "").strip()
    rules.append(
        {
            "rule": "reference_given",
            "ok": bool(ref),
            "detail": ref or "no --protocol-reference given",
        }
    )
    eco = manifest.ecosystem if manifest is not None else None
    rules.append(
        {"rule": "ecosystem_declared", "ok": bool(eco), "detail": f"manifest.ecosystem = {eco!r}"}
    )
    if not ref or not eco:
        return rules
    rules.append(
        {
            "rule": "reference_names_ecosystem",
            "ok": _norm(eco) in _norm(ref),
            "detail": f"reference {'mentions' if _norm(eco) in _norm(ref) else 'does not mention'} "
            f"the plugin's ecosystem {eco!r}",
        }
    )
    origin = info.origin if info is not None else ""
    rules.append(
        {
            "rule": "origin_from_ecosystem",
            "ok": origin.lower().startswith(f"{eco.lower()}:"),
            "detail": f"session origin {origin!r}",
        }
    )
    m = VERSION_TOKEN.search(ref)
    installed = installed_versions.get(eco)
    if m is None or installed is None:
        rules.append(
            {
                "rule": "reference_version_matches_installed",
                "ok": None,
                "detail": "not checkable: "
                + (
                    "no version in the reference"
                    if m is None
                    else f"no Python distribution named {eco!r} in the plugin's environment"
                ),
            }
        )
    else:
        want = m.group(1)
        ok = installed == want or installed.startswith(want + ".")
        rules.append(
            {
                "rule": "reference_version_matches_installed",
                "ok": ok,
                "detail": f"reference version {want}, installed {eco} {installed}",
            }
        )
    return rules


def protocol_tested(
    level1: bool, reference: str | None, rules: list[dict[str, Any]]
) -> dict[str, Any]:
    missing: list[str] = []
    if not level1:
        missing.append("adapter_implementation not achieved")
    if not reference:
        missing.append(
            "no --protocol-reference: name the external reference software that produced the "
            'data (e.g. "BrainFlow 5.23 BoardShim SYNTHETIC_BOARD")'
        )
    else:
        missing += [f"{r['rule']}: {r['detail']}" for r in rules if r["ok"] is False]
    achieved = not missing
    return {
        "achieved": achieved,
        "statement": f"protocol-tested against {reference} (operator statement)"
        if achieved
        else "not achieved",
        "why": "the operator named the reference software and the session's ecosystem and "
        "origin are consistent with it; the toolkit cannot observe which program produced the "
        "data, so this rests on the operator's statement"
        if achieved
        else "see missing",
        "missing": missing,
        "consistency": rules,
    }


# ----------------------------------------------------------------------------- level 3


def attestation_schema() -> dict[str, Any]:
    text = resources.files("concord_certify").joinpath("schemas/attestation.schema.json")
    doc: dict[str, Any] = json.loads(text.read_text(encoding="utf-8"))
    return doc


def _openssl() -> str | None:
    return shutil.which("openssl")


def key_fingerprint(public_key: Path) -> str | None:
    """SHA-256 of the DER-encoded public key (as ``openssl pkey -pubin -outform DER``)."""
    exe = _openssl()
    if exe is None:
        return None
    try:
        p = subprocess.run(
            [exe, "pkey", "-pubin", "-in", str(public_key), "-outform", "DER"],
            capture_output=True,
            timeout=OPENSSL_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return hashlib.sha256(p.stdout).hexdigest() if p.returncode == 0 and p.stdout else None


def verify_signature(document: Path, signature: Path, public_key: Path) -> tuple[bool, str]:
    """Ed25519 detached signature over the exact bytes of ``document`` (OpenSSL 3)."""
    exe = _openssl()
    if exe is None:
        return False, "cannot verify the signature: 'openssl' was not found"
    try:
        p = subprocess.run(
            [
                exe,
                "pkeyutl",
                "-verify",
                "-pubin",
                "-inkey",
                str(public_key),
                "-rawin",
                "-in",
                str(document),
                "-sigfile",
                str(signature),
            ],
            capture_output=True,
            text=True,
            timeout=OPENSSL_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"signature verification could not run: {exc}"
    if p.returncode == 0:
        return True, "Ed25519 signature verified with the supplied public key"
    detail = (p.stdout + p.stderr).strip().splitlines()
    return False, f"signature does not verify ({detail[0] if detail else 'openssl failed'})"


def check_attestation(
    path: Path,
    signature: Path | None,
    public_key: Path | None,
    *,
    plugin_name: str | None,
    plugin_version: str | None,
    tree_sha256: str | None,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Validate an operator attestation. Returns ``{"accepted": bool, "reason", ...}``.

    Accepted means: well-formed, signed by the holder of ``public_key``, about this plugin
    and version, dated not in the future. It never means the hardware claim was verified.
    """
    out: dict[str, Any] = {
        "file": str(path),
        "accepted": False,
        "reason": "",
        "file_sha256": None,
        "signature_file": str(signature) if signature else None,
        "public_key_file": str(public_key) if public_key else None,
        "public_key_sha256": None,
        "attested": None,
        "verified_by_toolkit": "signature and plugin identity only; hardware claims NOT verified",
    }

    def reject(reason: str) -> dict[str, Any]:
        out["reason"] = reason
        return out

    try:
        raw = path.read_bytes()
    except OSError as exc:
        return reject(f"cannot read attestation: {exc}")
    out["file_sha256"] = hashlib.sha256(raw).hexdigest()
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        return reject(f"attestation is not valid UTF-8 JSON: {exc}")
    schema = attestation_schema()
    err = jsonschema.exceptions.best_match(jsonschema.Draft202012Validator(schema).iter_errors(doc))
    if err is not None:
        where = "/".join(str(p) for p in err.absolute_path) or "(document)"
        return reject(f"attestation does not match the schema at {where}: {err.message[:200]}")
    out["attested"] = {
        "attested_by": doc["attested_by"],
        "date": doc["date"],
        "plugin": doc["plugin"],
        "hardware": doc["hardware"],
        "acquisition_software": doc["acquisition_software"],
        "setup": doc["setup"],
        "observations": doc["observations"],
        "duration_s": doc["duration_s"],
    }
    if signature is None or public_key is None:
        return reject(
            "attestation is not signed: pass --attestation-signature and "
            "--attestation-public-key (Ed25519, see docs/CERTIFICATION.md)"
        )
    out["public_key_sha256"] = key_fingerprint(public_key)
    ok, msg = verify_signature(path, signature, public_key)
    if not ok:
        return reject(msg)
    if plugin_name is None or doc["plugin"]["name"] != plugin_name:
        return reject(f"attestation is for plugin {doc['plugin']['name']!r}, not {plugin_name!r}")
    if doc["plugin"]["version"] != plugin_version:
        return reject(
            f"attestation is for version {doc['plugin']['version']!r}, the plugin under test "
            f"is {plugin_version!r}"
        )
    want_tree = doc["plugin"].get("tree_sha256")
    if want_tree is not None and want_tree != tree_sha256:
        return reject("attestation tree_sha256 does not match the plugin files under test")
    try:
        when = dt.datetime.fromisoformat(doc["date"].replace("Z", "+00:00"))
    except ValueError:
        return reject(f"attestation date {doc['date']!r} is not a valid ISO 8601 time")
    now = now or dt.datetime.now(dt.UTC)
    if when > now + dt.timedelta(minutes=5):
        return reject(f"attestation date {doc['date']} is in the future")
    out["accepted"] = True
    out["reason"] = msg
    return out


def hardware_tested(level1: bool, attestation: dict[str, Any] | None) -> dict[str, Any]:
    missing: list[str] = []
    if not level1:
        missing.append("adapter_implementation not achieved")
    if attestation is None:
        missing.append(
            "no operator attestation (--attestation): hardware testing cannot be established by "
            "software and is never inferred"
        )
    elif not attestation.get("accepted"):
        missing.append(f"attestation rejected: {attestation.get('reason')}")
    achieved = not missing
    hw = ((attestation or {}).get("attested") or {}).get("hardware") or {}
    who = ((attestation or {}).get("attested") or {}).get("attested_by") or {}
    return {
        "achieved": achieved,
        "statement": (
            f"hardware-tested: operator-attested by {who.get('name')} ({who.get('organization')}) "
            f"with {hw.get('make')} {hw.get('model')} serial {hw.get('serial_number')}; "
            "not verified by this toolkit"
        )
        if achieved
        else "not achieved",
        "why": "a signed operator attestation for this plugin and version was supplied and its "
        "signature verifies; the toolkit did not observe or verify the hardware"
        if achieved
        else "see missing",
        "missing": missing,
    }


# ----------------------------------------------------------------------------- level 4


def human_participant_validated() -> dict[str, Any]:
    return {
        "achieved": False,
        "statement": "never set by this toolkit",
        "why": "human-participant validation is out of scope for software: it requires an "
        "approved human-research protocol run by qualified investigators",
        "missing": ["out of scope for software; never granted by concord-certify"],
    }


def evaluate(
    checks: list[CheckResult],
    *,
    reference: str | None,
    rules: list[dict[str, Any]],
    attestation: dict[str, Any] | None,
) -> dict[str, Any]:
    l1 = adapter_implementation(checks)
    levels = {
        "adapter_implementation": l1,
        "protocol_tested": protocol_tested(l1["achieved"], reference, rules),
        "hardware_tested": hardware_tested(l1["achieved"], attestation),
        "human_participant_validated": human_participant_validated(),
    }
    achieved = [name for name in LEVELS if levels[name]["achieved"]]
    return {
        "achieved": achieved,
        "highest": achieved[-1] if achieved else None,
        "levels": levels,
    }
