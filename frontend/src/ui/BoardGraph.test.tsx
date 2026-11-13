import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DurableEvent, GraphNode, Snapshot } from "../api/types";
import { emptySnapshot } from "../state/reduce";
import { graphNode } from "../test/fixtures";
import { BoardGraph } from "./BoardGraph";

function snap(nodes: GraphNode[], over: Partial<Snapshot> = {}, state: Snapshot["investigation"]["state"] = "Running"): Snapshot {
  const base = emptySnapshot("inv-1");
  return { ...base, seq: 419, nodes, investigation: { ...base.investigation, state }, schedule: { order: [], reasons: {}, slots: 6 }, ...over };
}

const ev = (seq: number, type: string, node_id: string, data: Record<string, unknown> = {}): DurableEvent => ({
  seq, investigation_id: "inv-1", type, v: 1, at: `2026-11-13T10:00:${String(seq % 60).padStart(2, "0")}Z`,
  actor: "node", node_id, command_id: null, data,
});

const LONG = "Q".repeat(200) + "W".repeat(200);

const R = graphNode({ id: "R", display_id: "R", kind: "Synthesis", status: "Waiting on children", question: "Root" });
const kid = (id: string, over: Partial<GraphNode> = {}) => graphNode({ id, display_id: id, parent_id: "R", depth: 1, status: "Pending", ...over });

function graph(): GraphNode[] {
  return [
    R,
    kid("D1", { status: "Completed", verdict: { text: "Not visible", confidence: "high" } }),
    kid("D1a", { parent_id: "D1", depth: 2, status: "Completed" }),
    kid("D1b", { parent_id: "D1", depth: 2, status: "Failed" }),
    kid("D2", { status: "Running", activity: "Reading", question: LONG }),
    kid("D2a", { parent_id: "D2", depth: 2 }),
    kid("D3", { inclusion: "Ignored" }),
    kid("D3a", { parent_id: "D3", depth: 2, inclusion: "Ignored" }),
  ];
}

const nodeEl = (id: string) => document.querySelector(`.ng-canvas [data-node="${id}"]`);
const world = () => document.querySelector(".ng-canvas")!.firstElementChild as HTMLElement;

function show(s: Snapshot, events: DurableEvent[] = [], selectedId: string | null = null, onSelect = vi.fn(), live = true) {
  const utils = render(<BoardGraph s={s} events={events} selectedId={selectedId} onSelect={onSelect} live={live} />);
  return { ...utils, onSelect };
}

describe("BoardGraph", () => {
  it("toolbar shows node counts in mono and the last applied seq", () => {
    show(snap(graph()));
    const bar = document.querySelector(".ng-toolbar")!;
    expect(bar.querySelector(".ng-label")).toHaveTextContent("Graph");
    // 7 approved nodes below the root; 1 running; 2 excluded.
    expect(screen.getByText(/nodes · 1 running/)).toHaveClass("ng-mono");
    expect(screen.getByText(/nodes · 1 running/).textContent).toMatch(/^7 \/ \d+ nodes · 1 running · 2 excluded$/);
    expect(screen.getByText(`current to #${"0419"}`)).toHaveClass("ng-mono");
    for (const name of ["Fit", "Collapse completed"]) expect(screen.getByRole("button", { name })).toBeInTheDocument();
    expect(screen.getByLabelText("Show excluded")).toBeChecked();
    expect(screen.getByLabelText("Follow active")).toBeInTheDocument();
  });

  it("running node has ng-node--running and an activity line", () => {
    show(snap(graph()), [ev(10, "node.started", "D2"), ev(11, "node.activity", "D2", { activity: "Reading", detail: "britannica.com/topic/Great-Wall", retry: null })]);
    const d2 = nodeEl("D2")!;
    expect(d2).toHaveClass("ng-node--running");
    expect(d2.querySelector(".ng-node__sub .ng-activity__verb")).toHaveTextContent("Reading");
    expect(d2.querySelector(".ng-node__sub .ng-activity__what")).toHaveTextContent("britannica.com/topic/Great-Wall");
    expect(d2.querySelector(".ng-pulse")).not.toBeNull();
    // Completed: line 3 is the verdict summary.
    expect(nodeEl("D1")!.querySelector(".ng-node__sub")).toHaveTextContent("Not visible · high");
  });

  it("a 400-character question is on the node in full, clamped by CSS only", () => {
    show(snap(graph()));
    const q = nodeEl("D2")!.querySelector(".ng-node__q")!;
    expect(q.textContent).toBe(LONG);
    expect(LONG).toHaveLength(400);
  });

  it("completed graph contains no live class", () => {
    const done = graph().map((n) => ({ ...n, status: "Completed" }) as GraphNode);
    show(snap(done, {}, "Completed"));
    expect(document.querySelector(".ng-canvas")!.innerHTML).not.toMatch(/live|ng-pulse/);
  });

  it("edges to a running node are ng-edge--live", () => {
    show(snap(graph()));
    expect(document.querySelector('[data-edge="R>D2"]')).toHaveClass("ng-edge--live");
    expect(document.querySelector('[data-edge="R>D1"]')).not.toHaveClass("ng-edge--live");
    expect(document.querySelector('[data-edge="D2>D2a"]')).not.toHaveClass("ng-edge--live");
  });

  it("no pulse when paused or not live", () => {
    const { unmount } = show(snap(graph()), [], null, vi.fn(), false);
    expect(document.querySelector(".ng-canvas .ng-pulse")).toBeNull();
    unmount();
    show(snap(graph(), {}, "Paused"));
    expect(document.querySelector(".ng-canvas .ng-pulse")).toBeNull();
  });

  it("Show excluded off hides excluded nodes; on shows them hatched", () => {
    show(snap(graph()));
    expect(nodeEl("D3")).toHaveClass("ng-node--excluded");
    expect(nodeEl("D3a")).toHaveClass("ng-node--excluded");
    fireEvent.click(screen.getByLabelText("Show excluded"));
    expect(nodeEl("D3")).toBeNull();
    expect(nodeEl("D3a")).toBeNull();
    expect(nodeEl("D2")).not.toBeNull();
    fireEvent.click(screen.getByLabelText("Show excluded"));
    expect(nodeEl("D3")).toHaveClass("ng-node--excluded");
  });

  it("Collapse completed folds finished branches and shows the count", () => {
    show(snap(graph()));
    expect(nodeEl("D1a")).not.toBeNull();
    const btn = screen.getByRole("button", { name: "Collapse completed" });
    expect(btn).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(btn);
    expect(btn).toHaveAttribute("aria-pressed", "true");
    expect(nodeEl("D1a")).toBeNull();
    expect(nodeEl("D1b")).toBeNull();
    expect(nodeEl("D1")!.querySelector(".ng-node__fold")).toHaveTextContent("+2");
    // A branch with work left stays open; the root is never folded.
    expect(nodeEl("D2a")).not.toBeNull();
    expect(nodeEl("R")).not.toBeNull();
    fireEvent.click(btn);
    expect(nodeEl("D1a")).not.toBeNull();
  });

  it("selection from outside pans the canvas", () => {
    const { rerender, onSelect } = show(snap(graph()));
    const before = world().style.transform;
    rerender(<BoardGraph s={snap(graph())} events={[]} selectedId="D2a" onSelect={onSelect} live />);
    const panned = world().style.transform;
    expect(panned).not.toBe(before);
    rerender(<BoardGraph s={snap(graph())} events={[]} selectedId="D1" onSelect={onSelect} live />);
    expect(world().style.transform).not.toBe(panned);
  });

  it("a click on the canvas selects without panning", () => {
    const onSelect = vi.fn();
    const { rerender } = show(snap(graph()), [], null, onSelect);
    const before = world().style.transform;
    fireEvent.click(nodeEl("D2a")!);
    expect(onSelect).toHaveBeenCalledWith("D2a");
    rerender(<BoardGraph s={snap(graph())} events={[]} selectedId="D2a" onSelect={onSelect} live />);
    expect(world().style.transform).toBe(before);
  });

  it("left and right arrows move to parent and first child", () => {
    const onSelect = vi.fn();
    show(snap(graph()), [], "D2", onSelect);
    const canvas = document.querySelector(".ng-canvas")!;
    expect(canvas).toHaveAttribute("tabindex", "0");
    fireEvent.keyDown(canvas, { key: "ArrowLeft" });
    expect(onSelect).toHaveBeenLastCalledWith("R");
    fireEvent.keyDown(canvas, { key: "ArrowRight" });
    expect(onSelect).toHaveBeenLastCalledWith("D2a");
    // Keys on a focused node reach the canvas too.
    fireEvent.keyDown(nodeEl("D2")!, { key: "ArrowLeft" });
    expect(onSelect).toHaveBeenCalledTimes(3);
  });

  it("Follow active pans to the most recently started node", () => {
    const nodes = graph().map((n) => (n.id === "D2a" ? { ...n, status: "Running" } as GraphNode : n));
    const { rerender, onSelect } = show(snap(nodes), [ev(10, "node.started", "D2")]);
    expect(screen.getByLabelText("Follow active")).toBeChecked();
    const before = world().style.transform;
    act(() => {
      rerender(<BoardGraph s={snap(nodes)} events={[ev(10, "node.started", "D2"), ev(12, "node.started", "D2a")]} selectedId={null} onSelect={onSelect} live />);
    });
    expect(world().style.transform).not.toBe(before);
    // Off: a newer start does not move the view.
    fireEvent.click(screen.getByLabelText("Follow active"));
    const held = world().style.transform;
    rerender(<BoardGraph s={snap(nodes)} events={[ev(10, "node.started", "D2a"), ev(13, "node.started", "D2")]} selectedId={null} onSelect={onSelect} live />);
    expect(world().style.transform).toBe(held);
  });
});
