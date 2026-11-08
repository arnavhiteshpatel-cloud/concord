"""Shared helpers for concord-certify tests (uniquely named: no clash with other conftests)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from concord_certify import levels as lv
from concord_certify.runner import CertifyConfig, run

PLUGINS_DIR = Path(__file__).parent / "plugins"
MODULE = "certify_test_plugins"


def ref(cls: str = "DefectPlugin") -> str:
    return f"{MODULE}:{cls}"


def config(cls: str = "DefectPlugin", **over: Any) -> CertifyConfig:
    options = over.pop("options", {})
    base: dict[str, Any] = {
        "plugin": ref(cls),
        "options": options,
        "duration_s": 1.5,
        "reopen_s": 0.5,
        "runtime": False,
        "runtime_s": 1.5,
        "read_grace_s": 1.0,
        "start_timeout_s": 20.0,
        "open_timeout_s": 10.0,
        "extra_path": (str(PLUGINS_DIR),),
    }
    base.update(over)
    return CertifyConfig(**base)


def certify(cls: str = "DefectPlugin", **over: Any) -> dict[str, Any]:
    return run(config(cls, **over))


def check(report: dict[str, Any], check_id: str) -> dict[str, Any]:
    return next(c for c in report["checks"] if c["id"] == check_id)


# ----------------------------------------------------------------------------- attestations

OPENSSL = shutil.which("openssl")


def attestation_doc(**over: Any) -> dict[str, Any]:
    doc: dict[str, Any] = {
        "attestation_version": "1.0",
        "statement": lv.attestation_schema()["properties"]["statement"]["const"],
        "attested_by": {"name": "A. Researcher", "organization": "Test Lab", "role": "engineer",
                        "email": "a@example.org"},
        "date": "2026-11-01T10:00:00Z",
        "plugin": {"name": "concord-brainflow", "version": "0.1.0"},
        "hardware": {"make": "ExampleMaker", "model": "Board 8", "serial_number": "SN-1",
                     "firmware_version": "1.2.3"},
        "acquisition_software": "vendor acquisition app 2.0",
        "setup": "Board connected over USB to the Concord machine; 8 electrodes on a phantom.",
        "observations": "30 minutes, no gaps reported, values in expected range on all channels.",
        "duration_s": 1800,
    }  # fmt: skip
    doc.update(over)
    return doc


def keypair(tmp: Path) -> tuple[Path, Path]:
    assert OPENSSL is not None
    key, pub = tmp / "operator.key", tmp / "operator.pub"
    subprocess.run([OPENSSL, "genpkey", "-algorithm", "ed25519", "-out", str(key)], check=True)
    subprocess.run([OPENSSL, "pkey", "-in", str(key), "-pubout", "-out", str(pub)], check=True)
    return key, pub


def sign(doc_path: Path, key: Path) -> Path:
    assert OPENSSL is not None
    sig = doc_path.with_suffix(".json.sig")
    subprocess.run([OPENSSL, "pkeyutl", "-sign", "-rawin", "-inkey", str(key), "-in",
                    str(doc_path), "-out", str(sig)], check=True)  # fmt: skip
    return sig
