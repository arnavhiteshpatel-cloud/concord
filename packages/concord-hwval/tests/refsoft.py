"""Reference software for the tests: downloaded at test time, pinned by SHA-256, never committed.

* LabRecorder 1.16.4 (``LabRecorderCLI``) and liblsl 1.16.2 — official release packages from
  github.com/labstreaminglayer/App-LabRecorder and github.com/sccn/liblsl (MIT).
* Open Ephys GUI 1.1.0 for Linux and the ZMQ Interface plugin 1.0.0 (plugin API 10) — the
  official builds from openephys.jfrog.io (GPL-3: downloaded into a cache, never vendored).

The GUI is run headless: Xvfb provides the display and a PulseAudio null sink provides the
audio device whose callback drives the GUI's signal chain in real time (without an audio
device the GUI stops at a modal "No audio device found" dialog). HOME is a temporary
directory so the user's Open Ephys configuration is never touched. The GUI is controlled
through its documented HTTP API (port 37497).
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import tarfile
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CACHE = Path(os.environ.get("HWVAL_CACHE", Path.home() / ".cache" / "concord-hwval"))
REQUIRE = os.environ.get("HWVAL_REQUIRE_REFERENCE_SOFTWARE") == "1"


@dataclass(frozen=True)
class Artifact:
    name: str
    url: str
    sha256: str


LABRECORDER = Artifact(
    "LabRecorder-1.16.4-jammy_amd64.deb",
    "https://github.com/labstreaminglayer/App-LabRecorder/releases/download/v1.16.4/"
    "LabRecorder-1.16.4-jammy_amd64.deb",
    "d171e6d12c1c428115a66d8bccac41b31fd5a43f5bd0a311068786a5b944d823",
)
LIBLSL = Artifact(
    "liblsl-1.16.2-jammy_amd64.deb",
    "https://github.com/sccn/liblsl/releases/download/v1.16.2/liblsl-1.16.2-jammy_amd64.deb",
    "6043fbecef4b5e750b8158878156fae92de265ba450bd005ce4a8668830f7ebf",
)
OE_GUI = Artifact(
    "open-ephys-v1.1.0-linux.zip",
    "https://openephys.jfrog.io/artifactory/GUI-binaries/Release/linux/open-ephys-v1.1.0-linux.zip",
    "8ba047e6f10a9f27f3aab3f4ab29ad4245acdeb4981cf68ed493d2ea80a9b6d0",
)
OE_ZMQ = Artifact(
    "ZMQInterface-linux_1.0.0-API10.zip",
    "https://openephys.jfrog.io/artifactory/ZMQInterface-plugin/linux/"
    "ZMQInterface-linux_1.0.0-API10.zip",
    "0196349bab49adaa4b8c982b20a68a50a044a8a0688480dbf5adeb7d514f7ef1",
)
OE_API = "http://127.0.0.1:37497/api"


class Unavailable(Exception):
    """The reference software cannot run here (no network, missing system library, ...)."""


def fetch(a: Artifact) -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / a.name
    if not path.is_file():
        tmp = path.with_suffix(".part")
        try:
            with urllib.request.urlopen(a.url, timeout=120) as r, tmp.open("wb") as fh:
                shutil.copyfileobj(r, fh)
        except (urllib.error.URLError, OSError) as exc:
            tmp.unlink(missing_ok=True)
            raise Unavailable(f"cannot download {a.url}: {exc}") from exc
        tmp.rename(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != a.sha256:
        path.unlink()
        raise Unavailable(f"{a.name}: SHA-256 {digest} != pinned {a.sha256}")
    return path


def _deb_extract(deb: Path, dest: Path) -> None:
    """Extract a .deb's data.tar.* without dpkg (ar archive)."""
    data = deb.read_bytes()
    if not data.startswith(b"!<arch>\n"):
        raise Unavailable(f"{deb} is not an ar archive")
    pos = 8
    while pos < len(data):
        name = data[pos : pos + 16].decode().strip().rstrip("/")
        size = int(data[pos + 48 : pos + 58].decode().strip())
        body = data[pos + 60 : pos + 60 + size]
        if name.startswith("data.tar"):
            tmp = dest / name
            dest.mkdir(parents=True, exist_ok=True)
            tmp.write_bytes(body)
            with tarfile.open(tmp) as tf:
                tf.extractall(dest, filter="data")
            tmp.unlink()
            return
        pos += 60 + size + (size % 2)
    raise Unavailable(f"{deb}: no data.tar member")


@dataclass(frozen=True)
class LabRecorder:
    cli: Path
    lib_dir: Path
    version: str = "LabRecorder 1.16.4 (LabRecorderCLI) with liblsl 1.16.2"

    def env(self) -> dict[str, str]:
        return dict(os.environ, LD_LIBRARY_PATH=str(self.lib_dir))


def labrecorder() -> LabRecorder:
    root = CACHE / "labrecorder-1.16.4"
    cli = root / "usr" / "bin" / "LabRecorderCLI"
    lib = root / "usr" / "lib"
    if not cli.is_file():
        _deb_extract(fetch(LABRECORDER), root)
        _deb_extract(fetch(LIBLSL), root)
    so = lib / "liblsl.so.2"
    if not so.exists():
        so.symlink_to("liblsl.so.1.16.2")
    lr = LabRecorder(cli, lib)
    probe = subprocess.run([str(cli)], env=lr.env(), capture_output=True, text=True, timeout=20)
    if "Usage" not in probe.stdout + probe.stderr:
        raise Unavailable(
            "LabRecorderCLI does not start (missing system library? on Ubuntu install "
            f"libpugixml1v5): {probe.stderr.strip()[:300]}"
        )
    return lr


class LabRecorderRun:
    """LabRecorderCLI recording one stream until stopped (Enter on stdin)."""

    def __init__(self, lr: LabRecorder, out: Path, query: str) -> None:
        self.out = out
        self.proc = subprocess.Popen(
            [str(lr.cli), str(out), query],
            env=lr.env(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self.log = ""

    def wait_started(self, timeout: float = 20.0) -> None:
        # LabRecorderCLI prints "Started data collection" once the inlet is open; read it
        # from the file instead of the pipe (simpler): the header is written first.
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            if self.out.is_file() and self.out.stat().st_size > 2000:
                return
            if self.proc.poll() is not None:
                break
            time.sleep(0.1)
        self.stop()
        raise Unavailable(f"LabRecorderCLI did not start recording: {self.log[-800:]}")

    def stop(self) -> str:
        if self.proc.poll() is None:
            try:
                out, _ = self.proc.communicate(b"\n", timeout=30)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                out, _ = self.proc.communicate()
        else:
            out = self.proc.stdout.read() if self.proc.stdout else b""
        self.log += out.decode(errors="replace")
        return self.log


# ----------------------------------------------------------------------------- Open Ephys


def _free_display() -> int:
    for n in range(90, 140):
        if not Path(f"/tmp/.X11-unix/X{n}").exists() and not Path(f"/tmp/.X{n}-lock").exists():
            return n
    raise Unavailable("no free X display number")


def _port_free(port: int) -> bool:
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)  # ignore TIME_WAIT leftovers
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            return False
    return True


def _listening(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(1.0)
        return s.connect_ex(("127.0.0.1", port)) == 0


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = int(s.getsockname()[1])
    # the ZMQ Interface also binds port + 1 (heartbeats)
    return port if _port_free(port + 1) else free_port()


class OpenEphysGUI:
    """The official Open Ephys GUI, headless, controlled over its HTTP API."""

    version = "Open Ephys GUI 1.1.0 (Linux) + ZMQ Interface 1.0.0 (API 10)"

    def __init__(self, home: Path) -> None:
        self.home = home
        self.procs: list[subprocess.Popen[bytes]] = []
        self.gui_dir = CACHE / "open-ephys-1.1.0"
        self.env: dict[str, str] = {}
        self.log_path = home / "gui.log"

    def _install(self) -> None:
        if not (self.gui_dir / "open-ephys" / "open-ephys").is_file():
            with zipfile.ZipFile(fetch(OE_GUI)) as z:
                z.extractall(self.gui_dir)
            exe = self.gui_dir / "open-ephys" / "open-ephys"
            exe.chmod(0o755)
        cfg = self.home / ".config" / "open-ephys"
        plug = cfg / "plugins-api10"
        shared = cfg / "shared-api10"
        plug.mkdir(parents=True, exist_ok=True)
        shared.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(fetch(OE_ZMQ)) as z:
            for member in z.namelist():
                if member.endswith("zmq-interface.so"):
                    (plug / "zmq-interface.so").write_bytes(z.read(member))
                elif member.endswith("libzmq.so.5"):
                    (shared / "libzmq.so.5").write_bytes(z.read(member))

    def start(self, timeout: float = 90.0) -> None:
        for tool in ("Xvfb", "pulseaudio"):
            if shutil.which(tool) is None:
                raise Unavailable(
                    f"{tool} not installed (apt-get install xvfb pulseaudio libasound2-plugins)"
                )
        t_free = time.monotonic() + 15  # a previous GUI may still be shutting down
        while _listening(37497) and time.monotonic() < t_free:
            time.sleep(0.5)
        if _listening(37497):
            raise Unavailable("port 37497 (Open Ephys HTTP API) is in use")
        self._install()
        xdg = self.home / "xdg"
        xdg.mkdir(mode=0o700, parents=True, exist_ok=True)
        (self.home / ".asoundrc").write_text(
            "pcm.!default { type pulse }\nctl.!default { type pulse }\n"
        )
        disp = _free_display()
        self.env = dict(
            os.environ,
            HOME=str(self.home),
            DISPLAY=f":{disp}",
            XDG_RUNTIME_DIR=str(xdg),
            PULSE_RUNTIME_PATH=str(xdg / "pulse"),
        )
        self.env.pop("PULSE_SERVER", None)
        log = self.log_path.open("ab")
        self.procs.append(
            subprocess.Popen(
                ["Xvfb", f":{disp}", "-screen", "0", "1600x1000x24", "-nolisten", "tcp"],
                stdout=log,
                stderr=log,
            )
        )
        self.procs.append(
            subprocess.Popen(
                [
                    "pulseaudio",
                    "--daemonize=no",
                    "--exit-idle-time=-1",
                    "-n",
                    "--load=module-null-sink sink_name=hwval",
                    "--load=module-native-protocol-unix",
                    "--log-target=stderr",
                ],
                env=self.env,
                stdout=log,
                stderr=log,
            )
        )
        time.sleep(1.5)
        if any(p.poll() is not None for p in self.procs):
            self.stop()
            raise Unavailable(f"Xvfb/pulseaudio did not start: {self.log_path.read_text()[-800:]}")
        exe = self.gui_dir / "open-ephys" / "open-ephys"
        self.procs.append(
            subprocess.Popen([str(exe)], cwd=exe.parent, env=self.env, stdout=log, stderr=log)
        )
        t_end = time.monotonic() + timeout
        while time.monotonic() < t_end:
            if self.procs[-1].poll() is not None:
                break
            with contextlib.suppress(Exception):
                if self.api("GET", "/status").get("mode") == "IDLE":
                    return
            time.sleep(0.5)
        self.stop()
        raise Unavailable(f"Open Ephys GUI did not come up: {self.activity_log()[-1500:]}")

    def activity_log(self) -> str:
        p = self.home / ".config" / "open-ephys" / "configs-api10" / "activity.log"
        return p.read_text(errors="replace") if p.is_file() else self.log_path.read_text()

    def api(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(OE_API + path, method=method, data=data)
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()
        out = json.loads(raw) if raw else {}
        return out if isinstance(out, dict) else {"value": out}

    def processor_id(self, name: str) -> int:
        ids = [
            int(p["id"]) for p in self.api("GET", "/processors")["processors"] if p["name"] == name
        ]
        if not ids:
            raise RuntimeError(f"no processor {name!r}")
        return max(ids)

    def build_chain(
        self, zmq_port: int, record_dir: Path, between: list[str] | None = None
    ) -> dict[str, int]:
        """File Reader -> ZMQ Interface -> [between...] -> Record Node (Binary)."""
        record_dir.mkdir(parents=True, exist_ok=True)
        rec = self.api("PUT", "/recording", {"parent_directory": str(record_dir)})
        if rec.get("parent_directory") != str(record_dir):
            raise RuntimeError(f"recording directory not set: {rec}")
        self.api("PUT", "/processors/add", {"name": "File Reader"})
        ids = {"File Reader": self.processor_id("File Reader")}
        self.api(
            "PUT", "/processors/add", {"name": "ZMQ Interface", "source_id": ids["File Reader"]}
        )
        ids["ZMQ Interface"] = self.processor_id("ZMQ Interface")
        self.api(
            "PUT", f"/processors/{ids['ZMQ Interface']}/parameters/data_port", {"value": zmq_port}
        )
        last = ids["ZMQ Interface"]
        for name in between or []:
            self.api("PUT", "/processors/add", {"name": name, "source_id": last})
            last = ids[name] = self.processor_id(name)
        self.api("PUT", "/processors/add", {"name": "Record Node", "source_id": last})
        ids["Record Node"] = self.processor_id("Record Node")
        port = [
            p
            for p in self.api("GET", f"/processors/{ids['ZMQ Interface']}")["parameters"]
            if p["name"] == "data_port"
        ]
        if not port or int(port[0]["value"]) != zmq_port:
            raise RuntimeError(f"ZMQ Interface data_port not set: {port}")
        return ids

    def bundled_sample(self) -> Path:
        """The sample recording shipped with the GUI (Binary format, GUI 0.4.5 layout)."""
        return self.gui_dir / "open-ephys" / "resources"

    def set_status(self, mode: str) -> None:
        got = self.api("PUT", "/status", {"mode": mode}).get("mode")
        if got != mode:
            raise RuntimeError(f"GUI status {got!r}, expected {mode!r}")

    def stop(self) -> None:
        for p in reversed(self.procs):
            if p.poll() is None:
                p.send_signal(signal.SIGTERM)
                try:
                    p.wait(10)
                except subprocess.TimeoutExpired:
                    p.kill()
                    p.wait(5)
        self.procs.clear()


@contextlib.contextmanager
def open_ephys_gui(home: Path) -> Iterator[OpenEphysGUI]:
    gui = OpenEphysGUI(home)
    gui.start()
    try:
        yield gui
    finally:
        gui.stop()
