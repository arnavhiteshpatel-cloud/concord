"""Replay a recorded BCI2000 App Connector capture over UDP, looping, with original timing.

Used to certify the ``bci2000`` plugin without a running BCI2000: the datagrams are those a
genuine BCI2000 3.6 ConnectorOutput sent (``packages/brainos-bci2000/tests/fixtures/
bci2000_connector_output.json``), re-sent with their recorded inter-datagram timing.

Looping a capture needs two adjustments, both stated in the certification report's
``--protocol-reference`` / docs (nothing else is changed):

* the final block of the capture was truncated when BCI2000 stopped the run; it is not
  replayed (a truncated block at every loop boundary would look like loss);
* ``SourceTime`` (BCI2000's 16-bit millisecond acquisition clock) is advanced by one loop
  period on every loop, modulo 65536, so the replayed clock keeps running forward as a
  continuous BCI2000 run would. Loop periods are paced on that same clock.

Usage::

    python replay_bci2000_capture.py --port 20321 [--seconds 120] [--fixture PATH]
"""

from __future__ import annotations

import argparse
import itertools
import json
import socket
import statistics
import time
from pathlib import Path

DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "brainos-bci2000"
    / "tests"
    / "fixtures"
    / "bci2000_connector_output.json"
)


def load_blocks(path: Path) -> list[list[tuple[float, str]]]:
    raw = json.loads(path.read_text())["datagrams"]
    blocks: list[list[tuple[float, str]]] = []
    for t, text in raw:
        if text.startswith("Notes ") or not blocks:
            blocks.append([])
        blocks[-1].append((float(t), str(text)))
    full = statistics.mode(len(b) for b in blocks)
    complete = [b for b in blocks if len(b) == full]
    dropped = len(blocks) - len(complete)
    if dropped:
        print(f"[replay] {dropped} incomplete block(s) not replayed", flush=True)
    return complete


def source_time(block: list[tuple[float, str]]) -> int:
    for _, text in block:
        if text.startswith("SourceTime "):
            return int(text.split()[1])
    raise ValueError("block without SourceTime")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=20321)
    ap.add_argument("--seconds", type=float, default=120.0, help="stop after this long")
    a = ap.parse_args()
    blocks = load_blocks(a.fixture)
    st = [source_time(b) for b in blocks]
    steps = [(y - x) % 65536 for x, y in itertools.pairwise(st)]
    period_ms = (st[-1] - st[0]) % 65536 + round(statistics.median(steps))
    t_first = blocks[0][0][0]
    print(
        f"[replay] {len(blocks)} blocks of {len(blocks[0])} datagrams, loop period {period_ms} ms "
        f"(SourceTime), to {a.host}:{a.port}",
        flush=True,
    )
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    addr = (a.host, a.port)
    t0 = time.monotonic()
    loop = 0
    sent = 0
    try:
        while time.monotonic() - t0 < a.seconds:
            base = t0 + loop * period_ms / 1000.0
            shift = loop * period_ms
            for block in blocks:
                for t, text in block:
                    delay = base + (t - t_first) - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
                    if text.startswith("SourceTime "):
                        value = (int(text.split()[1]) + shift) % 65536
                        text = f"SourceTime {value}\n"
                    sock.sendto(text.encode("ascii"), addr)
                    sent += 1
            loop += 1
    except KeyboardInterrupt:
        pass
    finally:
        sock.close()
    print(f"[replay] sent {sent} datagrams in {loop} loop(s)", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
