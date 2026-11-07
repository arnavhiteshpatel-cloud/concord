"""REST + WebSocket transport (AT-18, AT-19, AT-21)."""

from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from brainos.contracts import SCHEMA_VERSION, parse_envelope
from brainos.server import create_app

from .conftest import make_settings

HELLO: dict[str, Any] = {
    "type": "hello",
    "protocol": "brainos.stream/1",
    "app": {"id": "t", "name": "test"},
    "capabilities": {"required": ["selection"], "optional": ["pointer_intent", "text_intent"]},
}


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(make_settings(tmp_path))) as c:
        yield c


def _err(resp: Any) -> str:
    code: str = resp.json()["error"]["code"]
    return code


def test_rest_lifecycle(client: TestClient) -> None:
    """AT-18: devices, connect, pause/resume, switch, disconnect, diagnostics."""
    health = client.get("/api/v1/health").json()
    assert health["read_only"] is True and health["schema_version"] == SCHEMA_VERSION
    devices = {d["device_id"]: d for d in client.get("/api/v1/devices").json()}
    assert set(devices) == {"sim-a", "sim-b"}
    assert all(d["synthetic"] for d in devices.values())
    assert client.get("/api/v1/devices/sim-b").json()["display_name"] == "Simulated Profile B"
    assert client.get("/api/v1/devices/nope").status_code == 404

    assert client.get("/api/v1/runtime").json()["state"] == "idle"
    r = client.post("/api/v1/runtime/connect", json={"device_id": "sim-a"})
    assert r.status_code == 200 and r.json()["state"] == "streaming"
    r = client.post("/api/v1/runtime/connect", json={"device_id": "sim-b"})
    assert r.status_code == 409 and _err(r) == "invalid_state"
    assert client.post("/api/v1/runtime/pause").json()["state"] == "paused"
    assert client.post("/api/v1/runtime/pause").status_code == 409
    assert client.post("/api/v1/runtime/resume").json()["state"] == "streaming"
    time.sleep(0.3)
    r = client.post("/api/v1/runtime/switch", json={"device_id": "sim-b"})
    assert r.json()["device"]["device_id"] == "sim-b"
    diag = client.get("/api/v1/diagnostics").json()
    assert diag["counters"]["events_published"] > 0
    assert diag["switches"][-1]["to_device"] == "sim-b"
    assert diag["pipeline_latency"]["count"] > 0
    assert client.post("/api/v1/runtime/disconnect").json()["state"] == "idle"


def test_rest_validation_errors(client: TestClient) -> None:
    assert client.post("/api/v1/runtime/connect", json={}).status_code == 422
    r = client.post("/api/v1/runtime/connect", json={"device_id": "ghost"})
    assert r.status_code == 404 and _err(r) == "device_not_found"
    r = client.post("/api/v1/runtime/connect", json={"device_id": "sim-a", "x": 1})
    assert r.status_code == 422


def test_negotiate_dry_run(client: TestClient) -> None:
    """AT-18: negotiation preview, explicit rejection, unknown capability error."""
    r = client.post(
        "/api/v1/negotiate",
        json={"device_id": "sim-b", "required": ["selection"], "optional": ["pointer_intent"]},
    ).json()
    assert r["status"] == "active" and r["granted"] == ["selection"]
    assert r["rejected"][0]["reason"] == "unsupported_by_device"
    r2 = client.post("/api/v1/negotiate", json={"required": ["telekinesis"]})
    assert r2.status_code == 422 and _err(r2) == "unknown_capability"


def test_schema_and_capabilities_endpoints(client: TestClient) -> None:
    schema = client.get("/api/v1/schema/event").json()
    assert "BrainOS EventEnvelope" in schema["title"]
    caps = {c["capability"]: c for c in client.get("/api/v1/capabilities").json()}
    assert caps["recording"]["event_types"] == ["recording.frame", "recording.annotation"]
    assert (
        len(caps) == 9
    )  # schema 1.1 added neural_features, behavior, kinematic_intent (1.2: none)


def _recv_until(ws: Any, pred: Any, limit: int = 500) -> dict[str, Any]:
    for _ in range(limit):
        msg: dict[str, Any] = ws.receive_json()
        if pred(msg):
            return msg
    raise AssertionError("message not received")


def test_ws_stream_negotiates_and_delivers(client: TestClient) -> None:
    """AT-19: hello -> welcome, granted-only events, contiguous delivery_seq, valid envelopes."""
    client.post("/api/v1/runtime/connect", json={"device_id": "sim-a"})
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_json(HELLO)
        welcome = ws.receive_json()
        assert welcome["type"] == "welcome"
        assert welcome["negotiation"]["status"] == "active"
        assert set(welcome["negotiation"]["granted"]) == {"selection", "pointer_intent"}
        last = None
        for _ in range(30):
            msg = _recv_until(ws, lambda m: m["type"] == "event")
            env = parse_envelope(msg["event"])
            assert env.capability.value in {"selection", "pointer_intent"}
            if last is not None:
                assert msg["delivery_seq"] == last + 1
            last = msg["delivery_seq"]
        ws.send_json({"type": "ping", "nonce": "n1"})
        assert _recv_until(ws, lambda m: m["type"] == "pong")["nonce"] == "n1"
        apps = client.get("/api/v1/runtime").json()["apps"]
        assert [a["app"]["id"] for a in apps] == ["t"]
    time.sleep(0.05)
    assert client.get("/api/v1/runtime").json()["apps"] == []


def test_ws_read_only_rejects_other_messages(client: TestClient) -> None:
    """AT-19 / FR-12: anything other than ping is answered with read_only_runtime."""
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_json(HELLO)
        assert ws.receive_json()["type"] == "welcome"
        ws.send_json({"type": "stimulate", "amplitude_ua": 50})
        err = _recv_until(ws, lambda m: m["type"] == "error")
        assert err["code"] == "read_only_runtime"
        ws.send_text("not json")
        assert _recv_until(ws, lambda m: m["type"] == "error")["code"] == "protocol_error"


@pytest.mark.parametrize(
    ("first", "code"),
    [
        ({"type": "subscribe"}, "hello_required"),
        ({**HELLO, "capabilities": {"required": ["telepathy"]}}, "unknown_capability"),
        ({**HELLO, "protocol": "brainos.stream/0"}, "unsupported_protocol"),
        ({"type": "hello", "protocol": "brainos.stream/1"}, "protocol_error"),
        ("garbage", "protocol_error"),
    ],
)
def test_ws_handshake_errors_close_connection(client: TestClient, first: Any, code: str) -> None:
    """AT-19: bad first message -> error + close (1008)."""
    with client.websocket_connect("/api/v1/stream") as ws:
        if isinstance(first, str):
            ws.send_text(first)
        else:
            ws.send_json(first)
        err = ws.receive_json()
        assert err["type"] == "error" and err["code"] == code
        with pytest.raises(WebSocketDisconnect) as info:
            ws.receive_json()
        assert info.value.code == 1008


def test_ws_receives_negotiation_on_switch(client: TestClient) -> None:
    client.post("/api/v1/runtime/connect", json={"device_id": "sim-a"})
    with client.websocket_connect("/api/v1/stream") as ws:
        ws.send_json(HELLO)
        ws.receive_json()
        client.post("/api/v1/runtime/switch", json={"device_id": "sim-b"})
        # a switch is disconnect + connect: apps see a transient no_device, then the new device
        first = _recv_until(ws, lambda m: m["type"] == "negotiation")["negotiation"]
        assert first["status"] == "no_device"
        neg = _recv_until(ws, lambda m: m["type"] == "negotiation")["negotiation"]
        assert neg["device_id"] == "sim-b"
        assert set(neg["granted"]) == {"selection", "text_intent"}


def test_sim_endpoints_reject_unsupported_intents(client: TestClient) -> None:
    """AT-21: simulation inputs a profile does not support -> 409 capability_unsupported."""
    r = client.post("/api/v1/sim/select")
    assert r.status_code == 409 and _err(r) == "invalid_state"  # nothing connected
    client.post("/api/v1/runtime/connect", json={"device_id": "sim-a"})
    assert client.post("/api/v1/sim/pointer", json={"vx": 0.5, "vy": 0}).status_code == 200
    assert client.post("/api/v1/sim/select").status_code == 200
    r = client.post("/api/v1/sim/text", json={"text": "a"})
    assert r.status_code == 409 and _err(r) == "capability_unsupported"
    assert client.post("/api/v1/sim/pointer", json={"vx": 5, "vy": 0}).status_code == 422
    client.post("/api/v1/runtime/switch", json={"device_id": "sim-b"})
    r = client.post("/api/v1/sim/pointer", json={"vx": 0.5, "vy": 0})
    assert r.status_code == 409 and _err(r) == "capability_unsupported"
    assert client.post("/api/v1/sim/text", json={"text": "a"}).status_code == 200
    status = client.get("/api/v1/sim").json()
    assert status["accepts"] == ["selection", "text_intent"]
    assert client.post("/api/v1/sim/faults", json={"fault": "melt"}).status_code == 422
    assert client.post("/api/v1/sim/faults", json={"fault": "link_drop"}).status_code == 200


def test_sim_disabled(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path, enable_sim=False))) as c:
        assert c.post("/api/v1/sim/select").status_code == 404
        assert c.get("/api/v1/health").json()["simulation_enabled"] is False


def test_recordings_api(client: TestClient) -> None:
    assert client.post("/api/v1/recordings/start", json={}).status_code == 409
    client.post("/api/v1/runtime/connect", json={"device_id": "sim-b"})
    r = client.post("/api/v1/recordings/start", json={"name": "demo-1"})
    assert r.json() == {"name": "demo-1"}
    assert client.get("/api/v1/runtime").json()["recording"] == "demo-1"
    time.sleep(0.3)
    info = client.post("/api/v1/recordings/stop").json()
    assert info["name"] == "demo-1" and info["events"] > 0
    assert client.post("/api/v1/recordings/start", json={"name": "Bad Name!"}).status_code == 409
    assert [r["name"] for r in client.get("/api/v1/recordings").json()] == ["demo-1"]
    ids = [d["device_id"] for d in client.get("/api/v1/devices").json()]
    assert "replay:demo-1" in ids
    r = client.post("/api/v1/runtime/switch", json={"device_id": "replay:demo-1"})
    assert r.json()["device"]["kind"] == "replay"
    assert client.post("/api/v1/sim/select").status_code == 409  # not a simulated device


def test_test_reports_endpoint(client: TestClient, tmp_path: Path) -> None:
    reports = client.get("/api/v1/system/tests").json()
    assert [r["available"] for r in reports] == [False, False, False]
    rdir = tmp_path / "reports"
    rdir.mkdir()
    (rdir / "pytest-junit.xml").write_text(
        '<testsuites><testsuite name="s"><testcase classname="a" name="ok" time="0.1"/>'
        '<testcase classname="a" name="bad" time="0.2"><failure message="boom"/></testcase>'
        '<testcase classname="a" name="skip"><skipped message="x"/></testcase>'
        "</testsuite></testsuites>"
    )
    (rdir / "e2e.json").write_text(json.dumps({"steps": [{"name": "s1", "ok": True}]}))
    reports = client.get("/api/v1/system/tests").json()
    py = reports[0]
    assert (py["total"], py["passed"], py["failed"], py["skipped"]) == (3, 1, 1, 1)
    assert py["cases"][1]["message"] == "boom"
    assert reports[2]["passed"] == 1


def test_corrupt_recording_files_do_not_break_listing(client: TestClient, tmp_path: Path) -> None:
    """Review #5: unreadable files in the recordings dir are skipped, not 500s."""
    rec = tmp_path / "data" / "recordings"
    rec.mkdir(parents=True)
    (rec / "binary.brainos.jsonl").write_bytes(b"\xff\xfe\x00garbage\n")
    (rec / "badver.brainos.jsonl").write_text(
        '{"format":"brainos.recording/1","schema_version":"x.0","created_at_ns":1,'
        '"device":{"device_id":"sim-a","display_name":"a","kind":"simulated","adapter":"a@1.0.0",'
        '"native_format":"-","capabilities":[],"synthetic":true},"synthetic":true}\n'
    )
    assert client.get("/api/v1/devices").status_code == 200
    assert client.get("/api/v1/recordings").json() == []
    assert client.get("/api/v1/devices/replay:binary").status_code == 404
