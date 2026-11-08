"""Milestone 4: SDK command-safety helper (concord.sdk.CommandGuard / ControlChannel)."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from typing import Any

import pytest

from concord.contracts import parse_envelope
from concord.contracts.protocol import (
    AppStatus,
    CapabilityRejection,
    NegotiationResult,
    RejectionReason,
    RuntimeSnapshot,
    RuntimeState,
)
from concord.sdk import CommandGuard, ControlChannel, NegotiationUpdate, RuntimeUpdate

from .helpers import valid_event


class Clock:
    def __init__(self) -> None:
        self.wall = 1_700_000_000_000_000_000
        self.mono = 5_000_000_000

    def advance(self, ms: float) -> None:
        self.wall += round(ms * 1e6)
        self.mono += round(ms * 1e6)


def _neg(granted: list[str], rejected: list[tuple[str, str, bool]] = ()) -> NegotiationResult:  # type: ignore[assignment]
    rej = [
        CapabilityRejection(capability=c, reason=RejectionReason(r), required=req)  # type: ignore[arg-type]
        for c, r, req in rejected
    ]
    status = AppStatus.SUSPENDED if any(r.required for r in rej) else AppStatus.ACTIVE
    return NegotiationResult(device_id="d", status=status, granted=granted, rejected=rej)  # type: ignore[arg-type]


def _runtime(state: str = "streaming", session: str | None = "ses_aaaaaaaa") -> RuntimeUpdate:
    return RuntimeUpdate(
        RuntimeSnapshot(
            state=RuntimeState(state),
            device=None,
            session_id=session,
            state_since_ns=0,
            last_error=None,
            recording=None,
            apps=[],
        )
    )


def _cmd(
    clock: Clock, event_type: str = "intent.pointer", age_ms: float = 0, **payload: Any
) -> Any:
    ev = valid_event(event_type, timestamp_ns=clock.wall - round(age_ms * 1e6))
    ev["provenance"].update(kind="decoded_intent", model_id="m1")
    ev["payload"].update(payload)
    return parse_envelope(ev)


def _guard(clock: Clock, stops: list[str], **kw: Any) -> CommandGuard:
    g = CommandGuard(
        on_stop=stops.append,
        wall_clock_ns=lambda: clock.wall,
        monotonic_ns=lambda: clock.mono,
        **kw,
    )
    g.handle(_runtime())
    return g


def test_waiting_for_authorization_then_active_then_revoked() -> None:
    clock, stops = Clock(), []
    g = _guard(clock, stops)
    g.handle(NegotiationUpdate(_neg([], [("selection", "not_authorized", True)])))
    assert g.waiting_for_authorization == ["selection"] and g.state("selection") == "not_authorized"
    assert g.handle(_cmd(clock, "intent.selection")) is None and g.stats.dropped_inactive == 1
    g.handle(NegotiationUpdate(_neg(["selection"])))
    assert g.is_active("selection") and g.waiting_for_authorization == []
    assert g.handle(_cmd(clock, "intent.selection")) is not None
    assert stops == []
    g.handle(NegotiationUpdate(_neg([], [("selection", "not_authorized", True)])))
    assert stops == ["authorization revoked"] and not g.is_active("selection")
    assert g.handle(_cmd(clock, "intent.selection")) is None


@pytest.mark.parametrize(
    ("update", "reason"),
    [
        (
            NegotiationUpdate(_neg([], [("pointer_intent", "unsupported_by_device", True)])),
            "command output stopped",
        ),
        (
            NegotiationUpdate(
                NegotiationResult(
                    device_id=None, status=AppStatus.NO_DEVICE, granted=[], rejected=[]
                )
            ),
            "source disconnected",
        ),
        (_runtime("paused"), "source paused"),
        (_runtime("reconnecting"), "source reconnecting"),
        (_runtime("idle", None), "source idle"),
    ],
)
def test_every_loss_of_command_input_stops_immediately(update: Any, reason: str) -> None:
    clock, stops = Clock(), []
    g = _guard(clock, stops)
    g.handle(NegotiationUpdate(_neg(["pointer_intent"])))
    assert g.handle(_cmd(clock, vx=0.5, vy=0.1)) is not None
    assert g.velocity == (0.5, 0.1)
    g.handle(update)
    assert stops == [reason] and g.velocity == (0.0, 0.0) and g.stop_reason == reason


def test_stream_close_stops_and_non_commands_pass_through() -> None:
    clock, stops = Clock(), []
    g = _guard(clock, stops)
    g.handle(NegotiationUpdate(_neg(["pointer_intent", "selection"])))
    tel = parse_envelope(valid_event("telemetry.sample"))
    assert g.handle(tel) is tel  # not a command: the guard does not filter it
    g.on_closed()
    assert stops == ["stream closed"] and g.state("pointer_intent") == "closed"
    assert g.state("text_intent") != "active"


def test_stale_and_late_commands_are_dropped() -> None:
    clock, stops = Clock(), []
    g = _guard(clock, stops, max_age_ms=300)
    g.handle(NegotiationUpdate(_neg(["pointer_intent"])))
    assert g.handle(_cmd(clock, age_ms=20)) is not None  # baseline delivery offset 20 ms
    assert g.handle(_cmd(clock, age_ms=301)) is None and g.stats.dropped_stale == 1
    # clocks disagree (runtime on another machine): only relative lateness counts
    g2 = _guard(clock, stops, max_age_ms=300, compare_wall_clock=False)
    g2.handle(NegotiationUpdate(_neg(["pointer_intent"])))
    assert g2.handle(_cmd(clock, age_ms=5000)) is not None  # skewed clock: accepted
    clock.advance(100)
    assert g2.handle(_cmd(clock, age_ms=5000)) is not None  # same offset: fresh
    clock.advance(100)
    assert g2.handle(_cmd(clock, age_ms=5400)) is None  # held up 400 ms vs baseline
    assert g2.stats.dropped_late == 1 and g2.stats.accepted == 2


def test_deadman_reports_zero_velocity_once_per_idle_period() -> None:
    clock, stops = Clock(), []
    idle: list[int] = []
    g = _guard(clock, stops, deadman_ms=200)
    g.on_deadman = lambda: idle.append(1)
    g.handle(NegotiationUpdate(_neg(["pointer_intent"])))
    g.handle(_cmd(clock, vx=1.0, vy=-1.0))
    clock.advance(150)
    assert not g.tick() and g.velocity == (1.0, -1.0)
    clock.advance(60)
    assert g.tick() and g.velocity == (0.0, 0.0) and idle == [1]
    clock.advance(500)
    assert not g.tick() and idle == [1]  # once per idle period
    g.handle(_cmd(clock, vx=0.2, vy=0.0))
    assert g.velocity == (0.2, 0.0)
    assert stops == []  # the dead-man is not a stop: commands may resume


def test_guard_rejects_bad_configuration() -> None:
    with pytest.raises(ValueError, match="not command capabilities"):
        CommandGuard(["recording"])
    with pytest.raises(ValueError, match="positive"):
        CommandGuard(max_age_ms=0)


class _FakeStream:
    def __init__(self, items: list[Any]) -> None:
        self.negotiation = _neg([], [("selection", "not_authorized", True)])
        self.runtime = _runtime().runtime
        self.items = items

    def __aiter__(self) -> AsyncIterator[Any]:
        async def gen() -> AsyncIterator[Any]:
            for it in self.items:
                await asyncio.sleep(0)
                yield it

        return gen()


async def test_control_channel_filters_and_reports_close() -> None:
    clock, stops = Clock(), []
    g = CommandGuard(on_stop=stops.append)
    sel = _cmd(clock, "intent.selection")
    fresh = parse_envelope({**valid_event("intent.selection"), "timestamp_ns": time.time_ns()})
    items = [
        sel,  # not yet authorized: dropped
        NegotiationUpdate(_neg(["selection"])),
        fresh,
        parse_envelope(valid_event("telemetry.sample")),
    ]
    out = [x async for x in ControlChannel(_FakeStream(items), g)]  # type: ignore[arg-type]
    assert isinstance(out[0], NegotiationUpdate)
    assert [getattr(x, "event_type", None) for x in out[1:]] == [
        "intent.selection",
        "telemetry.sample",
    ]
    assert stops == ["stream closed"]


# ------------------------------------------------------------------ schema 1.4 (M5-C)


def _ctl(active: bool, caps: list[str], reason: str, session: str = "ses_aaaaaaaa") -> Any:
    ev = valid_event("control.state", timestamp_ns=time.time_ns())
    ev["session_id"] = session
    ev["payload"] = {"active": active, "capabilities": caps, "reason": reason}
    return parse_envelope(ev)


def test_control_state_gates_commands_and_stops_with_the_runtimes_reason() -> None:
    clock, stops = Clock(), []
    g = _guard(clock, stops)
    g.handle(NegotiationUpdate(_neg(["selection", "navigation", "control_status"])))
    # control_status granted: nothing is usable until the runtime says so
    assert not g.is_active("selection") and g.state("selection") == "control_inactive"
    assert g.handle(_cmd(clock, "intent.selection")) is None
    on = _ctl(True, ["navigation", "selection"], "operator authorized this application")
    assert g.handle(on) is on  # passed through: the app may show it
    assert g.is_active("selection") and g.is_active("navigation")
    assert g.handle(_cmd(clock, "intent.navigate")) is not None
    assert g.control_state == (
        True,
        frozenset({"navigation", "selection"}),
        "operator authorized this application",
    )
    g.handle(_ctl(True, ["selection"], "authorization revoked by operator (navigation)"))
    assert stops == ["authorization revoked by operator (navigation)"]
    assert not g.is_active("navigation") and g.is_active("selection")
    g.handle(_ctl(False, [], "command output stopped: input stalled"))
    assert stops[-1] == "command output stopped: input stalled"
    assert g.handle(_cmd(clock, "intent.selection")) is None
    # a notice from another session never re-enables commands in this one
    g.handle(_runtime(session="ses_bbbbbbbb"))
    g.handle(_ctl(True, ["selection"], "stale", session="ses_aaaaaaaa"))
    assert not g.is_active("selection") and g.control_state is None
    g.handle(_ctl(True, ["selection"], "now", session="ses_bbbbbbbb"))
    assert g.is_active("selection")


def test_without_control_status_the_guard_behaves_as_before() -> None:
    clock, stops = Clock(), []
    g = _guard(clock, stops)
    g.handle(NegotiationUpdate(_neg(["navigation"])))
    assert g.is_active("navigation")  # navigation is a command capability (schema 1.4)
    assert g.handle(_cmd(clock, "intent.navigate")) is not None
    g.handle(_ctl(False, [], "not asked for"))  # control_status not granted: no gating
    assert g.is_active("navigation") and stops == []
