"""Plugin identity: entry points, distributions and RECORD hashes (a temporary install)."""

from __future__ import annotations

import base64
import hashlib
import shutil
from pathlib import Path

from certify_helpers import PLUGINS_DIR, certify, check

from concord_certify.identity import collect_identity

MODULE_FILE = PLUGINS_DIR / "certify_test_plugins.py"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def install(site: Path, name: str = "certify-test-plugins", ep: str = "certify-test") -> Path:
    """A minimal installed distribution: the module, METADATA, entry_points.txt, RECORD."""
    site.mkdir(parents=True, exist_ok=True)
    shutil.copy(MODULE_FILE, site / MODULE_FILE.name)
    info = site / f"{name.replace('-', '_')}-0.0.1.dist-info"
    info.mkdir(exist_ok=True)
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {name}\nVersion: 0.0.1\n")
    (info / "entry_points.txt").write_text(
        f"[concord.sources]\n{ep} = certify_test_plugins:DefectPlugin\n"
    )
    data = (site / MODULE_FILE.name).read_bytes()
    record = [
        f"{MODULE_FILE.name},sha256={_b64(data)},{len(data)}",
        f"{info.name}/METADATA,,",
        f"{info.name}/RECORD,,",
    ]
    (info / "RECORD").write_text("\n".join(record) + "\n")
    return site


def test_installed_entry_point_and_record_verified(tmp_path: Path) -> None:
    site = install(tmp_path / "site")
    r = certify(plugin="certify-test", extra_path=(str(site),))
    ep = check(r, "manifest.entry_point")
    assert ep["status"] == "pass" and "certify_test_plugins:DefectPlugin" in ep["reason"]
    dist = check(r, "manifest.distribution")
    assert dist["status"] == "pass", dist["reason"]
    assert "1 of 1 hashed RECORD entries verified" in dist["reason"]
    ident = r["plugin"]["identity"]
    assert ident["distribution"]["name"] == "certify-test-plugins"
    assert ident["distribution"]["record"]["verified"] == 1
    assert r["plugin"]["entry_point"] == "certify-test"
    assert r["summary"]["level"] == "adapter_implementation"


def test_modified_installed_file_is_reported(tmp_path: Path) -> None:
    site = install(tmp_path / "site")
    with open(site / MODULE_FILE.name, "a") as f:
        f.write("\n# edited after installation\n")
    doc = collect_identity("certify-test", extra_path=[str(site)])
    rec = doc["distribution"]["record"]
    assert rec["mismatched"] == [MODULE_FILE.name] and rec["verified"] == 0
    r = certify(plugin="certify-test", extra_path=(str(site),))
    dist = check(r, "manifest.distribution")
    assert dist["status"] == "warn" and "differ from RECORD" in dist["reason"]


def test_duplicate_entry_point_fails(tmp_path: Path) -> None:
    site = install(tmp_path / "site")
    install(tmp_path / "site", name="another-dist")  # same entry-point name, second dist
    doc = collect_identity("certify-test", extra_path=[str(site)])
    assert doc["entry_point"]["count"] == 2
    r = certify(plugin="certify-test", extra_path=(str(site),))
    assert check(r, "manifest.load")["status"] == "fail"  # the host refuses to choose
    ep = check(r, "manifest.entry_point")
    assert ep["status"] == "fail" and "several distributions" in ep["reason"]


def test_module_reference_hashes_files_without_importing(tmp_path: Path) -> None:
    pkg = tmp_path / "boom_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("raise RuntimeError('imported!')\n")
    doc = collect_identity("boom_pkg:Plugin", extra_path=[str(tmp_path)])
    assert doc["kind"] == "module" and doc["distribution"] is None
    assert doc["module"]["file_count"] == 1 and len(doc["module"]["tree_sha256"]) == 64
    assert not doc["errors"]
