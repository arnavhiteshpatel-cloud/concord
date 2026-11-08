"""Minimal Concord SDK example: negotiate capabilities and print standardized events.

    python backend/examples/print_events.py --connect sim-a

Run the server first (`make run`). This script is a *third-party application*:
it knows nothing about devices; it declares what it needs and adapts.
"""

from __future__ import annotations

import argparse
import asyncio

from concord.sdk import (
    ConcordError,
    EventStream,
    NegotiationUpdate,
    RuntimeClient,
    RuntimeUpdate,
    ServerNotice,
    is_event,
)


async def main(base_url: str, connect: str | None, limit: int) -> None:
    async with RuntimeClient(base_url) as rc:
        for d in await rc.devices():
            caps = ", ".join(c.capability for c in d.capabilities)
            print(f"device {d.device_id:<10} {d.display_name:<28} [{caps}]")
        if connect:
            try:
                await rc.connect(connect)
            except ConcordError as exc:
                print(f"connect: {exc.code} ({exc.message})")

    async with await EventStream.connect(
        app_id="example-printer",
        app_name="SDK example",
        required=["selection"],
        optional=["pointer_intent", "text_intent", "device_status"],
        base_url=base_url,
    ) as stream:
        print(
            f"negotiated: status={stream.negotiation.status} granted={stream.negotiation.granted}"
        )
        n = 0
        async for item in stream:
            if isinstance(item, NegotiationUpdate):
                print(
                    f"-- renegotiated for {item.negotiation.device_id}: {item.negotiation.granted}"
                )
            elif isinstance(item, RuntimeUpdate):
                continue
            elif isinstance(item, ServerNotice):
                print(f"!! {item.code}: {item.message}")
            elif is_event(item):
                n += 1
                print(
                    f"{item.seq:>6} {item.event_type:<17} {item.provenance.kind:<17} "
                    f"q={item.quality.score:.2f} {item.payload.model_dump()}"
                )
                if n >= limit:
                    break
        print(f"stats: {stream.stats.received} received, {stream.stats.delivery_gaps} gaps")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8000")
    ap.add_argument("--connect", default=None, help="device to connect first, e.g. sim-a")
    ap.add_argument("--limit", type=int, default=40)
    args = ap.parse_args()
    asyncio.run(main(args.url, args.connect, args.limit))
