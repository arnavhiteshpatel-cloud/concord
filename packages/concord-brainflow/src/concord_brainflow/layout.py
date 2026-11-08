"""Map a BrainFlow board description (``BoardShim.get_board_descr``) to Concord streams.

Everything here is derived from the description BrainFlow itself returns; there are no
per-board tables except :data:`EXG_NOT_MICROVOLTS`, which repeats explicit statements in
BrainFlow's documentation.

Sources (BrainFlow 5.23.0, ``docs/DataFormatDesc.rst`` and ``docs/SupportedBoards.rst``):

* "For EXG channels BrainFlow returns uV wherever possible." -> EEG/EMG/ECG/EOG rows are
  declared in microvolts. No unit is documented for any other channel type, so those
  units are ``None`` (shown as "arbitrary").
* gForcePro / gForceDual: "Unlike other boards it returns ADC values instead uV." -> those
  boards' EXG rows have unit ``None``.
* "For timestamps BrainFlow uses UNIX timestamp ... Precision is microsecond, but for
  some boards timestamps are generated on PC side as soon as packages were received."
* BrainFlow's marker row is filled by ``Board::push_package`` from the queue of
  ``insert_marker`` calls made on the *same* session, and set to 0 otherwise
  (``src/board_controller/board.cpp``, ``push_package``). Markers stored in a playback file
  or inserted by a streaming producer therefore never arrive, and this read-only plugin
  never calls ``insert_marker`` — so no MARKERS stream is declared (it could never carry
  data).
* "For some boards like OpenBCI Cyton, OpenBCI Ganglion, etc we cannot separate EMG,
  EEG, EDA and ECG and in this case we return exactly the same array for all these
  methods." -> a row listed under several types is *ambiguous*; we do not guess.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from concord_adapter_sdk import Channel, ClockInfo, Modality, StreamRole, StreamSpec

EXG_TYPES = ("EEG", "EMG", "ECG", "EOG")
# Documented exceptions to "EXG in uV" (SupportedBoards.rst, OYMotion section).
EXG_NOT_MICROVOLTS = frozenset({"GFORCE_PRO_BOARD", "GFORCE_DUAL_BOARD"})
MICROVOLTS = "microvolts"
# Modalities Concord treats as noninvasive (contracts/protocol.py NONINVASIVE_MODALITIES).
_SINGLE_TYPE_MODALITY = {"EEG": Modality.EEG, "EMG": Modality.EMG}

EXG_STREAM = "exg"
AUX_STREAM = "aux"

UNIX_CLOCK = ClockInfo(
    "unix",
    "BrainFlow timestamp channel: UNIX time in seconds. For some boards BrainFlow stamps "
    "packages on the PC when they are received (BrainFlow docs, Data Format Description).",
)


@dataclass(frozen=True, slots=True)
class StreamRows:
    """Rows of BrainFlow's data table that make up one Concord stream."""

    spec: StreamSpec
    rows: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class BoardLayout:
    board_name: str  # the board whose description defines the data format
    sampling_rate: float
    package_num_row: int | None
    timestamp_row: int
    marker_row: int | None
    signal_streams: tuple[StreamRows, ...]  # exg first (primary) when present
    ambiguous_rows: tuple[int, ...]  # rows BrainFlow lists under more than one type

    @property
    def primary_stream(self) -> str:
        return self.signal_streams[0].spec.stream_id

    def specs(self) -> tuple[StreamSpec, ...]:
        return tuple(s.spec for s in self.signal_streams)


def _type_name(key: str) -> str | None:
    if key.endswith("_channels"):
        return key[: -len("_channels")].upper()
    if key == "battery_channel":
        return "BATTERY"
    return None


def _ordered(types: set[str]) -> tuple[str, ...]:
    exg = [t for t in EXG_TYPES if t in types]
    return (*exg, *sorted(types - set(EXG_TYPES)))


def row_types(descr: Mapping[str, Any]) -> dict[int, tuple[str, ...]]:
    """Every data row BrainFlow assigns a type to, with all the types it is listed under."""
    found: dict[int, set[str]] = {}
    for key, value in descr.items():
        name = _type_name(key)
        if name is None:
            continue
        rows = [value] if isinstance(value, int) else list(value)
        for row in rows:
            found.setdefault(int(row), set()).add(name)
    return {row: _ordered(types) for row, types in sorted(found.items())}


def _eeg_names(descr: Mapping[str, Any]) -> dict[int, str]:
    names_raw = descr.get("eeg_names")
    eeg_rows = descr.get("eeg_channels")
    if not isinstance(names_raw, str) or not isinstance(eeg_rows, list):
        return {}
    names = [n.strip() for n in names_raw.split(",")]
    if len(names) != len(eeg_rows) or any(not n for n in names) or len(set(names)) != len(names):
        return {}  # inconsistent description: fall back to generic labels
    return {int(r): n for r, n in zip(eeg_rows, names, strict=True)}


def _labels(
    rows: Sequence[int], types: Mapping[int, tuple[str, ...]], eeg_names: Mapping[int, str]
) -> list[str]:
    counters: dict[str, int] = {}
    labels: list[str] = []
    for row in rows:
        t = types[row]
        if row in eeg_names:
            label = eeg_names[row]
        elif len(t) == 1:
            counters[t[0]] = counters.get(t[0], 0) + 1
            label = f"{t[0].lower()}{counters[t[0]]}"
        else:
            label = f"row{row}"
        labels.append(label)
    seen: set[str] = set()
    out: list[str] = []
    for row, label in zip(rows, labels, strict=True):
        if label in seen:
            label = f"{label}_row{row}"
        seen.add(label)
        out.append(label)
    return out


def _unit(board_name: str, t: tuple[str, ...]) -> str | None:
    if board_name in EXG_NOT_MICROVOLTS:
        return None
    if all(x in EXG_TYPES for x in t):
        return MICROVOLTS
    return None


def build_layout(board_name: str, descr: Mapping[str, Any]) -> BoardLayout:
    """Build stream specs from ``descr`` (the DEFAULT preset of ``board_name``)."""
    try:
        sampling_rate = float(descr["sampling_rate"])
        timestamp_row = int(descr["timestamp_channel"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"BrainFlow description of {board_name} lacks {exc}") from exc
    package_row = descr.get("package_num_channel")
    marker_row = descr.get("marker_channel")
    types = row_types(descr)
    reserved = {timestamp_row, package_row, marker_row} - {None}
    types = {r: t for r, t in types.items() if r not in reserved}
    names = _eeg_names(descr)

    exg_rows = [r for r, t in types.items() if any(x in EXG_TYPES for x in t)]
    aux_rows = [r for r in types if r not in exg_rows]
    streams: list[StreamRows] = []
    if exg_rows:
        type_sets = {types[r] for r in exg_rows}
        modality: Modality | None = None
        if len(type_sets) == 1:
            only = next(iter(type_sets))
            if len(only) == 1:
                modality = _SINGLE_TYPE_MODALITY.get(only[0], Modality.OTHER)
        # EEG and surface EMG are noninvasive; anything else (ambiguous rows, ECG, EOG
        # declared as OTHER) stays None rather than being guessed.
        invasive = False if modality in (Modality.EEG, Modality.EMG) else None
        labels = _labels(exg_rows, types, names)
        channels = tuple(
            Channel(label=lab, unit=_unit(board_name, types[r]), type="|".join(types[r]))
            for r, lab in zip(exg_rows, labels, strict=True)
        )
        streams.append(
            StreamRows(
                StreamSpec(
                    stream_id=EXG_STREAM,
                    role=StreamRole.SIGNAL,
                    channels=channels,
                    nominal_rate_hz=sampling_rate,
                    clock=UNIX_CLOCK,
                    modality=modality,
                    invasive=invasive,
                ),
                tuple(exg_rows),
            )
        )
    if aux_rows:
        labels = _labels(aux_rows, types, names)
        channels = tuple(
            Channel(label=lab, unit=None, type="|".join(types[r]))
            for r, lab in zip(aux_rows, labels, strict=True)
        )
        streams.append(
            StreamRows(
                StreamSpec(
                    stream_id=AUX_STREAM,
                    role=StreamRole.SIGNAL,
                    channels=channels,
                    nominal_rate_hz=sampling_rate,
                    clock=UNIX_CLOCK,
                    # Non-neural sensors (accelerometer, PPG, battery...): not a recording
                    # modality Concord knows; invasiveness not declared.
                    modality=Modality.OTHER,
                    invasive=None,
                ),
                tuple(aux_rows),
            )
        )
    if not streams:
        raise ValueError(f"BrainFlow description of {board_name} has no data channels")
    return BoardLayout(
        board_name=board_name,
        sampling_rate=sampling_rate,
        package_num_row=None if package_row is None else int(package_row),
        timestamp_row=timestamp_row,
        marker_row=None if marker_row is None else int(marker_row),
        signal_streams=tuple(streams),
        ambiguous_rows=tuple(r for r, t in types.items() if len(t) > 1),
    )
