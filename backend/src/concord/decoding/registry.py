"""Every decoder Concord can run, with its manifest, origin, execution mode and trust state.

Three sources:

* ``concord-trained``: built-in JSON families in the models directory (ridge, LDA, and any
  family registered in decoding/families.py). Run in-process.
* ``imported``: model files with a ``<id>.manifest.json`` (ONNX, skops, TorchScript,
  safetensors, and — only with an explicit trust decision — pickle / joblib). Run in an
  isolated decoder host.
* ``plugin``: installed ``concord.decoders`` entry points, discovered by
  ``python -m concord_decoder_sdk.host --list`` (each probed in its own process; plugin code
  is never imported here). Run in an isolated decoder host.

Every manifest is re-validated here (the host and the files are untrusted). Trust decisions
for unsafe formats are stored in ``<models_dir>/_trust.json`` keyed by model id AND the
artifact's SHA-256, with who decided and when; changing the file voids the decision.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from concord.decoding import model as models
from concord.decoding.families import family_of
from concord.oscompat import child_kwargs, helper_executable, replace

log = logging.getLogger(__name__)

Origin = Literal["concord-trained", "imported", "plugin"]
Status = Literal["ok", "rejected", "load_error"]
TRUST_FILE = "_trust.json"
LIST_TIMEOUT_S = 90.0


def _sdk() -> Any:
    try:
        from concord_decoder_sdk import manifest as mf
    except ImportError:  # pragma: no cover - the server extra installs it
        return None
    return mf


@dataclass
class ModelRecord:
    model_id: str
    origin: Origin
    family: str
    execution: Literal["in_process", "isolated"]
    manifest: dict[str, Any]
    status: Status = "ok"
    reason: str | None = None
    problems: list[dict[str, Any]] = field(default_factory=list)
    path: Path | None = None  # JSON model or manifest file
    plugin: str | None = None  # entry-point name
    dist: dict[str, Any] | None = None
    model: Any = None  # the in-process JSON model
    unsafe_format: bool = False
    artifact_sha256: str | None = None

    def summary(self, trust: dict[str, Any] | None = None) -> dict[str, Any]:
        if self.model is not None:
            base = models.summary(self.model)
        else:
            base = summary_from_manifest(self.manifest)
        return {
            **base,
            "family": self.family,
            "origin": self.origin,
            "execution": self.execution,
            "status": self.status,
            "reason": self.reason,
            "plugin": self.plugin,
            "package": self.dist,
            "modalities": list(self.manifest.get("modalities") or []),
            "participant_specific": bool(
                (self.manifest.get("compatibility") or {}).get("participant_specific", True)
            ),
            "description": self.manifest.get("description"),
            "author": self.manifest.get("author"),
            "license": self.manifest.get("license"),
            "model_version": self.manifest.get("version"),
            "format": (self.manifest.get("artifact") or {}).get("format"),
            "unsafe_format": self.unsafe_format,
            "trust": trust,
            "problems": self.problems,
        }


def summary_from_manifest(m: dict[str, Any]) -> dict[str, Any]:
    out = m.get("output") or {}
    kind = out.get("kind")
    inputs = list(m.get("inputs") or [])
    comp = m.get("compatibility") or {}
    prov = m.get("provenance") or {}
    outputs: dict[str, Any]
    if kind == "classes":
        outputs = {"type": "classes", "classes": list(out.get("dims") or [])}
    elif kind == "event":
        outputs = {"type": "event", "events": list(out.get("dims") or [])}
    else:
        outputs = {"type": "continuous"}
    return {
        "model_id": m.get("model_id"),
        "outputs": outputs,
        "dims": list(out.get("dims") or []),
        "unit": out.get("unit"),
        "quantity": out.get("quantity"),
        "space": out.get("space"),
        "method": m.get("description"),
        "input": inputs[0] if inputs else None,
        "inputs": inputs,
        "source_identity": comp.get("source_identity"),
        "training_session": None,
        "trained_on": prov.get("notes") or None,
        "created_at": prov.get("created_at"),
        "held_out_r2": None,
        "held_out_samples": None,
        "control_mean_predictor_r2": None,
    }


class ModelRegistry:
    def __init__(
        self, models_dir: Path, *, python: str | None = None, extra_path: Sequence[str] = ()
    ) -> None:
        self.models_dir = models_dir
        self.python = python or helper_executable()
        self.extra_path = list(extra_path)
        self._plugins: list[ModelRecord] = []
        self._lock = threading.Lock()
        self._discovery: asyncio.Lock | None = None
        self.discovering = False
        self.last_discovery_ns: int | None = None
        self.discovery_error: str | None = None
        self.plugin_problems: list[dict[str, Any]] = []

    def configure(self, python: str | None, extra_path: Sequence[str]) -> None:
        """Interpreter and extra sys.path for decoder hosts (same as source-plugin hosts)."""
        self.python = python or helper_executable()
        self.extra_path = list(extra_path)

    # ------------------------------------------------------------------ files
    def _json_records(self) -> list[ModelRecord]:
        out: list[ModelRecord] = []
        for model in models.list_models(self.models_dir):
            fam = family_of(model)
            out.append(
                ModelRecord(
                    model_id=model.model_id,
                    origin="concord-trained",
                    family=fam.name,
                    execution="in_process",
                    manifest=models.manifest_for(model),
                    path=self.models_dir / f"{model.model_id}.json",
                    model=model,
                )
            )
        return out

    def _manifest_records(self) -> list[ModelRecord]:
        mf = _sdk()
        out: list[ModelRecord] = []
        if mf is None or not self.models_dir.exists():
            return out
        for path in sorted(self.models_dir.glob("*.manifest.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                manifest = mf.manifest_from_dict(data)
            except (OSError, ValueError) as exc:
                log.warning("ignoring model manifest %s: %s", path.name, exc)
                continue
            problems = mf.validate_manifest(manifest)
            art = manifest.artifact
            if art is None:
                problems.append(mf.Problem("manifest.artifact", "the manifest names no model file"))
            elif art.format == "concord-json":
                problems.append(
                    mf.Problem("artifact.format", "concord-json models are listed directly")
                )
            status: Status = "rejected" if mf.has_errors(problems) else "ok"
            out.append(
                ModelRecord(
                    model_id=manifest.model_id,
                    origin="imported",
                    family=manifest.family,
                    execution="isolated",
                    manifest=mf.manifest_to_dict(manifest),
                    status=status,
                    reason=mf.summarize(problems) if status != "ok" else None,
                    problems=[p.to_dict() for p in problems],
                    path=path,
                    unsafe_format=bool(art and art.format in mf.UNSAFE_FORMATS),
                    artifact_sha256=art.sha256 if art else None,
                )
            )
        return out

    # ------------------------------------------------------------------ plugins
    async def discover_plugins(self) -> list[ModelRecord]:
        """Probe installed decoder plugins (each in its own host process)."""
        if self._discovery is None:
            self._discovery = asyncio.Lock()
        async with self._discovery:
            self.discovering = True
            try:
                doc = await self._run_list()
            except Exception as exc:
                self.discovery_error = str(exc)[:500]
                log.error("decoder plugin discovery failed: %s", exc)
                raise
            finally:
                self.discovering = False
            records = self._parse_list(doc)
            with self._lock:
                self._plugins = records
            self.last_discovery_ns = time.time_ns()
            self.discovery_error = None
            log.info("decoder plugins: %d found", len(records))
            return records

    async def _run_list(self) -> dict[str, Any]:
        from concord.adapters.plugin.host_client import host_env

        proc = await asyncio.create_subprocess_exec(
            self.python,
            "-m",
            "concord_decoder_sdk.host",
            "--list",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=host_env(self.extra_path),
            **child_kwargs(),
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), LIST_TIMEOUT_S)
        except TimeoutError:
            proc.kill()
            await proc.wait()
            raise RuntimeError(
                f"decoder discovery did not finish within {LIST_TIMEOUT_S:g} s"
            ) from None
        if proc.returncode != 0:
            tail = err.decode("utf-8", "replace").strip().splitlines()[-3:]
            raise RuntimeError(f"decoder discovery failed ({proc.returncode}): {' | '.join(tail)}")
        doc = json.loads(out.decode("utf-8"))
        if not isinstance(doc, dict) or not isinstance(doc.get("decoders"), list):
            raise RuntimeError("decoder discovery returned an unexpected document")
        return doc

    def _parse_list(self, doc: dict[str, Any]) -> list[ModelRecord]:
        mf = _sdk()
        records: list[ModelRecord] = []
        assert mf is not None
        for d in doc.get("decoders", []):
            if not isinstance(d, dict):
                continue
            name = str(d.get("name", ""))
            raw = d.get("manifest")
            status: Status = "ok"
            reason = None
            problems: list[dict[str, Any]] = [
                p for p in d.get("problems") or [] if isinstance(p, dict)
            ]
            manifest: dict[str, Any] = {}
            model_id = f"plugin:{name}"
            family = "plugin"
            if d.get("status") == "load_error" or not isinstance(raw, dict):
                status = "load_error" if d.get("status") == "load_error" else "rejected"
                err = d.get("error") or {}
                reason = (
                    str(err.get("message") or "failed to load")
                    if err
                    else mf.summarize([mf.Problem.from_dict(p) for p in problems])
                )
            else:
                try:
                    parsed = mf.manifest_from_dict(raw)
                except mf.ManifestError as exc:
                    status, reason = "rejected", f"malformed manifest: {exc}"
                else:
                    again = mf.validate_manifest(parsed)  # re-validate: the host is untrusted
                    problems = [p.to_dict() for p in again]
                    manifest = mf.manifest_to_dict(parsed)
                    model_id, family = parsed.model_id, parsed.family
                    if parsed.artifact is not None:
                        again.append(mf.Problem("plugin.artifact", "plugins carry no artifact"))
                    if mf.has_errors(again) or d.get("status") != "compatible":
                        status, reason = "rejected", mf.summarize(again) or "rejected"
            records.append(
                ModelRecord(
                    model_id=model_id,
                    origin="plugin",
                    family=family,
                    execution="isolated",
                    manifest=manifest,
                    status=status,
                    reason=reason,
                    problems=problems,
                    plugin=name,
                    dist=d.get("dist") if isinstance(d.get("dist"), dict) else None,
                )
            )
        return records

    # ------------------------------------------------------------------ listing
    def records(self) -> list[ModelRecord]:
        files = self._json_records() + self._manifest_records()
        with self._lock:
            plugins = list(self._plugins)
        seen: dict[str, ModelRecord] = {}
        out: list[ModelRecord] = []
        for r in files + plugins:
            first = seen.get(r.model_id)
            if first is not None:
                r.status = "rejected"
                r.reason = (
                    f"model id {r.model_id!r} is already used by "
                    f"{first.path.name if first.path else first.plugin}"
                )
            else:
                seen[r.model_id] = r
            out.append(r)
        return out

    def get(self, model_id: str) -> ModelRecord | None:
        for r in self.records():
            if r.model_id == model_id and r.status == "ok":
                return r
        for r in self.records():
            if r.model_id == model_id:
                return r
        return None

    # ------------------------------------------------------------------ trust
    def _trust_path(self) -> Path:
        return self.models_dir / TRUST_FILE

    def _read_trust(self) -> dict[str, dict[str, Any]]:
        p = self._trust_path()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            log.error("trust file %s unreadable (%s): treating every model as untrusted", p, exc)
            return {}
        return (
            {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}
        )

    def trust_of(self, record: ModelRecord) -> dict[str, Any] | None:
        """The operator's trust decision for this exact file, if any."""
        if record.artifact_sha256 is None:
            return None
        t = self._read_trust().get(record.model_id)
        if t and t.get("sha256") == record.artifact_sha256:
            return t
        return None

    def trusted_sha256(self, record: ModelRecord) -> str | None:
        t = self.trust_of(record)
        return str(t["sha256"]) if t else None

    def set_trust(
        self, model_id: str, trusted: bool, *, by: str = "operator"
    ) -> dict[str, Any] | None:
        rec = self.get(model_id)
        if rec is None or rec.origin != "imported" or rec.artifact_sha256 is None:
            raise KeyError(f"no model file {model_id!r} to trust")
        data = self._read_trust()
        if trusted:
            fmt = (rec.manifest.get("artifact") or {}).get("format")
            data[model_id] = {
                "sha256": rec.artifact_sha256,
                "format": fmt,
                "file": (rec.manifest.get("artifact") or {}).get("file"),
                "by": by,
                "at_ns": time.time_ns(),
                "note": "operator marked this exact file trusted: it may run code when loaded",
            }
            log.warning(
                "model %s (%s, sha256 %s) marked trusted by %s",
                model_id,
                fmt,
                rec.artifact_sha256[:12],
                by,
            )
        else:
            data.pop(model_id, None)
            log.info("trust in model %s revoked by %s", model_id, by)
        self.models_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._trust_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1), encoding="utf-8")
        replace(tmp, self._trust_path())
        return data.get(model_id)
