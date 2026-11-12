import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Investigations } from "./Investigations";
import { callsTo, mockApi } from "../test/fetch";
import { row, settings } from "../test/fixtures";
import type { InvestigationRow, InvestigationState } from "../api/types";

afterEach(() => vi.unstubAllGlobals());

function api(rows: InvestigationRow[] | (() => unknown), extra: Record<string, unknown> = {}) {
  return mockApi({
    "GET /api/investigations": rows,
    "GET /api/settings": settings(),
    "GET /api/system/storage": { total_bytes: 387 * 1024 * 1024, investigations: 6, pages: 0, data_dir: "/d" },
    ...extra,
  });
}

function show() {
  return render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<Investigations />} />
        <Route path="/investigations/:id" element={<p>opened</p>} />
        <Route path="/new" element={<p>new</p>} />
      </Routes>
    </MemoryRouter>,
  );
}

const bodyRows = () => screen.getAllByRole("row").slice(1);

describe("Investigations", () => {
  it("sorts needs-you first, then running, then last activity", async () => {
    api([
      row({ id: "a", prompt: "old draft", state: "Draft", last_activity_at: "2026-11-01T00:00:00Z" }),
      row({ id: "b", prompt: "running one", state: "Running" }),
      row({ id: "c", prompt: "recent completed", state: "Completed", last_activity_at: "2026-11-11T00:00:00Z" }),
      row({ id: "d", prompt: "paused one", state: "Paused", pause_cause: "user" }),
      row({ id: "e", prompt: "plan one", state: "Planning", last_activity_at: "2026-11-02T00:00:00Z" }),
    ]);
    show();
    await screen.findByText("old draft");
    const prompts = bodyRows().map((r) => r.querySelector(".ng-heading")!.textContent);
    expect(prompts).toEqual(["paused one", "plan one", "running one", "recent completed", "old draft"]);
  });

  it("sets the tab title to the needs-you count", async () => {
    api([row({ id: "a", state: "Planning" }), row({ id: "b", state: "Paused", pause_cause: "user" }), row({ id: "c", state: "Running" })]);
    show();
    await waitFor(() => expect(document.title).toBe("(2) Netgrip"));
  });

  it("tab title is Netgrip with nobody waiting", async () => {
    api([row({ state: "Running" })]);
    show();
    await screen.findAllByRole("row");
    await waitFor(() => expect(document.title).toBe("Netgrip"));
  });

  it.each<[InvestigationState, string, boolean]>([
    ["Draft", "Continue", false],
    ["Planning", "Review plan", true],
    ["Running", "Pause", false],
    ["Paused", "Resume", true],
    ["Stopped", "Finish into a report", false],
    ["Completed", "Open report", false],
    ["Synthesising", "Open", false],
  ])("one action button per row, chosen by state: %s → %s", async (state, label, steer) => {
    api([row({ state, pause_cause: state === "Paused" ? "user" : null })]);
    show();
    const r = (await screen.findAllByRole("row"))[1];
    const actions = within(r.querySelector("td:last-child") as HTMLElement).getAllByRole("button");
    const primary = actions.filter((b) => b.getAttribute("aria-haspopup") !== "menu");
    expect(primary).toHaveLength(1);
    expect(primary[0]).toHaveTextContent(label);
    expect(primary[0].classList.contains("ng-btn--steer")).toBe(steer);
    fireEvent.click(primary[0]);
    expect(await screen.findByText("opened")).toBeInTheDocument();
  });

  it('Paused row shows cause and "Nothing is lost"', async () => {
    api([row({ state: "Paused", pause_cause: "model_unavailable", pause_detail: "Model service stopped responding at 02:14." })]);
    show();
    const warn = await screen.findByText("Model service stopped responding at 02:14.");
    expect(warn).toHaveClass("ng-warn");
    expect(warn.parentElement).toHaveTextContent("Nothing is lost.");
    expect(screen.getByText("Paused · model service unavailable")).toHaveClass("ng-pill--warn");
  });

  it("a long prompt is clipped to one line with the full text in title", async () => {
    const long = "word ".repeat(1500).trim();
    api([row({ prompt: long })]);
    show();
    const heading = await screen.findByTitle(long);
    expect(heading).toHaveClass("ng-heading", "ng-clip");
  });

  it("empty state shows the prompt box and no table", async () => {
    api([]);
    show();
    expect(await screen.findByText(/Ask a question or state a claim\. Netgrip will check it, including the parts you take for granted\./)).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Your question or claim" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("API failure shows a warn banner, not the empty state", async () => {
    api(() => { throw new TypeError("Failed to fetch"); });
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    show();
    const banner = await screen.findByRole("alert");
    expect(banner).toHaveClass("ng-banner--warn");
    expect(screen.queryByText(/Ask a question or state a claim/)).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("delete dialog names prompt and freed space and calls DELETE", async () => {
    let rows = [row({ id: "inv-9", prompt: "Is coffee bad for you?", disk_bytes: 38 * 1024 * 1024 })];
    const fetchMock = api(() => rows, {
      "DELETE /api/investigations/inv-9": () => { rows = []; return new Response(null, { status: 204 }); },
    });
    show();
    await screen.findByText("Is coffee bad for you?");
    fireEvent.click(screen.getByRole("button", { name: "More" }));
    fireEvent.click(screen.getByRole("menuitem", { name: /Delete investigation/ }));
    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Is coffee bad for you?");
    expect(dialog).toHaveTextContent("38 MB");
    const del = within(dialog).getByRole("button", { name: "Delete investigation" });
    expect(del).toHaveClass("ng-btn--danger");
    fireEvent.click(del);
    await waitFor(() => expect(callsTo(fetchMock, "DELETE", "/api/investigations/inv-9")).toHaveLength(1));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("title row counts active against the limit, and filters", async () => {
    api([
      row({ id: "a", state: "Running", prompt: "alpha" }),
      row({ id: "b", state: "Paused", pause_cause: "user", prompt: "beta" }),
      row({ id: "c", state: "Completed", prompt: "gamma" }),
      row({ id: "d", state: "Draft", prompt: "delta" }),
    ]);
    show();
    expect(await screen.findByText("2 active of 5 allowed · 387 MB on disk")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Needs you 1" }));
    expect(bodyRows()).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "All 4" }));
    fireEvent.change(screen.getByLabelText("Search"), { target: { value: "gam" } });
    expect(bodyRows()).toHaveLength(1);
    expect(screen.getByText("gamma")).toBeInTheDocument();
  });
});
