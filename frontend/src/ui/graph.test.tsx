import { act, fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { GraphNode as Node } from "../api/types";
import { graphNode } from "../test/fixtures";
import { GraphCanvas } from "./GraphCanvas";
import { GraphNode } from "./GraphNode";

const LONG =
  "What do astronauts who flew in low Earth orbit between 1961 and 2024 report about seeing the Wall, " +
  "and under which light, weather and viewing-angle conditions did they say they saw it or did not?";

function plan(): Node[] {
  return [
    graphNode({ id: "r", display_id: "R", kind: "Synthesis", question: "Why is the Great Wall visible from space?" }),
    graphNode({ id: "p1", display_id: "P1", kind: "Premise check", parent_id: "r", depth: 1 }),
    graphNode({ id: "d2", display_id: "D2", parent_id: "r", depth: 1, depends_on: ["p1"], question: LONG }),
    graphNode({ id: "d3", display_id: "D3", parent_id: "r", depth: 1, depends_on: ["p1"] }),
    graphNode({ id: "d5", display_id: "D5", parent_id: "r", depth: 1, depends_on: ["p1"], inclusion: "Superseded" }),
    graphNode({ id: "d2a", display_id: "D2a", parent_id: "d2", depth: 2 }),
    graphNode({ id: "v1", display_id: "V1", kind: "Verification", parent_id: "r", depth: 1, depends_on: ["p1", "d3"] }),
  ];
}

const nodeEl = (displayId: string) => screen.getByText(displayId, { selector: ".ng-node__top span" }).closest(".ng-node")!;

describe("GraphNode", () => {
  it('GraphNode in plan mode is ng-node--proposed with the word "Planned"', () => {
    const { container } = render(<GraphNode node={graphNode({ id: "d2", display_id: "D2" })} selected={false} onSelect={() => {}} mode="plan" />);
    const el = container.querySelector(".ng-node")!;
    expect(el).toHaveClass("ng-node", "ng-node--proposed");
    expect(el.querySelector(".ng-node__state")).toHaveTextContent("◌ Planned");
    expect(el.querySelector(".ng-node__kind")).toHaveTextContent("DEEP");
    expect(container.querySelector(".ng-live, .ng-pulse")).toBeNull();
  });

  it("board mode uses the node's own state word and class", () => {
    const { container } = render(
      <GraphNode node={graphNode({ id: "x", status: "Running", activity: "Extracting" })} selected={false} onSelect={() => {}} mode="board" />,
    );
    const el = container.querySelector(".ng-node")!;
    expect(el).toHaveClass("ng-node--running");
    expect(el.querySelector(".ng-node__state")).toHaveTextContent("● Running");
    expect(el.querySelector(".ng-pulse")).not.toBeNull();
    expect(el.querySelector(".ng-node__sub")).toHaveTextContent("Extracting");
  });

  it("an instructed node carries the mark with its count; Task 9 can set the mark and Removed", () => {
    const { container, rerender } = render(
      <GraphNode node={graphNode({ id: "x", instruction_count: 2 })} selected={false} onSelect={() => {}} mode="plan" />,
    );
    expect(container.querySelector(".ng-node__mark")).toHaveTextContent("✎︎ 2");
    rerender(<GraphNode node={graphNode({ id: "x" })} selected={false} onSelect={() => {}} mode="plan" mark="new" />);
    expect(container.querySelector(".ng-node__mark")).toHaveTextContent("new");
    rerender(<GraphNode node={graphNode({ id: "x", inclusion: "Superseded" })} selected={false} onSelect={() => {}} mode="plan" removed />);
    expect(container.querySelector(".ng-node")).toHaveClass("ng-node--excluded");
    expect(container.querySelector(".ng-node__state")).toHaveTextContent("− Removed");
  });

  it("selection adds is-selected and never a steer class", () => {
    const onSelect = vi.fn();
    const { container } = render(<GraphNode node={graphNode({ id: "x", instruction_count: 1 })} selected onSelect={onSelect} mode="plan" />);
    const el = container.querySelector(".ng-node")!;
    expect(el).toHaveClass("is-selected");
    expect(el.className).not.toMatch(/steer|live/);
    expect(container.innerHTML).not.toMatch(/ng-[a-z-]*steer/);
    fireEvent.click(el);
    expect(onSelect).toHaveBeenCalledWith("x");
  });

  it("question is not shortened in the DOM", () => {
    const { container } = render(<GraphNode node={graphNode({ id: "x", question: LONG })} selected={false} onSelect={() => {}} mode="plan" />);
    expect(container.querySelector(".ng-node__q")!.textContent).toBe(LONG);
  });

  it("fold shows − when expanded and the hidden count when collapsed", () => {
    const { container, rerender } = render(<GraphNode node={graphNode({ id: "x" })} selected={false} onSelect={() => {}} mode="board" fold="−" />);
    expect(container.querySelector(".ng-node__fold")).toHaveTextContent("−");
    rerender(<GraphNode node={graphNode({ id: "x" })} selected={false} onSelect={() => {}} mode="board" fold="+4" />);
    expect(container.querySelector(".ng-node__fold")).toHaveTextContent("+4");
  });
});

describe("GraphCanvas", () => {
  it("draws every node in ng-canvas with edges of both kinds", () => {
    const { container } = render(<GraphCanvas nodes={plan()} selectedId={null} onSelect={() => {}} mode="plan" />);
    expect(container.querySelector(".ng-canvas")).not.toBeNull();
    expect(container.querySelectorAll(".ng-canvas .ng-node")).toHaveLength(7);
    expect(container.querySelectorAll("path.ng-edge:not(.ng-edge--dep)")).toHaveLength(6);
    // D3 → V1 is drawn; the I2 waits on premise checks are not (the premise check says "runs first").
    const deps = container.querySelectorAll("path.ng-edge--dep");
    expect(deps).toHaveLength(1);
    expect(deps[0]).toHaveAttribute("data-edge", "d3>v1");
    expect(deps[0].getAttribute("marker-end")).toMatch(/^url\(#/);
    expect(nodeEl("P1").querySelector(".ng-node__sub")).toHaveTextContent("runs first");
    expect(nodeEl("V1").querySelector(".ng-node__sub")).toHaveTextContent("after D3");
  });

  it("superseded node is ng-node--excluded and its edges ng-edge--off", () => {
    const { container } = render(<GraphCanvas nodes={plan()} selectedId={null} onSelect={() => {}} mode="plan" />);
    expect(nodeEl("D5")).toHaveClass("ng-node--excluded");
    expect(nodeEl("D5")).not.toHaveClass("ng-node--proposed");
    expect(container.querySelector('[data-edge="r>d5"]')).toHaveClass("ng-edge", "ng-edge--off");
    expect(container.querySelector('[data-edge="r>d3"]')).not.toHaveClass("ng-edge--off");
  });

  it("plan mode has no live class anywhere; board mode lights the path to running work", () => {
    const nodes = plan().map((n) => ({ ...n, status: n.id === "d2a" ? "Running" : "Pending" }) as Node);
    const { container, rerender } = render(<GraphCanvas nodes={nodes} selectedId={null} onSelect={() => {}} mode="plan" />);
    expect(container.innerHTML).not.toMatch(/--live/);
    rerender(<GraphCanvas nodes={nodes} selectedId={null} onSelect={() => {}} mode="board" />);
    expect(container.querySelector('[data-edge="r>d2"]')).toHaveClass("ng-edge--live");
    expect(container.querySelector('[data-edge="d2>d2a"]')).toHaveClass("ng-edge--live");
    expect(container.querySelector('[data-edge="r>d3"]')).not.toHaveClass("ng-edge--live");
  });

  it("selection adds is-selected and never a steer class", () => {
    const onSelect = vi.fn();
    const { container } = render(<GraphCanvas nodes={plan()} selectedId="d3" onSelect={onSelect} mode="plan" />);
    expect(nodeEl("D3")).toHaveClass("is-selected");
    expect(container.querySelectorAll(".is-selected")).toHaveLength(1);
    expect(nodeEl("D3").className).not.toMatch(/steer/);
    fireEvent.click(nodeEl("P1"));
    expect(onSelect).toHaveBeenCalledWith("p1");
  });

  it("question is not shortened in the DOM", () => {
    render(<GraphCanvas nodes={plan()} selectedId={null} onSelect={() => {}} mode="plan" />);
    expect(nodeEl("D2").querySelector(".ng-node__q")!.textContent).toBe(LONG);
  });

  it("double-click folds a branch and shows the hidden count", () => {
    render(<GraphCanvas nodes={plan()} selectedId={null} onSelect={() => {}} mode="board" />);
    expect(nodeEl("D2").querySelector(".ng-node__fold")).toHaveTextContent("−");
    expect(nodeEl("D3").querySelector(".ng-node__fold")).toBeNull();
    fireEvent.doubleClick(nodeEl("D2"));
    expect(screen.queryByText("D2a")).toBeNull();
    expect(nodeEl("D2").querySelector(".ng-node__fold")).toHaveTextContent("+1");
    fireEvent.doubleClick(nodeEl("D2"));
    expect(screen.getByText("D2a")).toBeInTheDocument();
  });

  it("drag pans and the wheel zooms the graph", () => {
    const { container } = render(<GraphCanvas nodes={plan()} selectedId={null} onSelect={() => {}} mode="plan" />);
    const canvas = container.querySelector(".ng-canvas")!;
    const world = canvas.firstElementChild as HTMLElement;
    const before = world.style.transform;
    fireEvent.mouseDown(canvas, { button: 0, clientX: 100, clientY: 100 });
    fireEvent.mouseMove(window, { clientX: 160, clientY: 130 });
    fireEvent.mouseUp(window);
    expect(world.style.transform).toBe(shift(before, 60, 30));
    act(() => {
      canvas.dispatchEvent(new WheelEvent("wheel", { deltaY: -100, clientX: 0, clientY: 0, bubbles: true, cancelable: true }));
    });
    expect(scaleOf(world.style.transform)).toBeGreaterThan(1);
    fireEvent.click(screen.getByRole("button", { name: "Fit" }));
    expect(world.style.transform).toBe(before);
  });

  it("a drag that starts on a node pans and does not select it", () => {
    const onSelect = vi.fn();
    const { container } = render(<GraphCanvas nodes={plan()} selectedId={null} onSelect={onSelect} mode="plan" />);
    const world = container.querySelector(".ng-canvas")!.firstElementChild as HTMLElement;
    const before = world.style.transform;
    fireEvent.mouseDown(nodeEl("D3"), { button: 0, clientX: 10, clientY: 10 });
    fireEvent.mouseMove(window, { clientX: 80, clientY: 10 });
    fireEvent.mouseUp(window);
    fireEvent.click(nodeEl("D3"));
    expect(world.style.transform).toBe(shift(before, 70, 0));
    expect(onSelect).not.toHaveBeenCalled();
    fireEvent.click(nodeEl("D3"));
    expect(onSelect).toHaveBeenCalledWith("d3");
  });

  it("renders the toolbar slot next to Fit", () => {
    render(
      <GraphCanvas nodes={plan()} selectedId={null} onSelect={() => {}} mode="plan"
        toolbar={<span className="ng-label">Proposed plan · version 3</span>} />,
    );
    const bar = screen.getByText("Proposed plan · version 3").closest(".ng-toolbar")!;
    expect(bar).toContainElement(screen.getByRole("button", { name: "Fit" }));
  });
});

function parse(t: string) {
  const m = /translate\((-?[\d.]+)px, (-?[\d.]+)px\) scale\(([\d.]+)\)/.exec(t)!;
  return { x: Number(m[1]), y: Number(m[2]), k: Number(m[3]) };
}
function shift(t: string, dx: number, dy: number) {
  const { x, y, k } = parse(t);
  return `translate(${x + dx}px, ${y + dy}px) scale(${k})`;
}
const scaleOf = (t: string) => parse(t).k;
