import { act, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { forgetInvestigation } from "../state/investigationStore";
import { forgetSelection } from "../state/selection";
import { FakeEventSource } from "../test/eventSource";
import { mockApi } from "../test/fetch";
import { runContract } from "../test/contract";
import { settings } from "../test/fixtures";
import { InvestigationRoute } from "./InvestigationRoute";

const { events, snapshots } = runContract();
const mid = snapshots[0];
const ID = mid.investigation.id;

beforeEach(() => {
  FakeEventSource.reset();
  forgetInvestigation(ID);
  forgetSelection(ID);
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

function show(path: string, snapshot = mid) {
  mockApi({ [`GET /api/investigations/${ID}`]: snapshot, "GET /api/settings": settings() });
  render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/investigations/:id" element={<InvestigationRoute />} />
        <Route path="/investigations/:id/board" element={<InvestigationRoute board />} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("ControlBoard", () => {
  it("a Running investigation opens the board: header and three named panes", async () => {
    show(`/investigations/${ID}`);
    expect(await screen.findByRole("heading", { name: mid.investigation.prompt })).toHaveClass("ng-title");
    const board = document.querySelector(".ng-board")!;
    expect(board.querySelector(".ng-board__head")).not.toBeNull();
    const body = board.querySelector(".ng-board__body")!;
    expect([...body.children].map((c) => c.getAttribute("data-slot"))).toEqual(["execution-order", "center", "inspector"]);
    expect(body.querySelector('[data-slot="execution-order"]')).toHaveClass("ng-pane", "ng-pane--left");
    expect(body.querySelector('[data-slot="inspector"]')).toHaveClass("ng-pane", "ng-pane--right");
    const center = body.querySelector('[data-slot="center"]')!;
    expect(center).toHaveClass("ng-center");
    expect([...center.children].map((c) => c.className)).toEqual(["ng-toolbar", "ng-canvas", "ng-dock"]);
    expect(center.querySelector(".ng-dock")).toHaveAttribute("data-slot", "event-log");
    // Nothing selected: the inspector is aimed at the root.
    const root = mid.nodes.find((n) => n.parent_id === null)!;
    expect(body.querySelector('[data-slot="inspector"] [data-node-id]')).toHaveAttribute("data-node-id", root.id);
    // Opened from the snapshot, then followed on the stream from its seq.
    expect(FakeEventSource.last.url).toContain(`after=${mid.seq}`);
  });

  it("a Stopped investigation opens the board as history", async () => {
    show(`/investigations/${ID}`, { ...mid, investigation: { ...mid.investigation, state: "Stopped" } });
    expect(await screen.findByRole("heading", { name: mid.investigation.prompt })).toBeInTheDocument();
    expect(document.querySelector(".ng-board__head .ng-pill")).toHaveTextContent("Stopped");
  });

  it("/board opens the board for a Completed investigation", async () => {
    const last = snapshots[snapshots.length - 1];
    show(`/investigations/${ID}/board`, last);
    expect(await screen.findByRole("heading", { name: last.investigation.prompt })).toBeInTheDocument();
    expect(document.querySelector(".ng-board__head .ng-pill")).toHaveTextContent("Completed");
    expect(document.querySelector('[data-slot="execution-order"]')).not.toBeNull();
  });

  it("a node completing after load sorts first in Done", async () => {
    show(`/investigations/${ID}`);
    await screen.findByRole("heading", { name: mid.investigation.prompt });
    const upTo = events.find((e) => e.type === "node.completed" && e.node_id === mid.nodes[2].id)!.seq;
    act(() => {
      for (const e of events.filter((e) => e.seq > mid.seq && e.seq <= upTo)) FakeEventSource.last.durable(e);
    });
    const done = [...document.querySelectorAll('.ng-qrow[data-section="done"]')];
    expect(done[0]).toHaveAttribute("data-node-id", mid.nodes[2].id);
    expect(done[0].querySelector(".ng-qrow__q")).toHaveTextContent(/^D1 /);
  });

  it("clicking a queue row selects the node for the inspector", async () => {
    show(`/investigations/${ID}`);
    await screen.findByRole("heading", { name: mid.investigation.prompt });
    const d1 = mid.nodes[2];
    fireEvent.click(document.querySelector(`.ng-qrow[data-node-id="${d1.id}"]`)!);
    expect(document.querySelector(`.ng-qrow[data-node-id="${d1.id}"]`)).toHaveClass("is-selected");
    expect(document.querySelector('[data-slot="inspector"] [data-node-id]')).toHaveAttribute("data-node-id", d1.id);
  });
});
