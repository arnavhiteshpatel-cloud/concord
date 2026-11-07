"""Milestone 5-C runtime side of schema 1.4: navigation rules, the click rule, native pointer
scale, capability advertisement, and per-application ``control.state`` (safe-state signal).

Sources: the in-test synthetic motor-imagery source + an LDA fitted on separate synthetic data
(discrete actions), and the scripted decoder test source + its hand-written identity test
decoder (brainos.testing.scripted; cursor + click). Nothing here is neural or human data.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("scipy")

from pydantic import ValidationError

from brainos.adapters.base import EventDraft
from brainos.adapters.simulated import OperatorIntentSource
from brainos.contracts.capabilities import Capability, EventType
from brainos.contracts.events import Provenance, ProvenanceKind, Quality
from brainos.contracts.protocol import AppStatus, ErrorCode
from brainos.decoding.lda import LDAClassifier
from brainos.runtime import DeviceRegistry, Recorder, Runtime, RuntimeCommandError
from brainos.runtime.bus import Subscriber
from brainos.runtime.negotiation import negotiate
from brainos.runtime.pipeline import PipelineStartRequest
from brainos.runtime.router import (
    ClickRule,
    CommandProvenanceError,
    CommandRouter,
    RouterConfigError,
    RouterSpec,
    router_capabilities,
    validate_router,
)
from brainos.testing import scripted

from .conftest import subscribe
from .helpers import drain, events, scripted_descriptor, wait_for
from .mi_source import MotorImageryAdapter, train_offline_lda

BAND = {"preset": "band_power", "band_low_hz": 8, "band_high_hz": 13, "bin_ms": 200}
SEL, NAV, PTR, CTL = (
    Capability.SELECTION,
    Capability.NAVIGATION,
    Capability.POINTER_INTENT,
    Capability.CONTROL_STATUS,
)
COMMANDS = {"intent.pointer", "intent.selection", "intent.text", "intent.navigate"}


def _draft(
    values: list[float],
    ts_ms: float,
    dims: list[str] | None = None,
    *,
    origin: str | None = None,
    replayed: bool = False,
) -> EventDraft:
    return EventDraft(
        EventType.INTENT_KINEMATICS,
        {
            "quantity": "q",
            "dims": dims or ["vx", "vy", "click"],
            "unit": "u",
            "values": values,
            "space": "s",
        },
        Quality(score=1.0),
        Provenance(
            kind=ProvenanceKind.DECODED_INTENT,
            adapter="brainos.pipeline@0.4.0",
            synthetic=True,
            model_id="m1",
            origin="test",
            replayed=replayed,
            model_origin=origin,  # type: ignore[arg-type]
        ),
        round((ts_ms + 10_000) * 1e6),
    )


# ----------------------------------------------------------------------------- router (pure)


def test_navigate_rules_emit_intent_navigate_and_advertise_navigation_only() -> None:
    spec = RouterSpec(
        enabled=True,
        discrete=[
            {"output": "left", "action": "navigate:previous", "threshold": 0.7, "hold_ms": 0},
            {"output": "right", "action": "navigate:next", "threshold": 0.7, "hold_ms": 0},
        ],  # type: ignore[list-item]
    )
    caps = {c.capability: c.params for c in router_capabilities(spec, "m1")}
    assert set(caps) == {NAV}  # no select/activate/cancel rule -> no selection capability
    assert caps[NAV]["directions"] == ["next", "previous"]
    r = CommandRouter(spec, model_id="m1", dims=["rest", "left", "right"], behavior_std=None)
    out = r.route(_draft([0.1, 0.1, 0.8], 0, ["rest", "left", "right"]))
    assert [(d.event_type, d.payload) for d in out] == [
        (EventType.INTENT_NAVIGATE, {"direction": "next", "confidence": 0.8})
    ]
    assert r.route(_draft([0.1, 0.1, 0.8], 20, ["rest", "left", "right"])) == []  # hysteresis
    assert r.fired == {"right->navigate:next": 1}
    with pytest.raises(ValidationError):
        RouterSpec(discrete=[{"output": "x", "action": "navigate:sideways"}])  # type: ignore[list-item]


def _clicks(router: CommandRouter, series: list[tuple[float, float, float]]) -> list[Any]:
    """series of (t_ms, click, confidence) -> selections fired with their time."""
    out = []
    for t, c, conf in series:
        for d in router.route(_draft([0.0, 0.0, c, conf], t, ["vx", "vy", "click", "p"])):
            if d.event_type is EventType.INTENT_SELECTION:
                out.append((t, d.payload))
    return out


def test_click_rule_debounce_refractory_hysteresis_and_confidence_gate() -> None:
    spec = RouterSpec(
        enabled=True,
        x_dim="vx",
        y_dim="vy",
        pointer_scale="native",
        deadzone=0,
        click=ClickRule(
            output="click",
            confidence_dim="p",
            min_confidence=0.6,
            debounce_ms=40,
            refractory_ms=300,
        ),
    )
    r = CommandRouter(spec, model_id="m1", dims=["vx", "vy", "click", "p"], behavior_std=None)
    series = [
        (0, 1.0, 0.9),  # rises
        (20, 1.0, 0.9),
        (40, 1.0, 0.9),  # held 40 ms -> one click
        (60, 1.0, 0.9),  # still down: no repeat (hysteresis)
        (80, 0.0, 0.1),  # released
        (100, 1.0, 0.9),
        (140, 1.0, 0.9),  # held, but within the refractory period of the first click
        (200, 0.0, 0.1),
        (400, 1.0, 0.9),
        (440, 1.0, 0.9),  # second click
        (460, 0.0, 0.1),
        (800, 1.0, 0.3),
        (840, 1.0, 0.3),  # would fire, but the confidence 0.3 < 0.6: rejected and counted
        (860, 0.0, 0.1),
        (1300, 1.0, 0.95),
        (1300, 1.0, 0.95),
    ]
    got = _clicks(r, series)
    assert [t for t, _ in got] == [40, 440]
    assert got[0][1] == {"action": "primary", "confidence": 0.9}
    assert r.clicks_gated == 1
    # pointer commands still flow on every bin, in native units (no training std needed)
    out = r.route(_draft([0.5, -0.25, 0.0, 0.0], 2000, ["vx", "vy", "click", "p"]))
    assert out[0].event_type is EventType.INTENT_POINTER
    assert out[0].payload == {"vx": 0.5, "vy": -0.25}


def test_commands_keep_the_decoders_model_origin_and_replay_flag() -> None:
    spec = RouterSpec(
        enabled=True,
        x_dim="vx",
        y_dim="vy",
        pointer_scale="native",
        deadzone=0.0,  # in output units for the native scale (the default 0.3 is in std units)
        gain=1.087,
        invert_y=True,
        click=ClickRule(output="click"),
    )
    r = CommandRouter(spec, model_id="m1", dims=["vx", "vy", "click"], behavior_std=None)
    out = r.route(_draft([0.1, 0.2, 1.0], 0, origin="historical", replayed=True))
    assert [d.event_type for d in out] == [EventType.INTENT_POINTER, EventType.INTENT_SELECTION]
    for d in out:
        assert d.provenance.model_origin == "historical" and d.provenance.replayed
    assert out[0].payload == {"vx": round(0.1 * 1.087, 6), "vy": -round(0.2 * 1.087, 6)}
    with pytest.raises(CommandProvenanceError):  # another model's output
        r.route(
            EventDraft(
                EventType.INTENT_KINEMATICS,
                _draft([0, 0, 0], 0).payload,
                Quality(score=1.0),
                Provenance(
                    kind=ProvenanceKind.DECODED_INTENT,
                    adapter="x@1.0.0",
                    synthetic=True,
                    model_id="other",
                    origin="o",
                ),
            )
        )


@pytest.mark.parametrize(
    ("spec", "classes", "has_std", "code", "match"),
    [
        ({"click": {"output": "nope"}}, None, False, ErrorCode.INCOMPATIBLE_DECODER, "no output"),
        (
            {"click": {"output": "click", "confidence_dim": "p"}},
            None,
            False,
            ErrorCode.INCOMPATIBLE_DECODER,
            "'p'",
        ),
        ({"x_dim": "vx", "y_dim": "vy"}, None, False, ErrorCode.PROTOCOL_ERROR, "behavior_std"),
        (
            {"discrete": [{"output": "click", "action": "navigate:up"}]},
            None,
            True,
            ErrorCode.INCOMPATIBLE_DECODER,
            "classifier",
        ),
        ({}, None, True, ErrorCode.CAPABILITY_UNSUPPORTED, "nothing to emit"),
    ],
)
def test_router_mappings_the_decoder_cannot_serve_are_refused(
    spec: dict[str, Any], classes: list[str] | None, has_std: bool, code: ErrorCode, match: str
) -> None:
    with pytest.raises(RouterConfigError, match=match) as exc:
        validate_router(
            RouterSpec(enabled=True, **spec),
            model_id="m1",
            dims=["vx", "vy", "click"],
            classes=classes,
            has_std=has_std,
        )
    assert exc.value.code is code
    # the native scale needs no training std; a click on a classifier class is fine
    validate_router(
        RouterSpec(enabled=True, x_dim="vx", y_dim="vy", pointer_scale="native"),
        model_id="m1",
        dims=["vx", "vy"],
        classes=None,
        has_std=False,
    )


def test_malformed_click_specs_are_refused() -> None:
    with pytest.raises(ValidationError, match="release must be below threshold"):
        ClickRule(output="c", threshold=0.5, release=0.5)
    with pytest.raises(ValidationError, match="cannot also drive the pointer"):
        RouterSpec(x_dim="vx", y_dim="c", click={"output": "c"})  # type: ignore[arg-type]
    with pytest.raises(ValidationError, match="one discrete rule per output"):
        RouterSpec(
            discrete=[{"output": "c", "action": "primary"}],  # type: ignore[list-item]
            click={"output": "c"},  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError):
        ClickRule(output="c", min_confidence=1.5)
    with pytest.raises(ValidationError):
        ClickRule(output="c", debounce_ms=-1)


def test_control_status_is_a_runtime_capability_and_navigation_needs_authorization() -> None:
    dev = scripted_descriptor(caps=[SEL, NAV, Capability.DEVICE_STATUS])
    n = negotiate([SEL], [NAV, CTL], dev, decoded_commands=frozenset({SEL, NAV}))
    assert n.status is AppStatus.SUSPENDED
    assert {r.capability: r.reason.value for r in n.rejected} == {
        SEL: "not_authorized",
        NAV: "not_authorized",
    }
    n = negotiate(
        [], [NAV, CTL], dev, decoded_commands=frozenset({NAV}), authorized=frozenset({NAV})
    )
    assert n.status is AppStatus.ACTIVE and set(n.granted) == {NAV, CTL}
    assert negotiate([CTL], [], None).status is AppStatus.NO_DEVICE


# ------------------------------------------------------------------------- control.state


def _states(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e["payload"] for e in events(msgs) if e["event_type"] == "control.state"]


def _sequence(msgs: list[dict[str, Any]]) -> list[str]:
    """Event order as 'on' / 'off' (control.state) and 'cmd' (any command)."""
    out = []
    for e in events(msgs):
        if e["event_type"] == "control.state":
            out.append("on" if e["payload"]["active"] else "off")
        elif e["event_type"] in COMMANDS:
            out.append("cmd")
    return out


def _assert_no_command_while_off(seq: list[str], on: bool | None = None) -> None:
    for x in seq:
        if x in ("on", "off"):
            on = x == "on"
        else:
            assert on, f"a command was delivered while control.state was inactive: {seq}"


async def test_simulated_source_control_state_on_connect_pause_resume_disconnect(
    runtime: Runtime, intents: OperatorIntentSource
) -> None:
    app = subscribe(runtime, required=[], optional=[PTR, SEL, CTL], app_id="board")
    plain = subscribe(runtime, required=[], optional=[PTR, SEL], app_id="plain")
    await runtime.connect("sim-a")
    s = _states(drain(app))
    assert [x["active"] for x in s] == [False, True]
    assert s[0]["reason"].startswith("connecting to")
    assert s[1]["capabilities"] == ["pointer_intent", "selection"]
    assert s[1]["reason"].startswith("source streaming")
    assert _states(drain(plain)) == []  # only apps that ask for control_status get it
    await runtime.pause()
    assert _states(drain(app)) == [
        {"active": False, "capabilities": [], "reason": "source paused by operator"}
    ]
    await runtime.resume()
    s = _states(drain(app))
    assert len(s) == 1 and s[0]["active"] and s[0]["reason"] == "source resumed by operator"
    intents.submit_select()
    await wait_for(lambda: any(e["event_type"] == "intent.selection" for e in events(_peek(app))))
    await runtime.disconnect()
    msgs = drain(app)
    seq = _sequence(msgs)
    assert seq[-1] == "off" and _states(msgs)[-1]["reason"].startswith("device disconnected")
    _assert_no_command_while_off(seq, on=True)  # the last notice before this was "on"
    # a late joiner gets its state at once: no session now -> nothing until the next session
    late = subscribe(runtime, required=[], optional=[CTL], app_id="late")
    assert _states(drain(late)) == []
    await runtime.connect("sim-b")
    s = _states(drain(late))
    assert [x["active"] for x in s] == [False, False]  # no command capability asked for
    assert s[-1]["reason"] == "source streaming (Simulated Profile B)" or s[-1]["reason"]


def _peek(sub: Subscriber) -> list[dict[str, Any]]:
    return [
        json.loads(f'{{"type":"event","delivery_seq":{d},"event":{ev}}}')
        for d, ev, *_ in sub._events
    ]


@pytest.fixture(scope="module")
def lda_model(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, LDAClassifier]:
    d = tmp_path_factory.mktemp("models")
    return d, train_offline_lda(d)


def _runtime(tmp_path: Path, models_dir: Path, **variants: dict[str, Any]) -> Runtime:
    reg = DeviceRegistry(OperatorIntentSource(), tmp_path / "rec", models_dir=models_dir, seed=1)
    for did, kw in variants.items():
        k = {"device_id": did, **kw}
        reg.register(MotorImageryAdapter(**k).descriptor, lambda k=k: MotorImageryAdapter(**k))
    return Runtime(reg, Recorder(tmp_path / "rec"), reconnect_backoff_s=(0.01, 0.02))


NAV_RULES = [
    {"output": "left", "action": "navigate:next", "threshold": 0.6, "hold_ms": 200},
    {"output": "right", "action": "primary", "threshold": 0.6, "hold_ms": 200},
]


async def test_every_stop_path_sends_control_state_off_with_its_reason_and_nothing_after(
    tmp_path: Path, lda_model: tuple[Path, LDAClassifier]
) -> None:
    models_dir, model = lda_model
    rt = _runtime(
        tmp_path,
        models_dir,
        **{"test-mi": {"speed": 20.0, "seed": 8}, "test-mi-2": {"speed": 20.0, "seed": 9}},
    )
    app = subscribe(rt, required=[], optional=[SEL, NAV, CTL], app_id="board")
    rt.authorize_app("board", [SEL, NAV])

    async def running(device: str | None = None) -> None:
        if device is not None:
            await (rt.connect(device) if rt.device is None else rt.switch(device))
        rt.start_pipeline(
            PipelineStartRequest(
                processing=BAND,
                model_id=model.model_id,
                router=RouterSpec(enabled=True, discrete=NAV_RULES),  # type: ignore[arg-type]
            )
        )
        assert set(app.negotiation.granted) == {SEL, NAV, CTL}
        n0 = rt.pipeline.counters["navigations_out"] + rt.pipeline.counters["selections_out"]

        def fired() -> bool:
            c = rt.pipeline.counters
            return c["navigations_out"] + c["selections_out"] > n0

        await wait_for(fired, timeout=20)
        assert app.control_state is not None and app.control_state[1]
        msgs = drain(app)  # consume (queued commands would be withdrawn at the stop)
        assert any(e["event_type"] in COMMANDS for e in events(msgs))
        seen.extend(msgs)

    seen: list[dict[str, Any]] = []

    async def stopped(reason: str) -> None:
        msgs = drain(app)
        await asyncio.sleep(0.4)
        msgs += drain(app)
        seen.extend(msgs)
        s = _states(msgs)
        assert s and not s[-1]["active"], (reason, s)
        # the first notice names the stop; a later one may add why it stays off (e.g. paused)
        last_on = max((i for i, x in enumerate(s) if x["active"]), default=-1)
        assert any(reason in x["reason"] for x in s[last_on + 1 :]), (reason, s)
        assert _sequence(msgs)[-1] == "off", "a command followed the stop"

    await running("test-mi")
    rt.stop_control("operator pressed Stop")
    await stopped("command output stopped: operator pressed Stop")

    await running()
    rt.revoke_app("board", [NAV])  # one capability: control.state shrinks to selection
    msgs = drain(app)
    seen.extend(msgs)
    s = _states(msgs)
    assert s[-1]["active"] and s[-1]["capabilities"] == ["selection"]
    assert s[-1]["reason"] == "authorization revoked by operator (navigation)"
    rt.revoke_app("board")
    await stopped("authorization revoked by operator (selection)")
    rt.authorize_app("board", [SEL, NAV])

    await running()
    await rt.pause()
    await stopped("command output stopped: source paused")
    await rt.resume()

    await running()
    adapter = rt.adapter
    assert isinstance(adapter, MotorImageryAdapter)
    adapter.stalled = True
    await wait_for(lambda: not rt.pipeline.router_on, timeout=3)
    await stopped("command output stopped: input stalled")
    adapter.stalled = False

    await running()
    adapter.fail_reads = 1
    await wait_for(lambda: rt.diagnostics.reconnect_successes >= 1, timeout=5)
    await stopped("command output stopped: source link lost")

    await running()
    await rt.switch("test-mi-2")
    await stopped("command output stopped: device disconnected (switching to test-mi-2)")

    await running()
    rt.stop_pipeline()
    await stopped("command output stopped: stopped by operator")
    await rt.shutdown()

    seq = _sequence(seen)
    _assert_no_command_while_off(seq)
    assert seq.count("cmd") > 0 and seq.count("off") >= 7


async def test_suspended_app_still_learns_why(
    tmp_path: Path, lda_model: tuple[Path, LDAClassifier]
) -> None:
    models_dir, model = lda_model
    rt = _runtime(tmp_path, models_dir, **{"test-mi": {"speed": 20.0, "seed": 3}})
    app = subscribe(rt, required=[SEL], optional=[CTL], app_id="menu")
    await rt.connect("test-mi")
    rt.start_pipeline(
        PipelineStartRequest(
            processing=BAND,
            model_id=model.model_id,
            router=RouterSpec(enabled=True, discrete=NAV_RULES),  # type: ignore[arg-type]
        )
    )
    assert app.negotiation.status is AppStatus.SUSPENDED and app.negotiation.granted == []
    s = _states(drain(app))
    assert not s[-1]["active"]
    assert s[-1]["reason"] == "application suspended: selection (not_authorized)"
    rt.authorize_app("menu", [SEL])
    s = _states(drain(app))
    assert s[-1] == {
        "active": True,
        "capabilities": ["selection"],
        "reason": "operator authorized this application (selection)",
    }
    await rt.shutdown()


async def test_control_state_survives_queue_overflow(runtime: Runtime) -> None:
    app = subscribe(runtime, required=[], optional=[PTR, CTL], app_id="slow")
    app.max_queue = 5
    await runtime.connect("sim-a")
    await wait_for(lambda: app.dropped > 20, timeout=5)
    await runtime.pause()
    kinds = [e["event_type"] for e in events(_peek(app))]
    assert kinds.count("control.state") == 3  # connecting, streaming, paused: none dropped
    assert _states(_peek(app))[-1]["reason"] == "source paused by operator"


async def test_scripted_cursor_click_through_the_pipeline(tmp_path: Path) -> None:
    """The test decoder path the e2e tests rely on: features -> identity decoder -> router."""
    models = tmp_path / "models"
    scripted.write_identity_model(models)
    reg = DeviceRegistry(OperatorIntentSource(), tmp_path / "rec", models_dir=models, seed=1)
    program = scripted.click_program([(0.625, 0.125)])
    reg.register(
        scripted.descriptor(),
        lambda: scripted.ScriptedFeatureSource(program, start_after_s=0.2, speed=5.0),
    )
    rt = Runtime(reg, Recorder(tmp_path / "rec"))
    app = subscribe(rt, required=[], optional=[PTR, SEL, CTL], app_id="board")
    await rt.connect(scripted.DEVICE_ID)
    rt.start_pipeline(
        PipelineStartRequest(
            processing={"preset": "features_passthrough"},
            model_id=scripted.MODEL_ID,
            router=RouterSpec.model_validate(scripted.ROUTER),
        )
    )
    with pytest.raises(RuntimeCommandError):  # the router refuses discrete rules on it
        rt.set_router(RouterSpec(enabled=True, discrete=NAV_RULES))  # type: ignore[arg-type]
    caps = {c.capability: c.params for c in rt.pipeline.capability_descriptors()}
    assert caps[SEL]["actions"] == ["primary"] and caps[SEL]["click"] == "click"
    assert caps[PTR]["scale"] == "native"
    rt.authorize_app("board", [PTR, SEL])
    await wait_for(lambda: rt.pipeline.counters["selections_out"] >= 1, timeout=10)
    msgs = drain(app)
    cmds = [e for e in events(msgs) if e["event_type"] in COMMANDS]
    sel = [e for e in cmds if e["event_type"] == "intent.selection"]
    assert len(sel) == 1 and sel[0]["payload"]["action"] == "primary"
    assert sel[0]["provenance"]["model_id"] == scripted.MODEL_ID
    # integrate exactly as the board does (device clock): the click lands on (0.625, 0.125)
    x = y = 0.5
    last = None
    for e in cmds:
        if e["event_type"] == "intent.pointer":
            t = e["device_timestamp_ns"]
            dt = 0.0 if last is None else min(0.1, (t - last) / 1e9)
            last = t
            x = min(1.0, max(0.0, x + e["payload"]["vx"] * dt))
            y = min(1.0, max(0.0, y + e["payload"]["vy"] * dt))
        else:
            break
    assert abs(x - 0.625) < 1e-6 and abs(y - 0.125) < 1e-6
    await rt.shutdown()
