"""The command router: the only path from decoder output to application commands.

Standardized action set (all ``decoded_intent`` + ``model_id``, produced only here):

* continuous 2-D movement -> ``intent.pointer`` (two decoded dimensions of a continuous
  decoder; scaled by the training behavior std (``pointer_scale="training_std"``) or taken
  as a velocity already in workspace units (``"native"``, e.g. a research system's original
  cursor decoder), then gain / dead-zone / clamp / optional y inversion);
* discrete ``select`` (``intent.selection`` action ``primary``), ``activate``, ``cancel``,
  ``text`` (``intent.text``) and, schema 1.4, ``navigate:<direction>`` (``intent.navigate``)
  -> from a classifier's class posteriors by explicit rules with threshold, hold time,
  refractory period and hysteresis;
* a **click** (schema 1.4 router feature, no contract change): one decoder output that is a
  click probability or a 0/1 click decision -> ``intent.selection`` (``primary`` or
  ``activate``), with debounce (hold), refractory period, hysteresis and a minimum-confidence
  gate. Works on a continuous decoder next to the pointer mapping (cursor + click).

The router accepts **only** a decoder output draft: ``intent.kinematics`` with provenance
``decoded_intent`` and the configured model's id (whoever produced it: a BrainOS model, an
external live decoder or a historical replay; ``provenance.model_origin`` is carried over to
every command unchanged). Anything else (raw signal, features, behavioral labels, simulated
intent) raises :class:`CommandProvenanceError`: recorded or cued behavior can never become a
command, whatever the configuration.
"""

from __future__ import annotations

import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal, Self, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from brainos.adapters.base import EventDraft
from brainos.contracts.capabilities import Capability, CapabilityDescriptor, EventType
from brainos.contracts.events import ProvenanceKind
from brainos.contracts.protocol import ErrorCode

DEFAULT_STALL_MS = 1000.0
DEFAULT_RELEASE_GAP = 0.15  # release level = threshold - this (hysteresis), unless given
NavigateDirection = Literal["up", "down", "left", "right", "next", "previous"]
NAVIGATE_DIRECTIONS: tuple[str, ...] = get_args(NavigateDirection)
DiscreteAction = Literal[
    "primary",
    "activate",
    "cancel",
    "text",
    "navigate:up",
    "navigate:down",
    "navigate:left",
    "navigate:right",
    "navigate:next",
    "navigate:previous",
]
SELECTION_ACTIONS = frozenset({"primary", "activate", "cancel"})


def navigate_direction(action: str) -> str | None:
    """``"navigate:next"`` -> ``"next"``; anything else -> None."""
    if action.startswith("navigate:"):
        d = action.split(":", 1)[1]
        return d if d in NAVIGATE_DIRECTIONS else None
    return None


class CommandProvenanceError(ValueError):
    """Something other than the running decoder's output was offered to the router."""


class RouterConfigError(ValueError):
    """A router mapping that does not fit the decoder (code: the runtime error code)."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        self.code, self.message = code, message
        super().__init__(message)


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


class ClickRule(BaseModel):
    """A click from one decoder output (a click probability, or a 0/1 click decision).

    Fires ``intent.selection`` with ``action`` when ``output`` >= ``threshold`` continuously
    for ``debounce_ms`` (decoder time), at most once per ``refractory_ms``, then waits until
    the output falls below ``release`` (default ``threshold - 0.15``): one click, one
    selection. At the moment it would fire, the confidence (``confidence_dim``, default the
    output itself, clipped to [0, 1]) must be >= ``min_confidence``, else the click is
    rejected (counted, not delivered) and the rule waits for the release like after a click.
    """

    model_config = ConfigDict(extra="forbid")

    output: str = Field(min_length=1, max_length=32, description="decoder dim: click p or 0/1")
    action: Literal["primary", "activate"] = "primary"
    threshold: float = Field(default=0.5, gt=0, le=1, allow_inf_nan=False)
    release: float | None = Field(default=None, ge=0, lt=1, allow_inf_nan=False)
    min_confidence: float = Field(default=0.0, ge=0, le=1, allow_inf_nan=False)
    confidence_dim: str | None = Field(default=None, min_length=1, max_length=32)
    debounce_ms: float = Field(default=0.0, ge=0, le=2_000, allow_inf_nan=False)
    refractory_ms: float = Field(default=300.0, ge=0, le=10_000, allow_inf_nan=False)

    @model_validator(mode="after")
    def _check(self) -> Self:
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
    # "training_std": value / training behavior std (unitless z), then gain;
    # "native": the value is already a velocity in workspace units per second, times gain
    pointer_scale: Literal["training_std", "native"] = "training_std"
    gain: float = Field(default=1.0, gt=0, le=10, description="workspace/s per input unit")
    deadzone: float = Field(default=0.3, ge=0, lt=3, description="in input units (see scale)")
    invert_y: bool = False
    max_speed: float = Field(default=2.0, gt=0, le=10)
    # discrete actions from a classifier's posteriors
    discrete: list[DiscreteRule] = Field(default_factory=list, max_length=8)
    # a click from one decoder output (probability or decision), e.g. cursor + click
    click: ClickRule | None = None
    # stop all commands when the decoder gets no input for this long (see pipeline.py)
    stall_ms: float = Field(default=DEFAULT_STALL_MS, ge=100, le=10_000, allow_inf_nan=False)

    @model_validator(mode="after")
    def _check(self) -> Self:
        if (self.x_dim is None) != (self.y_dim is None):
            raise ValueError("give both x_dim and y_dim for a pointer mapping, or neither")
        outs = [r.output for r in self.discrete]
        if self.click is not None:
            outs.append(self.click.output)
        if len(set(outs)) != len(outs):
            raise ValueError("one discrete rule per output (the click counts as one)")
        if self.click is not None and self.click.output in (self.x_dim, self.y_dim):
            raise ValueError("the click output cannot also drive the pointer")
        return self

    @property
    def pointer(self) -> bool:
        return self.x_dim is not None and self.y_dim is not None


def pointer_velocity(
    r: RouterSpec, dims: list[str], values: list[float], std: list[float] | None
) -> tuple[float, float]:
    res = []
    for d in (r.x_dim, r.y_dim):
        assert d is not None
        i = dims.index(d)
        if r.pointer_scale == "native":
            z = values[i]
        else:
            assert std is not None
            z = values[i] / std[i] if std[i] > 0 else 0.0
        if abs(z) < r.deadzone:
            z = 0.0
        v = max(-r.max_speed, min(r.max_speed, r.gain * z))
        res.append(round(v, 6))
    if r.invert_y:
        res[1] = -res[1]
    return res[0], res[1]


def validate_router(
    r: RouterSpec,
    *,
    model_id: str,
    dims: Sequence[str],
    classes: Sequence[str] | None,
    has_std: bool,
    quantity: str = "",
) -> None:
    """Refuse a mapping the decoder cannot serve (raises :class:`RouterConfigError`).

    Capabilities are only ever advertised for what passes here (see
    :func:`router_capabilities`): a pointer needs two continuous dims, discrete rules need a
    classifier's classes, a click needs an output that exists.
    """
    if not r.pointer and not r.discrete and r.click is None:
        raise RouterConfigError(
            ErrorCode.CAPABILITY_UNSUPPORTED,
            "the command router has nothing to emit: map two decoder dimensions to the "
            "pointer (x_dim, y_dim), add discrete rules, or a click output",
        )
    if r.pointer:
        if classes is not None:
            raise RouterConfigError(
                ErrorCode.INCOMPATIBLE_DECODER,
                f"pointer movement needs a continuous decoder; {model_id} is a "
                f"classifier (classes {list(classes)}). Use discrete rules instead.",
            )
        for d in (r.x_dim, r.y_dim):
            if d not in dims:
                raise RouterConfigError(
                    ErrorCode.PROTOCOL_ERROR, f"decoder has no dimension {d!r} ({list(dims)})"
                )
        if r.pointer_scale == "training_std" and not has_std:
            raise RouterConfigError(
                ErrorCode.PROTOCOL_ERROR,
                "model lacks training behavior_std; retrain it, or use pointer_scale "
                "'native' if its output already is a velocity in workspace units",
            )
    if r.discrete:
        if classes is None:
            raise RouterConfigError(
                ErrorCode.INCOMPATIBLE_DECODER,
                f"discrete actions need a classifier (outputs: classes); {model_id} "
                f"outputs continuous {quantity} {list(dims)}",
            )
        for rule in r.discrete:
            if rule.output not in classes:
                raise RouterConfigError(
                    ErrorCode.INCOMPATIBLE_DECODER,
                    f"decoder {model_id} has no class {rule.output!r} ({list(classes)})",
                )
    if r.click is not None:
        for d in (r.click.output, r.click.confidence_dim):
            if d is not None and d not in dims:
                raise RouterConfigError(
                    ErrorCode.INCOMPATIBLE_DECODER,
                    f"decoder {model_id} has no output {d!r} for the click ({list(dims)})",
                )


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
                    "scale": r.pointer_scale,
                },
                description="Pointer commands routed from a decoder by explicit operator mapping",
            )
        )
    actions = {d.action for d in r.discrete if d.action in SELECTION_ACTIONS}
    if r.click is not None:
        actions.add(r.click.action)
    if actions:
        params: dict[str, str | float | bool | list[str]] = {
            "source": "command_router",
            "model_id": model_id,
            "actions": sorted(actions),
        }
        if r.click is not None:
            params["click"] = r.click.output
        caps.append(
            CapabilityDescriptor(
                capability=Capability.SELECTION,
                params=params,
                description="Discrete actions from a decoder by explicit operator rules",
            )
        )
    directions = sorted(
        {d for d in (navigate_direction(x.action) for x in r.discrete) if d is not None}
    )
    if directions:
        caps.append(
            CapabilityDescriptor(
                capability=Capability.NAVIGATION,
                params={"source": "command_router", "model_id": model_id, "directions": directions},
                description="Navigation (move a highlight) from a classifier by explicit rules",
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
        self._click = _RuleState()
        self.fired: dict[str, int] = {}
        self.clicks_gated = 0  # clicks rejected by the minimum-confidence gate

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
        if self.spec.pointer and (self.spec.pointer_scale == "native" or self.std is not None):
            vx, vy = pointer_velocity(self.spec, self.dims, values, self.std)
            out.append(self._draft(decoded, EventType.INTENT_POINTER, {"vx": vx, "vy": vy}))
        # hold / refractory run on the decoder's (device) clock; a source without device
        # timestamps falls back to the runtime's monotonic clock
        ts = decoded.device_timestamp_ns or time.monotonic_ns()
        click = self.spec.click
        if click is not None:
            value = values[self.dims.index(click.output)]
            fire = _step(
                click.threshold,
                click.release_level,
                click.debounce_ms,
                click.refractory_ms,
                self._click,
                value,
                ts,
            )
            if fire:
                cdim = click.confidence_dim or click.output
                conf = min(1.0, max(0.0, values[self.dims.index(cdim)]))
                if conf >= click.min_confidence:
                    click_payload: dict[str, object] = {"action": click.action, "confidence": conf}
                    out.append(self._draft(decoded, EventType.INTENT_SELECTION, click_payload))
                    key = f"{click.output}->click"
                    self.fired[key] = self.fired.get(key, 0) + 1
                else:
                    self.clicks_gated += 1
        for rule, st in zip(self.spec.discrete, self._states, strict=True):
            value = values[self.dims.index(rule.output)]
            if not _step(
                rule.threshold, rule.release_level, rule.hold_ms, rule.refractory_ms, st, value, ts
            ):
                continue
            conf = min(1.0, max(0.0, value))
            direction = navigate_direction(rule.action)
            if rule.action == "text":
                text = rule.text or ""
                payload = {
                    "text": text,
                    "mode": "character" if len(text) == 1 else "word",
                    "confidence": conf,
                }
                out.append(self._draft(decoded, EventType.INTENT_TEXT, payload))
            elif direction is not None:
                payload = {"direction": direction, "confidence": conf}
                out.append(self._draft(decoded, EventType.INTENT_NAVIGATE, payload))
            else:
                payload = {"action": rule.action, "confidence": conf}
                out.append(self._draft(decoded, EventType.INTENT_SELECTION, payload))
            key = f"{rule.output}->{rule.action}"
            self.fired[key] = self.fired.get(key, 0) + 1
        return out

    @staticmethod
    def _draft(decoded: EventDraft, et: EventType, payload: Mapping[str, object]) -> EventDraft:
        return EventDraft(
            et, dict(payload), decoded.quality, decoded.provenance, decoded.device_timestamp_ns
        )


def _step(
    threshold: float,
    release: float,
    hold_ms: float,
    refractory_ms: float,
    st: _RuleState,
    value: float,
    ts: int,
) -> bool:
    """Threshold + hold + refractory + hysteresis on one output; True when it fires."""
    if st.last_fire is not None and ts < st.last_fire:
        st.last_fire = None  # source clock restarted (e.g. a looping replay)
    if not st.armed:
        if value < release:
            st.armed = True
        st.above_since = None
        return False
    if value < threshold:
        st.above_since = None
        return False
    if st.above_since is None or ts < st.above_since:
        st.above_since = ts
    held = (ts - st.above_since) / 1e6 >= hold_ms
    rested = st.last_fire is None or (ts - st.last_fire) / 1e6 >= refractory_ms
    if held and rested:
        st.last_fire = ts
        st.armed = False
        st.above_since = None
        return True
    return False
