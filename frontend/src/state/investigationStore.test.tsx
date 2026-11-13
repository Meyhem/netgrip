import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import {
  applyModelText, dropModelText, forgetInvestigation, gapRows, liveModelText, mergeEvents, startCatchUp, trackCatchUp, useInvestigation,
} from "./investigationStore";
import { emptySnapshot, reduce } from "./reduce";
import { FakeEventSource } from "../test/eventSource";
import { mockApi } from "../test/fetch";
import { planReviewContract, runContract } from "../test/contract";

const { events, snapshot } = planReviewContract();
const ID = snapshot.investigation.id;

beforeEach(() => {
  FakeEventSource.reset();
  forgetInvestigation(ID);
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

describe("useInvestigation", () => {
  it("loads the snapshot, streams from its seq, applies durable events and closes on unmount", async () => {
    const mid = events.slice(0, 20).reduce(reduce, emptySnapshot(ID));
    mockApi({ [`GET /api/investigations/${ID}`]: mid });
    const { result, unmount } = renderHook(() => useInvestigation(ID));
    await waitFor(() => expect(result.current.snapshot?.seq).toBe(20));
    const es = FakeEventSource.last;
    expect(es.url).toBe(`/api/investigations/${ID}/stream?after=20`);
    act(() => {
      es.open();
      for (const e of events.slice(15)) es.durable(e);
      es.ephemeral({ investigation_id: ID, node_id: null, kind: "model.text", data: { text: "…" } });
    });
    expect(result.current.status).toBe("open");
    expect(result.current.snapshot).toStrictEqual(snapshot);
    expect(result.current.ephemeral).toEqual([{ investigation_id: ID, node_id: null, kind: "model.text", data: { text: "…" } }]);
    unmount();
    expect(es.closed).toBe(true);
  });
});

describe("accumulated durable events", () => {
  it("starts from recent_events, appends streamed events, de-duplicates by seq and keeps seq order", async () => {
    const mid = events.slice(0, 20).reduce(reduce, emptySnapshot(ID));
    mockApi({ [`GET /api/investigations/${ID}`]: { ...mid, recent_events: events.slice(10, 20) } });
    const { result } = renderHook(() => useInvestigation(ID));
    await waitFor(() => expect(result.current.events.map((e) => e.seq)).toEqual(events.slice(10, 20).map((e) => e.seq)));
    act(() => {
      for (const e of events.slice(15, 25)) FakeEventSource.last.durable(e);
    });
    expect(result.current.events.map((e) => e.seq)).toEqual(events.slice(10, 25).map((e) => e.seq));
  });

  it("mergeEvents sorts by seq and keeps one envelope per seq", () => {
    const [a, b, c] = events;
    expect(mergeEvents([c, a], [b, a]).map((e) => e.seq)).toEqual([a.seq, b.seq, c.seq]);
  });
});

describe("live model text", () => {
  const run = runContract();
  const RID = run.snapshots[0].investigation.id;
  const mt = (node_id: string, step: number, delta: string) =>
    ({ investigation_id: RID, node_id, kind: "model_text", data: { step, delta } });

  it("applyModelText keeps the current text per node and step; a later step replaces it", () => {
    let m = applyModelText({}, mt("a", 1, "{\"act"), 1000);
    m = applyModelText(m, mt("a", 1, "ion\""), 1001);
    m = applyModelText(m, mt("b", 2, "x"), 1002);
    expect(m.a).toEqual({ node_id: "a", step: 1, text: "{\"action\"", at: new Date(1000).toISOString() });
    m = applyModelText(m, mt("a", 2, "new"), 1003);
    expect(m.a.text).toBe("new");
    // A late delta of an earlier step is dropped.
    expect(applyModelText(m, mt("a", 1, "late"), 1004).a.text).toBe("new");
    // Other kinds are not model text.
    expect(applyModelText(m, { ...mt("c", 1, "x"), kind: "other" }, 1005)).toBe(m);
  });

  it("dropModelText drops a node's text when its step completes or the node finishes", () => {
    const m = applyModelText(applyModelText({}, mt("a", 1, "x"), 1), mt("b", 1, "y"), 2);
    const e = (type: string, node_id: string) => ({ ...run.events[0], type, node_id });
    expect(dropModelText(m, e("spend.recorded", "a"))).toBe(m);
    for (const t of ["node.step_completed", "node.activity", "node.completed", "node.failed"]) {
      expect(Object.keys(dropModelText(m, e(t, "a")))).toEqual(["b"]);
    }
  });

  it("ephemeral rows vanish when the step completes (store)", async () => {
    const mid = run.snapshots[0];
    forgetInvestigation(RID);
    mockApi({ [`GET /api/investigations/${RID}`]: mid });
    const { result } = renderHook(() => useInvestigation(RID));
    await waitFor(() => expect(result.current.snapshot).not.toBeNull());
    const next = run.events.find((e) => e.seq > mid.seq && e.type === "node.step_completed")!;
    act(() => FakeEventSource.last.ephemeral(mt(next.node_id!, 1, "{\"action\": \"se")));
    expect(liveModelText(result.current).map((t) => t.text)).toEqual(["{\"action\": \"se"]);
    act(() => { for (const e of run.events.filter((e) => e.seq > mid.seq && e.seq <= next.seq)) FakeEventSource.last.durable(e); });
    expect(liveModelText(result.current)).toEqual([]);
    forgetInvestigation(RID);
  });
});

describe("catch-up gap", () => {
  const at = (s: number) => new Date(Date.UTC(2026, 0, 1, 0, 0, s)).toISOString();
  const e = (seq: number, sec: number) => ({ ...events[0], seq, at: at(sec) });
  const limitAt = (seq: number) => ({ ...e(seq, 20), type: "limit.changed", data: { spending_limit_usd: 5 } });

  it("trackCatchUp counts events recorded before the stream reopened and stops at the first live one", () => {
    let c = startCatchUp(100, Date.parse(at(50)));
    for (let s = 101; s <= 125; s++) c = trackCatchUp(c, e(s, 10));
    expect(c).toMatchObject({ afterSeq: 100, count: 25, done: false });
    c = trackCatchUp(c, e(126, 60));
    expect(c).toMatchObject({ count: 25, done: true });
    expect(trackCatchUp(c, e(127, 10)).count).toBe(25);
    // Replayed events at or below afterSeq are not new.
    expect(trackCatchUp(startCatchUp(100, Date.parse(at(50))), e(99, 10)).count).toBe(0);
  });

  it("gapRows keeps only catch-ups of more than 20 events", () => {
    expect(gapRows([{ afterSeq: 1, count: 20, since: 0, done: true }, { afterSeq: 40, count: 21, since: 0, done: false }]))
      .toEqual([{ afterSeq: 40, count: 21 }]);
  });

  it("gap row appears after a large catch-up (reconnect)", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    try {
      vi.setSystemTime(new Date(at(50)));
      const base = { ...emptySnapshot(ID), seq: 10 };
      mockApi({ [`GET /api/investigations/${ID}`]: base });
      const { result } = renderHook(() => useInvestigation(ID));
      await vi.waitFor(() => expect(result.current.snapshot).not.toBeNull());
      act(() => { FakeEventSource.last.open(); FakeEventSource.last.fail(); });
      act(() => { vi.advanceTimersByTime(1500); });
      const es = FakeEventSource.last;
      expect(es.url).toContain("after=10");
      act(() => { es.open(); for (let s = 11; s <= 40; s++) es.durable(limitAt(s)); });
      expect(result.current.gaps).toEqual([{ afterSeq: 10, count: 30 }]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("a small catch-up inserts no gap", async () => {
    vi.useFakeTimers({ toFake: ["setTimeout", "clearTimeout", "Date"] });
    try {
      vi.setSystemTime(new Date(at(50)));
      mockApi({ [`GET /api/investigations/${ID}`]: { ...emptySnapshot(ID), seq: 10 } });
      const { result } = renderHook(() => useInvestigation(ID));
      await vi.waitFor(() => expect(result.current.snapshot).not.toBeNull());
      act(() => { FakeEventSource.last.open(); FakeEventSource.last.fail(); });
      act(() => { vi.advanceTimersByTime(1500); });
      act(() => { FakeEventSource.last.open(); for (let s = 11; s <= 25; s++) FakeEventSource.last.durable(limitAt(s)); });
      expect(result.current.gaps).toEqual([]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("reopening after the tab was closed inserts a gap for the events since the last one seen", async () => {
    mockApi({ [`GET /api/investigations/${ID}`]: { ...emptySnapshot(ID), seq: 10 } });
    const first = renderHook(() => useInvestigation(ID));
    await waitFor(() => expect(first.result.current.snapshot?.seq).toBe(10));
    first.unmount();
    // The tab is closed: nothing in memory survives, only the last seq seen.
    forgetInvestigation(ID, { keepLastSeen: true });
    mockApi({ [`GET /api/investigations/${ID}`]: { ...emptySnapshot(ID), seq: 52 } });
    const { result } = renderHook(() => useInvestigation(ID));
    await waitFor(() => expect(result.current.gaps).toEqual([{ afterSeq: 10, count: 42 }]));
  });
});
