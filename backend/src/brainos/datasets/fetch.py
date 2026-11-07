"""Download pinned dataset files with checksum verification.

    python -m brainos.datasets.fetch                 # demo set (2 blocks, ~8.7 MiB)
    python -m brainos.datasets.fetch --all-calib     # all 13 held-in calibration blocks (~66 MiB)
    python -m brainos.datasets.fetch --list          # show what is available

Files land in data/datasets/dandi-<id>/ (git-ignored). Each file's SHA-256 is checked
against the pinned manifest; a mismatch is an error and the file is discarded.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from brainos.datasets import DatasetAsset, DownloadError, download_asset, manifest
from brainos.server.settings import REPO_ROOT

# Two recording blocks from the same day: one to train the decoder, one held out.
DEMO_FILES = (
    "sub-HumanPitt-held-in-calib_ses-19250108T110520.nwb",
    "sub-HumanPitt-held-in-calib_ses-19250108T111022.nwb",
)


def default_dest(dandiset: str) -> Path:
    return REPO_ROOT / "data" / "datasets" / f"dandi-{dandiset}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("dataset", nargs="?", default="falcon-h1")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--all-calib", action="store_true", help="all held-in calibration blocks")
    group.add_argument("--list", action="store_true", help="list pinned assets and exit")
    ap.add_argument("--dest", type=Path, default=None)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    m = manifest(args.dataset)
    if args.list:
        for a in m.assets:
            print(f"{a.size_bytes / 2**20:6.2f} MiB  {a.split:16s}  {a.filename}")
        return 0
    assets: list[DatasetAsset]
    if args.all_calib:
        assets = [a for a in m.assets if a.split == "held-in-calib"]
    else:
        assets = [a for a in m.assets if a.filename in DEMO_FILES]
    dest = args.dest or default_dest(m.dandiset)
    print(f"{m.title}\nDANDI {m.dandiset} ({m.version}) · {m.license} · {m.url}")
    print(f"By downloading you agree to the dataset's terms: {m.access}\n")
    try:
        for a in assets:
            path = download_asset(m, a, dest)
            print(f"  verified  {path}")
    except (DownloadError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"\n{len(assets)} file(s) ready in {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
