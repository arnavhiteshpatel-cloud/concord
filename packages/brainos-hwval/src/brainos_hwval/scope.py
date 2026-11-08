"""What a verification run can support as evidence, and the equipment manifest.

The toolkit **never** sets a hardware-verified or human-validated status. The most a single
run can be is a *hardware-validation run candidate*: every required check passed, the operator
documented real acquisition hardware in a complete equipment manifest, nothing in either
recording declares the data synthetic or prerecorded, the reference shows no file playback
(e.g. the Open Ephys File Reader), and the run is long enough. Whether a device is
"hardware-verified" (docs/VALIDATION_LEVELS.md level 3) is decided by people following
docs/HARDWARE_VALIDATION.md over several such runs, not by this program.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from brainos_hwval.model import Category, Check, InputError, Status

EQUIPMENT_FORMAT = "brainos-hwval.equipment/1"
SOURCE_KINDS = (
    "acquisition_hardware",  # a real amplifier / acquisition board digitising an input
    "signal_generator_through_hardware",  # a known test signal through the real hardware
    "file_playback",  # acquisition software replaying a file (not hardware)
    "software_simulator",  # a software publisher or simulator (not hardware)
)
HARDWARE_KINDS = frozenset(SOURCE_KINDS[:2])
HARDWARE_RUN_MIN_OVERLAP_S = 240.0

REQUIRED_FIELDS: tuple[tuple[str, ...], ...] = (
    ("laboratory",),
    ("operator",),
    ("date",),
    ("signal_source", "kind"),
    ("signal_source", "description"),
    ("acquisition_hardware", "manufacturer"),
    ("acquisition_hardware", "model"),
    ("acquisition_hardware", "serial_number"),
    ("acquisition_hardware", "firmware"),
    ("acquisition_software", "name"),
    ("acquisition_software", "version"),
    ("reference_recorder", "name"),
    ("reference_recorder", "version"),
    ("brainos", "version"),
    ("hosts",),
)


def equipment_template() -> dict[str, Any]:
    return {
        "format": EQUIPMENT_FORMAT,
        "laboratory": "",
        "operator": "",
        "date": "YYYY-MM-DD",
        "run_id": "",
        "signal_source": {
            "kind": " | ".join(SOURCE_KINDS),
            "description": "e.g. 10 Hz 100 uV sine from <generator model> into channels 1-8 "
            "through the headstage test board",
        },
        "acquisition_hardware": {
            "manufacturer": "",
            "model": "",
            "serial_number": "",
            "firmware": "",
            "headstage_or_amplifier": "",
            "sample_rate_hz": None,
            "channels": None,
        },
        "acquisition_software": {"name": "", "version": "", "plugins": []},
        "reference_recorder": {"name": "LabRecorder | Open Ephys Record Node", "version": ""},
        "brainos": {"version": "", "commit": "", "host": ""},
        "hosts": [{"name": "", "os": "", "cpu": "", "clock_sync": "NTP | PTP | none"}],
        "network": "",
        "notes": "",
    }


def load_equipment(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise InputError(f"equipment manifest not found: {path}") from exc
    except (OSError, ValueError) as exc:
        raise InputError(f"equipment manifest {path}: not valid JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("format") != EQUIPMENT_FORMAT:
        raise InputError(
            f"equipment manifest {path}: expected a JSON object with "
            f'"format": "{EQUIPMENT_FORMAT}" (see `brainos-hwval equipment-template`)'
        )
    return data


def _get(d: Any, path: tuple[str, ...]) -> Any:
    for k in path:
        if not isinstance(d, dict):
            return None
        d = d.get(k)
    return d


def _filled(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, str):
        s = v.strip()
        return bool(s) and s != "YYYY-MM-DD" and "|" not in s
    if isinstance(v, list):
        return bool(v) and all(_filled(x) if isinstance(x, str) else True for x in v)
    return True


def equipment_check(equipment: dict[str, Any] | None) -> Check:
    if equipment is None:
        return Check(
            "EQUIPMENT",
            "Acquisition hardware and software are documented",
            Category.SCOPE,
            False,
            Status.NOT_TESTED,
            "no equipment manifest given (--equipment); the run is not traceable to hardware",
            "Required fields of the brainos-hwval.equipment/1 manifest must be filled in.",
            {},
        )
    missing = [".".join(p) for p in REQUIRED_FIELDS if not _filled(_get(equipment, p))]
    kind = _get(equipment, ("signal_source", "kind"))
    bad_kind = isinstance(kind, str) and _filled(kind) and kind not in SOURCE_KINDS
    problems = missing + (
        [f"signal_source.kind {kind!r} not one of {SOURCE_KINDS}"] if bad_kind else []
    )
    return Check(
        "EQUIPMENT",
        "Acquisition hardware and software are documented",
        Category.SCOPE,
        False,
        Status.FAIL if problems else Status.PASS,
        ("incomplete manifest: " + ", ".join(problems)) if problems else "manifest complete",
        "Required fields of the brainos-hwval.equipment/1 manifest must be filled in.",
        {"missing_or_invalid": problems, "manifest": equipment},
    )


def evidence_scope(
    *,
    protocol: str,
    verdict: Status,
    overlap_s: float,
    equipment: dict[str, Any] | None,
    equipment_ok: bool,
    playback_or_synthetic: list[str],
) -> dict[str, Any]:
    kind = _get(equipment, ("signal_source", "kind")) if equipment else None
    reasons: list[str] = []
    if verdict is not Status.PASS:
        reasons.append(f"the comparison result is {verdict.value}, not pass")
    if kind not in HARDWARE_KINDS:
        reasons.append(
            "the operator did not declare acquisition hardware as the signal source"
            if kind is None
            else f"declared signal source is {kind!r}, not acquisition hardware"
        )
    if equipment is not None and not equipment_ok:
        reasons.append("the equipment manifest is incomplete")
    if equipment is None:
        reasons.append("no equipment manifest")
    reasons.extend(playback_or_synthetic)
    if overlap_s < HARDWARE_RUN_MIN_OVERLAP_S:
        reasons.append(
            f"overlap {overlap_s:.0f} s < {HARDWARE_RUN_MIN_OVERLAP_S:.0f} s required for a "
            "hardware-validation run"
        )
    candidate = not reasons
    if verdict is Status.PASS:
        level = "hardware_run_candidate" if candidate else "software_acquisition_comparison"
    else:
        level = "none"
    statements = {
        "hardware_run_candidate": (
            "This run meets the per-run criteria of docs/HARDWARE_VALIDATION.md §9. It is one "
            "run of the protocol; hardware compatibility is established only when the complete "
            "protocol (all runs, failure injection, timing test) is reviewed and signed by the "
            "laboratory."
        ),
        "software_acquisition_comparison": (
            f"BrainOS received, over {protocol}, exactly the data the reference software "
            "recorded from the same source, within the stated tolerances. This is software-level "
            "evidence about the acquisition path; it says nothing about hardware unless the "
            "source was real hardware and the hardware criteria below are met."
        ),
        "none": "The comparison did not pass; this run supports no compatibility claim.",
    }
    return {
        "level": level,
        "hardware_verified": False,
        "human_validated": False,
        "statement": statements[level],
        "not_a_hardware_run_because": reasons,
        "note": "brainos-hwval never sets hardware_verified or human_validated "
        "(docs/VALIDATION_LEVELS.md, docs/HARDWARE_VALIDATION.md).",
    }
