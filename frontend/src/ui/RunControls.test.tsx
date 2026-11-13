import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { DurableEvent, InvestigationState, Snapshot } from "../api/types";
import { emptySnapshot } from "../state/reduce";
import { useCommand } from "../state/useCommand";
import { callsTo, mockApi } from "../test/fetch";
import { RunControls } from "./RunControls";
import { emitDurable } from "../state/investigationStore";

afterEach(() => vi.unstubAllGlobals());

const snap = (state: InvestigationState): Snapshot => {
  const s = emptySnapshot("inv-1");
  return { ...s, investigation: { ...s.investigation, state } };
};
const COMMANDS = "/api/investigations/inv-1/commands";
const ack = () => new Response(JSON.stringify({ recorded: true, duplicate: false }), { status: 202 });

function Harness({ state, banner }: { state: InvestigationState; banner?: boolean }) {
  const command = useCommand("inv-1");
  return (
    <MemoryRouter>
      <RunControls s={snap(state)} command={command} bannerShown={banner} />
      {command.error && <p role="alert">{command.error.message}</p>}
    </MemoryRouter>
  );
}
const labels = () => [...document.querySelectorAll(".ng-btn")].map((b) => b.textContent);
const steer = () => document.querySelectorAll(".ng-btn--steer");
const ev = (to: string, over: Partial<DurableEvent> = {}): DurableEvent =>
  ({ seq: 1, investigation_id: "inv-1", type: "investigation.state_changed", v: 1, at: "", actor: "system", node_id: null, command_id: null, data: { to }, ...over }) as DurableEvent;

describe("RunControls", () => {
  it.each<[InvestigationState, string[]]>([
    ["Draft", []],
    ["Planning", ["Approve plan"]],
    ["Running", ["‖ Pause", "Finish now", "Stop"]],
    ["Paused", ["Resume", "Finish now", "Stop"]],
    ["Synthesising", []],
    ["Stopped", ["Resume", "Finish into a report"]],
    ["Completed", ["Open report", "Export Markdown"]],
  ])("controls per state: %s", (state, expected) => {
    render(<Harness state={state} />);
    expect(labels()).toEqual(expected);
  });

  it.each<[InvestigationState, number]>([["Planning", 1], ["Paused", 1], ["Stopped", 1], ["Running", 0], ["Completed", 0]])(
    "exactly one steer button when the investigation waits for the user: %s", (state, n) => {
      render(<Harness state={state} />);
      expect(steer()).toHaveLength(n);
    });

  it("Resume is not steer while a system pause banner shows", () => {
    render(<Harness state="Paused" banner />);
    expect(steer()).toHaveLength(0);
  });

  it('Pause shows "Pausing…" and stays until the paused event arrives', async () => {
    const f = mockApi({ [`POST ${COMMANDS}`]: ack });
    render(<Harness state="Running" />);
    fireEvent.click(screen.getByRole("button", { name: /Pause/ }));
    expect(await screen.findByRole("button", { name: "Pausing…" })).toBeDisabled();
    await waitFor(() => expect(callsTo(f, "POST", COMMANDS)).toHaveLength(1));
    // The command is recorded: nothing changes yet.
    expect(screen.getByRole("button", { name: "Pausing…" })).toBeDisabled();
    act(() => emitDurable("inv-1", ev("Running")));
    expect(screen.getByRole("button", { name: "Pausing…" })).toBeDisabled();
    act(() => emitDurable("inv-1", ev("Paused")));
    expect(screen.getByRole("button", { name: /Pause/ })).not.toBeDisabled();
  });

  it("409 shows the server message and restores the button", async () => {
    mockApi({ [`POST ${COMMANDS}`]: () => new Response(JSON.stringify({ code: "limit_reached", message: "The spending limit is reached; raise it first" }), { status: 409 }) });
    render(<Harness state="Paused" />);
    fireEvent.click(screen.getByRole("button", { name: "Resume" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("The spending limit is reached; raise it first");
    expect(screen.getByRole("button", { name: "Resume" })).not.toBeDisabled();
  });

  it("no confirmation dialog opens for Stop or Finish now", async () => {
    const f = mockApi({ [`POST ${COMMANDS}`]: ack });
    render(<Harness state="Running" />);
    fireEvent.click(screen.getByRole("button", { name: "Stop" }));
    await waitFor(() => expect(callsTo(f, "POST", COMMANDS)).toHaveLength(1));
    expect(screen.queryByRole("dialog")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Finish now" }));
    await waitFor(() => expect(callsTo(f, "POST", COMMANDS)).toHaveLength(2));
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
