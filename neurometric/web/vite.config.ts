/// <reference types="vitest" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Cross-origin isolation headers give the 5 us performance.now() resolution (browser_timing.md).
// The app loads nothing from other origins, so require-corp is safe.
const isolation = {
  "Cross-Origin-Opener-Policy": "same-origin",
  "Cross-Origin-Embedder-Policy": "require-corp",
};

// Production builds get a strict CSP: no third-party origins, no external network (connect-src
// 'self' only, so session upload can reach only the NeuroMetric backend that serves the app).
const csp = {
  name: "neurometric-csp",
  apply: "build" as const,
  transformIndexHtml(html: string) {
    return html.replace(
      "<head>",
      `<head>\n    <meta http-equiv="Content-Security-Policy" content="default-src 'self'; connect-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; object-src 'none'; base-uri 'self'" />`,
    );
  },
};

export default defineConfig({
  base: "./",
  plugins: [react(), csp],
  server: { headers: isolation },
  preview: { headers: isolation },
  build: { outDir: "dist", sourcemap: false, target: "es2022" },
  test: { environment: "node", include: ["test/**/*.test.ts"] },
});
