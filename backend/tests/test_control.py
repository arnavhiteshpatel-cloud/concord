"""Milestone 4 control bridge: authorization (default deny), the command router's action set,
discrete rules with hysteresis, provenance checks and stale-command prevention.

Runtime tests use an in-process synthetic motor-imagery source (tests/mi_source.py, declared
synthetic) and an LDA classifier fitted on separately generated synthetic data.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

pytest.importorskip("scipy")

from pydantic import ValidationError

from brainos.adapters.base import EventDraft
from brainos.adapters.simulated import OperatorIntentSource
from brainos.contracts.capabilities import Capability, EventType
from brainos.contracts.events import Provenance, ProvenanceKind, Quality, parse_envelope
from brainos.contracts.protocol import AppInfo, AppStatus, ErrorCode, NegotiationResult
from brainos.decoding.lda import LDAClassifier
from brainos.runtime import DeviceRegistry, Recorder, Runtime, RuntimeCommandError
from brainos.runtime.bus import EventBus, Subscriber
from brainos.runtime.control import AuthorizationStore
from brainos.runtime.negotiation import negotiate
from brainos.runtime.pipeline import PipelineStartRequest
from brainos.runtime.router import CommandProvenanceError, CommandRouter, DiscreteRule, RouterSpec

from .conftest import subscribe
from .helpers import drain, events, scripted_descriptor, valid_event, wait_for
from .mi_source import CHANNELS, CLASS_NAMES, ORIGIN, MotorImageryAdapter, train_offline_lda

BAND = {"preset": "band_power", "band_low_hz": 8, "band_high_hz": 13, "bin_ms": 200}
SEL = Capability.SELECTION
TXT = Capability.TEXT_INTENT
PTR = Capability.POINTER_INTENT
COMMAND_TYPES = {"intent.pointer", "intent.selection", "intent.text"}


def _prov(
    kind: ProvenanceKind = ProvenanceKind.DECODED_INTENT, model: str | None = "m1"
) -> Provenance:
    return Provenance(
        kind=kind,
        adapter="brainos.pipeline@0.4.0",
        synthetic=True,
        model_id=model if kind is ProvenanceKind.DECODED_INTENT else None,
        origin="test",
    )


def _posterior(values: list[float], ts_ms: float, model: str = "m1") -> EventDraft:
    return EventDraft(
        EventType.INTENT_KINEMATICS,
        {
            "quantity": "class_posterior",
            "dims": ["rest", "left", "right"],
            "unit": "probability",
            "values": values,
            "space": "classes_cue",
        },
        Quality(score=1.0),
        _prov(model=model),
        round((ts_ms + 10_000) * 1e6),  # device clock (0 would mean "no device timestamp")
    )


# ------------------------------------------------------------------------- negotiation


def test_decoded_commands_need_authorization_native_ones_do_not() -> None:
    dev = scripted_descriptor(caps=[SEL, PTR, Capability.DEVICE_STATUS])
    # selection only from the router (decoded), pointer native (e.g. a simulator)
    n = negotiate([SEL], [PTR], dev, decoded_commands=frozenset({SEL}))
    assert n.status is AppStatus.SUSPENDED and n.granted == []
    assert [(r.capability, r.reason.value) for r in n.rejected] == [(SEL, "not_authorized")]
    n = negotiate([SEL], [PTR], dev, decoded_commands=frozenset({SEL}), authorized=frozenset({SEL}))
    assert n.status is AppStatus.ACTIVE and n.granted == [SEL, PTR]
    # an unsupported capability is reported as such, never as not_authorized
    n = negotiate([TXT], [], dev, decoded_commands=frozenset({SEL}))
    assert n.rejected[0].reason.value == "unsupported_by_device"
    # optional decoded command without authorization: app active, capability withheld
    n = negotiate([Capability.DEVICE_STATUS], [SEL], dev, decoded_commands=frozenset({SEL}))
    assert n.status is AppStatus.ACTIVE and n.granted == [Capability.DEVICE_STATUS]
    assert n.rejected[0].reason.value == "not_authorized" and not n.rejected[0].required


def test_not_authorized_rejection_round_trips_and_unknown_reasons_fail() -> None:
    n = negotiate([SEL], [], scripted_descriptor(caps=[SEL]), decoded_commands=frozenset({SEL}))
    assert NegotiationResult.model_validate_json(n.model_dump_json()) == n
    bad = json.loads(n.model_dump_json())
    bad["rejected"][0]["reason"] = "operator_says_no"
    with pytest.raises(ValidationError):
        NegotiationResult.model_validate(bad)


def test_authorization_store_rules() -> None:
    store = AuthorizationStore()
    with pytest.raises(ValueError, match="only command capabilities"):
        store.authorize("app", frozenset({Capability.RECORDING}))
    with pytest.raises(ValueError, match="no capabilities"):
        store.authorize("app", frozenset())
    store.authorize("app", frozenset({SEL}))
    store.authorize("app", frozenset({TXT}))  # additive
    assert store.authorized("app") == {SEL, TXT}
    assert store.revoke("app", frozenset({TXT})) == {TXT}
    assert store.authorized("app") == {SEL}
    assert store.revoke("app") == {SEL} and store.authorized("app") == frozenset()
    assert store.revoke("nobody") == frozenset()
    assert [e.kind for e in store.history] == ["authorized", "authorized", "revoked", "revoked"]


# ------------------------------------------------------------------------------ bus


def _env(event_type: str, kind: str, model: str | None = None) -> Any:
    ev = valid_event(event_type)
    ev["provenance"]["kind"] = kind
    ev["provenance"]["model_id"] = model
    return parse_envelope(ev)


def _sub(app_id: str, caps: list[Capability]) -> Subscriber:
    neg = NegotiationResult(device_id="d", status=AppStatus.ACTIVE, granted=caps, rejected=[])
    return Subscriber(f"con_{app_id}", AppInfo(id=app_id, name=app_id), caps, [], neg)


def test_bus_never_delivers_decoded_commands_to_unauthorized_subscribers() -> None:
    bus = EventBus()
    a, b = _sub("a", [SEL]), _sub("b", [SEL])
    b.authorized = frozenset({SEL})
    bus.add(a)
    bus.add(b)
    decoded = _env("intent.selection", "decoded_intent", "m1")
    simulated = _env("intent.selection", "simulated_intent")
    for env in (decoded, simulated):
        bus.publish(env, SEL, env.model_dump_json())
    got_a = [m["event"]["provenance"]["kind"] for m in drain(a)]
    got_b = [m["event"]["provenance"]["kind"] for m in drain(b)]
    assert got_a == ["simulated_intent"] and a.refused_commands == 1
    assert got_b == ["decoded_intent", "simulated_intent"]


async def test_revoking_one_capability_withdraws_only_its_queued_commands(runtime: Runtime) -> None:
    """Regression: a revoke must not withdraw commands of capabilities still authorized."""
    sub = subscribe(runtime, required=[], optional=[SEL, TXT], app_id="menu")
    runtime.authorize_app("menu", [SEL, TXT])
    sel = _env("intent.selection", "decoded_intent", "m1")
    txt = _env("intent.text", "decoded_intent", "m1")
    sub.offer_event(sel.model_dump_json(), SEL)
    sub.offer_event(txt.model_dump_json(), TXT)
    assert runtime.revoke_app("menu", [PTR]) == frozenset()  # never held: nothing withdrawn
    assert len(sub._events) == 2
    assert runtime.revoke_app("menu", [TXT]) == {TXT}
    assert [e[3] for e in sub._events] == [SEL] and sub.authorized == {SEL}
    assert runtime.stop_control("nothing running") is False  # idempotent, still withdraws
    assert len(sub._events) == 0


def test_purge_withdraws_queued_decoded_commands_and_keeps_delivery_seq_contiguous() -> None:
    bus = EventBus()
    sub = _sub("a", [SEL, Capability.TELEMETRY])
    sub.authorized = frozenset({SEL})
    bus.add(sub)
    tel = _env("telemetry.sample", "device_report")
    dec = _env("intent.selection", "decoded_intent", "m1")
    sim = _env("intent.selection", "simulated_intent")
    sub.offer_event("{}")  # delivery_seq 0, sent before the purge
    assert sub._events.popleft()[0] == 0
    for env, cap in (
        (tel, Capability.TELEMETRY),
        (dec, SEL),
        (sim, SEL),
        (dec, SEL),
        (tel, Capability.TELEMETRY),
    ):
        bus.publish(env, cap, env.model_dump_json())
    assert bus.purge_commands() == 2 and sub.purged_commands == 2
    msgs = drain(sub)
    assert [m["delivery_seq"] for m in msgs] == [1, 2, 3]
    assert [m["event"]["provenance"]["kind"] for m in msgs] == [
        "device_report",
        "simulated_intent",
        "device_report",
    ]
    sub.offer_event("y")
    assert sub._events[-1][0] == 4


# --------------------------------------------------------------------------- router


def test_router_accepts_only_the_running_decoders_output() -> None:
    spec = RouterSpec(
        enabled=True, discrete=[DiscreteRule(output="left", action="primary", hold_ms=0)]
    )
    r = CommandRouter(spec, model_id="m1", dims=["rest", "left", "right"], behavior_std=None)
    q = Quality(score=1.0)
    behavior = EventDraft(
        EventType.BEHAVIOR_SAMPLE,
        {
            "quantity": "cue_class",
            "dims": ["cue_class"],
            "unit": "class",
            "values": [1.0],
            "sample_index": 0,
        },
        q,
        _prov(ProvenanceKind.BEHAVIORAL_LABEL),
        0,
    )
    frame = EventDraft(
        EventType.RECORDING_FRAME,
        {"sample_rate_hz": 250.0, "channel_count": 1, "first_sample_index": 0, "samples": [[1.0]]},
        q,
        _prov(ProvenanceKind.RAW_SIGNAL),
        0,
    )
    features = EventDraft(
        EventType.FEATURES_VECTOR,
        {
            "feature": "log_band_power",
            "unit": "x",
            "bin_ms": 200,
            "bin_index": 0,
            "channel_count": 3,
            "values": [0.0, 1.0, 0.0],
        },
        q,
        _prov(ProvenanceKind.PROCESSED_FEATURE),
        0,
    )
    simulated = EventDraft(
        EventType.INTENT_KINEMATICS,
        {**_posterior([0, 1, 0], 0).payload},
        q,
        _prov(ProvenanceKind.SIMULATED_INTENT),
        0,
    )
    for draft in (
        behavior,
        frame,
        features,
        simulated,
        _posterior([0.0, 1.0, 0.0], 0, model="other"),
    ):
        with pytest.raises(CommandProvenanceError):
            r.route(draft)
    assert r.route(_posterior([0.0, 1.0, 0.0], 0))[0].event_type is EventType.INTENT_SELECTION


def _fire_times(rule: DiscreteRule, series: list[tuple[float, float]]) -> list[tuple[float, Any]]:
    r = CommandRouter(
        RouterSpec(enabled=True, discrete=[rule]),
        model_id="m1",
        dims=["rest", "left", "right"],
        behavior_std=None,
    )
    out = []
    for t, p in series:
        for d in r.route(_posterior([1 - p, p, 0.0], t)):
            out.append((t, d))
    return out


def test_discrete_rule_hold_refractory_and_hysteresis() -> None:
    rule = DiscreteRule(
        output="left", threshold=0.8, hold_ms=200, refractory_ms=1000, action="activate"
    )
    # 100 ms bins: above threshold from t=0 -> fires once the hold (200 ms) is met
    fired = _fire_times(rule, [(t, 0.9) for t in range(0, 3000, 100)])
    assert [t for t, _ in fired] == [200]  # stays high: no re-arm without release
    d = fired[0][1]
    assert d.payload == {"action": "activate", "confidence": 0.9}
    assert d.provenance.kind is ProvenanceKind.DECODED_INTENT and d.provenance.model_id == "m1"
    # noise around the threshold does not chatter: it must fall below release (0.65) first
    noisy = [(t, 0.85 if (t // 100) % 2 else 0.75) for t in range(0, 4000, 100)]
    assert len(_fire_times(rule.model_copy(update={"hold_ms": 0}), noisy)) == 1
    # release + refractory: re-fires only after dropping below 0.65 AND 1000 ms since the last
    series = [(0, 0.9), (100, 0.5), (200, 0.9), (1100, 0.9), (1200, 0.5), (1300, 0.95)]
    times = [t for t, _ in _fire_times(rule.model_copy(update={"hold_ms": 0}), series)]
    assert times == [0, 1100]  # 1300: high again but not released since 1200 -> 1200 was
    # a brief dip below threshold restarts the hold
    series = [(0, 0.9), (100, 0.9), (150, 0.7), (200, 0.9), (300, 0.9), (400, 0.9)]
    assert [t for t, _ in _fire_times(rule, series)] == [400]


def test_text_rule_and_confidence() -> None:
    rule = DiscreteRule(output="left", threshold=0.6, hold_ms=0, action="text", text="yes")
    ((_, d),) = _fire_times(rule, [(0, 0.7)])
    assert d.event_type is EventType.INTENT_TEXT
    assert d.payload == {"text": "yes", "mode": "word", "confidence": 0.7}
    rule = rule.model_copy(update={"text": "a"})
    assert _fire_times(rule, [(0, 0.7)])[0][1].payload["mode"] == "character"


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"output": "left", "action": "text"}, "needs 'text'"),
        ({"output": "left", "action": "primary", "text": "x"}, "only valid for action 'text'"),
        (
            {"output": "left", "action": "primary", "threshold": 0.5, "release": 0.6},
            "below threshold",
        ),
        ({"output": "left", "action": "primary", "threshold": 1.5}, "less than or equal"),
        ({"output": "left", "action": "jump"}, "Input should be"),
        ({"output": "", "action": "primary"}, "at least 1"),
    ],
)
def test_malformed_discrete_rules_are_refused(kwargs: dict[str, Any], match: str) -> None:
    with pytest.raises(ValidationError, match=match):
        DiscreteRule(**kwargs)


def test_malformed_router_specs_are_refused() -> None:
    with pytest.raises(ValidationError, match="both x_dim and y_dim"):
        RouterSpec(enabled=True, x_dim="tx")
    rule = {"output": "left", "action": "primary"}
    with pytest.raises(ValidationError, match="one discrete rule per output"):
        RouterSpec(enabled=True, discrete=[rule, {**rule, "action": "cancel"}])
    with pytest.raises(ValidationError):
        RouterSpec(enabled=True, stall_ms=10)
    with pytest.raises(ValidationError):
        RouterSpec.model_validate({"enabled": True, "x_dim": "a", "y_dim": "b", "extra": 1})


# ------------------------------------------------------------------ runtime (synthetic MI)


@pytest.fixture(scope="module")
def lda_model(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, LDAClassifier]:
    """An LDA trained on 240 s of separately generated synthetic data (seed 11)."""
    d = tmp_path_factory.mktemp("models")
    return d, train_offline_lda(d)


def _runtime(tmp_path: Path, models_dir: Path, **variants: dict[str, Any]) -> Runtime:
    reg = DeviceRegistry(OperatorIntentSource(), tmp_path / "rec", models_dir=models_dir, seed=1)
    for did, kw in variants.items():
        adapter_kw = {"device_id": did, **kw}
        reg.register(
            MotorImageryAdapter(**adapter_kw).descriptor,
            lambda k=adapter_kw: MotorImageryAdapter(**k),
        )
    return Runtime(reg, Recorder(tmp_path / "rec"), reconnect_backoff_s=(0.01, 0.02))


RULES = [
    {"output": "left", "action": "primary", "threshold": 0.7, "hold_ms": 200, "refractory_ms": 600},
    {
        "output": "right",
        "action": "activate",
        "threshold": 0.7,
        "hold_ms": 200,
        "refractory_ms": 600,
    },
]


def _commands(msgs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in events(msgs) if e["event_type"] in COMMAND_TYPES]


async def _start_decoding(rt: Runtime, model: LDAClassifier, **router: Any) -> None:
    rt.start_pipeline(
        PipelineStartRequest(
            processing=BAND,
            model_id=model.model_id,
            router=RouterSpec(enabled=True, discrete=RULES, **router),  # type: ignore[arg-type]
        )
    )


async def test_decoded_actions_reach_only_authorized_apps(
    tmp_path: Path, lda_model: tuple[Path, LDAClassifier]
) -> None:
    models_dir, model = lda_model
    rt = _runtime(tmp_path, models_dir, **{"test-mi": {"speed": 20.0, "seed": 3}})
    menu = subscribe(rt, required=[SEL], optional=[], app_id="menu")
    other = subscribe(rt, required=[SEL], optional=[], app_id="other")
    console = subscribe(rt, app_id="console")  # everything optional
    await rt.connect("test-mi")
    assert menu.negotiation.status is AppStatus.SUSPENDED
    assert menu.negotiation.rejected[0].reason.value == "unsupported_by_device"
    # a decoder without the router: posteriors flow, still no commands
    rt.start_pipeline(PipelineStartRequest(processing=BAND, model_id=model.model_id))
    await wait_for(lambda: rt.pipeline.counters["decoded_out"] >= 20, timeout=15)
    st = rt.pipeline.status()
    assert st.decoder is not None and st.decoder["outputs"]["classes"] == CLASS_NAMES
    assert menu.negotiation.rejected[0].reason.value == "unsupported_by_device"
    # router on: selection exists now but nobody is authorized
    rt.set_router(RouterSpec(enabled=True, discrete=RULES))  # type: ignore[arg-type]
    assert rt.pipeline.command_capabilities == {SEL}  # no text rule -> no text_intent
    for sub in (menu, other):
        assert sub.negotiation.status is AppStatus.SUSPENDED
        assert [r.reason.value for r in sub.negotiation.rejected] == ["not_authorized"]
    assert SEL not in console.negotiation.granted
    await wait_for(lambda: rt.pipeline.counters["selections_out"] >= 3, timeout=20)
    assert _commands(drain(menu) + drain(other) + drain(console)) == []
    # authorize one app: it alone receives decoded actions
    rt.authorize_app("menu", [SEL])
    assert menu.negotiation.status is AppStatus.ACTIVE and menu.authorized == {SEL}
    assert other.negotiation.status is AppStatus.SUSPENDED
    n0 = rt.pipeline.counters["selections_out"]
    await wait_for(lambda: rt.pipeline.counters["selections_out"] >= n0 + 3, timeout=20)
    got = _commands(drain(menu))
    assert len(got) >= 3 and _commands(drain(other)) == [] and _commands(drain(console)) == []
    for e in got:
        assert e["event_type"] == "intent.selection"
        assert e["payload"]["action"] in ("primary", "activate")
        assert 0.7 <= e["payload"]["confidence"] <= 1.0
        p = e["provenance"]
        assert p["kind"] == "decoded_intent" and p["model_id"] == model.model_id and p["synthetic"]
    await rt.shutdown()


async def test_every_stop_path_turns_command_output_off(
    tmp_path: Path, lda_model: tuple[Path, LDAClassifier]
) -> None:
    models_dir, model = lda_model
    rt = _runtime(
        tmp_path,
        models_dir,
        **{"test-mi": {"speed": 20.0, "seed": 4}, "test-mi-2": {"speed": 20.0, "seed": 5}},
    )
    app = subscribe(rt, required=[SEL], optional=[], app_id="menu")
    rt.authorize_app("menu", [SEL])  # before any source: authorizations are by app id

    async def running(device: str | None = None) -> None:
        if device is not None:
            if rt.device is None:
                await rt.connect(device)
            else:
                await rt.switch(device)
        await _start_decoding(rt, model)
        assert app.negotiation.status is AppStatus.ACTIVE
        n0 = rt.pipeline.counters["selections_out"]
        await wait_for(lambda: rt.pipeline.counters["selections_out"] > n0, timeout=20)

    async def assert_off(reason: str) -> None:
        assert not rt.pipeline.router_on
        assert app.negotiation.status is AppStatus.SUSPENDED
        stop = rt.pipeline.last_router_stop
        assert stop is not None and reason in stop.reason, (reason, stop)
        drain(app)
        await asyncio.sleep(0.4)
        assert _commands(drain(app)) == []  # nothing after the stop

    await running("test-mi")
    assert rt.stop_control("operator pressed Stop")
    await assert_off("operator pressed Stop")
    assert not rt.stop_control("again")  # idempotent

    await running()
    rt.revoke_app("menu")
    assert app.negotiation.rejected[0].reason.value == "not_authorized"
    drain(app)
    await asyncio.sleep(0.4)
    assert _commands(drain(app)) == []
    rt.authorize_app("menu", [SEL])

    await running()
    await rt.pause()
    await assert_off("source paused")
    await rt.resume()

    await running()
    rt.set_router(RouterSpec(enabled=False, discrete=RULES))  # type: ignore[arg-type]
    await assert_off("disabled by operator")

    await running()  # restart (same decoder): the previous router state is not inherited
    rt.start_pipeline(PipelineStartRequest(processing=BAND, model_id=model.model_id))
    await assert_off("pipeline restarted")

    await running()  # decoder change -> restart without a router
    rt.start_pipeline(PipelineStartRequest(processing=BAND))
    await assert_off("pipeline restarted")

    await running()
    rt.stop_pipeline()
    await assert_off("stopped by operator")

    await running()  # input stall: the source stops delivering while the link stays up
    adapter = rt.adapter
    assert isinstance(adapter, MotorImageryAdapter)
    limit = rt.pipeline.stall_limit_ms()
    assert limit == 1000.0  # max(stall_ms 1000, 3 x 200 ms bins)
    adapter.stalled = True
    await wait_for(lambda: not rt.pipeline.router_on, timeout=limit / 1000 + 1.5)
    await assert_off("input stalled")
    assert rt.pipeline.counters["router_stalls"] == 1
    adapter.stalled = False

    await running()  # link loss: off at once, and still off after the reconnect succeeds
    adapter.fail_reads = 1
    await wait_for(lambda: not rt.pipeline.router_on, timeout=5)
    await wait_for(lambda: rt.diagnostics.reconnect_successes >= 1, timeout=5)
    await assert_off("source link lost")
    assert rt.pipeline.running  # the pipeline keeps decoding; only command output stopped

    await running()  # source switch: router always off after a source change
    await rt.switch("test-mi-2")
    await assert_off("device disconnected")
    assert rt.authorizations.authorized("menu") == {SEL}  # authorizations survive the switch

    await running()
    await rt.disconnect()
    assert not rt.pipeline.router_on and app.negotiation.status is AppStatus.NO_DEVICE
    await rt.shutdown()


async def test_stall_limit_respects_long_bins_and_a_short_setting(
    tmp_path: Path, lda_model: tuple[Path, LDAClassifier]
) -> None:
    models_dir, model = lda_model
    rt = _runtime(tmp_path, models_dir, **{"test-mi": {"speed": 20.0, "seed": 6}})
    await rt.connect("test-mi")
    await _start_decoding(rt, model, stall_ms=100)
    assert rt.pipeline.stall_limit_ms() == 600.0  # never below 3 bins
    # not armed before the first decoder input since enabling
    assert not rt.pipeline.check_stall(now=1e12)
    await wait_for(lambda: rt.pipeline.counters["decoded_out"] >= 2, timeout=10)
    assert rt.pipeline.check_stall(now=1e12)
    assert "input stalled" in (
        rt.pipeline.last_router_stop.reason if rt.pipeline.last_router_stop else ""
    )
    await rt.shutdown()


async def test_router_requests_that_the_decoder_cannot_serve_are_refused(
    tmp_path: Path, lda_model: tuple[Path, LDAClassifier]
) -> None:
    models_dir, model = lda_model
    rt = _runtime(tmp_path, models_dir, **{"test-mi": {"speed": 20.0}})
    await rt.connect("test-mi")
    rt.start_pipeline(PipelineStartRequest(processing=BAND, model_id=model.model_id))
    cases: list[tuple[dict[str, Any], ErrorCode, str]] = [
        ({"x_dim": "left", "y_dim": "right"}, ErrorCode.INCOMPATIBLE_DECODER, "classifier"),
        (
            {"discrete": [{"output": "feet", "action": "primary"}]},
            ErrorCode.INCOMPATIBLE_DECODER,
            "no class 'feet'",
        ),
        ({}, ErrorCode.CAPABILITY_UNSUPPORTED, "nothing to emit"),
    ]
    for spec, code, msg in cases:
        with pytest.raises(RuntimeCommandError) as exc:
            rt.set_router(RouterSpec.model_validate({"enabled": True, **spec}))
        assert exc.value.code is code and msg in exc.value.message
    assert not rt.pipeline.router_on and rt.pipeline.command_capabilities == frozenset()
    # only what the rules provide is advertised: a text rule alone -> text_intent, no selection
    rt.set_router(
        RouterSpec.model_validate(
            {"enabled": True, "discrete": [{"output": "right", "action": "text", "text": "yes"}]}
        )
    )
    assert rt.pipeline.command_capabilities == {TXT}
    caps = {c.capability: c.params for c in rt.pipeline.capability_descriptors()}
    assert caps[TXT]["text_modes"] == ["word"] and caps[TXT]["model_id"] == model.model_id
    rt.set_router(RouterSpec.model_validate({"enabled": True, "discrete": RULES}))
    caps = {c.capability: c.params for c in rt.pipeline.capability_descriptors()}
    assert caps[SEL]["actions"] == ["activate", "primary"] and TXT not in caps
    # discrete rules on a continuous decoder are refused (needs a classifier)
    rt.stop_pipeline()
    with pytest.raises(RuntimeCommandError) as exc:
        rt.start_pipeline(
            PipelineStartRequest(processing=BAND, router=RouterSpec(enabled=True, discrete=RULES))  # type: ignore[arg-type]
        )
    assert "needs a loaded decoder" in exc.value.message
    await rt.shutdown()


async def test_raw_only_and_label_only_sources_never_yield_commands(
    tmp_path: Path, lda_model: tuple[Path, LDAClassifier]
) -> None:
    models_dir, _ = lda_model
    rt = _runtime(
        tmp_path,
        models_dir,
        **{
            "test-mi-raw": {"speed": 20.0, "behavior": False},
            "test-mi-labels": {"speed": 20.0, "signal": False},
        },
    )
    app = subscribe(rt, required=[SEL], optional=[PTR, TXT], app_id="menu")
    watcher = subscribe(rt, app_id="watcher")  # all capabilities optional
    rt.authorize_app("menu", [SEL, PTR, TXT])
    rt.authorize_app("watcher", [SEL, PTR, TXT])
    # raw signal only: features flow through the pipeline, never commands
    await rt.connect("test-mi-raw")
    rt.start_pipeline(PipelineStartRequest(processing=BAND))
    await wait_for(lambda: rt.pipeline.counters["features_out"] >= 20, timeout=15)
    with pytest.raises(RuntimeCommandError, match="needs a loaded decoder"):
        rt.set_router(RouterSpec(enabled=True, discrete=RULES))  # type: ignore[arg-type]
    # behavior labels + markers only: nothing to decode, no pipeline, no commands
    await rt.switch("test-mi-labels")
    with pytest.raises(RuntimeCommandError) as exc:
        rt.start_pipeline(PipelineStartRequest(processing=BAND))
    assert exc.value.code is ErrorCode.CAPABILITY_UNSUPPORTED
    await wait_for(lambda: rt.diagnostics.totals["behavior.sample"] >= 50, timeout=10)
    assert app.negotiation.status is AppStatus.SUSPENDED
    msgs = drain(app) + drain(watcher)
    assert events(msgs, "behavior.sample")  # the labels themselves are delivered as labels
    assert _commands(msgs) == []
    assert all(
        e["provenance"]["kind"]
        in ("behavioral_label", "runtime", "raw_signal", "processed_feature")
        for e in events(msgs)
    )
    await rt.shutdown()


async def test_classifier_calibrated_from_a_recording_runs_in_the_pipeline(
    tmp_path: Path,
) -> None:
    """Record the synthetic source (band power through the pipeline + cue labels), calibrate
    an LDA from the recording, load it back: synthetic data, labelled as such."""
    from brainos.decoding.calibrate import calibrate_classifier, classifier_report_markdown

    models_dir = tmp_path / "models"
    rt = _runtime(tmp_path, models_dir, **{"test-mi": {"speed": 40.0, "seed": 21}})
    await rt.connect("test-mi")
    rt.start_pipeline(PipelineStartRequest(processing=BAND))
    name = rt.start_recording("mi-cal", exclude_raw=True)
    await wait_for(lambda: rt.pipeline.counters["features_out"] >= 1500, timeout=60)  # 300 s
    rt.stop_recording()
    await rt.disconnect()
    path = tmp_path / "rec" / f"{name}.brainos.jsonl"
    model, report = calibrate_classifier(
        [path], models_dir=models_dir, feature_source="brainos.pipeline"
    )
    assert report["synthetic_source"] is True and report["classes"] == CLASS_NAMES  # declared names
    assert model.source["identity"] == ORIGIN and model.input["channel_labels"] == list(CHANNELS)
    k = len(CLASS_NAMES)
    assert report["chance_balanced_accuracy"] == pytest.approx(1 / k)
    assert np.asarray(report["confusion"]).sum() == report["samples"]
    # the synthetic ERD is decodable well above chance, and the shift control is not
    assert report["balanced_accuracy"] > 0.5
    assert report["control_time_shift_balanced_accuracy"] < 0.45
    assert report["beats_all_shifts"]
    md = classifier_report_markdown(report)
    assert "**synthetic data**" in md and "Confusion matrix" in md
    print("\nSYNTHETIC LDA calibration report:\n" + md)  # numbers for docs (synthetic data)

    await rt.connect("test-mi")
    st = rt.start_pipeline(
        PipelineStartRequest(
            processing=BAND,
            model_id=model.model_id,
            router=RouterSpec(enabled=True, discrete=RULES),  # type: ignore[arg-type]
        )
    )
    assert (
        st.decoder is not None
        and st.decoder["held_out_balanced_accuracy"] == report["balanced_accuracy"]
    )
    rt.authorize_app("menu", [SEL])
    app = subscribe(rt, required=[SEL], optional=[], app_id="menu")
    await wait_for(lambda: rt.pipeline.counters["selections_out"] >= 2, timeout=20)
    await wait_for(lambda: len(_commands(list(_peek(app)))) >= 1, timeout=5)
    await rt.shutdown()


def _peek(sub: Subscriber) -> list[dict[str, Any]]:
    return [
        {"type": "event", "delivery_seq": d, "event": json.loads(ev)} for d, ev, *_ in sub._events
    ]
