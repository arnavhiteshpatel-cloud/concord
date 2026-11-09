"""Clean-room check of the developer distribution, from built wheels, in fresh virtualenvs.

Three roles, each in its own new environment, none touching the repository's sources:

1. **Adapter developer** — installs only ``concord-adapter-sdk``; scaffolds a new plugin with
   ``concord-adapter new``; installs it; ``concord-adapter check`` runs it through the real
   plugin host and validator; the scaffold's own test passes.
2. **Lab running Concord** — installs ``concordos[server]`` + the adapter SDK + that plugin;
   starts ``concord-server``; the plugin is discovered as compatible; configured; connected.
3. **Application developer** — installs only ``concord`` (the application SDK: pydantic,
   httpx, websockets — no server, no numpy); receives the plugin's signal through the SDK.
   ``concord-server`` in this environment fails with an install hint, not a traceback.
4. **Lab verifying acquisition** — installs only ``concord-hwval`` (numpy + pyxdf, no
   Concord); reads a recording that the lab's server (2) made from the plugin, including the
   source metadata Concord keeps in the recording header.

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
    "sdk": ROOT / "packages" / "concord-adapter-sdk",
    "decoder_sdk": ROOT / "packages" / "concord-decoder-sdk",  # concordos[server] needs it (M5)
    "concord": ROOT / "backend",
    "hwval": ROOT / "packages" / "concord-hwval",  # hardware-validation toolkit (M5)
}
UV = shutil.which("uv")


def run(cmd: list[str], **kw: object) -> subprocess.CompletedProcess[str]:
    print("$", " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run(  # type: ignore[call-overload]
        cmd, text=True, encoding="utf-8", errors="replace", capture_output=True, **kw
    )
    if r.returncode != 0:
        print(r.stdout[-4000:], r.stderr[-4000:], sep="\n")
        raise SystemExit(f"FAILED: {' '.join(str(c) for c in cmd)}")
    return r  # type: ignore[no-any-return]


WINDOWS = os.name == "nt"


def venv(path: Path) -> Path:
    if UV:
        run([UV, "venv", "-q", "-p", sys.executable, str(path)])
    else:
        run([sys.executable, "-m", "venv", str(path)])
    # Windows virtualenvs keep their programs in Scripts\ with an .exe suffix
    return path / "Scripts" / "python.exe" if WINDOWS else path / "bin" / "python"


def script(py: Path, name: str) -> Path:
    """A console script installed in the virtualenv of interpreter ``py``."""
    return py.parent / (f"{name}.exe" if WINDOWS else name)


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
from concord.sdk import EventStream, RuntimeClient, is_event

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
    tmp = Path(tempfile.mkdtemp(prefix="concord-dist-"))
    dist = tmp / "dist"
    print(f"workdir {tmp}")
    server: subprocess.Popen[str] | None = None
    try:
        build(dist)
        print("wheels:", sorted(p.name for p in dist.glob("*.whl")))

        # 1. adapter developer: only the adapter SDK
        dev = venv(tmp / "adapter-dev")
        install(dev, "concord-adapter-sdk", "pytest", find_links=dist)
        cli = script(dev, "concord-adapter")
        run(
            [
                str(cli),
                "new",
                "acme-amp",
                "--dir",
                str(tmp / "concord-acme-amp"),
                "--display",
                "ACME amplifier",
            ]
        )
        install(dev, "-e", str(tmp / "concord-acme-amp"), find_links=dist)
        out = run([str(cli), "check", "acme-amp", "--seconds", "1"]).stdout
        assert "OK" in out, out
        run([str(dev), "-m", "pytest", "-q", str(tmp / "concord-acme-amp" / "tests")])
        assert (
            run(
                [str(dev), "-c", "import importlib.util as u; print(u.find_spec('concord'))"]
            ).stdout.strip()
            == "None"
        )
        print("1. adapter developer: scaffolded, installed, checked, tested — without Concord")

        # 2. lab: Concord server + plugin, from wheels
        lab = venv(tmp / "lab")
        install(lab, "concordos[server]", "-e", str(tmp / "concord-acme-amp"), find_links=dist)
        port = free_port()
        env = {
            **os.environ,
            "CONCORD_PORT": str(port),
            "CONCORD_DATA_DIR": str(tmp / "data"),
            "CONCORD_REPORTS_DIR": str(tmp / "reports"),
            "CONCORD_STATIC_DIR": "",
            "CONCORD_LOG_LEVEL": "WARNING",
        }
        server = subprocess.Popen(
            [str(script(lab, "concord-server"))],
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",  # Windows pipes use the ANSI code page: never fail on decoding
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
        install(app, "concordos", find_links=dist)
        mods = run(
            [
                str(app),
                "-c",
                "import importlib.util as u; print([m for m in "
                "('fastapi','uvicorn','numpy','concord_adapter_sdk') if u.find_spec(m)])",
            ]
        ).stdout.strip()
        assert mods == "[]", f"application SDK pulled in server/numeric packages: {mods}"
        (tmp / "app.py").write_text(APP, encoding="utf-8")
        out = run([str(app), str(tmp / "app.py"), base, device_id]).stdout.strip()
        print(f"3. app developer (SDK only, deps: pydantic/httpx/websockets): {out}")
        r = subprocess.run(
            [str(script(app, "concord-server"))],
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        assert r.returncode != 0 and "concordos[server]" in (r.stderr + r.stdout), r
        print("   concord-server without the server extra: clear install hint")

        # 4. lab verifying acquisition: the hwval toolkit alone reads a lab-server recording
        http("POST", base + "/api/v1/runtime/connect", {"device_id": device_id})
        http("POST", base + "/api/v1/recordings/start", {"name": "dist-hwval"})
        time.sleep(1.5)
        http("POST", base + "/api/v1/recordings/stop", {})
        http("POST", base + "/api/v1/runtime/disconnect", {})
        recording = tmp / "data" / "recordings" / "dist-hwval.concord.jsonl"
        hw = venv(tmp / "hwval")
        install(hw, "concord-hwval", find_links=dist)
        mods = run(
            [
                str(hw),
                "-c",
                "import importlib.util as u; print([m for m in ('concord', 'fastapi') "
                "if u.find_spec(m)])",
            ]
        ).stdout.strip()
        assert mods == "[]", f"concord-hwval pulled in Concord: {mods}"
        hcli = script(hw, "concord-hwval")
        version = run([str(hcli), "--version"]).stdout.strip()
        json.loads(run([str(hcli), "equipment-template"]).stdout)
        info = json.loads(run([str(hcli), "inspect", str(recording)]).stdout)
        assert info["file_type"] == "Concord recording" and info["frames"] > 0, info
        assert info["device_id"] == device_id and info["source_metadata_in_header"], info
        assert "cannot be reconstructed" in info["timing"], info
        print(
            f"4. lab verification ({version}, without Concord): read {info['frames']} frames "
            f"of the server's recording; header source metadata present"
        )
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
