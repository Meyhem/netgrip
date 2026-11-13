import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { forgetInvestigation, mergeEvents, useInvestigation } from "./investigationStore";
import { emptySnapshot, reduce } from "./reduce";
import { FakeEventSource } from "../test/eventSource";
import { mockApi } from "../test/fetch";
import { planReviewContract } from "../test/contract";

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
