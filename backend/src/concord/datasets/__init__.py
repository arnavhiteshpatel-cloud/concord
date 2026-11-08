"""Verified public datasets: pinned manifests, checksum verification, download.

A manifest pins every asset by DANDI asset id and SHA-256 so a file on disk can be
proven to be the published recording (DANDI drafts can change; checksums cannot).
Recordings themselves are never committed to git (``data/`` is ignored).

Large assets (Milestone 5, e.g. AJILE12 ECoG: 8-18 GiB per file) are not downloaded whole:
a manifest may pin **slices** (exact sample ranges of one series of one asset). The slice is
streamed with HTTP range requests from the pinned asset and written to a local NWB extract;
the slice is pinned by the SHA-256 of its raw stored values (``data_sha256``), which Concord
recomputes from the extract at load time (see ``datasets/extract.py``).
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
class DatasetSlice:
    """An exact, pinned part of one asset, stored locally as an NWB extract (M5)."""

    id: str
    asset_path: str
    filename: str  # local extract file name
    role: str  # "train" | "test": how Concord's own evaluation uses it (sessions never mix)
    demo: bool  # part of the small default download
    series: str  # HDF5 path of the sliced series, e.g. "acquisition/ElectricalSeries"
    samples: tuple[int, int]  # [start, stop) sample indices of ``series``
    channels: int
    data_sha256: str  # SHA-256 of the slice's stored values (file dtype, little-endian, C order)
    pose_frames: tuple[int, int] | None = None  # [start, stop) frames of the pose series
    pose_sha256: str | None = None
    note: str = ""

    @property
    def session(self) -> str | None:
        return session_of(self.filename)


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
    # Milestone 5 (all optional): declared recording modality (contract ``Modality`` value),
    # mains frequency of the recording site, pinned slices of large assets, dataset notes.
    modality: str | None = None
    line_hz: float | None = None
    slices: tuple[DatasetSlice, ...] = ()
    notes: tuple[str, ...] = ()

    def asset_url(self, asset: DatasetAsset) -> str:
        return f"{self.api}/assets/{asset.asset_id}/download/"

    def find(self, sha256: str) -> DatasetAsset | None:
        return next((a for a in self.assets if a.sha256 == sha256), None)

    def by_filename(self, filename: str) -> DatasetAsset | None:
        return next((a for a in self.assets if a.filename == filename), None)

    def by_path(self, path: str) -> DatasetAsset | None:
        return next((a for a in self.assets if a.path == path), None)

    def find_slice(self, data_sha256: str) -> DatasetSlice | None:
        return next((s for s in self.slices if s.data_sha256 == data_sha256), None)


# M5 P0: cursor + click blocks (Dryad); the leakage unit is the block (train and test blocks
# share a day, as for the original online decoder, never a block)
BLOCK_RE = re.compile(r"(t\d+)_day(\d+)_block(\d+)_")


def session_of(filename: str) -> str | None:
    m = SESSION_RE.search(filename)
    if m:
        return m.group(1)
    b = BLOCK_RE.search(filename)
    return f"{b.group(1)}-day{int(b.group(2)):05d}-block{int(b.group(3)):02d}" if b else None


@cache
def manifests() -> tuple[DatasetManifest, ...]:
    out = []
    for entry in resources.files(__package__).iterdir():
        if not entry.name.endswith(".json"):
            continue
        raw = json.loads(entry.read_text(encoding="utf-8"))
        assets = tuple(DatasetAsset(**a) for a in raw.pop("assets"))
        slices = tuple(_slice(s) for s in raw.pop("slices", []))
        notes = tuple(raw.pop("notes", []))
        out.append(DatasetManifest(assets=assets, slices=slices, notes=notes, **raw))
    return tuple(out)


def _slice(raw: dict[str, object]) -> DatasetSlice:
    d = dict(raw)
    samples = d.pop("samples")
    frames = d.pop("pose_frames", None)
    assert isinstance(samples, list) and len(samples) == 2
    return DatasetSlice(
        samples=(int(samples[0]), int(samples[1])),
        pose_frames=(int(frames[0]), int(frames[1])) if isinstance(frames, list) else None,
        **d,  # type: ignore[arg-type]
    )


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
    # M5: set when the file is a local extract whose sliced data matches a pinned slice
    slice: DatasetSlice | None = None

    @property
    def verified(self) -> bool:
        return self.asset is not None

    def describe(self) -> str:
        if self.manifest and self.asset and self.slice:
            a, b = self.slice.samples
            return (
                f"Extract: SHA-256 of {self.slice.series} samples [{a}, {b}) matches the slice "
                f"pinned from DANDI {self.manifest.dandiset} asset {self.asset.asset_id} "
                f"({self.asset.path}, full-file SHA-256 {self.asset.sha256[:12]}…)"
            )
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


def verify_slice(file_sha256: str, data_sha256: str) -> Verification:
    """A local extract is verified when the digest of its sliced data equals a pinned slice."""
    for m in manifests():
        s = m.find_slice(data_sha256)
        if s is not None:
            return Verification(file_sha256, m, m.by_path(s.asset_path), s)
    return Verification(file_sha256, None, None)


def find_slice_by_filename(filename: str) -> tuple[DatasetManifest, DatasetSlice] | None:
    for m in manifests():
        for s in m.slices:
            if s.filename == filename:
                return m, s
    return None


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
