"""A cursor + click block as a ``ReplaySource`` (offline replay through the ``ReplayAdapter``).

Per 10 ms bin, all stamped with the bin-end time on the block clock:

* ``features.binned`` threshold crossings and ``features.vector`` spike band power
  (``processed_feature``; the two streams share bin times so a decoder can join them),
* ``behavior.sample`` cursor and target position (``behavioral_label``: task state, never a
  command),
* ``intent.kinematics`` with the **original online decoders' recorded outputs** — cursor
  velocity and click — as ``decoded_intent`` with ``model_origin: historical`` and
  ``replayed: true``. They are what the research system decoded during the session, not
  BrainOS, and the operator must choose to route them (passthrough) like any decoder output.
* ``recording.annotation`` at each trial start (cued target) and at the start of the block.

Positions use the dataset's frame: origin at the screen centre, +x right, **+y up**, unit =
screen height (space ``t15_screen``).
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from brainos.adapters.cursorclick.reader import BIN_S, T15Block, load
from brainos.adapters.replay.format import ReplayRecord
from brainos.contracts.capabilities import Capability, CapabilityDescriptor, EventType
from brainos.contracts.events import Provenance, ProvenanceKind, Quality
from brainos.contracts.protocol import DeviceDescriptor, DeviceKind, Modality
from brainos.datasets.dryad import DryadVerification, manifests, verify_file

ADAPTER = "brainos.cursorclick.t15@0.1.0"
DEVICE_PREFIX = "t15:"
LABEL = "Recorded Human Intracortical Data (cursor + click) — Offline Replay"
SPACE = "t15_screen"
POS_UNIT = "screen_height"
VEL_UNIT = "screen_height/s"
SBP_UNIT = "arbitrary^2"  # the README does not state the unit of the filtered signal
HISTORICAL_VELOCITY = "t15-historical-velocity"
HISTORICAL_CLICK = "t15-historical-click"
BIN_MS = BIN_S * 1000


DOI = "10.5061/dryad.prr4xgxzq"
_ORIGIN = re.compile(r"dryad:10\.5061/dryad\.prr4xgxzq/(t\d+)_day(\d+)_block(\d+)_")


def source_identity(origin: str | None) -> str | None:
    """Participant identity of a replayed T15 block (decoders do not transfer across people)."""
    from brainos.decoding.model import source_identity as identity

    return identity(origin) if _ORIGIN.search(origin or "") else None


def block_session(origin: str | None) -> str | None:
    """Leakage unit: one block. Training and test blocks share a day (as for the original online
    decoder), never a block; a model is refused on any block it was trained on."""
    from brainos.datasets import session_of

    return session_of(origin or "") if _ORIGIN.search(origin or "") else None


def device_id_for(block: T15Block) -> str:
    return f"{DEVICE_PREFIX}day{block.day:05d}-block{block.block:02d}-{block.task}"[:64].replace(
        "_", "-"
    )


def neural_streams(block: T15Block) -> list[dict[str, Any]]:
    labels = [f"{a}-{i:03d}" for i, a in enumerate(block.array_labels)]
    common = {"bin_ms": BIN_MS, "channel_count": block.channel_count, "channel_labels": labels}
    return [
        {
            "event_type": EventType.FEATURES_BINNED.value,
            "feature": "threshold_crossing_count",
            "unit": "count",
            **common,
        },
        {
            "event_type": EventType.FEATURES_VECTOR.value,
            "feature": "spike_band_power",
            "unit": SBP_UNIT,
            **common,
        },
    ]


def _by_name(path: Path) -> DryadVerification:
    size = path.stat().st_size
    for m in manifests():
        f = m.by_filename(path.name)
        if f is not None and f.size_bytes == size:
            return DryadVerification("", m, f)
    return DryadVerification("", None, None)


class T15CursorClickSource:
    def __init__(
        self,
        path: Path,
        *,
        block: T15Block | None = None,
        verification: DryadVerification | None = None,
        verify: bool = True,
    ) -> None:
        """``verify=False`` (device listing only): the file is matched to the pinned manifest by
        name and size, and its SHA-256 is checked when the device is opened (``verify=True``)."""
        self.path = Path(path)
        self.block = block or load(self.path)
        self.hashed = verification is not None or verify
        self.verification = verification or (
            verify_file(self.path) if verify else _by_name(self.path)
        )
        m, f = self.verification.manifest, self.verification.file
        self.origin = f"dryad:{m.doi}/{f.path}" if m and f else f"file:{self.path.name}"
        self.name = self.path.stem
        self._q = Quality(score=1.0, flags=[])
        self._p_feat = Provenance(
            kind=ProvenanceKind.PROCESSED_FEATURE,
            adapter=ADAPTER,
            synthetic=False,
            origin=self.origin,
        )
        self._p_beh = Provenance(
            kind=ProvenanceKind.BEHAVIORAL_LABEL,
            adapter=ADAPTER,
            synthetic=False,
            origin=self.origin,
        )

        def historical(model_id: str) -> Provenance:
            return Provenance(
                kind=ProvenanceKind.DECODED_INTENT,
                adapter=ADAPTER,  # the adapter that replays them; the decoder is model_id
                synthetic=False,
                model_id=model_id,
                model_origin="historical",
                replayed=True,
                origin=self.origin,
            )

        self._p_vel = historical(HISTORICAL_VELOCITY)
        self._p_click = historical(HISTORICAL_CLICK)

    # ------------------------------------------------------------- ReplaySource API
    def duration_ns(self) -> int:
        return round(self.block.duration_s * 1e9)

    def descriptor(self) -> DeviceDescriptor:
        b = self.block
        rate = 1.0 / BIN_S
        streams = neural_streams(b)
        decoders: list[dict[str, Any]] = [
            {
                "model_id": HISTORICAL_VELOCITY,
                "dims": ["vx", "vy"],
                "quantity": "velocity",
                "unit": VEL_UNIT,
                "space": SPACE,
                "model_origin": "historical",
                "y_axis": "up",
            }
        ]
        if b.has_click:
            decoders.append(
                {
                    "model_id": HISTORICAL_CLICK,
                    "dims": ["click"],
                    "quantity": "click_decision",
                    "unit": "probability",
                    "space": SPACE,
                    "model_origin": "historical",
                }
            )
        caps = [
            CapabilityDescriptor(
                capability=Capability.NEURAL_FEATURES,
                params={
                    # first stream, for consumers that read a single feature
                    "feature": "threshold_crossing_count",
                    "bin_ms": BIN_MS,
                    "rate_hz": rate,
                    "channel_count": b.channel_count,
                    "unit": "count",
                    "streams": streams,
                },
                description=(
                    "Threshold crossings (features.binned) and spike band power (features.vector) "
                    "per electrode, 10 ms bins, as published."
                ),
            ),
            CapabilityDescriptor(
                capability=Capability.BEHAVIOR,
                params={
                    "quantities": ["cursor_position", "target_position"],
                    "dims": ["x", "y"],
                    "unit": POS_UNIT,
                    "space": SPACE,
                    "rate_hz": rate,
                },
                description="Recorded cursor and cued-target positions (task state, not intent).",
            ),
            CapabilityDescriptor(
                capability=Capability.KINEMATIC_INTENT,
                params={"rate_hz": rate, "decoders": decoders},
                description=(
                    "HISTORICAL: the original research system's online decoder outputs, recorded "
                    "during the session (model_origin historical). Not BrainOS decoding."
                ),
            ),
            CapabilityDescriptor(capability=Capability.RECORDING),
            CapabilityDescriptor(capability=Capability.DEVICE_STATUS),
        ]
        m = self.verification.manifest
        if m is None:
            where = "unverified local file: not the pinned published file"
        elif self.hashed:
            where = f"Dryad doi:{m.doi}, SHA-256 verified"
        else:
            where = f"Dryad doi:{m.doi}, pinned file; SHA-256 is verified when opened"
        assist = "fully neural" if b.fully_neural else "includes computer assistance"
        return DeviceDescriptor(
            device_id=device_id_for(b),
            display_name=LABEL,
            kind=DeviceKind.REPLAY,
            adapter=ADAPTER,
            description=(
                f"{self.path.name} ({where}): participant {b.participant}, day {b.day}, "
                f"block {b.block}, {b.task.replace('_', ' ')} ({assist}), "
                f"{b.duration_s:.0f} s. Offline replay of a recording made in the past; "
                "not a live implant connection."
            ),
            native_format="MATLAB .mat: 10 ms binned features + task state + decoder outputs",
            capabilities=caps,
            synthetic=False,
            modality=Modality.INTRACORTICAL,
            invasive=True,
        )

    def records(self) -> Iterator[ReplayRecord]:
        b = self.block
        n_ch = b.channel_count
        starts = {int(s): k for k, s in enumerate(b.trial_start_bin)}
        click = b.click_decoder
        yield self._rec(
            0,
            EventType.RECORDING_ANNOTATION,
            {
                "label": "block",
                "value": f"{b.participant} day {b.day} block {b.block}: {b.task}",
                "duration_ms": round(b.duration_s * 1000),
            },
            self._p_beh,
        )
        for i in range(b.n_bins):
            t_ns = round(b.bin_end_s(i) * 1e9)
            if i in starts:
                tx, ty = b.target[i]
                yield self._rec(
                    t_ns,
                    EventType.RECORDING_ANNOTATION,
                    {
                        "label": "trial_start",
                        "value": f"trial {starts[i]} target ({tx:.4f}, {ty:.4f})",
                        "duration_ms": 0,
                    },
                    self._p_beh,
                )
            yield self._rec(
                t_ns,
                EventType.FEATURES_BINNED,
                {
                    "feature": "threshold_crossing_count",
                    "unit": "count",
                    "bin_ms": BIN_MS,
                    "bin_index": i,
                    "channel_count": n_ch,
                    "counts": b.tx[i].tolist(),
                },
                self._p_feat,
            )
            yield self._rec(
                t_ns,
                EventType.FEATURES_VECTOR,
                {
                    "feature": "spike_band_power",
                    "unit": SBP_UNIT,
                    "band_hz": None,
                    "bin_ms": BIN_MS,
                    "bin_index": i,
                    "channel_count": n_ch,
                    "values": [float(v) for v in b.sbp[i]],
                },
                self._p_feat,
            )
            for quantity, arr in (("cursor_position", b.cursor), ("target_position", b.target)):
                yield self._rec(
                    t_ns,
                    EventType.BEHAVIOR_SAMPLE,
                    {
                        "quantity": quantity,
                        "dims": ["x", "y"],
                        "unit": POS_UNIT,
                        "values": [float(arr[i, 0]), float(arr[i, 1])],
                        "sample_index": i,
                        "valid": True,
                    },
                    self._p_beh,
                )
            yield self._rec(
                t_ns,
                EventType.INTENT_KINEMATICS,
                {
                    "quantity": "velocity",
                    "dims": ["vx", "vy"],
                    "unit": VEL_UNIT,
                    "values": [float(b.cursor_decoder[i, 0]), float(b.cursor_decoder[i, 1])],
                    "space": SPACE,
                },
                self._p_vel,
            )
            if click is not None:
                yield self._rec(
                    t_ns,
                    EventType.INTENT_KINEMATICS,
                    {
                        "quantity": "click_decision",
                        "dims": ["click"],
                        "unit": "probability",
                        "values": [float(click[i])],
                        "space": SPACE,
                    },
                    self._p_click,
                )

    def _rec(
        self, t_ns: int, et: EventType, payload: dict[str, Any], prov: Provenance
    ) -> ReplayRecord:
        return ReplayRecord(
            t_ns=t_ns,
            envelope={
                "event_type": et.value,
                "payload": payload,
                "quality": self._q,
                "provenance": prov,
                "device_timestamp_ns": t_ns,
            },
        )
