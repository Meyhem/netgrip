import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { PlanReview } from "./PlanReview";
import { forgetInvestigation } from "../state/investigationStore";
import { emptySnapshot, reduce } from "../state/reduce";
import { FakeEventSource } from "../test/eventSource";
import { callsTo, mockApi } from "../test/fetch";
import { planReviewContract } from "../test/contract";
import type { DurableEvent, Snapshot } from "../api/types";

const { events } = planReviewContract();
const ID = events[0].investigation_id;
const COMMANDS = `/api/investigations/${ID}/commands`;
const ack = () => new Response(JSON.stringify({ recorded: true, duplicate: false }), { status: 202 });
const at = (seq: number) => events.slice(0, seq).reduce(reduce, emptySnapshot(ID));
const ev = (seq: number) => events[seq - 1];

beforeEach(() => {
  FakeEventSource.reset();
  forgetInvestigation(ID);
  vi.stubGlobal("EventSource", FakeEventSource);
  sessionStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

function show(snapshot: Snapshot, extra: Record<string, unknown> = {}) {
  const f = mockApi({ [`GET /api/investigations/${ID}`]: snapshot, [`POST ${COMMANDS}`]: ack, ...extra });
  render(
    <MemoryRouter initialEntries={[`/investigations/${ID}`]}>
      <Routes>
        <Route path="/investigations/:id" element={<PlanReview id={ID} />} />
        <Route path="/" element={<p>home</p>} />
      </Routes>
    </MemoryRouter>,
  );
  return f;
}

const stream = (...es: DurableEvent[]) => act(() => { for (const e of es) FakeEventSource.last.durable(e); });
const range = (from: number, to: number) => events.slice(from - 1, to);
const approve = () => screen.getByRole("button", { name: /Approve plan and start|Starting…/ });
const sentBodies = (f: ReturnType<typeof mockApi>) => callsTo(f, "POST", COMMANDS).map(([, i]) => JSON.parse(i!.body as string));

describe("PlanReview", () => {
  it("header, regions and every node Planned in plan v1", async () => {
    show(at(14));
    expect(await screen.findByRole("heading", { name: "Is the Great Wall visible from space?" })).toHaveClass("ng-title");
    const head = document.querySelector(".ng-board__head")!;
    expect(head.querySelector(".ng-pill")).toHaveClass("ng-pill--steer");
    expect(head).toHaveTextContent("Medium · Balanced · no research has run");
    expect(head).toHaveTextContent("Spend$0.01 / $5.00");
    expect(head).toHaveTextContent("Planned nodes6 / 40");
    expect(document.querySelector(".ng-toolbar")).toHaveTextContent("Proposed plan · version 1");
    const nodes = document.querySelectorAll(".ng-canvas .ng-node");
    expect(nodes).toHaveLength(7);
    for (const n of nodes) {
      expect(n).toHaveClass("ng-node--proposed");
      expect(n.querySelector(".ng-node__state")).toHaveTextContent("◌ Planned");
    }
    expect(document.querySelector("[class*='live']")).toBeNull();
    const pane = document.querySelector(".ng-pane--right")!;
    expect(pane).toHaveTextContent("Root goal");
    expect(pane).toHaveTextContent("Establish whether, and under what conditions");
    expect(pane).toHaveTextContent("Assumptions in your question · checked first");
    expect(pane.querySelector(".ng-claim")).toHaveTextContent("PRMP1The Wall is visible to the naked eye from low Earth orbit.");
    expect(pane).toHaveTextContent("Your question takes these as given. If they turn out false, the report says so first.");
    expect(pane).toHaveTextContent("P1 runs first. Then D1, D2 and D3 run in parallel, 4 at a time.");
    expect(document.querySelector(".ng-composer__head")).toHaveTextContent("Instruct R · the whole investigation · reaches 7 nodes");
  });

  it("exactly one ng-btn--steer on the screen", async () => {
    show(at(14));
    await screen.findByRole("heading", { name: "Is the Great Wall visible from space?" });
    fireEvent.change(screen.getByRole("textbox", { name: "Instruction for R" }), { target: { value: "Only human eyes." } });
    const steer = document.querySelectorAll(".ng-btn--steer");
    expect(steer).toHaveLength(1);
    expect(steer[0]).toHaveTextContent("Approve plan and start");
    expect(screen.getByRole("button", { name: "Re-plan" })).not.toHaveClass("ng-btn--steer");
  });

  it('button reads "Re-planning…" (is-sent) until instruction.applied arrives', async () => {
    const f = show(at(14));
    const box = await screen.findByRole("textbox", { name: "Instruction for R" });
    fireEvent.change(box, { target: { value: "Drop the marketing angle; look at origins and photos." } });
    fireEvent.click(screen.getByRole("button", { name: "Re-plan" }));
    expect(screen.getByRole("button", { name: "Re-planning…" })).toHaveClass("is-sent");
    await waitFor(() => expect(sentBodies(f)).toHaveLength(1));
    const [body] = sentBodies(f);
    expect(body).toMatchObject({ type: "instruct_plan", payload: { text: "Drop the marketing angle; look at origins and photos." } });
    // Recorded: instruction.queued arrives; the re-plan has not been drawn yet.
    stream({ ...ev(15), command_id: body.id });
    expect(screen.getByRole("button", { name: "Re-planning…" })).toHaveClass("is-sent");
    expect(document.querySelector(".ng-toolbar .ng-activity")).toHaveTextContent("Re-planning…");
    expect(document.querySelector(".ng-instr--queued")).toHaveTextContent("Drop the marketing angle");
    stream(...range(16, 19).map((e) => ({ ...e, command_id: body.id })));
    expect(screen.getByRole("button", { name: "Re-planning…" })).toBeInTheDocument();
    stream(...range(20, 21).map((e) => ({ ...e, command_id: body.id })));
    expect(screen.getByRole("button", { name: "Re-plan" })).not.toHaveClass("is-sent");
    expect(document.querySelector(".ng-toolbar .ng-activity")).toBeNull();
    expect(box).toHaveValue("");
  });

  it("a re-plan recovered after a restart (no command id) still reads Re-planning… while queued", async () => {
    show(at(15));
    expect(await screen.findByRole("button", { name: "Re-planning…" })).toBeDisabled();
    stream(...range(16, 21));
    expect(screen.getByRole("button", { name: "Re-plan" })).toBeInTheDocument();
  });

  it("Approve is disabled while an instruction is queued", async () => {
    show(at(15));
    await screen.findByRole("heading", { name: "Is the Great Wall visible from space?" });
    expect(approve()).toBeDisabled();
    expect(screen.getByRole("button", { name: "Undo last instruction" })).toBeDisabled();
    stream(...range(16, 21));
    expect(approve()).toBeEnabled();
    expect(screen.getByRole("button", { name: "Undo last instruction" })).toBeEnabled();
  });

  it("the last instruction's added nodes carry \"new\", removed ones show once as − Removed; the diff is listed", async () => {
    show(at(21));
    await screen.findByRole("heading", { name: "Is the Great Wall visible from space?" });
    expect(document.querySelector(".ng-toolbar")).toHaveTextContent("Proposed plan · version 2");
    expect(document.querySelector(".ng-toolbar")).toHaveTextContent("changed by your last instruction: 1 removed, 2 added");
    const node = (display: string) => [...document.querySelectorAll(".ng-canvas .ng-node")].find((n) => n.querySelector(".ng-node__top span:nth-child(2)")?.textContent === display)!;
    expect(node("D4").querySelector(".ng-node__mark")).toHaveTextContent("new");
    expect(node("D4")).toHaveTextContent("added by your instruction");
    expect(node("D3")).toHaveClass("ng-node--excluded");
    expect(node("D3").querySelector(".ng-node__state")).toHaveTextContent("− Removed");
    expect(node("R").querySelector(".ng-node__mark")).toBeNull();
    const instr = document.querySelector(".ng-pane--right .ng-instr")!;
    expect(instr).toHaveTextContent("plan v1 → v2");
    expect(instr.querySelector(".ng-diff__s")).toHaveTextContent("↺ superseded D3");
    expect(instr.querySelectorAll(".ng-diff__n")).toHaveLength(2);
    // Undo: back to v1; the superseded proposals leave the canvas, D3 is back.
    stream(...range(22, 24));
    expect(document.querySelector(".ng-toolbar")).toHaveTextContent("Proposed plan · version 1");
    expect(node("D4")).toBeUndefined();
    expect(node("D3")).toHaveClass("ng-node--proposed");
    expect(document.querySelector(".ng-pane--right .ng-instr__meta")).toHaveTextContent("undone");
  });

  it("Undo and Approve send their commands and hold the is-sent wording", async () => {
    const f = show(at(21));
    await screen.findByRole("heading", { name: "Is the Great Wall visible from space?" });
    fireEvent.click(screen.getByRole("button", { name: "Undo last instruction" }));
    expect(screen.getByRole("button", { name: "Undoing…" })).toBeDisabled();
    expect(approve()).toBeDisabled();
    await waitFor(() => expect(sentBodies(f)).toHaveLength(1));
    const undoId = sentBodies(f)[0].id;
    expect(sentBodies(f)[0].type).toBe("undo_plan_instruction");
    stream(...range(22, 24).map((e) => ({ ...e, command_id: undoId })));
    fireEvent.click(approve());
    expect(screen.getByRole("button", { name: "Starting…" })).toHaveClass("is-sent");
    await waitFor(() => expect(sentBodies(f)).toHaveLength(2));
    expect(sentBodies(f)[1].type).toBe("approve_plan");
    // The pill changes only when the event arrives.
    expect(document.querySelector(".ng-board__head .ng-pill")).toHaveTextContent("Plan review");
  });

  it("plan.failed before any plan shows the warn banner with Draft the plan, which re-drafts", async () => {
    const failed = { ...ev(4), seq: 4, type: "plan.failed", data: { reason: "The model service did not answer." } };
    const f = show([...range(1, 3), failed].reduce(reduce, emptySnapshot(ID)));
    const banner = await screen.findByRole("alert");
    expect(banner).toHaveClass("ng-banner--warn");
    expect(banner).toHaveTextContent("The model service did not answer.");
    expect(document.querySelector(".ng-toolbar .ng-activity")).toBeNull();
    expect(approve()).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Draft the plan" }));
    expect(screen.getByRole("button", { name: "Drafting…" })).toBeDisabled();
    await waitFor(() => expect(sentBodies(f)).toHaveLength(1));
    const { id, type } = sentBodies(f)[0];
    expect(type).toBe("draft_plan");
    // plan.draft_requested clears the failure: the banner goes and the snapshot says drafting.
    stream({ ...ev(3), seq: 5, command_id: id });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(document.querySelector(".ng-toolbar .ng-activity")).toHaveTextContent("Drafting the plan from your prompt");
    stream(...range(4, 14).map((e) => ({ ...e, seq: e.seq + 2, command_id: id })));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(document.querySelector(".ng-toolbar .ng-activity")).toBeNull();
    expect(document.querySelectorAll(".ng-canvas .ng-node")).toHaveLength(7);
  });

  it("a re-draft recovered after a restart (no command id) reads as drafting from the snapshot", async () => {
    const failed = { ...ev(4), seq: 4, type: "plan.failed", data: { reason: "The model service did not answer." } };
    show([...range(1, 3), failed, { ...ev(3), seq: 5 }].reduce(reduce, emptySnapshot(ID)));
    await screen.findByRole("heading", { name: "Is the Great Wall visible from space?" });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.queryByRole("button", { name: "Draft the plan" })).toBeNull();
    expect(document.querySelector(".ng-toolbar .ng-activity")).toHaveTextContent("Drafting the plan from your prompt");
    expect(document.querySelector(".ng-pane--right")).toHaveTextContent("Netgrip is drafting it from your prompt.");
    expect(approve()).toBeDisabled();
  });

  it("a failed re-plan is shown by its diff note, not the draft banner", async () => {
    const failedApply = { ...ev(20), data: { instruction_id: ev(15).data.instruction_id, at_step: null, diff: { kept: [], superseded: [], proposed: [], notes: ["Re-plan failed: the model did not answer."] } } };
    show([...range(1, 15), { ...ev(16), type: "plan.failed", data: { reason: "x" } }, { ...failedApply, seq: 17 }].reduce(reduce, emptySnapshot(ID)));
    await screen.findByRole("heading", { name: "Is the Great Wall visible from space?" });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(document.querySelector(".ng-pane--right .ng-diff")).toHaveTextContent("Re-plan failed: the model did not answer.");
    expect(document.querySelector(".ng-toolbar")).toHaveTextContent("Proposed plan · version 1");
    expect(approve()).toBeEnabled();
  });

  it("Discard draft asks with the delete dialog, then deletes and goes home", async () => {
    const f = show(at(14), { [`DELETE /api/investigations/${ID}`]: new Response(null, { status: 204 }) });
    await screen.findByRole("heading", { name: "Is the Great Wall visible from space?" });
    fireEvent.click(screen.getByRole("button", { name: "Discard draft" }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Is the Great Wall visible from space?");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete investigation" }));
    expect(await screen.findByText("home")).toBeInTheDocument();
    expect(callsTo(f, "DELETE", `/api/investigations/${ID}`)).toHaveLength(1);
  });

  it("after approval the pill becomes Running", async () => {
    show(at(31));
    await screen.findByRole("heading", { name: "Is the Great Wall visible from space?" });
    stream(...range(32, 39));
    expect([...document.querySelectorAll(".ng-pill")].map((p) => p.textContent)).toContain("●Running");
  });
});
