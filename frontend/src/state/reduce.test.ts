import { describe, expect, it } from "vitest";
import { emptySnapshot, HANDLED, PHASE_4_TYPES, reduce } from "./reduce";
import { planReviewContract, runContract } from "../test/contract";
import type { DurableEvent, Snapshot } from "../api/types";

const { events, snapshot } = planReviewContract();
const fold = (start: Snapshot, evs: DurableEvent[]) => evs.reduce(reduce, start);

describe("reduce", () => {
  it("reducing contract/plan_review.json events from an empty snapshot equals its snapshot", () => {
    expect(fold(emptySnapshot(snapshot.investigation.id), events)).toStrictEqual(snapshot);
  });

  it("events at or below seq are ignored", () => {
    const end = fold(emptySnapshot(snapshot.investigation.id), events);
    expect(fold(end, events)).toStrictEqual(snapshot);
    const created = events[0];
    const later = reduce(end, { ...created, data: { prompt: "changed", settings: {} } });
    expect(later).toBe(end);
  });

  it("a stream that drops and replays from an earlier seq during a re-plan ends identical to a fresh load", () => {
    // Drop after the first re-plan's version, reconnect from an older seq: overlap is ignored.
    const cut = events.findIndex((e) => e.type === "plan.version_created" && e.data.version === 2) + 1;
    const partial = fold(emptySnapshot(snapshot.investigation.id), events.slice(0, cut));
    const replayFrom = events.findIndex((e) => e.type === "instruction.queued");
    expect(fold(partial, events.slice(replayFrom))).toStrictEqual(snapshot);
  });

  it("starting from a mid-way snapshot gives the same graph", () => {
    const mid = fold(emptySnapshot(snapshot.investigation.id), events.slice(0, 20));
    expect(mid.seq).toBe(20);
    expect(fold(mid, events.slice(20))).toStrictEqual(snapshot);
  });

  it("plan.draft_requested clears an earlier plan.failed, as the backend projector does", () => {
    const start = fold(emptySnapshot(snapshot.investigation.id), events.slice(0, 3));
    expect(events[2].type).toBe("plan.draft_requested");
    const failed = reduce(start, { ...events[2], seq: 4, type: "plan.failed", data: { reason: "No plan." } });
    expect(failed.plan_failed).toBe("No plan.");
    const again = reduce(failed, { ...events[2], seq: 5 });
    expect(again.plan_failed).toBeNull();
    expect(again.plan_version).toBe(0);
    expect(again.investigation.state).toBe("Planning");
  });

  it("unknown event types only advance seq", () => {
    const end = fold(emptySnapshot(snapshot.investigation.id), events);
    const next = reduce(end, { ...events[0], seq: end.seq + 1, type: "node.something_new", data: {} });
    expect(next).toEqual({ ...end, seq: end.seq + 1 });
  });
});

describe("reduce: the full run (contract/run.json)", () => {
  const run = runContract();
  const final = run.snapshots[run.snapshots.length - 1];
  const id = final.investigation.id;
  const fresh = () => fold(emptySnapshot(id), run.events);

  it("reducing every event from an empty snapshot equals the final snapshot", () => {
    expect(fresh()).toStrictEqual(final);
    expect(final.investigation.state).toBe("Completed");
  });

  it("reducing up to each mid-run snapshot's seq equals that snapshot", () => {
    for (const snap of run.snapshots.slice(0, -1)) {
      expect(fold(emptySnapshot(id), run.events.filter((e) => e.seq <= snap.seq))).toStrictEqual(snap);
    }
    expect(run.snapshots[0].investigation.summary).toBe("P1 Reading");
    expect(run.snapshots[0].investigation.running_count).toBe(1);
  });

  it("every Phase 4 event type has a case", () => {
    for (const t of PHASE_4_TYPES) expect(HANDLED.has(t), t).toBe(true);
  });

  it("a stream that drops and replays from an earlier seq ends identical to a fresh load", () => {
    const cut = Math.floor(run.events.length / 2);
    const partial = fold(emptySnapshot(id), run.events.slice(0, cut));
    expect(fold(partial, run.events.slice(cut - 10))).toStrictEqual(final);
  });
});

describe("reduce: Phase 4 events the run does not reach", () => {
  const run = runContract();
  const mid = run.snapshots[0];
  const p1 = mid.nodes.find((n) => n.display_id === "P1")!;
  const d1 = mid.nodes.find((n) => n.display_id === "D1")!;
  let seq = mid.seq;
  const at = "2026-02-01T00:00:00.000Z";
  const ev = (type: string, data: Record<string, unknown>, node_id: string | null = null): DurableEvent => ({
    seq: ++seq, investigation_id: mid.investigation.id, type, v: 1, at, actor: "system", node_id, command_id: null, data,
  });
  const node = (s: Snapshot, nid: string) => s.nodes.find((n) => n.id === nid)!;

  it("node.failed, node.reset and node.rejected set the status and clear the activity", () => {
    const failed = reduce(mid, ev("node.failed", { reason: "No source answered.", auto_retry_used: false }, p1.id));
    expect([node(failed, p1.id).status, node(failed, p1.id).activity]).toEqual(["Failed", null]);
    expect(failed.investigation.running_count).toBe(0);
    expect(failed.investigation.summary).toBeNull();
    const reset = reduce(failed, ev("node.reset", { reason: "auto_retry", hint: "Try others." }, p1.id));
    expect([node(reset, p1.id).status, node(reset, p1.id).activity]).toEqual(["Pending", null]);
    const again = reduce(reset, ev("node.activity", { activity: "Searching", detail: "q", step: "search", retry: null }, p1.id));
    expect(node(again, p1.id).status).toBe("Running");
    expect(again.investigation.summary).toBe("P1 Searching");
    const rejected = reduce(again, ev("node.rejected", { reason: "budget", duplicate_of: null }, d1.id));
    expect(node(rejected, d1.id).status).toBe("Rejected");
    expect(rejected.investigation.nodes_total).toBe(again.investigation.nodes_total - 1);
  });

  it("a Paused row's summary is the cause; Running nodes stop counting", () => {
    const paused = reduce(mid, ev("investigation.state_changed", {
      from: "Running", to: "Paused", origin: "system", cause: "spending_limit", detail: "The spending limit was reached",
    }));
    expect(paused.investigation.summary).toBe("Reached the spending limit.");
    expect(paused.investigation.running_count).toBe(0);
    expect(paused.investigation.pause_cause).toBe("spending_limit");
  });

  it("limit.changed sets the limit; premise.outcome refuted is carried in the summary", () => {
    const raised = reduce(mid, ev("limit.changed", { spending_limit_usd: 12.5 }));
    expect(raised.investigation.spending_limit_usd).toBe(12.5);
    const premise = mid.premises[0];
    const refuted = reduce(raised, ev("premise.outcome", { premise_id: premise.id, outcome: "refuted" }, p1.id));
    expect(refuted.premises[0].outcome).toBe("refuted");
    expect(refuted.investigation.summary).toBe(`P1 Reading · Premise refuted: ${premise.text}`);
  });

  it("evidence and bookkeeping events change nothing in the snapshot but seq and last activity", () => {
    const quiet: [string, Record<string, unknown>][] = [
      ["node.off_topic", { reason: "About tourism." }], ["node.left_failed", { reason: "auto_retry_used" }],
      ["node.relevance_checked", { reason: null }], ["page.unobtainable", { url: "https://x.test", attempts: [] }],
      ["claim.updated", { claim_id: "c1", status: "Supported", supporting: [], contradicting: [], merged_into: "c2" }],
      ["claim.contradiction_recorded", { claim_ids: ["c1", "c2"] }], ["system.recovered", { reset_node_ids: [] }],
    ];
    for (const [type, data] of quiet) {
      const e = ev(type, data, p1.id);
      expect(reduce(mid, e), type).toStrictEqual({ ...mid, seq: e.seq, investigation: { ...mid.investigation, last_activity_at: at } });
    }
  });
});
