import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";
import { forgetSelection, useSelection } from "./selection";

beforeEach(() => { forgetSelection("inv-1"); forgetSelection("inv-2"); });

describe("useSelection", () => {
  it("starts with nothing selected (the inspector shows the root)", () => {
    const { result } = renderHook(() => useSelection("inv-1"));
    expect(result.current.selectedId).toBeNull();
  });

  it("one selection per investigation, shared by every pane", () => {
    const a = renderHook(() => useSelection("inv-1"));
    const b = renderHook(() => useSelection("inv-1"));
    const other = renderHook(() => useSelection("inv-2"));
    act(() => a.result.current.select("n-3"));
    expect(b.result.current.selectedId).toBe("n-3");
    expect(other.result.current.selectedId).toBeNull();
    act(() => b.result.current.select(null));
    expect(a.result.current.selectedId).toBeNull();
  });
});
