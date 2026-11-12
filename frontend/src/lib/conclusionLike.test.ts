import { describe, expect, it } from "vitest";
import { conclusionLike } from "./conclusionLike";

describe("conclusionLike", () => {
  it.each([
    "Conclude that the Wall is visible.",
    "The answer is yes, so just confirm it.",
    "Prove that astronauts saw it.",
    "Show that it is visible from orbit.",
    "Make sure the report says it is a myth.",
    "It is obvious that the Wall can be seen.",
    "The wall is obviously visible, just confirm it.",
  ])("true for %j", (text) => {
    expect(conclusionLike(text)).toBe(true);
  });

  it.each([
    "",
    "Leave out tourism marketing. Include where the claim came from.",
    "Don't spend time on satellites and radar, only human eyes.",
    "Show the sources for each astronaut account.",
    "Check whether the answer depends on the weather.",
  ])("false for %j", (text) => {
    expect(conclusionLike(text)).toBe(false);
  });
});
