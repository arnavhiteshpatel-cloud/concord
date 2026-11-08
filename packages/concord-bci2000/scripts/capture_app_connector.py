"""Record what a genuine BCI2000 ConnectorOutput sends (raw datagrams + receive times).

Usage::

    python packages/concord-bci2000/scripts/capture_app_connector.py \
        --prog-dir /path/to/BCI2000/prog --out capture.json [--port 20321]

Needs a BCI2000 build with BCI2000Shell, Operator, SignalGenerator, DummySignalProcessing
and DummyApplication (see docs/ECOSYSTEMS.md). This is how
``tests/fixtures/bci2000_connector_output.json`` was recorded.
"""

from __future__ import annotations

import argparse
import json
import socket
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from bci2000_live import SAMPLE_BLOCK_SIZE, SAMPLING_RATE, SOURCE_CH, batch_script, run_bci2000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prog-dir", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--port", type=int, default=20321)
    ap.add_argument("--work", type=Path, default=Path("bci2000_capture_work"))
    args = ap.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", args.port))
    sock.settimeout(0.2)
    proc = run_bci2000(args.prog_dir, args.port, args.work)
    t0 = None
    got: list[list[object]] = []
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            data = sock.recv(65536)
        except TimeoutError:
            if proc.poll() is not None:
                break
            continue
        now = time.monotonic()
        t0 = now if t0 is None else t0
        got.append([round(now - t0, 6), data.decode("ascii")])
    proc.wait(timeout=30)
    log = proc.stdout.read().decode(errors="replace") if proc.stdout else ""
    args.out.write_text(
        json.dumps(
            {
                "description": (
                    "UDP datagrams sent by a genuine BCI2000 ConnectorOutput filter "
                    "(SignalGenerator + DummySignalProcessing + DummyApplication), with receive "
                    "times in seconds relative to the first datagram"
                ),
                "parameters": {
                    "SourceCh": SOURCE_CH,
                    "SampleBlockSize": SAMPLE_BLOCK_SIZE,
                    "SamplingRate": SAMPLING_RATE,
                },
                "script": batch_script(args.port, Path("<data>")),
                "operator_output": log[-2000:],
                "datagrams": got,
            },
            indent=0,
        )
    )
    print(f"{len(got)} datagrams -> {args.out}")


if __name__ == "__main__":
    main()
