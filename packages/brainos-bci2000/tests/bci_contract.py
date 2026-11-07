"""Checks of the rules documented in ``brainos_adapter_sdk.api`` (module docstring and
dataclass comments), applied directly to a plugin's manifest, session info and output.

The plugin host / certification toolkit (other workstreams) run their own validation; this
helper lets this package's tests check the same rules through the public API only.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

import numpy as np
from brainos_adapter_sdk.api import (
    API_VERSION,
    KEY_PATTERN,
    PRIMARY_ROLES,
    Chunk,
    MarkerChunk,
    Modality,
    PluginManifest,
    SessionInfo,
    SourceSession,
    StreamRole,
)

NONINVASIVE = {Modality.EEG, Modality.MEG, Modality.EMG}
INVASIVE = {Modality.ECOG, Modality.SEEG, Modality.INTRACORTICAL}


def check_manifest(manifest: PluginManifest) -> None:
    assert manifest.api_version == API_VERSION
    assert manifest.roles, "manifest declares no roles"
    for key in manifest.options:
        assert KEY_PATTERN.match(key), f"option key {key!r} does not match KEY_PATTERN"
    for key, spec in manifest.options.items():
        if spec.type == "choice":
            assert spec.choices, f"choice option {key} has no choices"
            assert spec.default is None or spec.default in spec.choices, key


def check_session_info(info: SessionInfo, manifest: PluginManifest) -> None:
    ids = [s.stream_id for s in info.streams]
    assert len(ids) == len(set(ids)), f"duplicate stream ids {ids}"
    for sid in ids:
        assert KEY_PATTERN.match(sid), f"stream id {sid!r} does not match KEY_PATTERN"
    by_id = {s.stream_id: s for s in info.streams}
    assert info.primary_stream in by_id, "primary stream not declared"
    assert by_id[info.primary_stream].role in PRIMARY_ROLES
    assert info.origin
    for s in info.streams:
        assert s.role in manifest.roles, f"stream {s.stream_id} role {s.role} not in manifest"
        labels = [c.label for c in s.channels]
        assert labels and all(labels), f"stream {s.stream_id} has empty labels"
        assert len(labels) == len(set(labels)), f"stream {s.stream_id} labels not unique"
        assert s.nominal_rate_hz >= 0.0
        if s.modality is not None:
            assert s.role in (StreamRole.SIGNAL, StreamRole.SPIKE_COUNTS)
            if s.invasive is not None and s.modality in NONINVASIVE:
                assert s.invasive is False
            if s.invasive is not None and s.modality in INVASIVE:
                assert s.invasive is True
        if s.role is StreamRole.DECODER_OUTPUT:
            assert s.model_id, "DECODER_OUTPUT needs model_id"
        if s.role is StreamRole.SPIKE_COUNTS:
            assert s.bin_ms
        if s.role is StreamRole.MARKERS:
            assert s.nominal_rate_hz == 0.0


@dataclass
class StreamTracker:
    """Accumulates per-stream output and checks ordering / continuity rules."""

    info: SessionInfo
    next_index: dict[str, int] = field(default_factory=dict)
    last_ts: dict[str, float] = field(default_factory=dict)
    gaps: dict[str, int] = field(default_factory=dict)
    samples: dict[str, int] = field(default_factory=dict)
    data: dict[str, list[np.ndarray]] = field(default_factory=dict)
    timestamps: dict[str, list[np.ndarray]] = field(default_factory=dict)
    indices: dict[str, list[np.ndarray]] = field(default_factory=dict)
    markers: dict[str, list[tuple[str, float]]] = field(default_factory=dict)

    def feed(self, items: Iterable[Chunk | MarkerChunk]) -> None:
        by_id = {s.stream_id: s for s in self.info.streams}
        for item in items:
            spec = by_id.get(item.stream_id)
            assert spec is not None, f"undeclared stream {item.stream_id}"
            if isinstance(item, MarkerChunk):
                assert spec.role is StreamRole.MARKERS
                assert item.timestamps.shape == (len(item.labels),)
                assert all(isinstance(lab, str) and lab for lab in item.labels)
                self._check_ts(item.stream_id, item.timestamps)
                self.markers.setdefault(item.stream_id, []).extend(
                    zip(item.labels, item.timestamps.tolist(), strict=True)
                )
                continue
            assert spec.role is not StreamRole.MARKERS
            assert item.data.ndim == 2
            n, c = item.data.shape
            assert n > 0, "empty chunk"
            assert c == len(spec.channels), (
                f"{item.stream_id}: {c} cols, {len(spec.channels)} channels"
            )
            assert item.timestamps.shape == (n,)
            assert item.timestamps.dtype == np.float64
            assert np.issubdtype(item.data.dtype, np.number)
            assert np.all(np.isfinite(item.timestamps))
            self._check_ts(item.stream_id, item.timestamps)
            expected = self.next_index.get(item.stream_id, 0)
            assert item.first_index >= expected, (
                f"{item.stream_id}: first_index {item.first_index} < expected {expected}"
            )
            self.gaps[item.stream_id] = (
                self.gaps.get(item.stream_id, 0) + item.first_index - expected
            )
            self.next_index[item.stream_id] = item.first_index + n
            self.samples[item.stream_id] = self.samples.get(item.stream_id, 0) + n
            self.data.setdefault(item.stream_id, []).append(np.asarray(item.data))
            self.timestamps.setdefault(item.stream_id, []).append(item.timestamps)
            self.indices.setdefault(item.stream_id, []).append(
                item.first_index + np.arange(n, dtype=np.int64)
            )

    def _check_ts(self, sid: str, ts: np.ndarray) -> None:
        if ts.size == 0:
            return
        assert np.all(np.diff(ts) >= 0), f"{sid}: timestamps decrease within a chunk"
        prev = self.last_ts.get(sid)
        if prev is not None:
            assert ts[0] >= prev, f"{sid}: timestamps decrease across chunks"
        self.last_ts[sid] = float(ts[-1])

    def read_for(
        self,
        session: SourceSession,
        seconds: float,
        *,
        until: Callable[[StreamTracker], bool] | None = None,
        on_read: Callable[[Sequence[Chunk | MarkerChunk], float], None] | None = None,
    ) -> None:
        """Read ``session`` for ``seconds`` (or until ``until(self)``), checking everything."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            items = session.read(0.05)
            if on_read is not None:
                on_read(items, time.time())
            self.feed(items)
            if until is not None and until(self):
                return

    def stacked(self, sid: str) -> np.ndarray:
        return np.concatenate(self.data[sid], axis=0)

    def all_timestamps(self, sid: str) -> np.ndarray:
        return np.concatenate(self.timestamps[sid])

    def all_indices(self, sid: str) -> np.ndarray:
        return np.concatenate(self.indices[sid])
