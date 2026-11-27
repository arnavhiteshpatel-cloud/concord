// End-to-end: complete A2 (short) with synthetic mouse moves incl. PAUSE and ASSIST, A4 with
// keyboard-only two-switch step scanning, E1 copy typing with dwell; validate every exported
// canonical event with the Python validator and score the sessions with the Python scorer.
import { test, expect, type Page } from "@playwright/test";
import { writeFileSync } from "node:fs";
import path from "node:path";
import { RESULTS, centerOf, ensureDir, moveTo, pyValidate, waitForRun } from "./helpers";

const summary: Record<string, unknown> = {};

function checkCommon(v: any) {
  expect(v.n_validation_errors, JSON.stringify(v.validation_errors)).toBe(0);
  expect(v.stream_report.non_monotonic).toBe(0);
  expect(v.stream_report.duplicate_seq).toBe(0);
  expect(v.stream_report.seq_gaps).toBe(0);
  expect(v.merge_order_matches_python).toBe(true);
  expect(v.stimulus_hash_matches).toBe(true);
}

async function stimSeq(page: Page): Promise<number> {
  return Number((await page.locator("#task-canvas").getAttribute("data-stimulus-seq")) ?? 0);
}

test("A2 (short) with synthetic mouse moves, pause/resume and recorded assistance", async ({ page }) => {
  await page.goto("/#/run/A2?blocks=1&n=8&autostart=1&selection=click");
  await expect(page.locator("#task-canvas")).toBeVisible();
  let pos = await centerOf(page, "#task-canvas");
  await page.mouse.move(pos.x, pos.y);
  let i = 0;
  const jitter = [3, -4, 6, -2, 5, -6, 2, -3, 4, -5, 1, 0];
  while (!(await page.locator('[data-run="A2"]').count()) && i < 40) {
    if (i === 3) {
      await page.click("#btn-pause");
      await expect(page.locator("#overlay-resume")).toBeVisible();
      await page.click("#overlay-resume");
      await page.click("#btn-assist");
      await expect(page.locator("dialog[open]")).toBeVisible();
      await page.click("#assist-verbal");
      await expect(page.locator("dialog[open]")).toHaveCount(0);
    }
    const tgt = page.locator("#task-canvas .titem.target");
    if (!(await tgt.count())) break;
    const c = await centerOf(page, "#task-canvas .titem.target");
    const aim = { x: c.x + jitter[i % jitter.length], y: c.y - jitter[(i + 3) % jitter.length] };
    await moveTo(page, pos, aim, 14);
    await page.mouse.down();
    await page.mouse.up();
    pos = aim;
    i++;
    await page.waitForTimeout(60);
  }
  const run = await waitForRun(page, "A2");
  expect(run.completed).toBe(true);
  const [v] = pyValidate([run], "e2e_A2");
  checkCommon(v);
  expect(v.kinds).toEqual(expect.arrayContaining(["pointer_move", "click", "pause", "resume", "assist", "marker"]));
  expect(v.assist_types).toEqual(["verbal"]);
  const s = v.scores;
  expect(s.n_trials).toBeGreaterThanOrEqual(7);
  expect(s.fitts_throughput_bps).toBeGreaterThan(0.5);
  expect(s.fitts_throughput_bps).toBeLessThan(50);
  expect(s.path_efficiency_mean).toBeGreaterThan(0.8);
  expect(s.path_efficiency_mean).toBeLessThanOrEqual(1.0);
  expect(s.session.interruptions).toBe(1);
  expect(s.session.assist_events).toBe(1);
  summary.A2 = { events: v.n_events, kinds: v.kinds, scores: { n_trials: s.n_trials, fitts_throughput_bps: s.fitts_throughput_bps, error_rate: s.error_rate, movement_time_ms_mean: s.movement_time_ms_mean, path_efficiency_mean: s.path_efficiency_mean, interruptions: s.session.interruptions, assist_events: s.session.assist_events }, provisional_browser: run.provisional.values };
});

test("A4 completed keyboard-only with two-switch step scanning", async ({ page }) => {
  const stim = await (await page.request.get("/battery/A4.json")).json();
  await page.goto("/#/run/A4?trials=4&autostart=1&selection=scan&scan_mode=step");
  await expect(page.locator("#task-canvas")).toBeFocused();
  for (let i = 0; i < 4; i++) {
    await expect.poll(() => stimSeq(page)).toBe(i + 1);
    if (i === 0) await page.keyboard.press("Space"); // first press of switch 1 starts the scan at item 0
    const cue = stim.cues[i];
    for (let k = 0; k < cue; k++) await page.keyboard.press("Space"); // switch 1: step
    await expect(page.locator(`#task-canvas [data-item-id="${cue}"]`)).toHaveClass(/scan-hl/);
    await expect(page.locator(`#task-canvas [data-item-id="${cue}"]`)).toBeFocused();
    await page.keyboard.press("Enter"); // switch 2: select
  }
  const run = await waitForRun(page, "A4");
  const [v] = pyValidate([run], "e2e_A4");
  checkCommon(v);
  expect(v.kinds).toEqual(expect.arrayContaining(["switch", "key", "marker"]));
  expect(v.kinds).not.toContain("pointer_down");
  const s = v.scores;
  expect(s.n_trials).toBe(4);
  expect(s.success_rate).toBe(1);
  expect(s.achieved_bitrate_bps).toBeGreaterThan(0);
  summary.A4 = { events: v.n_events, kinds: v.kinds, scores: { n_trials: s.n_trials, success_rate: s.success_rate, achieved_bitrate_bps: s.achieved_bitrate_bps, movement_time_ms_mean: s.movement_time_ms_mean }, provisional_browser: run.provisional.values };
});

test("E1 copy typing with dwell selection (incl. one corrected error)", async ({ page }) => {
  const stim = await (await page.request.get("/battery/E1.json")).json();
  const phrase: string = stim.phrases[0];
  const dwell = 300;
  await page.goto(`/#/run/E1?trials=1&autostart=1&selection=dwell&dwell_ms=${dwell}`);
  await expect.poll(() => page.locator("#task-canvas").getAttribute("data-paused")).toBe("0");
  // type a wrong letter after the 3rd character and correct it with Backspace
  const seq: string[] = [];
  [...phrase].forEach((ch, i) => {
    if (i === 3) seq.push("x", "\b");
    seq.push(ch);
  });
  const id = (ch: string) => (ch === " " ? "key-space" : ch === "\b" ? "key-backspace" : `key-${ch}`);
  let pos = await centerOf(page, "#task-canvas");
  const away = await centerOf(page, "#e1-presented");
  await page.mouse.move(pos.x, pos.y);
  let prev = "";
  for (const ch of [...seq, "DONE"]) {
    const sel = ch === "DONE" ? '[data-item-id="key-done"]' : `[data-item-id="${id(ch)}"]`;
    if (ch === prev) {
      await moveTo(page, pos, away, 4); // leave the key so it can be dwell-selected again
      await page.waitForTimeout(40);
      pos = away;
    }
    const c = await centerOf(page, `#task-canvas ${sel}`);
    await moveTo(page, pos, c, 5);
    pos = c;
    await page.waitForTimeout(dwell + 150);
    prev = ch;
  }
  const run = await waitForRun(page, "E1");
  const [v] = pyValidate([run], "e2e_E1");
  checkCommon(v);
  expect(v.kinds).toEqual(expect.arrayContaining(["dwell_select", "text_input", "key"]));
  const s = v.scores;
  expect(s.n_phrases).toBe(1);
  expect(s.msd_error_rate_mean).toBe(0);
  expect(s.corrected_error_rate_mean).toBeGreaterThan(0);
  expect(s.wpm_mean).toBeGreaterThan(1);
  expect(s.wpm_mean).toBeLessThan(60);
  summary.E1 = { events: v.n_events, kinds: v.kinds, presented: phrase, scores: { wpm_mean: s.wpm_mean, msd_error_rate_mean: s.msd_error_rate_mean, total_error_rate_mean: s.total_error_rate_mean, corrected_error_rate_mean: s.corrected_error_rate_mean, kspc_mean: s.kspc_mean }, provisional_browser: run.provisional.values };
});

test("Setup is operable with a single switch (auto-scan) and reaches the task list", async ({ page }) => {
  await page.goto("/#/setup?ui_scanning=1&scan_ms=150");
  await expect(page.locator("#setup-h")).toBeFocused();
  // one switch: press to start scanning, wait until "Continue to tasks" is highlighted, press again
  await page.keyboard.press("Space");
  await expect(page.locator("#go-tasks")).toHaveClass(/scan-hl/, { timeout: 60_000 });
  await page.keyboard.press("Space");
  await expect(page).toHaveURL(/#\/tasks/);
  await expect(page.locator("#tasks-h")).toBeVisible();
  summary.single_switch_setup = { reached_task_list: true, scan_ms: 150 };
});

test("Degradation demo: live ISO run (identity, position control) and virtual-user table", async ({ page }) => {
  await page.goto("/#/demo");
  await page.click("#preset-identity");
  await page.click("text=Position control (pointer-like)");
  const canvas = page.locator(".task-canvas").first();
  await expect(canvas).toBeVisible();
  let pos = await centerOf(page, ".task-canvas");
  for (let k = 0; k < 13; k++) {
    const c = await centerOf(page, ".task-canvas .titem.target");
    await moveTo(page, pos, c, 8);
    await page.waitForTimeout(40); // let the 10 ms simulation ticks catch up
    await page.mouse.down();
    await page.waitForTimeout(30);
    await page.mouse.up();
    pos = c;
    await page.waitForTimeout(40);
  }
  const row = page.locator("#demo-results tbody tr", { hasText: "you (live)" });
  await expect(row).toHaveCount(1);
  const cells = await row.locator("td").allTextContents();
  const tp = Number(cells[3]);
  expect(tp).toBeGreaterThan(0.5);
  await page.click("#demo-tab-watch");
  await expect(page.locator("#demo-results tbody tr", { hasText: "virtual user" })).toHaveCount(8);
  const vrows = await page.locator("#demo-results tbody tr", { hasText: "virtual user" }).evaluateAll((trs) =>
    trs.map((tr) => [...tr.querySelectorAll("th, td")].map((c) => c.textContent)),
  );
  summary.demo = { live_identity_position_iso_tp_bps: tp, virtual_user_rows: vrows };
});

test.afterAll(() => {
  const dir = ensureDir(path.join(RESULTS, "Q_accessibility"));
  writeFileSync(path.join(dir, "e2e_tasks_summary.json"), JSON.stringify({ generated: new Date().toISOString(), note: "Automated Playwright runs in headless Chromium with synthetic input (CDP mouse, keyboard as switch). Not a substitute for testing with real assistive technology.", results: summary }, null, 1) + "\n");
});
