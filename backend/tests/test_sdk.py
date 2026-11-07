"""Python SDK end-to-end against a real uvicorn server (AT-20)."""

from __future__ import annotations

import asyncio

import pytest

from brainos.sdk import (
    BrainOSError,
    EventStream,
    NegotiationUpdate,
    RuntimeClient,
    ServerNotice,
    is_event,
)


async def test_sdk_negotiates_receives_ordered_events_and_survives_switch(live_server: str) -> None:
    """AT-20: SDK negotiates, receives ordered valid events, follows a device switch."""
    async with RuntimeClient(live_server) as rc:
        devices = await rc.devices()
        assert {d.device_id for d in devices} == {"sim-a", "sim-b"}
        await rc.connect("sim-a")
        async with await EventStream.connect(
            app_id="sdk-test",
            app_name="SDK test",
            required=["selection"],
            optional=["pointer_intent", "text_intent", "device_status"],
            base_url=live_server,
        ) as stream:
            assert stream.negotiation.status == "active"
            seen_devices: set[str] = set()
            switched = False
            negotiations: list[NegotiationUpdate] = []

            async def consume() -> None:
                nonlocal switched
                async for item in stream:
                    if isinstance(item, NegotiationUpdate):
                        negotiations.append(item)
                    elif is_event(item):
                        seen_devices.add(item.device_id)
                        if (
                            item.device_id == "sim-a"
                            and stream.stats.received > 20
                            and not switched
                        ):
                            switched = True
                            await rc.switch("sim-b")
                    if "sim-b" in seen_devices:
                        return

            await asyncio.wait_for(consume(), 10)
            assert seen_devices == {"sim-a", "sim-b"}
            assert negotiations[-1].negotiation.device_id == "sim-b"
            assert "text_intent" in negotiations[-1].negotiation.granted
            assert stream.stats.out_of_order == 0
            assert stream.stats.delivery_gaps == 0
            assert stream.stats.invalid == 0
        diag = await rc.diagnostics()
        assert diag["switches"][-1]["to_device"] == "sim-b"


async def test_sdk_unknown_capability_raises(live_server: str) -> None:
    with pytest.raises(BrainOSError) as info:
        await EventStream.connect(
            app_id="x", app_name="x", required=["levitation"], base_url=live_server
        )
    assert info.value.code == "unknown_capability"


async def test_sdk_rest_errors_are_typed(live_server: str) -> None:
    async with RuntimeClient(live_server) as rc:
        with pytest.raises(BrainOSError) as info:
            await rc.connect("not-a-device")
        assert info.value.code == "device_not_found" and info.value.status == 404
        neg = await rc.negotiate(["pointer_intent"], device_id="sim-b")
        assert neg.status == "suspended"


async def test_sdk_reports_server_notices(live_server: str) -> None:
    async with await EventStream.connect(
        app_id="x", app_name="x", optional=["selection"], base_url=live_server
    ) as stream:
        assert stream.negotiation.status == "no_device"
        await stream.send_raw({"type": "write_register", "value": 1})

        async def first_notice() -> ServerNotice:
            async for item in stream:
                if isinstance(item, ServerNotice):
                    return item
            raise AssertionError("stream ended")

        notice = await asyncio.wait_for(first_notice(), 5)
        assert notice.code == "read_only_runtime"


async def test_clients_that_leave_during_handshake_are_unregistered(live_server: str) -> None:
    """Review #3: hello-then-close must not leave phantom subscribers behind."""
    import json

    import httpx
    import websockets

    url = live_server.replace("http://", "ws://") + "/api/v1/stream"
    hello = {
        "type": "hello",
        "protocol": "brainos.stream/1",
        "app": {"id": "ghost", "name": "ghost"},
        "capabilities": {"required": [], "optional": ["selection"]},
    }
    for _ in range(20):
        ws = await websockets.connect(url)
        await ws.send(json.dumps(hello))
        await ws.close()  # leave before reading the welcome
    async with httpx.AsyncClient() as http:
        for _ in range(100):
            apps = (await http.get(live_server + "/api/v1/runtime")).json()["apps"]
            if not apps:
                break
            await asyncio.sleep(0.05)
    assert apps == []
