// Playwright configuration for the NeuroMetric web app (chromium, headless).
// Uses the pre-installed browsers (PLAYWRIGHT_BROWSERS_PATH); never runs `playwright install`.
// The app is served by `vite preview` from web/dist (build first: cd web && npm run build).
import { defineConfig, devices } from "@playwright/test";
import path from "node:path";

const WEB = path.resolve(__dirname, "../../web");

export default defineConfig({
  testDir: ".",
  testMatch: /.*\.spec\.ts/,
  timeout: 240_000,
  expect: { timeout: 15_000 },
  workers: 1, // timing experiments must not share the CPU with other tests
  fullyParallel: false,
  reporter: [["list"]],
  outputDir: ".tmp/test-results",
  use: {
    baseURL: "http://127.0.0.1:4173/",
    ...devices["Desktop Chrome"],
    viewport: { width: 1400, height: 1000 },
    headless: true,
    bypassCSP: true, // lets axe-core be injected; the app itself is unaffected
    launchOptions: { args: ["--enable-precise-memory-info", "--js-flags=--expose-gc"] },
  },
  webServer: {
    command: `npm --prefix "${WEB}" run preview -- --host 127.0.0.1`,
    url: "http://127.0.0.1:4173/",
    reuseExistingServer: true,
    timeout: 60_000,
  },
});
