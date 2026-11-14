import { describe, expect, it } from "vitest";
import { fuzzy, rank } from "./fuzzy";

const ids = [
  "anthropic/claude-sonnet-4.5",
  "anthropic/claude-opus-5.5",
  "openai/gpt-5.2",
  "openai/gpt-5.2-mini",
  "meta-llama/llama-4-maverick",
  "mistralai/mistral-large",
  "z-ai/octopus-1",
];
const top = (q: string) => rank(ids, q, (id) => [id]).map((h) => h.item);

describe("fuzzy", () => {
  it("matches words in any order", () => {
    expect(top("5.5 opus")[0]).toBe("anthropic/claude-opus-5.5");
  });

  it("matches letters in order with gaps and ignores separators", () => {
    expect(top("sonnet45")[0]).toBe("anthropic/claude-sonnet-4.5");
    expect(top("llmav")[0]).toBe("meta-llama/llama-4-maverick");
  });

  it("prefers a word start over a match inside a word", () => {
    expect(top("opus").slice(0, 2)).toEqual(["anthropic/claude-opus-5.5", "z-ai/octopus-1"]);
  });

  it("is case-insensitive and rejects text that lacks a word", () => {
    expect(fuzzy("openai/gpt-5.2", "GPT")).not.toBeNull();
    expect(fuzzy("openai/gpt-5.2", "gpt claude")).toBeNull();
  });

  it("marks the matched letters", () => {
    expect(fuzzy("openai/gpt-5.2", "gpt")!.marks).toEqual([7, 8, 9]);
  });

  it("an empty query keeps every item", () => {
    expect(top("")).toHaveLength(ids.length);
  });

  it("matches the name as well as the id", () => {
    const hits = rank([{ id: "x/abc-1", name: "Maverick Turbo" }], "turbo", (m) => [m.id, m.name]);
    expect(hits).toHaveLength(1);
    expect(hits[0].marks[1]).toEqual([9, 10, 11, 12, 13]);
  });
});
