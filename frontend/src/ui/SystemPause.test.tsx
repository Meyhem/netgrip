import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DurableEvent, PauseCause, Snapshot } from "../api/types";
import { emitDurable } from "../state/investigationStore";
import { emptySnapshot } from "../state/reduce";
import { useCommand } from "../state/useCommand";
import { callsTo, mockApi } from "../test/fetch";
import { graphNode, settings } from "../test/fixtures";
import { RecoveryNotice, SystemPause, useRecoveryNotice } from "./SystemPause";
import { RunControls } from "./RunControls";

const COMMANDS = "/api/investigations/inv-1/commands";
const ack = () => new Response(JSON.stringify({ recorded: true, duplicate: false }), { status: 202 });

beforeEach(() => localStorage.clear());
afterEach(() => vi.unstubAllGlobals());

function snap(cause: PauseCause | null, detail: string | null = null): Snapshot {
  const s = emptySnapshot("inv-1");
  return {
    ...s,
    nodes: [graphNode({ id: "R", kind: "Synthesis" }), graphNode({ id: "a", parent_id: "R", depth: 1, status: "Completed" }), graphNode({ id: "b", parent_id: "R", depth: 1, status: "Pending" })],
    investigation: { ...s.investigation, state: "Paused", pause_cause: cause, pause_detail: detail, spent_usd: 5, spending_limit_usd: 5 },
  };
}

function Harness({ s, onErrors = () => {} }: { s: Snapshot; onErrors?: () => void }) {
  const command = useCommand("inv-1");
  return (
    <MemoryRouter>
      <SystemPause s={s} command={command} onShowErrors={onErrors} />
      <RunControls s={s} command={command} bannerShown={s.investigation.pause_cause !== "user"} />
    </MemoryRouter>
  );
}
const banner = () => document.querySelector(".ng-banner");
const ev = (to: string): DurableEvent => ({ seq: 1, investigation_id: "inv-1", type: "investigation.state_changed", v: 1, at: "", actor: "system", node_id: null, command_id: null, data: { to } }) as DurableEvent;

describe("SystemPause", () => {
  it.each<[PauseCause, string, string, string[]]>([
    ["spending_limit", "ng-banner--warn", "Paused: the spending limit of $5.00 was reached", ["Raise limit and resume", "Finish now", "Stop"]],
    ["model_unavailable", "ng-banner--warn", "Paused: the model service stopped responding", ["Resume", "Show the errors in the log"]],
    ["search_unavailable", "ng-banner--warn", "Paused: the search service stopped responding", ["Resume", "Show the errors in the log"]],
    ["key_rejected", "ng-banner--danger", "Paused: a key was rejected", ["Open Settings → Keys", "Resume"]],
    ["credit_exhausted", "ng-banner--danger", "Paused: the provider has no credit left", ["Open Settings → Keys", "Resume"]],
  ])("banner per cause with its tone and choices: %s", async (cause, tone, title, choices) => {
    mockApi({ "GET /api/settings": settings() });
    render(<Harness s={snap(cause, "The provider said so.")} />);
    await waitFor(() => expect(banner()).toHaveClass(tone));
    expect(banner()!.querySelector(".ng-banner__t")).toHaveTextContent(title);
    const inBanner = [...banner()!.querySelectorAll(".ng-btn")].map((b) => b.textContent);
    expect(inBanner).toEqual(choices);
  });

  it("an outage banner says Netgrip stopped retrying and nothing is lost", async () => {
    mockApi({ "GET /api/settings": settings() });
    render(<Harness s={snap("model_unavailable")} />);
    expect(banner()).toHaveTextContent("Netgrip stopped retrying so it would not spend without progress. Nothing is lost.");
  });

  it("Show the errors in the log asks the log for Problems", () => {
    const onErrors = vi.fn();
    mockApi({ "GET /api/settings": settings() });
    render(<Harness s={snap("search_unavailable")} onErrors={onErrors} />);
    fireEvent.click(screen.getByRole("button", { name: "Show the errors in the log" }));
    expect(onErrors).toHaveBeenCalled();
  });

  it("raise limit sends raise_limit then resume, in that order, and shows is-sent until Running", async () => {
    const f = mockApi({ "GET /api/settings": settings(), [`POST ${COMMANDS}`]: ack });
    const view = render(<Harness s={snap("spending_limit")} />);
    const field = screen.getByLabelText("New spending limit") as HTMLInputElement;
    await waitFor(() => expect(field.value).toBe("10")); // current limit + the default limit
    fireEvent.change(field, { target: { value: "12.5" } });
    fireEvent.click(screen.getByRole("button", { name: "Raise limit and resume" }));
    await waitFor(() => expect(callsTo(f, "POST", COMMANDS)).toHaveLength(2));
    const bodies = callsTo(f, "POST", COMMANDS).map((c) => JSON.parse(c[1]!.body as string));
    expect(bodies.map((b) => b.type)).toEqual(["raise_limit", "resume"]);
    expect(bodies[0].payload).toEqual({ spending_limit_usd: 12.5 });
    // The banner's button and the header's Resume both hold the wording.
    for (const b of screen.getAllByRole("button", { name: "Resuming…" })) expect(b).toBeDisabled();
    act(() => emitDurable("inv-1", ev("Running")));
    // The state event arrives: the investigation is Running, the banner is gone.
    const running = snap(null);
    running.investigation.state = "Running";
    view.rerender(<Harness s={running} />);
    expect(banner()).toBeNull();
  });

  it("Resume is disabled while the key is rejected", async () => {
    const base = settings();
    mockApi({ "GET /api/settings": settings({ keys: { ...base.keys, search: { set: true, status: "rejected", checked_at: null, message: "invalid key" } } }) });
    render(<Harness s={snap("key_rejected", 'Tavily answered "invalid key".')} />);
    await waitFor(() => expect(banner()!.querySelector("button")).toBeDisabled());
    expect(banner()).toHaveTextContent("Replace the key, then resume.");
  });

  it("no banner for a user pause", () => {
    mockApi({ "GET /api/settings": settings() });
    render(<Harness s={snap("user")} />);
    expect(banner()).toBeNull();
  });

  it("only one steer button while the banner shows", async () => {
    mockApi({ "GET /api/settings": settings() });
    render(<Harness s={snap("model_unavailable")} />);
    expect(document.querySelectorAll(".ng-btn--steer")).toHaveLength(1);
    expect(banner()!.querySelector(".ng-btn--steer")).not.toBeNull();
  });

  it("is not dismissible", () => {
    mockApi({ "GET /api/settings": settings() });
    render(<Harness s={snap("model_unavailable")} />);
    expect(screen.queryByRole("button", { name: "Dismiss" })).toBeNull();
  });
});

const recovered = (seq: number, nodes: string[] = ["a", "b"]): DurableEvent =>
  ({ seq, investigation_id: "inv-1", type: "system.recovered", v: 1, at: "", actor: "system", node_id: null, command_id: null, data: { reset_node_ids: nodes } }) as DurableEvent;

function Notice({ events }: { events: DurableEvent[] }) {
  const { notice, dismiss } = useRecoveryNotice("inv-1", events);
  return notice ? <RecoveryNotice event={notice} onDismiss={dismiss} /> : <p>none</p>;
}

describe("recovery notice", () => {
  it("shows once per recovery and can be dismissed", () => {
    const first = render(<Notice events={[recovered(10)]} />);
    expect(screen.getByText("Picked up where it stopped.")).toBeInTheDocument();
    expect(document.body).toHaveTextContent("2 nodes running");
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.getByText("none")).toBeInTheDocument();
    first.unmount();
    // The same recovery does not show again in this browser; a newer one does.
    const again = render(<Notice events={[recovered(10)]} />);
    expect(screen.getByText("none")).toBeInTheDocument();
    again.unmount();
    render(<Notice events={[recovered(10), recovered(40)]} />);
    expect(screen.getByText("Picked up where it stopped.")).toBeInTheDocument();
  });
});
