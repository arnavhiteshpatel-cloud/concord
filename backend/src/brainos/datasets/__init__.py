"""Verified public datasets: pinned manifests, checksum verification, download.

A manifest pins every asset by DANDI asset id and SHA-256 so a file on disk can be
proven to be the published recording (DANDI drafts can change; checksums cannot).
Recordings themselves are never committed to git (``data/`` is ignored).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import urllib.request
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path

log = logging.getLogger(__name__)

SESSION_RE = re.compile(r"_ses-([0-9T]+)")


@dataclass(frozen=True, slots=True)
class DatasetAsset:
    path: str
    asset_id: str
    size_bytes: int
    sha256: str

    @property
    def filename(self) -> str:
        return self.path.rsplit("/", 1)[-1]

    @property
    def session(self) -> str | None:
        return session_of(self.filename)

    @property
    def split(self) -> str:
        """e.g. 'held-in-calib' or 'held-in-minival'."""
        m = re.search(r"sub-HumanPitt-([a-z\-]+)", self.filename)
        return m.group(1) if m else "unknown"


@dataclass(frozen=True, slots=True)
class DatasetManifest:
    id: str
    title: str
    dandiset: str
    version: str
    url: str
    api: str
    license: str
    access: str
    citation: str
    species: str
    recording_type: str
    verified_at: str
    assets: tuple[DatasetAsset, ...]

    def asset_url(self, asset: DatasetAsset) -> str:
        return f"{self.api}/assets/{asset.asset_id}/download/"

    def find(self, sha256: str) -> DatasetAsset | None:
        return next((a for a in self.assets if a.sha256 == sha256), None)

    def by_filename(self, filename: str) -> DatasetAsset | None:
        return next((a for a in self.assets if a.filename == filename), None)


def session_of(filename: str) -> str | None:
    m = SESSION_RE.search(filename)
    return m.group(1) if m else None


@cache
def manifests() -> tuple[DatasetManifest, ...]:
    out = []
    for entry in resources.files(__package__).iterdir():
        if not entry.name.endswith(".json"):
            continue
        raw = json.loads(entry.read_text(encoding="utf-8"))
        assets = tuple(DatasetAsset(**a) for a in raw.pop("assets"))
        out.append(DatasetManifest(assets=assets, **raw))
    return tuple(out)


def manifest(dataset_id: str) -> DatasetManifest:
    for m in manifests():
        if m.id == dataset_id:
            return m
    raise KeyError(f"unknown dataset {dataset_id!r}; known: {[m.id for m in manifests()]}")


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


@dataclass(frozen=True, slots=True)
class Verification:
    sha256: str
    manifest: DatasetManifest | None
    asset: DatasetAsset | None

    @property
    def verified(self) -> bool:
        return self.asset is not None

    def describe(self) -> str:
        if self.manifest and self.asset:
            return (
                f"SHA-256 matches DANDI {self.manifest.dandiset} asset {self.asset.asset_id} "
                f"({self.asset.path})"
            )
        return "file is not in any pinned dataset manifest (unverified provenance)"


def verify_file(path: Path) -> Verification:
    digest = sha256_file(path)
    for m in manifests():
        asset = m.find(digest)
        if asset is not None:
            return Verification(digest, m, asset)
    return Verification(digest, None, None)


class DownloadError(RuntimeError):
    pass


def download_asset(m: DatasetManifest, asset: DatasetAsset, dest_dir: Path) -> Path:
    """Download one asset, verifying size and SHA-256; idempotent."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / asset.filename
    if (
        dest.exists()
        and dest.stat().st_size == asset.size_bytes
        and sha256_file(dest) == asset.sha256
    ):
        log.info("already present and verified: %s", dest.name)
        return dest
    tmp = dest.with_suffix(dest.suffix + ".part")
    url = m.asset_url(asset)
    log.info("downloading %s (%.1f MiB)", asset.filename, asset.size_bytes / 2**20)
    h = hashlib.sha256()
    size = 0
    with urllib.request.urlopen(url, timeout=120) as resp, tmp.open("wb") as fh:
        while block := resp.read(1 << 20):
            fh.write(block)
            h.update(block)
            size += len(block)
    if size != asset.size_bytes or h.hexdigest() != asset.sha256:
        tmp.unlink(missing_ok=True)
        raise DownloadError(
            f"{asset.filename}: checksum/size mismatch (got {size} bytes, sha256 {h.hexdigest()})"
        )
    tmp.replace(dest)
    return dest
