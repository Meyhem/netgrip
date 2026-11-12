import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { useInvestigation } from "./investigationStore";
import { emptySnapshot, reduce } from "./reduce";
import { FakeEventSource } from "../test/eventSource";
import { mockApi } from "../test/fetch";
import { planReviewContract } from "../test/contract";

const { events, snapshot } = planReviewContract();
const ID = snapshot.investigation.id;

beforeEach(() => {
  FakeEventSource.reset();
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
