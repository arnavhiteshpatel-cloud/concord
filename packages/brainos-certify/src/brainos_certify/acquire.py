"""Reading a plugin session through the real plugin host and recording what arrived.

Each ``read`` request goes over the host's binary IPC exactly as BrainOS sends it. For every
chunk the certifier keeps the metadata (stream, first index, sample count, first/last
timestamp, arrival time on the host's monotonic and wall clocks) and the timestamps of numeric
streams (bounded), re-validates the chunk locally with the SDK's ``ChunkValidator`` (the host
already validated it; the certifier does not trust the host either), and drops the sample data.
"""

from __future__ import annotations

import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from brainos_adapter_sdk import Chunk, MarkerChunk, SessionInfo, StreamRole, StreamSpec, ipc
from brainos_adapter_sdk import validate as v
from brainos_adapter_sdk.client import HostDied, HostError, SyncHostClient
from numpy.typing import NDArray

MAX_STORED_SAMPLES = 2_000_000  # timestamps kept per stream for jitter analysis
MAX_NOTICES = 20


@dataclass
class Arrival:
    """One chunk as it arrived."""

    t_mono: float  # host monotonic clock when the read answer arrived (s)
    t_wall: float  # time.time() at the same moment
    t_lsl: float | None  # liblsl local_clock() at the same moment, if the clock is lsl
    n: int
    cumulative: int  # samples of this stream delivered so far, including this chunk
    ts_first: float
    ts_last: float


@dataclass
class StreamTrack:
    spec: StreamSpec
    samples: int = 0
    chunks: int = 0
    next_index: int = 0
    gaps: int = 0
    lost: int = 0
    overlaps: int = 0
    decreasing: int = 0
    first_index: int | None = None
    last_ts: float | None = None
    arrivals: list[Arrival] = field(default_factory=list)
    _ts: list[NDArray[np.float64]] = field(default_factory=list)
    _idx: list[NDArray[np.int64]] = field(default_factory=list)
    stored: int = 0
    truncated: bool = False

    @property
    def role(self) -> StreamRole:
        return StreamRole(self.spec.role)

    @property
    def is_markers(self) -> bool:
        return self.role is StreamRole.MARKERS

    def timestamps(self) -> NDArray[np.float64]:
        return np.concatenate(self._ts) if self._ts else np.zeros(0)

    def indices(self) -> NDArray[np.int64]:
        return np.concatenate(self._idx) if self._idx else np.zeros(0, dtype=np.int64)

    def add(
        self,
        first_index: int,
        ts: NDArray[np.float64],
        t_mono: float,
        t_wall: float,
        t_lsl: float | None,
    ) -> None:
        n = int(ts.shape[0])
        if n == 0:
            return
        if self.first_index is None:
            self.first_index = first_index
        if first_index > self.next_index:
            self.gaps += 1
            self.lost += first_index - self.next_index
        elif first_index < self.next_index:
            self.overlaps += 1
        self.next_index = max(self.next_index, first_index + n)
        if self.last_ts is not None and float(ts[0]) < self.last_ts:
            self.decreasing += 1
        if n > 1:
            self.decreasing += int(np.count_nonzero(np.diff(ts) < 0))
        self.last_ts = float(ts[-1])
        self.samples += n
        self.chunks += 1
        self.arrivals.append(
            Arrival(t_mono, t_wall, t_lsl, n, self.samples, float(ts[0]), float(ts[-1]))
        )
        room = MAX_STORED_SAMPLES - self.stored
        if room <= 0:
            self.truncated = True
            return
        keep = min(room, n)
        self._ts.append(np.asarray(ts[:keep], dtype=np.float64).copy())
        self._idx.append(np.arange(first_index, first_index + keep, dtype=np.int64))
        self.stored += keep
        self.truncated = self.truncated or keep < n


@dataclass
class Failure:
    """Why a read loop stopped early."""

    kind: str  # "HostError" | "HostDied" | "WireError"
    type: str  # ipc error type, or the exception class
    message: str
    problems: list[dict[str, Any]] = field(default_factory=list)
    after_s: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "type": self.type,
            "message": self.message[:500],
            "problems": self.problems[:10],
            "after_s": round(self.after_s, 3),
        }


@dataclass
class Acquisition:
    info: SessionInfo
    tracks: dict[str, StreamTrack]
    t_start: float
    t_end: float = 0.0
    reads: int = 0
    empty_reads: int = 0
    bytes: int = 0
    first_data_s: float | None = None  # from t_start to the first non-empty answer
    failure: Failure | None = None
    local_problems: list[v.Problem] = field(default_factory=list)
    notice_counts: Counter[str] = field(default_factory=Counter)
    notices: list[dict[str, Any]] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return self.t_end - self.t_start

    @property
    def samples(self) -> int:
        return sum(t.samples for t in self.tracks.values())

    @property
    def local_errors(self) -> list[v.Problem]:
        return v.errors(self.local_problems)

    def primary(self) -> StreamTrack:
        return self.tracks[self.info.primary_stream]


def _clock_fn(info: SessionInfo) -> Callable[[], float] | None:
    if not any(s.clock.domain == "lsl" for s in info.streams):
        return None
    try:
        import pylsl
    except Exception:  # pylsl missing or liblsl not loadable: compared to monotonic instead
        return None
    fn: Callable[[], float] = pylsl.local_clock
    return fn


def new_acquisition(info: SessionInfo) -> Acquisition:
    return Acquisition(
        info=info,
        tracks={s.stream_id: StreamTrack(s) for s in info.streams},
        t_start=time.monotonic(),
    )


def acquire(
    client: SyncHostClient,
    acq: Acquisition,
    validator: v.ChunkValidator,
    duration_s: float,
    *,
    read_timeout_s: float = 0.1,
    grace_s: float = 5.0,
    stop_after_first_data: bool = False,
) -> Acquisition:
    """Read for ``duration_s`` (or until the first data / the first failure)."""
    lsl_clock = _clock_fn(acq.info)
    deadline = time.monotonic() + duration_s
    while time.monotonic() < deadline:
        try:
            result, arrays = client.request(
                "read", {"timeout_s": read_timeout_s}, timeout_s=read_timeout_s + grace_s
            )
        except HostError as exc:
            acq.failure = Failure(
                "HostError",
                exc.type,
                exc.message,
                [dict(p) for p in exc.problems],
                time.monotonic() - acq.t_start,
            )
            break
        except HostDied as exc:
            acq.failure = Failure(
                "HostDied", "HostDied", str(exc), [], time.monotonic() - acq.t_start
            )
            break
        t_mono = time.monotonic()
        t_wall = time.time()
        t_lsl = lsl_clock() if lsl_clock is not None else None
        acq.reads += 1
        try:
            items = ipc.chunks_from_wire(result.get("chunks", []), arrays)
        except ipc.WireError as exc:
            acq.failure = Failure("WireError", "WireError", str(exc), [], t_mono - acq.t_start)
            break
        for n in result.get("notices") or []:
            if isinstance(n, dict):
                acq.notice_counts[str(n.get("code"))] += 1
                if len(acq.notices) < MAX_NOTICES:
                    acq.notices.append({str(k): str(x)[:300] for k, x in n.items()})
        acq.bytes += sum(int(a.nbytes) for a in arrays)
        if not items:
            acq.empty_reads += 1
            continue
        if acq.first_data_s is None:
            acq.first_data_s = t_mono - acq.t_start
        problems = validator.check_all(items)
        acq.local_problems.extend(problems)
        for item in items:
            track = acq.tracks.get(item.stream_id)
            if track is None:
                continue  # reported by the validator (chunk.stream.unknown)
            if isinstance(item, MarkerChunk):
                ts = np.asarray(item.timestamps, dtype=np.float64)
                track.add(track.next_index, ts, t_mono, t_wall, t_lsl)
            elif isinstance(item, Chunk):
                ts = np.asarray(item.timestamps, dtype=np.float64)
                track.add(int(item.first_index), ts, t_mono, t_wall, t_lsl)
        if v.has_errors(problems):
            acq.failure = Failure(
                "LocalValidation",
                "InvalidData",
                v.summarize(problems),
                [p.to_dict() for p in v.errors(problems)],
                t_mono - acq.t_start,
            )
            break
        if stop_after_first_data:
            break
    acq.t_end = time.monotonic()
    return acq


def session_info_from_open(opened: dict[str, Any]) -> SessionInfo:
    return ipc.session_info_from_dict(opened.get("info") or {})
