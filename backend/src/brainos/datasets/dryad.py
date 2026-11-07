"""Pinned Dryad datasets: manifest, SHA-256 verification, token-aware download.

    python -m brainos.datasets.dryad --list                  # pinned files and subsets
    python -m brainos.datasets.dryad                         # demo subset (day 468 blocks 0-3)
    python -m brainos.datasets.dryad --subset day468         # all 18 blocks of day 468 (~472 MiB)
    python -m brainos.datasets.dryad --verify                # check files already on disk

Dryad (datadryad.org) serves files to programs only with an API token. Sign in at
datadryad.org, open "My account", create API credentials and generate a token (it is valid
for 10 hours), then ``export DRYAD_TOKEN=...``. For unattended use (CI), set
``DRYAD_CLIENT_ID`` and ``DRYAD_CLIENT_SECRET`` (the API account's credentials) instead and a
token is requested for each run (OAuth client-credentials grant, as Dryad documents).
Alternatively download the files in a browser from the dataset page, put them in
``data/datasets/dryad-prr4xgxzq/`` and run ``--verify``.

Every file is pinned by SHA-256 from the Dryad API listing of the published version; a file
whose digest differs is rejected. Files land in ``data/datasets/dryad-<doi suffix>/``, which is
git-ignored: recordings are never committed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from functools import cache
from importlib import resources
from pathlib import Path

log = logging.getLogger(__name__)

TOKEN_ENV = "DRYAD_TOKEN"
CLIENT_ID_ENV = "DRYAD_CLIENT_ID"
CLIENT_SECRET_ENV = "DRYAD_CLIENT_SECRET"
TOKEN_URL = "https://datadryad.org/oauth/token"


@dataclass(frozen=True, slots=True)
class DryadFile:
    path: str
    file_id: int
    size_bytes: int
    sha256: str
    day: int | None = None
    block: int | None = None
    task: str | None = None

    @property
    def filename(self) -> str:
        return self.path.rsplit("/", 1)[-1]


@dataclass(frozen=True, slots=True)
class DryadManifest:
    id: str
    title: str
    doi: str
    url: str
    api: str
    version_id: int
    license: str
    access: str
    citation: str
    publication: str
    code: str
    species: str
    participant: str
    recording_type: str
    modality: str
    verified_at: str
    files: tuple[DryadFile, ...]

    @property
    def dirname(self) -> str:
        return "dryad-" + self.doi.rsplit(".", 1)[-1]

    def file_url(self, f: DryadFile) -> str:
        return f"{self.api}/files/{f.file_id}/download"

    def by_filename(self, name: str) -> DryadFile | None:
        return next((f for f in self.files if f.filename == name), None)

    def find(self, sha256: str) -> DryadFile | None:
        return next((f for f in self.files if f.sha256 == sha256), None)

    def blocks(self, day: int, task: str | None = None) -> list[DryadFile]:
        return sorted(
            (
                f
                for f in self.files
                if f.day == day and f.block is not None and (task is None or f.task == task)
            ),
            key=lambda f: f.block or 0,
        )


@cache
def manifests() -> tuple[DryadManifest, ...]:
    out = []
    for entry in resources.files(__package__).joinpath("dryad").iterdir():
        if entry.name.endswith(".json"):
            raw = json.loads(entry.read_text(encoding="utf-8"))
            files = tuple(DryadFile(**f) for f in raw.pop("files"))
            out.append(DryadManifest(files=files, **raw))
    return tuple(out)


def manifest(dataset_id: str) -> DryadManifest:
    for m in manifests():
        if m.id == dataset_id:
            return m
    raise KeyError(f"unknown Dryad dataset {dataset_id!r}; known: {[m.id for m in manifests()]}")


# Day 468 (cursor + click): calibration blocks 0-2 train, grid block 3 is held out.
DEMO_BLOCKS = (0, 1, 2, 3)
DEMO_DAY = 468


def subset(m: DryadManifest, name: str) -> list[DryadFile]:
    readme = [f for f in m.files if f.path == "README.md"]
    if name == "demo":
        return readme + [f for f in m.blocks(DEMO_DAY) if f.block in DEMO_BLOCKS]
    if name.startswith("day"):
        return readme + m.blocks(int(name[3:]))
    if name == "all":
        return list(m.files)
    raise ValueError(f"unknown subset {name!r}: demo, day<N> (e.g. day468) or all")


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


@dataclass(frozen=True, slots=True)
class DryadVerification:
    sha256: str
    manifest: DryadManifest | None
    file: DryadFile | None

    @property
    def verified(self) -> bool:
        return self.file is not None

    def describe(self) -> str:
        if self.manifest and self.file:
            return (
                f"SHA-256 matches Dryad doi:{self.manifest.doi} "
                f"(version {self.manifest.version_id}) file {self.file.file_id} ({self.file.path})"
            )
        return "file is not in any pinned Dryad manifest (unverified provenance)"


def verify_file(path: Path) -> DryadVerification:
    digest = sha256_file(path)
    for m in manifests():
        f = m.find(digest)
        if f is not None:
            return DryadVerification(digest, m, f)
    return DryadVerification(digest, None, None)


class DownloadError(RuntimeError):
    pass


def download(m: DryadManifest, f: DryadFile, dest_dir: Path, token: str | None) -> Path:
    """Download one file and verify size and SHA-256; idempotent."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f.filename
    if dest.exists() and dest.stat().st_size == f.size_bytes and sha256_file(dest) == f.sha256:
        log.info("already present and verified: %s", dest.name)
        return dest
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    req = urllib.request.Request(m.file_url(f), headers=headers)
    tmp = dest.with_suffix(dest.suffix + ".part")
    h = hashlib.sha256()
    size = 0
    try:
        with urllib.request.urlopen(req, timeout=300) as resp, tmp.open("wb") as fh:
            while block := resp.read(1 << 20):
                fh.write(block)
                h.update(block)
                size += len(block)
    except urllib.error.HTTPError as exc:
        tmp.unlink(missing_ok=True)
        if exc.code in (401, 403):
            raise DownloadError(
                f"{f.filename}: Dryad refused the download (HTTP {exc.code}). Dryad requires an "
                f"API token for programmatic downloads: set {TOKEN_ENV} (see --help), or download "
                f"the file in a browser from {m.url} and run --verify."
            ) from exc
        raise DownloadError(f"{f.filename}: HTTP {exc.code}") from exc
    if size != f.size_bytes or h.hexdigest() != f.sha256:
        tmp.unlink(missing_ok=True)
        raise DownloadError(
            f"{f.filename}: checksum/size mismatch (got {size} bytes, sha256 {h.hexdigest()}); "
            "the file was discarded"
        )
    tmp.replace(dest)
    return dest


def token_from_env() -> str | None:
    """DRYAD_TOKEN, or a token minted from DRYAD_CLIENT_ID/DRYAD_CLIENT_SECRET, or None."""
    token = os.environ.get(TOKEN_ENV)
    if token:
        return token
    cid, secret = os.environ.get(CLIENT_ID_ENV), os.environ.get(CLIENT_SECRET_ENV)
    if not (cid and secret):
        return None
    body = urllib.parse.urlencode(
        {"grant_type": "client_credentials", "client_id": cid, "client_secret": secret}
    ).encode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            access = json.loads(resp.read()).get("access_token")
    except (urllib.error.URLError, ValueError) as exc:
        raise DownloadError(
            f"could not obtain a Dryad token with the client credentials: {exc}"
        ) from exc
    if not isinstance(access, str) or not access:
        raise DownloadError("Dryad returned no access_token for the client credentials")
    return access


def default_dest(m: DryadManifest) -> Path:
    from brainos.server.settings import REPO_ROOT

    return REPO_ROOT / "data" / "datasets" / m.dirname


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("dataset", nargs="?", default="t15-cursor-click")
    ap.add_argument("--subset", default="demo", help="demo (default), day<N>, or all")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--list", action="store_true", help="list pinned files and exit")
    group.add_argument("--verify", action="store_true", help="verify files on disk, no download")
    ap.add_argument("--dest", type=Path, default=None)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    m = manifest(args.dataset)
    if args.list:
        for f in m.files:
            print(f"{f.size_bytes / 2**20:7.2f} MiB  {f.path}")
        print(f"\nsubsets: demo = README + day {DEMO_DAY} blocks {list(DEMO_BLOCKS)}; day<N>; all")
        return 0
    dest = args.dest or default_dest(m)
    files = subset(m, args.subset)
    print(f"{m.title}\nDryad doi:{m.doi} · {m.license} · {m.url}\n{m.access}\n")
    if args.verify:
        bad = 0
        for f in files:
            p = dest / f.filename
            ok = p.exists() and sha256_file(p) == f.sha256
            bad += not ok
            print(f"  {'verified' if ok else 'MISSING/MISMATCH':16s} {p}")
        return 1 if bad else 0
    try:
        token = token_from_env()
        for f in files:
            print(f"  verified  {download(m, f, dest, token)}")
    except (DownloadError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"\n{len(files)} file(s) ready in {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
