import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { TrailStep } from "../api/types";
import { forgetInvestigation } from "../state/investigationStore";
import { forgetSelection } from "../state/selection";
import { FakeEventSource } from "../test/eventSource";
import { mockApi } from "../test/fetch";
import { runContract } from "../test/contract";
import { nodeDetail, settings } from "../test/fixtures";
import { ControlBoard } from "./ControlBoard";

// Render counters: BoardHeader and BoardGraph render only when ControlBoard does; the Inspector
// calls useNodeDetail once per render of its own.
const renders = vi.hoisted(() => ({ header: 0, graph: 0, inspector: 0 }));
vi.mock("../ui/BoardHeader", async (orig) => {
  const m = await orig<typeof import("../ui/BoardHeader")>();
  return { ...m, BoardHeader: (p: Parameters<typeof m.BoardHeader>[0]) => { renders.header++; return <m.BoardHeader {...p} />; } };
});
vi.mock("../ui/BoardGraph", async (orig) => {
  const m = await orig<typeof import("../ui/BoardGraph")>();
  return { ...m, BoardGraph: (p: Parameters<typeof m.BoardGraph>[0]) => { renders.graph++; return <m.BoardGraph {...p} />; } };
});
vi.mock("../state/useNodeDetail", async (orig) => {
  const m = await orig<typeof import("../state/useNodeDetail")>();
  return { ...m, useNodeDetail: (...a: Parameters<typeof m.useNodeDetail>) => { renders.inspector++; return m.useNodeDetail(...a); } };
});

const { snapshots } = runContract();
const mid = snapshots[0];
const ID = mid.investigation.id;
const running = mid.nodes.find((n) => n.status === "Running" && n.parent_id !== null)!;
const openStep: TrailStep = {
  step: 1, name: "reason", kind: "decision", activity: "Reasoning", detail: "deciding", summary: null,
  started_at: "2026-11-13T10:01:10Z", ended_at: null, route: null, page_version_id: null, retry: null, instruction_applied: [],
};

beforeEach(() => {
  FakeEventSource.reset();
  forgetInvestigation(ID);
  forgetSelection(ID);
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

describe("ControlBoard render cost", () => {
  it("streamed model text re-renders the trail only, not the board around it", async () => {
    mockApi({
      [`GET /api/investigations/${ID}`]: mid,
      "GET /api/settings": settings(),
      [`GET /api/investigations/${ID}/nodes/*`]: () => nodeDetail(running, { trail: [openStep] }),
    });
    render(<MemoryRouter><ControlBoard id={ID} /></MemoryRouter>);
    await screen.findByRole("heading", { name: mid.investigation.prompt });
    act(() => FakeEventSource.last.open());
    fireEvent.click(document.querySelector(`.ng-qrow[data-node-id="${running.id}"]`)!);
    fireEvent.click(screen.getByRole("tab", { name: "Trail" }));
    await screen.findByText(/deciding/);
    const before = { ...renders };
    act(() => {
      for (const d of ["{\"act", "ion\": ", "\"search\"}"]) {
        FakeEventSource.last.ephemeral({ investigation_id: ID, node_id: running.id, kind: "model_text", data: { step: 1, delta: d } });
      }
    });
    await waitFor(() => expect(document.querySelector(".trail__live")).toHaveTextContent("{\"action\": \"search\"}"));
    // The log's live row shows it too.
    expect(document.querySelector('[data-slot="event-log"] .ng-log__row--eph')).toHaveTextContent("search");
    expect(renders).toEqual(before);
  });
});
