import { describe, expect, it } from "vitest";
import type { DurableEvent, GraphNode, Snapshot } from "../api/types";
import { graphNode } from "../test/fixtures";
import { emptySnapshot } from "./reduce";
import { counts, reach, refutedPremises, sections, waitReasonText } from "./derive";

function snap(nodes: GraphNode[], over: Partial<Snapshot> = {}): Snapshot {
  const base = emptySnapshot("inv-1");
  return {
    ...base, seq: 100, nodes,
    investigation: {
      ...base.investigation, state: "Running",
      settings: { ...base.investigation.settings, effort_budget: { max_depth: 4, max_nodes: 40, sources_per_node: 8, parallel: 4, sources_to_confirm: 2 } },
    },
    ...over,
  };
}

const ev = (seq: number, type: string, node_id: string): DurableEvent => ({
  seq, investigation_id: "inv-1", type, v: 1, at: `2026-11-13T10:00:${String(seq).padStart(2, "0")}Z`,
  actor: "node", node_id, command_id: null, data: {},
});

const R = graphNode({ id: "R", kind: "Synthesis", status: "Waiting on children" });
const kid = (id: string, over: Partial<GraphNode> = {}) => graphNode({ id, parent_id: "R", depth: 1, status: "Pending", ...over });
const ids = (rows: { node: GraphNode }[]) => rows.map((r) => r.node.id);

describe("sections", () => {
  it("sections puts Paused, Ignored, Superseded and Rejected in notRunning", () => {
    const s = snap([
      R,
      kid("A", { status: "Running" }),
      kid("P", { status: "Paused" }),
      kid("I", { status: "Completed", inclusion: "Ignored" }),
      kid("S", { status: "Pending", inclusion: "Superseded" }),
      kid("X", { status: "Rejected" }),
      kid("Q", { status: "Pending" }),
      kid("C", { status: "Completed" }),
    ], { schedule: { order: ["Q"], reasons: {}, slots: 4 } });
    const out = sections(s, []);
    expect(ids(out.notRunning)).toEqual(["P", "I", "S", "X"]);
    expect(out.notRunning.map((r) => r.why)).toEqual(["Paused", "Ignored", "Superseded", "Rejected"]);
    expect(ids(out.now)).toEqual(["A"]);
    expect(ids(out.done)).toEqual(["C"]);
    expect(ids(out.next)).toEqual(["Q", "R"]);
  });

  it("a pending node whose branch is paused is not running", () => {
    const s = snap([R, kid("Q"), kid("Z")], { schedule: { order: ["Q"], reasons: { Z: "paused" }, slots: 4 } });
    expect(ids(sections(s, []).notRunning)).toEqual(["Z"]);
  });

  it("next follows schedule.order, not node order", () => {
    const s = snap([
      R,
      kid("A"), kid("B"), kid("C"),
      kid("D", { depends_on: ["A"] }),
      kid("N", { status: "Proposed", depth: 2, parent_id: "A" }),
    ], {
      schedule: {
        order: ["C", "A", "B"],
        reasons: { B: "slot", D: "dependency:A", N: "orchestrator" },
        slots: 2,
      },
    });
    const next = sections(s, []).next;
    expect(ids(next)).toEqual(["C", "A", "B", "D", "N", "R"]);
    expect(next.map((r) => r.position)).toEqual([1, 2, 3, 4, 5, 6]);
    expect(next.map((r) => r.waitText)).toEqual([
      "", "", "waits for a free slot", "waits for A (dependency)", "awaiting the orchestrator", "waits for A, B, C, D",
    ]);
    expect(next[3].reason).toBe("dependency:A");
  });

  it("while the investigation is Paused, Running nodes head Next with paused", () => {
    const base = snap([R, kid("A", { status: "Running" }), kid("B")], { schedule: { order: ["B"], reasons: {}, slots: 4 } });
    const s = { ...base, investigation: { ...base.investigation, state: "Paused" as const } };
    const out = sections(s, []);
    expect(out.now).toEqual([]);
    expect(ids(out.next)).toEqual(["A", "B", "R"]);
    expect(out.next[0]).toMatchObject({ position: 1, reason: "paused", waitText: "paused" });
  });

  it("done prefers the finish projected on the node row", () => {
    const s = snap([R, kid("A", { status: "Completed", finished_seq: 9, finished_at: "2026-11-13T09:00:00Z" }), kid("B", { status: "Completed", finished_seq: 5, finished_at: "2026-11-13T08:00:00Z" })]);
    const done = sections(s, []).done;
    expect(ids(done)).toEqual(["A", "B"]);
    expect(done[0].finishedAt).toBe("2026-11-13T09:00:00Z");
  });

  it("drops scheduled ids that have already started", () => {
    const s = snap([R, kid("A", { status: "Running" }), kid("B")], { schedule: { order: ["A", "B"], reasons: {}, slots: 1 } });
    const out = sections(s, []);
    expect(ids(out.next)).toEqual(["B", "R"]);
    expect(ids(out.now)).toEqual(["A"]);
  });

  it("done is newest first by the finishing event", () => {
    const s = snap([R, kid("A", { status: "Completed" }), kid("B", { status: "Failed" }), kid("C", { status: "Completed" })]);
    const events = [ev(10, "node.completed", "B"), ev(11, "node.failed", "B"), ev(12, "node.completed", "C"), ev(13, "node.completed", "A")];
    const done = sections(s, events).done;
    expect(ids(done)).toEqual(["A", "C", "B"]);
    expect(done[0].finishedAt).toBe("2026-11-13T10:00:13Z");
    // Without events: newest created first.
    expect(ids(sections(s, []).done)).toEqual(["C", "B", "A"]);
    expect(sections(s, []).done[0].finishedAt).toBeNull();
  });

  it("refuted premise in done is flagged", () => {
    const s = snap([
      R,
      kid("P1", { kind: "Premise check", status: "Completed" }),
      kid("P2", { kind: "Premise check", status: "Completed" }),
      kid("D1", { status: "Completed" }),
    ], {
      premises: [
        { id: "pr-1", text: "Visible from orbit", node_id: "P1", outcome: "refuted" },
        { id: "pr-2", text: "Visible from the Moon", node_id: "P2", outcome: "confirmed" },
      ],
    });
    const done = sections(s, []).done;
    expect(Object.fromEntries(done.map((r) => [r.node.id, r.refutedPremise]))).toEqual({ P1: true, P2: false, D1: false });
    expect(refutedPremises(s).map((p) => p.id)).toEqual(["pr-1"]);
  });
});

describe("waitReasonText", () => {
  const nodes = [graphNode({ id: "n3", display_id: "D3" }), graphNode({ id: "n2", display_id: "D2" })];
  it.each([
    ["dependency:n3", "waits for D3 (dependency)"],
    ["slot", "waits for a free slot"],
    ["orchestrator", "awaiting the orchestrator"],
    ["focus:n2", "waits: you are running only D2"],
    ["paused", "paused"],
  ])("%s → %s", (reason, text) => {
    expect(waitReasonText(reason, nodes)).toBe(text);
  });
});

describe("counts and reach", () => {
  const s = snap([
    graphNode({ id: "R", kind: "Synthesis", status: "Waiting on children" }),
    kid("A", { status: "Running" }),
    kid("B", { status: "Waiting on children" }),
    graphNode({ id: "B1", parent_id: "B", depth: 2, status: "Pending" }),
    graphNode({ id: "B2", parent_id: "B", depth: 2, status: "Completed" }),
    graphNode({ id: "B3", parent_id: "B", depth: 2, status: "Pending", inclusion: "Ignored" }),
    kid("N", { status: "Proposed" }),
    kid("X", { status: "Rejected" }),
  ], { schedule: { order: [], reasons: {}, slots: 6 } });

  it("counts nodes, running, excluded, depth and slots", () => {
    expect(counts(s)).toEqual({ nodes: 5, maxNodes: 40, running: 1, excluded: 2, depth: 2, maxDepth: 4, slots: 6 });
  });

  it("reach is the included nodes of the branch that may still run", () => {
    expect(reach(s, "B")).toBe(2);
    expect(reach(s, "R")).toBe(4);
    expect(reach(s, "B2")).toBe(0);
  });
});
