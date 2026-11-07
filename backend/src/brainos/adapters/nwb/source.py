"""NWB spike-time recordings as a ``ReplaySource`` for the existing ``ReplayAdapter``.

Per time bin the source yields, all stamped with the bin-end time on the recording clock:
  * ``features.binned``  — spike counts per channel      (provenance ``processed_feature``)
  * ``behavior.sample``  — recorded kinematics, if any    (provenance ``behavioral_label``)
  * ``intent.kinematics`` — only if a held-out decoder is attached
                                                          (provenance ``decoded_intent`` + model_id)

Recorded neural activity is never emitted as ``pointer_intent``/``selection``/``text_intent``.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from brainos.adapters.nwb.reader import NWBUnitsRecording, load
from brainos.adapters.replay.format import ReplayRecord
from brainos.contracts.capabilities import Capability, CapabilityDescriptor, EventType
from brainos.contracts.events import Provenance, ProvenanceKind, Quality
from brainos.contracts.protocol import (
    DatasetInfo,
    DeviceDescriptor,
    DeviceKind,
    SourceBehavior,
    SourceChannel,
    SourceDecoder,
    SourceFile,
    SourceMetadata,
)
from brainos.datasets import Verification, session_of, verify_file
from brainos.decoding.ridge import RidgeDecoder

ADAPTER = "brainos.nwb.units@0.1.0"
DECODER_ADAPTER = "brainos.decoding.ridge@0.1.0"
DEVICE_PREFIX = "nwb:"
HUMAN_LABEL = "Recorded Human Intracranial Data — Offline Replay"
OTHER_LABEL = "Recorded Neural Data — Offline Replay"
KINEMATIC_SPACE = "falcon_h1_7dof"


class DecoderLeakageError(ValueError):
    """Refused: the decoder was trained on data from this recording's session."""


class DecoderMismatchError(ValueError):
    """Refused: the decoder's channels, bin width or dimensions do not match the file."""


def device_id_for(path: Path) -> str:
    slug = re.sub(r"[^a-z0-9_.\-]+", "-", path.stem.lower()).strip("-")
    return (DEVICE_PREFIX + slug)[:64]


def _is_human(species: str | None) -> bool:
    return bool(species) and "homo sapiens" in str(species).lower()


class NWBUnitsSource:
    def __init__(
        self,
        path: Path,
        *,
        decoder: RidgeDecoder | None = None,
        recording: NWBUnitsRecording | None = None,
        verification: Verification | None = None,
    ) -> None:
        self.path = Path(path)
        self.rec = recording or load(self.path)
        self.verification = verification or verify_file(self.path)
        self.name = self.path.stem
        m, a = self.verification.manifest, self.verification.asset
        self.origin = f"dandi:{m.dandiset}/{a.path}" if m and a else f"file:{self.path.name}"
        self.decoder = decoder
        if decoder is not None:
            self._check_decoder(decoder)
        q = Quality(score=1.0, flags=[])
        self._q = q
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
        self._p_dec = (
            Provenance(
                kind=ProvenanceKind.DECODED_INTENT,
                adapter=DECODER_ADAPTER,
                synthetic=False,
                model_id=decoder.model_id,
                origin=self.origin,
            )
            if decoder
            else None
        )

    # ------------------------------------------------------------------ checks
    def _check_decoder(self, d: RidgeDecoder) -> None:
        rec = self.rec
        trained_sha = d.training.get("sha256")
        trained_session = d.training.get("session")
        if trained_sha == self.verification.sha256 or (
            trained_session is not None and trained_session == session_of(self.path.name)
        ):
            raise DecoderLeakageError(
                f"model {d.model_id} was trained on session {trained_session}; replaying "
                f"{self.path.name} with it would score the model on its own training data "
                "(note: FALCON minival files are subsets of the calib files of the same session)"
            )
        if d.channel_count != rec.channel_count or abs(d.bin_ms - rec.bin_s * 1000) > 1e-6:
            raise DecoderMismatchError(
                f"model {d.model_id} expects {d.channel_count} channels at {d.bin_ms} ms bins; "
                f"file has {rec.channel_count} at {rec.bin_s * 1000:g} ms"
            )
        if rec.behavior is not None and rec.behavior.dims != d.dims:
            raise DecoderMismatchError(f"model dims {d.dims} != file dims {rec.behavior.dims}")

    # --------------------------------------------------------- ReplaySource API
    def duration_ns(self) -> int | None:
        return round(self.rec.duration_s * 1e9)

    def descriptor(self) -> DeviceDescriptor:
        rec = self.rec
        rate = 1.0 / rec.bin_s
        caps = [
            CapabilityDescriptor(
                capability=Capability.NEURAL_FEATURES,
                params={
                    "feature": rec.feature,
                    "bin_ms": rec.bin_s * 1000,
                    "rate_hz": rate,
                    "channel_count": rec.channel_count,
                    "unit": "count",
                },
                description="Spike counts per channel per bin, computed from recorded spike times.",
            )
        ]
        if rec.behavior is not None:
            caps.append(
                CapabilityDescriptor(
                    capability=Capability.BEHAVIOR,
                    params={
                        "quantity": rec.behavior.quantity,
                        "dims": rec.behavior.dims,
                        "unit": rec.behavior.unit,
                        "rate_hz": rate,
                    },
                    description="Recorded behavioral ground truth from the file (not an intent).",
                )
            )
        if self.decoder is not None:
            caps.append(
                CapabilityDescriptor(
                    capability=Capability.KINEMATIC_INTENT,
                    params={
                        "model_id": self.decoder.model_id,
                        "dims": self.decoder.dims,
                        "space": KINEMATIC_SPACE,
                        "rate_hz": rate,
                    },
                    description="Offline baseline decoder output, held-out data (decoded_intent).",
                )
            )
        caps.append(CapabilityDescriptor(capability=Capability.DEVICE_STATUS))
        human = _is_human(rec.species)
        m = self.verification.manifest
        where = f"DANDI {m.dandiset}" if m else "unverified local file"
        return DeviceDescriptor(
            device_id=device_id_for(self.path),
            display_name=HUMAN_LABEL if human else OTHER_LABEL,
            kind=DeviceKind.REPLAY,
            adapter=ADAPTER,
            description=(
                f"{self.path.name} ({where}). Offline replay of a recording made in the past; "
                "not a live implant connection."
            ),
            native_format="NWB 2.x / HDF5: Units spike times + behavioral TimeSeries",
            capabilities=caps,
            synthetic=False,
        )

    def records(self) -> Iterator[ReplayRecord]:
        rec = self.rec
        beh = rec.behavior
        dec = self.decoder.streaming() if self.decoder else None
        bin_ms = rec.bin_s * 1000
        n_ch = rec.channel_count
        for start, chunk in rec.iter_counts():
            for j in range(chunk.shape[0]):
                i = start + j
                t_ns = round(rec.bin_end_s(i) * 1e9)
                counts = chunk[j]
                yield self._rec(
                    t_ns,
                    EventType.FEATURES_BINNED,
                    {
                        "feature": rec.feature,
                        "unit": "count",
                        "bin_ms": bin_ms,
                        "bin_index": i,
                        "channel_count": n_ch,
                        "counts": counts.tolist(),
                    },
                    self._p_feat,
                )
                if beh is not None:
                    yield self._rec(
                        t_ns,
                        EventType.BEHAVIOR_SAMPLE,
                        {
                            "quantity": beh.quantity,
                            "dims": beh.dims,
                            "unit": beh.unit,
                            "values": [float(v) for v in beh.values[i]],
                            "sample_index": i,
                            "valid": bool(beh.valid[i]),
                        },
                        self._p_beh,
                    )
                if dec is not None and self._p_dec is not None:
                    pred = dec.step(counts)
                    yield self._rec(
                        t_ns,
                        EventType.INTENT_KINEMATICS,
                        {
                            "quantity": dec.model.quantity,
                            "dims": dec.model.dims,
                            "unit": dec.model.unit,
                            "values": [float(v) for v in pred],
                            "space": KINEMATIC_SPACE,
                        },
                        self._p_dec,
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

    # ---------------------------------------------------------------- metadata
    def metadata(self) -> SourceMetadata:
        rec, v = self.rec, self.verification
        m, a = v.manifest, v.asset
        notes = list(rec.notes)
        if rec.session_start_time[:4].isdigit() and int(rec.session_start_time[:4]) < 1970:
            notes.append(
                f"Session date {rec.session_start_time[:10]} is not a real calendar date; the "
                "dataset shifts dates for de-identification."
            )
        d = self.decoder
        ev = next((e for e in d.evaluations if e.get("sha256") == v.sha256), None) if d else None
        return SourceMetadata(
            device_id=device_id_for(self.path),
            label=HUMAN_LABEL if _is_human(rec.species) else OTHER_LABEL,
            source_type="nwb_units",
            dataset=DatasetInfo(
                id=m.id,
                title=m.title,
                dandiset=m.dandiset,
                version=m.version,
                url=m.url,
                license=m.license,
                access=m.access,
                citation=m.citation,
                asset_id=a.asset_id,
                asset_path=a.path,
            )
            if m and a
            else None,
            file=SourceFile(
                name=self.path.name,
                size_bytes=self.path.stat().st_size,
                sha256=v.sha256,
                verified=v.verified,
                verification=v.describe(),
            ),
            species=rec.species,
            subject_id=rec.subject_id,
            identifier=rec.identifier,
            session_description=rec.session_description,
            session_start_time=rec.session_start_time,
            experiment_description=rec.experiment_description,
            institution=rec.institution,
            lab=rec.lab,
            recording_type=m.recording_type if m else "spike times (NWB units table)",
            profile=rec.profile,
            feature=rec.feature,
            feature_unit="count",
            bin_ms=rec.bin_s * 1000,
            n_bins=rec.n_bins,
            duration_s=round(rec.duration_s, 3),
            channel_count=rec.channel_count,
            channels=[
                SourceChannel(
                    index=c.index,
                    unit_id=c.unit_id,
                    spike_count=c.spike_count,
                    electrode=c.electrode,
                )
                for c in rec.channels
            ],
            behavior=SourceBehavior(
                series=rec.behavior.series,
                quantity=rec.behavior.quantity,
                dims=rec.behavior.dims,
                unit=rec.behavior.unit,
                valid_fraction=round(float(rec.behavior.valid.mean()), 4),
            )
            if rec.behavior is not None
            else None,
            decoder=SourceDecoder(
                model_id=d.model_id,
                method=d.method,
                dims=d.dims,
                alpha=d.alpha,
                trained_on=f"{d.training.get('file')} (session {d.training.get('session')})",
                evaluated_r2=ev.get("r2") if ev else None,
                evaluated_samples=ev.get("samples") if ev else None,
                control_mean_predictor_r2=ev.get("control_mean_predictor_r2") if ev else None,
                control_time_shift_r2=ev.get("control_time_shift_r2") if ev else None,
            )
            if d
            else None,
            notes=notes,
        )
