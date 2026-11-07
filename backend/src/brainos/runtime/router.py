"""The command router: the only path from decoder output to application commands.

Standardized action set (all ``decoded_intent`` + ``model_id``, produced only here):

* continuous 2-D movement -> ``intent.pointer`` (two decoded dimensions of a continuous
  decoder, z-scored by the training behavior std, gain / dead-zone / clamp);
* discrete ``select`` (``intent.selection`` action ``primary``), ``activate``, ``cancel`` and
  ``text`` (``intent.text``) -> from a classifier's class posteriors by explicit rules with
  threshold, hold time, refractory period and hysteresis.

The router accepts **only** a decoder output draft: ``intent.kinematics`` with provenance
``decoded_intent`` and the running model's id. Anything else (raw signal, features,
behavioral labels, simulated intent) raises :class:`CommandProvenanceError`: recorded or
cued behavior can never become a command, whatever the configuration.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from brainos.adapters.base import EventDraft
from brainos.contracts.capabilities import Capability, CapabilityDescriptor, EventType
from brainos.contracts.events import ProvenanceKind

DEFAULT_STALL_MS = 1000.0
DEFAULT_RELEASE_GAP = 0.15  # release level = threshold - this (hysteresis), unless given
DiscreteAction = Literal["primary", "activate", "cancel", "text"]


class CommandProvenanceError(ValueError):
    """Something other than the running decoder's output was offered to the router."""


class DiscreteRule(BaseModel):
    """Fire one discrete action when a class posterior stays high.

    Fires when ``output`` >= ``threshold`` continuously for ``hold_ms`` (decoder time), at
    most once per ``refractory_ms``; after firing, the output must drop below ``release``
    (default ``threshold - 0.15``) before the rule re-arms (hysteresis: noise around the
    threshold cannot chatter).
    """

    model_config = ConfigDict(extra="forbid")

    output: str = Field(min_length=1, max_length=32, description="class name (decoder dim)")
    threshold: float = Field(default=0.8, gt=0, le=1, allow_inf_nan=False)
    release: float | None = Field(default=None, ge=0, lt=1, allow_inf_nan=False)
    hold_ms: float = Field(default=300.0, ge=0, le=10_000, allow_inf_nan=False)
    refractory_ms: float = Field(default=1000.0, ge=0, le=60_000, allow_inf_nan=False)
    action: DiscreteAction
    text: str | None = Field(default=None, min_length=1, max_length=64)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.action == "text" and not self.text:
            raise ValueError("a text rule needs 'text'")
        if self.action != "text" and self.text is not None:
            raise ValueError("'text' is only valid for action 'text'")
        if self.release is not None and self.release >= self.threshold:
            raise ValueError("release must be below threshold (hysteresis)")
        return self

    @property
    def release_level(self) -> float:
        if self.release is not None:
            return self.release
        return max(0.0, self.threshold - DEFAULT_RELEASE_GAP)


class RouterSpec(BaseModel):
    """Explicit operator mapping from decoder outputs to commands. Off by default."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    # continuous pointer: two dims of a continuous decoder (both or neither)
    x_dim: str | None = None
    y_dim: str | None = None
    gain: float = Field(default=1.0, gt=0, le=10, description="workspace/s per training-std unit")
    deadzone: float = Field(default=0.3, ge=0, lt=3, description="in training-std units")
    invert_y: bool = False
    max_speed: float = Field(default=2.0, gt=0, le=10)
    # discrete actions from a classifier's posteriors
    discrete: list[DiscreteRule] = Field(default_factory=list, max_length=8)
    # stop all commands when the decoder gets no input for this long (see pipeline.py)
    stall_ms: float = Field(default=DEFAULT_STALL_MS, ge=100, le=10_000, allow_inf_nan=False)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if (self.x_dim is None) != (self.y_dim is None):
            raise ValueError("give both x_dim and y_dim for a pointer mapping, or neither")
        outs = [r.output for r in self.discrete]
        if len(set(outs)) != len(outs):
            raise ValueError("one discrete rule per output")
        return self

    @property
    def pointer(self) -> bool:
        return self.x_dim is not None and self.y_dim is not None


def pointer_velocity(
    r: RouterSpec, dims: list[str], values: list[float], std: list[float]
) -> tuple[float, float]:
    res = []
    for d in (r.x_dim, r.y_dim):
        assert d is not None
        i = dims.index(d)
        z = values[i] / std[i] if std[i] > 0 else 0.0
        if abs(z) < r.deadzone:
            z = 0.0
        v = max(-r.max_speed, min(r.max_speed, r.gain * z))
        res.append(round(v, 6))
    if r.invert_y:
        res[1] = -res[1]
    return res[0], res[1]


def router_capabilities(r: RouterSpec, model_id: str) -> list[CapabilityDescriptor]:
    """What an enabled router actually provides (nothing it is not configured for)."""
    caps: list[CapabilityDescriptor] = []
    if r.pointer:
        assert r.x_dim is not None and r.y_dim is not None
        caps.append(
            CapabilityDescriptor(
                capability=Capability.POINTER_INTENT,
                params={
                    "source": "command_router",
                    "model_id": model_id,
                    "x_dim": r.x_dim,
                    "y_dim": r.y_dim,
                    "gain": r.gain,
                },
                description="Pointer commands routed from a decoder by explicit operator mapping",
            )
        )
    actions = sorted({d.action for d in r.discrete if d.action != "text"})
    if actions:
        caps.append(
            CapabilityDescriptor(
                capability=Capability.SELECTION,
                params={"source": "command_router", "model_id": model_id, "actions": actions},
                description="Discrete actions from a classifier by explicit operator rules",
            )
        )
    texts = [d for d in r.discrete if d.action == "text" and d.text]
    if texts:
        modes = sorted({"character" if len(d.text or "") == 1 else "word" for d in texts})
        caps.append(
            CapabilityDescriptor(
                capability=Capability.TEXT_INTENT,
                params={"source": "command_router", "model_id": model_id, "text_modes": modes},
                description="Text from a classifier by explicit operator rules",
            )
        )
    return caps


@dataclass
class _RuleState:
    armed: bool = True
    above_since: int | None = None
    last_fire: int | None = None


class CommandRouter:
    """Stateful router for one running decoder and one router spec (pure, no I/O)."""

    def __init__(
        self,
        spec: RouterSpec,
        *,
        model_id: str,
        dims: list[str],
        behavior_std: list[float] | None,
    ) -> None:
        self.spec, self.model_id, self.dims, self.std = spec, model_id, list(dims), behavior_std
        self._states = [_RuleState() for _ in spec.discrete]
        self.fired: dict[str, int] = {}

    def route(self, decoded: EventDraft) -> list[EventDraft]:
        p = decoded.provenance
        if (
            decoded.event_type is not EventType.INTENT_KINEMATICS
            or p.kind is not ProvenanceKind.DECODED_INTENT
            or p.model_id != self.model_id
        ):
            raise CommandProvenanceError(
                f"the command router only accepts output of decoder {self.model_id} "
                f"(got {decoded.event_type} / {p.kind} / model {p.model_id})"
            )
        if list(decoded.payload.get("dims", [])) != self.dims:
            raise CommandProvenanceError("decoder output dimensions changed")
        values = [float(v) for v in decoded.payload["values"]]
        out: list[EventDraft] = []
        if not self.spec.enabled:
            return out
        if self.spec.pointer and self.std is not None:
            vx, vy = pointer_velocity(self.spec, self.dims, values, self.std)
            out.append(self._draft(decoded, EventType.INTENT_POINTER, {"vx": vx, "vy": vy}))
        # hold / refractory run on the decoder's (device) clock; a source without device
        # timestamps falls back to the runtime's monotonic clock
        ts = decoded.device_timestamp_ns or time.monotonic_ns()
        for rule, st in zip(self.spec.discrete, self._states, strict=True):
            value = values[self.dims.index(rule.output)]
            if self._step(rule, st, value, ts):
                conf = min(1.0, max(0.0, value))
                if rule.action == "text":
                    text = rule.text or ""
                    payload = {
                        "text": text,
                        "mode": "character" if len(text) == 1 else "word",
                        "confidence": conf,
                    }
                    out.append(self._draft(decoded, EventType.INTENT_TEXT, payload))
                else:
                    payload = {"action": rule.action, "confidence": conf}
                    out.append(self._draft(decoded, EventType.INTENT_SELECTION, payload))
                key = f"{rule.output}->{rule.action}"
                self.fired[key] = self.fired.get(key, 0) + 1
        return out

    @staticmethod
    def _step(rule: DiscreteRule, st: _RuleState, value: float, ts: int) -> bool:
        if st.last_fire is not None and ts < st.last_fire:
            st.last_fire = None  # source clock restarted (e.g. a looping replay)
        if not st.armed:
            if value < rule.release_level:
                st.armed = True
            st.above_since = None
            return False
        if value < rule.threshold:
            st.above_since = None
            return False
        if st.above_since is None or ts < st.above_since:
            st.above_since = ts
        held = (ts - st.above_since) / 1e6 >= rule.hold_ms
        rested = st.last_fire is None or (ts - st.last_fire) / 1e6 >= rule.refractory_ms
        if held and rested:
            st.last_fire = ts
            st.armed = False
            st.above_since = None
            return True
        return False

    @staticmethod
    def _draft(decoded: EventDraft, et: EventType, payload: Mapping[str, object]) -> EventDraft:
        return EventDraft(
            et, dict(payload), decoded.quality, decoded.provenance, decoded.device_timestamp_ns
        )
