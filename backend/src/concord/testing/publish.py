"""Hardware-free test publishers, runnable from a terminal.

Each speaks a real protocol (liblsl outlets, or the Open Ephys ZMQ Interface wire format), so
Concord — or any other LSL / Open Ephys client — can be exercised without acquisition
hardware. Every stream is declared for what it is (synthetic, or prerecorded).

    python -m concord.testing.publish lsl-ephys --channels 32 --rate 30000
    python -m concord.testing.publish falcon data/datasets/dandi-000954/<file>.nwb --speed 1
    python -m concord.testing.publish openephys --port 5556 --channels 64

Stop with Ctrl-C (or ``--seconds``).
"""

from __future__ import annotations

import argparse
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Any


def _wait(seconds: float | None, done: threading.Event | None = None) -> None:
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    end = None if seconds is None else time.monotonic() + seconds
    while not stop.is_set() and (end is None or time.monotonic() < end):
        if done is not None and done.is_set():
            return
        stop.wait(0.1)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="kind", required=True)

    e = sub.add_parser("lsl-ephys", help="synthetic broadband ephys over LSL (declared synthetic)")
    e.add_argument("--channels", type=int, default=32)
    e.add_argument("--rate", type=float, default=30_000.0)
    e.add_argument("--chunk-ms", type=float, default=10.0)
    e.add_argument("--source-id", default="concord-synthetic-ephys")
    e.add_argument("--unit", default="microvolts", help="channel unit, or 'none' to omit")
    e.add_argument("--seed", type=int, default=0)
    e.add_argument("--no-latent", action="store_true", help="omit the latent velocity stream")

    f = sub.add_parser("falcon", help="a FALCON H1 NWB block over LSL (declared prerecorded)")
    f.add_argument("file", type=Path)
    f.add_argument("--speed", type=float, default=1.0)
    f.add_argument("--loop", action="store_true")
    f.add_argument("--source-prefix", default=None)

    o = sub.add_parser("openephys", help="Open Ephys ZMQ Interface wire format (synthetic)")
    o.add_argument("--host", default="127.0.0.1")
    o.add_argument("--port", type=int, default=5556, help="data port; heartbeat is port+1")
    o.add_argument("--channels", type=int, default=16)
    o.add_argument("--rate", type=float, default=30_000.0)
    o.add_argument("--block-size", type=int, default=1024)
    o.add_argument("--seed", type=int, default=0)

    for p in (e, f, o):
        p.add_argument("--seconds", type=float, default=None, help="stop after N seconds")
    args = ap.parse_args(argv)

    pub: Any
    if args.kind == "lsl-ephys":
        from concord.testing.lsl_publishers import SyntheticEphysPublisher

        pub = SyntheticEphysPublisher(
            channels=args.channels,
            fs=args.rate,
            chunk_ms=args.chunk_ms,
            source_id=args.source_id,
            unit=None if args.unit == "none" else args.unit,
            seed=args.seed,
            latent=not args.no_latent,
        )
        pub.start()
        print(
            f"LSL synthetic ephys: source_id={args.source_id} {args.channels} ch @ {args.rate:g} Hz"
        )
        _wait(args.seconds)
        pub.stop()
        print(f"pushed {pub.pushed} samples per channel")
    elif args.kind == "falcon":
        from concord.testing.lsl_publishers import FalconLSLPublisher

        pub = FalconLSLPublisher(
            args.file, speed=args.speed, loop=args.loop, source_prefix=args.source_prefix
        )
        pub.start()
        print(f"FALCON over LSL: prefix={pub.prefix} ({pub.origin}), declared prerecorded")
        _wait(args.seconds, pub.finished)
        pub.stop()
        print(f"published {pub.bins_published} bins")
    else:
        import numpy as np

        from concord.adapters.openephys.publisher import OpenEphysTestPublisher
        from concord.testing.lsl_publishers import SyntheticEphys

        gen = SyntheticEphys(channels=args.channels, fs=args.rate, seed=args.seed)

        def sig(_s: int, n: int, chans: tuple[int, ...]) -> Any:
            return gen.chunk(n).T[: len(chans)].astype(np.float32)

        pub = OpenEphysTestPublisher(
            data_port=args.port,
            host=args.host,
            sample_rate=args.rate,
            channels=tuple(range(args.channels)),
            block_size=args.block_size,
            signal=sig,
        ).start()
        print(
            f"Open Ephys ZMQ test publisher on tcp://{args.host}:{args.port} "
            f"(heartbeat {args.port + 1}), {args.channels} ch @ {args.rate:g} Hz, synthetic"
        )
        _wait(args.seconds)
        pub.stop()
        print(f"sent {pub.blocks_sent} blocks, {pub.messages_sent} messages")
    err = getattr(pub, "error", None)
    if err is not None:
        print(f"publisher failed: {err}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
