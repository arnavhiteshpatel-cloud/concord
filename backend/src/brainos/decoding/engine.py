"""The one decoder interface the pipeline uses: built-in (in-process) or isolated (host).

:class:`PipelineDecoder` hides where a decoder runs. Built-in JSON families step their
``streaming()`` object in the BrainOS process (bit-identical to the model's offline
prediction). Model files and plugins run in a decoder host (``brainos_decoder_sdk.host``)
through the same asyncio client the source plugins use; every output is validated again
here, because the host runs third-party code.

A failure (host exit, hang, protocol error, invalid output, exception in decoder code) marks
the decoder ``failed`` with the reason; it never produces another output.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from brainos.decoding.registry import ModelRecord

log = logging.getLogger(__name__)

FloatArray = NDArray[np.float64]
State = Literal["starting", "ready", "failed", "closed"]
START_TIMEOUT_S = 30.0
LOAD_TIMEOUT_S = 60.0
STEP_TIMEOUT_S = 5.0


class DecoderFailed(Exception):
    """The decoder can no longer produce outputs (reason in the message)."""


class PipelineDecoder(ABC):
    def __init__(self, record: ModelRecord) -> None:
        self.record = record
        m = record.manifest
        out = m.get("output") or {}
        self.model_id = record.model_id
        self.family = record.family
        self.origin = record.origin
        self.dims: list[str] = [str(d) for d in out.get("dims") or []]
        self.quantity = str(out.get("quantity", ""))
        self.unit = str(out.get("unit", ""))
        self.space = str(out.get("space", ""))
        self.output_kind = str(out.get("kind", "continuous"))
        self.y_axis: str | None = out.get("y_axis")
        self.confidence = str(m.get("confidence", "none"))
        self.inputs: list[dict[str, Any]] = list(m.get("inputs") or [])
        self.width = sum(int(i.get("channel_count", 0)) for i in self.inputs)
        self.state: State = "starting"
        self.error: str | None = None
        self.steps = 0

    @property
    def isolated(self) -> bool:
        return self.record.execution == "isolated"

    @property
    def classes(self) -> list[str] | None:
        """Names discrete router rules may use (classes or events); None if continuous."""
        return list(self.dims) if self.output_kind in ("classes", "event") else None

    @property
    def behavior_std(self) -> list[float] | None:
        """Per-dim scale for the router's pointer z-scoring: the training targets' std, or
        the manifest's declared output scale."""
        model = self.record.model
        if model is not None:
            std = model.training.get("behavior_std")
            if isinstance(std, list):
                return [float(v) for v in std]
        scale = (self.record.manifest.get("output") or {}).get("scale")
        return [float(v) for v in scale] if isinstance(scale, list) else None

    def fail(self, reason: str) -> None:
        if self.state != "failed":
            log.error("decoder %s failed: %s", self.model_id, reason)
        self.state, self.error = "failed", reason[:500]

    @abstractmethod
    async def start(self) -> None: ...

    @abstractmethod
    async def step(self, x: FloatArray, ts_s: list[float]) -> tuple[FloatArray, FloatArray | None]:
        """Decode n bins: x (n, width) -> values (n, dims), confidence (n, k) or None."""

    @abstractmethod
    async def reset(self) -> None: ...

    @abstractmethod
    async def close(self) -> None: ...

    def info(self) -> dict[str, Any]:
        return {
            "model_id": self.model_id,
            "family": self.family,
            "origin": self.origin,
            "execution": self.record.execution,
            "state": self.state,
            "error": self.error,
            "steps": self.steps,
            "output_kind": self.output_kind,
            "confidence": self.confidence,
            "y_axis": self.y_axis,
        }


class InProcessDecoder(PipelineDecoder):
    """A built-in JSON family, stepped in this process."""

    def __init__(self, record: ModelRecord) -> None:
        super().__init__(record)
        assert record.model is not None
        self.model = record.model
        self._stream = self.model.streaming()
        self.state = "ready"

    async def start(self) -> None:
        return None

    def step_sync(self, x: FloatArray) -> tuple[FloatArray, FloatArray | None]:
        if self.state != "ready":
            raise DecoderFailed(self.error or f"decoder {self.state}")
        n = x.shape[0]
        values = np.empty((n, len(self.dims)), dtype=np.float64)
        conf: FloatArray | None = None
        for i in range(n):
            values[i] = self._stream.step(x[i])
            c = self._confidence()
            if c is not None:
                if conf is None:
                    conf = np.empty((n, c.size), dtype=np.float64)
                conf[i] = c.reshape(-1)
        self.steps += n
        return values, conf

    def _confidence(self) -> FloatArray | None:
        if self.confidence == "covariance" and hasattr(self._stream, "covariance"):
            return np.asarray(self._stream.covariance(), dtype=np.float64)
        if self.confidence == "variance" and hasattr(self._stream, "variance"):
            return np.asarray(self._stream.variance(), dtype=np.float64)
        return None

    async def step(self, x: FloatArray, ts_s: list[float]) -> tuple[FloatArray, FloatArray | None]:
        return self.step_sync(x)

    async def reset(self) -> None:
        self._stream.reset()

    async def close(self) -> None:
        self.state = "closed"


class IsolatedDecoder(PipelineDecoder):
    """A model file or plugin, run in its own decoder-host process."""

    def __init__(
        self,
        record: ModelRecord,
        *,
        trusted_sha256: str | None = None,
        python: str | None = None,
        extra_path: list[str] | None = None,
    ) -> None:
        super().__init__(record)
        from brainos_decoder_sdk import ipc
        from brainos_decoder_sdk import manifest as mf

        from brainos.adapters.plugin.host_client import AsyncHostClient

        self._ipc, self._mf = ipc, mf
        if record.origin == "plugin":
            assert record.plugin is not None
            args = [record.plugin]
        else:
            assert record.path is not None
            args = ["--model", str(record.path)]
            if trusted_sha256:
                args += ["--trusted-sha256", trusted_sha256]
        self.client = AsyncHostClient(
            record.plugin or record.model_id,
            python=python,
            extra_path=extra_path or [],
            label=f"decoder {record.model_id}",
            module="brainos_decoder_sdk.host",
            protocol=ipc.PROTOCOL,
            args=args,
        )
        self.validator = mf.OutputValidator(mf.manifest_from_dict(record.manifest))
        self.pid: int | None = None

    async def start(self) -> None:
        from brainos.adapters.plugin.host_client import HostFailure, RemoteError

        try:
            hello = await self.client.start(START_TIMEOUT_S)
            self.pid = self.client.pid
            if hello.get("load_error"):
                raise DecoderFailed(str(hello["load_error"].get("message")))
            got, _ = await self.client.request("manifest", timeout_s=START_TIMEOUT_S)
            if got.get("error"):
                raise DecoderFailed(str(got["error"].get("message")))
            if got.get("manifest") != self.record.manifest:
                raise DecoderFailed(
                    "the decoder's manifest changed since it was listed; search for decoders "
                    "again before starting it"
                )
            await self.client.request("load", timeout_s=LOAD_TIMEOUT_S)
        except DecoderFailed as exc:
            self.fail(str(exc))
            await self.client.close()
            raise
        except RemoteError as exc:
            self.fail(f"{exc.type}: {exc.message}")
            await self.client.close()
            raise DecoderFailed(self.error or exc.message) from None
        except HostFailure as exc:
            self.fail(str(exc))
            raise DecoderFailed(str(exc)) from None
        self.state = "ready"
        log.info("decoder %s ready in host pid %s", self.model_id, self.pid)

    async def step(self, x: FloatArray, ts_s: list[float]) -> tuple[FloatArray, FloatArray | None]:
        from brainos.adapters.plugin.host_client import HostFailure, RemoteError

        if self.state != "ready":
            raise DecoderFailed(self.error or f"decoder {self.state}")
        arr = np.ascontiguousarray(x, dtype=np.float64)
        try:
            _, bufs = await self.client.request(
                "step", {"timestamps_s": ts_s}, timeout_s=STEP_TIMEOUT_S, buffers=[arr]
            )
        except RemoteError as exc:
            self.fail(f"{exc.type}: {exc.message}")
            await self.client.close()
            raise DecoderFailed(self.error or exc.message) from None
        except HostFailure as exc:
            self.fail(str(exc))
            raise DecoderFailed(str(exc)) from None
        n, dims = arr.shape[0], len(self.dims)
        values = bufs[0] if bufs else None
        if values is None or values.dtype != np.float64 or values.shape != (n, dims):
            self.fail("decoder host returned values of the wrong shape")
            await self.client.close()
            raise DecoderFailed(self.error or "bad output")
        conf = bufs[1] if len(bufs) > 1 else None
        k = {"variance": dims, "covariance": dims * dims}.get(self.confidence)
        for i in range(n):
            c = None
            if k is not None:
                if conf is None or conf.shape != (n, k):
                    c = np.zeros(0)  # rejected below as a shape error
                else:
                    c = conf[i] if self.confidence == "variance" else conf[i].reshape(dims, dims)
            problems = self.validator.check(values[i], c)
            if self._mf.has_errors(problems):
                self.fail(f"invalid output from the decoder host: {self._mf.summarize(problems)}")
                await self.client.close()
                raise DecoderFailed(self.error or "invalid output")
        self.steps += n
        return np.array(values, dtype=np.float64), None if conf is None else np.array(conf)

    async def reset(self) -> None:
        from brainos.adapters.plugin.host_client import HostFailure, RemoteError

        if self.state != "ready":
            return
        try:
            await self.client.request("reset", timeout_s=STEP_TIMEOUT_S)
        except (RemoteError, HostFailure) as exc:
            self.fail(str(exc))
            raise DecoderFailed(str(exc)) from None

    async def close(self) -> None:
        if self.state != "failed":
            self.state = "closed"
        await self.client.close()

    def info(self) -> dict[str, Any]:
        return {**super().info(), "pid": self.pid, "isolated": True}


def make_decoder(
    record: ModelRecord,
    *,
    trusted_sha256: str | None = None,
    python: str | None = None,
    extra_path: list[str] | None = None,
) -> PipelineDecoder:
    if record.execution == "in_process":
        return InProcessDecoder(record)
    return IsolatedDecoder(
        record, trusted_sha256=trusted_sha256, python=python, extra_path=extra_path
    )
