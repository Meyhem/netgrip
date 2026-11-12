import { readFileSync } from "node:fs";
import { join } from "node:path";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CLAIM_STATUS, INCLUSION_PILL, INVESTIGATION_PILL, NODE_PILL, PAUSE_ORIGIN, KIND_CODE, type PillSpec } from "./vocab";
import { StatusPill } from "./StatusPill";

const COMPONENTS = join(__dirname, "../../../design-system/project/components");

/** Rows of the markdown table whose first header cell is `first`. */
function table(readme: string, first: string): string[][] {
  const text = readFileSync(join(COMPONENTS, readme, "README.md"), "utf8");
  const lines = text.split("\n");
  const start = lines.findIndex((l) => l.startsWith(`| ${first} |`));
  const rows: string[][] = [];
  for (const line of lines.slice(start + 2)) {
    if (!line.startsWith("|")) break;
    rows.push(line.split("|").slice(1, -1).map((c) => c.trim()));
  }
  return rows;
}

function expected(glyphCell: string, toneCell: string) {
  const pulses = glyphCell.includes("(pulses)");
  const glyph = glyphCell.replace("(pulses)", "").trim();
  const words = toneCell.split(/[,(]/).map((w) => w.trim());
  const tone = words[0] === "idle" ? "idle" : words[0];
  return { glyph, tone, ghost: words.includes("ghost"), hollow: words.includes("hollow"), pulses };
}

function actual(spec: PillSpec) {
  return { glyph: spec.glyph, tone: spec.tone, ghost: !!spec.ghost, hollow: !!spec.hollow, pulses: !!spec.pulses };
}

describe("vocabulary matches the design system READMEs", () => {
  it("investigation pills", () => {
    const rows = table("StatusPill", "Investigation");
    expect(rows).toHaveLength(7);
    for (const [word, glyph, tone] of rows) {
      const entry = Object.values(INVESTIGATION_PILL).find((p) => p.word === word);
      expect(entry, word).toBeDefined();
      expect(actual(entry!), word).toEqual(expected(glyph, tone));
    }
    expect(INVESTIGATION_PILL.Planning).toMatchObject({ glyph: "✎︎", word: "Plan review", tone: "steer" });
  });

  it("node pills", () => {
    const rows = table("StatusPill", "Node execution");
    expect(rows).toHaveLength(8);
    for (const [word, glyph, tone] of rows) {
      const entry = NODE_PILL[word as keyof typeof NODE_PILL];
      expect(entry, word).toBeDefined();
      expect(actual(entry), word).toEqual(expected(glyph, tone));
    }
    expect(NODE_PILL["Waiting on children"]).toMatchObject({ glyph: "◔", tone: "live", hollow: true });
    expect(NODE_PILL.Rejected).toMatchObject({ glyph: "⊘", tone: "danger", hollow: true });
  });

  it("claim statuses", () => {
    const rows = table("ClaimStatus", "Status");
    expect(rows).toHaveLength(5);
    for (const [word, glyph, tone] of rows) {
      expect(actual(CLAIM_STATUS[word as keyof typeof CLAIM_STATUS]), word).toEqual(expected(glyph, tone));
    }
  });

  it("inclusion pills, kind codes, pause origins", () => {
    expect(INCLUSION_PILL.Ignored).toMatchObject({ glyph: "⦸", word: "Ignored by you", tone: "steer", hollow: true });
    expect(INCLUSION_PILL.Superseded).toMatchObject({ glyph: "↺", word: "Superseded by re-plan", tone: "idle", ghost: true });
    expect(KIND_CODE).toEqual({ "Premise check": "PRM", Divergent: "DIV", "Deep-dive": "DEEP", Verification: "VER", Synthesis: "SYN" });
    expect(Object.values(PAUSE_ORIGIN)).toEqual([
      "by you", "spending limit", "model service unavailable", "search unavailable", "key rejected", "credit exhausted",
    ]);
  });
});

describe("StatusPill", () => {
  it("renders glyph plus word with the tone class", () => {
    const { container } = render(<StatusPill kind="node" state="Rejected" />);
    const pill = container.querySelector(".ng-pill")!;
    expect(pill).toHaveClass("ng-pill--danger", "ng-pill--hollow");
    expect(pill.querySelector("i")).toHaveTextContent("⊘");
    expect(pill).toHaveTextContent("⊘Rejected");
  });

  it("Paused renders its origin", () => {
    render(<StatusPill kind="investigation" state="Paused" origin="spending_limit" />);
    expect(screen.getByText(/Paused · spending limit/)).toHaveClass("ng-pill", "ng-pill--warn");
  });

  it("Running pulses", () => {
    const { container } = render(<StatusPill kind="investigation" state="Running" />);
    expect(container.querySelector(".ng-pill--live .ng-pulse")).toHaveTextContent("●");
  });
});
