import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

const SRC = join(__dirname);
const BUNDLE = readFileSync(join(__dirname, "../../design-system/project/components/bundle.css"), "utf8");

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) return files(p);
    return /\.(tsx|ts|css)$/.test(name) && !name.endsWith("design.contract.test.ts") ? [p] : [];
  });
}

const sources = files(SRC).map((p) => ({ p, text: readFileSync(p, "utf8") }));
const defined = new Set(BUNDLE.match(/\.ng-[a-z0-9_-]+/g)!.map((c) => c.slice(1)));

describe("design contract", () => {
  it("every ng- class used in src exists in bundle.css", () => {
    const unknown: string[] = [];
    for (const { p, text } of sources) {
      for (const m of text.matchAll(/(?<![\w-])ng-[a-z0-9-]+(?:--[a-z0-9-]+)?(?:__[a-z0-9-]+)?/g)) {
        if (!defined.has(m[0])) unknown.push(`${p}: ${m[0]}`);
      }
    }
    expect(unknown).toEqual([]);
  });

  it("src has no colour or font-family literals", () => {
    const bad: string[] = [];
    for (const { p, text } of sources) {
      for (const re of [/#[0-9a-fA-F]{3,8}\b/g, /rgb\(/g, /hsl\(/g, /font-family:/g]) {
        for (const m of text.matchAll(re)) bad.push(`${p}: ${m[0]}`);
      }
    }
    expect(bad).toEqual([]);
  });
});
