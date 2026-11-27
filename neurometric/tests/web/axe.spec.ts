// axe-core accessibility scan of every screen (setup, task list, intro, each task while running,
// pause overlay, assistance dialog, stop confirmation, results, demo), in light, dark and
// high-contrast themes. Requirement: zero serious / critical violations.
// axe-core is vendored as a devDependency of web/ (web/node_modules/axe-core).
import { test, expect, type Page } from "@playwright/test";
import path from "node:path";
import { writeFileSync } from "node:fs";
import { RESULTS, ensureDir, writeCsv, ROOT } from "./helpers";

const AXE = path.join(ROOT, "web", "node_modules", "axe-core", "axe.min.js");
const TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"];

interface Rec {
  screen: string;
  theme: string;
  violations: { id: string; impact: string; nodes: number; help: string; targets: string[] }[];
  passes: number;
  incomplete: number;
}
const records: Rec[] = [];

async function scan(page: Page, screen: string, theme = "system"): Promise<Rec> {
  await page.addScriptTag({ path: AXE });
  const r = await page.evaluate(async (tags) => {
    // @ts-expect-error axe is injected
    const res = await window.axe.run(document, { runOnly: { type: "tag", values: tags }, resultTypes: ["violations", "incomplete"] });
    return {
      violations: res.violations.map((v: any) => ({ id: v.id, impact: v.impact, nodes: v.nodes.length, help: v.help, targets: v.nodes.slice(0, 5).map((n: any) => String(n.target)) })),
      passes: res.passes.length,
      incomplete: res.incomplete.length,
    };
  }, TAGS);
  const rec = { screen, theme, ...r };
  records.push(rec);
  return rec;
}

function serious(r: Rec) {
  return r.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
}

const THEMES = ["light", "dark", "contrast"];

for (const theme of THEMES) {
  test(`static screens (${theme})`, async ({ page }) => {
    for (const [name, hash, ready] of [
      ["setup", "#/setup", "#setup-h"],
      ["task list", "#/tasks", ".task-list"],
      ["task intro (A2)", "#/run/A2", "#begin-task"],
      ["results (empty)", "#/results", "#res-h"],
      ["demo: try it yourself", "#/demo", "#demo-results"],
    ] as const) {
      await page.goto(`/${hash}${hash.includes("?") ? "&" : "?"}theme=${theme}`);
      await expect(page.locator(ready).first()).toBeVisible();
      const r = await scan(page, name, theme);
      expect(serious(r), `${name}/${theme}: ${JSON.stringify(serious(r), null, 1)}`).toEqual([]);
    }
    await page.goto(`/#/demo?theme=${theme}`);
    await page.click("#demo-tab-watch");
    await expect(page.locator("#watch-play")).toBeVisible();
    const r = await scan(page, "demo: watch a virtual user", theme);
    expect(serious(r)).toEqual([]);
  });
}

const RUNNING = ["A1", "A2", "A3", "A4", "B1", "B2", "C1", "D1", "E1", "E2", "F1", "F2", "F3", "F4", "F5", "F6", "F7"];

test("every task while running (light + high contrast), A5 with time pressure on", async ({ page }) => {
  for (const theme of ["light", "contrast"]) {
    for (const id of RUNNING) {
      await page.goto(`/#/run/${id}?autostart=1&theme=${theme}`);
      await expect(page.locator("#task-canvas")).toBeVisible();
      await page.waitForTimeout(150);
      const r = await scan(page, `running ${id}`, theme);
      expect(serious(r), `${id}/${theme}: ${JSON.stringify(serious(r), null, 1)}`).toEqual([]);
    }
  }
  await page.addInitScript(() => {
    try {
      localStorage.setItem("neurometric.settings.v1", JSON.stringify({ noTimePressure: false }));
    } catch {
      /* ignore */
    }
  });
  await page.goto("about:blank");
  await page.goto("/#/run/A5?autostart=1&theme=light");
  await expect(page.locator("#task-canvas")).toBeVisible();
  const r = await scan(page, "running A5 (time pressure on)", "light");
  expect(serious(r)).toEqual([]);
});

test("dialogs and states: pause overlay, assistance dialog, stop confirmation, results with data, scanning highlight", async ({ page }) => {
  await page.goto("/#/run/F1?autostart=1&theme=light");
  await expect(page.locator("#task-canvas")).toBeVisible();
  await page.click("#btn-pause");
  let r = await scan(page, "pause overlay", "light");
  expect(serious(r)).toEqual([]);
  await page.click("#overlay-resume");
  await page.click("#btn-assist");
  await expect(page.locator("dialog[open]")).toBeVisible();
  r = await scan(page, "assistance dialog", "light");
  expect(serious(r)).toEqual([]);
  await page.click("#assist-cancel");
  await page.click("#btn-stop");
  await expect(page.locator("#btn-stop-confirm")).toBeVisible();
  r = await scan(page, "stop confirmation", "light");
  expect(serious(r)).toEqual([]);
  await page.click("#btn-stop-confirm");
  await expect(page.locator('[data-run="F1"]')).toBeVisible();
  r = await scan(page, "results (with a run)", "light");
  expect(serious(r)).toEqual([]);
  await page.goto("about:blank"); // settings are read from the URL on a fresh load
  await page.goto("/#/setup?ui_scanning=1&scan_ms=400&theme=dark");
  await page.keyboard.press("Space");
  await expect(page.locator(".scan-hl")).toHaveCount(1);
  r = await scan(page, "setup with switch-scanning highlight", "dark");
  expect(serious(r)).toEqual([]);
});

test.afterAll(() => {
  const dir = ensureDir(path.join(RESULTS, "Q_accessibility"));
  const all = records.flatMap((r) => r.violations.map((v) => [r.screen, r.theme, v.id, v.impact, v.nodes, v.help, v.targets.join(" | ")]));
  writeCsv(path.join(dir, "axe_violations.csv"), ["screen", "theme", "rule", "impact", "nodes", "help", "example_targets"], all as any);
  const byImpact: Record<string, number> = {};
  for (const r of records) for (const v of r.violations) byImpact[v.impact] = (byImpact[v.impact] ?? 0) + 1;
  writeFileSync(
    path.join(dir, "axe_summary.json"),
    JSON.stringify(
      {
        generated: new Date().toISOString(),
        tool: "axe-core 4.10.3 (vendored npm devDependency) via Playwright, headless Chromium",
        tags: TAGS,
        screens_scanned: records.length,
        violations_by_impact: byImpact,
        serious_or_critical: records.reduce((a, r) => a + serious(r).length, 0),
        screens: records.map((r) => ({ screen: r.screen, theme: r.theme, violations: r.violations.map((v) => `${v.id} (${v.impact}, ${v.nodes} nodes)`), rules_passed: r.passes, needs_review: r.incomplete })),
        caveat: "Automated rules find roughly a third to a half of WCAG issues. Zero automated violations does not mean the app is accessible; the manual protocol in docs/accessibility/ACCESSIBILITY.md (screen readers, switch hardware, eye trackers) has NOT been carried out.",
      },
      null,
      1,
    ) + "\n",
  );
});
