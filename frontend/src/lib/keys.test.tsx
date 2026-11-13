import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useBoardKeys, type BoardKeyHandlers } from "./keys";

function Board({ handlers }: { handlers: BoardKeyHandlers }) {
  useBoardKeys(handlers);
  return <><textarea aria-label="composer" /><div contentEditable suppressContentEditableWarning data-testid="ce" /></>;
}

describe("useBoardKeys", () => {
  it("maps each key to its handler", () => {
    const h = { instruct: vi.fn(), deeper: vi.fn(), focus: vi.fn(), pause: vi.fn(), ignore: vi.fn(), rerun: vi.fn(), log: vi.fn(), menu: vi.fn(), escape: vi.fn() };
    render(<Board handlers={h} />);
    for (const key of ["i", "d", "f", " ", "x", "r", "l", ".", "Escape"]) fireEvent.keyDown(window, { key });
    for (const fn of Object.values(h)) expect(fn).toHaveBeenCalledTimes(1);
  });

  it("does nothing while typing in the composer", () => {
    const h = { ignore: vi.fn(), pause: vi.fn(), instruct: vi.fn() };
    const { getByLabelText, getByTestId } = render(<Board handlers={h} />);
    fireEvent.keyDown(getByLabelText("composer"), { key: "x" });
    fireEvent.keyDown(getByLabelText("composer"), { key: " " });
    fireEvent.keyDown(getByTestId("ce"), { key: "i" });
    expect(h.ignore).not.toHaveBeenCalled();
    expect(h.pause).not.toHaveBeenCalled();
    expect(h.instruct).not.toHaveBeenCalled();
  });

  it("ignores keys with a modifier held", () => {
    const h = { ignore: vi.fn(), rerun: vi.fn() };
    render(<Board handlers={h} />);
    fireEvent.keyDown(window, { key: "x", ctrlKey: true });
    fireEvent.keyDown(window, { key: "r", metaKey: true });
    expect(h.ignore).not.toHaveBeenCalled();
    expect(h.rerun).not.toHaveBeenCalled();
  });

  it("leaves Escape to an open dialog", () => {
    const escape = vi.fn();
    render(<><Board handlers={{ escape }} /><div role="dialog" /></>);
    fireEvent.keyDown(window, { key: "Escape" });
    expect(escape).not.toHaveBeenCalled();
  });
});
