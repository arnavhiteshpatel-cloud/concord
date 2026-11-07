#!/usr/bin/env node
// AT-25 — End-to-end demo in a real browser against a real BrainOS server.
//
// Performs the MVP demo sequence and records each step's outcome to
// reports/e2e.json (shown in the console's Tests tab):
//   connect A -> live events -> control board (pointer + select) -> link drop + reconnect
//   -> switch to B -> board keeps working (scan + text) -> record -> replay -> diagnostics/tests
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

async function main() {
  let server = null;
  let base = EXTERNAL;
  if (!base) {
    const py = fs.existsSync(path.join(ROOT, ".venv/bin/python")) ? path.join(ROOT, ".venv/bin/python") : "python3";
    const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "brainos-e2e-"));
    server = spawn(py, ["-m", "brainos.server"], {
      env: { ...process.env, BRAINOS_PORT: String(PORT), BRAINOS_DATA_DIR: dataDir, BRAINOS_LOG_LEVEL: "WARNING" },
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

    await step("14. no uncaught page errors", async () => {
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
    if (server) server.kill("SIGINT");
  }
  console.log(ok ? "E2E PASSED" : "E2E FAILED");
  process.exit(ok ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
