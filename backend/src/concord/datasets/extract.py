"""Stream pinned slices of large DANDI NWB assets into small, verified local NWB extracts.

Some public recordings are far too large to download for a demo (AJILE12: 8-18 GiB per
day-long file). Instead of the whole file, Concord reads only the pinned parts with HTTP range
requests (``remfile`` + ``h5py``), straight from the pinned DANDI asset:

1. the asset's DANDI metadata must still report the pinned SHA-256 and size (DANDI blobs are
   content-addressed: same digest = same bytes), otherwise nothing is read;
2. the sliced ``ElectricalSeries`` samples are read with their stored dtype and attributes and
   their SHA-256 (``data_sha256``: stored values, little-endian, C order) must equal the pinned
   one; the same holds for the pose frames (``pose_sha256``);
3. an NWB file is written to ``data/datasets/dandi-<id>/`` containing exactly that slice, the
   complete electrodes table and electrode groups, the pose frames of the same time range and
   the interval tables overlapping it, all on the ORIGINAL file's timeline (seconds since the
   session start). Its ``notes`` record which asset and sample range it came from.

At load time the importer recomputes ``data_sha256`` from the extract (``verify_slice``), so a
modified extract is reported as unverified. Extracts are research data: never committed
(``data/`` is git-ignored) and not redistributed.

    python -m concord.datasets.extract --pin ajile12   # maintainer: print digests of all slices
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import urllib.request
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

from concord.datasets import (
    DatasetManifest,
    DatasetSlice,
    DownloadError,
    manifest,
    sha256_file,
)
from concord.oscompat import replace

log = logging.getLogger(__name__)

EXTRACT_TAG = "concord_extract"
POSE_PATH = "processing/behavior/Position"
ELECTRODES_PATH = "general/extracellular_ephys/electrodes"
# columns of the electrodes table that are written by pynwb's own arguments
_BUILTIN_COLUMNS = ("x", "y", "z", "imp", "location", "filtering", "group", "group_name", "id")


def data_digest(values: NDArray[Any]) -> str:
    """SHA-256 of an array's stored values: its own dtype, little-endian, C order."""
    arr = np.ascontiguousarray(values)
    le = arr.astype(arr.dtype.newbyteorder("<"), copy=False)
    return hashlib.sha256(np.ascontiguousarray(le).tobytes()).hexdigest()


def pose_digest(pose: dict[str, NDArray[Any]]) -> str:
    h = hashlib.sha256()
    for name in sorted(pose):
        h.update(name.encode())
        arr = np.ascontiguousarray(pose[name])
        h.update(np.ascontiguousarray(arr.astype(arr.dtype.newbyteorder("<"))).tobytes())
    return h.hexdigest()


# ------------------------------------------------------------------ remote access


def asset_content(m: DatasetManifest, asset_path: str) -> tuple[str, str, int]:
    """(S3 URL, SHA-256, size) from DANDI's metadata for the pinned asset id; checked."""
    asset = m.by_path(asset_path)
    if asset is None:
        raise DownloadError(f"{asset_path}: not in manifest {m.id}")
    url = f"{m.api}/assets/{asset.asset_id}/"
    with urllib.request.urlopen(url, timeout=60) as resp:
        meta = json.load(resp)
    digest = meta.get("digest", {}).get("dandi:sha2-256")
    size = int(meta.get("contentSize", -1))
    if digest != asset.sha256 or size != asset.size_bytes:
        raise DownloadError(
            f"{asset_path}: DANDI now reports sha256 {digest} / {size} bytes; pinned "
            f"{asset.sha256} / {asset.size_bytes}. Refusing to read a different file."
        )
    s3 = [u for u in meta.get("contentUrl", []) if "s3.amazonaws.com" in u]
    return (s3[0] if s3 else f"{m.api}/assets/{asset.asset_id}/download/"), digest, size


def open_remote(url: str) -> Any:
    try:
        import h5py
        import remfile
    except ImportError as exc:  # pragma: no cover - depends on install
        raise DownloadError(
            f"streaming needs {exc.name}: pip install 'concordos[nwb]' (remfile, h5py)"
        ) from exc
    return h5py.File(remfile.File(url), "r")


# ------------------------------------------------------------------ slice content


def _s(v: Any) -> str:
    return v.decode() if isinstance(v, bytes) else str(v)


@dataclass
class SliceContent:
    """Everything read from the source for one slice (in memory, before writing)."""

    data: NDArray[Any]  # (samples, channels), stored dtype
    rate: float
    starting_time: float  # of the SLICE (seconds since session start)
    conversion: float
    unit: str
    series_attrs: dict[str, str]
    electrodes: dict[str, NDArray[Any]]  # column -> values (no 'group')
    electrode_descriptions: dict[str, str]
    electrode_ids: NDArray[np.int64]
    groups: list[dict[str, str]]  # name, description, location, device
    group_of: list[str]  # per electrode
    session: dict[str, Any]
    pose: dict[str, NDArray[np.float64]] = field(default_factory=dict)
    pose_rate: float | None = None
    pose_start: float | None = None
    pose_attrs: dict[str, dict[str, Any]] = field(default_factory=dict)
    intervals: dict[str, dict[str, Any]] = field(default_factory=dict)
    reach_events_match_reaches: bool | None = None


def read_slice(f: Any, s: DatasetSlice) -> SliceContent:
    ds = f[s.series + "/data"]
    a, b = s.samples
    if not 0 <= a < b <= ds.shape[0] or ds.ndim != 2 or ds.shape[1] != s.channels:
        raise DownloadError(f"{s.id}: series shape {ds.shape} does not contain slice {s.samples}")
    st = f[s.series + "/starting_time"]
    rate = float(st.attrs["rate"])
    t_start = float(st[()])
    data = ds[a:b, :]
    attrs = {k: _s(v) for k, v in f[s.series].attrs.items() if k in ("description", "comments")}
    el = f[ELECTRODES_PATH]
    cols: dict[str, NDArray[Any]] = {}
    desc: dict[str, str] = {}
    for name, obj in el.items():
        if name in ("group", "id") or getattr(obj, "ndim", 0) != 1:
            continue
        vals = obj[:]
        cols[name] = np.array([_s(v) for v in vals]) if vals.dtype.kind in "OS" else vals
        desc[name] = _s(obj.attrs.get("description", ""))
    groups: list[dict[str, str]] = []
    for name, g in f["general/extracellular_ephys"].items():
        if _s(g.attrs.get("neurodata_type", "")) != "ElectrodeGroup":
            continue
        dev = g.get("device", getlink=True)
        dev_name = _s(dev.path).rsplit("/", 1)[-1] if hasattr(dev, "path") else name
        groups.append(
            {
                "name": name,
                "description": _s(g.attrs.get("description", "")),
                "location": _s(g.attrs.get("location", "unknown")),
                "device": dev_name,
            }
        )
    general = f["general"]
    subject = general.get("subject")
    session = {
        "identifier": _s(f["identifier"][()]),
        "session_description": _s(f["session_description"][()]),
        "session_start_time": _s(f["session_start_time"][()]),
        "session_id": _s(general["session_id"][()]) if "session_id" in general else None,
        "subject_id": _s(subject["subject_id"][()])
        if subject and "subject_id" in subject
        else None,
        "species": _s(subject["species"][()]) if subject and "species" in subject else None,
        "institution": _s(general["institution"][()]) if "institution" in general else None,
    }
    content = SliceContent(
        data=data,
        rate=rate,
        starting_time=t_start + a / rate,
        conversion=float(ds.attrs.get("conversion", 1.0)),
        unit=_s(ds.attrs.get("unit", "")),
        series_attrs=attrs,
        electrodes=cols,
        electrode_descriptions=desc,
        electrode_ids=el["id"][:].astype(np.int64),
        groups=groups,
        group_of=[_s(v) for v in el["group_name"][:]],
        session=session,
    )
    t0, t1 = content.starting_time, t_start + b / rate
    if s.pose_frames is not None and POSE_PATH in f:
        pa, pb = s.pose_frames
        for kp, obj in f[POSE_PATH].items():
            pst = obj["starting_time"]
            content.pose_rate = float(pst.attrs["rate"])
            content.pose_start = float(pst[()]) + pa / content.pose_rate
            content.pose[kp] = obj["data"][pa:pb, :]
            content.pose_attrs[kp] = {
                "unit": _s(obj["data"].attrs.get("unit", "")),
                "conversion": float(obj["data"].attrs.get("conversion", np.nan)),
                "reference_frame": _s(obj["reference_frame"][()])
                if "reference_frame" in obj
                else "",
                "description": _s(obj.attrs.get("description", "")),
            }
    for name, tab in f.get("intervals", {}).items():
        start, stop = tab["start_time"][:], tab["stop_time"][:]
        keep = np.flatnonzero((stop > t0) & (start < t1))
        cols_i: dict[str, Any] = {"__description__": _s(tab.attrs.get("description", ""))}
        for c, obj in tab.items():
            if c == "id" or getattr(obj, "ndim", 0) != 1 or obj.shape[0] != start.shape[0]:
                continue
            vals = obj[:][keep]
            cols_i[c] = (
                [_s(v) for v in vals] if vals.dtype.kind in "OS" else np.asarray(vals).tolist()
            )
            cols_i[f"__desc__{c}"] = _s(obj.attrs.get("description", ""))
        content.intervals[name] = cols_i
    ev = "processing/behavior/ReachEvents/timestamps"
    if ev in f and "reaches" in content.intervals:
        ts = f[ev][:]
        rs = np.asarray(f["intervals/reaches/start_time"][:])
        content.reach_events_match_reaches = bool(
            ts.shape == rs.shape and np.allclose(np.sort(ts), np.sort(rs), atol=1e-6)
        )
    return content


# ------------------------------------------------------------------ writing


def write_extract(
    content: SliceContent, m: DatasetManifest, s: DatasetSlice, path: Path, origin_sha256: str
) -> None:
    from hdmf.backends.hdf5.h5_utils import H5DataIO
    from pynwb import NWBHDF5IO, NWBFile
    from pynwb.behavior import Position, SpatialSeries
    from pynwb.ecephys import ElectricalSeries
    from pynwb.epoch import TimeIntervals
    from pynwb.file import Subject

    sess = content.session
    a, b = s.samples
    provenance = {
        EXTRACT_TAG: {
            "dataset": m.id,
            "dandiset": m.dandiset,
            "version": m.version,
            "asset_path": s.asset_path,
            "asset_sha256": origin_sha256,
            "slice_id": s.id,
            "series": s.series,
            "samples": [a, b],
            "pose_frames": list(s.pose_frames) if s.pose_frames else None,
            "data_sha256": data_digest(content.data),
            "pose_sha256": pose_digest(content.pose) if content.pose else None,
            "original_identifier": sess["identifier"],
            "reach_events_equal_reaches_start_time": content.reach_events_match_reaches,
            "note": "Times are seconds since the ORIGINAL session start. Written by Concord "
            "from HTTP range reads of the pinned asset; not an official DANDI file.",
        }
    }
    nwb = NWBFile(
        session_description=sess["session_description"] or "no description",
        identifier=f"{sess['identifier']}:concord-extract:{s.id}",
        session_start_time=datetime.fromisoformat(sess["session_start_time"]),
        session_id=sess["session_id"],
        subject=Subject(subject_id=sess["subject_id"], species=sess["species"])
        if sess["subject_id"] or sess["species"]
        else None,
        institution=sess["institution"],
        notes=json.dumps(provenance),
        source_script="concord.datasets.extract",
        source_script_file_name="concord/datasets/extract.py",
    )
    groups = {}
    for g in content.groups:
        dev = (
            nwb.devices[g["device"]]
            if g["device"] in nwb.devices
            else nwb.create_device(name=g["device"])
        )
        groups[g["name"]] = nwb.create_electrode_group(
            name=g["name"], description=g["description"], location=g["location"], device=dev
        )
    custom = [c for c in content.electrodes if c not in _BUILTIN_COLUMNS]
    for c in custom:
        nwb.add_electrode_column(name=c, description=content.electrode_descriptions.get(c) or c)
    cols = content.electrodes
    for i, eid in enumerate(content.electrode_ids):
        kw: dict[str, Any] = {c: cols[c][i].item() for c in custom}
        for c in ("x", "y", "z", "imp"):
            if c in cols:
                kw[c] = float(cols[c][i])
        nwb.add_electrode(
            group=groups[content.group_of[i]],
            location=str(cols["location"][i]) if "location" in cols else "unknown",
            filtering=str(cols["filtering"][i]) if "filtering" in cols else None,
            id=int(eid),
            **kw,
        )
    region = nwb.create_electrode_table_region(
        region=list(range(len(content.electrode_ids))), description="all electrodes"
    )
    nwb.add_acquisition(
        ElectricalSeries(
            name=s.series.rsplit("/", 1)[-1],
            data=H5DataIO(content.data, compression="gzip", chunks=(min(4096, b - a), 1)),
            electrodes=region,
            starting_time=content.starting_time,
            rate=content.rate,
            conversion=content.conversion,
            description=content.series_attrs.get("description", "no description"),
            comments=content.series_attrs.get("comments", "no comments"),
        )
    )
    if content.pose and content.pose_rate is not None and content.pose_start is not None:
        module = nwb.create_processing_module(name="behavior", description="pose data")
        series = []
        for kp in sorted(content.pose):
            at = content.pose_attrs[kp]
            series.append(
                SpatialSeries(
                    name=kp,
                    data=H5DataIO(content.pose[kp], compression="gzip"),
                    reference_frame=at["reference_frame"] or "unknown",
                    unit=at["unit"] or "meters",
                    conversion=at["conversion"],
                    starting_time=content.pose_start,
                    rate=content.pose_rate,
                    description=at["description"] or "no description",
                )
            )
        module.add(Position(spatial_series=series))
    for name, tab in content.intervals.items():
        n = len(tab["start_time"])
        cols_i = [c for c in tab if not c.startswith("__") and c not in ("start_time", "stop_time")]
        if name == "epochs":
            for c in cols_i:
                nwb.add_epoch_column(name=c, description=tab.get(f"__desc__{c}") or c)
            for i in range(n):
                nwb.add_epoch(
                    start_time=tab["start_time"][i],
                    stop_time=tab["stop_time"][i],
                    **{c: tab[c][i] for c in cols_i},
                )
            continue
        ti = TimeIntervals(name=name, description=tab["__description__"] or name)
        for c in cols_i:
            ti.add_column(name=c, description=tab.get(f"__desc__{c}") or c)
        for i in range(n):
            ti.add_row(
                start_time=tab["start_time"][i],
                stop_time=tab["stop_time"][i],
                **{c: tab[c][i] for c in cols_i},
            )
        nwb.add_time_intervals(ti)
    tmp = path.with_suffix(".part")  # not *.nwb: never picked up by the catalog half-written
    tmp.unlink(missing_ok=True)
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*does not end in '.nwb'.*")
        with NWBHDF5IO(str(tmp), "w") as io:
            io.write(nwb)
    replace(tmp, path)  # retried on Windows while a virus scanner holds the new file


# ------------------------------------------------------------------ public entry points


def extract_digest(path: Path) -> tuple[str, dict[str, Any] | None]:
    """(data_sha256 of the extract's sliced series, its provenance note) — no pynwb needed."""
    import h5py

    with h5py.File(path, "r") as f:
        notes = _s(f["general/notes"][()]) if "general/notes" in f else ""
        try:
            prov = json.loads(notes).get(EXTRACT_TAG) if notes.startswith("{") else None
        except ValueError:
            prov = None
        series = (prov or {}).get("series", "acquisition/ElectricalSeries")
        if series + "/data" not in f:
            return "", prov
        return data_digest(f[series + "/data"][:]), prov


def fetch_slice(m: DatasetManifest, s: DatasetSlice, dest_dir: Path) -> Path:
    """Stream one pinned slice and write its verified extract (idempotent)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    path = dest_dir / s.filename
    if path.exists():
        digest, _ = extract_digest(path)
        if digest == s.data_sha256:
            log.info("already present and verified: %s", path.name)
            return path
        log.warning("%s exists but does not match the pinned slice; re-fetching", path.name)
    url, sha, _size = asset_content(m, s.asset_path)
    log.info("streaming %s samples %s from %s", s.asset_path, s.samples, url)
    with open_remote(url) as f:
        content = read_slice(f, s)
    got = data_digest(content.data)
    if got != s.data_sha256:
        raise DownloadError(f"{s.id}: sliced data sha256 {got} != pinned {s.data_sha256}")
    if s.pose_sha256 is not None and pose_digest(content.pose) != s.pose_sha256:
        raise DownloadError(f"{s.id}: pose frames do not match the pinned digest")
    write_extract(content, m, s, path, sha)
    digest, _ = extract_digest(path)
    if digest != s.data_sha256:  # the written file must hold exactly the pinned values
        path.unlink(missing_ok=True)
        raise DownloadError(f"{s.id}: written extract does not reproduce the pinned data")
    log.info("wrote %s (%.1f MiB)", path.name, path.stat().st_size / 2**20)
    return path


def pin(dataset_id: str) -> list[dict[str, Any]]:
    """Maintainer tool: read every slice of a manifest and report the digests to pin."""
    m = manifest(dataset_id)
    out = []
    for s in m.slices:
        url, _sha, _ = asset_content(m, s.asset_path)
        with open_remote(url) as f:
            c = read_slice(f, s)
        out.append(
            {
                "id": s.id,
                "data_sha256": data_digest(c.data),
                "pose_sha256": pose_digest(c.pose) if c.pose else None,
                "shape": list(c.data.shape),
                "dtype": str(c.data.dtype),
                "nan": int(np.isnan(c.data).sum()) if c.data.dtype.kind == "f" else 0,
                "reaches": len(c.intervals.get("reaches", {}).get("start_time", [])),
                "reach_events_match": c.reach_events_match_reaches,
            }
        )
        print(json.dumps(out[-1]), flush=True)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--pin", metavar="DATASET", required=True)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        pin(args.pin)
    except (DownloadError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


__all__ = [
    "data_digest",
    "extract_digest",
    "fetch_slice",
    "pose_digest",
    "sha256_file",
]

if __name__ == "__main__":
    raise SystemExit(main())
