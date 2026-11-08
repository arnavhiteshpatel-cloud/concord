// AT-23: the board app is device-agnostic. It may import only from src/sdk (and
// itself), and must not mention device identifiers. This is the code-level proof
// that switching devices requires no app changes.
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const appsDir = resolve(here, "..");
const sdkDir = resolve(here, "../../sdk");

function walk(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((d) =>
    d.isDirectory() ? walk(join(dir, d.name)) : [join(dir, d.name)],
  );
}

const sources = walk(appsDir).filter((f) => /\.(ts|tsx)$/.test(f) && !/\.test\.tsx?$/.test(f));

describe("application boundary", () => {
  it("finds app sources", () => {
    expect(sources.length).toBeGreaterThan(0);
  });

  for (const file of sources) {
    const rel = file.slice(appsDir.length + 1);
    const text = readFileSync(file, "utf8");

    it(`${rel} imports only react, the SDK, or app-local modules`, () => {
      const imports = [...text.matchAll(/from\s+["']([^"']+)["']/g)].map((m) => m[1]!);
      for (const spec of imports) {
        if (!spec.startsWith(".")) {
          expect(["react", "react-dom/client"]).toContain(spec);
          continue;
        }
        const target = resolve(dirname(file), spec);
        const ok = target.startsWith(sdkDir) || target.startsWith(dirname(file));
        expect(ok, `${rel} imports ${spec}`).toBe(true);
      }
    });

    it(`${rel} contains no device identifiers or device-specific branches`, () => {
      expect(text).not.toMatch(/sim-a|sim-b|profile[_ ]?[ab]\b|replay:/i);
      expect(text).not.toMatch(/\/api\/v1\/sim/);
    });

    // M5-C: an application declares capabilities and waits; it never configures the runtime,
    // the decoder or the command router, and never authorizes itself.
    it(`${rel} never acts as the operator (no REST control surface)`, () => {
      expect(text).not.toMatch(/\bruntimeApi\b|\bapiCall\b|\/api\/v1\/(control|pipeline|runtime|calibration|negotiate)/);
    });
  }

  it("every app acts on commands only through the SDK CommandGuard", () => {
    const apps = sources.filter((f) => /[\\/]apps[\\/][^\\/]+[\\/][A-Z][^\\/]*\.tsx$/.test(f));
    expect(apps.length).toBeGreaterThan(0);
    for (const f of apps) {
      const t = readFileSync(f, "utf8");
      if (/ConcordStream/.test(t)) expect(t, f).toMatch(/attachGuard|CommandGuard/);
    }
  });
});
