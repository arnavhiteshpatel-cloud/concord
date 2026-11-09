"""The desktop app when another copy of Concord answers on its address.

Regression: an older build (from before the rename) was still running, so a newly installed
Concord.app found it at http://127.0.0.1:8000, opened its console and exited without a word.
The console showed the other copy's name, version and data, and the app's own data folder was
never created. The app now compares what answers with this build and says what is going on.
The single-instance behaviour for this data directory's own server is unchanged.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from concord import __version__, desktop, launcher, oscompat
from concord.contracts.events import SCHEMA_VERSION
from concord.contracts.protocol import STREAM_PROTOCOL
from concord.server.routes import Health

from .conftest import free_port
from .helpers import assert_mode, fake_health_server

OTHER_PID = 4242
# A build from before the rename: the same version number, another stream protocol name and
# another data directory. Only the protocol and the missing instance lock tell it apart.
# a build from before the rename reported the same version number as this one
PRE_RENAME = {"version": __version__, "stream_protocol": "previous-name.stream/1"}


def concord_health(**overrides: Any) -> dict[str, Any]:
    """What a Concord server's ``/api/v1/health`` answers (server/routes.py), as another copy."""
    h: dict[str, Any] = {
        "status": "ok",
        "version": __version__,
        "schema_version": SCHEMA_VERSION,
        "stream_protocol": STREAM_PROTOCOL,
        "simulation_enabled": True,
        "read_only": True,
        "pid": OTHER_PID,
    }
    h.update(overrides)
    return h


def test_the_fake_health_answer_matches_the_real_one() -> None:
    assert set(concord_health()) == set(Health.model_fields)
    Health.model_validate(concord_health())


@contextmanager
def held_pid_file(pid_file: Path, url: str) -> Iterator[None]:
    """This data directory's instance lock, held as a running Concord server holds it."""
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(pid_file, os.O_RDWR | os.O_CREAT | oscompat.O_BINARY, 0o600)
    try:
        assert oscompat.try_lock(fd), "the pid file is already locked"
        os.write(fd, json.dumps({"pid": OTHER_PID, "url": url, "version": __version__}).encode())
        yield
    finally:
        os.close(fd)


def instance(from_pid_file: bool, **health: Any) -> launcher.Instance:
    return launcher.Instance(
        pid=OTHER_PID,
        url="http://127.0.0.1:8000",
        health=concord_health(**health),
        from_pid_file=from_pid_file,
    )


# --------------------------------------------------------------------------- launcher


@pytest.mark.parametrize(
    ("inst", "expected"),
    [
        (instance(True), []),  # this data directory's own server: single instance
        (instance(False), ["data_dir"]),  # same build, another data directory
        (instance(False, **PRE_RENAME), ["data_dir", "stream_protocol"]),  # the reported case
        (instance(True, version="0.2.0"), ["version"]),  # older build, same data directory
        (instance(True, stream_protocol="concord.stream/2"), ["stream_protocol"]),
        (
            launcher.Instance(
                pid=None, url="http://127.0.0.1:8000", health={"status": "ok"}, from_pid_file=False
            ),
            ["data_dir", "version", "stream_protocol"],
        ),
    ],
)
def test_differences_names_what_is_not_this_builds_server(
    inst: launcher.Instance, expected: list[str]
) -> None:
    diffs = launcher.differences(inst, version=__version__, stream_protocol=STREAM_PROTOCOL)
    assert diffs == expected


def test_find_reports_a_server_on_the_url_as_not_this_data_directorys(tmp_path: Path) -> None:
    port = free_port()
    url = f"http://127.0.0.1:{port}"
    with fake_health_server(port, concord_health(**PRE_RENAME)):
        found = launcher.find(url, tmp_path / "data" / "concord.pid")
        assert found is not None and found.health is not None
        assert not found.from_pid_file and found.pid == OTHER_PID
        assert found.health["stream_protocol"] == PRE_RENAME["stream_protocol"]
        with held_pid_file(tmp_path / "data" / "concord.pid", url):
            mine = launcher.find(url, tmp_path / "data" / "concord.pid")
        assert mine is not None and mine.from_pid_file and mine.health is not None


# --------------------------------------------------------------------------- desktop app


@pytest.fixture
def app(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    """The desktop app's environment (a fresh data directory on a free port), the browser
    and window replaced by recorders; the process-wide logging and umask that ``main()`` sets
    are restored afterwards."""
    port = free_port()
    for env, value in {
        "CONCORD_CONFIG": str(tmp_path / "absent.toml"),
        "CONCORD_DATA_DIR": str(tmp_path / "data"),
        "CONCORD_PORT": str(port),
        "CONCORD_HOST": "127.0.0.1",
        "CONCORD_LOG_LEVEL": "INFO",
        "CONCORD_OPEN_BROWSER": "1",  # restored by monkeypatch even after --no-browser sets it
    }.items():
        monkeypatch.setenv(env, value)
    opened: list[str] = []
    monkeypatch.setattr(launcher, "open_browser", lambda url: opened.append(url) or True)
    monkeypatch.setattr(desktop, "has_window_toolkit", lambda: False)
    root = logging.getLogger()
    saved = (root.handlers[:], root.level)
    umask = os.umask(0o022)
    os.umask(umask)
    try:
        yield {
            "port": port,
            "url": f"http://127.0.0.1:{port}",
            "data": tmp_path / "data",
            "opened": opened,
        }
    finally:
        os.umask(umask)
        for h in root.handlers[:]:
            root.removeHandler(h)
            h.close()
        for h in saved[0]:
            root.addHandler(h)
        root.setLevel(saved[1])


def _log(data: Path) -> str:
    for h in logging.getLogger().handlers:
        h.flush()
    return (data / "logs" / "concord.log").read_text()


def test_an_older_copy_on_the_address_is_explained_not_silently_opened(
    app: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """The reported case, headless: stderr and the log say what runs, and the app exits."""
    with fake_health_server(app["port"], concord_health(**PRE_RENAME)) as requests:
        code = desktop.main(["--headless"])
    out, err = capsys.readouterr()
    assert code == desktop.OTHER_COPY_EXIT == 3
    assert "already running" not in out
    assert "Another copy of Concord is running" in err
    assert f"Concord version {__version__}, process ID {OTHER_PID}" in err and app["url"] in err
    assert f"does not use this app's data folder ({app['data']})" in err
    assert f"uses stream protocol previous-name.stream/1 (this app: {STREAM_PROTOCOL})" in err
    assert "is version" not in err  # the version is the same; it is not listed as a difference
    assert "Quit the other copy" in err and "open Concord again" in err
    # no window could be shown: that copy's console still opens, as before
    assert app["opened"] == [app["url"]]
    # the other copy was only asked for its health: nothing was stopped or changed there
    assert requests and set(requests) == {"GET /api/v1/health"}
    # this app did not start: no instance lock; the explanation is in its own log (private)
    assert not (app["data"] / "concord.pid").exists()
    text = _log(app["data"])
    assert f"another copy of Concord answers at {app['url']}" in text
    assert f"pid {OTHER_PID}" in text and "differs: data_dir, stream_protocol" in text
    assert_mode(app["data"], 0o700)  # POSIX permission bits; Windows has none
    assert_mode(app["data"] / "logs" / "concord.log", 0o600)


def test_the_same_build_with_another_data_directory_is_explained(
    app: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """Same version and protocol, but not this data directory's server (e.g. `make run`)."""
    with fake_health_server(app["port"], concord_health()):
        code = desktop.main(["--headless", "--no-browser"])
    err = capsys.readouterr().err
    assert code == desktop.OTHER_COPY_EXIT
    assert "Another copy of Concord is running" in err and "does not use this app's data" in err
    assert "is version" not in err and "stream protocol" not in err
    assert app["opened"] == []  # --no-browser


def test_an_older_server_of_this_data_directory_is_explained(
    app: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """Found through this data directory's pid file, but a different version."""
    with (
        fake_health_server(app["port"], concord_health(version="0.2.0")),
        held_pid_file(app["data"] / "concord.pid", app["url"]),
    ):
        code = desktop.main(["--headless"])
    err = capsys.readouterr().err
    assert code == desktop.OTHER_COPY_EXIT
    assert f"is version 0.2.0 (this app: {__version__})" in err
    assert "data folder" not in err  # it is this data directory's server


def test_this_data_directorys_server_keeps_single_instance(
    app: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    """Same version, found through the pid file: a second launch just opens its console."""
    with (
        fake_health_server(app["port"], concord_health()),
        held_pid_file(app["data"] / "concord.pid", app["url"]),
    ):
        code = desktop.main(["--headless"])
    out, err = capsys.readouterr()
    assert code == 0
    assert f"Concord is already running at {app['url']}" in out
    assert "Another copy" not in err
    assert app["opened"] == [app["url"]]
    assert not (app["data"] / "logs").exists()  # nothing written, as before


def test_the_window_shows_the_explanation_and_offers_the_console(
    app: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """With a window, the message is shown there first; the console opens only on request."""
    shown: list[str] = []

    def window(message: str, open_console: Any, stop_event: Any, on_ready: Any = None) -> None:
        shown.append(message)
        assert app["opened"] == []  # not opened behind the explanation
        open_console()  # the user clicks "Open its console"

    monkeypatch.setattr(desktop, "has_window_toolkit", lambda: True)
    monkeypatch.setattr(desktop, "show_other_copy", window)
    with fake_health_server(app["port"], concord_health(**PRE_RENAME)):
        code = desktop.main([])
    assert code == desktop.OTHER_COPY_EXIT
    assert len(shown) == 1 and f"process ID {OTHER_PID}" in shown[0]
    assert "previous-name.stream/1" in shown[0] and "open Concord again" in shown[0]
    assert app["opened"] == [app["url"]]
    assert "Another copy of Concord is running" in capsys.readouterr().err


def test_without_a_window_the_message_goes_to_stderr_and_the_log(
    app: dict[str, Any], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def no_window(*_: Any, **__: Any) -> None:
        raise desktop.WindowUnavailable("no display")

    monkeypatch.setattr(desktop, "has_window_toolkit", lambda: True)
    monkeypatch.setattr(desktop, "show_other_copy", no_window)
    with fake_health_server(app["port"], concord_health(**PRE_RENAME)):
        code = desktop.main([])
    assert code == desktop.OTHER_COPY_EXIT
    assert "Another copy of Concord is running" in capsys.readouterr().err
    text = _log(app["data"])
    assert "another copy of Concord answers at" in text and "no window could be created" in text
    assert app["opened"] == [app["url"]]
