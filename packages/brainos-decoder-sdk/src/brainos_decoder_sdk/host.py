"""The decoder host: runs ONE decoder (a plugin or a model file) in its own process.

Usage::

    python -m brainos_decoder_sdk.host <entry-point name | module:Class>      # serve (IPC)
    python -m brainos_decoder_sdk.host --model PATH.manifest.json [--trusted-sha256 HEX]
    python -m brainos_decoder_sdk.host --list                                  # JSON on stdout
    python -m brainos_decoder_sdk.host --check <ref> | --check --model PATH

Serve mode speaks ``brainos.decoder-ipc/1`` (:mod:`brainos_decoder_sdk.ipc`) on the
process's original stdin/stdout, moved to private descriptors before any decoder code is
imported (fd 1 -> stderr, fd 0 -> /dev/null), so ``print()`` in a decoder or a native library
writing to stdout cannot corrupt the channel.

The manifest is validated before the decoder can be used; every output is validated before
it is sent (:class:`~brainos_decoder_sdk.manifest.OutputValidator`). An invalid output or an
unexpected exception in decoder code STOPS the decoder: every later request is refused with
the reason. Isolation is fault isolation (a crash, hang or memory blow-up of the decoder does
not take BrainOS down), not a security sandbox: the process has the same user, files and
network as BrainOS.
"""

from __future__ import annotations

import argparse
import importlib
import json
import logging
import os
import sys
import time
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from importlib import metadata
from pathlib import Path
from typing import IO, Any, TypeVar

import numpy as np
from brainos_adapter_sdk.host import _claim_stdio, traceback_summary

from brainos_decoder_sdk import __version__, ipc
from brainos_decoder_sdk import manifest as mf
from brainos_decoder_sdk.api import (
    API_VERSION,
    ENTRY_POINT_GROUP,
    Confidence,
    Decoder,
    DecoderError,
    InputMismatch,
    ModelLoadError,
    ModelManifest,
    UntrustedModelError,
)

log = logging.getLogger("brainos.decoder_host")
T = TypeVar("T")


class _Reply(Exception):
    def __init__(
        self, type_: str, message: str, *, tb: str | None = None, problems: Sequence[Any] = ()
    ) -> None:
        self.type, self.message, self.tb, self.problems = type_, message, tb, list(problems)
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "message": self.message,
            "traceback": self.tb,
            "problems": [p.to_dict() for p in self.problems],
        }


def _call(what: str, fn: Callable[[], T]) -> T:
    """Run decoder code; map its exceptions to typed IPC errors."""
    try:
        return fn()
    except UntrustedModelError as exc:
        raise _Reply(ipc.UNTRUSTED_MODEL, str(exc) or "untrusted model") from exc
    except ModelLoadError as exc:
        raise _Reply(ipc.MODEL_LOAD_ERROR, str(exc) or "model load failed") from exc
    except InputMismatch as exc:
        raise _Reply(ipc.INPUT_MISMATCH, str(exc)) from exc
    except DecoderError as exc:
        raise _Reply(ipc.DECODER_ERROR, str(exc) or type(exc).__name__) from exc
    except (Exception, SystemExit) as exc:
        log.exception("decoder %s raised", what)
        raise _Reply(
            ipc.INTERNAL_ERROR,
            f"{what} raised {type(exc).__name__}: {exc}"[:500],
            tb=traceback_summary(exc),
        ) from exc


# ----------------------------------------------------------------------------- loading


class Loaded:
    def __init__(
        self,
        decoder: Decoder | None,
        manifest: ModelManifest | None,
        problems: list[mf.Problem],
        entry: dict[str, Any],
        error: _Reply | None = None,
    ) -> None:
        self.decoder, self.manifest, self.problems, self.entry = decoder, manifest, problems, entry
        self.error = error

    @property
    def compatible(self) -> bool:
        return self.manifest is not None and self.error is None and not mf.has_errors(self.problems)


def load_plugin(ref: str) -> Loaded:
    """Import and instantiate a decoder plugin by entry-point name or ``module:Class``."""
    entry: dict[str, Any] = {"ref": ref, "name": None, "value": None, "dist": None}
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
            raise LookupError(f"entry point {ref!r} is provided by several distributions")
        ep = eps[0]
        entry.update(name=ep.name, value=ep.value)
        if ep.dist is not None:
            entry["dist"] = {"name": ep.dist.name, "version": ep.dist.version}
        obj = ep.load()
    if not (isinstance(obj, type) and issubclass(obj, Decoder)):
        raise TypeError(f"{ref!r} is not a Decoder subclass (got {obj!r})"[:300])
    manifest = getattr(obj, "manifest", None)
    problems = mf.validate_manifest(manifest)
    if isinstance(manifest, ModelManifest) and manifest.artifact is not None:
        problems.append(
            mf.Problem(
                "plugin.artifact",
                "a plugin ships its parameters itself; 'artifact' is for model files only",
                "error",
                "artifact",
            )
        )
    decoder = obj() if not mf.has_errors(problems) else None
    return Loaded(
        decoder, manifest if isinstance(manifest, ModelManifest) else None, problems, entry
    )


def load_model_file(path: Path, trusted_sha256: str | None) -> Loaded:
    """A manifest + artifact from a models directory, loaded by its format's loader."""
    from brainos_decoder_sdk.formats import load_file_model

    entry: dict[str, Any] = {"ref": str(path), "name": None, "value": None, "dist": None}
    try:
        manifest = mf.read_manifest(path)
    except mf.ManifestError as exc:
        return Loaded(None, None, [mf.Problem("manifest.parse", str(exc))], entry)
    problems = mf.validate_manifest(manifest)
    if manifest.artifact is None:
        problems.append(mf.Problem("manifest.artifact", "a model file manifest needs 'artifact'"))
    if mf.has_errors(problems):
        return Loaded(None, manifest, problems, entry)
    try:
        decoder = _call(
            "loading the model file", lambda: load_file_model(manifest, path.parent, trusted_sha256)
        )
    except _Reply as r:
        return Loaded(None, manifest, problems, entry, error=r)
    return Loaded(decoder, manifest, problems, entry)


# ----------------------------------------------------------------------------- serving


class Host:
    def __init__(self, out: IO[bytes]) -> None:
        self.out = out
        self.loaded: Loaded | None = None
        self.load_error: _Reply | None = None
        self.ready = False  # load() succeeded
        self.validator: mf.OutputValidator | None = None
        self.stopped_reason: str | None = None
        self.counters: Counter[str] = Counter()

    def send(self, header: Mapping[str, Any], buffers: Sequence[Any] = ()) -> None:
        ipc.write_message(self.out, header, buffers)

    def hello(self, ref: str) -> dict[str, Any]:
        lp = self.loaded
        return {
            "type": "hello",
            "protocol": ipc.PROTOCOL,
            "api_version": API_VERSION,
            "sdk_version": __version__,
            "python": sys.version.split()[0],
            "pid": os.getpid(),
            "ref": ref,
            "loaded": lp is not None and lp.decoder is not None,
            "load_error": self.load_error.to_dict() if self.load_error else None,
        }

    def _manifest(self) -> dict[str, Any]:
        lp = self.loaded
        return {
            "manifest": mf.manifest_to_dict(lp.manifest) if lp and lp.manifest else None,
            "problems": [p.to_dict() for p in lp.problems] if lp else [],
            "compatible": bool(lp and lp.compatible),
            "entry": lp.entry if lp else None,
            "error": lp.error.to_dict() if lp and lp.error else None,
        }

    def cmd_ping(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return {"nonce": args.get("nonce"), "monotonic": time.monotonic()}

    def cmd_manifest(self, args: Mapping[str, Any]) -> dict[str, Any]:
        return self._manifest()

    def _decoder(self) -> Decoder:
        if self.stopped_reason is not None:
            raise _Reply(ipc.STOPPED, f"decoder stopped: {self.stopped_reason}")
        lp = self.loaded
        if lp is None or lp.decoder is None or lp.manifest is None:
            if self.load_error is not None:
                raise self.load_error
            if lp is not None and lp.error is not None:
                raise lp.error
            raise _Reply(
                ipc.INCOMPATIBLE,
                f"decoder rejected: {mf.summarize(lp.problems) if lp else 'not loaded'}",
                problems=mf.errors(lp.problems) if lp else [],
            )
        if not lp.compatible:
            raise _Reply(
                ipc.INCOMPATIBLE,
                f"decoder rejected: {mf.summarize(lp.problems)}",
                problems=mf.errors(lp.problems),
            )
        return lp.decoder

    def cmd_load(self, args: Mapping[str, Any]) -> dict[str, Any]:
        dec = self._decoder()
        _call("load()", dec.load)
        _call("reset()", dec.reset)
        assert self.loaded is not None and self.loaded.manifest is not None
        self.validator = mf.OutputValidator(self.loaded.manifest)
        self.ready = True
        return self._manifest()

    def _ready(self) -> Decoder:
        dec = self._decoder()
        if not self.ready:
            raise _Reply(ipc.NOT_LOADED, "call load first")
        return dec

    def cmd_reset(self, args: Mapping[str, Any]) -> dict[str, Any]:
        dec = self._ready()
        self._guarded("reset()", dec.reset)
        return {}

    def _guarded(self, what: str, fn: Callable[[], T]) -> T:
        try:
            return _call(what, fn)
        except _Reply as r:
            if r.type == ipc.INTERNAL_ERROR:
                self.stopped_reason = r.message
            raise

    def cmd_step(
        self, args: Mapping[str, Any], arrays: Sequence[Any]
    ) -> tuple[dict[str, Any], list[Any]]:
        dec = self._ready()
        assert self.loaded is not None and self.loaded.manifest is not None
        assert self.validator is not None
        m = self.loaded.manifest
        if len(arrays) != 1:
            raise _Reply(ipc.BAD_REQUEST, "step needs exactly one features buffer")
        x = arrays[0]
        if x.ndim != 2 or x.shape[1] != m.input_width or x.dtype != np.float64:
            raise _Reply(
                ipc.INPUT_MISMATCH,
                f"features must be float64 (n, {m.input_width}); got {x.dtype} {x.shape}",
            )
        n = x.shape[0]
        if not 0 < n <= ipc.MAX_STEP_BINS:
            raise _Reply(ipc.BAD_REQUEST, f"1-{ipc.MAX_STEP_BINS} bins per step")
        ts = args.get("timestamps_s")
        if not isinstance(ts, list) or len(ts) != n:
            ts = [0.0] * n
        dims = len(m.output.dims)
        values = np.empty((n, dims), dtype=np.float64)
        conf_w = {Confidence.VARIANCE: dims, Confidence.COVARIANCE: dims * dims}.get(m.confidence)
        conf = np.empty((n, conf_w), dtype=np.float64) if conf_w else None
        for i in range(n):
            row = np.array(x[i], dtype=np.float64)
            t = float(ts[i]) if isinstance(ts[i], int | float) else 0.0
            out = self._guarded("step()", lambda r=row, tt=t: dec.step(r, tt))  # type: ignore[misc]
            vals = getattr(out, "values", None)
            c = getattr(out, "confidence", None)
            problems = self.validator.check(vals, c)
            if mf.has_errors(problems):
                self.stopped_reason = f"invalid output: {mf.summarize(problems)}"
                self.counters["invalid_outputs"] += 1
                raise _Reply(
                    ipc.INVALID_OUTPUT,
                    f"decoder produced an invalid output; stopped ({mf.summarize(problems)})",
                    problems=problems,
                )
            values[i] = np.asarray(vals, dtype=np.float64)
            if conf is not None:
                conf[i] = np.asarray(c, dtype=np.float64).reshape(-1)
        self.counters["steps"] += n
        return {"n": n}, [values] if conf is None else [values, conf]

    def cmd_close(self, args: Mapping[str, Any]) -> dict[str, Any]:
        self._close()
        return {}

    def _close(self) -> None:
        lp = self.loaded
        if lp is not None and lp.decoder is not None:
            try:
                lp.decoder.close()
            except (Exception, SystemExit):
                log.exception("decoder close() raised (ignored)")
        self.ready = False

    def handle(self, header: Mapping[str, Any], arrays: Sequence[Any]) -> bool:
        rid = header.get("id")
        cmd = header.get("cmd")
        args = header.get("args") if isinstance(header.get("args"), dict) else {}
        assert isinstance(args, dict)
        if cmd == "shutdown":
            self._close()
            self.send({"id": rid, "ok": True, "result": {}})
            return False
        try:
            if cmd == "step":
                result, bufs = self.cmd_step(args, arrays)
                self.send({"id": rid, "ok": True, "result": result}, bufs)
                return True
            handler = getattr(self, f"cmd_{cmd}", None) if isinstance(cmd, str) else None
            if handler is None:
                raise _Reply(ipc.BAD_REQUEST, f"unknown command {cmd!r}")
            self.send({"id": rid, "ok": True, "result": handler(args)})
        except _Reply as r:
            self.send({"id": rid, "ok": False, "error": r.to_dict()})
        return True


def serve(ref: str | None, model: Path | None, trusted_sha256: str | None) -> int:
    ipc_in, ipc_out = _claim_stdio()
    label = ref or (model.name if model else "?")
    logging.basicConfig(
        stream=sys.stderr,
        level=os.environ.get("BRAINOS_DECODER_LOG_LEVEL", "INFO").upper(),
        format=f"[decoder {label} pid {os.getpid()}] %(levelname)s %(name)s: %(message)s",
    )
    host = Host(ipc_out)
    try:
        if model is not None:
            host.loaded = load_model_file(model, trusted_sha256)
        else:
            assert ref is not None
            host.loaded = load_plugin(ref)
    except (Exception, SystemExit) as exc:
        log.exception("loading decoder %s failed", label)
        host.load_error = _Reply(
            ipc.LOAD_FAILED,
            f"loading decoder {label!r} failed: {type(exc).__name__}: {exc}"[:500],
            tb=traceback_summary(exc),
        )
    host.send(host.hello(label))
    try:
        while True:
            msg = ipc.read_message(ipc_in)
            if msg is None:
                break
            if not host.handle(msg[0], msg[1]):
                break
    except ipc.WireError as exc:
        log.error("protocol error from the runtime: %s", exc)
        return 3
    except BrokenPipeError:
        return 0
    finally:
        host._close()
    return 0


# ----------------------------------------------------------------------------- --list


def _probe(name: str, timeout_s: float, python: str | None) -> dict[str, Any]:
    from brainos_decoder_sdk.client import DecoderHostDied, DecoderHostError, SyncDecoderHost

    rec: dict[str, Any] = {}
    client: SyncDecoderHost | None = None
    try:
        client = SyncDecoderHost(ref=name, python=python, hello_timeout_s=timeout_s)
        if client.hello.get("load_error"):
            rec["status"] = "load_error"
            rec["error"] = client.hello["load_error"]
            return rec
        m = client.manifest(timeout_s)
        rec.update(manifest=m.get("manifest"), problems=m.get("problems", []))
        rec["status"] = "compatible" if m.get("compatible") else "rejected"
    except DecoderHostDied as exc:
        rec["status"] = "load_error"
        rec["error"] = {"type": "HostDied", "message": str(exc), "traceback": None}
    except DecoderHostError as exc:
        rec["status"] = "load_error"
        rec["error"] = {"type": exc.type, "message": exc.message, "traceback": exc.traceback}
    finally:
        if client is not None:
            client.shutdown()
            rec["stderr_tail"] = list(client.stderr_tail)[-20:]
    return rec


def list_decoders(timeout_s: float = 30.0, python: str | None = None) -> dict[str, Any]:
    """Every installed ``brainos.decoders`` entry point, each probed in its own process."""
    eps = sorted(metadata.entry_points(group=ENTRY_POINT_GROUP), key=lambda e: (e.name, e.value))
    counts = Counter(ep.name for ep in eps)
    records: list[dict[str, Any]] = []
    todo: list[tuple[dict[str, Any], str]] = []
    for ep in eps:
        rec: dict[str, Any] = {
            "name": ep.name,
            "entry": ep.value,
            "dist": {"name": ep.dist.name, "version": ep.dist.version} if ep.dist else None,
            "status": "rejected",
            "manifest": None,
            "problems": [],
            "error": None,
            "stderr_tail": [],
        }
        records.append(rec)
        if counts[ep.name] > 1:
            rec["problems"] = [
                mf.Problem(
                    "entry_point.duplicate",
                    f"entry point {ep.name!r} is installed by more than one distribution",
                ).to_dict()
            ]
            continue
        todo.append((rec, ep.name))
    if todo:
        with ThreadPoolExecutor(max_workers=min(8, len(todo))) as pool:
            futures = [(r, pool.submit(_probe, n, timeout_s, python)) for r, n in todo]
            for r, fut in futures:
                r.update(fut.result())
    return {
        "protocol": ipc.PROTOCOL,
        "api_version": API_VERSION,
        "sdk_version": __version__,
        "python": sys.executable,
        "decoders": records,
    }


# ----------------------------------------------------------------------------- --check


def check(ref: str | None, model: Path | None, steps: int, trusted_sha256: str | None) -> int:
    """Load a decoder in a real host, decode synthetic features, validate every output."""
    from brainos_decoder_sdk.client import DecoderHostDied, DecoderHostError, SyncDecoderHost

    def say(msg: str) -> None:
        print(msg, flush=True)

    try:
        c = SyncDecoderHost(ref=ref, model_path=model, trusted_sha256=trusted_sha256)
    except DecoderHostDied as exc:
        say(f"HOST FAILED: {exc}")
        return 1
    with c:
        if c.hello.get("load_error"):
            err = c.hello["load_error"]
            say(f"LOAD FAILED: {err.get('message')}\n{err.get('traceback') or ''}")
            return 1
        m = c.manifest()
        man = m.get("manifest") or {}
        say(
            f"decoder  {man.get('model_id')} ({man.get('family')}) {man.get('version')} "
            f"API {man.get('api_version')}"
        )
        for p in m.get("problems", []):
            say(f"  {p['severity']:7s} {p['code']}: {p['where']} {p['message']}")
        if m.get("error"):
            say(f"LOAD FAILED [{m['error']['type']}]: {m['error']['message']}")
            return 1
        if not m.get("compatible"):
            say("REJECTED: BrainOS would list this decoder but refuse to run it.")
            return 1
        man_obj = mf.manifest_from_dict(man)
        for i, s in enumerate(man_obj.inputs):
            labels = "positional" if s.channel_labels is None else f"{len(s.channel_labels)} labels"
            say(
                f"  input {i}  {s.event_type}/{s.feature} {s.bin_ms:g} ms {s.channel_count} ch "
                f"({labels}) unit={s.unit}"
            )
        o = man_obj.output
        say(f"  output   {o.kind} {o.quantity} dims={list(o.dims)} unit={o.unit}")
        mods = sorted(str(x) for x in man_obj.modalities)
        say(f"  modality {mods} confidence={man_obj.confidence}")
        try:
            c.load()
            rng = np.random.default_rng(0)
            width = man_obj.input_width
            feats = np.abs(rng.standard_normal((steps, width))) * 2.0
            t0 = time.perf_counter()
            for i in range(steps):
                c.step(feats[i : i + 1], [i * man_obj.inputs[0].bin_ms / 1e3])
            dt = time.perf_counter() - t0
            c.reset()
            values, _ = c.step(feats[:8], None)
        except (DecoderHostError, DecoderHostDied) as exc:
            say(f"DECODE FAILED: {exc}")
            return 1
        say(
            f"  decoded  {steps} bins one at a time: {dt / max(1, steps) * 1e6:.0f} us per bin "
            f"incl. IPC; batch of 8 -> {values.shape}"
        )
    say("OK: manifest, load and every output passed validation")
    return 0


# ----------------------------------------------------------------------------- main


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m brainos_decoder_sdk.host",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("decoder", nargs="?", help="entry-point name or module:Class")
    ap.add_argument("--model", type=Path, help="a model manifest (<id>.manifest.json)")
    ap.add_argument("--trusted-sha256", help="SHA-256 the operator marked trusted")
    ap.add_argument("--list", action="store_true", help="list installed decoder plugins (JSON)")
    ap.add_argument("--timeout", type=float, default=30.0, help="with --list: per-plugin timeout")
    ap.add_argument("--check", action="store_true", help="run the decoder and print a report")
    ap.add_argument("--steps", type=int, default=200, help="with --check: bins to decode")
    a = ap.parse_args(argv)
    if a.list:
        sys.stdout.write(json.dumps(list_decoders(a.timeout)) + "\n")
        return 0
    if (a.decoder is None) == (a.model is None):
        ap.error("give exactly one of: a decoder (entry point / module:Class) or --model PATH")
    if a.check:
        return check(a.decoder, a.model, max(1, a.steps), a.trusted_sha256)
    return serve(a.decoder, a.model, a.trusted_sha256)


if __name__ == "__main__":
    raise SystemExit(main())
