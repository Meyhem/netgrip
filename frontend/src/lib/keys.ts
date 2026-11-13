import { useEffect, useRef } from "react";

/** What each board key does. A missing handler leaves the key alone. */
export interface BoardKeyHandlers {
  instruct?: () => void;
  deeper?: () => void;
  focus?: () => void;
  pause?: () => void;
  ignore?: () => void;
  rerun?: () => void;
  log?: () => void;
  menu?: () => void;
  escape?: () => void;
}

const KEYS: Record<string, keyof BoardKeyHandlers> = {
  i: "instruct", d: "deeper", f: "focus", " ": "pause", x: "ignore", r: "rerun", l: "log", ".": "menu", Escape: "escape",
};

/** True while the user types: a key then types a character and steers nothing. */
export function typing(target: EventTarget | null): boolean {
  return !!(target as HTMLElement | null)?.closest?.("input, textarea, select, [contenteditable]");
}

/** The board's keyboard (ScreenControlBoard): `I` instruct, `D` go deeper, `F` run only this
 * branch (again: run everything), `Space` pause or resume the branch, `X` ignore or restore,
 * `R` re-run, `L` log, `.` node menu, `Esc` clear selection. Ignored while focus is in an
 * input, textarea or contenteditable, or while a modifier is held. A dialog takes Escape. */
export function useBoardKeys(handlers: BoardKeyHandlers): void {
  const ref = useRef(handlers);
  ref.current = handlers;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey || typing(e.target)) return;
      const name = KEYS[e.key.length === 1 ? e.key.toLowerCase() : e.key];
      if (!name) return;
      if (name === "escape" && document.querySelector('[role="dialog"]')) return;
      const fn = ref.current[name];
      if (!fn) return;
      // A focused button would click on Space: the key steers the branch instead.
      e.preventDefault();
      fn();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
