import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DurableEvent, GraphNode, Snapshot } from "../api/types";
import { emptySnapshot } from "../state/reduce";
import { graphNode } from "../test/fixtures";
import { ExecutionOrder } from "./ExecutionOrder";

function snap(nodes: GraphNode[], over: Partial<Snapshot> = {}, state: Snapshot["investigation"]["state"] = "Running"): Snapshot {
  const base = emptySnapshot("inv-1");
  return { ...base, seq: 100, nodes, investigation: { ...base.investigation, state }, schedule: { order: [], reasons: {}, slots: 6 }, ...over };
}

const ev = (seq: number, type: string, node_id: string, data: Record<string, unknown> = {}): DurableEvent => ({
  seq, investigation_id: "inv-1", type, v: 1, at: `2026-11-13T10:00:${String(seq).padStart(2, "0")}Z`,
  actor: "node", node_id, command_id: null, data,
});

const R = graphNode({ id: "R", display_id: "R", kind: "Synthesis", status: "Waiting on children", question: "Synthesis" });
const kid = (id: string, over: Partial<GraphNode> = {}) => graphNode({ id, parent_id: "R", depth: 1, status: "Pending", ...over });

function show(s: Snapshot, events: DurableEvent[] = [], selectedId: string | null = null, onSelect = vi.fn()) {
  const utils = render(<ExecutionOrder s={s} events={events} selectedId={selectedId} onSelect={onSelect} />);
  return { ...utils, onSelect };
}

const heads = () => [...document.querySelectorAll(".ng-queue__head")].map((h) => h.textContent);
const rowIds = () => [...document.querySelectorAll(".ng-qrow")].map((r) => r.getAttribute("data-node-id"));

describe("ExecutionOrder", () => {
  it("sections render in fixed order even when empty", () => {
    show(snap([]));
    const labels = [...document.querySelectorAll(".ng-queue__head .ng-label")].map((l) => l.textContent);
    expect(labels).toEqual(["Now", "Next", "Done", "Not running"]);
    expect(document.querySelectorAll(".ng-qrow")).toHaveLength(0);
  });

  it("now shows the activity line, time in this run and the slots in use", () => {
    vi.useFakeTimers({ now: new Date("2026-11-13T10:02:51Z") });
    try {
      const s = snap([R, kid("A", { display_id: "D1b", question: "Textbook repetition", status: "Running", activity: "Reading" })]);
      show(s, [ev(10, "node.started", "A"), ev(11, "node.activity", "A", { activity: "Reading", detail: "britannica.com/topic/Great-Wall", retry: null, step: "read" })]);
      expect(heads()[0]).toBe("Now1 running · 6 slots");
      const row = document.querySelector('.ng-qrow[data-node-id="A"]')!;
      expect(row.querySelector(".ng-qrow__q")).toHaveTextContent("D1b Textbook repetition");
      expect(row.querySelector(".ng-activity__verb")).toHaveTextContent("Reading");
      expect(row.querySelector(".ng-activity__what")).toHaveTextContent("britannica.com/topic/Great-Wall");
      expect(row.querySelector(".ng-qrow__side")).toHaveTextContent("2:41");
      expect(row.querySelector(".ng-qrow__n .ng-pulse")).toHaveClass("ng-live");
    } finally {
      vi.useRealTimers();
    }
  });

  it("paused head and empty Now", () => {
    show(snap([R, kid("A", { status: "Running", activity: "Reading" })], {}, "Paused"));
    expect(heads()[0]).toBe("NowNothing runs while paused");
    expect(document.querySelector('.ng-qrow[data-node-id="A"]')).toBeNull();
    expect(document.querySelector(".ng-pulse")).toBeNull();
  });

  it("empty Next copy", () => {
    show(snap([graphNode({ id: "R", status: "Running" })]));
    expect(screen.getByText("Nothing queued. The orchestrator is deciding.")).toBeInTheDocument();
  });

  it("next shows position and wait reason in the scheduler's order", () => {
    const s = snap([R, kid("A"), kid("B")], { schedule: { order: ["B", "A"], reasons: { B: "slot", A: "dependency:B" }, slots: 6 } });
    show(s);
    const next = [...document.querySelectorAll(".ng-qrow")].filter((r) => r.getAttribute("data-section") === "next");
    expect(next.map((r) => r.getAttribute("data-node-id"))).toEqual(["B", "A", "R"]);
    expect(next[0].querySelector(".ng-qrow__n")).toHaveTextContent("1");
    expect(next[0].querySelector(".ng-qrow__meta")).toHaveTextContent("○ waits for a free slot");
    expect(next[1].querySelector(".ng-qrow__meta")).toHaveTextContent("○ waits for B (dependency)");
    expect(next[2].querySelector(".ng-qrow__meta")).toHaveTextContent("◔ waits for A, B");
  });

  it("done shows the verdict and confidence, or the failure reason", () => {
    const s = snap([
      R,
      kid("C", { status: "Completed", verdict: { text: "Said he could not see it", confidence: "high" } }),
      kid("F", { status: "Failed" }),
    ]);
    show(s, [ev(20, "node.completed", "C"), ev(21, "node.failed", "F", { reason: "Every page timed out.", auto_retry_used: true })]);
    const c = document.querySelector('.ng-qrow[data-node-id="C"]')!;
    expect(c.querySelector(".ng-qrow__meta")).toHaveTextContent("Said he could not see it · high");
    expect(c.querySelector(".ng-qrow__n .ng-ok")).toHaveTextContent("✓");
    const f = document.querySelector('.ng-qrow[data-node-id="F"]')!;
    expect(f.querySelector(".ng-qrow__meta")).toHaveTextContent("Every page timed out.");
    expect(f.querySelector(".ng-qrow__n .ng-danger")).toHaveTextContent("✕");
    expect(heads()[2]).toBe("Done2 · newest first");
  });

  it("refuted premise row uses the danger cross", () => {
    const s = snap([R, kid("P1", { kind: "Premise check", status: "Completed", verdict: { text: "No.", confidence: "high" } })], {
      premises: [{ id: "pr-1", text: "Visible from orbit", node_id: "P1", outcome: "refuted" }],
    });
    show(s, [ev(20, "node.completed", "P1")]);
    const row = document.querySelector('.ng-qrow[data-node-id="P1"]')!;
    expect(row.querySelector(".ng-qrow__n .ng-danger")).toHaveTextContent("✕");
    expect(row.querySelector(".ng-ok")).toBeNull();
    expect(row.querySelector(".ng-qrow__meta")).toHaveTextContent("Premise refuted · high");
  });

  it("not running says who excluded it and offers no Restore yet", () => {
    const s = snap([
      R,
      kid("I", { display_id: "D4", status: "Completed", inclusion: "Ignored" }),
      kid("S", { status: "Pending", inclusion: "Superseded" }),
      kid("X", { status: "Rejected" }),
    ], { instructions: [{ id: "i-1", node_id: "R", text: "Narrow it", state: "applied", queued_seq: 30, applied_seq: 31, diff: null, undone: false }] });
    show(s, [
      { ...ev(30, "node.inclusion_changed", "I", { node_ids: ["I"], inclusion: "Ignored", by: "user", instruction_id: null }), actor: "user", node_id: null },
      ev(31, "node.inclusion_changed", "S", { node_ids: ["S"], inclusion: "Superseded", by: "replan", instruction_id: "i-1" }),
      ev(32, "node.rejected", "X", { reason: "does not help answer the root goal", duplicate_of: null }),
    ]);
    const meta = (id: string) => document.querySelector(`.ng-qrow[data-node-id="${id}"] .ng-qrow__meta`)!.textContent;
    expect(meta("I")).toMatch(/^Ignored by you · \d\d:\d\d$/);
    expect(meta("S")).toBe("Superseded by your instruction on R");
    expect(meta("X")).toBe("Rejected: does not help answer the root goal");
    expect(document.querySelector('.ng-qrow[data-node-id="I"]')).toHaveClass("is-off");
    expect(screen.queryByText(/Restore/)).toBeNull();
  });

  it("clicking a row calls select with the node id", () => {
    const { onSelect } = show(snap([R, kid("A")]));
    fireEvent.click(within(document.querySelector('.ng-qrow[data-node-id="A"]') as HTMLElement).getByText(/Question of A/));
    expect(onSelect).toHaveBeenCalledWith("A");
  });

  it("arrow keys move selection", () => {
    const s = snap([R, kid("A", { status: "Running", activity: "Searching" }), kid("B"), kid("C", { status: "Completed" })]);
    const { onSelect, rerender } = show(s, [], null);
    expect(rowIds()).toEqual(["A", "B", "R", "C"]);
    const pane = screen.getByRole("listbox", { name: "Execution order" });
    fireEvent.keyDown(pane, { key: "ArrowDown" });
    expect(onSelect).toHaveBeenLastCalledWith("A");
    rerender(<ExecutionOrder s={s} events={[]} selectedId="B" onSelect={onSelect} />);
    expect(document.querySelector('.ng-qrow[data-node-id="B"]')).toHaveClass("is-selected");
    fireEvent.keyDown(pane, { key: "ArrowDown" });
    expect(onSelect).toHaveBeenLastCalledWith("R");
    fireEvent.keyDown(pane, { key: "ArrowUp" });
    expect(onSelect).toHaveBeenLastCalledWith("A");
    rerender(<ExecutionOrder s={s} events={[]} selectedId="C" onSelect={onSelect} />);
    onSelect.mockClear();
    fireEvent.keyDown(pane, { key: "ArrowDown" });
    expect(onSelect).not.toHaveBeenCalled();
  });
});
