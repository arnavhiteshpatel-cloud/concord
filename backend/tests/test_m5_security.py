"""Milestone 5 (D): config file, bind policy, private permissions, redaction, logging."""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

import pytest

from concord.config import (
    ConfigError,
    load_config,
    parse_config,
    template,
    toml_string,
    write_template,
)
from concord.security import (
    BindRefused,
    RedactingFormatter,
    check_bind,
    configure_logging,
    ensure_private_dir,
    harden_tree,
    is_loopback,
    open_permissions,
    redact,
    redact_secrets,
)
from concord.server.serve import AlreadyRunning, acquire_instance, read_instance, run
from concord.server.settings import Settings

from .helpers import assert_mode

posix = pytest.mark.skipif(os.name != "posix", reason="POSIX permissions and symlinks")


def mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


# --------------------------------------------------------------------------- config


def test_default_bind_is_loopback_and_settings_defaults_are_safe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("CONCORD_CONFIG", str(tmp_path / "absent.toml"))
    for var in ("CONCORD_HOST", "CONCORD_ALLOW_REMOTE", "CONCORD_PORT"):
        monkeypatch.delenv(var, raising=False)
    s = Settings.from_env()
    assert s.host == "127.0.0.1" and s.port == 8000 and s.allow_remote is False
    assert Settings().host == "127.0.0.1"
    assert s.config_path is None and not s.retention.active


def test_config_file_is_read_validated_and_overridden_by_env(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text(
        '[server]\nport = 8123\nopen_browser = false\nlog_level = "warning"\n'
        f"[storage]\ndata_dir = {toml_string(str(tmp_path / 'd'))}\n"
        "[retention]\nrecordings_days = 30\nmodels_days = 0\n",
        encoding="utf-8",
    )
    cfg.chmod(0o600)
    monkeypatch.setenv("CONCORD_CONFIG", str(cfg))
    monkeypatch.delenv("CONCORD_PORT", raising=False)
    monkeypatch.delenv("CONCORD_DATA_DIR", raising=False)
    s = Settings.from_env()
    assert s.port == 8123 and not s.open_browser and s.log_level == "WARNING"
    assert s.data_dir == tmp_path / "d" and s.config_path == cfg
    assert s.retention.recordings_days == 30 and s.retention.models_days is None
    monkeypatch.setenv("CONCORD_PORT", "8200")
    assert Settings.from_env().port == 8200  # environment beats the file


@pytest.mark.parametrize(
    ("text", "match"),
    [
        ("[server]\nprot = 1\n", "unknown key"),
        ("[srv]\n", "unknown section"),
        ('[server]\nport = "80"\n', "integer"),
        ("[server]\nport = 70000\n", "1-65535"),
        ('[server]\nallow_remote = "yes"\n', "true or false"),
        ("[retention]\nrecordings_days = -1\n", "days"),
        ('[server]\nlog_level = "LOUD"\n', "one of"),
        ("[server\n", "invalid TOML"),
    ],
)
def test_malformed_config_is_refused(text: str, match: str) -> None:
    with pytest.raises(ConfigError, match=match):
        parse_config(text, Path("c.toml"))


@posix
def test_config_writable_by_others_is_refused(tmp_path: Path) -> None:
    cfg = tmp_path / "config.toml"
    cfg.write_text("[server]\nport = 8001\n", encoding="utf-8")
    cfg.chmod(0o666)
    with pytest.raises(ConfigError, match="other users"):
        load_config(cfg)
    cfg.chmod(0o644)  # readable by others is allowed (it holds no secrets)
    assert load_config(cfg).get("server", "port") == 8001


def test_config_template_round_trips_and_is_private(tmp_path: Path) -> None:
    path = write_template(tmp_path / "sub" / "config.toml")
    assert_mode(path, 0o600)
    cfg = load_config(path)
    assert cfg.get("server", "host") == "127.0.0.1" and cfg.get("server", "allow_remote") is False
    assert not cfg.retention().active  # 0 = keep forever
    with pytest.raises(FileExistsError):
        write_template(path)
    assert "allow_remote" in template()


@pytest.mark.parametrize(
    "folder",
    [r"C:\Users\Ana Lopez\AppData\Local\Concord\data", "/home/ana/.local/share/concord/data"],
)
def test_template_paths_are_valid_toml_when_uncommented(
    monkeypatch: pytest.MonkeyPatch, folder: str
) -> None:
    """Regression (Windows): the template wrote data_dir = "C:\\Users\\...", where TOML reads
    "\\U" as an escape; uncommenting the line made the config file invalid."""
    from concord import config

    monkeypatch.setattr(config, "default_data_dir", lambda: Path(folder))
    text = "\n".join(
        line[2:] if line.startswith("# data_dir") else line for line in template().splitlines()
    )
    assert parse_config(text, Path("c.toml"))["storage"]["data_dir"] == str(Path(folder))


# --------------------------------------------------------------------------- bind policy


def test_bind_policy() -> None:
    for host in ("127.0.0.1", "localhost", "::1", "127.0.0.2"):
        assert is_loopback(host) and check_bind(host, False) is None
    for host in ("0.0.0.0", "192.168.1.20", "::", "example.org"):
        assert not is_loopback(host)
        with pytest.raises(BindRefused, match="no authentication"):
            check_bind(host, False)
        warning = check_bind(host, True)
        assert warning and "NO authentication" in warning


def test_server_refuses_non_local_bind_without_the_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    s = Settings(host="0.0.0.0", port=1, data_dir=tmp_path / "data", static_dir=None)
    assert run(s) == 2
    assert "refusing to listen on '0.0.0.0'" in capsys.readouterr().err
    assert not (tmp_path / "data" / "concord.pid").exists()  # refused before anything else


def test_single_instance_lock(tmp_path: Path) -> None:
    """Also on Windows, where the lock is a byte-range lock beyond the end of the pid file (so
    its content stays readable) and the file is deleted after it is closed."""
    s = Settings(data_dir=tmp_path / "data", port=8999)
    lock = acquire_instance(s)
    try:
        info = read_instance(s.pid_file)
        assert info is not None and info["pid"] == os.getpid() and info["port"] == 8999
        assert_mode(s.pid_file, 0o600)
        with pytest.raises(AlreadyRunning):
            acquire_instance(s)
    finally:
        lock.release()
    assert read_instance(s.pid_file) is None
    assert not s.pid_file.exists()  # removed on release (Windows: after closing it)
    s.pid_file.write_text(
        '{"pid": 999999}', encoding="utf-8"
    )  # stale file from a crash: nobody holds the lock
    assert read_instance(s.pid_file) is None
    acquire_instance(s).release()


# --------------------------------------------------------------------------- permissions


@posix
def test_private_dirs_and_hardening(tmp_path: Path) -> None:
    root = tmp_path / "data"
    (root / "recordings").mkdir(parents=True)
    (root / "recordings" / "a.concord.jsonl").write_text("x", encoding="utf-8")
    (root / "datasets").mkdir()
    (root / "datasets" / "public.nwb").write_text("x", encoding="utf-8")
    shared = tmp_path / "shared-models"
    shared.mkdir()
    (shared / "m.json").write_text("{}", encoding="utf-8")
    (root / "models").symlink_to(shared)
    os.chmod(root / "recordings" / "a.concord.jsonl", 0o644)
    os.chmod(root / "datasets" / "public.nwb", 0o644)
    os.chmod(shared / "m.json", 0o644)
    assert open_permissions(root, skip=("datasets",)) == (1, 1)  # recordings dir + file
    rep = harden_tree(root, skip=("datasets",))
    assert rep.files_fixed == 1 and str(root / "models") in rep.symlinks_skipped
    assert mode(root) == 0o700 and mode(root / "recordings") == 0o700
    assert mode(root / "recordings" / "a.concord.jsonl") == 0o600
    assert mode(root / "datasets" / "public.nwb") == 0o644  # public datasets left alone
    assert mode(shared / "m.json") == 0o644  # never through a symlink
    assert open_permissions(root, skip=("datasets",)) == (0, 0)
    ensure_private_dir(tmp_path / "new" / "deep")
    assert mode(tmp_path / "new" / "deep") == 0o700


@posix
def test_app_startup_secures_the_data_directory(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from concord.server import create_app

    from .conftest import make_settings

    data = tmp_path / "data"
    (data / "recordings").mkdir(parents=True)
    leaked = data / "recordings" / "old.recovery.json"
    leaked.write_text("{}", encoding="utf-8")
    os.chmod(data, 0o755)
    os.chmod(data / "recordings", 0o755)
    os.chmod(leaked, 0o644)
    with TestClient(create_app(make_settings(tmp_path))) as c:
        assert c.get("/api/v1/health").json()["pid"] == os.getpid()
        assert mode(data) == 0o700 and mode(leaked) == 0o600
        assert mode(data / "recordings") == 0o700
        # directories created later by their owners are private from the start
        c.post("/api/v1/sessions", json={"name": "perm"}).raise_for_status()
        c.post("/api/v1/runtime/connect", json={"device_id": "sim-a"}).raise_for_status()
        c.post("/api/v1/recordings/start", json={"name": "perm"}).raise_for_status()
        c.post("/api/v1/safe-stop").raise_for_status()
    assert mode(data / "sessions") == 0o700
    for f in [*(data / "recordings").iterdir(), *(data / "sessions").rglob("*")]:
        assert mode(f) == (0o700 if f.is_dir() else 0o600), f


# --------------------------------------------------------------------------- redaction / logging


def test_redaction() -> None:
    home = Path.home()
    line = (
        f"ERROR open {home}/concord/data/recordings/p07.concord.jsonl failed; token=abc123SECRET "
        'password: hunter2 {"api_key": "k-123"} Authorization: Bearer abcdefghijklmnop '
        "samples [1.5, 2.25, -3.0, 4e-3, 5, 6, 7, 8, 9] small [1, 2] "
        "from 192.168.1.20 and 127.0.0.1 mail alice@example.org /home/bob/x /Users/carol/y "
        r'C:\Users\erin\data {"p": "D:\\Users\\frank\\x"}'
    )
    out = redact(line)
    for secret in (
        "abc123SECRET",
        "hunter2",
        "k-123",
        "abcdefghijklmnop",
        "192.168.1.20",
        "alice@example.org",
        "bob",
        "carol",
        "erin",  # Windows profiles, as text and as JSON writes them
        "frank",
        str(home) + "/",
    ):
        assert secret not in out, secret
    assert "~/concord/data" in out and "[9 values redacted]" in out and "[1, 2]" in out
    assert "127.0.0.1" in out
    # the log-file redaction keeps paths and addresses (local) but never secrets or arrays
    local = redact_secrets(line)
    assert (
        "abc123SECRET" not in local and "192.168.1.20" in local and "[9 values redacted]" in local
    )


def test_logging_is_redacted_and_private(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "concord.log"
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    try:
        configure_logging("INFO", log_file)
        logging.getLogger("concord.test").warning(
            "frame %s token=%s", [0.1 * i for i in range(64)], "s3cr3t"
        )
        for h in root.handlers:
            h.flush()
        text = log_file.read_text(encoding="utf-8")
        assert "s3cr3t" not in text and "64 values redacted" in text
        assert_mode(log_file, 0o600)
        assert_mode(log_file.parent, 0o700)
        rec = logging.LogRecord("x", logging.INFO, "", 0, "y" * 10_000, None, None)
        assert len(RedactingFormatter("%(message)s").format(rec)) < 4100
    finally:
        for h in root.handlers[:]:
            root.removeHandler(h)
            h.close()
        for h in saved[0]:
            root.addHandler(h)
        root.setLevel(saved[1])


# --------------------------------------------------------------------------- browser origins


def test_web_pages_on_other_sites_cannot_use_the_local_api(tmp_path: Path) -> None:
    """Cross-site requests and DNS rebinding through the operator's browser are refused;
    the console (same origin), the Vite dev server (loopback) and non-browser clients work."""
    from fastapi.testclient import TestClient
    from starlette.websockets import WebSocketDisconnect

    from concord.server import create_app

    from .conftest import make_settings

    with TestClient(create_app(make_settings(tmp_path))) as c:
        connect = {"device_id": "sim-a"}
        evil = {"origin": "http://evil.example"}
        r = c.post("/api/v1/runtime/connect", json=connect, headers=evil)
        assert r.status_code == 403 and r.json()["error"]["code"] == "forbidden_origin"
        assert c.get("/api/v1/runtime").json()["state"] == "idle"  # nothing happened
        assert c.post("/api/v1/safe-stop", headers={"origin": "null"}).status_code == 403
        cross = {"sec-fetch-site": "cross-site", "user-agent": "Mozilla/5.0"}
        assert c.get("/api/v1/recordings", headers=cross).status_code == 403
        # DNS rebinding: a site name that resolves to 127.0.0.1 is "same origin" for the page
        rebound = {"host": "evil.example:8000", "sec-fetch-site": "same-origin"}
        assert c.get("/api/v1/recordings", headers=rebound).status_code == 403
        moz = {"host": "evil.example:8000", "user-agent": "Mozilla/5.0 (Macintosh)"}
        assert c.get("/api/v1/sessions", headers=moz).status_code == 403
        with (
            pytest.raises(WebSocketDisconnect) as refused,
            c.websocket_connect("/api/v1/stream", headers=evil) as ws,
        ):
            ws.receive_json()
        assert refused.value.code == 1008
        # allowed: the console itself, the Vite dev server, SDKs/scripts without browser headers
        console = {
            "origin": "http://127.0.0.1:8000",
            "host": "127.0.0.1:8000",
            "sec-fetch-site": "same-origin",
            "user-agent": "Mozilla/5.0",
        }
        assert c.get("/api/v1/health", headers=console).status_code == 200
        dev = {"origin": "http://localhost:5173", "host": "localhost:5173"}
        assert c.post("/api/v1/runtime/connect", json=connect, headers=dev).status_code == 200
        assert c.post("/api/v1/runtime/disconnect").status_code == 200

    with TestClient(create_app(make_settings(tmp_path, allow_remote=True))) as c:
        lan = {
            "origin": "http://192.168.1.5:8000",
            "host": "192.168.1.5:8000",
            "user-agent": "Mozilla/5.0",
        }
        assert c.get("/api/v1/health", headers=lan).status_code == 200
        foreign = {**lan, "origin": "http://evil.example"}
        assert c.get("/api/v1/health", headers=foreign).status_code == 403
