"""The plugin host: runs ONE source plugin in its own process.

Usage::

    python -m concord_adapter_sdk.host <entry-point-name | module:Class>   # serve (IPC)
    python -m concord_adapter_sdk.host --list [--discover-timeout 1.0]     # JSON on stdout
    python -m concord_adapter_sdk.host --check <plugin> [--device KEY] [--option k=v ...]

Serve mode speaks ``concord.plugin-ipc/1`` (see :mod:`concord_adapter_sdk.ipc`) on the
process's original stdin/stdout. Before any plugin code is imported, those two file
descriptors are moved to private descriptors; fd 1 is pointed at stderr and fd 0 at
/dev/null, so a plugin's ``print()`` (or a C library writing to stdout) ends up in the log
and cannot corrupt the IPC channel.

Everything the plugin declares or returns is validated (:mod:`concord_adapter_sdk.validate`)
before it is sent. Plugin exceptions become typed errors; an invalid chunk stops the
session.

``--list`` enumerates the ``concord.sources`` entry points WITHOUT importing them and asks
one fresh host process per plugin for its manifest (and, optionally, its devices), so a
plugin that crashes, hangs or exits on import cannot affect the others.
"""

from __future__ import annotations

import argparse
import contextlib
import importlib
import json
import logging
import math
import os
import sys
import time
import traceback
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from importlib import metadata
from typing import IO, Any, TypeVar

from concord_adapter_sdk import __version__, ipc
from concord_adapter_sdk import validate as v
from concord_adapter_sdk.api import (
    API_VERSION,
    ENTRY_POINT_GROUP,
    Chunk,
    ConfigurationChanged,
    InvalidOptions,
    LinkLost,
    MarkerChunk,
    OpenFailed,
    PluginError,
    PluginManifest,
    SourcePlugin,
    SourceSession,
)

log = logging.getLogger("concord.plugin_host")
T = TypeVar("T")
MAX_READ_TIMEOUT_S = 10.0
MAX_DISCOVER_TIMEOUT_S = 30.0
TRACEBACK_CHARS = 4000


class _Reply(Exception):
    """An error answer to the current request."""

    def __init__(
        self,
        type_: str,
        message: str,
        *,
        tb: str | None = None,
        problems: Sequence[v.Problem] = (),
    ) -> None:
        self.type = type_
        self.message = message
        self.tb = tb
        self.problems = list(problems)
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "message": self.message,
            "traceback": self.tb,
            "problems": [p.to_dict() for p in self.problems],
        }


def traceback_summary(exc: BaseException) -> str:
    text = "".join(traceback.format_exception(exc))
    return text if len(text) <= TRACEBACK_CHARS else "…" + text[-TRACEBACK_CHARS:]


def _call_plugin(what: str, fn: Callable[[], T]) -> T:
    """Run plugin code; map its exceptions to typed IPC errors."""
    try:
        return fn()
    except InvalidOptions as exc:
        raise _Reply(ipc.INVALID_OPTIONS, str(exc) or "invalid options") from exc
    except OpenFailed as exc:
        raise _Reply(ipc.OPEN_FAILED, str(exc) or "open failed") from exc
    except ConfigurationChanged as exc:
        raise _Reply(ipc.CONFIGURATION_CHANGED, str(exc) or "configuration changed") from exc
    except LinkLost as exc:
        raise _Reply(ipc.LINK_LOST, str(exc) or "link lost") from exc
    except PluginError as exc:
        raise _Reply(ipc.PLUGIN_ERROR, str(exc) or type(exc).__name__) from exc
    except (Exception, SystemExit) as exc:
        log.exception("plugin %s raised", what)
        raise _Reply(
            ipc.INTERNAL_ERROR,
            f"{what} raised {type(exc).__name__}: {exc}"[:500],
            tb=traceback_summary(exc),
        ) from exc


# ----------------------------------------------------------------------------- loading


class LoadedPlugin:
    def __init__(
        self,
        plugin: SourcePlugin,
        manifest: PluginManifest | None,
        problems: list[v.Problem],
        entry: dict[str, Any],
    ) -> None:
        self.plugin = plugin
        self.manifest = manifest
        self.problems = problems
        self.entry = entry

    @property
    def compatible(self) -> bool:
        return self.manifest is not None and not v.has_errors(self.problems)


def load_plugin(ref: str) -> LoadedPlugin:
    """Import and instantiate a plugin by entry-point name or ``module:Class``."""
    entry: dict[str, Any] = {"ref": ref, "name": None, "value": None, "dist": None}
    problems: list[v.Problem] = []
    if ":" in ref:
        module, _, attr = ref.partition(":")
        entry["value"] = ref
        obj: Any = importlib.import_module(module)
        for part in attr.split("."):
            obj = getattr(obj, part)
    else:
        eps = list(metadata.entry_points(group=ENTRY_POINT_GROUP, name=ref))
        if not eps:
            raise LookupError(f"no '{ENTRY_POINT_GROUP}' entry point named {ref!r} is installed")
        if len(eps) > 1:
            dists = sorted(str(ep.dist.name) if ep.dist else "?" for ep in eps)
            raise LookupError(f"entry point {ref!r} is provided by several distributions: {dists}")
        ep = eps[0]
        entry.update(name=ep.name, value=ep.value)
        if ep.dist is not None:
            entry["dist"] = {"name": ep.dist.name, "version": ep.dist.version}
        problems += v.validate_entry_point_name(ep.name)
        obj = ep.load()
    if not (isinstance(obj, type) and issubclass(obj, SourcePlugin)):
        raise TypeError(f"{ref!r} is not a SourcePlugin subclass (got {obj!r})"[:300])
    manifest = getattr(obj, "manifest", None)
    problems += v.validate_manifest(manifest)
    if isinstance(manifest, PluginManifest) and entry["dist"] is not None:
        dist_name = str(entry["dist"]["name"])
        if _norm(dist_name) != _norm(manifest.name):
            problems.append(
                v.Problem(
                    "manifest.name.dist_mismatch",
                    f"manifest name {manifest.name!r} differs from the installed distribution "
                    f"{dist_name!r}",
                    "warning",
                    "name",
                )
            )
        if entry["dist"]["version"] != manifest.version:
            problems.append(
                v.Problem(
                    "manifest.version.dist_mismatch",
                    f"manifest version {manifest.version!r} differs from the installed "
                    f"distribution version {entry['dist']['version']!r}",
                    "warning",
                    "version",
                )
            )
    plugin = obj()
    return LoadedPlugin(
        plugin, manifest if isinstance(manifest, PluginManifest) else None, problems, entry
    )


def _norm(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


# ----------------------------------------------------------------------------- serving


class Host:
    def __init__(self, ref: str, out: IO[bytes]) -> None:
        self.ref = ref
        self.out = out
        self.loaded: LoadedPlugin | None = None
        self.load_error: _Reply | None = None
        self.session: SourceSession | None = None
        self.validator: v.ChunkValidator | None = None
        self.counters: Counter[str] = Counter()
        self.stopped_reason: str | None = None

    def load(self) -> None:
        try:
            self.loaded = load_plugin(self.ref)
        except (Exception, SystemExit) as exc:
            log.exception("loading plugin %s failed", self.ref)
            self.load_error = _Reply(
                ipc.LOAD_FAILED,
                f"loading plugin {self.ref!r} failed: {type(exc).__name__}: {exc}"[:500],
                tb=traceback_summary(exc),
            )

    def send(self, header: Mapping[str, Any], buffers: Sequence[Any] = ()) -> None:
        ipc.write_message(self.out, header, buffers)

    def hello(self) -> dict[str, Any]:
        return {
            "type": "hello",
            "protocol": ipc.PROTOCOL,
            "api_version": API_VERSION,
            "sdk_version": __version__,
            "python": sys.version.split()[0],
            "pid": os.getpid(),
            "plugin": self.ref,
            "loaded": self.loaded is not None,
            "load_error": self.load_error.to_dict() if self.load_error else None,
        }

    # -- commands ------------------------------------------------------------------
    def _plugin(self) -> LoadedPlugin:
        if self.loaded is None:
            assert self.load_error is not None
            raise self.load_error
        return self.loaded

    def cmd_ping(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return {"nonce": args.get("nonce"), "monotonic": time.monotonic()}

    def cmd_manifest(self, args: Mapping[str, Any]) -> dict[str, Any]:
        lp = self._plugin()
        return {
            "manifest": ipc.manifest_to_dict(lp.manifest) if lp.manifest else None,
            "problems": [p.to_dict() for p in lp.problems],
            "compatible": lp.compatible,
            "entry": lp.entry,
        }

    def _compatible(self) -> LoadedPlugin:
        lp = self._plugin()
        if not lp.compatible:
            raise _Reply(
                ipc.INCOMPATIBLE,
                f"plugin rejected: {v.summarize(lp.problems)}",
                problems=v.errors(lp.problems),
            )
        return lp

    def cmd_discover(self, args: Mapping[str, Any]) -> dict[str, Any]:
        lp = self._compatible()
        t = _timeout(args, MAX_DISCOVER_TIMEOUT_S, 1.0)
        devices = _call_plugin("discover()", lambda: lp.plugin.discover(t))
        problems = v.validate_devices(devices)
        if v.has_errors(problems):
            raise _Reply(
                ipc.INVALID_DEVICES,
                f"discover() returned invalid devices: {v.summarize(problems)}",
                problems=problems,
            )
        return {"devices": [ipc.device_to_dict(d) for d in devices]}

    def cmd_open(self, args: Mapping[str, Any]) -> dict[str, Any]:
        lp = self._compatible()
        assert lp.manifest is not None
        self._close_session()
        key = args.get("device_key")
        if not isinstance(key, str):
            raise _Reply(ipc.BAD_REQUEST, "open needs a string device_key")
        raw = args.get("options") or {}
        options, problems = v.validate_options(lp.manifest.options, raw)
        if v.has_errors(problems):
            raise _Reply(ipc.INVALID_OPTIONS, v.summarize(problems), problems=problems)
        session = _call_plugin("open()", lambda: lp.plugin.open(key, options))
        try:
            if not isinstance(session, SourceSession):
                raise _Reply(
                    ipc.INVALID_SESSION,
                    f"open() must return a SourceSession, got {type(session).__name__}",
                )
            info = _call_plugin("SourceSession.info", lambda: session.info)
            problems = v.validate_session_info(info, lp.manifest)
            if v.has_errors(problems):
                raise _Reply(
                    ipc.INVALID_SESSION,
                    f"session rejected: {v.summarize(problems)}",
                    problems=problems,
                )
        except _Reply:
            if isinstance(session, SourceSession):
                self._safe_close(session)
            raise
        self.session = session
        self.validator = v.ChunkValidator(info)
        self.counters.clear()
        self.stopped_reason = None
        return {
            "info": ipc.session_info_to_dict(info),
            "problems": [p.to_dict() for p in problems],
            "options": options,
        }

    def cmd_read(self, args: Mapping[str, Any]) -> tuple[dict[str, Any], list[Any]]:
        session, validator = self.session, self.validator
        if session is None or validator is None:
            reason = f" (stopped: {self.stopped_reason})" if self.stopped_reason else ""
            raise _Reply(ipc.NOT_OPEN, f"no open session{reason}")
        t = _timeout(args, MAX_READ_TIMEOUT_S, 0.1)
        items = _call_plugin("read()", lambda: session.read(t))
        problems = validator.check_all(items)
        if v.has_errors(problems):
            self.stopped_reason = v.summarize(problems)
            self._close_session()
            raise _Reply(
                ipc.INVALID_DATA,
                f"plugin sent invalid data; session stopped: {self.stopped_reason}",
                problems=problems,
            )
        send: list[Chunk | MarkerChunk] = []
        for item in items:
            n = len(item.labels) if isinstance(item, MarkerChunk) else item.data.shape[0]
            if n:
                send.append(item)
                self.counters["samples"] += n
                self.counters["chunks"] += 1
        heads, arrays = ipc.chunks_to_wire(send)
        self.counters["reads"] += 1
        self.counters["bytes"] += sum(a.nbytes for a in arrays)
        notices = [p.to_dict() for p in problems if p.severity != "error"]
        return {"chunks": heads, "notices": notices}, arrays

    def cmd_stats(self, args: Mapping[str, Any]) -> dict[str, Any]:
        stats: dict[str, int | float] = {}
        dropped = 0
        if self.session is not None:
            session = self.session
            raw = _call_plugin("stats()", lambda: session.stats())
            if isinstance(raw, Mapping):
                for k, val in list(raw.items())[:64]:
                    ok_key = isinstance(k, str) and 0 < len(k) <= 48
                    ok_val = isinstance(val, int | float) and not isinstance(val, bool)
                    if ok_key and ok_val and math.isfinite(val):
                        stats[k] = val
                    else:
                        dropped += 1
            else:
                dropped += 1
        return {"stats": stats, "invalid_stats": dropped, "host": dict(self.counters)}

    def cmd_close(self, args: Mapping[str, Any]) -> dict[str, Any]:
        self._close_session()
        return {}

    # -- helpers -------------------------------------------------------------------
    def _safe_close(self, session: SourceSession) -> None:
        try:
            session.close()
        except (Exception, SystemExit):
            log.exception("plugin close() raised (ignored)")

    def _close_session(self) -> None:
        session, self.session, self.validator = self.session, None, None
        if session is not None:
            self._safe_close(session)

    def handle(self, header: Mapping[str, Any]) -> bool:
        """Answer one request. Returns False when the host should exit."""
        rid = header.get("id")
        cmd = header.get("cmd")
        args = header.get("args") if isinstance(header.get("args"), dict) else {}
        assert isinstance(args, dict)
        handler = getattr(self, f"cmd_{cmd}", None) if isinstance(cmd, str) else None
        if cmd == "shutdown":
            self._close_session()
            self.send({"id": rid, "ok": True, "result": {}})
            return False
        try:
            if handler is None:
                raise _Reply(ipc.BAD_REQUEST, f"unknown command {cmd!r}")
            result = handler(args)
            arrays: list[Any] = []
            if isinstance(result, tuple):
                result, arrays = result
            self.send({"id": rid, "ok": True, "result": result}, arrays)
        except _Reply as r:
            self.send({"id": rid, "ok": False, "error": r.to_dict()})
        return True


def _timeout(args: Mapping[str, Any], limit: float, default: float) -> float:
    t = args.get("timeout_s", default)
    if isinstance(t, bool) or not isinstance(t, int | float) or not math.isfinite(t):
        return default
    return min(max(float(t), 0.0), limit)


def _claim_stdio() -> tuple[IO[bytes], IO[bytes]]:
    """Move the IPC channel off fds 0/1 before any plugin code runs."""
    sys.stdout.flush()
    in_fd = os.dup(0)  # non-inheritable: child processes of the plugin do not get them
    out_fd = os.dup(1)
    os.dup2(2, 1)  # fd 1 -> stderr: print() / C printf from plugin code go to the log
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    os.close(devnull)
    sys.stdin = open(os.devnull, encoding="utf-8")  # noqa: SIM115 - process lifetime
    # plugin text output must never raise: on Windows the streams use the ANSI code page
    # (cp1252), which cannot encode e.g. "→"; such characters are written escaped instead
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(errors="backslashreplace")
    return os.fdopen(in_fd, "rb"), os.fdopen(out_fd, "wb")


def serve(ref: str) -> int:
    ipc_in, ipc_out = _claim_stdio()
    logging.basicConfig(
        stream=sys.stderr,
        level=os.environ.get("CONCORD_PLUGIN_LOG_LEVEL", "INFO").upper(),
        format=f"[plugin {ref} pid {os.getpid()}] %(levelname)s %(name)s: %(message)s",
    )
    host = Host(ref, ipc_out)
    host.load()
    host.send(host.hello())
    try:
        while True:
            msg = ipc.read_message(ipc_in)
            if msg is None:
                break
            if not host.handle(msg[0]):
                break
    except ipc.WireError as exc:
        log.error("protocol error from the runtime: %s", exc)
        return 3
    except BrokenPipeError:
        return 0
    finally:
        host._close_session()
    return 0


# ----------------------------------------------------------------------------- --list


def _probe(
    name: str, discover_timeout_s: float, timeout_s: float, python: str | None
) -> dict[str, Any]:
    from concord_adapter_sdk.client import HostDied, HostError, SyncHostClient

    rec: dict[str, Any] = {}
    client: SyncHostClient | None = None
    try:
        client = SyncHostClient(name, python=python, hello_timeout_s=timeout_s)
        if not client.hello.get("loaded"):
            rec["status"] = "load_error"
            rec["error"] = client.hello.get("load_error")
            return rec
        m = client.request("manifest", timeout_s=timeout_s)[0]
        rec.update(manifest=m.get("manifest"), problems=m.get("problems", []))
        rec["status"] = "compatible" if m.get("compatible") else "rejected"
        if m.get("compatible") and discover_timeout_s > 0:
            try:
                # discover() may scan for discover_timeout_s; a little slack, never unbounded
                rec["devices"] = client.request(
                    "discover",
                    {"timeout_s": discover_timeout_s},
                    timeout_s=discover_timeout_s + min(5.0, timeout_s),
                )[0]["devices"]
            except HostError as exc:
                rec["discovery_error"] = {"type": exc.type, "message": exc.message}
            except HostDied as exc:  # hung or crashed in discover(): still listed, no devices
                rec["discovery_error"] = {"type": "HostDied", "message": str(exc)}
    except HostDied as exc:
        rec.setdefault("status", "load_error")
        rec["error"] = {"type": "HostDied", "message": str(exc), "traceback": None}
    except HostError as exc:
        rec["status"] = "load_error"
        rec["error"] = {"type": exc.type, "message": exc.message, "traceback": exc.traceback}
    finally:
        if client is not None:
            client.shutdown()
            rec["stderr_tail"] = list(client.stderr_tail)[-20:]
    return rec


def list_plugins(
    discover_timeout_s: float = 0.0, timeout_s: float = 15.0, python: str | None = None
) -> dict[str, Any]:
    """All installed ``concord.sources`` entry points, each probed in its own process."""
    eps = list(metadata.entry_points(group=ENTRY_POINT_GROUP))
    counts = Counter(ep.name for ep in eps)
    records: list[dict[str, Any]] = []
    to_probe: list[tuple[dict[str, Any], str]] = []
    for ep in sorted(eps, key=lambda e: (e.name, e.value)):
        rec: dict[str, Any] = {
            "name": ep.name,
            "entry": ep.value,
            "dist": {"name": ep.dist.name, "version": ep.dist.version} if ep.dist else None,
            "status": "rejected",
            "manifest": None,
            "problems": [],
            "error": None,
            "devices": None,
            "discovery_error": None,
            "stderr_tail": [],
        }
        records.append(rec)
        name_problems = v.validate_entry_point_name(ep.name)
        if counts[ep.name] > 1:
            name_problems.append(
                v.Problem(
                    "entry_point.duplicate",
                    f"entry point {ep.name!r} is installed by more than one distribution",
                    "error",
                    "entry point",
                )
            )
        if name_problems:
            rec["problems"] = [p.to_dict() for p in name_problems]
            continue
        to_probe.append((rec, ep.name))
    if to_probe:
        with ThreadPoolExecutor(max_workers=min(8, len(to_probe))) as pool:
            futures = [
                (rec, pool.submit(_probe, name, discover_timeout_s, timeout_s, python))
                for rec, name in to_probe
            ]
            for rec, fut in futures:
                rec.update(fut.result())
    return {
        "protocol": ipc.PROTOCOL,
        "api_version": API_VERSION,
        "sdk_version": __version__,
        "python": sys.executable,
        "plugins": records,
    }


# ----------------------------------------------------------------------------- --check


def check(ref: str, device: str | None, options: dict[str, str], seconds: float) -> int:
    """Run a plugin through a real host and print what Concord would see (for authors)."""
    from concord_adapter_sdk.client import HostDied, HostError, SyncHostClient

    def say(msg: str) -> None:
        print(msg, flush=True)

    failed = False
    with SyncHostClient(ref) as c:
        if not c.hello.get("loaded"):
            err = c.hello.get("load_error") or {}
            say(f"LOAD FAILED: {err.get('message')}\n{err.get('traceback') or ''}")
            return 1
        m = c.manifest()
        man = m.get("manifest") or {}
        say(f"plugin   {man.get('name')} {man.get('version')} (API {man.get('api_version')})")
        for p in m.get("problems", []):
            say(f"  {p['severity']:7s} {p['code']}: {p['where']} {p['message']}")
        if not m.get("compatible"):
            say("REJECTED: Concord would list this plugin but refuse to connect it.")
            return 1
        try:
            devices = c.discover(2.0)["devices"]
        except HostError as exc:
            say(f"discover() failed: {exc}")
            return 1
        for d in devices:
            say(f"device   {d['device_key']}: {d['display_name']}")
        key = device or (devices[0]["device_key"] if devices else None)
        if key is None:
            say("no device to open (pass --device KEY)")
            return 1
        try:
            opened = c.open(key, options)
        except HostError as exc:
            say(f"OPEN FAILED [{exc.type}]: {exc.message}")
            for p in exc.problems:
                say(f"  {p.get('severity')} {p.get('code')}: {p.get('where')} {p.get('message')}")
            return 1
        info = opened["info"]
        say(
            f"session  primary={info['primary_stream']} synthetic={info['synthetic']} "
            f"prerecorded={info['prerecorded']} origin={info['origin']}"
        )
        for s in info["streams"]:
            units = sorted({str(ch["unit"]) for ch in s["channels"]})
            say(
                f"  stream {s['stream_id']:12s} {s['role']:14s} {len(s['channels']):4d} ch "
                f"@ {s['nominal_rate_hz']:g} Hz clock={s['clock']['domain']} units={units} "
                f"modality={s['modality']}"
            )
        counts: Counter[str] = Counter()
        t0 = time.monotonic()
        try:
            while time.monotonic() - t0 < seconds:
                for ch in c.read(0.1):
                    n = len(ch.labels) if isinstance(ch, MarkerChunk) else ch.data.shape[0]
                    counts[ch.stream_id] += n
        except (HostError, HostDied) as exc:
            say(f"READ FAILED: {exc}")
            failed = True
        elapsed = time.monotonic() - t0
        for s in info["streams"]:
            n = counts[s["stream_id"]]
            rate = n / elapsed if elapsed > 0 else 0.0
            say(
                f"  read   {s['stream_id']:12s} {n:8d} samples in {elapsed:.2f} s "
                f"({rate:.1f}/s, nominal {s['nominal_rate_hz']:g})"
            )
        if not failed:
            say(f"stats    {c.stats()}")
    say("FAILED" if failed else "OK: all declarations and data passed validation")
    return 1 if failed else 0


# ----------------------------------------------------------------------------- main


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m concord_adapter_sdk.host",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("plugin", nargs="?", help="entry-point name or module:Class")
    ap.add_argument("--list", action="store_true", help="list installed plugins as JSON")
    ap.add_argument(
        "--discover-timeout",
        type=float,
        default=0.0,
        help="with --list: also call discover() with this timeout (s)",
    )
    ap.add_argument(
        "--timeout",
        type=float,
        default=15.0,
        help="with --list: per-plugin start / manifest timeout (s)",
    )
    ap.add_argument("--check", action="store_true", help="run the plugin and print a report")
    ap.add_argument("--device", help="with --check: device key to open")
    ap.add_argument(
        "--option",
        action="append",
        default=[],
        metavar="NAME=VALUE",
        help="with --check: an open() option (repeatable)",
    )
    ap.add_argument("--seconds", type=float, default=3.0, help="with --check: read duration")
    a = ap.parse_args(argv)
    if a.list:
        doc = list_plugins(max(0.0, a.discover_timeout), a.timeout)
        sys.stdout.write(json.dumps(doc) + "\n")
        return 0
    if not a.plugin:
        ap.error("a plugin (entry-point name or module:Class) is required")
    if a.check:
        opts = dict(o.split("=", 1) for o in a.option if "=" in o)
        return check(a.plugin, a.device, opts, a.seconds)
    return serve(a.plugin)


if __name__ == "__main__":
    raise SystemExit(main())
