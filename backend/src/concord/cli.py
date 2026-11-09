"""The ``concord`` command.

    concord start [--port N] [--no-browser]   start the server in the background, open console
    concord stop                              safe stop, then end the server
    concord status [--json]                   is it running, where, what is it doing
    concord doctor [--json F] [--markdown F]  diagnostics + support report (no neural/personal data)
    concord version [--json]
    concord config path|show|init             the config file (safe defaults; docs/SECURITY.md)
    concord dataset [--all-calib]             download + verify the public demo recordings
    concord reproduce BUNDLE.zip              verify a session export and re-run its evaluation
    concord serve                             run the server in the foreground (Ctrl-C stops)

Settings come from the config file and CONCORD_* environment variables; the flags here
override both for one run. Ordinary use needs no flags.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from concord import __version__
from concord.config import (
    CONFIG_ENV,
    ConfigError,
    default_config_path,
    load_config,
    template,
    write_template,
)

SERVER_HINT = 'The Concord server is not installed. Install it: pip install "concordos[server]"'


def _server_available() -> bool:
    import importlib.util

    return all(importlib.util.find_spec(m) is not None for m in ("fastapi", "uvicorn"))


def _apply_overrides(args: argparse.Namespace) -> None:
    """CLI flags become environment variables: the child server process reads the same."""
    if getattr(args, "config", None):
        os.environ[CONFIG_ENV] = str(Path(args.config).expanduser())
    for flag, env in (
        ("port", "CONCORD_PORT"),
        ("host", "CONCORD_HOST"),
        ("data_dir", "CONCORD_DATA_DIR"),
        ("log_level", "CONCORD_LOG_LEVEL"),
    ):
        value = getattr(args, flag, None)
        if value is not None:
            os.environ[env] = str(value)
    if getattr(args, "allow_remote", False):
        os.environ["CONCORD_ALLOW_REMOTE"] = "1"
    if getattr(args, "no_browser", False):
        os.environ["CONCORD_OPEN_BROWSER"] = "0"


def _settings(args: argparse.Namespace) -> Any:
    from concord.server.settings import Settings

    _apply_overrides(args)
    try:
        return Settings.from_env()
    except ConfigError as exc:
        print(f"concord: {exc}", file=sys.stderr)
        raise SystemExit(2) from None


def _print_json(obj: Any) -> None:
    print(json.dumps(obj, indent=1, default=str))


# --------------------------------------------------------------------------- commands


def cmd_version(args: argparse.Namespace) -> int:
    from concord.environment import packages, platform_info

    info: dict[str, Any] = {"concord": __version__, "platform": platform_info()}
    if args.json:
        info["packages"] = [p for p in packages() if p["installed"]]
        _print_json(info)
    else:
        p = info["platform"]
        print(f"Concord {__version__} · Python {p['python']} · {p['system']} {p['machine']}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    if not _server_available():
        print(SERVER_HINT, file=sys.stderr)
        return 1
    from concord.server.serve import run

    return run(_settings(args))


def cmd_start(args: argparse.Namespace) -> int:
    if not _server_available():
        print(SERVER_HINT, file=sys.stderr)
        return 1
    from concord import launcher
    from concord.security import BindRefused, check_bind

    s = _settings(args)
    try:
        warning = check_bind(s.host, s.allow_remote)
    except BindRefused as exc:
        print(f"concord: {exc}", file=sys.stderr)
        return 2
    if args.foreground:
        from concord.server.serve import run

        return run(s)
    try:
        inst = launcher.start(
            url=s.url,
            host=s.host,
            port=s.port,
            data_dir=s.data_dir,
            pid_file=s.pid_file,
            env=dict(os.environ),
            timeout_s=args.timeout,
        )
    except launcher.LaunchError as exc:
        print(f"concord: {exc}", file=sys.stderr)
        return 1
    if warning:
        print(f"WARNING: {warning}", file=sys.stderr)
    print(f"Concord {inst.health.get('version') if inst.health else ''} is running: {inst.url}")
    print(f"  data: {s.data_dir}")
    print("  stop it with: concord stop")
    if s.open_browser:
        launcher.open_browser(inst.url)
    return 0


def cmd_stop(args: argparse.Namespace) -> int:
    from concord import launcher

    s = _settings(args)
    inst = launcher.find(s.url, s.pid_file)
    if inst is None:
        print("Concord is not running.")
        return 0
    try:
        result = launcher.stop(inst, timeout_s=args.timeout, pid_file=s.pid_file)
    except launcher.LaunchError as exc:
        print(f"concord: {exc}", file=sys.stderr)
        return 1
    st = result.get("safe_stop")
    if isinstance(st, dict):
        done = [x["detail"] for x in st.get("steps", []) if x.get("done")]
        print("Safe stop: " + ("; ".join(done) if done else "nothing was running"))
    if result["forced"]:
        print(
            "The server did not exit in time and was killed; an active recording will be "
            "recovered and marked incomplete at the next start.",
            file=sys.stderr,
        )
        return 1
    print(f"Concord stopped (pid {result['pid']}).")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    from concord import launcher

    s = _settings(args)
    inst = launcher.find(s.url, s.pid_file)
    status: dict[str, Any] = {
        "running": inst is not None and inst.health is not None,
        "url": inst.url if inst else s.url,
        "pid": inst.pid if inst else None,
        "data_dir": str(s.data_dir),
        "config": str(s.config_path) if s.config_path else None,
    }
    if inst is not None and inst.health is not None:
        status["version"] = inst.health.get("version")
        try:
            rt = launcher.http_json(inst.url + "/api/v1/runtime")
            sessions = launcher.http_json(inst.url + "/api/v1/sessions")
            ctl = launcher.http_json(inst.url + "/api/v1/control")
        except Exception as exc:
            status["error"] = str(exc)
        else:
            dev = rt.get("device") or {}
            status["runtime"] = {
                "state": rt.get("state"),
                "source": dev.get("display_name"),
                "recording": rt.get("recording"),
                "apps": len(rt.get("apps") or []),
            }
            active = sessions.get("active")
            status["session"] = active.get("id") if active else None
            status["command_output"] = "on" if ctl.get("router_on") else "off"
    if args.json:
        _print_json(status)
    elif status["running"]:
        r = status.get("runtime", {})
        print(
            f"Concord {status.get('version')} is running at {status['url']} (pid {status['pid']})"
        )
        print(f"  source: {r.get('source') or 'none'} ({r.get('state')})")
        rec = r.get("recording") or "no"
        print(f"  recording: {rec} · command output: {status.get('command_output')}")
        print(f"  research session: {status.get('session') or 'none'}")
        print(f"  data: {status['data_dir']}")
    else:
        print(f"Concord is not running (would use {status['url']}, data {status['data_dir']}).")
    return 0 if status["running"] else 3


def cmd_doctor(args: argparse.Namespace) -> int:
    from concord import doctor

    _apply_overrides(args)
    config_path: Path | None = None
    try:
        from concord.server.settings import Settings

        s = Settings.from_env()
        data_dir, host, port, allow, config_path = (
            s.data_dir,
            s.host,
            s.port,
            s.allow_remote,
            s.config_path,
        )
    except ConfigError:
        # the config problem is itself reported as a failed check
        from concord.config import default_data_dir

        data_dir, host, port, allow = default_data_dir(), "127.0.0.1", 8000, False
        config_path = default_config_path()
    report = doctor.run(
        data_dir=data_dir,
        host=host,
        port=port,
        allow_remote=allow,
        config_path=config_path,
        discover_plugins=not args.no_plugins,
    )
    md = doctor.to_markdown(report)
    written: list[Path] = []
    if args.json:
        Path(args.json).write_text(json.dumps(report, indent=1) + "\n")
        written.append(Path(args.json))
    if args.markdown:
        Path(args.markdown).write_text(md)
        written.append(Path(args.markdown))
    if not written and not args.print:
        j, m = doctor.write(report, data_dir / "support")
        written += [j, m]
    if args.print == "json":
        _print_json(report)
    elif args.print == "markdown":
        print(md)
    else:
        s2 = report["summary"]
        for c in report["checks"]:
            if c["status"] in ("warn", "fail"):
                print(
                    f"[{c['status'].upper()}] {c['title']}: {c['detail']}"
                    + (f" — {c['hint']}" if c.get("hint") else "")
                )
        print(f"{s2['fail']} failed, {s2['warn']} warning(s), {s2['ok']} ok.")
        for p in written:
            print(f"support report: {p}")
        print("The report contains no neural data and no personal data; see its last section.")
    return 1 if report["summary"]["fail"] else 0


def cmd_config(args: argparse.Namespace) -> int:
    _apply_overrides(args)
    path = default_config_path()
    if args.action == "path":
        print(path)
        return 0
    if args.action == "init":
        if path.exists():
            print(f"concord: {path} already exists (not overwritten)", file=sys.stderr)
            return 1
        write_template(path)
        print(f"wrote {path} (mode 600)")
        return 0
    if args.action == "template":
        print(template())
        return 0
    try:
        cfg = load_config(path)
        from concord.server.settings import Settings

        s = Settings.from_env(cfg)
    except ConfigError as exc:
        print(f"concord: {exc}", file=sys.stderr)
        return 2
    shown = {
        "config_file": str(path) + ("" if cfg.exists else " (not present; defaults apply)"),
        "host": s.host,
        "port": s.port,
        "allow_remote": s.allow_remote,
        "open_browser": s.open_browser,
        "log_level": s.log_level,
        "data_dir": str(s.data_dir),
        "reports_dir": str(s.reports_dir),
        "console": str(s.static_dir) if s.static_dir else None,
        "simulation": s.enable_sim,
        "plugins_discover": s.discover_plugins,
        "retention_days": s.retention.as_dict(),
    }
    _print_json(shown)
    return 0


def cmd_dataset(args: argparse.Namespace) -> int:
    from concord.datasets import fetch, manifest

    s = _settings(args)
    m = manifest(args.dataset)
    dest = s.datasets_dir / f"dandi-{m.dandiset}"
    argv = [args.dataset, "--dest", str(dest)]
    if args.all_calib:
        argv.append("--all-calib")
    if args.list:
        argv.append("--list")
    return fetch.main(argv)


def cmd_reproduce(args: argparse.Namespace) -> int:
    try:
        from concord.reproduce import main as reproduce_main
    except ImportError as exc:
        print(
            f"concord reproduce needs numpy: pip install 'concordos[dsp]' ({exc})", file=sys.stderr
        )
        return 1
    argv = [str(args.bundle)]
    if args.json:
        argv += ["--json", str(args.json)]
    return reproduce_main(argv)


# --------------------------------------------------------------------------- parser


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="concord",
        description="Concord: read-only neural interface runtime (research use only).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("\n\n")[1] if __doc__ else None,
    )
    ap.add_argument("--version", action="version", version=f"Concord {__version__}")
    sub = ap.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def common(p: argparse.ArgumentParser, server: bool = True) -> None:
        p.add_argument("--config", help="config file (default: see `concord config path`)")
        p.add_argument("--data-dir", help="data directory (overrides the config file)")
        p.add_argument("--port", type=int, help="TCP port (default 8000)")
        if server:
            p.add_argument("--host", help="bind address (default 127.0.0.1)")
            p.add_argument(
                "--allow-remote",
                action="store_true",
                help="permit a non-loopback --host (no authentication; not recommended)",
            )
            p.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    p = sub.add_parser("start", help="start the server in the background and open the console")
    common(p)
    p.add_argument("--no-browser", action="store_true", help="do not open the console")
    p.add_argument("--foreground", action="store_true", help="run here instead (Ctrl-C stops)")
    p.add_argument("--timeout", type=float, default=90.0, help="seconds to wait for startup")
    p.set_defaults(fn=cmd_start)

    p = sub.add_parser(
        "stop", help="safe stop (control off, recording closed), then end the server"
    )
    common(p, server=False)
    p.add_argument("--timeout", type=float, default=30.0)
    p.set_defaults(fn=cmd_stop)

    p = sub.add_parser("status", help="whether Concord runs, and what it is doing")
    common(p, server=False)
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_status)

    p = sub.add_parser(
        "doctor", help="diagnostics and a support report (no neural or personal data)"
    )
    common(p, server=False)
    p.add_argument("--json", help="write the JSON report here")
    p.add_argument("--markdown", help="write the Markdown report here")
    p.add_argument("--print", choices=["json", "markdown"], help="print the report")
    p.add_argument("--no-plugins", action="store_true", help="skip plugin discovery")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("version", help="versions of Concord and its packages")
    p.add_argument("--json", action="store_true")
    p.set_defaults(fn=cmd_version)

    p = sub.add_parser(
        "config", help="the config file: path, show (effective settings), init, template"
    )
    p.add_argument(
        "action", choices=["path", "show", "init", "template"], nargs="?", default="show"
    )
    p.add_argument("--config", help="config file to use")
    p.set_defaults(fn=cmd_config)

    p = sub.add_parser(
        "dataset", help="download + verify the public demo recordings (DANDI 000954)"
    )
    common(p, server=False)
    p.add_argument("dataset", nargs="?", default="falcon-h1")
    p.add_argument("--all-calib", action="store_true", help="all 13 calibration blocks (~66 MiB)")
    p.add_argument("--list", action="store_true", help="list the pinned files")
    p.set_defaults(fn=cmd_dataset)

    p = sub.add_parser("reproduce", help="verify a session export and re-run its evaluation")
    p.add_argument("bundle", type=Path)
    p.add_argument("--json", type=Path, help="write the reproduction report here")
    p.set_defaults(fn=cmd_reproduce)

    p = sub.add_parser("serve", help="run the server in the foreground (what `start` runs)")
    common(p)
    p.set_defaults(fn=cmd_serve)

    p = sub.add_parser(
        "publish",
        help="test streams for rehearsing without hardware (LSL, Open Ephys); declared "
        "synthetic or prerecorded. `concord publish --help` lists them",
        add_help=False,
    )
    p.add_argument("publish_args", nargs=argparse.REMAINDER)
    p.set_defaults(fn=cmd_publish)
    return ap


def cmd_publish(args: argparse.Namespace) -> int:
    """`concord publish …` = `python -m concord.testing.publish …`, also in the desktop app
    (whose bundled program is not a Python interpreter), so app users can rehearse too."""
    from concord.testing.publish import main as publish_main

    return publish_main(list(args.publish_args))


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["publish"]:  # its own options (incl. --help) go to the publisher unparsed
        return cmd_publish(argparse.Namespace(publish_args=argv[1:]))
    args = parser().parse_args(argv)
    code: int = args.fn(args)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
