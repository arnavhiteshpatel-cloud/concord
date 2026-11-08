"""Clean-room lab acceptance test: an outside lab, approximated, from built wheels.

Extends ``scripts/dist_check.py`` (same helpers, same fresh-virtualenv approach). Only
documented commands and the documented REST API (what the console calls) are used —
docs/LAB_SETUP.md lists them. Steps:

 1. build wheels (the console staged into the brainos wheel when it can be built);
 2. fresh venv: ``pip install "brainos[lab]"``; ``brainos version``; ``brainos doctor``;
 3. ``brainos config init``, set the data directory and port in the config file;
    ``brainos start --no-browser``; ``brainos status``; the console page is served;
 4. a research session;
 5. an external protocol source in a separate process: the LSL synthetic ephys publisher
    (declared synthetic) -> discovery -> spike-band pipeline -> calibration recording ->
    calibrate -> decode with the model + command output on -> recording of decoder output;
 6. an SDK-only application (its own venv with only ``brainos``) asks for pointer commands,
    is authorized by the operator, and collects a result;
 7. a known recording: FALCON H1 (DANDI 000954) fetched with ``brainos dataset`` (pinned
    SHA-256) and streamed over LSL by a separate process (declared prerecorded) ->
    passthrough -> record -> calibrate; plus the file as offline replay. Skipped, with the
    reason printed, if the network does not allow the download;
 8. safe stop & disconnect; export the session bundle (recordings included);
 9. in another fresh venv, ``brainos reproduce <bundle>`` re-runs the evaluation and must
    reproduce it;
10. ``brainos stop``; ``brainos status`` reports it stopped.

Synthetic data is synthetic; FALCON H1 is real recorded human data streamed as prerecorded.
Nothing here is hardware or human validation (docs/VALIDATION_LEVELS.md).

Usage:  python scripts/lab_acceptance.py [--keep] [--skip-dataset] [--report PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dist_check as dc

ROOT = dc.ROOT
STEPS: list[dict[str, Any]] = []
APP_ID = "lab-acceptance-app"

APP = r"""
import asyncio, json, math, sys
from brainos.sdk import EventStream, NegotiationUpdate, is_event

async def main(base, n):
    statuses, got = [], []
    async with await EventStream.connect(app_id="lab-acceptance-app", app_name="Lab acceptance app",
                                         required=["pointer_intent"], base_url=base) as s:
        async def consume():
            async for item in s:
                if isinstance(item, NegotiationUpdate):
                    statuses.append(str(item.negotiation.status.value))
                elif is_event(item) and item.event_type.value == "intent.pointer":
                    got.append(item)
                    if len(got) >= n:
                        return
        await asyncio.wait_for(consume(), 180)
    p = got[-1].provenance
    speeds = [math.hypot(e.payload.vx, e.payload.vy) for e in got]
    print(json.dumps({"pointer_commands": len(got), "provenance": p.kind.value,
                      "model_id": p.model_id, "synthetic": p.synthetic,
                      "statuses_seen": sorted(set(statuses)),
                      "mean_speed": sum(speeds) / len(speeds)}))

asyncio.run(main(sys.argv[1], int(sys.argv[2])))
"""


def step(name: str, detail: Any, ok: bool | None = True) -> None:
    STEPS.append({"step": name, "ok": ok, "detail": detail})
    mark = {True: "ok  ", False: "FAIL", None: "skip"}[ok]
    print(f"[{mark}] {name}: {detail}", flush=True)


def wait(cond: Any, timeout: float, what: str, interval: float = 0.25) -> Any:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = cond()
        if value:
            return value
        time.sleep(interval)
    raise SystemExit(f"FAILED: timed out after {timeout:.0f} s waiting for {what}")


class Lab:
    def __init__(self, tmp: Path, py: Path, env: dict[str, str], port: int) -> None:
        self.tmp, self.py, self.env, self.port = tmp, py, env, port
        self.base = f"http://127.0.0.1:{port}"
        self.bin = py.parent
        self.children: list[subprocess.Popen[str]] = []

    def brainos(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        cmd = [str(self.bin / "brainos"), *args]
        print("$ brainos", " ".join(args), flush=True)
        r = subprocess.run(cmd, env=self.env, text=True, capture_output=True, timeout=600)
        if check and r.returncode != 0:
            print(r.stdout[-3000:], r.stderr[-3000:], sep="\n")
            raise SystemExit(f"FAILED: brainos {' '.join(args)} (exit {r.returncode})")
        return r

    def api(self, method: str, path: str, body: Any = None) -> Any:
        # calibration and export take seconds on an idle machine, much longer on a busy one
        slow = path.startswith("/calibration/") or path.endswith("/export")
        return dc.http(method, self.base + "/api/v1" + path, body, timeout=900 if slow else 60)

    def publisher(self, *args: str) -> subprocess.Popen[str]:
        log = (self.tmp / f"publisher-{len(self.children)}.log").open("w")
        p = subprocess.Popen(
            [str(self.py), "-m", "brainos.testing.publish", *args],
            env=self.env,
            text=True,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        self.children.append(p)
        return p

    def lsl_streams(self, source_ids: list[str]) -> dict[str, str]:
        """Discover until every source id is visible; returns source_id -> stream key."""

        def found() -> dict[str, str] | None:
            d = self.api("POST", "/sources/lsl/discover", {"wait_s": 1.5})
            keys = {s["source_id"]: s["key"] for s in d["streams"] if s.get("source_id")}
            return keys if all(sid in keys for sid in source_ids) else None

        keys: dict[str, str] = wait(found, 60, f"LSL streams {source_ids}", interval=0.5)
        return keys

    def counter(self, name: str) -> int:
        return int(self.api("GET", "/pipeline")["counters"].get(name, 0))

    def record(self, name: str, counter: str, n: int, timeout: float = 240) -> dict[str, Any]:
        self.api("POST", "/recordings/start", {"name": name, "exclude_raw": True})
        start = self.counter(counter)
        wait(lambda: self.counter(counter) - start >= n, timeout, f"{n} {counter} into {name}")
        info: dict[str, Any] = self.api("POST", "/recordings/stop")
        return info


def build_wheels(dist: Path) -> str:
    console = "not staged (npm unavailable): the wheel serves the API only"
    stage = [sys.executable, str(ROOT / "packaging" / "stage_console.py")]
    if (ROOT / "frontend" / "dist" / "index.html").is_file():
        dc.run(stage)
        console = "staged from frontend/dist"
    elif shutil.which("npm"):
        dc.run([*stage, "--build"])
        console = "built with npm and staged"
    dc.build(dist)
    return console


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--keep", action="store_true", help="keep the temporary directory")
    ap.add_argument("--skip-dataset", action="store_true", help="skip the FALCON H1 part")
    ap.add_argument("--report", type=Path, default=ROOT / "reports" / "lab-acceptance.json")
    args = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="brainos-lab-"))
    dist = tmp / "dist"
    print(f"workdir {tmp}", flush=True)
    lab: Lab | None = None
    ok = False
    t0 = time.monotonic()
    try:
        # 1. wheels -----------------------------------------------------------------------
        console = build_wheels(dist)
        step("wheels", f"{sorted(p.name for p in dist.glob('*.whl'))}; console {console}")

        # 2. fresh lab venv ---------------------------------------------------------------
        py = dc.venv(tmp / "lab")
        dc.install(py, "brainos[lab]", find_links=dist)
        port = dc.free_port()
        cfg = tmp / "config" / "config.toml"
        env = {k: v for k, v in os.environ.items() if not k.startswith("BRAINOS_")}
        env["BRAINOS_CONFIG"] = str(cfg)
        lab = Lab(tmp, py, env, port)
        step(
            "install",
            'pip install "brainos[lab]" from wheels: ' + lab.brainos("version").stdout.strip(),
        )
        data = tmp / "lab-data"
        r = lab.brainos("doctor", "--json", str(tmp / "doctor.json"), "--data-dir", str(data))
        rep = json.loads((tmp / "doctor.json").read_text())
        checks = {c["id"]: c["status"] for c in rep["checks"]}
        assert all(checks[c] == "ok" for c in ("dsp", "nwb", "lsl", "zmq", "server_extra")), checks
        step(
            "doctor",
            f"exit {r.returncode}; {rep['summary']}; no neural/personal data by construction",
        )

        # 3. config + start ---------------------------------------------------------------
        lab.brainos("config", "init")
        text = cfg.read_text().replace("port = 8000", f"port = {port}")
        text = text.replace("open_browser = true", "open_browser = false")
        text = re.sub(r"^# data_dir = .*$", f'data_dir = "{data}"', text, count=1, flags=re.M)
        cfg.write_text(text)
        shown = json.loads(lab.brainos("config", "show").stdout)
        assert (
            shown["port"] == port
            and shown["data_dir"] == str(data)
            and shown["host"] == "127.0.0.1"
        ), shown
        out = lab.brainos("start", "--no-browser").stdout
        assert f"is running: {lab.base}" in out, out
        st = json.loads(lab.brainos("status", "--json", check=False).stdout)
        assert st["running"], st
        page = dc.http_text(lab.base + "/")
        served = "console served" if "<title>" in page else "API only"
        step(
            "start",
            f"brainos start -> {lab.base} (pid {st['pid']}); {served}; config file mode "
            f"{oct(cfg.stat().st_mode & 0o777)}; data dir mode {oct(data.stat().st_mode & 0o777)}",
        )

        # 4. research session -------------------------------------------------------------
        session = lab.api(
            "POST",
            "/sessions",
            {
                "name": "lab acceptance",
                "operator": "Acceptance Script",
                "notes": "clean-room run; synthetic LSL + FALCON H1",
            },
        )
        step("session", f"research session {session['id']}")

        # 5. external protocol source: LSL synthetic ephys in a separate process ----------
        sid = f"lab-acceptance-ephys-{os.getpid()}"
        lab.publisher(
            "lsl-ephys", "--channels", "16", "--source-id", sid, "--seed", "7", "--seconds", "1200"
        )
        keys = lab.lsl_streams([sid, sid + "-behavior"])
        dev = lab.api(
            "POST", "/sources/lsl", {"signal": keys[sid], "behavior": keys[sid + "-behavior"]}
        )
        lab.api("POST", "/runtime/connect", {"device_id": dev["device_id"]})
        lab.api("POST", "/pipeline/start", {"processing": {"preset": "spikeband_threshold"}})
        wait(
            lambda: lab.api("GET", "/pipeline")["warmup_remaining_s"] == 0, 30, "threshold warm-up"
        )
        cal = lab.record("lab-syn-cal", "features_out", 900)
        res = lab.api(
            "POST",
            "/calibration/train",
            {"recordings": ["lab-syn-cal"], "feature_source": "brainos.pipeline"},
        )
        syn_model, syn_rep = res["model"]["model_id"], res["report"]
        assert syn_rep["r2"] > syn_rep["control_mean_predictor_r2"], syn_rep
        control = syn_rep["control_mean_predictor_r2"]
        step(
            "external LSL source (synthetic, separate process)",
            f"{dev['device_id']} -> spikeband -> {cal['events']} events recorded -> model "
            f"{syn_model}: held-out R² {syn_rep['r2']:.3f} vs mean-predictor control "
            f"{control:.3f} (synthetic data, cosine-tuned by construction)",
        )

        # 6. decode + SDK-only app, authorized by the operator ----------------------------
        lab.api("POST", "/pipeline/stop")
        lab.api(
            "POST",
            "/pipeline/start",
            {
                "processing": {"preset": "spikeband_threshold"},
                "model_id": syn_model,
                "router": {"enabled": True, "x_dim": "vx", "y_dim": "vy"},
            },
        )
        wait(
            lambda: lab.api("GET", "/pipeline")["warmup_remaining_s"] == 0, 30, "threshold warm-up"
        )
        lab.api("POST", "/recordings/start", {"name": "lab-syn-decode", "exclude_raw": True})
        app_py = dc.venv(tmp / "app")
        dc.install(app_py, "brainos", find_links=dist)
        (tmp / "app.py").write_text(APP)
        app = subprocess.Popen(
            [str(app_py), str(tmp / "app.py"), lab.base, "40"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        def waiting_for_authorization() -> bool:
            for a in lab.api("GET", "/control")["apps"]:
                if a["app_id"] == APP_ID:
                    return any(w["reason"] == "not_authorized" for w in a["waiting"])
            return False

        wait(waiting_for_authorization, 60, "the app to ask for pointer commands")
        time.sleep(1.0)  # the router produces commands; none may reach the app yet
        entry = next(a for a in lab.api("GET", "/control")["apps"] if a["app_id"] == APP_ID)
        assert entry["status"] != "active" and not entry["receiving"], entry
        produced_before = lab.counter("commands_out")
        assert produced_before > 0, "the router produced no commands"
        lab.api("POST", f"/control/apps/{APP_ID}/authorize", {"capabilities": ["pointer_intent"]})
        out_s, err_s = app.communicate(timeout=240)
        if app.returncode != 0:
            raise SystemExit(f"FAILED: SDK app exited {app.returncode}: {err_s[-2000:]}")
        result = json.loads(out_s.strip().splitlines()[-1])
        assert result["model_id"] == syn_model and result["provenance"] == "decoded_intent", result
        time.sleep(2.0)
        dec = lab.api("POST", "/recordings/stop")
        step(
            "SDK-only app (own venv: brainos only), authorized by the operator",
            f"{result['pointer_commands']} pointer commands from {result['model_id']} "
            f"({result['provenance']}, synthetic={result['synthetic']}); "
            f"before authorization it was {entry['status']} (not_authorized) while the router "
            f"had produced {produced_before} commands (default deny); decoder output recorded "
            f"({dec['events']} events)",
        )

        # 7. known recording: FALCON H1 ---------------------------------------------------
        if args.skip_dataset:
            step("known recording (FALCON H1)", "skipped: --skip-dataset", None)
        else:
            r = lab.brainos("dataset", check=False)
            if r.returncode != 0:
                why = (r.stderr or r.stdout).strip()[-300:]
                step("known recording (FALCON H1)", f"skipped: download not possible ({why})", None)
            else:
                lab.api("POST", "/runtime/disconnect")
                ddir = data / "datasets" / "dandi-000954"
                block = ddir / "sub-HumanPitt-held-in-calib_ses-19250108T111022.nwb"
                prefix = f"lab-falcon-{os.getpid()}"
                lab.publisher(
                    "falcon",
                    str(block),
                    "--speed",
                    "2",
                    "--source-prefix",
                    prefix,
                    "--seconds",
                    "600",
                )
                keys = lab.lsl_streams(
                    [prefix + "-counts", prefix + "-behavior", prefix + "-markers"]
                )
                dev = lab.api(
                    "POST",
                    "/sources/lsl",
                    {
                        "signal": keys[prefix + "-counts"],
                        "behavior": keys[prefix + "-behavior"],
                        "markers": keys[prefix + "-markers"],
                    },
                )
                snap = lab.api("POST", "/runtime/connect", {"device_id": dev["device_id"]})
                lab.api(
                    "POST", "/pipeline/start", {"processing": {"preset": "features_passthrough"}}
                )
                # 100 s of the ~136 s block (6786 bins of 20 ms; not looped: a repeated block
                # would put training data into the held-out tail). At 2x, discovery and
                # connecting cannot use up the rest of the block first.
                info = lab.record("lab-falcon-cal", "inputs", 5000)
                res = lab.api("POST", "/calibration/train", {"recordings": ["lab-falcon-cal"]})
                frep = res["report"]
                nwb = [d for d in lab.api("GET", "/devices") if d["device_id"].startswith("nwb:")]
                lab.api("POST", "/runtime/disconnect")
                # the file itself as offline replay; left connected for the safe stop below
                offline = (
                    lab.api("POST", "/runtime/connect", {"device_id": nwb[0]["device_id"]})
                    if nwb
                    else None
                )
                files = len(list(ddir.glob("*.nwb")))
                replay = "connected" if offline else "not listed"
                step(
                    "known recording (FALCON H1, real human data, declared prerecorded)",
                    f"`brainos dataset` verified {files} file(s) by SHA-256; streamed over LSL "
                    f"({snap['device']['kind']}) -> {info['events']} events recorded -> model "
                    f"{res['model']['model_id']}: held-out R² {frep['r2']:.3f} (within-block "
                    f"chronological split; mean-predictor control "
                    f"{frep['control_mean_predictor_r2']:.3f}); offline replay of {len(nwb)} "
                    f"file(s) {replay}",
                )

        # 8. safe stop + export -----------------------------------------------------------
        stop = lab.api("POST", "/safe-stop", {})
        assert lab.api("GET", "/runtime")["state"] == "idle"
        step("safe stop & disconnect", "; ".join(s["detail"] for s in stop["steps"]))
        exp = lab.api("POST", f"/sessions/{session['id']}/export", {"include_recordings": True})
        bundle = data / "sessions" / session["id"] / "exports" / exp["file"]
        shutil.copy(bundle, tmp / exp["file"])
        step(
            "export",
            f"{exp['file']}: {exp['files']} files, {exp['size_bytes']} bytes, recordings "
            f"{exp['included_recordings']}, models {exp['models']}, sha256 {exp['sha256'][:16]}…",
        )

        # 9. reproduce in a fresh venv ----------------------------------------------------
        ver = dc.venv(tmp / "verify")
        dc.install(ver, "brainos[dsp]", find_links=dist)
        r = subprocess.run(
            [
                str(ver.parent / "brainos"),
                "reproduce",
                str(tmp / exp["file"]),
                "--json",
                str(tmp / "reproduce.json"),
            ],
            text=True,
            capture_output=True,
            timeout=900,
        )
        print(r.stdout)
        rep = json.loads((tmp / "reproduce.json").read_text())
        assert r.returncode == 0 and rep["status"] == "reproduced", (r.returncode, r.stderr[-2000:])
        cals = [c for c in rep["checks"] if c["check"] == "calibration"]
        decs = [c for c in rep["checks"] if c["check"] == "decoded_output" and c.get("ok")]
        step(
            "reproduce (fresh venv: brainos[dsp])",
            f"{len(cals)} calibration(s) re-fitted (identical model ids: "
            f"{all(c.get('identical_model_id') for c in cals)}), "
            f"{sum(c['compared'] for c in decs)} decoded outputs recomputed exactly "
            f"(max diff {max((c['max_abs_diff'] for c in decs), default=None)})",
        )

        # 10. stop ------------------------------------------------------------------------
        out = lab.brainos("stop").stdout
        st = lab.brainos("status", check=False)
        assert st.returncode == 3, st.stdout
        step("stop", out.strip().splitlines()[-1])
        ok = True
        print("LAB ACCEPTANCE PASSED", flush=True)
        return 0
    except (AssertionError, KeyError, ValueError, OSError) as exc:
        step("unexpected", f"{type(exc).__name__}: {exc}", False)
        raise SystemExit(f"FAILED: {exc!r}") from exc
    finally:
        if lab is not None:
            for c in lab.children:
                c.terminate()
            if not ok:
                lab.brainos("stop", check=False)
                for log in [
                    *sorted(tmp.glob("publisher-*.log")),
                    tmp / "lab-data" / "logs" / "brainos.log",
                ]:
                    if log.exists():
                        print(
                            f"--- {log.name}\n"
                            + "\n".join(log.read_text(errors="replace").splitlines()[-30:])
                        )
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(
                {"ok": ok, "seconds": round(time.monotonic() - t0, 1), "steps": STEPS}, indent=1
            )
            + "\n"
        )
        if not args.keep:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
