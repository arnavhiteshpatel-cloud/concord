"""``concord-certify``: certify a Concord source plugin (software checks only).

Examples::

    concord-certify example-mi-eeg
    concord-certify brainflow --device synthetic \\
        --protocol-reference "BrainFlow 5.23 BoardShim SYNTHETIC_BOARD"
    concord-certify bci2000 --option port=20321 --option declare_synthetic=true
    concord-certify my_pkg.plugin:MyPlugin --path ./src --duration 5

Exit code: 0 if the ``adapter_implementation`` level was achieved, 1 if not, 2 for usage
errors. Reports: ``<out>/<name>.certify.json`` and ``<out>/<name>.certify.md``.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from concord_certify import __version__
from concord_certify.report import report_schema, to_markdown, write
from concord_certify.runner import CertifyConfig, run


def _positive(text: str) -> float:
    try:
        x = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{text!r} is not a number") from None
    if not x > 0:
        raise argparse.ArgumentTypeError(f"{text!r} must be > 0")
    return x


def _tolerance(text: str) -> float:
    x = _positive(text)
    if x >= 1:
        raise argparse.ArgumentTypeError("--rate-tolerance is a fraction, e.g. 0.02 for 2 %")
    return x


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="concord-certify",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("plugin", nargs="?", help="entry-point name (concord.sources) or module:Class")
    ap.add_argument("--device", help="device key to open (default: the first discovered)")
    ap.add_argument(
        "--option",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="an open() option (repeatable)",
    )
    ap.add_argument(
        "--duration",
        type=_positive,
        default=20.0,
        help="main acquisition length in seconds (default 20)",
    )
    ap.add_argument(
        "--reopen-seconds",
        type=_positive,
        default=2.0,
        help="read time after each reopen (default 2)",
    )
    ap.add_argument(
        "--rate-tolerance",
        type=_tolerance,
        default=0.02,
        help="allowed |measured/nominal - 1| (default 0.02 = 2 %%)",
    )
    ap.add_argument(
        "--read-grace",
        type=_positive,
        default=5.0,
        help="seconds past the read timeout before a read counts as hung",
    )
    ap.add_argument(
        "--start-timeout",
        type=_positive,
        default=30.0,
        help="plugin host start / import timeout (s)",
    )
    ap.add_argument("--open-timeout", type=_positive, default=30.0, help="open() timeout (s)")
    ap.add_argument(
        "--kill-detect-limit",
        type=_positive,
        default=2.0,
        help="max seconds for a killed host to surface as a link loss",
    )
    ap.add_argument("--python", help="interpreter for the plugin host (default: this one)")
    ap.add_argument(
        "--path",
        action="append",
        default=[],
        metavar="DIR",
        help="extra sys.path entry for the plugin host (repeatable)",
    )
    ap.add_argument(
        "--no-runtime",
        action="store_true",
        help="skip the Concord runtime phase even if Concord is installed",
    )
    ap.add_argument(
        "--runtime-seconds",
        type=_positive,
        default=5.0,
        help="how long the runtime phase streams (default 5)",
    )
    ap.add_argument(
        "--protocol-reference",
        metavar="TEXT",
        help="operator statement: the external reference software that produced "
        'the data, e.g. "BrainFlow 5.23 BoardShim SYNTHETIC_BOARD"',
    )
    ap.add_argument("--attestation", type=Path, help="operator hardware-test attestation (JSON)")
    ap.add_argument(
        "--attestation-signature", type=Path, help="detached Ed25519 signature (default <file>.sig)"
    )
    ap.add_argument(
        "--attestation-public-key", type=Path, help="the operator's Ed25519 public key (PEM)"
    )
    ap.add_argument("--out", type=Path, default=Path("."), help="report directory (default .)")
    ap.add_argument("--name", help="report file stem (default: derived from the plugin)")
    ap.add_argument("--quiet", action="store_true", help="no progress output")
    ap.add_argument("--print-schema", action="store_true", help="print the report JSON Schema")
    ap.add_argument("--version", action="version", version=f"concord-certify {__version__}")
    return ap


def _stem(plugin: str, device: str | None) -> str:
    base = re.sub(r"[^A-Za-z0-9_.-]+", "-", plugin).strip("-") or "plugin"
    return f"{base}-{device}" if device else base


def main(argv: Sequence[str] | None = None) -> int:
    ap = parser()
    a = ap.parse_args(argv)
    if a.print_schema:
        sys.stdout.write(json.dumps(report_schema(), indent=1) + "\n")
        return 0
    if not a.plugin:
        ap.error("a plugin (entry-point name or module:Class) is required")
    options: dict[str, str] = {}
    for item in a.option:
        if "=" not in item:
            ap.error(f"--option {item!r} must be NAME=VALUE")
        k, _, val = item.partition("=")
        options[k.strip()] = val
    if a.attestation_signature is None and a.attestation is not None:
        a.attestation_signature = Path(str(a.attestation) + ".sig")
    logging.basicConfig(level=logging.ERROR, format="%(levelname)s %(name)s: %(message)s")

    def progress(msg: str) -> None:
        if not a.quiet:
            print(f"[certify] {msg}", file=sys.stderr, flush=True)

    cfg = CertifyConfig(
        plugin=a.plugin,
        device=a.device,
        options=options,
        duration_s=a.duration,
        reopen_s=a.reopen_seconds,
        rate_tolerance=a.rate_tolerance,
        read_grace_s=a.read_grace,
        start_timeout_s=a.start_timeout,
        open_timeout_s=a.open_timeout,
        kill_detect_limit_s=a.kill_detect_limit,
        python=a.python,
        extra_path=tuple(str(Path(p).resolve()) for p in a.path),
        runtime=not a.no_runtime,
        runtime_s=a.runtime_seconds,
        protocol_reference=a.protocol_reference,
        attestation=a.attestation,
        attestation_signature=a.attestation_signature,
        attestation_public_key=a.attestation_public_key,
    )
    report = run(cfg, progress)
    stem = a.name or _stem(a.plugin, a.device)
    json_path = a.out / f"{stem}.certify.json"
    md_path = a.out / f"{stem}.certify.md"
    write(report, json_path, md_path)
    s = report["summary"]
    if not a.quiet:
        for c in report["checks"]:
            print(f"  {c['status']:8s} {c['id']:28s} {c['reason']}", file=sys.stderr)
        print(f"[certify] wrote {json_path} and {md_path}", file=sys.stderr)
    print(f"level: {s['level'] or 'none'} - {s['level_statement']}")
    print(f"checks: {json.dumps(s['counts'])}")
    for b in s["blocking"][:10]:
        print(f"  blocking: {b}")
    code: int = s["exit_code"]
    return code


__all__ = ["main", "to_markdown"]

if __name__ == "__main__":
    raise SystemExit(main())
