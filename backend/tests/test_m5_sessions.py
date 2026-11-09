"""Milestone 5 (D): research sessions, safe stop, export bundle, reproduction, deletion.

The data is SYNTHETIC (tests/feature_source.py): the point is that every control performs the
real operation end to end, and that an exported bundle reproduces the session's evaluation.
"""

from __future__ import annotations

import io
import json
import logging
import time
import zipfile
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

pytest.importorskip("scipy")

from concord.reproduce import reproduce
from concord.server import create_app

from .conftest import make_settings
from .feature_source import FeatureSourceAdapter, feature_descriptor
from .helpers import assert_mode

OPERATOR = "Dr Example Person"
NOTES = "Participant P-07 reported fatigue after block 2"


def wait_until(cond: Callable[[], bool], timeout: float = 20.0) -> None:
    deadline = time.monotonic() + timeout
    while not cond():
        if time.monotonic() > deadline:
            raise AssertionError("condition not met within timeout")
        time.sleep(0.02)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    app = create_app(make_settings(tmp_path))
    app.state.services.runtime.registry.register(
        feature_descriptor(), lambda: FeatureSourceAdapter(speed=50.0)
    )
    with TestClient(app) as c:
        yield c


def ok(r: Any) -> Any:
    assert r.status_code == 200, r.text
    return r.json()


def _record(client: TestClient, name: str, bins: int) -> None:
    """Record until the pipeline has taken ``bins`` inputs. Then pause the source and let the
    pipeline finish its queue before stopping, so every recorded feature bin has its decoder
    output in the file however far decoding lagged (the test source replays at 50x; a slow
    computer, such as the Windows CI runner, falls hundreds of bins behind)."""
    svc = client.app.state.services  # type: ignore[attr-defined]
    ok(client.post("/api/v1/recordings/start", json={"name": name, "exclude_raw": True}))
    start = svc.runtime.pipeline.counters["inputs"]
    wait_until(lambda: svc.runtime.pipeline.counters["inputs"] - start >= bins)
    ok(client.post("/api/v1/runtime/pause"))
    wait_until(lambda: svc.runtime.pipeline.status().counters["queue_depth"] == 0)
    ok(client.post("/api/v1/recordings/stop"))
    ok(client.post("/api/v1/runtime/resume"))


def _run_session(client: TestClient) -> tuple[str, str]:
    """A whole session through the REST API: connect, record, calibrate, decode, safe stop."""
    s = ok(
        client.post(
            "/api/v1/sessions", json={"name": "pilot 1", "operator": OPERATOR, "notes": NOTES}
        )
    )
    sid = s["id"]
    assert s["status"] == "active" and s["operator"] == OPERATOR
    ok(client.post("/api/v1/runtime/connect", json={"device_id": "test-features"}))
    ok(
        client.post(
            "/api/v1/pipeline/start", json={"processing": {"preset": "features_passthrough"}}
        )
    )
    _record(client, "cal-1", 900)
    cal = ok(client.post("/api/v1/calibration/train", json={"recordings": ["cal-1"]}))
    model_id = cal["model"]["model_id"]
    assert cal["report"]["r2"] > 0.3 > cal["report"]["control_mean_predictor_r2"]  # synthetic
    ok(client.post("/api/v1/pipeline/stop"))
    ok(
        client.post(
            "/api/v1/pipeline/start",
            json={"processing": {"preset": "features_passthrough"}, "model_id": model_id},
        )
    )
    _record(client, "dec-1", 300)
    ok(client.post("/api/v1/recordings/start", json={"name": "left-open", "exclude_raw": True}))
    return sid, model_id


def test_session_safe_stop_export_and_reproduce(
    client: TestClient, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    sid, model_id = _run_session(client)
    r = client.post("/api/v1/sessions", json={"name": "second"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "invalid_state"

    # safe stop: recording closed, decoding stopped, source disconnected, control already off
    st = ok(client.post("/api/v1/safe-stop", json={}))
    steps = {x["step"]: x for x in st["steps"]}
    assert [x["step"] for x in st["steps"]] == ["command_output", "recording", "decoding", "source"]
    assert steps["recording"]["done"] and "left-open" in steps["recording"]["detail"]
    assert steps["decoding"]["done"] and steps["source"]["done"] and st["ok"]
    assert not steps["command_output"]["done"]
    rt = ok(client.get("/api/v1/runtime"))
    assert rt["state"] == "idle" and rt["recording"] is None
    assert not ok(client.get("/api/v1/pipeline"))["running"]

    detail = ok(client.get(f"/api/v1/sessions/{sid}"))
    assert detail["session"]["recordings"] == ["cal-1", "dec-1", "left-open"]
    assert detail["session"]["models"] == [model_id]
    kinds = [e["kind"] for e in detail["log"]]
    for k in (
        "session_created",
        "operator_action",
        "device_status",
        "calibration",
        "recording_started",
        "safe_stop",
    ):
        assert k in kinds, k
    actions = [e.get("action") for e in detail["log"] if e["kind"] == "operator_action"]
    assert "connect" in actions and actions.count("pipeline_start") == 2

    # export, recordings included (explicit)
    info = ok(client.post(f"/api/v1/sessions/{sid}/export", json={"include_recordings": True}))
    assert info["included_recordings"] == ["cal-1", "dec-1", "left-open"] and info["models"] == [
        model_id
    ]
    folder = tmp_path / "data" / "sessions" / sid
    bundle = folder / "exports" / info["file"]
    assert_mode(bundle, 0o600)
    assert_mode(folder, 0o700)
    dl = client.get(f"/api/v1/sessions/{sid}/exports/{info['file']}")
    assert dl.status_code == 200 and dl.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(dl.content))
    names = set(zf.namelist())
    for required in (
        "manifest.json",
        "session.json",
        "session-log.jsonl",
        "environment.json",
        "REPRODUCE.md",
        f"models/{model_id}.json",
        f"models/{model_id}.manifest.json",
        f"calibration/{model_id}.json",
        "recordings/cal-1.concord.jsonl",
        "recordings/dec-1.concord.jsonl",
        "pipeline/01-start.json",
        "devices/test-features.json",
    ):
        assert required in names, required
    manifest = json.loads(zf.read("manifest.json"))
    assert manifest["format"] == "concord.session-bundle/1"
    assert {f["path"] for f in manifest["files"]} == names - {"manifest.json"}
    assert any(
        p["name"] == "concordos" and p["version"] for p in manifest["environment"]["packages"]
    )
    assert manifest["results"]["calibrations"][0]["model_id"] == model_id
    session_json = json.loads(zf.read("session.json"))
    assert session_json["operator"] is None and session_json["notes"] is None  # default: excluded
    assert "concord reproduce" in zf.read("REPRODUCE.md").decode()
    for name in names - {"session.json"}:
        text = zf.read(name).decode("utf-8", "replace")
        assert OPERATOR not in text and "P-07" not in text, name

    # the bundle reproduces the session's evaluation
    result = reproduce(bundle)
    assert result["status"] == "reproduced", result
    checks = {c["check"]: c for c in result["checks"]}
    assert checks["integrity"]["ok"]
    cal = checks["calibration"]
    assert cal["ok"] and cal["identical_model_id"] and cal["max_parameter_difference"] == 0.0
    decoded = [c for c in result["checks"] if c["check"] == "decoded_output"]
    # dec-1 is compared; the short left-open recording may hold only warm-up bins (skipped)
    by_rec = {c["recording"]: c for c in decoded}
    dec = by_rec["dec-1.concord.jsonl"]
    assert dec["ok"] is True, json.dumps(dec)  # plain text: counts are shown in full on failure
    assert all(c["ok"] is not False for c in decoded)
    assert sum(c["compared"] for c in decoded) > 200
    assert max(c["max_abs_diff"] for c in decoded) == 0.0

    # outputs may lag their inputs by any number of bins (a fast replay on a slow computer: the
    # Windows CI runner fell >256 bins behind and none were matched). Worst case: every output
    # after every input; each must still be matched by its timestamp (regression).
    from concord.reproduce import check_decoded_output

    root = tmp_path / "lagged"
    with zipfile.ZipFile(bundle) as zf2:
        zf2.extractall(root)
    rec_path = root / "recordings" / "dec-1.concord.jsonl"
    header, *lines = rec_path.read_text(encoding="utf-8").splitlines(keepends=True)
    outputs = [ln for ln in lines if '"intent.kinematics"' in ln]
    inputs = [ln for ln in lines if '"intent.kinematics"' not in ln]
    rec_path.write_text(header + "".join(inputs + outputs), encoding="utf-8", newline="")
    (lagged,) = [c for c in check_decoded_output(root, rec_path) if c["model_id"] == model_id]
    # same result as the unshuffled recording: outputs whose inputs came before the recording
    # started (a lagging decoder) are unmatched in both
    assert lagged["ok"] is True, json.dumps(lagged)
    assert lagged["unmatched"] == dec["unmatched"], json.dumps([lagged, dec])
    assert lagged["compared"] == dec["compared"], json.dumps([lagged, dec])

    # a tampered bundle fails integrity
    tampered = tmp_path / "tampered.zip"
    with zipfile.ZipFile(bundle) as src, zipfile.ZipFile(tampered, "w") as dst:
        for item in src.namelist():
            data = src.read(item)
            if item == f"models/{model_id}.json":
                data = data.replace(b'"alpha"', b'"alpha" ', 1)
            dst.writestr(item, data)
    bad = reproduce(tampered)
    assert bad["status"] == "failed" and not bad["checks"][0]["ok"]

    # without recordings: integrity only, the omitted recordings are listed with their hashes
    info2 = ok(client.post(f"/api/v1/sessions/{sid}/export", json={}))
    assert info2["included_recordings"] == [] and len(info2["omitted_recordings"]) == 3
    plain = folder / "exports" / info2["file"]
    with zipfile.ZipFile(plain) as zf2:
        omitted = json.loads(zf2.read("manifest.json"))["recordings"]["omitted"]
        assert all(len(o["sha256"]) == 64 for o in omitted)
        assert not [n for n in zf2.namelist() if n.startswith("recordings/")]
    assert reproduce(plain)["status"] == "nothing_to_reproduce"

    # personal data only on request
    info3 = ok(client.post(f"/api/v1/sessions/{sid}/export", json={"include_personal": True}))
    with zipfile.ZipFile(folder / "exports" / info3["file"]) as zf3:
        sj = json.loads(zf3.read("session.json"))
        assert sj["operator"] == OPERATOR and sj["notes"] == NOTES

    # the session log and the application log never contain operator name or notes
    log_text = (folder / "log.jsonl").read_text(encoding="utf-8")
    assert OPERATOR not in log_text and "P-07" not in log_text
    assert_mode(folder / "log.jsonl", 0o600)
    assert_mode(folder / "session.json", 0o600)
    assert not [r for r in caplog.records if OPERATOR in r.getMessage() or "P-07" in r.getMessage()]

    closed = ok(client.post(f"/api/v1/sessions/{sid}/close", json={"safe_stop": True}))
    assert closed["session"]["status"] == "closed" and closed["safe_stop"]["ok"]
    assert ok(client.get("/api/v1/sessions"))["active"] is None


def test_close_session_stops_everything_and_validation(client: TestClient) -> None:
    for bad in (
        {"name": ""},
        {"name": "x" * 81},
        {"name": "ok", "notes": "n" * 4001},
        {"name": "a", "extra": 1},
    ):
        assert client.post("/api/v1/sessions", json=bad).status_code == 422
    r = client.post("/api/v1/sessions", json={"name": "bell\x07"})
    assert r.status_code == 409
    sid = ok(client.post("/api/v1/sessions", json={"name": "close test"}))["id"]
    ok(client.post("/api/v1/runtime/connect", json={"device_id": "sim-a"}))
    ok(client.post("/api/v1/recordings/start", json={}))
    closed = ok(client.post(f"/api/v1/sessions/{sid}/close", json={}))
    steps = {x["step"]: x["done"] for x in closed["safe_stop"]["steps"]}
    assert steps == {"command_output": False, "recording": True, "decoding": False, "source": True}
    assert ok(client.get("/api/v1/runtime"))["state"] == "idle"
    assert client.post(f"/api/v1/sessions/{sid}/close", json={}).status_code == 409
    assert client.get("/api/v1/sessions/nope").status_code == 404
    assert client.get("/api/v1/sessions/20991231-000000-zzzz").status_code == 404
    assert client.get(f"/api/v1/sessions/{sid}/exports/../../x.zip").status_code == 404


def test_deletion_requires_confirmation_and_refuses_items_in_use(
    client: TestClient, tmp_path: Path
) -> None:
    ok(client.post("/api/v1/runtime/connect", json={"device_id": "sim-a"}))
    name = ok(client.post("/api/v1/recordings/start", json={"name": "rec-a"}))["name"]
    time.sleep(0.3)
    r = client.delete(f"/api/v1/recordings/{name}", params={"confirm": name})
    assert r.status_code == 409  # being written
    ok(client.post("/api/v1/recordings/stop"))
    r = client.delete(f"/api/v1/recordings/{name}")
    assert r.status_code == 400 and r.json()["error"]["code"] == "confirmation_required"
    assert (
        client.delete(f"/api/v1/recordings/{name}", params={"confirm": "other"}).status_code == 400
    )
    rec_dir = tmp_path / "data" / "recordings"
    assert (rec_dir / f"{name}.concord.jsonl").exists()
    gone = ok(client.delete(f"/api/v1/recordings/{name}", params={"confirm": name}))
    assert gone["bytes"] > 0 and not list(rec_dir.glob(f"{name}*"))
    assert client.delete("/api/v1/recordings/rec-a", params={"confirm": "rec-a"}).status_code == 404
    names = [x["name"] for x in ok(client.get("/api/v1/recordings"))]
    assert name not in names

    # models: refused while the running pipeline uses it
    models = tmp_path / "data" / "models"
    models.mkdir(parents=True, exist_ok=True)
    (models / "m-1.json").write_text("{}", encoding="utf-8")
    assert client.delete("/api/v1/models/m-1").status_code == 400
    assert client.delete("/api/v1/models/..%2Fx", params={"confirm": "../x"}).status_code in (
        404,
        405,
    )
    ok(client.delete("/api/v1/models/m-1", params={"confirm": "m-1"}))
    assert not (models / "m-1.json").exists()

    # sessions: refused while active; recordings optionally deleted with it
    sid = ok(client.post("/api/v1/sessions", json={"name": "to delete"}))["id"]
    ok(client.post("/api/v1/recordings/start", json={"name": "rec-b"}))
    time.sleep(0.2)
    ok(client.post("/api/v1/recordings/stop"))
    assert client.delete(f"/api/v1/sessions/{sid}", params={"confirm": sid}).status_code == 409
    ok(client.post(f"/api/v1/sessions/{sid}/close", json={"safe_stop": False}))
    assert client.delete(f"/api/v1/sessions/{sid}").status_code == 400
    d = ok(
        client.delete(f"/api/v1/sessions/{sid}", params={"confirm": sid, "delete_recordings": True})
    )
    assert d["also_deleted"] == ["rec-b"] and not (tmp_path / "data" / "sessions" / sid).exists()
    storage = ok(client.get("/api/v1/storage"))
    assert storage["usage"]["recordings"]["count"] == 0
    assert set(storage["retention"]) == {
        "recordings_days",
        "sessions_days",
        "exports_days",
        "models_days",
    }


def test_session_left_active_by_a_crash_is_marked_interrupted(tmp_path: Path) -> None:
    from concord.runtime.sessions import SessionManager

    sm = SessionManager(tmp_path / "data" / "sessions")
    sid = sm.create("crashed").id  # never closed: as if the process died
    with TestClient(create_app(make_settings(tmp_path))) as c:
        st = ok(c.get("/api/v1/sessions"))
        assert st["active"] is None
        s = next(x for x in st["sessions"] if x["id"] == sid)
        assert s["status"] == "interrupted" and "stopped" in s["end_reason"]
        assert ok(c.get("/api/v1/storage"))["interrupted_sessions"] == [sid]


def test_clean_server_stop_closes_the_active_session(tmp_path: Path) -> None:
    with TestClient(create_app(make_settings(tmp_path))) as c:
        sid = ok(c.post("/api/v1/sessions", json={"name": "stopped cleanly"}))["id"]
    with TestClient(create_app(make_settings(tmp_path))) as c:
        s = ok(c.get(f"/api/v1/sessions/{sid}"))["session"]
        assert s["status"] == "closed" and "stopped" in s["end_reason"]
