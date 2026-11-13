import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DurableEvent, NodeDetail } from "../api/types";
import { callsTo, mockApi } from "../test/fetch";
import { claim, graphNode, nodeDetail } from "../test/fixtures";
import { addEvents, forgetInvestigation } from "./investigationStore";
import { useNodeDetail } from "./useNodeDetail";

const ID = "inv-1";
const path = (n: string) => `/api/investigations/${ID}/nodes/${n}`;

const ev = (seq: number, type: string, node_id: string | null, data: Record<string, unknown> = {}): DurableEvent => ({
  seq, investigation_id: ID, type, v: 1, at: "2026-11-13T10:00:00Z", actor: "node", node_id, command_id: null, data,
});

beforeEach(() => forgetInvestigation(ID));
afterEach(() => vi.unstubAllGlobals());

describe("useNodeDetail", () => {
  it("refetches when a durable event for the node, or a claim of it, arrives", async () => {
    let version = 0;
    const fn = mockApi({
      [`GET ${path("A")}`]: () => nodeDetail(graphNode({ id: "A", question: `v${++version}` }), { claims: [claim({ id: "C1" })] }),
    });
    const { result } = renderHook(() => useNodeDetail(ID, "A"));
    await waitFor(() => expect(result.current.detail?.node.question).toBe("v1"));
    expect(result.current.status).toBe("ready");

    // Another node's event: no refetch.
    act(() => addEvents(ID, [ev(5, "node.activity", "B")]));
    await act(async () => {});
    expect(callsTo(fn, "GET", path("A"))).toHaveLength(1);

    act(() => addEvents(ID, [ev(6, "node.activity", "A")]));
    await waitFor(() => expect(result.current.detail?.node.question).toBe("v2"));

    // A claim of this node updated by another node's verification.
    act(() => addEvents(ID, [ev(7, "claim.updated", "V1", { claim_id: "C1", status: "Confirmed" })]));
    await waitFor(() => expect(result.current.detail?.node.question).toBe("v3"));

    // An inclusion change names its nodes in data.
    act(() => addEvents(ID, [ev(8, "node.inclusion_changed", null, { node_ids: ["A", "A1"], inclusion: "Superseded", by: "replan" })]));
    await waitFor(() => expect(result.current.detail?.node.question).toBe("v4"));
  });

  it("a response for a previous node never overwrites the current one", async () => {
    const pending: Record<string, (d: NodeDetail) => void> = {};
    mockApi({
      [`GET ${path("A")}`]: () => new Promise((r) => (pending.A = r)),
      [`GET ${path("B")}`]: () => new Promise((r) => (pending.B = r)),
    });
    const { result, rerender } = renderHook(({ n }) => useNodeDetail(ID, n), { initialProps: { n: "A" } });
    await waitFor(() => expect(pending.A).toBeDefined());
    expect(result.current.status).toBe("loading");
    rerender({ n: "B" });
    await waitFor(() => expect(pending.B).toBeDefined());
    await act(async () => pending.B(nodeDetail(graphNode({ id: "B" }))));
    await act(async () => pending.A(nodeDetail(graphNode({ id: "A" }))));
    expect(result.current.detail?.node.id).toBe("B");
    expect(result.current.status).toBe("ready");
  });

  it("does not show the previous node's detail while the next one loads", async () => {
    const pending: Record<string, (d: NodeDetail) => void> = {};
    mockApi({
      [`GET ${path("A")}`]: nodeDetail(graphNode({ id: "A" })),
      [`GET ${path("B")}`]: () => new Promise((r) => (pending.B = r)),
    });
    const { result, rerender } = renderHook(({ n }) => useNodeDetail(ID, n), { initialProps: { n: "A" } });
    await waitFor(() => expect(result.current.detail?.node.id).toBe("A"));
    rerender({ n: "B" });
    expect(result.current.detail).toBeNull();
    expect(result.current.status).toBe("loading");
  });

  it("an error is reported for the current node", async () => {
    mockApi({ [`GET ${path("A")}`]: () => new Response("{}", { status: 500 }) });
    const { result } = renderHook(() => useNodeDetail(ID, "A"));
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.detail).toBeNull();
  });
});
