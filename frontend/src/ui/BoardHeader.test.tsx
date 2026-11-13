import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { GraphNode, Snapshot } from "../api/types";
import { emptySnapshot } from "../state/reduce";
import { callsTo, mockApi } from "../test/fetch";
import { graphNode, row } from "../test/fixtures";
import { BoardHeader } from "./BoardHeader";

afterEach(() => vi.unstubAllGlobals());

function snap(over: Partial<Snapshot["investigation"]> = {}, rest: Partial<Snapshot> = {}): Snapshot {
  const base = emptySnapshot("inv-1");
  const nodes: GraphNode[] = [
    graphNode({ id: "R", kind: "Synthesis", status: "Waiting on children" }),
    graphNode({ id: "P1", parent_id: "R", depth: 1, kind: "Premise check", status: "Completed" }),
    graphNode({ id: "D1", parent_id: "R", depth: 1, status: "Running" }),
    graphNode({ id: "D1a", parent_id: "D1", depth: 2, status: "Pending" }),
  ];
  return {
    ...base, seq: 419, nodes,
    investigation: {
      ...base.investigation,
      ...row({ state: "Running", spent_usd: 1.84, spending_limit_usd: 5, run_seconds: 1330, running_count: 1, nodes_total: 3, disk_bytes: 2 * 1024 * 1024 }),
      settings: {
        effort: "Medium", preset: "balanced", tiers: {} as never, excluded_domains: [], prefer: "none", page_reuse: "1d", spending_limit_usd: 5,
        effort_budget: { max_depth: 4, max_nodes: 40, sources_per_node: 8, parallel: 4, sources_to_confirm: 2 },
      },
      root_goal: null,
      ...over,
    },
    premises: [{ id: "pr-1", text: "Visible from orbit", node_id: "P1", outcome: null }],
    ...rest,
  };
}

function show(s: Snapshot, status: "open" | "reconnecting" = "open") {
  return render(
    <MemoryRouter initialEntries={["/investigations/inv-1/board"]}>
      <Routes>
        <Route path="/investigations/:id/board" element={<BoardHeader s={s} status={status} runControls={<span data-testid="run-controls" />} />} />
        <Route path="/" element={<p>home</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

const head = () => document.querySelector(".ng-board__head")!;

describe("BoardHeader focus", () => {
  it('reads "Running only D2" with a Run everything button while a branch runs alone', () => {
    const s = snap({}, { focus_node_id: "D1" });
    render(
      <MemoryRouter>
        <BoardHeader s={s} status="open" focusAction={<button>Run everything</button>} />
      </MemoryRouter>,
    );
    expect(head()).toHaveTextContent("Running only D1");
    expect(screen.getByRole("button", { name: "Run everything" })).toBeInTheDocument();
  });

  it("has no Run everything without a focus", () => {
    render(
      <MemoryRouter>
        <BoardHeader s={snap()} status="open" focusAction={<button>Run everything</button>} />
      </MemoryRouter>,
    );
    expect(screen.queryByRole("button", { name: "Run everything" })).toBeNull();
  });
});

describe("BoardHeader", () => {
  it("shows state, effort, preset, run time and running count, the prompt and three meters", () => {
    show(snap());
    const pill = head().querySelector(".ng-pill")!;
    expect(pill).toHaveClass("ng-pill--live");
    expect(pill).toHaveTextContent("Running");
    expect(head()).toHaveTextContent("Medium · Balanced · 0:22:10 · 1 running");
    expect(screen.getByRole("heading", { name: /Great Wall/ })).toHaveClass("ng-title");
    expect(screen.getByRole("link", { name: "Back to investigations" })).toHaveAttribute("href", "/");
    const meters = head().querySelectorAll(".ng-meter");
    expect([...meters].map((m) => m.textContent)).toEqual(["Spend$1.84 / $5.00", "Nodes3 / 40", "Depth2 / 4"]);
    expect(screen.getByTestId("run-controls")).toBeInTheDocument();
    expect(head().querySelector(".ng-pill--danger")).toBeNull();
  });

  it("header shows the danger pill when a premise is refuted", () => {
    show(snap({}, { premises: [{ id: "pr-1", text: "Visible from orbit", node_id: "P1", outcome: "refuted" }] }));
    const danger = head().querySelector(".ng-pill--danger")!;
    expect(danger).toHaveTextContent("✕Premise refuted");
  });

  it("counts several refuted premises", () => {
    show(snap({}, {
      premises: [
        { id: "pr-1", text: "a", node_id: "P1", outcome: "refuted" },
        { id: "pr-2", text: "b", node_id: null, outcome: "refuted" },
      ],
    }));
    expect(head().querySelector(".ng-pill--danger")).toHaveTextContent("2 premises refuted");
  });

  it('header pill shows "· reconnecting"', () => {
    show(snap(), "reconnecting");
    const pill = head().querySelector(".ng-pill")!;
    expect(pill).toHaveTextContent(/^●?Running\s*· reconnecting$/);
    expect(pill.querySelector(".ng-warn")).toHaveTextContent("· reconnecting");
    // Pulsing stops while the stream is disconnected.
    expect(pill.querySelector(".ng-pulse")).toBeNull();
  });

  it('spend meter shows "≈" when approximate', () => {
    show(snap({ spend_approximate: true }));
    expect(head().querySelector(".ng-meter")).toHaveTextContent("Spend≈ $1.84 / $5.00");
  });

  it("a paused investigation says who paused it", () => {
    show(snap({ state: "Paused", pause_cause: "spending_limit" }));
    expect(head().querySelector(".ng-pill--warn")).toHaveTextContent("Paused · spending limit");
  });

  it("running only one branch replaces the mono line", () => {
    show(snap({}, { focus_node_id: "D1" }));
    expect(head()).toHaveTextContent("Running only D1");
    expect(head()).not.toHaveTextContent("1 running");
  });

  it("overflow offers Export events, Open report and Delete investigation", async () => {
    const f = mockApi({ "GET /api/investigations/inv-1/events": [{ seq: 1 }], "DELETE /api/investigations/inv-1": new Response(null, { status: 204 }) });
    const createObjectURL = vi.fn(() => "blob:x");
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL, revokeObjectURL: vi.fn() }));
    const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    show(snap());
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    const items = screen.getAllByRole("menuitem");
    expect(items.map((i) => i.querySelector("b")!.textContent)).toEqual(["Export events", "Open report", "Delete investigation"]);
    // The report is written when the run completes.
    expect(items[1]).toHaveClass("is-disabled");

    fireEvent.click(items[0]);
    await waitFor(() => expect(click).toHaveBeenCalled());
    expect(callsTo(f, "GET", "/api/investigations/inv-1/events")).toHaveLength(1);
    expect(createObjectURL).toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "More" }));
    fireEvent.click(screen.getAllByRole("menuitem")[2]);
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Frees 2 MB");
    fireEvent.click(screen.getByRole("button", { name: "Delete investigation" }));
    expect(await screen.findByText("home")).toBeInTheDocument();
    click.mockRestore();
  });

  it("open report links to the investigation once Completed", () => {
    show(snap({ state: "Completed" }));
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    const open = screen.getAllByRole("menuitem")[1];
    expect(open).not.toHaveClass("is-disabled");
    expect(open).toHaveAttribute("href", "/investigations/inv-1");
  });
});
