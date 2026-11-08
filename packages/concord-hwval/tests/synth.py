"""Synthetic fixtures for edge cases real reference software cannot be made to produce.

The writers follow the published formats and are themselves checked by independent readers in
the tests: XDF files by pyxdf, Open Ephys Binary recordings by the official
open-ephys-python-tools reader (REF-READER), Concord recordings by Concord's own contract
models (CONCORD-FILE). They are used for *defect injection*; the evidence that the toolkit works
on real files comes from the LabRecorder and Open Ephys GUI tests.
"""

from __future__ import annotations

import json
import struct
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import numpy as np
from numpy.typing import NDArray

from concord_hwval.testsignal import make_block

SCHEMA = "1.4"
SESSION = "ses_synthetic01"

# ------------------------------------------------------------------------------- XDF writer

_FMT = {"float32": "<f4", "double64": "<f8", "int16": "<i2", "int32": "<i4"}


def _varlen(n: int) -> bytes:
    if n < 256:
        return b"\x01" + struct.pack("<B", n)
    if n < 2**32:
        return b"\x04" + struct.pack("<I", n)
    return b"\x08" + struct.pack("<Q", n)


def _chunk(tag: int, content: bytes) -> bytes:
    body = struct.pack("<H", tag) + content
    return _varlen(len(body)) + body


@dataclass
class XStream:
    name: str
    values: NDArray[Any]  # (n, channels)
    stamps: NDArray[np.float64]
    srate: float
    stype: str = "EEG"
    fmt: str = "float32"
    source_id: str = "sid"
    hostname: str = "testhost"
    uid: str = field(default_factory=lambda: str(uuid.uuid4()))
    labels: list[str] | None = None
    units: list[str] | None = None
    declaration: dict[str, str] | None = None
    clock: list[tuple[float, float]] = field(default_factory=list)  # (time, offset)


def write_xdf(path: Path, streams: list[XStream], chunk: int = 50) -> None:
    out = bytearray(b"XDF:")
    out += _chunk(1, b'<?xml version="1.0"?><info><version>1.0</version></info>')
    for sid, s in enumerate(streams, start=1):
        nch = s.values.shape[1]
        chans = ""
        if s.labels is not None:
            for i, lab in enumerate(s.labels):
                unit = f"<unit>{escape(s.units[i])}</unit>" if s.units else ""
                chans += f"<channel><label>{escape(lab)}</label>{unit}<type>EEG</type></channel>"
        decl = ""
        if s.declaration:
            decl = (
                "<concord>"
                + "".join(f"<{k}>{v}</{k}>" for k, v in s.declaration.items())
                + "</concord>"
            )
        xml = (
            f'<?xml version="1.0"?><info><name>{escape(s.name)}</name><type>{s.stype}</type>'
            f"<channel_count>{nch}</channel_count><nominal_srate>{s.srate}</nominal_srate>"
            f"<channel_format>{s.fmt}</channel_format><source_id>{s.source_id}</source_id>"
            f"<version>1.1</version><created_at>1.0</created_at><uid>{s.uid}</uid>"
            f"<session_id>default</session_id><hostname>{s.hostname}</hostname>"
            f"<desc>{'<channels>' + chans + '</channels>' if chans else ''}{decl}</desc></info>"
        )
        out += _chunk(2, struct.pack("<I", sid) + xml.encode())
    for sid, s in enumerate(streams, start=1):
        dt = np.dtype(_FMT[s.fmt])
        ci = 0
        clocks = sorted(s.clock)
        for a in range(0, len(s.stamps), chunk):
            b = min(a + chunk, len(s.stamps))
            body = bytearray(struct.pack("<I", sid))
            body += _varlen(b - a)
            for i in range(a, b):
                body += b"\x08" + struct.pack("<d", s.stamps[i])
                body += np.asarray(s.values[i], dtype=dt).tobytes()
            out += _chunk(3, bytes(body))
            while ci < len(clocks) and (b == len(s.stamps) or clocks[ci][0] <= s.stamps[b - 1]):
                t, v = clocks[ci]
                out += _chunk(4, struct.pack("<Idd", sid, t, v))
                ci += 1
    for sid, s in enumerate(streams, start=1):
        n = len(s.stamps)
        xml = (
            f'<?xml version="1.0"?><info><first_timestamp>{s.stamps[0] if n else 0}'
            f"</first_timestamp><last_timestamp>{s.stamps[-1] if n else 0}</last_timestamp>"
            f"<sample_count>{n}</sample_count></info>"
        )
        out += _chunk(6, struct.pack("<I", sid) + xml.encode())
    path.write_bytes(bytes(out))


# ---------------------------------------------------------------------- Concord recordings


def _env(
    seq: int,
    did: str,
    t_wall: int,
    t_dev: int | None,
    event_type: str,
    cap: str,
    payload: dict[str, Any],
    prov: dict[str, Any],
    flags: list[str],
) -> dict[str, Any]:
    q = {"score": 0.5 if "dropped_samples" in flags else 1.0, "flags": flags}
    return {
        "schema_version": SCHEMA,
        "session_id": SESSION,
        "device_id": did,
        "seq": seq,
        "timestamp_ns": t_wall,
        "device_timestamp_ns": t_dev,
        "capability": cap,
        "quality": q,
        "provenance": prov,
        "event_type": event_type,
        "payload": payload,
    }


@dataclass
class BFrame:
    index: int
    data: NDArray[np.float64]  # (n, channels)
    t_dev_ns: int | None
    t_wall_ns: int
    flags: list[str] = field(default_factory=list)
    unit: str = "uV"
    rate: float | None = None


def write_concord(
    path: Path,
    device: dict[str, Any],
    frames: Iterable[BFrame],
    rate: float,
    prov: dict[str, Any],
    annotations: Iterable[tuple[int, int, str, Any]] = (),
    header_extra: dict[str, Any] | None = None,
) -> None:
    """``annotations``: (t_wall_ns, t_dev_ns, label, value) — emitted in time order.
    ``header_extra``: optional header fields (e.g. ``source_metadata``, Concord >= M5)."""
    header = {
        "format": "concord.recording/1",
        "schema_version": SCHEMA,
        "created_at_ns": 1_700_000_000_000_000_000,
        "device": device,
        "synthetic": bool(device.get("synthetic")),
        "note": "",
        **(header_extra or {}),
    }
    items: list[tuple[int, int, dict[str, Any]]] = []
    for f in frames:
        payload = {
            "sample_rate_hz": f.rate or rate,
            "channel_count": int(f.data.shape[1]),
            "first_sample_index": f.index,
            "unit": f.unit,
            "samples": f.data.T.tolist(),
        }
        items.append(
            (
                f.t_dev_ns or 0,
                0,
                {
                    "event_type": "recording.frame",
                    "cap": "recording",
                    "payload": payload,
                    "t_wall": f.t_wall_ns,
                    "t_dev": f.t_dev_ns,
                    "flags": f.flags,
                    "kind": "raw_signal",
                },
            )
        )
    for tw, td, label, value in annotations:
        items.append(
            (
                td,
                1,
                {
                    "event_type": "recording.annotation",
                    "cap": "recording",
                    "payload": {"label": label, "value": value, "duration_ms": None},
                    "t_wall": tw,
                    "t_dev": td,
                    "flags": [],
                    "kind": "behavioral_label",
                },
            )
        )
    if any(k == 1 for _, k, _ in items):  # interleave annotations by device time
        items.sort(key=lambda x: (x[0], x[1]))
    did = device["device_id"]
    lines = [json.dumps(header)]
    for seq, (_, _, it) in enumerate(items):
        p = dict(prov, kind=it["kind"])
        lines.append(
            json.dumps(
                _env(
                    seq,
                    did,
                    it["t_wall"],
                    it["t_dev"],
                    it["event_type"],
                    it["cap"],
                    it["payload"],
                    p,
                    it["flags"],
                )
            )
        )
    path.write_text("\n".join(lines) + "\n")


def lsl_device(
    name: str,
    stype: str,
    host: str,
    sid: str | None,
    labels: list[str],
    rate: float,
    unit: str = "uV",
    fmt: str = "float32",
    synthetic: bool = False,
) -> dict[str, Any]:
    params = {
        "channel_count": len(labels),
        "sample_rate_hz": rate,
        "unit": unit,
        "channel_labels": labels,
        "stream_type": stype,
        "channel_format": fmt,
    }
    return {
        "device_id": f"lsl:{sid or name}",
        "display_name": f"LSL · {name} ({stype})" + (" — declared synthetic" if synthetic else ""),
        "kind": "simulated" if synthetic else "stream",
        "adapter": "concord.lsl@0.1.0",
        "description": f"Lab Streaming Layer stream {name!r} from {host} "
        f"(source_id {sid or 'not set'}). Origin as declared by the publisher.",
        "native_format": f"LSL {fmt} x {len(labels)} @ {rate:g} Hz",
        "capabilities": [
            {"capability": "recording", "params": params, "description": "LSL signal stream"},
            {"capability": "device_status"},
        ],
        "synthetic": synthetic,
    }


def lsl_provenance(name: str, host: str, synthetic: bool = False) -> dict[str, Any]:
    return {
        "adapter": "concord.lsl@0.1.0",
        "synthetic": synthetic,
        "origin": f"lsl:{name}@{host}",
        "replayed": False,
    }


@dataclass
class LSLCase:
    """A synthetic LSL session: the source, the XDF and a perfect Concord recording."""

    rate: float = 500.0
    channels: int = 4
    seconds: float = 12.0
    t0: float = 1000.0
    frame: int = 25
    concord_start: int = 250  # Concord connected later than LabRecorder
    concord_stop_before_end: int = 100
    name: str = "synth-eeg"
    host: str = "testhost"
    sid: str = "synth-sid"
    units: str = "microvolts"
    seed: int = 7
    fmt: str = "float32"

    def __post_init__(self) -> None:
        n = int(self.seconds * self.rate)
        self.n = n
        self.values: NDArray[Any] = make_block(0, n, self.channels, self.rate, self.seed)
        self.stamps = self.t0 + np.arange(n) / self.rate
        self.labels = [f"C{i + 1}" for i in range(self.channels)]

    def xstream(self, **kw: Any) -> XStream:
        args: dict[str, Any] = dict(
            name=self.name,
            values=self.values,
            stamps=self.stamps,
            srate=self.rate,
            source_id=self.sid,
            hostname=self.host,
            labels=self.labels,
            units=[self.units] * self.channels,
            fmt=self.fmt,
            clock=[(self.t0 + 5.0 * k + 0.01, 0.0) for k in range(int(self.seconds / 5) + 1)],
        )
        args.update(kw)
        return XStream(**args)

    def frames(self) -> list[BFrame]:
        out = []
        scale = {"millivolts": 1e3, "volts": 1e6}.get(self.units, 1.0)
        for a in range(self.concord_start, self.n - self.concord_stop_before_end, self.frame):
            b = min(a + self.frame, self.n - self.concord_stop_before_end)
            data = self.values[a:b].astype(np.float64) * scale
            t_dev = round(float(self.stamps[a]) * 1e9)
            # emitted 4 ms after the frame's last sample (+ jitter)
            t_wall = 1_700_000_000_000_000_000 + round(
                (float(self.stamps[b - 1]) + 0.004 + 0.0005 * (a % 3)) * 1e9
            )
            out.append(BFrame(a - self.concord_start, data, t_dev, t_wall))
        return out

    def device(self, **kw: Any) -> dict[str, Any]:
        args: dict[str, Any] = dict(
            name=self.name,
            stype="EEG",
            host=self.host,
            sid=self.sid,
            labels=self.labels,
            rate=self.rate,
            fmt=self.fmt,
        )
        args.update(kw)
        return lsl_device(**args)

    def write(
        self,
        root: Path,
        *,
        xstream: XStream | None = None,
        frames: list[BFrame] | None = None,
        device: dict[str, Any] | None = None,
        prov: dict[str, Any] | None = None,
        header_extra: dict[str, Any] | None = None,
    ) -> tuple[Path, Path]:
        x = root / "ref.xdf"
        b = root / "run.concord.jsonl"
        write_xdf(x, [xstream or self.xstream()])
        write_concord(
            b,
            device or self.device(),
            frames if frames is not None else self.frames(),
            self.rate,
            prov or lsl_provenance(self.name, self.host),
            header_extra=header_extra,
        )
        return x, b


# ------------------------------------------------------------------- Open Ephys Binary writer


def write_oe_binary(
    root: Path,
    samples_i16: NDArray[np.int16],
    sample_numbers: NDArray[Any],
    rate: float,
    names: list[str],
    bit_volts: float = 0.195,
    stream: str = "example_data",
    source: str = "Acquisition Board",
    history: str | None = "Acquisition Board -> ZMQ Interface -> Record Node",
    ttl: tuple[NDArray[Any], NDArray[Any], NDArray[Any]] | None = None,
    gui_version: str = "1.1.0",
    units: str = "uV",
) -> Path:
    """Write ``Record Node 101/experiment1/recording1`` in the GUI's Binary layout."""
    rec = root / "Record Node 101" / "experiment1" / "recording1"
    folder = f"{source.replace(' ', '_')}-100.{stream}"
    cdir = rec / "continuous" / folder
    cdir.mkdir(parents=True, exist_ok=True)
    np.ascontiguousarray(samples_i16, dtype="<i2").tofile(cdir / "continuous.dat")
    legacy = float(".".join(gui_version.split(".")[:2])) < 0.6
    sn = np.asarray(sample_numbers, dtype=np.int64)
    if legacy:
        np.save(cdir / "timestamps.npy", sn)
    else:
        np.save(cdir / "sample_numbers.npy", sn)
        np.save(cdir / "timestamps.npy", sn / rate)
    chans = [
        {
            "channel_name": n,
            "description": "",
            "identifier": "",
            "history": history or "",
            "bit_volts": bit_volts,
            "units": units,
            "type": 0,
        }
        for n in names
    ]
    if history is None:
        for c in chans:
            del c["history"]
    cont = {
        "folder_name": folder + "/",
        "sample_rate": rate,
        "source_processor_name": source,
        "source_processor_id": 100,
        "stream_name": stream,
        "recorded_processor": "Record Node",
        "recorded_processor_id": 101,
        "num_channels": len(names),
        "channels": chans,
    }
    if legacy:  # GUI 0.5.x: streams are sub-processor indices, no stream_name
        del cont["stream_name"]
        cont["source_processor_sub_idx"] = 0
    events = []
    edir = rec / "events" / folder / "TTL"
    edir.mkdir(parents=True, exist_ok=True)
    if ttl is None:
        ttl = (np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0, np.int64))
    tsn, lines, rising = ttl
    states = (np.asarray(lines) + 1) * np.where(np.asarray(rising) > 0, 1, -1)
    if legacy:
        np.save(edir / "channel_states.npy", states.astype(np.int16))
        np.save(edir / "timestamps.npy", np.asarray(tsn, dtype=np.int64))
    else:
        np.save(edir / "states.npy", states.astype(np.int16))
        np.save(edir / "sample_numbers.npy", np.asarray(tsn, dtype=np.int64))
        np.save(edir / "timestamps.npy", np.asarray(tsn, dtype=np.float64) / rate)
    np.save(edir / "full_words.npy", np.zeros(len(tsn), dtype=np.uint64))
    events.append(
        {
            "folder_name": f"{folder}/TTL/",
            "channel_name": "TTL Input",
            "description": "",
            "identifier": "",
            "sample_rate": rate,
            "type": "int16",
            "num_channels": 1,
            "source_processor": source,
            "stream_name": stream,
        }
    )
    oebin = {"GUI version": gui_version, "continuous": [cont], "events": events, "spikes": []}
    (rec / "structure.oebin").write_text(json.dumps(oebin, indent=2))
    (rec / "sync_messages.txt").write_text(
        f"Start Time for {source} (100) - {stream} @ {rate:g} Hz: {int(sn[0]) if len(sn) else 0}\n"
    )
    return rec


def oe_device(
    names: list[str], rate: float, unit: str = "uV", stream: str = "example_data", port: int = 5556
) -> dict[str, Any]:
    params = {
        "unit": "arbitrary" if unit == "unknown" else "uV",
        "source_unit": unit,
        "channel_count": len(names),
        "sample_rate_hz": rate,
        "channel_names": names,
        "stream": stream,
        "frame_samples": 1024,
    }
    return {
        "device_id": f"openephys:127.0.0.1:{port}",
        "display_name": f"Open Ephys (ZMQ) · 127.0.0.1:{port}",
        "kind": "stream",
        "adapter": "concord.openephys.zmq@0.1.0",
        "description": "Open Ephys GUI over the ZMQ Interface plugin.",
        "native_format": "Open Ephys ZMQ Interface",
        "capabilities": [
            {"capability": "recording", "params": params, "description": "x"},
            {"capability": "device_status"},
        ],
        "synthetic": False,
    }


def oe_provenance(port: int = 5556, stream: str = "example_data") -> dict[str, Any]:
    return {
        "adapter": "concord.openephys.zmq@0.1.0",
        "synthetic": False,
        "origin": f"openephys:127.0.0.1:{port}/{stream}",
        "replayed": False,
    }


@dataclass
class OECase:
    rate: float = 30000.0
    channels: int = 8
    seconds: float = 8.0
    block: int = 1024
    first_sample: int = 123_456
    bit_volts: float = 0.195
    concord_start_block: int = 20
    seed: int = 3

    def __post_init__(self) -> None:
        n = int(self.seconds * self.rate)
        self.n = n
        uv = make_block(0, n, self.channels, self.rate, self.seed).astype(np.float64) * 2.0
        # what the GUI holds in float (µV) and what the Record Node stores as int16
        self.float_uv = uv.astype(np.float32)
        self.i16 = np.clip(
            np.round(self.float_uv / np.float32(self.bit_volts)), -32768, 32767
        ).astype(np.int16)
        self.sn = self.first_sample + np.arange(n, dtype=np.int64)
        self.names = [f"CH{i + 1}" for i in range(self.channels)]

    def frames(self, unit: str = "uV") -> list[BFrame]:
        out = []
        for a in range(self.concord_start_block * self.block, self.n - self.block, self.block):
            b = a + self.block
            data = self.float_uv[a:b].astype(np.float64)
            idx = int(self.sn[a])
            t_dev = round(idx * 1_000_000_000 / self.rate)
            t_wall = 1_700_000_000_000_000_000 + round((b / self.rate + 0.002) * 1e9)
            out.append(
                BFrame(idx, data, t_dev, t_wall, unit="arbitrary" if unit == "unknown" else "uV")
            )
        return out

    def write(
        self,
        root: Path,
        *,
        frames: list[BFrame] | None = None,
        device: dict[str, Any] | None = None,
        annotations: Iterable[tuple[int, int, str, Any]] = (),
        mutate_ref: Callable[[OECase], dict[str, Any]] | None = None,
    ) -> tuple[Path, Path]:
        kw: dict[str, Any] = {}
        if mutate_ref is not None:
            kw = mutate_ref(self)
        rec = write_oe_binary(
            root / "ref",
            kw.pop("samples", self.i16),
            kw.pop("sample_numbers", self.sn),
            self.rate,
            self.names,
            bit_volts=self.bit_volts,
            **kw,
        )
        b = root / "run.concord.jsonl"
        write_concord(
            b,
            device or oe_device(self.names, self.rate),
            frames if frames is not None else self.frames(),
            self.rate,
            oe_provenance(),
            annotations,
        )
        return rec, b
