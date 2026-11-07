from __future__ import annotations

import socket
import threading
import time
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn

from brainos.adapters.simulated import OperatorIntentSource
from brainos.contracts.capabilities import Capability
from brainos.contracts.protocol import AppInfo
from brainos.runtime import DeviceRegistry, Recorder, Runtime, Subscriber
from brainos.server import Settings, create_app

FAST_BACKOFF = (0.01, 0.02, 0.03)


@pytest.fixture
def intents() -> OperatorIntentSource:
    return OperatorIntentSource()


@pytest.fixture
def registry(tmp_path: Path, intents: OperatorIntentSource) -> DeviceRegistry:
    return DeviceRegistry(intents, tmp_path / "recordings", seed=1)


@pytest.fixture
async def runtime(registry: DeviceRegistry, tmp_path: Path) -> AsyncIterator[Runtime]:
    rt = Runtime(registry, Recorder(tmp_path / "recordings"), reconnect_backoff_s=FAST_BACKOFF)
    yield rt
    await rt.shutdown()


def subscribe(
    rt: Runtime,
    required: list[Capability] | None = None,
    optional: list[Capability] | None = None,
    app_id: str = "test",
) -> Subscriber:
    return rt.register_app(
        AppInfo(id=app_id, name=app_id),
        required or [],
        optional if optional is not None else list(Capability),
    )


@pytest.fixture
def publishers() -> Iterator[list[Any]]:
    """Test publishers (LSL / Open Ephys threads) stopped at teardown."""
    pubs: list[Any] = []
    yield pubs
    for p in pubs:
        p.stop()


def make_settings(tmp_path: Path, **overrides: object) -> Settings:
    base: dict[str, object] = {
        "data_dir": tmp_path / "data",
        "reports_dir": tmp_path / "reports",
        "static_dir": None,
        "reconnect_backoff_s": FAST_BACKOFF,
        "seed": 1,
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


@pytest.fixture
def live_server(tmp_path: Path) -> Iterator[str]:
    """A real uvicorn server on a free port in a background thread."""
    port = _free_port()
    config = uvicorn.Config(
        create_app(make_settings(tmp_path, port=port)),
        host="127.0.0.1",
        port=port,
        log_level="warning",
        ws_max_size=64 * 1024,
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        try:
            if httpx.get(base + "/api/v1/health", timeout=0.5).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.05)
    else:
        raise RuntimeError("server did not start")
    yield base
    server.should_exit = True
    thread.join(timeout=10)
