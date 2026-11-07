"""Milestone 5 (D): config file, bind policy, private permissions, redaction, logging."""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path

import pytest

from brainos.config import ConfigError, load_config, parse_config, template, write_template
from brainos.security import (
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
from brainos.server.serve import AlreadyRunning, acquire_instance, read_instance, run
from brainos.server.settings import Settings

posix = pytest.mark.skipif(os.name != "posix", reason="POSIX permissions")


def mode(p: Path) -> int:
    return stat.S_IMODE(p.stat().st_mode)


# --------------------------------------------------------------------------- config


def test_default_bind_is_loopback_and_settings_defaults_are_safe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BRAINOS_CONFIG", str(tmp_path / "absent.toml"))
    for var in ("BRAINOS_HOST", "BRAINOS_ALLOW_REMOTE", "BRAINOS_PORT"):
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
        f'[storage]\ndata_dir = "{tmp_path / "d"}"\n[retention]\nrecordings_days = 30\nmodels_days = 0\n'
    )
    cfg.chmod(0o600)
    monkeypatch.setenv("BRAINOS_CONFIG", str(cfg))
    monkeypatch.delenv("BRAINOS_PORT", raising=False)
    monkeypatch.delenv("BRAINOS_DATA_DIR", raising=False)
    s = Settings.from_env()
    assert s.port == 8123 and not s.open_browser and s.log_level == "WARNING"
    assert s.data_dir == tmp_path / "d" and s.config_path == cfg
    assert s.retention.recordings_days == 30 and s.retention.models_days is None
    monkeypatch.setenv("BRAINOS_PORT", "8200")
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
    cfg.write_text("[server]\nport = 8001\n")
    cfg.chmod(0o666)
    with pytest.raises(ConfigError, match="other users"):
        load_config(cfg)
    cfg.chmod(0o644)  # readable by others is allowed (it holds no secrets)
    assert load_config(cfg).get("server", "port") == 8001


@posix
def test_config_template_round_trips_and_is_private(tmp_path: Path) -> None:
    path = write_template(tmp_path / "sub" / "config.toml")
    assert mode(path) == 0o600
    cfg = load_config(path)
    assert cfg.get("server", "host") == "127.0.0.1" and cfg.get("server", "allow_remote") is False
    assert not cfg.retention().active  # 0 = keep forever
    with pytest.raises(FileExistsError):
        write_template(path)
    assert "allow_remote" in template()


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
    assert not (tmp_path / "data" / "brainos.pid").exists()  # refused before anything else


@posix
def test_single_instance_lock(tmp_path: Path) -> None:
    s = Settings(data_dir=tmp_path / "data", port=8999)
    lock = acquire_instance(s)
    try:
        info = read_instance(s.pid_file)
        assert info is not None and info["pid"] == os.getpid() and info["port"] == 8999
        assert mode(s.pid_file) == 0o600
        with pytest.raises(AlreadyRunning):
            acquire_instance(s)
    finally:
        lock.release()
    assert read_instance(s.pid_file) is None
    s.pid_file.write_text('{"pid": 999999}')  # stale file from a crash: nobody holds the lock
    assert read_instance(s.pid_file) is None
    acquire_instance(s).release()


# --------------------------------------------------------------------------- permissions


@posix
def test_private_dirs_and_hardening(tmp_path: Path) -> None:
    root = tmp_path / "data"
    (root / "recordings").mkdir(parents=True)
    (root / "recordings" / "a.brainos.jsonl").write_text("x")
    (root / "datasets").mkdir()
    (root / "datasets" / "public.nwb").write_text("x")
    shared = tmp_path / "shared-models"
    shared.mkdir()
    (shared / "m.json").write_text("{}")
    (root / "models").symlink_to(shared)
    os.chmod(root / "recordings" / "a.brainos.jsonl", 0o644)
    os.chmod(root / "datasets" / "public.nwb", 0o644)
    os.chmod(shared / "m.json", 0o644)
    assert open_permissions(root, skip=("datasets",)) == (1, 1)  # recordings dir + file
    rep = harden_tree(root, skip=("datasets",))
    assert rep.files_fixed == 1 and str(root / "models") in rep.symlinks_skipped
    assert mode(root) == 0o700 and mode(root / "recordings") == 0o700
    assert mode(root / "recordings" / "a.brainos.jsonl") == 0o600
    assert mode(root / "datasets" / "public.nwb") == 0o644  # public datasets left alone
    assert mode(shared / "m.json") == 0o644  # never through a symlink
    assert open_permissions(root, skip=("datasets",)) == (0, 0)
    ensure_private_dir(tmp_path / "new" / "deep")
    assert mode(tmp_path / "new" / "deep") == 0o700


@posix
def test_app_startup_secures_the_data_directory(tmp_path: Path) -> None:
    from fastapi.testclient import TestClient

    from brainos.server import create_app

    from .conftest import make_settings

    data = tmp_path / "data"
    (data / "recordings").mkdir(parents=True)
    leaked = data / "recordings" / "old.recovery.json"
    leaked.write_text("{}")
    os.chmod(data, 0o755)
    os.chmod(leaked, 0o644)
    with TestClient(create_app(make_settings(tmp_path))) as c:
        assert c.get("/api/v1/health").json()["pid"] == os.getpid()
    assert mode(data) == 0o700 and mode(leaked) == 0o600
    for sub in ("recordings", "sessions", "logs", "models"):
        assert mode(data / sub) == 0o700, sub


# --------------------------------------------------------------------------- redaction / logging


def test_redaction() -> None:
    home = Path.home()
    line = (
        f"ERROR open {home}/brainos/data/recordings/p07.brainos.jsonl failed; token=abc123SECRET "
        'password: hunter2 {"api_key": "k-123"} Authorization: Bearer abcdefghijklmnop '
        "samples [1.5, 2.25, -3.0, 4e-3, 5, 6, 7, 8, 9] small [1, 2] "
        "from 192.168.1.20 and 127.0.0.1 mail alice@example.org /home/bob/x /Users/carol/y"
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
        str(home) + "/",
    ):
        assert secret not in out, secret
    assert "~/brainos/data" in out and "[9 values redacted]" in out and "[1, 2]" in out
    assert "127.0.0.1" in out
    # the log-file redaction keeps paths and addresses (local) but never secrets or arrays
    local = redact_secrets(line)
    assert (
        "abc123SECRET" not in local and "192.168.1.20" in local and "[9 values redacted]" in local
    )


@posix
def test_logging_is_redacted_and_private(tmp_path: Path) -> None:
    log_file = tmp_path / "logs" / "brainos.log"
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    try:
        configure_logging("INFO", log_file)
        logging.getLogger("brainos.test").warning(
            "frame %s token=%s", [0.1 * i for i in range(64)], "s3cr3t"
        )
        for h in root.handlers:
            h.flush()
        text = log_file.read_text()
        assert "s3cr3t" not in text and "64 values redacted" in text
        assert mode(log_file) == 0o600 and mode(log_file.parent) == 0o700
        rec = logging.LogRecord("x", logging.INFO, "", 0, "y" * 10_000, None, None)
        assert len(RedactingFormatter("%(message)s").format(rec)) < 4100
    finally:
        for h in root.handlers[:]:
            root.removeHandler(h)
            h.close()
        for h in saved[0]:
            root.addHandler(h)
        root.setLevel(saved[1])
