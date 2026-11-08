"""``brainos-hwval``: verify BrainOS acquisition against an independent reference recording.

Compare (no BrainOS installation needed)::

    brainos-hwval lsl --reference session.xdf --brainos run1.brainos.jsonl
    brainos-hwval openephys --reference "~/data/2026-11-08_10-00-00/Record Node 102" \\
        --brainos run1.brainos.jsonl

Inspect a file before comparing::

    brainos-hwval inspect session.xdf
    brainos-hwval inspect "Record Node 102/experiment1/recording1"
    brainos-hwval inspect run1.brainos.jsonl

Record through BrainOS's own runtime (needs BrainOS installed)::

    brainos-hwval capture lsl --stream "MyAmp EEG" --duration 240 --out runs/ --name run1
    brainos-hwval capture openephys --host 127.0.0.1 --port 5556 --unit uV --duration 240 \\
        --out runs/ --name run1

Document the setup (for docs/HARDWARE_VALIDATION.md)::

    brainos-hwval equipment-template > equipment.json

Exit codes: 0 PASS, 1 FAIL, 3 INCONCLUSIVE, 2 usage or input error. Reports are written to
``--out`` as ``<name>.hwval.json`` and ``<name>.hwval.md``.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from brainos_hwval import __version__
from brainos_hwval.model import EXIT_CODES, EXIT_INPUT_ERROR, InputError, Status, Thresholds

log = logging.getLogger("brainos_hwval")


def _nonneg(text: str) -> float:
    try:
        x = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number") from None
    if not x >= 0:
        raise argparse.ArgumentTypeError(f"{text!r} must be >= 0")
    return x


def _positive(text: str) -> float:
    x = _nonneg(text)
    if x == 0:
        raise argparse.ArgumentTypeError(f"{text!r} must be > 0")
    return x


def _fraction(text: str) -> float:
    x = _nonneg(text)
    if x >= 1:
        raise argparse.ArgumentTypeError(f"{text!r} must be a fraction below 1 (e.g. 1e-6)")
    return x


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument(
        "--brainos",
        required=True,
        type=Path,
        metavar="FILE",
        help="BrainOS recording (*.brainos.jsonl)",
    )
    p.add_argument(
        "--equipment",
        type=Path,
        metavar="JSON",
        help="equipment manifest (brainos-hwval equipment-template)",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=Path("hwval-reports"),
        help="report directory (default: ./hwval-reports)",
    )
    p.add_argument("--name", help="report file stem (default: the BrainOS recording's name)")
    p.add_argument(
        "--max-loss-fraction",
        type=_fraction,
        default=0.0,
        help="fraction of reference samples BrainOS may miss (default 0)",
    )
    p.add_argument(
        "--min-overlap",
        type=_positive,
        default=5.0,
        metavar="SECONDS",
        help="minimum overlap for a conclusive comparison (default 5 s)",
    )
    p.add_argument(
        "--max-excess-delay",
        type=_positive,
        default=1.0,
        metavar="SECONDS",
        help="ingest delay above the best case that counts as delayed (default 1 s)",
    )
    p.add_argument("--json", action="store_true", help="also print the JSON report to stdout")


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="brainos-hwval",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--version", action="version", version=f"brainos-hwval {__version__}")
    ap.add_argument("-v", "--verbose", action="store_true")
    sub = ap.add_subparsers(dest="cmd", required=True)

    lsl = sub.add_parser("lsl", help="compare with an XDF file (LabRecorder)")
    lsl.add_argument(
        "--reference",
        required=True,
        type=Path,
        metavar="XDF",
        help="XDF file recorded by LabRecorder at the same time",
    )
    lsl.add_argument(
        "--stream",
        help="XDF stream name, stream id, uid or source_id "
        "(default: identified from the BrainOS recording)",
    )
    lsl.add_argument(
        "--sidecar",
        type=Path,
        metavar="JSON",
        help="<name>.capture.json from `brainos-hwval capture` (default: next to "
        "the BrainOS recording, if present)",
    )
    lsl.add_argument(
        "--value-rtol",
        type=_nonneg,
        default=2.5e-7,
        help="relative value tolerance (default 2.5e-7: single precision; "
        "0 demands bit-exact values)",
    )
    _common(lsl)

    oe = sub.add_parser("openephys", help="compare with an Open Ephys Binary recording")
    oe.add_argument(
        "--reference",
        required=True,
        type=Path,
        metavar="DIR",
        help="Record Node / experiment / recording directory (Binary format)",
    )
    oe.add_argument("--stream", help="stream name if the recording has several")
    oe.add_argument(
        "--quantisation-steps",
        type=_positive,
        default=0.51,
        help="value tolerance in units of bit_volts (default 0.51)",
    )
    _common(oe)

    ins = sub.add_parser("inspect", help="load and summarise one file or recording")
    ins.add_argument("path", type=Path)

    cap = sub.add_parser("capture", help="record through BrainOS's runtime (needs BrainOS)")
    capsub = cap.add_subparsers(dest="protocol", required=True)
    cl = capsub.add_parser("lsl", help="record an LSL stream")
    cl.add_argument("--stream", required=True, help="LSL stream name")
    cl.add_argument("--source-id", help="LSL source_id (if several streams share the name)")
    cl.add_argument("--host", help="LSL hostname (if several streams share the name)")
    co = capsub.add_parser("openephys", help="record the Open Ephys ZMQ Interface")
    co.add_argument("--host", default="127.0.0.1")
    co.add_argument("--port", type=int, default=5556, help="ZMQ Interface data port")
    co.add_argument(
        "--unit",
        default="unknown",
        choices=["unknown", "uV", "mV", "V"],
        help="unit configured in the GUI (the protocol does not transmit it)",
    )
    for c in (cl, co):
        c.add_argument("--duration", type=_positive, required=True, metavar="SECONDS")
        c.add_argument("--out", type=Path, required=True, help="output directory")
        c.add_argument(
            "--name", required=True, help="recording name ([a-z0-9][a-z0-9_-]*, max 48 chars)"
        )

    sub.add_parser("equipment-template", help="print an equipment manifest template")
    return ap


def _stem(args: argparse.Namespace) -> str:
    if args.name:
        return str(args.name)
    return Path(args.brainos).name.removesuffix(".brainos.jsonl").removesuffix(".jsonl")


def _print_summary(rep: dict[str, Any], paths: tuple[Path, Path]) -> None:
    print(f"Result: {rep['result'].upper()}")
    print(f"  {rep['result_explanation']}")
    print(f"  Evidence level: {rep['evidence_scope']['level']} (hardware verified: no)")
    for c in rep["checks"]:
        mark = {"pass": "ok  ", "fail": "FAIL", "inconclusive": "??  ", "not_tested": "--  "}[
            c["status"]
        ]
        req = "" if c["required"] else " (advisory)"
        print(f"  [{mark}] {c['id']}{req}: {c['summary']}")
    print(f"Reports: {paths[0]}\n         {paths[1]}")


def _compare(args: argparse.Namespace, argv: Sequence[str]) -> int:
    from brainos_hwval import report as R

    th_kwargs: dict[str, Any] = {
        "max_loss_fraction": args.max_loss_fraction,
        "min_overlap_s": args.min_overlap,
        "max_excess_delay_s": args.max_excess_delay,
    }
    cmd = ["brainos-hwval", *argv]
    if args.cmd == "lsl":
        from brainos_hwval.compare_lsl import LSLOptions, compare_lsl

        th_kwargs["value_rtol"] = args.value_rtol
        sidecar = args.sidecar
        if sidecar is None:
            guess = Path(str(args.brainos).removesuffix(".brainos.jsonl") + ".capture.json")
            sidecar = guess if guess.is_file() else None
        rep = compare_lsl(
            args.reference,
            args.brainos,
            LSLOptions(
                stream=args.stream,
                sidecar=sidecar,
                equipment=args.equipment,
                thresholds=Thresholds(**th_kwargs),
                command=cmd,
            ),
        )
    else:
        from brainos_hwval.compare_oe import OEOptions, compare_openephys

        th_kwargs["quantisation_steps"] = args.quantisation_steps
        rep = compare_openephys(
            args.reference,
            args.brainos,
            OEOptions(
                stream=args.stream,
                equipment=args.equipment,
                thresholds=Thresholds(**th_kwargs),
                command=cmd,
            ),
        )
    paths = R.write(rep, args.out, _stem(args))
    if args.json:
        print(json.dumps(rep, indent=1))
    else:
        _print_summary(rep, paths)
    return EXIT_CODES[Status(rep["result"])]


def _inspect(path: Path) -> dict[str, Any]:
    from brainos_hwval import brainos_rec, oe_ref, xdf_ref

    if path.is_dir() or path.name == "structure.oebin":
        rec = oe_ref.load_oe_recording(path)
        return {
            "kind": "Open Ephys Binary recording",
            "path": str(rec.path),
            "gui_version": rec.gui_version,
            "continuous": [c.describe() for c in rec.continuous],
            "ttl_event_folders": [
                {"folder": t.folder, "events": len(t.sample_numbers)} for t in rec.ttl
            ],
            "sync_messages": rec.sync_messages,
        }
    if path.suffix.lower() in (".xdf", ".xdfz"):
        hdr, streams = xdf_ref.load_xdf(path)
        return {
            "kind": "XDF",
            "path": str(path),
            "header": hdr,
            "streams": [
                s.describe() | {"clock_offsets": len(s.clock_times), "footer": s.footer}
                for s in streams
            ],
        }
    rec_b = brainos_rec.load_brainos_recording(path)
    return {"kind": "BrainOS recording"} | brainos_rec.summary(rec_b)


def main(argv: Sequence[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    ap = parser()
    args = ap.parse_args(argv)
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    try:
        if args.cmd in ("lsl", "openephys"):
            return _compare(args, argv)
        if args.cmd == "inspect":
            print(json.dumps(_inspect(args.path), indent=1, default=str))
            return 0
        if args.cmd == "equipment-template":
            from brainos_hwval.scope import equipment_template

            print(json.dumps(equipment_template(), indent=1))
            return 0
        if args.cmd == "capture":
            from brainos_hwval import capture

            if args.protocol == "lsl":
                rec, side = capture.capture_lsl(
                    stream=args.stream,
                    source_id=args.source_id,
                    hostname=args.host,
                    duration_s=args.duration,
                    out_dir=args.out,
                    name=args.name,
                )
            else:
                rec, side = capture.capture_openephys(
                    host=args.host,
                    data_port=args.port,
                    unit=args.unit,
                    duration_s=args.duration,
                    out_dir=args.out,
                    name=args.name,
                )
            print(f"BrainOS recording: {rec}\nSidecar:           {side}")
            return 0
    except InputError as exc:
        print(f"brainos-hwval: error: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    except Exception as exc:
        # capture: BrainOS runtime errors (device not found, connect failed) are reported
        # as such; anything else is a bug and is re-raised with its traceback.
        if type(exc).__name__ == "RuntimeCommandError":
            print(f"brainos-hwval: BrainOS could not record: {exc}", file=sys.stderr)
            return EXIT_INPUT_ERROR
        raise
    ap.error(f"unknown command {args.cmd}")
    return EXIT_INPUT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
