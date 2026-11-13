import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
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

  it("running glyphs pulse only while the stream is open", async () => {
    show(`/investigations/${ID}`);
    await screen.findByRole("heading", { name: mid.investigation.prompt });
    const running = () => document.querySelector('.ng-qrow[data-section="now"] .ng-qrow__n span')!;
    expect(running()).not.toHaveClass("ng-pulse"); // loading: not yet connected
    act(() => FakeEventSource.last.open());
    expect(running()).toHaveClass("ng-pulse");
    act(() => FakeEventSource.last.fail());
    expect(running()).not.toHaveClass("ng-pulse");
  });

  it("the centre shows the running graph, current to the last applied seq", async () => {
    show(`/investigations/${ID}`);
    await screen.findByRole("heading", { name: mid.investigation.prompt });
    const center = document.querySelector('[data-slot="center"]')!;
    expect(center.querySelectorAll(".ng-canvas .ng-node")).toHaveLength(mid.nodes.length);
    const fresh = () => center.querySelector(".ng-toolbar")!.textContent;
    expect(fresh()).toContain(`current to #${String(mid.seq).padStart(4, "0")}`);
    const next = events.find((e) => e.seq > mid.seq)!;
    act(() => FakeEventSource.last.durable(next));
    expect(fresh()).toContain(`current to #${String(next.seq).padStart(4, "0")}`);
  });

  it("selecting a queue row selects the same node on the graph; graph pulses stop when not open", async () => {
    show(`/investigations/${ID}`);
    await screen.findByRole("heading", { name: mid.investigation.prompt });
    act(() => FakeEventSource.last.open());
    const running = mid.nodes.find((n) => n.status === "Running");
    expect(running).toBeDefined();
    expect(document.querySelector(`.ng-canvas [data-node="${running!.id}"] .ng-pulse`)).not.toBeNull();
    const d1 = mid.nodes[2];
    fireEvent.click(document.querySelector(`.ng-qrow[data-node-id="${d1.id}"]`)!);
    expect(document.querySelector(`.ng-canvas [data-node="${d1.id}"]`)).toHaveClass("is-selected");
    act(() => FakeEventSource.last.fail());
    expect(document.querySelector(".ng-canvas .ng-pulse")).toBeNull();
  });
});

describe("ControlBoard event log", () => {
  const last = snapshots[snapshots.length - 1];
  const OLDER = `/api/investigations/${ID}/events`;

  function showWithLog(snapshot: typeof mid, older: (url: string) => unknown) {
    const fetchFn = mockApi({ [`GET /api/investigations/${ID}`]: snapshot, "GET /api/settings": settings(), [`GET ${OLDER}`]: older });
    render(
      <MemoryRouter initialEntries={[`/investigations/${ID}/board`]}>
        <Routes><Route path="/investigations/:id/board" element={<InvestigationRoute board />} /></Routes>
      </MemoryRouter>,
    );
    return fetchFn;
  }
  const olderCalls = (fn: ReturnType<typeof mockApi>) => fn.mock.calls.map(([u]) => String(u)).filter((u) => u.startsWith(OLDER));

  it("the dock shows the log from the snapshot's recent events, newest first", async () => {
    const recent = events.filter((e) => e.seq > last.seq - 50 && e.seq <= last.seq);
    showWithLog({ ...last, recent_events: recent }, () => []);
    await screen.findByRole("heading", { name: last.investigation.prompt });
    const seqs = [...document.querySelectorAll('[data-slot="event-log"] .ng-log__row .ng-log__seq')].map((s) => s.textContent);
    expect(seqs[0]).toBe(`#0${last.seq}`);
    expect(seqs.length).toBeGreaterThan(0);
    expect(seqs.length).toBeLessThan(recent.length); // schedule and spend rows are left out
  });

  it("older rows load on reaching the end, with before=, until none are returned", async () => {
    const recent = events.filter((e) => e.seq > 140 && e.seq <= last.seq);
    const fn = showWithLog({ ...last, recent_events: recent }, (url) => {
      const before = Number(new URL(url, "http://x").searchParams.get("before"));
      return before > 120 ? events.filter((e) => e.seq < before && e.seq >= before - 20) : [];
    });
    await screen.findByRole("heading", { name: last.investigation.prompt });
    // Opening does not fetch the whole history.
    expect(olderCalls(fn)).toEqual([]);
    const log = document.querySelector('[data-slot="event-log"] .ng-log') as HTMLElement;
    Object.defineProperty(log, "scrollHeight", { configurable: true, value: 1000 });
    Object.defineProperty(log, "clientHeight", { configurable: true, value: 166 });
    const toEnd = async (n: number) => {
      log.scrollTop = 834;
      fireEvent.scroll(log);
      await waitFor(() => expect(olderCalls(fn)).toHaveLength(n));
      await waitFor(() => expect(log.closest('[data-older]')).not.toHaveAttribute("data-older", "loading"));
    };
    await toEnd(1);
    expect(olderCalls(fn)[0]).toContain("before=141");
    expect(olderCalls(fn)[0]).toContain("limit=");
    const seqs = () => [...log.querySelectorAll(".ng-log__seq")].map((s) => Number(s.textContent!.slice(1)));
    await waitFor(() => expect(Math.min(...seqs())).toBeLessThan(141));
    await toEnd(2);
    expect(olderCalls(fn)[1]).toContain("before=121");
    await toEnd(3);
    expect(olderCalls(fn)[2]).toContain("before=101");
    // None returned: it stops asking.
    log.scrollTop = 834;
    fireEvent.scroll(log);
    await new Promise((r) => setTimeout(r, 20));
    expect(olderCalls(fn)).toHaveLength(3);
  });

  it("after a remount past more than 200 events, older rows load back to the hole", async () => {
    // First visit: the board held events up to seq 60.
    const fn1 = showWithLog({ ...mid, seq: 60, recent_events: events.filter((e) => e.seq <= 60) }, () => []);
    await screen.findByRole("heading", { name: mid.investigation.prompt });
    expect(olderCalls(fn1)).toEqual([]);
    cleanup();
    // Back after the rest of the run: recent events start at 141, far past what was held.
    const fn = showWithLog({ ...last, recent_events: events.filter((e) => e.seq > 140) }, (url) => {
      const before = Number(new URL(url, "http://x").searchParams.get("before"));
      return events.filter((e) => e.seq < before && e.seq >= before - 200);
    });
    await screen.findByRole("heading", { name: last.investigation.prompt });
    const log = document.querySelector('[data-slot="event-log"] .ng-log') as HTMLElement;
    Object.defineProperty(log, "scrollHeight", { configurable: true, value: 1000 });
    Object.defineProperty(log, "clientHeight", { configurable: true, value: 166 });
    log.scrollTop = 834;
    fireEvent.scroll(log);
    await waitFor(() => expect(olderCalls(fn)).toHaveLength(1));
    expect(olderCalls(fn)[0]).toContain("before=141");
    // Rows from the hole (61..140) are now in the log.
    const seqs = () => [...log.querySelectorAll("[data-seq]")].map((r) => Number(r.getAttribute("data-seq")));
    await waitFor(() => expect(seqs().some((n) => n > 60 && n < 141)).toBe(true));
    expect(Math.min(...seqs())).toBeLessThan(61);
  });

  it("a short list loads older rows without a scroll", async () => {
    const fn = showWithLog({ ...last, recent_events: events.filter((e) => e.seq > 140) }, (url) => {
      const before = Number(new URL(url, "http://x").searchParams.get("before"));
      return before > 101 ? events.filter((e) => e.seq < before && e.seq >= before - 20) : [];
    });
    await screen.findByRole("heading", { name: last.investigation.prompt });
    expect(olderCalls(fn)).toEqual([]);
    const log = document.querySelector('[data-slot="event-log"] .ng-log') as HTMLElement;
    // The rows do not fill the log (a filter on a long run): nothing to scroll.
    Object.defineProperty(log, "scrollHeight", { configurable: true, value: 100 });
    Object.defineProperty(log, "clientHeight", { configurable: true, value: 166 });
    fireEvent.click(screen.getByRole("button", { name: /^Problems/ }));
    // It keeps loading until a page comes back empty, then stops.
    await waitFor(() => expect(olderCalls(fn).length).toBeGreaterThanOrEqual(3));
    await new Promise((r) => setTimeout(r, 30));
    const n = olderCalls(fn).length;
    expect(olderCalls(fn)[n - 1]).toContain("before=101");
    await new Promise((r) => setTimeout(r, 30));
    expect(olderCalls(fn)).toHaveLength(n);
  });

  it("L collapses the log to its head row and back", async () => {
    showWithLog({ ...last, recent_events: events.slice(-20) }, () => []);
    await screen.findByRole("heading", { name: last.investigation.prompt });
    const dock = document.querySelector('[data-slot="event-log"]')!;
    expect(dock.querySelector(".ng-log")).not.toBeNull();
    fireEvent.keyDown(window, { key: "l" });
    expect(dock.querySelector(".ng-log")).toBeNull();
    expect(dock).toHaveTextContent("Event log");
    fireEvent.keyDown(window, { key: "L" });
    expect(dock.querySelector(".ng-log")).not.toBeNull();
  });

  it("clicking a log row selects its node everywhere", async () => {
    showWithLog({ ...last, recent_events: events.slice(-40) }, () => []);
    await screen.findByRole("heading", { name: last.investigation.prompt });
    const row = [...document.querySelectorAll('[data-slot="event-log"] .ng-log__row')]
      .find((r) => r.querySelector(".ng-log__who")!.textContent === "D1")!;
    fireEvent.click(row);
    const d1 = last.nodes.find((n) => n.display_id === "D1")!;
    expect(document.querySelector('[data-slot="inspector"] [data-node-id]')).toHaveAttribute("data-node-id", d1.id);
  });

  it("streamed model text shows as a live row until its step completes", async () => {
    showWithLog(mid, () => []);
    await screen.findByRole("heading", { name: mid.investigation.prompt });
    const next = events.find((e) => e.seq > mid.seq && e.type === "node.step_completed")!;
    act(() => FakeEventSource.last.ephemeral({ investigation_id: ID, node_id: next.node_id, kind: "model_text", data: { step: 9, delta: "{\"action\":" } }));
    expect(document.querySelector('[data-slot="event-log"] .ng-log__row--eph')).toHaveTextContent("{\"action\":");
    act(() => { for (const e of events.filter((e) => e.seq > mid.seq && e.seq <= next.seq)) FakeEventSource.last.durable(e); });
    expect(document.querySelector('[data-slot="event-log"] .ng-log__row--eph')).toBeNull();
  });
});
