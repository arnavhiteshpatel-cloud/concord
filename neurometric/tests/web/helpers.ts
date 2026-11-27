import { expect, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

export const ROOT = path.resolve(__dirname, "../..");
export const TMP = path.join(__dirname, ".tmp");
export const RESULTS = path.join(ROOT, "experiments", "results");

export function ensureDir(p: string): string {
  mkdirSync(p, { recursive: true });
  return p;
}

/** Run the Python validator + scorer on exported runs. */
export function pyValidate(runs: unknown[], name: string): any[] {
  ensureDir(TMP);
  const f = path.join(TMP, `${name}.json`);
  writeFileSync(f, JSON.stringify(runs));
  const out = execFileSync("python", [path.join(__dirname, "validate_runs.py"), f], { cwd: ROOT, encoding: "utf8", maxBuffer: 1 << 28 });
  return JSON.parse(out);
}

export async function centerOf(page: Page, selector: string): Promise<{ x: number; y: number }> {
  const box = await page.locator(selector).first().boundingBox();
  if (!box) throw new Error(`no box for ${selector}`);
  return { x: box.x + box.width / 2, y: box.y + box.height / 2 };
}

/** Move the real (CDP) mouse along a straight line in `steps` moves. */
export async function moveTo(page: Page, from: { x: number; y: number }, to: { x: number; y: number }, steps = 12): Promise<void> {
  for (let i = 1; i <= steps; i++) {
    const f = i / steps;
    // slight curvature so path efficiency is < 1 like a real movement
    const bulge = Math.sin(Math.PI * f) * 6;
    await page.mouse.move(from.x + (to.x - from.x) * f + bulge, from.y + (to.y - from.y) * f - bulge);
  }
}

export async function runs(page: Page): Promise<any[]> {
  return page.evaluate(() => (window as any).__nm.runs);
}

export async function waitForRun(page: Page, task: string): Promise<any> {
  await expect(page.locator(`[data-run="${task}"]`).first()).toBeVisible({ timeout: 120_000 });
  const rs = await runs(page);
  return rs.filter((r: any) => r.task_id === task).at(-1);
}

export function writeCsv(file: string, header: string[], rows: (string | number | boolean | null)[][]): void {
  const esc = (v: unknown) => (v === null || v === undefined ? "" : typeof v === "string" && /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : String(v));
  writeFileSync(file, [header.join(","), ...rows.map((r) => r.map(esc).join(","))].join("\n") + "\n");
}

export function readJson(file: string): any {
  return JSON.parse(readFileSync(file, "utf8"));
}

export function quantiles(a: number[]): Record<string, number> {
  const s = [...a].filter(Number.isFinite).sort((x, y) => x - y);
  const q = (p: number) => {
    if (!s.length) return NaN;
    const i = (s.length - 1) * p;
    const lo = Math.floor(i);
    const hi = Math.ceil(i);
    return s[lo] + (s[hi] - s[lo]) * (i - lo);
  };
  const mean = s.reduce((x, y) => x + y, 0) / (s.length || 1);
  const sd = Math.sqrt(s.reduce((x, y) => x + (y - mean) ** 2, 0) / Math.max(1, s.length - 1));
  return { n: s.length, mean, sd, min: s[0], p05: q(0.05), p50: q(0.5), p95: q(0.95), p99: q(0.99), max: s[s.length - 1] };
}
