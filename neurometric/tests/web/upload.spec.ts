// Integration with the NeuroMetric backend (src/neurometric/api): the backend serves web/dist,
// a SYNTHETIC demo study is seeded, a task is completed in the browser and uploaded through the
// Results screen (POST /api/participants/{pid}/sessions); the server re-validates and scores it.
// Skipped automatically when the backend cannot be started (it is developed concurrently).
import { test, expect } from "@playwright/test";
import { spawn, execFileSync, type ChildProcess } from "node:child_process";
import { rmSync, writeFileSync } from "node:fs";
import path from "node:path";
import { ROOT, TMP, RESULTS, ensureDir, centerOf } from "./helpers";

const PORT = 8765;
const BASE = `http://127.0.0.1:${PORT}`;
const PW = "demo-pass-web-tests-1";
let server: ChildProcess | null = null;
let users: Record<string, string> = {};
let studyId = "";
let skipReason = "";

test.beforeAll(async () => {
  try {
    ensureDir(TMP);
    const db = path.join(TMP, "upload_demo.sqlite");
    for (const s of ["", "-wal", "-shm"]) rmSync(db + s, { force: true });
    const env = { ...process.env, PYTHONPATH: path.join(ROOT, "src"), NEUROMETRIC_DEMO_PASSWORD: PW, NEUROMETRIC_WEB_DIST: path.join(ROOT, "web", "dist") };
    const out = execFileSync("python", ["-m", "neurometric.api", "seed-demo", "--db", db, "--per-modality", "1"], { env, encoding: "utf8", timeout: 120_000 });
    studyId = /Study id:\s*(\S+)/.exec(out)?.[1] ?? "";
    for (const m of out.matchAll(/^\s+(\w+)\s+(demo-\S+)$/gm)) users[m[1]] = m[2];
    server = spawn("python", ["-m", "neurometric.api", "serve", "--db", db, "--port", String(PORT)], { env, stdio: "ignore" });
    for (let i = 0; i < 60; i++) {
      try {
        const r = await fetch(`${BASE}/api/health`);
        if (r.ok) return;
      } catch {
        /* not up yet */
      }
      await new Promise((r) => setTimeout(r, 250));
    }
    skipReason = "backend did not start";
  } catch (e) {
    skipReason = `backend unavailable: ${(e as Error).message.slice(0, 200)}`;
  }
});

test.afterAll(() => {
  server?.kill();
});

test("complete A4 and upload it to the backend; server-side scores are returned", async ({ page }) => {
  test.skip(!!skipReason, skipReason);
  const user = users.coordinator;
  expect(user, "coordinator user from seed-demo").toBeTruthy();
  const login = await (await fetch(`${BASE}/api/auth/login`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ username: user, password: PW }) })).json();
  const parts = await (await fetch(`${BASE}/api/studies/${studyId}/participants`, { headers: { authorization: `Bearer ${login.token}` } })).json();
  const pid = (parts as any[]).find((p) => ["enrolled", "active"].includes(p.enrollment_state))?.id;
  expect(pid).toBeTruthy();

  const stim = await (await fetch(`${BASE}/battery/A4.json`)).json();
  await page.goto(`${BASE}/#/run/A4?trials=3&autostart=1&selection=click`);
  for (let i = 0; i < 3; i++) {
    await expect.poll(async () => Number(await page.locator("#task-canvas").getAttribute("data-stimulus-seq"))).toBe(i + 1);
    const c = await centerOf(page, `#task-canvas [data-item-id="${stim.cues[i]}"]`);
    await page.mouse.move(c.x - 30, c.y - 20);
    await page.mouse.move(c.x, c.y, { steps: 5 });
    await page.mouse.down();
    await page.mouse.up();
  }
  await expect(page.locator('[data-run="A4"]')).toBeVisible();
  await expect(page.locator("#up-pid")).toBeVisible();
  await page.fill("#up-pid", pid);
  await page.fill("#up-user", user);
  await page.fill("#up-pw", PW);
  await page.click('form button[type="submit"]');
  await expect(page.locator("text=Uploaded 1 session(s)")).toBeVisible({ timeout: 30_000 });
  const list = await (await fetch(`${BASE}/api/participants/${pid}/sessions`, { headers: { authorization: `Bearer ${login.token}` } })).json();
  const mine = (list as any[]).filter((s) => s.task_id === "A4").at(-1);
  expect(mine).toBeTruthy();
  const detail = await (await fetch(`${BASE}/api/sessions/${mine.id}`, { headers: { authorization: `Bearer ${login.token}` } })).json();
  const metrics = detail.metrics ?? JSON.parse(detail.metrics_json ?? "{}");
  expect(metrics.n_trials).toBe(3);
  expect(metrics.success_rate).toBe(1);
  const dir = ensureDir(path.join(RESULTS, "Q_accessibility"));
  writeFileSync(path.join(dir, "e2e_backend_upload.json"), JSON.stringify({ generated: new Date().toISOString(), task: "A4", trials: 3, server_session_id: mine.id, server_metrics: { n_trials: metrics.n_trials, success_rate: metrics.success_rate, achieved_bitrate_bps: metrics.achieved_bitrate_bps }, note: "SYNTHETIC demo study seeded by neurometric.api seed-demo; upload via the web Results screen." }, null, 1) + "\n");
});
