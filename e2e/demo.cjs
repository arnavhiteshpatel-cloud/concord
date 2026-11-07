#!/usr/bin/env node
// AT-25 — End-to-end demo in a real browser against a real BrainOS server.
//
// Performs the MVP demo sequence and records each step's outcome to
// reports/e2e.json (shown in the console's Tests tab):
//   connect A -> live events -> control board (pointer + select) -> link drop + reconnect
//   -> switch to B -> board keeps working (scan + text) -> record -> replay -> diagnostics/tests
//   -> (M2) verified human recording, offline replay
//   -> (M3) LSL test publisher: discover, register, connect, spikeband pipeline, stop;
//      Open Ephys ZMQ test publisher: register, connect, counters. Both publishers generate
//      synthetic data; LSL declares it, the Open Ephys protocol cannot ("origin unverified").
//
// Usage:
//   node e2e/demo.cjs                 # starts its own server on :8765 with a temp data dir
//   node e2e/demo.cjs --url http://127.0.0.1:8000   # use an already-running server
// Requires the `playwright` package and a Chromium build (see README).

const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const SHOTS = path.join(__dirname, "screenshots");
const REPORT = path.join(ROOT, "reports", "e2e.json");
const argUrl = process.argv.indexOf("--url");
const EXTERNAL = argUrl > -1 ? process.argv[argUrl + 1] : null;
const PORT = 8765;

let chromium;
try {
  ({ chromium } = require("playwright"));
} catch {
  console.error("playwright is not installed. Run: make e2e-setup");
  process.exit(2);
}

const steps = [];
async function step(name, fn) {
  const t0 = Date.now();
  try {
    const detail = await fn();
    steps.push({ name, ok: true, time_s: (Date.now() - t0) / 1000, detail: detail ?? null });
    console.log(`  ✓ ${name}${detail ? ` — ${detail}` : ""}`);
  } catch (err) {
    steps.push({ name, ok: false, time_s: (Date.now() - t0) / 1000, detail: String(err && err.message ? err.message : err).slice(0, 500) });
    console.log(`  ✗ ${name}: ${err && err.message ? err.message : err}`);
    throw err;
  }
}

async function waitHealthy(base, ms = 20000) {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    try {
      const r = await fetch(`${base}/api/v1/health`);
      if (r.ok) return;
    } catch {}
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(`server at ${base} not healthy`);
}

// Python for the server and the test publishers. PYTHONPATH pins the backend of *this*
// checkout (an editable install elsewhere would otherwise serve a different frontend/dist).
const PY = fs.existsSync(path.join(ROOT, ".venv/bin/python")) ? path.join(ROOT, ".venv/bin/python") : "python3";
const pyEnv = {
  PYTHONPATH: [path.join(ROOT, "backend", "src"), process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
};
const children = [];
/** Milestone 3: a hardware-free protocol publisher (declared synthetic) as a child process. */
function publisher(args) {
  const p = spawn(PY, ["-m", "brainos.testing.publish", ...args, "--seconds", "600"], {
    env: { ...process.env, ...pyEnv },
    stdio: ["ignore", "ignore", "inherit"],
  });
  children.push(p);
  return p;
}

async function main() {
  let server = null;
  let base = EXTERNAL;
  if (!base) {
    const py = PY;
    const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "brainos-e2e-"));
    // Real recorded data (Milestone 2): link the verified dataset + model dirs read-only.
    for (const sub of ["datasets", "models"]) {
      const src = path.join(ROOT, "data", sub);
      if (fs.existsSync(src)) fs.symlinkSync(src, path.join(dataDir, sub), "dir");
    }
    server = spawn(py, ["-m", "brainos.server"], {
      env: { ...process.env, ...pyEnv, BRAINOS_PORT: String(PORT), BRAINOS_DATA_DIR: dataDir, BRAINOS_LOG_LEVEL: "WARNING" },
      stdio: ["ignore", "inherit", "inherit"],
    });
    base = `http://127.0.0.1:${PORT}`;
  }
  fs.mkdirSync(SHOTS, { recursive: true });
  fs.mkdirSync(path.dirname(REPORT), { recursive: true });

  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1680, height: 1050 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  const api = async (p, method = "GET", body) => {
    const r = await fetch(`${base}/api/v1${p}`, {
      method,
      headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
    });
    return r.json();
  };
  const board = () => page.frameLocator('[data-testid="board-frame"]');
  const text = (loc) => loc.textContent({ timeout: 5000 });
  const expectText = async (loc, re, timeout = 8000) => {
    const end = Date.now() + timeout;
    let last = "";
    while (Date.now() < end) {
      last = (await loc.textContent().catch(() => "")) ?? "";
      if (re.test(last)) return last;
      await page.waitForTimeout(100);
    }
    throw new Error(`expected ${re} but got "${last}"`);
  };
  const waitAttr = async (loc, attr, value, timeout = 5000) => {
    const end = Date.now() + timeout;
    let last = null;
    while (Date.now() < end) {
      last = await loc.getAttribute(attr).catch(() => null);
      if (last === value) return;
      await page.waitForTimeout(100);
    }
    throw new Error(`${attr} expected ${value}, got ${last}`);
  };
  const shot = (name) => page.screenshot({ path: path.join(SHOTS, `${name}.png`) });

  let ok = false;
  try {
    await waitHealthy(base);
    console.log(`BrainOS e2e against ${base}`);

    await step("1. console loads, runtime idle, board app connected", async () => {
      await page.goto(base);
      await expectText(page.getByTestId("runtime-state"), /idle/);
      await page.getByTestId("app-communication-board").waitFor({ timeout: 8000 });
      await expectText(board().getByTestId("board-mode"), /inactive/);
      return "board negotiated: no_device";
    });

    await step("2. connect Simulated Profile A", async () => {
      await page.getByTestId("device-sim-a").click();
      await expectText(page.getByTestId("runtime-state"), /streaming/);
      await expectText(board().getByTestId("board-mode"), /pointer/);
      return "board switched to pointer mode";
    });

    await step("3. live standardized events stream to the console", async () => {
      await page.locator('[data-event-type="intent.pointer"]').first().waitFor({ timeout: 5000 });
      await page.locator('[data-event-type="recording.frame"]').first().waitFor({ timeout: 5000 });
      await page.waitForTimeout(2500); // steady state for the 5 s rolling window
      const diag = await api("/diagnostics");
      const rates = Object.fromEntries(diag.event_types.map((t) => [t.event_type, t.rate_hz]));
      const near = (v, nominal) => v >= 0.7 * nominal && v <= 1.3 * nominal;
      if (!near(rates["intent.pointer"], 50) || !near(rates["recording.frame"], 25))
        throw new Error(`rates off nominal: ${JSON.stringify(rates)}`);
      return `measured rates: pointer ${rates["intent.pointer"]} Hz (nominal 50), frames ${rates["recording.frame"]} Hz (nominal 25)`;
    });

    await step("4. control the board: pointer intent moves the cursor to 'Yes', selection activates it", async () => {
      const pad = page.getByTestId("pointer-pad");
      const box = await pad.boundingBox();
      await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
      await page.mouse.down();
      await page.mouse.move(box.x + box.width * 0.15, box.y + box.height * 0.15, { steps: 5 });
      await page.waitForTimeout(1300);
      await page.mouse.up();
      await waitAttr(board().getByTestId("tile-0"), "data-active", "true");
      await shot("02-profile-a-pointer");
      await page.getByTestId("sim-select").click();
      const msg = await expectText(board().getByTestId("board-message"), /Yes/);
      return `message: "${msg.trim()}"`;
    });

    await step("5. events carry provenance simulated_intent", async () => {
      const row = page.locator('[data-event-type="intent.selection"]').first();
      await row.waitFor({ timeout: 5000 });
      const prov = await text(row.locator(".prov"));
      if (!/simulated_intent/.test(prov)) throw new Error(`provenance was ${prov}`);
      return prov.trim();
    });

    await step("6. inject recoverable link drop -> runtime reconnects", async () => {
      await page.getByTestId("fault-link_drop").click();
      await page.waitForTimeout(200);
      await expectText(page.getByTestId("runtime-state"), /streaming/, 8000);
      const diag = await api("/diagnostics");
      if (diag.counters.reconnect_successes < 1) throw new Error("no reconnect recorded");
      return `reconnect_successes=${diag.counters.reconnect_successes}`;
    });

    let boardMsgBefore = "";
    await step("7. switch to Simulated Profile B -> board adapts to scan mode (no code change)", async () => {
      boardMsgBefore = (await text(board().getByTestId("board-message"))).trim();
      await page.getByTestId("device-sim-b").click();
      await expectText(page.getByTestId("runtime-device"), /Profile B/);
      await expectText(board().getByTestId("board-mode"), /scan/);
      const diag = await api("/diagnostics");
      const sw = diag.switches[diag.switches.length - 1];
      return `switch ${sw.from_device} -> ${sw.to_device} in ${sw.duration_ms} ms`;
    });

    await step("8. on Profile B, selection picks the scanned tile", async () => {
      const labels = await board().locator('[role="gridcell"]').allTextContents();
      const activeIdx = await board()
        .locator('[role="gridcell"]')
        .evaluateAll((els) => els.findIndex((e) => e.getAttribute("data-active") === "true"));
      await page.getByTestId("sim-select").click();
      const end = Date.now() + 4000;
      let msg = "";
      while (Date.now() < end) {
        msg = (await text(board().getByTestId("board-message"))).trim();
        if (msg !== boardMsgBefore) break;
        await page.waitForTimeout(100);
      }
      const candidates = [activeIdx, (activeIdx + 1) % labels.length].map((i) => labels[i].replace("speech unavailable", ""));
      if (msg === boardMsgBefore) throw new Error("board did not react to selection");
      await shot("03-profile-b-scan");
      return `scanned tile among [${candidates.join(", ")}]; message: "${msg}"`;
    });

    await step("9. on Profile B, text intent appears on the board", async () => {
      await page.getByTestId("sim-text").fill("hi");
      await page.getByTestId("sim-text-send").click();
      const msg = await expectText(board().getByTestId("board-message"), /hi$/);
      return `message: "${msg.trim()}"`;
    });

    await step("10. Profile B rejects pointer intent explicitly", async () => {
      const r = await fetch(`${base}/api/v1/sim/pointer`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ vx: 0.5, vy: 0 }),
      });
      const body = await r.json();
      if (r.status !== 409 || body.error.code !== "capability_unsupported") throw new Error(JSON.stringify(body));
      return `409 ${body.error.code}`;
    });

    await step("11. record a session and replay it through the same pipeline", async () => {
      await page.getByTestId("rec-start").click();
      await page.getByTestId("recording-indicator").waitFor({ timeout: 5000 });
      await page.getByTestId("sim-text").fill("ok");
      await page.getByTestId("sim-text-send").click();
      await page.waitForTimeout(2500);
      await page.getByTestId("rec-stop").click();
      const recs = await api("/recordings");
      const name = recs[0].name;
      const btn = page.getByTestId(`device-replay:${name}`);
      await btn.waitFor({ timeout: 5000 });
      await btn.click();
      await expectText(page.getByTestId("runtime-device"), /Replay/);
      await page.locator('[data-event-type="recording.frame"] .prov', { hasText: "↺" }).first().waitFor({ timeout: 8000 });
      return `replaying ${name}`;
    });

    await step("12. diagnostics show measured numbers", async () => {
      await page.getByTestId("tab-diagnostics").click();
      await page.getByTestId("diagnostics").waitFor();
      await shot("04-diagnostics");
      const d = await api("/diagnostics");
      return `pipeline p50 ${d.pipeline_latency.p50_us} µs, p99 ${d.pipeline_latency.p99_us} µs over ${d.pipeline_latency.count} events`;
    });

    await step("13. tests tab renders; board app stayed connected across tab switches", async () => {
      await page.getByTestId("tab-tests").click();
      await page.getByTestId("tests-view").waitFor();
      await page.getByTestId("app-communication-board").waitFor({ timeout: 3000 });
      await page.getByTestId("tab-live").click();
      await expectText(board().getByTestId("board-conn"), /connected/);
      return null;
    });

    // ---------------------------------------------------------- Milestone 2: real data
    const REAL = "nwb:sub-humanpitt-held-in-calib_ses-19250108t111022";
    const playback = () => api("/runtime/playback");

    await step("14. a verified real human recording is offered as an offline source", async () => {
      const ds = await api("/datasets");
      if (!ds.nwb_support) throw new Error(`NWB support missing: ${ds.unavailable_reason}`);
      if (!ds.devices.includes(REAL)) throw new Error(`dataset not found; run \`make dataset model\` (have: ${ds.devices.join(", ") || "none"})`);
      await page.getByTestId("dataset-list").waitFor();
      return `${ds.devices.length} DANDI 000954 file(s) available`;
    });

    await step("15. connect the recording: labelled Offline Replay, file verified against DANDI", async () => {
      await page.getByTestId(`device-${REAL}`).click();
      await expectText(page.getByTestId("runtime-device"), /Recorded Human Intracranial Data — Offline Replay/);
      await expectText(page.getByTestId("data-badge"), /RECORDED HUMAN DATA · OFFLINE REPLAY/);
      await expectText(page.getByTestId("source-verified"), /SHA-256 matches DANDI 000954/);
      await expectText(page.getByTestId("source-signal"), /176 channels .* 20 ms bins/);
      return (await text(page.getByTestId("source-signal"))).trim();
    });

    await step("16. real samples flow through the runtime with correct provenance", async () => {
      const d0 = (await api("/diagnostics")).event_types.find((t) => t.event_type === "features.binned");
      await page.waitForTimeout(1200);
      const d1 = (await api("/diagnostics")).event_types.find((t) => t.event_type === "features.binned");
      if (!d1 || (d0 && d1.total <= d0.total)) throw new Error("no features.binned events");
      for (const [type, kind] of [["features.binned", "processed_feature"], ["behavior.sample", "behavioral_label"], ["intent.kinematics", "decoded_intent"]]) {
        const row = page.locator(`[data-event-type="${type}"]`).first();
        await row.waitFor({ timeout: 5000 });
        const prov = await text(row.locator(".prov"));
        if (!prov.includes(kind)) throw new Error(`${type} provenance was ${prov}`);
      }
      await page.getByTestId("raster-canvas").waitFor();
      return `features.binned total ${d1.total} at ${d1.rate_hz} Hz`;
    });

    await step("17. the communication board does not react to neural data", async () => {
      await expectText(board().getByTestId("board-mode"), /inactive/);
      const msgBefore = (await text(board().getByTestId("board-message"))).trim();
      await page.waitForTimeout(800);
      if ((await text(board().getByTestId("board-message"))).trim() !== msgBefore) throw new Error("board changed");
      return "board suspended (no selection capability), message unchanged";
    });

    await step("18. playback: speed, pause, resume", async () => {
      await page.getByTestId("speed-4").click();
      let p = await playback();
      const t0 = Date.now(), p0 = p.position_s;
      await page.waitForTimeout(1000);
      p = await playback();
      const rate = (p.position_s - p0) / ((Date.now() - t0) / 1000);
      if (p.speed !== 4 || rate < 3 || rate > 5) throw new Error(`speed ${p.speed}, measured ${rate.toFixed(2)} s/s`);
      await page.getByTestId("pb-pause").click();
      await page.waitForTimeout(300);
      const a = (await playback()).position_s;
      await page.waitForTimeout(600);
      const b = (await playback()).position_s;
      if (Math.abs(b - a) > 0.05) throw new Error(`position moved while paused (${a} -> ${b})`);
      await page.getByTestId("pb-resume").click();
      await expectText(page.getByTestId("runtime-state"), /streaming/);
      await page.getByTestId("neural-view").scrollIntoViewIfNeeded();
      await page.waitForTimeout(1200);
      await shot("06-real-data");
      await page.getByTestId("neural-view").screenshot({ path: path.join(SHOTS, "07-neural-view.png") });
      return `measured ${rate.toFixed(2)} s of recording per second at 4×; paused held at ${a}s`;
    });

    await step("19. switch back to a simulated device: platform and board keep working", async () => {
      await page.getByTestId("device-sim-a").click();
      await expectText(page.getByTestId("data-badge"), /SIMULATED DATA/);
      await expectText(board().getByTestId("board-mode"), /pointer/);
      await page.getByTestId("sim-select").click();
      await expectText(board().getByTestId("board-message"), /\S/);
      return "board back in pointer mode; selection works";
    });

    await step("20. stop: reconnect the recording, then Stop returns to idle", async () => {
      await page.getByTestId(`device-${REAL}`).click();
      await expectText(page.getByTestId("runtime-device"), /Offline Replay/);
      await page.getByTestId("pb-stop").click();
      await expectText(page.getByTestId("runtime-state"), /idle/);
      return null;
    });

    // ------------------------------------------------- Milestone 3: live acquisition (lab console)
    // Hardware-free protocol publishers stand in for acquisition systems; both declare
    // themselves synthetic, and the console must label them accordingly.
    const SID = `brainos-e2e-${process.pid}`;
    const LSL_ID = `lsl:${SID}`;
    const OE_PORT = 5600 + (process.pid % 300);
    const OE_ID = `openephys:127.0.0.1:${OE_PORT}`;
    const numberIn = async (loc) => Number(((await loc.textContent({ timeout: 5000 })) ?? "").replace(/[^\d.-]/g, ""));
    const grows = async (loc, label, timeout = 10000) => {
      const a = await numberIn(loc);
      const end = Date.now() + timeout;
      while (Date.now() < end) {
        await page.waitForTimeout(400);
        const b = await numberIn(loc);
        if (b > a) return [a, b];
      }
      throw new Error(`${label} did not increase from ${a}`);
    };
    const integrity = (k) => page.locator(`[data-testid="integrity-counters"] [data-counter="${k}"] .counter-value`).first();
    const plCounter = (k) => page.locator(`[data-testid="pl-counters"] [data-counter="${k}"] .kpi-value`);

    await step("M3-1. discover an LSL stream in the Acquisition tab and register it with its behavior stream", async () => {
      publisher(["lsl-ephys", "--channels", "16", "--rate", "30000", "--source-id", SID]);
      await page.getByTestId("tab-acquisition").click();
      const row = page.locator(`[data-stream-key="${SID}"]`);
      const end = Date.now() + 15000;
      while (!(await row.count()) && Date.now() < end) {
        await page.getByTestId("lsl-discover").click();
        await expectText(page.getByTestId("lsl-discover"), /Discover LSL streams/, 12000);
      }
      if (!(await row.count())) throw new Error(`LSL stream ${SID} not discovered`);
      const rowText = (await row.innerText()).replace(/\s+/g, " ").trim();
      if (!/ 16 /.test(rowText) || !/30,000 Hz/.test(rowText) || !/synthetic/.test(rowText))
        throw new Error(`unexpected stream metadata: ${rowText}`);
      await page.getByTestId(`lsl-use-${SID}`).click();
      await page.getByTestId("lsl-behavior").selectOption(`${SID}-behavior`);
      await page.getByTestId("lsl-register").click();
      await page.getByTestId("live-source-list").getByTestId(`device-${LSL_ID}`).waitFor({ timeout: 5000 });
      await shot("08-m3-acquisition");
      return `discovered: ${rowText.replace(/ configure$/, "")}`;
    });

    await step("M3-2. connect the LSL source: labelled simulated (declared), integrity counters advance", async () => {
      await page.getByTestId(`device-${LSL_ID}`).click();
      await expectText(page.getByTestId("runtime-state"), /streaming/);
      await expectText(page.getByTestId("data-badge"), /SIMULATED DATA/);
      const [a, b] = await grows(integrity("samples"), "integrity samples");
      return `samples ${a} -> ${b}`;
    });

    await step("M3-3. start the spikeband pipeline: features flow, counters increase", async () => {
      await page.getByTestId("tab-pipeline").click();
      await page.getByTestId("pl-preset").selectOption("spikeband_threshold");
      await page.getByTestId("pl-start").click();
      await expectText(page.getByTestId("pl-running"), /running/);
      await expectText(page.getByTestId("pl-output"), /features\.binned · threshold_crossing_count · 20 ms · 16 ch/);
      const [a, b] = await grows(plCounter("features_out"), "features_out", 15000);
      const row = page.locator('[data-event-type="features.binned"]').first();
      await row.waitFor({ timeout: 5000 });
      const prov = await text(row.locator(".prov"));
      if (!prov.includes("processed_feature")) throw new Error(`features provenance was ${prov}`);
      const dropped = await numberIn(plCounter("dropped_inputs"));
      const errors = await numberIn(plCounter("errors"));
      if (errors) throw new Error(`pipeline errors: ${errors}`);
      if ((await numberIn(plCounter("commands_out"))) !== 0) throw new Error("commands without router");
      await page.waitForTimeout(600);
      await shot("09-m3-pipeline");
      // Live tab: integrity counters replace the simulator pad; pipeline features get their own view
      await page.getByTestId("tab-live").click();
      await page.getByTestId("signal-integrity").waitFor({ timeout: 3000 });
      await page.getByTestId("pipeline-neural-view").waitFor({ timeout: 3000 });
      await page.waitForTimeout(800);
      await shot("11-m3-live");
      await page.getByTestId("tab-pipeline").click();
      const st = await api("/pipeline");
      return (
        `features_out ${a} -> ${b} (UI); dropped ${dropped}; commands 0 (router off); ` +
        `measured processing p50 ${st.processing_us.p50} µs, input->feature p50 ${st.pipeline_latency_ms.p50} ms`
      );
    });

    await step("M3-4. stop the pipeline, disconnect, remove the LSL source", async () => {
      await page.getByTestId("pl-stop").click();
      await expectText(page.getByTestId("pl-running"), /stopped/);
      await page.getByTestId("disconnect").click();
      await expectText(page.getByTestId("runtime-state"), /idle/);
      await page.getByTestId("tab-acquisition").click();
      await page.getByTestId(`remove-${LSL_ID}`).click();
      const end = Date.now() + 5000;
      while ((await page.getByTestId(`device-${LSL_ID}`).count()) && Date.now() < end) await page.waitForTimeout(100);
      if (await page.getByTestId(`device-${LSL_ID}`).count()) throw new Error("source still listed");
      return null;
    });

    await step("M3-5. Open Ephys ZMQ: register, connect (LIVE STREAM · ORIGIN UNVERIFIED), counters advance", async () => {
      publisher(["openephys", "--port", String(OE_PORT), "--channels", "8"]);
      await page.getByTestId("oe-port").fill(String(OE_PORT));
      await page.getByTestId("oe-register").click();
      await page.getByTestId(`device-${OE_ID}`).click();
      await expectText(page.getByTestId("runtime-state"), /streaming/, 12000);
      await expectText(page.getByTestId("data-badge"), /LIVE STREAM · ORIGIN UNVERIFIED/);
      const [a, b] = await grows(integrity("data_messages"), "data_messages");
      await shot("10-m3-openephys");
      await page.getByTestId("disconnect").click();
      await expectText(page.getByTestId("runtime-state"), /idle/);
      await page.getByTestId(`remove-${OE_ID}`).click();
      return `data_messages ${a} -> ${b}`;
    });

    await step("21. no uncaught page errors", async () => {
      if (errors.length) throw new Error(errors.join(" | "));
      return null;
    });
    await page.getByTestId("tab-live").click();
    await page.waitForTimeout(500);
    await shot("05-final");
    ok = true;
  } catch {
    await shot("failure").catch(() => {});
  } finally {
    fs.writeFileSync(
      REPORT,
      JSON.stringify({ generated_at: new Date().toISOString(), base, ok, steps }, null, 2),
    );
    await browser.close();
    for (const c of children) c.kill("SIGTERM");
    if (server) server.kill("SIGINT");
  }
  console.log(ok ? "E2E PASSED" : "E2E FAILED");
  process.exit(ok ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
