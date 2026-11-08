"""Session recorder: writes published envelopes to a BrainOS recording file.

Milestone 5 (D) adds durability and recovery:

* files are created with mode 0600 (directory 0700);
* while a recording is written, ``<name>.active.json`` exists and the recorder holds an
  exclusive OS lock on it (released by the OS even if the process is killed);
* the write buffer is flushed at least every ``FLUSH_INTERVAL_S`` (a kill loses at most that
  much), and a clean stop flushes, fsyncs and removes the marker;
* ``recover()`` (run at server start) finds recordings whose writer died: the valid prefix
  (header + every complete event line) is kept, anything after it is moved byte-for-byte to
  ``<name>.discarded.bin``, and ``<name>.recovery.json`` marks the recording **incomplete**
  with counts and hashes. Nothing is ever dropped silently.
"""

from __future__ import annotations

import builtins
import contextlib
import hashlib
import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import IO, Any

from pydantic import BaseModel

from brainos.adapters.replay.format import (
    RECORDING_FORMAT,
    RECORDING_SUFFIX,
    RecordingFormatError,
    RecordingHeader,
    read_header,
    recording_path,
)
from brainos.contracts.events import SCHEMA_VERSION, EventEnvelope
from brainos.contracts.protocol import DeviceDescriptor
from brainos.security import ensure_private_dir, open_private, write_private

try:  # POSIX advisory locks; on other platforms the marker's pid is used instead
    import fcntl
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore[assignment]

log = logging.getLogger(__name__)

MAX_DURATION_S = 300.0
MAX_DURATION_NO_RAW_S = 3600.0  # features + labels only: small enough for calibration sessions
MAX_BYTES = 200 * 1024 * 1024
RAW_EVENT = "recording.frame"
FLUSH_INTERVAL_S = 0.25
ACTIVE_SUFFIX = ".active.json"
RECOVERY_SUFFIX = ".recovery.json"
DISCARDED_SUFFIX = ".discarded.bin"
SIDECAR_SUFFIXES = (ACTIVE_SUFFIX, RECOVERY_SUFFIX, DISCARDED_SUFFIX)

RecorderListener = Callable[[str, str, dict[str, Any]], None]  # (kind, name, details)


class RecoveryInfo(BaseModel):
    """Why a recording is incomplete and exactly what was kept."""

    status: str  # "incomplete" (valid prefix kept) | "unreadable" (header invalid; untouched)
    reason: str
    detected_at_ns: int
    valid_events: int
    valid_bytes: int
    discarded_bytes: int
    discarded_sha256: str | None
    discarded_file: str | None
    first_event_ns: int | None
    last_event_ns: int | None
    writer_pid: int | None


class RecordingInfo(BaseModel):
    name: str
    device_id: str
    device_name: str
    synthetic: bool
    created_at_ns: int
    size_bytes: int
    events: int | None = None
    active: bool = False
    # Milestone 5 (D): a recording interrupted by a crash/kill is kept and marked incomplete
    complete: bool = True
    recovery: RecoveryInfo | None = None


class RecorderError(Exception):
    pass


def _sidecar(directory: Path, name: str, suffix: str) -> Path:
    return directory / f"{name}{suffix}"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class Recorder:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._fh: IO[str] | None = None
        self._marker_fd: int | None = None
        self._name: str | None = None
        self._started = 0.0
        self._last_flush = 0.0
        self._bytes = 0
        self._events = 0
        self._device: DeviceDescriptor | None = None
        self._exclude_raw = False
        self.stop_reason: str | None = None
        self.listeners: list[RecorderListener] = []
        self.recovered: list[tuple[str, RecoveryInfo]] = []  # from the last recover()

    @property
    def active_name(self) -> str | None:
        return self._name

    def _notify(self, kind: str, name: str, details: dict[str, Any]) -> None:
        for fn in list(self.listeners):
            try:
                fn(kind, name, details)
            except Exception:  # a listener must never break recording
                log.exception("recording listener failed (%s %s)", kind, name)

    def start(
        self, device: DeviceDescriptor, name: str | None = None, *, exclude_raw: bool = False
    ) -> str:
        """Start recording. ``exclude_raw`` drops ``recording.frame`` events (features, labels,
        intents and annotations are kept), e.g. for long calibration sessions."""
        if self._fh is not None:
            raise RecorderError(f"already recording {self._name!r}")
        # a local file player is its own recording; external streams (LSL, Open Ephys) that
        # declare prerecorded content are recorded, keeping their 'replayed' provenance
        if device.device_id.startswith(("replay:", "nwb:")):
            raise RecorderError("re-recording a local file replay is not supported")
        ensure_private_dir(self.directory)
        name = name or time.strftime(f"{device.device_id}-%Y%m%d-%H%M%S").lower()
        try:
            path = recording_path(self.directory, name)
        except RecordingFormatError as exc:
            raise RecorderError(str(exc)) from exc
        if path.exists():
            raise RecorderError(f"recording {name!r} already exists")
        header = RecordingHeader(
            format=RECORDING_FORMAT,
            schema_version=SCHEMA_VERSION,
            created_at_ns=time.time_ns(),
            device=device,
            synthetic=device.synthetic,
            note=_note(device) + (" Raw signal frames excluded." if exclude_raw else ""),
        )
        try:
            fd = open_private(path, exclusive=True)
        except FileExistsError:
            raise RecorderError(f"recording {name!r} already exists") from None
        self._marker_fd = self._write_marker(name, device, header.created_at_ns)
        self._fh = os.fdopen(fd, "w", encoding="utf-8")
        line = header.model_dump_json() + "\n"
        self._fh.write(line)
        self._fh.flush()  # header must be readable while recording (device listing)
        self._name, self._device, self._exclude_raw = name, device, exclude_raw
        self._started = self._last_flush = time.monotonic()
        self._bytes, self._events = len(line), 0
        self.stop_reason = None
        log.info("recording %s started for %s", name, device.device_id)
        self._notify("started", name, {"device_id": device.device_id, "exclude_raw": exclude_raw})
        return name

    def _write_marker(self, name: str, device: DeviceDescriptor, created_at_ns: int) -> int:
        marker = _sidecar(self.directory, name, ACTIVE_SUFFIX)
        fd = open_private(marker)
        if fcntl is not None:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        body = {
            "pid": os.getpid(),
            "device_id": device.device_id,
            "created_at_ns": created_at_ns,
        }
        os.write(fd, json.dumps(body).encode())
        return fd

    def _release_marker(self, name: str) -> None:
        fd, self._marker_fd = self._marker_fd, None
        with contextlib.suppress(OSError):
            _sidecar(self.directory, name, ACTIVE_SUFFIX).unlink()
        if fd is not None:
            with contextlib.suppress(OSError):
                os.close(fd)  # releases the lock

    def wants(self, envelope: EventEnvelope) -> bool:
        """Whether ``on_event`` would write ``envelope`` (the bus serializes only then)."""
        return self._fh is not None and not (
            self._exclude_raw and envelope.event_type.value == RAW_EVENT
        )

    def on_event(self, envelope: EventEnvelope, event_json: str) -> None:
        fh = self._fh
        if fh is None or not self.wants(envelope):
            return
        try:
            fh.write(event_json)
            fh.write("\n")
            now = time.monotonic()
            if now - self._last_flush >= FLUSH_INTERVAL_S:
                fh.flush()  # bounds what a crash can lose; see recover()
                self._last_flush = now
        except OSError as exc:
            log.error("recording %s write failed: %s", self._name, exc)
            self.stop(f"write failed: {exc}")
            return
        self._bytes += len(event_json) + 1
        self._events += 1
        limit = MAX_DURATION_NO_RAW_S if self._exclude_raw else MAX_DURATION_S
        if time.monotonic() - self._started > limit:
            self.stop("max duration reached")
        elif self._bytes > MAX_BYTES:
            self.stop("max size reached")

    def stop(self, reason: str = "stopped") -> RecordingInfo | None:
        if self._fh is None or self._name is None or self._device is None:
            return None
        fh, self._fh = self._fh, None
        # Each step separately: after a failed write (disk full) the flush fails too, and the
        # file must still be closed. Stopping must never raise into the event pump.
        try:
            fh.flush()
            os.fsync(fh.fileno())
        except Exception as exc:
            log.error("recording %s flush failed: %s", self._name, exc)
        try:
            fh.close()
        except Exception as exc:
            log.error("recording %s close failed: %s", self._name, exc)
        name, self._name = self._name, None
        self._release_marker(name)
        self.stop_reason = reason
        log.info("recording %s stopped (%s, %d events)", name, reason, self._events)
        self._notify("stopped", name, {"reason": reason, "events": self._events})
        path = recording_path(self.directory, name)
        info = self._info(path)
        return info.model_copy(update={"events": self._events}) if info else None

    def _recovery(self, name: str) -> RecoveryInfo | None:
        p = _sidecar(self.directory, name, RECOVERY_SUFFIX)
        if not p.exists():
            return None
        try:
            return RecoveryInfo.model_validate_json(p.read_text(encoding="utf-8"))
        except (ValueError, OSError) as exc:
            log.warning("unreadable recovery record %s: %s", p.name, exc)
            return None

    def _info(self, path: Path) -> RecordingInfo | None:
        try:
            h = read_header(path)
        except (RecordingFormatError, OSError) as exc:
            log.warning("skipping unreadable recording %s: %s", path.name, exc)
            return None
        name = path.name.removesuffix(RECORDING_SUFFIX)
        recovery = self._recovery(name)
        return RecordingInfo(
            name=name,
            device_id=h.device.device_id,
            device_name=h.device.display_name,
            synthetic=h.synthetic,
            created_at_ns=h.created_at_ns,
            size_bytes=path.stat().st_size,
            events=recovery.valid_events if recovery else None,
            active=name == self._name,
            complete=recovery is None,
            recovery=recovery,
        )

    def info(self, name: str) -> RecordingInfo | None:
        try:
            path = recording_path(self.directory, name)
        except RecordingFormatError:
            return None
        return self._info(path) if path.exists() else None

    def list(self) -> list[RecordingInfo]:
        if not self.directory.exists():
            return []
        infos = [self._info(p) for p in sorted(self.directory.glob(f"*{RECORDING_SUFFIX}"))]
        return sorted((i for i in infos if i), key=lambda i: i.created_at_ns, reverse=True)

    def files(self, name: str) -> builtins.list[Path]:
        """The recording file and its sidecars that exist."""
        base = recording_path(self.directory, name)
        out = [base] if base.exists() else []
        out += [p for s in SIDECAR_SUFFIXES if (p := _sidecar(self.directory, name, s)).exists()]
        return out

    def delete(self, name: str) -> int:
        """Delete a closed recording and its sidecars; returns the bytes removed."""
        if name == self._name:
            raise RecorderError(f"recording {name!r} is being written; stop it first")
        try:
            recording_path(self.directory, name)
        except RecordingFormatError as exc:
            raise RecorderError(str(exc)) from None
        files = self.files(name)
        if not any(p.name.endswith(RECORDING_SUFFIX) for p in files):
            raise RecorderError(f"no recording {name!r}")
        freed = 0
        for p in files:
            freed += p.stat().st_size
            p.unlink()
        log.info("recording %s deleted (%d bytes)", name, freed)
        self._notify("deleted", name, {"bytes": freed})
        return freed

    # ------------------------------------------------------------------ recovery
    def recover(self) -> builtins.list[tuple[str, RecoveryInfo]]:
        """Detect recordings whose writer died and keep their valid prefix (server start)."""
        self.recovered = []
        if not self.directory.exists():
            return []
        candidates: dict[str, int | None] = {}
        for marker in sorted(self.directory.glob(f"*{ACTIVE_SUFFIX}")):
            name = marker.name.removesuffix(ACTIVE_SUFFIX)
            if name == self._name:
                continue
            owner = self._marker_owner(marker)
            if owner == "alive":
                log.warning("recording %s is being written by another process; left alone", name)
                continue
            candidates[name] = owner if isinstance(owner, int) else None
        # recordings from before markers existed: a file that does not end with a newline
        for path in self.directory.glob(f"*{RECORDING_SUFFIX}"):
            name = path.name.removesuffix(RECORDING_SUFFIX)
            if name in candidates or name == self._name:
                continue
            if _sidecar(self.directory, name, RECOVERY_SUFFIX).exists():
                continue
            if not _ends_with_newline(path):
                candidates[name] = None
        for name, pid in sorted(candidates.items()):
            info = self._recover_one(name, pid)
            if info is not None:
                self.recovered.append((name, info))
        return self.recovered

    def _marker_owner(self, marker: Path) -> int | str | None:
        """'alive' if a live process holds the marker; else the dead writer's pid (or None)."""
        try:
            body = json.loads(marker.read_text(encoding="utf-8"))
            raw = body.get("pid") if isinstance(body, dict) else None
            pid = int(raw) if raw else None
        except (ValueError, OSError, TypeError):
            pid = None
        if fcntl is not None:
            try:
                fd = os.open(marker, os.O_RDONLY)
            except OSError:
                return pid
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                return "alive"
            finally:
                os.close(fd)
            return pid
        if pid is not None and pid != os.getpid() and _pid_alive(pid):
            return "alive"
        return pid

    def _recover_one(self, name: str, pid: int | None) -> RecoveryInfo | None:
        path = recording_path(self.directory, name)
        marker = _sidecar(self.directory, name, ACTIVE_SUFFIX)
        now = time.time_ns()
        reason = (
            "BrainOS stopped while this recording was being written (crash, kill or power loss)"
        )
        if not path.exists():
            log.warning("stale recording marker %s without a recording; removed", marker.name)
            marker.unlink(missing_ok=True)
            return None
        try:
            read_header(path)
        except (RecordingFormatError, OSError) as exc:
            info = RecoveryInfo(
                status="unreadable",
                reason=f"{reason}; the header is unreadable ({exc}); the file was left untouched",
                detected_at_ns=now,
                valid_events=0,
                valid_bytes=0,
                discarded_bytes=0,
                discarded_sha256=None,
                discarded_file=None,
                first_event_ns=None,
                last_event_ns=None,
                writer_pid=pid,
            )
            write_private(_sidecar(self.directory, name, RECOVERY_SUFFIX), info.model_dump_json())
            marker.unlink(missing_ok=True)
            log.error("recording %s interrupted and unreadable: %s", name, exc)
            return info
        valid_bytes, events, first, last = _valid_prefix(path)
        size = path.stat().st_size
        discarded = size - valid_bytes
        digest = None
        discarded_name = None
        if discarded > 0:
            with path.open("rb") as fh:
                fh.seek(valid_bytes)
                tail = fh.read()
            digest = hashlib.sha256(tail).hexdigest()
            discarded_name = f"{name}{DISCARDED_SUFFIX}"
            write_private(self.directory / discarded_name, tail)
            with path.open("r+b") as fh:
                fh.truncate(valid_bytes)
                fh.flush()
                os.fsync(fh.fileno())
        info = RecoveryInfo(
            status="incomplete",
            reason=reason,
            detected_at_ns=now,
            valid_events=events,
            valid_bytes=valid_bytes,
            discarded_bytes=discarded,
            discarded_sha256=digest,
            discarded_file=discarded_name,
            first_event_ns=first,
            last_event_ns=last,
            writer_pid=pid,
        )
        write_private(_sidecar(self.directory, name, RECOVERY_SUFFIX), info.model_dump_json())
        marker.unlink(missing_ok=True)
        log.warning(
            "recording %s was interrupted: kept %d complete events (%d bytes), moved %d trailing "
            "bytes to %s; marked incomplete",
            name,
            events,
            valid_bytes,
            discarded,
            discarded_name or "-",
        )
        self._notify("recovered", name, {"valid_events": events, "discarded_bytes": discarded})
        return info


def _ends_with_newline(path: Path) -> bool:
    try:
        size = path.stat().st_size
        if size == 0:
            return False
        with path.open("rb") as fh:
            fh.seek(size - 1)
            return fh.read(1) == b"\n"
    except OSError:
        return True


def _valid_prefix(path: Path) -> tuple[int, int, int | None, int | None]:
    """Bytes of the header + leading complete, parseable event lines; events; first/last ts."""
    valid = 0
    events = 0
    first: int | None = None
    last: int | None = None
    with path.open("rb") as fh:
        header = fh.readline()
        if not header.endswith(b"\n"):
            return 0, 0, None, None
        valid = len(header)
        for raw in fh:
            if not raw.endswith(b"\n"):
                break
            try:
                obj = json.loads(raw)
                ts = int(obj["timestamp_ns"])
                if not isinstance(obj.get("event_type"), str):
                    break
            except (ValueError, KeyError, TypeError):
                break
            valid += len(raw)
            events += 1
            first = ts if first is None else first
            last = ts
    return valid, events, first, last


def _note(device: DeviceDescriptor) -> str:
    if device.kind.value == "simulated" and device.device_id.startswith("sim-"):
        return "Synthetic data from a BrainOS simulated profile."
    if device.synthetic:
        return "Synthetic data (declared by the source)."
    if device.kind.value == "replay":
        return "Prerecorded data received over a live protocol (declared by the source)."
    return ""
