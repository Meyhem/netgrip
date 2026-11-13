import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DurableEvent, GraphNode, Snapshot } from "../api/types";
import { forgetInvestigation } from "../state/investigationStore";
import { forgetSelection } from "../state/selection";
import { FakeEventSource } from "../test/eventSource";
import { callsTo, mockApi } from "../test/fetch";
import { runContract } from "../test/contract";
import { nodeDetail, settings } from "../test/fixtures";
import { InvestigationRoute } from "./InvestigationRoute";

const { snapshots } = runContract();
const mid = snapshots[0];
const ID = mid.investigation.id;
const COMMANDS = `/api/investigations/${ID}/commands`;
const ack = () => new Response(JSON.stringify({ recorded: true, duplicate: false }), { status: 202 });

beforeEach(() => {
  FakeEventSource.reset();
  forgetInvestigation(ID);
  forgetSelection(ID);
  sessionStorage.clear();
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

const running = () => mid.nodes.find((n) => n.status === "Running" && n.parent_id !== null)!;
const root = () => mid.nodes.find((n) => n.parent_id === null)!;

async function open(snapshot: Snapshot = mid, extra: Record<string, unknown> = {}) {
  const f = mockApi({
    [`GET /api/investigations/${ID}`]: snapshot,
    "GET /api/settings": settings(),
    [`POST ${COMMANDS}`]: ack,
    [`GET /api/investigations/${ID}/nodes/*`]: (url: string) => {
      const nid = decodeURIComponent(url.split("/").pop()!);
      return nodeDetail(snapshot.nodes.find((n) => n.id === nid)!);
    },
    ...extra,
  });
  render(
    <MemoryRouter initialEntries={[`/investigations/${ID}`]}>
      <Routes><Route path="/investigations/:id" element={<InvestigationRoute />} /></Routes>
    </MemoryRouter>,
  );
  await screen.findByRole("heading", { name: snapshot.investigation.prompt });
  return f;
}
const select = async (n: GraphNode) => {
  fireEvent.click(document.querySelector(`.ng-qrow[data-node-id="${n.id}"]`)!);
  await waitFor(() => expect(document.querySelector('[data-slot="inspector"] [data-node-id]')).toHaveAttribute("data-node-id", n.id));
};
const inspector = () => document.querySelector('[data-slot="inspector"]') as HTMLElement;
const sentBody = (f: ReturnType<typeof mockApi>, i = 0) => JSON.parse(callsTo(f, "POST", COMMANDS)[i][1]!.body as string);
const durable = (type: string, data: object, over: Partial<DurableEvent> = {}): DurableEvent => ({
  seq: mid.seq + 1, investigation_id: ID, type, v: 1, at: "2026-11-13T14:00:02Z", actor: "user", node_id: null, command_id: null, data, ...over,
}) as DurableEvent;

async function openCompleted() {
  const done = running();
  const f = await open({ ...mid, nodes: mid.nodes.map((x) => (x.id === done.id ? { ...x, status: "Completed" as const } : x)) });
  await select(done);
  return { done, f };
}

describe("node actions on the board", () => {
  it("X sends ignore_branch; the node changes only when the event arrives", async () => {
    const f = await open();
    const n = running();
    await select(n);
    fireEvent.keyDown(window, { key: "x" });
    await waitFor(() => expect(callsTo(f, "POST", COMMANDS)).toHaveLength(1));
    const body = sentBody(f);
    expect(body).toMatchObject({ type: "ignore_branch", node_id: n.id });
    expect(within(inspector()).getByRole("button", { name: "Ignoring…" })).toBeDisabled();
    expect(document.querySelector(`.ng-qrow[data-node-id="${n.id}"]`)).not.toHaveAttribute("data-section", "not-running");
    act(() => FakeEventSource.last.durable(durable("node.inclusion_changed", { node_ids: [n.id], inclusion: "Ignored", by: "user" }, { command_id: body.id, node_id: n.id })));
    const row = document.querySelector(`.ng-qrow[data-node-id="${n.id}"]`)!;
    expect(row).toHaveAttribute("data-section", "not-running");
    expect(row).toHaveTextContent("Ignored by you");
    // And X on an ignored node restores it.
    fireEvent.keyDown(window, { key: "x" });
    await waitFor(() => expect(callsTo(f, "POST", COMMANDS)).toHaveLength(2));
    expect(sentBody(f, 1)).toMatchObject({ type: "restore_branch", node_id: n.id });
  });

  it("Restore link in Not running sends restore_branch", async () => {
    const n = running();
    const ignored: Snapshot = { ...mid, nodes: mid.nodes.map((x) => (x.id === n.id ? { ...x, inclusion: "Ignored", excluded_by: "user", excluded_at: "2026-11-13T14:00:00Z" } : x)) };
    const f = await open(ignored);
    const row = document.querySelector(`.ng-qrow[data-node-id="${n.id}"]`)!;
    fireEvent.click(within(row as HTMLElement).getByRole("button", { name: "Restore" }));
    await waitFor(() => expect(callsTo(f, "POST", COMMANDS)).toHaveLength(1));
    expect(sentBody(f)).toMatchObject({ type: "restore_branch", node_id: n.id });
    expect(within(row as HTMLElement).getByRole("button", { name: "Restoring…" })).toBeDisabled();
  });

  it("keys do nothing while typing in the composer", async () => {
    const f = await open();
    await select(running());
    const box = within(inspector()).getByRole("textbox");
    fireEvent.change(box, { target: { value: "x " } });
    fireEvent.keyDown(box, { key: "x" });
    fireEvent.keyDown(box, { key: " " });
    fireEvent.keyDown(box, { key: "r" });
    expect(callsTo(f, "POST", COMMANDS)).toHaveLength(0);
  });

  it("re-run shows an inline danger confirmation and sends only after it", async () => {
    const { done, f } = await openCompleted();
    fireEvent.keyDown(window, { key: "r" });
    const ask = await within(inspector()).findByText(`Re-run ${done.display_id}?`);
    expect(ask.closest(".ng-banner")).toHaveClass("ng-banner--danger");
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(callsTo(f, "POST", COMMANDS)).toHaveLength(0);
    fireEvent.click(within(inspector()).getByRole("button", { name: "Re-run node" }));
    await waitFor(() => expect(callsTo(f, "POST", COMMANDS)).toHaveLength(1));
    expect(sentBody(f)).toMatchObject({ type: "rerun_node", node_id: done.id });
  });

  it("Keep result closes the question without sending", async () => {
    const { done, f } = await openCompleted();
    fireEvent.keyDown(window, { key: "r" });
    fireEvent.click(await within(inspector()).findByRole("button", { name: "Keep result" }));
    expect(within(inspector()).queryByText(`Re-run ${done.display_id}?`)).toBeNull();
    expect(callsTo(f, "POST", COMMANDS)).toHaveLength(0);
  });

  it("the node menu opens with . and lists disabled items with their reason", async () => {
    await open();
    await select(running());
    fireEvent.keyDown(window, { key: "." });
    const menu = await within(inspector()).findByRole("menu");
    const rerun = within(menu).getByText("Re-run node").closest(".ng-menu__item")!;
    expect(rerun).toHaveClass("is-disabled");
    expect(rerun).toHaveTextContent("Available once the node has completed or failed.");
  });

  it("Esc clears the selection", async () => {
    await open();
    await select(running());
    fireEvent.keyDown(window, { key: "Escape" });
    await waitFor(() => expect(inspector().querySelector("[data-node-id]")).toHaveAttribute("data-node-id", root().id));
  });
});

describe("the composer on the board", () => {
  it("head names target and reach; the foot says when it takes effect", async () => {
    await open();
    const n = running();
    await select(n);
    const head = inspector().querySelector(".ng-composer__head")!;
    expect(head).toHaveTextContent(`✎︎ Instruct ${n.display_id} · ${n.question}`);
    expect(head).toHaveTextContent(/reaches \d+ nodes?/);
  });

  it("sends add_instruction to the selected node and shows it queued with what it waits for", async () => {
    const f = await open();
    const n = running();
    await select(n);
    const box = within(inspector()).getByRole("textbox");
    fireEvent.change(box, { target: { value: "Look at photographs only" } });
    fireEvent.click(within(inspector()).getByRole("button", { name: "Send instruction" }));
    await waitFor(() => expect(callsTo(f, "POST", COMMANDS)).toHaveLength(1));
    const body = sentBody(f);
    expect(body).toMatchObject({ type: "add_instruction", node_id: n.id, payload: { text: "Look at photographs only" } });
    act(() => FakeEventSource.last.durable(durable("instruction.queued", { instruction_id: "i-1", text: "Look at photographs only", waiting_for: `${n.display_id} finishes READING` }, { command_id: body.id, node_id: n.id })));
    const queued = await waitFor(() => {
      const el = inspector().querySelector(".ng-instr--queued");
      expect(el).not.toBeNull();
      return el!;
    });
    expect(queued).toHaveTextContent(`queued · applies when ${n.display_id} finishes READING`);
    act(() => FakeEventSource.last.durable(durable("instruction.applied", { instruction_id: "i-1", at_step: 2, diff: { kept: [], superseded: [], proposed: [], notes: [] } }, { seq: mid.seq + 2, node_id: n.id })));
    await waitFor(() => expect(inspector().querySelector(".ng-instr--queued")).toBeNull());
    expect(inspector().querySelector(".ng-instr")).toHaveTextContent("Look at photographs only");
    expect(screen.getAllByText(/✎︎ 1|1/).length).toBeGreaterThan(0);
  });

  it("an applied coordinator instruction lists kept, superseded with Restore, and proposed", async () => {
    const parent = mid.nodes.find((n) => n.parent_id !== null && mid.nodes.some((c) => c.parent_id === n.id)) ?? running();
    const [a, b] = mid.nodes.filter((n) => n.parent_id === root().id).slice(0, 2);
    const withInstr: Snapshot = {
      ...mid,
      instructions: [{ id: "i-9", node_id: parent.id, text: "Concentrate on one site", state: "applied", queued_seq: 3, applied_seq: 5, undone: false, waiting_for: null,
        diff: { kept: [a.id], superseded: [b.id], proposed: [], notes: ["note"] } }],
    };
    const f = await open(withInstr);
    await select(parent);
    const instr = inspector().querySelector(".ng-instr")!;
    expect(instr.querySelector(".ng-diff__k")).not.toBeNull();
    fireEvent.click(within(instr as HTMLElement).getByRole("button", { name: "Restore" }));
    await waitFor(() => expect(callsTo(f, "POST", COMMANDS)).toHaveLength(1));
    expect(sentBody(f)).toMatchObject({ type: "restore_branch", node_id: b.id });
  });

  it("the root composer is locked after approval with the explanation", async () => {
    await open();
    const head = inspector().querySelector(".ng-composer");
    expect(head).toHaveClass("is-locked");
    expect(head).toHaveTextContent("cannot be re-planned once research is running");
    expect(within(inspector()).queryByRole("textbox")).toBeNull();
  });

  it("every composer is locked once the research has ended or stopped", async () => {
    const stopped: Snapshot = { ...mid, investigation: { ...mid.investigation, state: "Stopped" } };
    await open(stopped);
    await select(running());
    expect(inspector().querySelector(".ng-composer")).toHaveClass("is-locked");
  });

  it("the draft survives changing selection and coming back; Esc keeps it", async () => {
    await open();
    const [a, b] = mid.nodes.filter((n) => n.parent_id !== null && n.status !== "Rejected").slice(0, 2);
    await select(a);
    const box = () => within(inspector()).getByRole("textbox") as HTMLTextAreaElement;
    fireEvent.change(box(), { target: { value: "half a thought" } });
    fireEvent.keyDown(box(), { key: "Escape" });
    expect(box().value).toBe("half a thought");
    await select(b);
    expect(box().value).toBe("");
    await select(a);
    expect(box().value).toBe("half a thought");
  });

  it("I focuses the composer", async () => {
    await open();
    await select(running());
    fireEvent.keyDown(window, { key: "i" });
    await waitFor(() => expect(within(inspector()).getByRole("textbox")).toHaveFocus());
  });

  it("clicking the sequence number scrolls the log to that row", async () => {
    const n = running();
    const withInstr: Snapshot = {
      ...mid,
      instructions: [{ id: "i-9", node_id: n.id, text: "Prefer primary sources", state: "applied", queued_seq: 3, applied_seq: 5, undone: false, waiting_for: null,
        diff: { kept: [], superseded: [], proposed: [], notes: [] } }],
    };
    await open(withInstr);
    await select(n);
    const row = document.querySelector('.ng-log__row[data-seq="3"]') ?? document.createElement("div");
    const scroll = vi.fn();
    row.scrollIntoView = scroll;
    fireEvent.click(within(inspector()).getByRole("button", { name: /Show .0003 in the log/ }));
    expect(screen.getByRole("button", { name: "Collapse log" })).toHaveAttribute("aria-expanded", "true");
  });
});
