import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { forgetInvestigation, useInvestigation } from "./investigationStore";
import { useCommand } from "./useCommand";
import { emptySnapshot, reduce } from "./reduce";
import { FakeEventSource } from "../test/eventSource";
import { callsTo, mockApi } from "../test/fetch";
import { planReviewContract } from "../test/contract";
import type { DurableEvent } from "../api/types";

const { events } = planReviewContract();
const ID = events[0].investigation_id;
const COMMANDS = `/api/investigations/${ID}/commands`;
const ack = () => new Response(JSON.stringify({ recorded: true, duplicate: false }), { status: 202 });

beforeEach(() => {
  FakeEventSource.reset();
  forgetInvestigation(ID);
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());
const push = (e: DurableEvent) => FakeEventSource.last.durable(e);

function setup(commandResponse: () => Response = ack) {
  const start = events.slice(0, 14).reduce(reduce, emptySnapshot(ID));
  const f = mockApi({ [`GET /api/investigations/${ID}`]: start, [`POST ${COMMANDS}`]: commandResponse });
  const hook = renderHook(() => ({ inv: useInvestigation(ID), cmd: useCommand(ID) }));
  return { f, hook };
}

describe("useCommand", () => {
  it("isSent stays true from the click until a durable event with that command_id arrives", async () => {
    const { f, hook } = setup();
    await waitFor(() => expect(hook.result.current.inv.snapshot?.seq).toBe(14));
    act(() => { void hook.result.current.cmd.send("instruct_plan", { key: "instruct", payload: { text: "Only human eyes." } }); });
    expect(hook.result.current.cmd.isSent("instruct")).toBe(true);
    await waitFor(() => expect(callsTo(f, "POST", COMMANDS)).toHaveLength(1));
    const body = JSON.parse(callsTo(f, "POST", COMMANDS)[0][1]!.body as string);
    expect(body).toMatchObject({ type: "instruct_plan", payload: { text: "Only human eyes." }, node_id: null });
    // An event for another command does not confirm it.
    act(() => push({ ...events[14], command_id: "someone-else" }));
    expect(hook.result.current.cmd.isSent("instruct")).toBe(true);
    act(() => push({ ...events[15], command_id: body.id }));
    expect(hook.result.current.cmd.isSent("instruct")).toBe(false);
  });

  it("with `until`, only a matching event of that command confirms it", async () => {
    const { f, hook } = setup();
    await waitFor(() => expect(hook.result.current.inv.snapshot?.seq).toBe(14));
    act(() => {
      void hook.result.current.cmd.send("instruct_plan", {
        key: "instruct", payload: { text: "x" }, until: (ev) => ev.type === "plan.version_created",
      });
    });
    await waitFor(() => expect(callsTo(f, "POST", COMMANDS)).toHaveLength(1));
    const { id } = JSON.parse(callsTo(f, "POST", COMMANDS)[0][1]!.body as string);
    act(() => { for (const e of events.slice(14, 20)) push({ ...e, command_id: id }); });
    expect(hook.result.current.cmd.isSent("instruct")).toBe(true);
    act(() => push({ ...events[20], command_id: id }));
    expect(hook.result.current.cmd.isSent("instruct")).toBe(false);
  });

  it("a refused command ends is-sent and reports the server's message", async () => {
    const { hook } = setup(() => new Response(JSON.stringify({ code: "replanning", message: "The plan is being re-planned" }), { status: 409 }));
    await waitFor(() => expect(hook.result.current.inv.snapshot?.seq).toBe(14));
    let ok: boolean | undefined;
    await act(async () => { ok = await hook.result.current.cmd.send("approve_plan", { key: "approve" }); });
    expect(ok).toBe(false);
    expect(hook.result.current.cmd.isSent("approve")).toBe(false);
    expect(hook.result.current.cmd.error).toMatchObject({ key: "approve", code: "replanning", message: "The plan is being re-planned" });
  });
});
