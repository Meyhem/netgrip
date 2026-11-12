import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TopBar } from "./TopBar";
import { InvestigationRoute, screenFor } from "../screens/InvestigationRoute";
import { mockApi } from "../test/fetch";
import { POOLS, row, settings } from "../test/fixtures";
import type { InvestigationState } from "../api/types";

afterEach(() => vi.unstubAllGlobals());

describe("TopBar", () => {
  it("renders pools from the API in the README's format", async () => {
    mockApi({ "GET /api/system/pools": POOLS });
    render(<MemoryRouter><TopBar /></MemoryRouter>);
    const pools = await screen.findByLabelText("models 5/8 · search 1/4 · browsers 4/6 · today $3.12");
    expect(pools).toHaveClass("ng-pools");
    expect(pools.querySelectorAll("span")).toHaveLength(4);
    expect(pools).toHaveTextContent("today $3.12");
    expect(screen.getByText("grip").closest(".ng-brand")).toHaveTextContent("netgrip");
    expect(screen.getByRole("link", { name: "Investigations" })).toHaveClass("is-on");
  });
});

describe("InvestigationRoute", () => {
  it.each<[InvestigationState, string]>([
    ["Draft", "NewInvestigation"],
    ["Planning", "PlanReview"],
    ["Running", "ControlBoard"],
    ["Paused", "ControlBoard"],
    ["Stopped", "ControlBoard"],
    ["Synthesising", "ControlBoard"],
    ["Completed", "Report"],
  ])("%s → %s", (state, name) => {
    expect(screenFor(state)).toBe(name);
  });

  it("route /investigations/:id picks the screen by state", async () => {
    mockApi({
      "GET /api/investigations/inv-1": { seq: 3, investigation: { ...row({ state: "Planning" }), settings: {}, root_goal: null } },
      "GET /api/settings": settings(),
    });
    render(
      <MemoryRouter initialEntries={["/investigations/inv-1"]}>
        <Routes><Route path="/investigations/:id" element={<InvestigationRoute />} /></Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByText(/Plan review/)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveClass("ng-banner");
  });
});
