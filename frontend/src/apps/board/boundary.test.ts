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
  }
});
