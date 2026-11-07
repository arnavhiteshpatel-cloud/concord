"""Clean-room check of the developer distribution, from built wheels, in fresh virtualenvs.

Three roles, each in its own new environment, none touching the repository's sources:

1. **Adapter developer** — installs only ``brainos-adapter-sdk``; scaffolds a new plugin with
   ``brainos-adapter new``; installs it; ``brainos-adapter check`` runs it through the real
   plugin host and validator; the scaffold's own test passes.
2. **Lab running BrainOS** — installs ``brainos[server]`` + the adapter SDK + that plugin;
   starts ``brainos-server``; the plugin is discovered as compatible; configured; connected.
3. **Application developer** — installs only ``brainos`` (the application SDK: pydantic,
   httpx, websockets — no server, no numpy); receives the plugin's signal through the SDK.
   ``brainos-server`` in this environment fails with an install hint, not a traceback.

Usage:  python scripts/dist_check.py [--keep]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WHEELS = {
    "sdk": ROOT / "packages" / "brainos-adapter-sdk",
    "brainos": ROOT / "backend",
}
UV = shutil.which("uv")


def run(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run(cmd, text=True, capture_output=True, **kw)  # type: ignore[call-overload]
    if r.returncode != 0:
        print(r.stdout[-4000:], r.stderr[-4000:], sep="\n")
        raise SystemExit(f"FAILED: {' '.join(str(c) for c in cmd)}")
    return r  # type: ignore[no-any-return]


def venv(path: Path) -> Path:
    if UV:
        run([UV, "venv", "-q", "-p", sys.executable, str(path)])
    else:
        run([sys.executable, "-m", "venv", str(path)])
    return path / "bin" / "python"


def install(py: Path, *specs: str, find_links: Path) -> None:
    if UV:
        run(
            [
                UV,
                "pip",
                "install",
                "-q",
                "--python",
                str(py),
                "--find-links",
                str(find_links),
                *specs,
            ]
        )
    else:
        run([str(py), "-m", "pip", "install", "-q", "--find-links", str(find_links), *specs])


def build(dist: Path) -> None:
    for src in WHEELS.values():
        if UV:
            run([UV, "build", "-q", "--wheel", "-o", str(dist), str(src)])
        else:
            run(
                [sys.executable, "-m", "pip", "wheel", "-q", "--no-deps", "-w", str(dist), str(src)]
            )


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def http(
    method: str, url: str, body: dict[str, object] | None = None, timeout: float = 30
) -> object:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(
        url, data=data, method=method, headers={"content-type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def http_text(url: str) -> str:
    """GET a page as text (M5-D lab acceptance: the console served from the wheel)."""
    with urllib.request.urlopen(url, timeout=30) as r:
        return str(r.read().decode("utf-8", "replace"))


APP = r"""
import asyncio, sys
from brainos.sdk import EventStream, RuntimeClient, is_event

async def main(base, device):
    async with RuntimeClient(base) as op:
        async with await EventStream.connect(app_id="dist-check-app", app_name="Dist check",
                                             optional=["recording"], base_url=base) as s:
            await op.connect(device)
            n = 0
            async def consume():
                nonlocal n
                async for item in s:
                    if is_event(item) and item.event_type.value == "recording.frame":
                        n += 1
                        if n >= 5:
                            return item
            item = await asyncio.wait_for(consume(), 20)
            await op.disconnect()
    p = item.payload
    print(f"received {n} frames; {p.channel_count} ch @ {p.sample_rate_hz} Hz, unit {p.unit}, "
          f"synthetic={item.provenance.synthetic}")

asyncio.run(main(sys.argv[1], sys.argv[2]))
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep", action="store_true", help="keep the temporary directory")
    args = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="brainos-dist-"))
    dist = tmp / "dist"
    print(f"workdir {tmp}")
    server: subprocess.Popen[str] | None = None
    try:
        build(dist)
        print("wheels:", sorted(p.name for p in dist.glob("*.whl")))

        # 1. adapter developer: only the adapter SDK
        dev = venv(tmp / "adapter-dev")
        install(dev, "brainos-adapter-sdk", "pytest", find_links=dist)
        cli = dev.parent / "brainos-adapter"
        run(
            [
                str(cli),
                "new",
                "acme-amp",
                "--dir",
                str(tmp / "brainos-acme-amp"),
                "--display",
                "ACME amplifier",
            ]
        )
        install(dev, "-e", str(tmp / "brainos-acme-amp"), find_links=dist)
        out = run([str(cli), "check", "acme-amp", "--seconds", "1"]).stdout
        assert "OK" in out, out
        run([str(dev), "-m", "pytest", "-q", str(tmp / "brainos-acme-amp" / "tests")])
        assert (
            run(
                [str(dev), "-c", "import importlib.util as u; print(u.find_spec('brainos'))"]
            ).stdout.strip()
            == "None"
        )
        print("1. adapter developer: scaffolded, installed, checked, tested — without BrainOS")

        # 2. lab: BrainOS server + plugin, from wheels
        lab = venv(tmp / "lab")
        install(lab, "brainos[server]", "-e", str(tmp / "brainos-acme-amp"), find_links=dist)
        port = free_port()
        env = {
            **os.environ,
            "BRAINOS_PORT": str(port),
            "BRAINOS_DATA_DIR": str(tmp / "data"),
            "BRAINOS_REPORTS_DIR": str(tmp / "reports"),
            "BRAINOS_STATIC_DIR": "",
            "BRAINOS_LOG_LEVEL": "WARNING",
        }
        server = subprocess.Popen(
            [str(lab.parent / "brainos-server")],
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        base = f"http://127.0.0.1:{port}"
        for _ in range(200):
            try:
                st = http("GET", base + "/api/v1/plugins")
                if isinstance(st, dict) and st.get("discovered_at_ns"):
                    break
            except OSError:
                pass
            time.sleep(0.1)
        else:
            raise SystemExit("server did not start / discover plugins")
        plugin = next(p for p in st["plugins"] if p["name"] == "acme-amp")  # type: ignore[index]
        assert plugin["status"] == "compatible", plugin
        dev_desc = http(
            "POST",
            base + "/api/v1/plugins/acme-amp/configure",
            {"device_key": "default", "options": {}},
        )
        device_id = dev_desc["device_id"]  # type: ignore[index]
        assert dev_desc["integration"]["isolated"] is True  # type: ignore[index]
        print(f"2. lab: server discovered acme-amp ({plugin['status']}), device {device_id}")

        # 3. app developer: the application SDK only
        app = venv(tmp / "app-dev")
        install(app, "brainos", find_links=dist)
        mods = run(
            [
                str(app),
                "-c",
                "import importlib.util as u; print([m for m in "
                "('fastapi','uvicorn','numpy','brainos_adapter_sdk') if u.find_spec(m)])",
            ]
        ).stdout.strip()
        assert mods == "[]", f"application SDK pulled in server/numeric packages: {mods}"
        (tmp / "app.py").write_text(APP)
        out = run([str(app), str(tmp / "app.py"), base, device_id]).stdout.strip()
        print(f"3. app developer (SDK only, deps: pydantic/httpx/websockets): {out}")
        r = subprocess.run([str(app.parent / "brainos-server")], text=True, capture_output=True)
        assert r.returncode != 0 and "brainos[server]" in (r.stderr + r.stdout), r
        print("   brainos-server without the server extra: clear install hint")
        print("DIST CHECK PASSED")
        return 0
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(10)
            except subprocess.TimeoutExpired:
                server.kill()
        if not args.keep:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
