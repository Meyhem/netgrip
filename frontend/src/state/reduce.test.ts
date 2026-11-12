import { describe, expect, it } from "vitest";
import { emptySnapshot, reduce } from "./reduce";
import { planReviewContract } from "../test/contract";
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
