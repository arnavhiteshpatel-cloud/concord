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
//   -> real human recording streamed over LSL (declared prerecorded): passthrough + trained
//      model, Start control, Stop control from the title bar.
//
// The console is one session screen: title bar (status line, Stop control), four rows,
// the session log, and an Advanced section; the steps open Advanced sections (event stream,
// simulator controls, communication board, …) where they need them. Review screenshots of
// the redesign go to e2e/screenshots/redesign/ (1440×900, 2× pixels).
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
const DESIGN = path.join(SHOTS, "redesign");
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
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
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
  // Screenshots of the redesigned console for review (1440×900 viewport, 2× pixels).
  const designShot = async (name, opts = {}) => {
    fs.mkdirSync(DESIGN, { recursive: true });
    await page.waitForTimeout(300);
    await page.screenshot({ path: path.join(DESIGN, `${name}.png`), ...opts });
  };

  // ---- session-screen helpers
  const status = page.getByTestId("status-line");
  /** the runtime state, as the title-bar status line reports it */
  const expectState = (value, timeout = 8000) => waitAttr(status, "data-state", value, timeout);
  const expanded = async (testId) => (await page.getByTestId(`${testId}-toggle`).getAttribute("aria-expanded")) === "true";
  /** Opens a disclosure (and the Advanced section first, for an Advanced section). */
  const open = async (testId) => {
    if (testId.startsWith("adv-") && !(await expanded("advanced"))) await page.getByTestId("advanced-toggle").click();
    await page.getByTestId(`${testId}-toggle`).waitFor({ timeout: 5000 });
    if (!(await expanded(testId))) await page.getByTestId(`${testId}-toggle`).click();
  };
  const closeAll = async () => {
    if (await page.getByTestId("source-picker").count()) await page.getByTestId("sheet-close").click();
    // collapse every open Advanced section, then Advanced itself
    const openSection = page.locator('[data-testid^="adv-"][data-testid$="-toggle"][aria-expanded="true"]');
    while (await openSection.count()) await openSection.first().click();
    if (await expanded("advanced")) await page.getByTestId("advanced-toggle").click();
    await page.evaluate(() => window.scrollTo(0, 0));
  };
  const openPicker = async () => {
    if (await page.getByTestId("source-picker").count()) return;
    const connect = page.getByTestId("connect-source");
    await ((await connect.count()) ? connect : page.getByTestId("change-source")).click();
    await page.getByTestId("source-picker").waitFor({ timeout: 5000 });
  };
  /** Source picker -> Connect/Switch; the picker closes on success. */
  const pick = async (deviceId) => {
    await openPicker();
    const btn = page.getByTestId(`device-${deviceId}`);
    // the dataset list shows a few files until "Show all"
    if (!(await btn.count()) && (await page.getByTestId("datasets-more").count()))
      await page.getByTestId("datasets-more").click();
    await btn.waitFor({ timeout: 8000 });
    await btn.click();
    await page.getByTestId("source-picker").waitFor({ state: "detached", timeout: 8000 });
  };
  const disconnect = async () => {
    await page.getByTestId("disconnect").click();
    await expectState("idle");
  };

  let ok = false;
  try {
    await waitHealthy(base);
    console.log(`BrainOS e2e against ${base}`);

    await step("1. console loads, runtime idle, board app connected", async () => {
      await page.goto(base);
      await expectState("idle");
      await expectText(status, /No source connected/);
      await expectText(page.getByTestId("apps-line"), /Communication Board waiting for: selection/);
      await expectText(board().getByTestId("board-mode"), /inactive/);
      // the default view: four rows, the session log, one collapsed Advanced section
      if (await expanded("advanced")) throw new Error("Advanced is open by default");
      if ((await page.getByTestId("stop-control").isDisabled()) !== true) throw new Error("Stop control enabled with output off");
      await designShot("1-no-source", { fullPage: true });
      return "board negotiated: no_device; Advanced collapsed; Stop control disabled";
    });

    await step("2. connect Simulated Profile A", async () => {
      await openPicker();
      await page.getByTestId("dataset-list").waitFor({ timeout: 5000 }).catch(() => {});
      await designShot("4-source-picker");
      await pick("sim-a");
      await expectState("streaming");
      await expectText(status, /Streaming · Simulated data/);
      await expectText(board().getByTestId("board-mode"), /pointer/);
      await expectText(page.getByTestId("verdict"), /Good/);
      await page.waitForTimeout(2500); // the 2 s trace window fills
      await designShot("2-simulated-profile", { fullPage: true });
      return `board switched to pointer mode; verdict ${(await text(page.getByTestId("verdict"))).trim()}`;
    });

    await step("3. live standardized events stream to the console", async () => {
      await open("adv-events");
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
      await open("adv-board");
      await open("adv-simulator");
      const pad = page.getByTestId("pointer-pad");
      // centre it: the sticky title bar must not cover the pad
      await pad.evaluate((el) => el.scrollIntoView({ block: "center" }));
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

    await step("6. inject recoverable link drop -> runtime reconnects, logged in the session log", async () => {
      await page.getByTestId("fault-link_drop").click();
      await page.waitForTimeout(200);
      await expectState("streaming", 8000);
      const diag = await api("/diagnostics");
      if (diag.counters.reconnect_successes < 1) throw new Error("no reconnect recorded");
      await expectText(page.getByTestId("session-log"), /Link lost, reconnecting/);
      return `reconnect_successes=${diag.counters.reconnect_successes}`;
    });

    let boardMsgBefore = "";
    await step("7. switch to Simulated Profile B -> board adapts to scan mode (no code change)", async () => {
      boardMsgBefore = (await text(board().getByTestId("board-message"))).trim();
      await pick("sim-b");
      await expectText(page.getByTestId("runtime-device"), /Profile B/);
      await expectText(board().getByTestId("board-mode"), /scan/);
      const diag = await api("/diagnostics");
      const sw = diag.switches[diag.switches.length - 1];
      return `switch ${sw.from_device} -> ${sw.to_device} in ${sw.duration_ms} ms`;
    });

    await step("8. on Profile B, selection picks the scanned tile", async () => {
      await open("adv-simulator");
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
      await open("adv-recording");
      await page.getByTestId("rec-start").click();
      await page.getByTestId("recording-indicator").waitFor({ timeout: 5000 });
      await page.getByTestId("sim-text").fill("ok");
      await page.getByTestId("sim-text-send").click();
      await page.waitForTimeout(2500);
      await page.getByTestId("rec-stop").click();
      await page.getByTestId("recording-indicator").waitFor({ state: "detached", timeout: 5000 });
      const recs = await api("/recordings");
      const name = recs[0].name;
      await pick(`replay:${name}`);
      await expectText(page.getByTestId("runtime-device"), /Replay/);
      await page.locator('[data-event-type="recording.frame"] .prov', { hasText: "↺" }).first().waitFor({ timeout: 8000 });
      await expectText(page.getByTestId("session-log"), /Recording stopped/);
      return `replaying ${name}`;
    });

    await step("12. diagnostics show measured numbers", async () => {
      await open("adv-diagnostics");
      await page.getByTestId("diagnostics").waitFor();
      await page.getByTestId("diagnostics").scrollIntoViewIfNeeded();
      await shot("04-diagnostics");
      const d = await api("/diagnostics");
      return `pipeline p50 ${d.pipeline_latency.p50_us} µs, p99 ${d.pipeline_latency.p99_us} µs over ${d.pipeline_latency.count} events`;
    });

    await step("13. tests section renders; board app stayed connected throughout", async () => {
      await open("adv-tests");
      await page.getByTestId("tests-view").waitFor();
      await open("adv-apps");
      await page.getByTestId("app-communication-board").waitFor({ timeout: 3000 });
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
      await openPicker();
      await page.getByTestId("dataset-list").waitFor();
      return `${ds.devices.length} DANDI 000954 file(s) available`;
    });

    await step("15. connect the recording: labelled offline replay, file verified against DANDI", async () => {
      await pick(REAL);
      await expectText(page.getByTestId("runtime-device"), /Recorded Human Intracranial Data — Offline Replay/);
      await expectText(status, /Recorded human data, offline replay/);
      await open("adv-acquisition");
      await expectText(page.getByTestId("source-verified"), /SHA-256 matches DANDI 000954/);
      await expectText(page.getByTestId("source-signal"), /176 channels .* 20 ms bins/);
      await expectText(page.getByTestId("fig-channels"), /176 of 176/);
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
      await expectText(page.getByTestId("trace-caption"), /Showing 4 of 176 channels/);
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
      await open("source-options");
      await page.getByTestId("speed-4").click();
      let p = await playback();
      const t0 = Date.now(), p0 = p.position_s;
      await page.waitForTimeout(1000);
      p = await playback();
      const rate = (p.position_s - p0) / ((Date.now() - t0) / 1000);
      if (p.speed !== 4 || rate < 3 || rate > 5) throw new Error(`speed ${p.speed}, measured ${rate.toFixed(2)} s/s`);
      await page.getByTestId("pause").click();
      await expectState("paused");
      await expectText(page.getByTestId("verdict"), /Paused/);
      await page.waitForTimeout(300);
      const a = (await playback()).position_s;
      await page.waitForTimeout(600);
      const b = (await playback()).position_s;
      if (Math.abs(b - a) > 0.05) throw new Error(`position moved while paused (${a} -> ${b})`);
      await page.getByTestId("resume").click();
      await expectState("streaming");
      await page.getByTestId("neural-view").scrollIntoViewIfNeeded();
      await page.waitForTimeout(1200);
      await shot("06-real-data");
      await page.getByTestId("neural-view").screenshot({ path: path.join(SHOTS, "07-neural-view.png") });
      return `measured ${rate.toFixed(2)} s of recording per second at 4×; paused held at ${a}s`;
    });

    await step("19. switch back to a simulated device: platform and board keep working", async () => {
      await pick("sim-a");
      await expectText(status, /Simulated data/);
      await expectText(board().getByTestId("board-mode"), /pointer/);
      await open("adv-simulator");
      await page.getByTestId("sim-select").click();
      await expectText(board().getByTestId("board-message"), /\S/);
      return "board back in pointer mode; selection works";
    });

    await step("20. stop: reconnect the recording, then Disconnect returns to idle", async () => {
      await pick(REAL);
      await expectText(page.getByTestId("runtime-device"), /Offline Replay/);
      await disconnect();
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
    /** Source picker -> Find LSL streams -> search until `key` is listed. */
    const discover = async (key) => {
      await openPicker();
      await open("find-lsl");
      const row = page.locator(`[data-stream-key="${key}"]`);
      const end = Date.now() + 15000;
      while (!(await row.count()) && Date.now() < end) {
        await page.getByTestId("lsl-discover").click();
        await expectText(page.getByTestId("lsl-discover"), /Search the network/, 12000);
      }
      if (!(await row.count())) throw new Error(`LSL stream ${key} not discovered`);
      return row;
    };

    await step("M3-1. discover an LSL stream in the source picker and register it with its behavior stream", async () => {
      publisher(["lsl-ephys", "--channels", "16", "--rate", "30000", "--source-id", SID]);
      const row = await discover(SID);
      const rowText = (await row.innerText()).replace(/\s+/g, " ").trim();
      if (!/ 16 /.test(rowText) || !/30,000 Hz/.test(rowText) || !/synthetic/.test(rowText))
        throw new Error(`unexpected stream metadata: ${rowText}`);
      await page.getByTestId(`lsl-use-${SID}`).click();
      await page.getByTestId("lsl-behavior").selectOption(`${SID}-behavior`);
      await page.getByTestId("lsl-register").click();
      await page.getByTestId("live-source-list").getByTestId(`device-${LSL_ID}`).waitFor({ timeout: 5000 });
      await shot("08-m3-acquisition");
      return `discovered: ${rowText.replace(/ Use$/, "")}`;
    });

    await step("M3-2. connect the LSL source: labelled simulated (declared), integrity counters advance", async () => {
      await pick(LSL_ID);
      await expectState("streaming");
      await expectText(status, /Simulated data/);
      await open("adv-acquisition");
      const [a, b] = await grows(integrity("samples"), "integrity samples");
      await expectText(page.getByTestId("fig-received"), /^\d/); // LSL reports samples vs estimated missing
      return `samples ${a} -> ${b}; data received ${(await text(page.getByTestId("fig-received"))).trim()}%`;
    });

    await step("M3-3. start decoding (spike-band preset, no model): features flow, counters increase", async () => {
      await page.getByTestId("start-decoding-open").click();
      const preset = page.getByTestId("pl-preset");
      await preset.waitFor();
      if ((await preset.inputValue()) !== "spikeband_threshold") throw new Error(`default preset ${await preset.inputValue()}`);
      await page.getByTestId("pl-start").click();
      await page.getByTestId("start-decoding").waitFor({ state: "detached", timeout: 8000 });
      await expectText(page.getByTestId("decoder-state"), /Running · Spike-band threshold crossings/);
      await open("adv-pipeline");
      await expectText(page.getByTestId("pl-running"), /Running/);
      await expectText(page.getByTestId("pl-output"), /features\.binned · threshold_crossing_count · 20 ms · 16 ch/);
      const [a, b] = await grows(plCounter("features_out"), "features_out", 15000);
      await open("adv-events");
      const row = page.locator('[data-event-type="features.binned"]').first();
      await row.waitFor({ timeout: 5000 });
      const prov = await text(row.locator(".prov"));
      if (!prov.includes("processed_feature")) throw new Error(`features provenance was ${prov}`);
      const dropped = await numberIn(plCounter("dropped_inputs"));
      const errors = await numberIn(plCounter("errors"));
      if (errors) throw new Error(`pipeline errors: ${errors}`);
      if ((await numberIn(plCounter("commands_out"))) !== 0) throw new Error("commands without router");
      if ((await page.getByTestId("router-on").count()) !== 0) throw new Error("Start control offered without a model");
      await open("adv-acquisition");
      await page.getByTestId("signal-integrity").waitFor({ timeout: 3000 });
      await page.getByTestId("pipeline-neural-view").waitFor({ timeout: 3000 });
      await page.waitForTimeout(600);
      await shot("09-m3-pipeline");
      const st = await api("/pipeline");
      return (
        `features_out ${a} -> ${b} (UI); dropped ${dropped}; commands 0 (router off); ` +
        `measured processing p50 ${st.processing_us.p50} µs, input->feature p50 ${st.pipeline_latency_ms.p50} ms`
      );
    });

    await step("M3-4. stop decoding, disconnect, remove the LSL source", async () => {
      await page.getByTestId("pl-stop").click();
      await expectText(page.getByTestId("decoder-state"), /^Off$/);
      await expectText(page.getByTestId("pl-running"), /Stopped/);
      await disconnect();
      await openPicker();
      await page.getByTestId(`remove-${LSL_ID}`).click();
      const end = Date.now() + 5000;
      while ((await page.getByTestId(`device-${LSL_ID}`).count()) && Date.now() < end) await page.waitForTimeout(100);
      if (await page.getByTestId(`device-${LSL_ID}`).count()) throw new Error("source still listed");
      return null;
    });

    await step("M3-5. Open Ephys ZMQ: register, connect (live stream, origin unverified), counters advance", async () => {
      publisher(["openephys", "--port", String(OE_PORT), "--channels", "8"]);
      await openPicker();
      await open("add-openephys");
      await page.getByTestId("oe-port").fill(String(OE_PORT));
      await page.getByTestId("oe-register").click();
      await pick(OE_ID);
      await expectState("streaming", 12000);
      await expectText(status, /Live stream, origin unverified/);
      await open("adv-acquisition");
      const [a, b] = await grows(integrity("data_messages"), "data_messages");
      await shot("10-m3-openephys");
      await disconnect();
      await openPicker();
      await page.getByTestId(`remove-${OE_ID}`).click();
      await page.getByTestId("sheet-close").click();
      return `data_messages ${a} -> ${b}`;
    });

    // ------------------------------------------- real human data over LSL -> decoder -> control
    const FALCON_FILE = path.join(ROOT, "data", "datasets", "dandi-000954", "sub-HumanPitt-held-in-calib_ses-19250108T111022.nwb");
    const FP = `falcon-e2e-${process.pid}`;
    const FALCON_ID = `lsl:${FP}-counts`;

    await step("M3-6. FALCON over LSL: passthrough + trained model, Start control, Stop control in the title bar", async () => {
      if (!fs.existsSync(FALCON_FILE)) throw new Error(`missing ${FALCON_FILE}; run \`make dataset\``);
      const models = await api("/models");
      // never a model trained on the replayed session (leakage): the baseline is trained on 110520
      const model = models.find((m) => m.summary.trained_on !== path.basename(FALCON_FILE) && /falcon/.test(m.summary.model_id));
      if (!model) throw new Error("no FALCON model; run `make model`");
      publisher(["falcon", FALCON_FILE, "--loop", "--source-prefix", FP]);
      await discover(`${FP}-counts`);
      await page.getByTestId(`lsl-use-${FP}-counts`).click();
      await page.getByTestId("lsl-behavior").selectOption(`${FP}-behavior`);
      await page.getByTestId("lsl-markers").selectOption(`${FP}-markers`);
      await page.getByTestId("lsl-register").click();
      await pick(FALCON_ID);
      await expectState("streaming", 12000);
      await expectText(status, /Recorded data, streamed replay \(declared\)/);
      await expectText(page.getByTestId("verdict"), /Good/, 10000);

      await page.getByTestId("start-decoding-open").click();
      const preset = page.getByTestId("pl-preset");
      await preset.waitFor();
      if ((await preset.inputValue()) !== "features_passthrough") throw new Error(`default preset ${await preset.inputValue()}`);
      await page.getByTestId("pl-model").selectOption(model.summary.model_id);
      await page.getByTestId("pl-start").click();
      let crossSource = false;
      const started = await page
        .getByTestId("start-decoding")
        .waitFor({ state: "detached", timeout: 5000 })
        .then(() => true)
        .catch(() => false);
      if (!started) {
        // the model was calibrated on the file, not this LSL source: the server refuses unless
        // the operator explicitly allows cross-source decoding
        const refusal = (await text(page.getByTestId("pl-error"))).trim();
        await page.getByTestId("pl-cross").check();
        await page.getByTestId("pl-start").click();
        await page.getByTestId("start-decoding").waitFor({ state: "detached", timeout: 8000 });
        crossSource = refusal;
      }
      await expectText(page.getByTestId("decoder-state"), /Running · Source features \(passthrough\)/);
      await expectText(page.getByTestId("decoder-model"), new RegExp(model.summary.model_id));

      // Start control: the deliberate action; the title-bar Stop becomes active
      await page.getByTestId("router-on").click();
      await expectText(page.getByTestId("router-state"), /On · x ← tx, y ← ty/);
      if (await page.getByTestId("stop-control").isDisabled()) throw new Error("Stop control disabled while output is on");
      const c0 = (await api("/pipeline")).counters.commands_out;
      await page.waitForTimeout(1500);
      const c1 = (await api("/pipeline")).counters.commands_out;
      if (!(c1 > c0)) throw new Error(`commands_out did not grow (${c0} -> ${c1})`);
      await closeAll();
      await page.waitForTimeout(1500);
      await designShot("3-falcon-lsl-decoding-control-on", { fullPage: true });
      await open("adv-pipeline");
      // the Advanced heading just below the sticky title bar
      await page.evaluate(() => {
        const el = document.querySelector('[data-testid="advanced"]');
        if (el) window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 72);
      });
      await page.waitForTimeout(500);
      await designShot("5-advanced-pipeline-details");

      // Stop control from the title bar
      await page.getByTestId("stop-control").click();
      await expectText(page.getByTestId("router-state"), /^Off$/);
      await waitAttr(page.getByTestId("stop-control"), "disabled", "");
      const s0 = (await api("/pipeline")).counters.commands_out;
      await page.waitForTimeout(800);
      const s1 = (await api("/pipeline")).counters.commands_out;
      if (s1 !== s0) throw new Error(`commands continued after Stop control (${s0} -> ${s1})`);
      await expectText(page.getByTestId("session-log"), /Control stopped/);

      await page.getByTestId("pl-stop").click();
      await expectText(page.getByTestId("decoder-state"), /^Off$/);
      await disconnect();
      await openPicker();
      await page.getByTestId(`remove-${FALCON_ID}`).click();
      await page.getByTestId("sheet-close").click();
      return (
        `commands_out ${c0} -> ${c1} while on, unchanged (${s0}) after title-bar Stop; model ${model.summary.model_id}` +
        (crossSource ? `; cross-source override needed (server: "${crossSource}")` : "")
      );
    });

    await step("21. no uncaught page errors", async () => {
      if (errors.length) throw new Error(errors.join(" | "));
      return null;
    });
    await closeAll();
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
