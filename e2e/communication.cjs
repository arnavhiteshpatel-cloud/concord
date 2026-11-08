#!/usr/bin/env node
// Milestone 5 (P0) — reproducible neural-to-communication test, in a real browser.
//
// Recorded human intracortical data (participant T15, Singer-Clark et al., Dryad, CC0) is
// replayed through the unchanged runtime -> pipeline -> operator-enabled command router ->
// operator-authorized SDK app: the participant communication board (14 x 14 word grid laid
// over the task's target grid, pointer + click). Two chains:
//   historical — the original research decoders' recorded outputs (model_origin historical)
//   concord    — Concord Kalman + click decoders fitted on calibration blocks 0-2 only
// The board takes no mouse input. What it selected is read from its read-only snapshot
// (window.__concordBoard) and compared with an offline prediction of the same chain
// (python -m concord.evaluation.board_e2e compare): same bins, same tiles. Selections are
// also scored against the cued task targets. Open loop: the person recorded was steering the
// original cursor, not this one; replayed text is never the participant's message.
//
// Usage: node e2e/communication.cjs   (needs `make build`, the T15 demo subset
//        `python -m concord.datasets.dryad`, and playwright: `make e2e-setup`)
// Writes reports/communication_e2e.json.

const { spawn, execFileSync } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const ROOT = path.resolve(__dirname, "..");
const REPORT = path.join(ROOT, "reports", "communication_e2e.json");
const PORT = 8769;
const base = `http://127.0.0.1:${PORT}`;
const SPEED = 8;
const PY = fs.existsSync(path.join(ROOT, ".venv/bin/python")) ? path.join(ROOT, ".venv/bin/python") : "python3";
const pyEnv = {
  PYTHONPATH: [path.join(ROOT, "backend", "src"), process.env.PYTHONPATH].filter(Boolean).join(path.delimiter),
};

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
    console.log(`  ✓ ${name}${detail ? ` — ${typeof detail === "string" ? detail : JSON.stringify(detail)}` : ""}`);
    return detail;
  } catch (err) {
    steps.push({ name, ok: false, time_s: (Date.now() - t0) / 1000, detail: String(err?.message ?? err).slice(0, 800) });
    console.log(`  ✗ ${name}: ${err?.message ?? err}`);
    throw err;
  }
}

async function api(p, method = "GET", body) {
  const r = await fetch(`${base}/api/v1${p}`, {
    method,
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json().catch(() => null);
  if (!r.ok) throw new Error(`${method} ${p}: ${r.status} ${JSON.stringify(data)}`);
  return data;
}

async function waitFor(fn, label, timeoutMs, everyMs = 200) {
  const end = Date.now() + timeoutMs;
  let last;
  while (Date.now() < end) {
    last = await fn();
    if (last) return last;
    await new Promise((r) => setTimeout(r, everyMs));
  }
  throw new Error(`timed out: ${label}`);
}

async function main() {
  const work = fs.mkdtempSync(path.join(os.tmpdir(), "concord-e2e-comm-"));
  const results = {};
  let server = null;
  let browser = null;
  let ok = false;
  try {
    let plan = null;
    await step("P0-1. prepare: T15 demo blocks + Concord models fitted on calibration blocks 0-2 only", async () => {
      execFileSync(PY, ["-m", "concord.evaluation.board_e2e", "prepare", "--out", work], {
        env: { ...process.env, ...pyEnv },
        encoding: "utf8",
      });
      plan = JSON.parse(fs.readFileSync(path.join(work, "plan.json"), "utf8"));
      return `device ${plan.device_id}; Kalman ${plan.modes.concord.model_id}; click ${plan.modes.concord.model_ids[0]}`;
    });

    server = spawn(PY, ["-m", "concord.server"], {
      env: {
        ...process.env,
        ...pyEnv,
        CONCORD_PORT: String(PORT),
        CONCORD_DATA_DIR: work,
        CONCORD_LOG_LEVEL: "WARNING",
        CONCORD_OPEN_BROWSER: "0",
      },
      stdio: ["ignore", "inherit", "inherit"],
    });
    await waitFor(async () => (await fetch(`${base}/api/v1/health`).catch(() => null))?.ok, "server healthy", 30000);
    browser = await chromium.launch();

    // the 14 x 14 board is the task's own grid; 7 x 7 and 2 x 2 boards group whole task cells
    const RUNS = [["historical", 14], ["concord", 14], ["concord", 7], ["concord", 2]];
    for (const [mode, n] of RUNS) {
      const run = `${mode} ${n}x${n}`;
      const spec = plan.modes[mode];
      const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
      const errors = [];
      page.on("pageerror", (e) => errors.push(String(e)));
      await page.goto(`${base}/board.html?layout=grid&n=${n}&method=cursor_click`);
      await waitFor(async () => /Connected/.test((await page.getByTestId("board-conn").textContent().catch(() => "")) ?? ""), "board connected", 15000);

      let positionS = 0;
      await step(`P0-2 (${run}). connect the grid block paused, start the chain, enable the router, authorize the board`, async () => {
        await api("/runtime/connect", "POST", { device_id: plan.device_id });
        await api("/runtime/pause", "POST");
        positionS = (await api("/runtime/playback")).position_s;
        const body = { processing: spec.processing, router: spec.router, allow_cross_source: false };
        if (spec.model_id) Object.assign(body, { model_id: spec.model_id, model_ids: spec.model_ids });
        const st = await api("/pipeline/start", "POST", body);
        await api("/control/apps/communication-board/authorize", "POST", { capabilities: ["pointer_intent", "selection"] });
        await api("/runtime/playback", "POST", { speed: SPEED });
        const before = await page.evaluate(() => window.__concordBoard.counters.selections);
        if (before !== 0) throw new Error(`board selected ${before} tiles before the replay resumed`);
        await api("/runtime/resume", "POST");
        const decs = (st.decoders || []).map((d) => `${d.model_id} (${d.model_origin ?? d.origin ?? "?"})`);
        return `paused at ${positionS.toFixed(2)} s; decoders: ${decs.join(", ") || "source outputs (passthrough)"}`;
      });

      const snap = await step(`P0-3 (${run}). replay one full pass at ${SPEED}x; the board selects words by decoded click`, async () => {
        await waitFor(async () => {
          const pb = await api("/runtime/playback");
          return pb.loops >= 1 || (pb.duration_s && pb.position_s >= pb.duration_s - 0.05) ? pb : null;
        }, "end of the block", 200000, 500);
        await api("/runtime/pause", "POST");
        const s = await page.evaluate(() => window.__concordBoard);
        if (!s.selections.length) throw new Error("no selections");
        const via = [...new Set(s.selections.map((x) => x.via))];
        if (via.some((v) => v !== "click")) throw new Error(`unexpected selection methods ${via}`);
        const input = s.input ? `${s.input.label}${s.input.qualifiers.length ? ` (${s.input.qualifiers.join(", ")})` : ""}` : "";
        return { selections: s.selections.length, input, text_label: s.textLabel };
      });

      await step(`P0-4 (${run}). the board's selections equal the offline prediction of the same chain`, async () => {
        const s = await page.evaluate(() => window.__concordBoard);
        const obsPath = path.join(work, `observed-${mode}-${n}.json`);
        fs.writeFileSync(obsPath, JSON.stringify(s));
        const outPath = path.join(work, `compare-${mode}-${n}.json`);
        execFileSync(
          PY,
          ["-m", "concord.evaluation.board_e2e", "compare", "--plan", path.join(work, "plan.json"), "--mode", mode,
            "--observed", obsPath, "--position-s", String(positionS), "--n", String(n), "--out", outPath],
          { env: { ...process.env, ...pyEnv }, encoding: "utf8" },
        );
        const r = JSON.parse(fs.readFileSync(outPath, "utf8"));
        r.board_input = snap.input;
        r.text_label = s.textLabel ?? null;
        r.page_errors = errors;
        results[run] = r;
        if (r.agreement < 0.98) throw new Error(`agreement ${r.agreement}: ${JSON.stringify(r)}`);
        if (errors.length) throw new Error(errors.join(" | "));
        return `${r.same_tile}/${r.board_selections} selections on the predicted tile (start bin ${r.start_bin}, max cursor diff ${r.max_cursor_difference.toExponential(1)}); ` +
          `${r.selections_on_the_cued_word}/${r.board_selections} on the cued word (chance ${(r.chance_per_selection * 100).toFixed(1)} %)`;
      });
      await step(`P0-5 (${run}). provenance shown on the board`, async () => {
        const want = mode === "historical" ? /historical decoder replay/i : /\(Concord\)/;
        if (!want.test(snap.input)) throw new Error(`board input label: ${snap.input}`);
        if (!/demonstration/i.test(snap.text_label ?? "")) throw new Error(`text label: ${snap.text_label}`);
        return `${snap.input}; text: ${snap.text_label}`;
      });
      await api("/pipeline/stop", "POST").catch(() => {});
      await api("/runtime/disconnect", "POST");
      await page.close();
    }
    ok = true;
  } finally {
    fs.mkdirSync(path.dirname(REPORT), { recursive: true });
    fs.writeFileSync(
      REPORT,
      JSON.stringify({ generated_at: new Date().toISOString(), ok, speed: SPEED, steps, results }, null, 1),
    );
    if (browser) await browser.close().catch(() => {});
    if (server) server.kill("SIGTERM");
    console.log(ok ? "COMMUNICATION E2E PASSED" : "COMMUNICATION E2E FAILED");
    console.log(`report: ${REPORT}`);
  }
}

main().catch(() => process.exit(1));
