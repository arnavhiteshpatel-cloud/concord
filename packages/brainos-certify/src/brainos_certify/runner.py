"""Orchestrates a certification run.

Sequence (every step through the real plugin host, ``python -m brainos_adapter_sdk.host``):

1. host #1 starts; ``manifest``; plugin identity (metadata + file hashes); ``discover``
2. ``open`` #1 -> session metadata; main acquisition for ``--duration`` seconds while the
   host's CPU / RSS are sampled from /proc; ``stats``; IPC pings
3. clean ``close`` + ``open`` #2 in the same host -> time to first data, identity
4. SIGKILL host #1 mid-stream -> how the failure surfaces; host #2 starts, ``open`` #3 ->
   time to first data, identity; clean ``shutdown`` (exit code)
5. optional BrainOS runtime phase (``open`` #4 / #5 through ``PluginAdapter`` + ``Runtime``)
6. levels; JSON + Markdown report
"""

from __future__ import annotations

import contextlib
import datetime as dt
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from brainos_adapter_sdk import PluginManifest, SessionInfo, ipc
from brainos_adapter_sdk import validate as v
from brainos_adapter_sdk.client import HostDied, HostError, SyncHostClient

from brainos_certify import checks_static as cs
from brainos_certify import checks_stream as cst
from brainos_certify import levels as lv
from brainos_certify import procstat
from brainos_certify.acquire import Acquisition, acquire, new_acquisition
from brainos_certify.identity import collect_identity, host_env
from brainos_certify.model import Results
from brainos_certify.reconnect import KillOutcome, kill_mid_stream
from brainos_certify.runtime_phase import RUNTIME_CHECKS, run_runtime_phase

log = logging.getLogger(__name__)

PINGS = 30
KILL_STREAM_S = 0.5


@dataclass
class CertifyConfig:
    plugin: str  # entry-point name or module:Class
    device: str | None = None
    options: dict[str, str] = field(default_factory=dict)
    duration_s: float = 20.0
    reopen_s: float = 2.0
    rate_tolerance: float = 0.02
    read_timeout_s: float = 0.1
    read_grace_s: float = 5.0
    start_timeout_s: float = 30.0
    open_timeout_s: float = 30.0
    discover_timeout_s: float = 2.0
    kill_detect_limit_s: float = 2.0
    python: str | None = None
    extra_path: tuple[str, ...] = ()
    runtime: bool = True
    runtime_s: float = 5.0
    protocol_reference: str | None = None
    attestation: Path | None = None
    attestation_signature: Path | None = None
    attestation_public_key: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "plugin": self.plugin,
            "device": self.device,
            "duration_s": self.duration_s,
            "reopen_s": self.reopen_s,
            "rate_tolerance": self.rate_tolerance,
            "read_timeout_s": self.read_timeout_s,
            "read_grace_s": self.read_grace_s,
            "start_timeout_s": self.start_timeout_s,
            "open_timeout_s": self.open_timeout_s,
            "discover_timeout_s": self.discover_timeout_s,
            "kill_detect_limit_s": self.kill_detect_limit_s,
            "python": self.python,
            "extra_path": list(self.extra_path),
            "runtime": self.runtime,
            "runtime_s": self.runtime_s,
            "protocol_reference": self.protocol_reference,
            "attestation": str(self.attestation) if self.attestation else None,
            "attestation_signature": str(self.attestation_signature)
            if self.attestation_signature
            else None,
            "attestation_public_key": str(self.attestation_public_key)
            if self.attestation_public_key
            else None,
        }


@dataclass
class RunState:
    hello: dict[str, Any] | None = None
    manifest: PluginManifest | None = None
    compatible: bool = False
    identity: dict[str, Any] = field(default_factory=dict)
    entry_point_name: str | None = None
    device_key: str | None = None
    info: SessionInfo | None = None
    resolved_options: dict[str, Any] = field(default_factory=dict)
    acqs: dict[str, Acquisition] = field(default_factory=dict)
    snapshots: dict[str, dict[str, Any]] = field(default_factory=dict)
    stats_reply: dict[str, Any] | None = None
    stats_error: str | None = None
    sampler: dict[str, Any] | None = None
    ping_ms: list[float] = field(default_factory=list)
    kill: KillOutcome | None = None
    host_log: list[str] = field(default_factory=list)
    runtime_facts: dict[str, Any] = field(default_factory=dict)
    stopped: str | None = None  # why the host phases ended early


def _err(exc: Exception) -> str:
    if isinstance(exc, HostError):
        first = exc.problems[0] if exc.problems else None
        code = f" [{first.get('code')}]" if isinstance(first, dict) else ""
        return f"{exc.type}: {exc.message}{code}"
    return f"{type(exc).__name__}: {exc}"


class Runner:
    def __init__(self, cfg: CertifyConfig, progress: Any = None) -> None:
        self.cfg = cfg
        self.results = Results()
        self.st = RunState()
        self._say = progress or (lambda _msg: None)
        self._env = host_env(cfg.extra_path)

    def say(self, msg: str) -> None:
        self._say(msg)

    def _client(self) -> SyncHostClient:
        return SyncHostClient(
            self.cfg.plugin,
            python=self.cfg.python,
            env=self._env,
            hello_timeout_s=self.cfg.start_timeout_s,
        )

    # ------------------------------------------------------------------ main
    def run(self) -> dict[str, Any]:
        started = dt.datetime.now(dt.UTC)
        t0 = time.monotonic()
        try:
            self._host_phases()
        except Exception as exc:  # a certifier bug must still produce a report
            log.exception("certification run failed")
            self.st.stopped = f"certifier error: {_err(exc)}"
        try:
            self.evaluate_streams()
        except Exception as exc:
            log.exception("evaluating the acquisitions failed")
            self.st.stopped = f"certifier error: {_err(exc)}"
        self._runtime_phase()
        cs.check_channel_identity(self.results, self.st.snapshots)
        checks = self.results.finalize(
            f"not run: {self.st.stopped}" if self.st.stopped else "not run"
        )
        rules = lv.protocol_consistency(
            self.cfg.protocol_reference,
            self.st.manifest,
            self.st.info,
            dict(self.st.identity.get("versions") or {}),
        )
        attestation = None
        if self.cfg.attestation is not None:
            mod = self.st.identity.get("module") or {}
            attestation = lv.check_attestation(
                self.cfg.attestation,
                self.cfg.attestation_signature,
                self.cfg.attestation_public_key,
                plugin_name=self.st.manifest.name if self.st.manifest else None,
                plugin_version=self.st.manifest.version if self.st.manifest else None,
                tree_sha256=mod.get("tree_sha256"),
            )
        levels = lv.evaluate(
            checks,
            reference=self.cfg.protocol_reference,
            rules=rules,
            attestation=attestation,
        )
        from brainos_certify.report import build_report

        return build_report(
            cfg=self.cfg,
            st=self.st,
            checks=checks,
            levels=levels,
            rules=rules,
            attestation=attestation,
            started=started,
            elapsed_s=time.monotonic() - t0,
        )

    # ------------------------------------------------------------------ host phases
    def _host_phases(self) -> None:
        cfg, r, st = self.cfg, self.results, self.st
        self.say(f"starting plugin host for {cfg.plugin}")
        t_spawn = time.monotonic()
        try:
            c1 = self._client()
        except HostDied as exc:
            r.set("manifest.load", "fail", f"plugin host did not start: {exc}")
            st.stopped = "the plugin host did not start"
            self._identity()
            return
        try:
            self._host1(c1, t_spawn)
        finally:
            c1.shutdown()
            st.host_log.extend(list(c1.stderr_tail)[-40:])

    def _host1(self, c1: SyncHostClient, t_spawn: float) -> None:
        cfg, r, st = self.cfg, self.results, self.st
        hello = c1.hello
        st.hello = hello
        startup = time.monotonic() - t_spawn
        if not hello.get("loaded"):
            err = hello.get("load_error") or {}
            tb = str(err.get("traceback") or "").strip().splitlines()
            r.set(
                "manifest.load",
                "fail",
                f"{err.get('type', 'LoadFailed')}: {err.get('message')}",
                {"load_error": err, "traceback_tail": tb[-6:], "startup_s": round(startup, 3)},
            )
            st.stopped = "the plugin failed to load"
            self._identity()
            return
        r.set(
            "manifest.load",
            "pass",
            f"plugin loaded in its own host process (pid {hello.get('pid')}) in {startup:.2f} s",
            {
                "pid": hello.get("pid"),
                "protocol": hello.get("protocol"),
                "host_sdk_version": hello.get("sdk_version"),
                "host_api_version": hello.get("api_version"),
                "host_python": hello.get("python"),
                "startup_s": round(startup, 3),
            },
        )
        try:
            reply = c1.request("manifest", timeout_s=cfg.open_timeout_s)[0]
        except (HostError, HostDied) as exc:
            r.set("manifest.valid", "fail", f"manifest request failed: {_err(exc)}")
            st.stopped = "no manifest"
            self._identity()
            return
        st.manifest = cs.check_manifest(r, reply, hello)
        st.compatible = bool(reply.get("compatible"))
        self._identity([st.manifest.ecosystem] if st.manifest and st.manifest.ecosystem else [])
        if st.manifest is None or not st.compatible:
            st.stopped = "the plugin host rejects the plugin (manifest)"
            return
        if not self._discover(c1):
            return
        assert st.device_key is not None
        self.say(f"opening device {st.device_key!r}")
        t = time.monotonic()
        try:
            opened = c1.request(
                "open",
                {"device_key": st.device_key, "options": dict(cfg.options)},
                timeout_s=cfg.open_timeout_s,
            )[0]
        except (HostError, HostDied) as exc:
            problems = exc.problems if isinstance(exc, HostError) else []
            r.set(
                "metadata.session_valid",
                "fail",
                f"open() failed: {_err(exc)}",
                {"problems": problems[:20], "options": cs.redact(cfg.options)},
            )
            st.stopped = "open() failed"
            return
        open_s = time.monotonic() - t
        st.resolved_options = dict(opened.get("options") or {})
        info = cs.check_session_metadata(
            r, opened, st.manifest, redacted_options=cs.redact(st.resolved_options), open_s=open_s
        )
        if info is None:
            st.stopped = "the session was rejected"
            return
        st.info = info
        st.snapshots["open_1"] = cs.session_identity(info)
        self._main_acquisition(c1, info)
        main = st.acqs["main"]
        if main.failure is not None and main.failure.kind == "HostDied":
            st.stopped = "the plugin host died during the main acquisition"
            r.not_run(
                ["reconnect.clean_reopen", "reconnect.host_killed", "integrity.plugin_stats"],
                f"not run: {st.stopped}",
            )
            return
        self._stats_and_pings(c1)
        if main.failure is not None or main.samples == 0:
            st.stopped = "the main acquisition failed"
            r.not_run(
                ["reconnect.clean_reopen", "reconnect.host_killed"],
                "not run: the main acquisition failed (see integrity.read)",
            )
            return
        if not self._clean_reopen(c1):
            return
        self._kill_and_fresh_host(c1)

    def _identity(self, versions: list[str] | None = None) -> None:
        """Entry point, distribution and file hashes (also when the plugin fails to load:
        identity is read from metadata and files, never by importing the plugin)."""
        cfg, r, st = self.cfg, self.results, self.st
        self.say("collecting plugin identity (metadata, RECORD and file hashes)")
        st.identity = collect_identity(
            cfg.plugin, python=cfg.python, extra_path=cfg.extra_path, versions=versions or []
        )
        st.entry_point_name = cs.check_entry_point(r, st.identity, cfg.plugin)
        cs.check_distribution(r, st.identity, st.manifest)

    def _discover(self, c1: SyncHostClient) -> bool:
        cfg, r, st = self.cfg, self.results, self.st
        t = time.monotonic()
        try:
            res = c1.request(
                "discover",
                {"timeout_s": cfg.discover_timeout_s},
                timeout_s=cfg.discover_timeout_s + 10.0,
            )[0]
        except (HostError, HostDied) as exc:
            r.set("manifest.discover", "fail", f"discover() failed: {_err(exc)}")
            st.stopped = "discover() failed"
            return False
        took = time.monotonic() - t
        try:
            devices = [ipc.device_from_dict(d) for d in res.get("devices") or []]
        except ipc.WireError as exc:
            r.set("manifest.discover", "fail", f"device list malformed: {exc}")
            st.stopped = "discover() failed"
            return False
        problems = v.validate_devices(devices)
        keys = [d.device_key for d in devices]
        ev = {
            "devices": [ipc.device_to_dict(d) for d in devices][:20],
            "discover_s": round(took, 3),
            "problems": [p.to_dict() for p in problems],
        }
        if v.has_errors(problems):
            r.set("manifest.discover", "fail", v.summarize(problems), ev)
            st.stopped = "discover() returned invalid devices"
            return False
        key = cfg.device or (keys[0] if keys else None)
        if key is None:
            r.set(
                "manifest.discover",
                "fail",
                "discover() returned no device and no --device "
                "was given (plugins that cannot enumerate return one configurable entry)",
                ev,
            )
            st.stopped = "no device to open"
            return False
        st.device_key = key
        ev["tested_device"] = key
        if cfg.device and cfg.device not in keys:
            r.set(
                "manifest.discover",
                "warn",
                f"device {cfg.device!r} is not among the discovered {keys}; opened as given",
                ev,
            )
        else:
            r.set(
                "manifest.discover",
                "pass",
                f"{len(keys)} device(s) {keys} in {took:.2f} s; testing {key!r}",
                ev,
            )
        return True

    def _main_acquisition(self, c1: SyncHostClient, info: SessionInfo) -> None:
        cfg, st = self.cfg, self.st
        self.say(f"main acquisition: {cfg.duration_s:g} s")
        pid = c1.proc.pid
        sampler = procstat.ProcSampler(pid).start() if procstat.available(pid) else None
        a = new_acquisition(info)
        acquire(
            c1,
            a,
            v.ChunkValidator(info),
            cfg.duration_s,
            read_timeout_s=cfg.read_timeout_s,
            grace_s=cfg.read_grace_s,
        )
        st.sampler = sampler.stop() if sampler is not None else None
        st.acqs["main"] = a

    def _stats_and_pings(self, c1: SyncHostClient) -> None:
        st = self.st
        try:
            st.stats_reply = c1.stats()
        except HostError as exc:
            st.stats_error = _err(exc)
        except HostDied as exc:
            st.stats_error = _err(exc)
            return
        for i in range(PINGS):
            t = time.monotonic()
            try:
                c1.request("ping", {"nonce": i}, timeout_s=5.0)
            except (HostError, HostDied):
                break
            st.ping_ms.append((time.monotonic() - t) * 1e3)

    def _clean_reopen(self, c1: SyncHostClient) -> bool:
        cfg, r, st = self.cfg, self.results, self.st
        assert st.device_key is not None
        self.say("clean close + reopen in the same host")
        t = time.monotonic()
        try:
            c1.close_session()
        except (HostError, HostDied) as exc:
            r.set("reconnect.clean_reopen", "fail", f"close failed: {_err(exc)}")
            r.not_run(["reconnect.host_killed"], "not run: close failed")
            return False
        close_s = time.monotonic() - t
        t = time.monotonic()
        try:
            opened = c1.request(
                "open",
                {"device_key": st.device_key, "options": dict(cfg.options)},
                timeout_s=cfg.open_timeout_s,
            )[0]
        except (HostError, HostDied) as exc:
            r.set(
                "reconnect.clean_reopen",
                "fail",
                f"reopen after a clean close failed: {_err(exc)}",
                {"close_s": round(close_s, 3)},
            )
            r.not_run(["reconnect.host_killed"], "not run: no streaming session to kill")
            return False
        open_s = time.monotonic() - t
        info = ipc.session_info_from_dict(opened.get("info") or {})
        snap = cs.session_identity(info)
        st.snapshots["reopen_same_host"] = snap
        b = new_acquisition(info)
        acquire(
            c1,
            b,
            v.ChunkValidator(info),
            cfg.reopen_s,
            read_timeout_s=cfg.read_timeout_s,
            grace_s=cfg.read_grace_s,
        )
        st.acqs["reopen"] = b
        diffs = cs.identity_diff(st.snapshots["open_1"], snap)
        first = open_s + b.first_data_s if b.first_data_s is not None else None
        ev = {
            "close_s": round(close_s, 3),
            "reopen_s": round(open_s, 3),
            "first_data_after_open_s": round(first, 3) if first is not None else None,
            "samples": b.samples,
            "read_s": round(b.duration_s, 3),
            "failure": b.failure.to_dict() if b.failure else None,
            "identity_unchanged": not diffs,
            "identity_differences": diffs[:10],
        }
        if b.failure is not None:
            r.set(
                "reconnect.clean_reopen",
                "fail",
                f"after reopen: {b.failure.type}: {b.failure.message}",
                ev,
            )
        elif b.samples == 0:
            r.set(
                "reconnect.clean_reopen",
                "fail",
                f"no data within {cfg.reopen_s:g} s of reopening",
                ev,
            )
        elif diffs:
            r.set("reconnect.clean_reopen", "fail", f"identity changed on reopen: {diffs[0]}", ev)
        else:
            r.set(
                "reconnect.clean_reopen",
                "pass",
                f"closed in {close_s * 1e3:.1f} ms, reopened in {open_s:.3f} s, first data "
                f"{first:.3f} s after open; identity unchanged",
                ev,
            )
        if b.failure is not None and b.failure.kind == "HostDied":
            r.not_run(["reconnect.host_killed"], "not run: the host died after reopening")
            return False
        return True

    def _kill_and_fresh_host(self, c1: SyncHostClient) -> None:
        cfg, r, st = self.cfg, self.results, self.st
        assert st.device_key is not None
        self.say("fault injection: SIGKILL the plugin host mid-stream")
        outcome = kill_mid_stream(
            c1, stream_s=KILL_STREAM_S, read_timeout_s=cfg.read_timeout_s, grace_s=cfg.read_grace_s
        )
        st.kill = outcome
        problems: list[str] = []
        if outcome.detected != "HostDied":
            problems.append(
                f"killing the host surfaced as {outcome.detected!r} ({outcome.message}), "
                "not as a link loss"
            )
        elif outcome.detect_s is None or outcome.detect_s > cfg.kill_detect_limit_s:
            problems.append(
                f"link loss detected after {outcome.detect_s} s "
                f"(limit {cfg.kill_detect_limit_s:g} s)"
            )
        self.say("fresh plugin host after the kill")
        t_spawn = time.monotonic()
        ev: dict[str, Any] = {"kill": outcome.to_dict()}
        try:
            c2 = self._client()
        except HostDied as exc:
            problems.append(f"a fresh host did not start: {exc}")
            r.set("reconnect.host_killed", "fail", problems[0], ev)
            return
        try:
            if not c2.hello.get("loaded"):
                problems.append("the plugin did not load in a fresh host")
            else:
                t_open = time.monotonic()
                try:
                    opened = c2.request(
                        "open",
                        {"device_key": st.device_key, "options": dict(cfg.options)},
                        timeout_s=cfg.open_timeout_s,
                    )[0]
                except (HostError, HostDied) as exc:
                    problems.append(f"open in a fresh host after the kill failed: {_err(exc)}")
                    opened = None
                if opened is not None:
                    open_s = time.monotonic() - t_open
                    info = ipc.session_info_from_dict(opened.get("info") or {})
                    snap = cs.session_identity(info)
                    st.snapshots["fresh_host_after_kill"] = snap
                    c = new_acquisition(info)
                    acquire(
                        c2,
                        c,
                        v.ChunkValidator(info),
                        cfg.reopen_s,
                        read_timeout_s=cfg.read_timeout_s,
                        grace_s=cfg.read_grace_s,
                    )
                    st.acqs["fresh_host"] = c
                    diffs = cs.identity_diff(st.snapshots["open_1"], snap)
                    first_open = open_s + c.first_data_s if c.first_data_s is not None else None
                    first_spawn = (
                        (t_open - t_spawn) + first_open if first_open is not None else None
                    )
                    ev.update(
                        {
                            "fresh_host_start_s": round(t_open - t_spawn, 3),
                            "open_s": round(open_s, 3),
                            "first_data_after_open_s": _round(first_open),
                            "first_data_after_host_start_s": _round(first_spawn),
                            "samples": c.samples,
                            "failure": c.failure.to_dict() if c.failure else None,
                            "identity_unchanged": not diffs,
                            "identity_differences": diffs[:10],
                        }
                    )
                    if c.failure is not None:
                        problems.append(
                            f"after the fresh open: {c.failure.type}: {c.failure.message}"
                        )
                    elif c.samples == 0:
                        problems.append(f"no data within {cfg.reopen_s:g} s of the fresh open")
                    if diffs:
                        problems.append(f"identity changed after the kill: {diffs[0]}")
                    try:
                        c2.close_session()
                    except (HostError, HostDied) as exc:
                        problems.append(f"close in the fresh host failed: {_err(exc)}")
        finally:
            c2.shutdown()
            st.host_log.extend(list(c2.stderr_tail)[-20:])
        ev["fresh_host_exit_code"] = c2.proc.returncode
        if problems:
            r.set("reconnect.host_killed", "fail", problems[0], {**ev, "problems": problems})
            return
        r.set(
            "reconnect.host_killed",
            "pass",
            f"SIGKILL after {outcome.reads_before_kill} reads surfaced as a link loss in "
            f"{(outcome.detect_s or 0) * 1e3:.1f} ms; fresh host: first data "
            f"{ev['first_data_after_host_start_s']} s after start "
            f"({ev['first_data_after_open_s']} s after open); identity unchanged; exit code "
            f"{c2.proc.returncode}",
            ev,
        )

    # ------------------------------------------------------------------ evaluation
    def evaluate_streams(self) -> None:
        cfg, r, st = self.cfg, self.results, self.st
        if "main" not in st.acqs:
            return
        main = st.acqs["main"]
        mapped = cst.mapped_problems(st.acqs)
        cst.check_read(r, main, cfg.duration_s, mapped)
        cst.check_chunks(r, st.acqs, mapped)
        cst.check_monotonic(r, st.acqs, mapped)
        cst.check_sample_index(r, st.acqs, mapped)
        cst.check_markers(r, st.acqs, mapped)
        if not r.has("integrity.plugin_stats"):
            cst.check_plugin_stats(r, st.stats_reply, st.stats_error)
        if cst.data_checks_not_run(r, main):
            return
        cst.check_rate(r, main, cfg.rate_tolerance)
        cst.check_jitter(r, main)
        cst.check_clock_domain(r, main)
        cst.check_throughput(r, main, cfg.rate_tolerance)
        cst.check_latency(r, main)
        cst.check_resources(r, st.sampler)
        host = (st.stats_reply or {}).get("host")
        cst.check_ipc(r, main, host if isinstance(host, dict) else None, st.ping_ms)

    def _runtime_phase(self) -> None:
        cfg, r, st = self.cfg, self.results, self.st
        if not cfg.runtime:
            for cid in RUNTIME_CHECKS:
                r.set(cid, "not_run", "runtime phase disabled (--no-runtime)", applicable=False)
            return
        main = st.acqs.get("main")
        if (
            st.manifest is None
            or st.info is None
            or st.device_key is None
            or main is None
            or main.failure is not None
        ):
            r.not_run(
                list(RUNTIME_CHECKS), "not run: the plugin did not pass the host-level phases"
            )
            return
        self.say(f"BrainOS runtime phase: {cfg.runtime_s:g} s")
        st.runtime_facts = run_runtime_phase(
            r,
            plugin_ref=cfg.plugin,
            entry_point_name=st.entry_point_name,
            device_key=st.device_key,
            options=st.resolved_options,
            manifest=st.manifest,
            info=st.info,
            python=cfg.python,
            extra_path=cfg.extra_path,
            seconds=cfg.runtime_s,
            start_timeout_s=cfg.start_timeout_s,
            open_timeout_s=cfg.open_timeout_s,
            read_grace_s=cfg.read_grace_s,
        )
        raw = st.runtime_facts.get("session_info")
        if isinstance(raw, dict):
            with contextlib.suppress(ipc.WireError):
                st.snapshots["brainos_runtime"] = cs.session_identity(
                    ipc.session_info_from_dict(raw)
                )


def _round(x: float | None, nd: int = 3) -> float | None:
    return round(x, nd) if x is not None else None


def run(cfg: CertifyConfig, progress: Any = None) -> dict[str, Any]:
    return Runner(cfg, progress).run()
