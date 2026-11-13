import { describe, expect, it } from "vitest";
import type { GraphNode, InvestigationState, Snapshot } from "../api/types";
import { emptySnapshot } from "../state/reduce";
import { graphNode } from "../test/fixtures";
import { actionsFor, descendants } from "./NodeActions";

function board(node: Partial<GraphNode>, state: InvestigationState = "Running", extra: GraphNode[] = [], focus: string | null = null): { s: Snapshot; n: GraphNode } {
  const base = emptySnapshot("i");
  const n = graphNode({ id: "D2", parent_id: "R", depth: 1, status: "Pending", ...node });
  const nodes = [graphNode({ id: "R", kind: "Synthesis", status: "Waiting on children" }), n, ...extra];
  return { s: { ...base, nodes, focus_node_id: focus, investigation: { ...base.investigation, state } }, n };
}
const kids = [graphNode({ id: "a", parent_id: "D2", depth: 2 }), graphNode({ id: "b", parent_id: "D2", depth: 2 })];
const by = (a: ReturnType<typeof actionsFor>) => Object.fromEntries(a.map((x) => [x.type, x]));

describe("actionsFor", () => {
  it.each<[string, Partial<GraphNode>, string[]]>([
    ["Pending", { status: "Pending" }, ["instruct", "go_deeper", "run_only", "pause_branch", "ignore_branch"]],
    ["Running", { status: "Running" }, ["instruct", "go_deeper", "run_only", "pause_branch", "ignore_branch"]],
    ["Waiting on children", { status: "Waiting on children" }, ["instruct", "go_deeper", "run_only", "pause_branch", "ignore_branch"]],
    ["Paused", { status: "Paused" }, ["instruct", "go_deeper", "run_only", "resume_branch", "ignore_branch"]],
    ["Completed", { status: "Completed" }, ["instruct", "go_deeper", "run_only", "ignore_branch", "rerun_node"]],
    ["Failed", { status: "Failed" }, ["instruct", "go_deeper", "run_only", "ignore_branch", "rerun_node"]],
    ["Ignored", { status: "Completed", inclusion: "Ignored" }, ["instruct", "restore_branch"]],
  ])("enabled actions of a %s node", (_, over, enabled) => {
    const { s, n } = board(over);
    const a = actionsFor(n, s);
    expect(a.filter((x) => x.enabled).map((x) => x.type).sort()).toEqual([...enabled].sort());
    // Items that do not apply stay in the list, with the reason.
    for (const x of a.filter((x) => !x.enabled)) expect(x.consequence.length).toBeGreaterThan(5);
  });

  it("names the scope: this node and its descendants", () => {
    const { s, n } = board({ status: "Running" }, "Running", kids);
    expect(descendants(s, n.id)).toBe(2);
    expect(by(actionsFor(n, s)).ignore_branch.consequence).toContain("this node and its 2 descendants");
  });

  it("the root cannot be instructed once research has started", () => {
    const { s } = board({});
    const rootActions = by(actionsFor(s.nodes[0], s));
    expect(rootActions.instruct.enabled).toBe(false);
    expect(rootActions.ignore_branch.enabled).toBe(false);
  });

  it("run only this branch needs a running investigation; again it becomes Run everything", () => {
    const paused = board({ status: "Running" }, "Paused");
    expect(by(actionsFor(paused.n, paused.s)).run_only.enabled).toBe(false);
    const focused = board({ status: "Running" }, "Running", [], "D2");
    const a = by(actionsFor(focused.n, focused.s));
    expect(a.run_everything.enabled).toBe(true);
    expect(a.run_only).toBeUndefined();
  });

  it("a rejected node's only action is Add instruction, aimed at its parent", () => {
    const { s, n } = board({ status: "Rejected", parent_id: "D1", depth: 2 }, "Running", [graphNode({ id: "D1", parent_id: "R", depth: 1 })]);
    const a = actionsFor(n, s);
    expect(a.filter((x) => x.enabled).map((x) => x.type)).toEqual(["instruct"]);
    expect(a[0].consequence).toContain("the parent that proposed it");
  });

  it("nothing but the reason is offered once the investigation has ended", () => {
    const { s, n } = board({ status: "Completed" }, "Completed");
    expect(actionsFor(n, s).every((x) => !x.enabled)).toBe(true);
  });
});
