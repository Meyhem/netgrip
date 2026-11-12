import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TopBar } from "./TopBar";
import { InvestigationRoute, screenFor } from "../screens/InvestigationRoute";
import { mockApi } from "../test/fetch";
import { POOLS, row, settings } from "../test/fixtures";
import type { InvestigationSettings, InvestigationState } from "../api/types";
import { FakeEventSource } from "../test/eventSource";
import { emptySnapshot } from "../state/reduce";

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
    FakeEventSource.reset();
    vi.stubGlobal("EventSource", FakeEventSource);
    const planning = { ...emptySnapshot("inv-1"), seq: 3, investigation: { ...emptySnapshot("inv-1").investigation, ...row({ state: "Planning" }), settings: {} as InvestigationSettings, root_goal: null } };
    mockApi({
      "GET /api/investigations/inv-1": planning,
      "GET /api/investigations/inv-2": { ...planning, investigation: { ...planning.investigation, id: "inv-2", state: "Running" } },
      "GET /api/settings": settings(),
    });
    const { unmount } = render(
      <MemoryRouter initialEntries={["/investigations/inv-1"]}>
        <Routes><Route path="/investigations/:id" element={<InvestigationRoute />} /></Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole("button", { name: "Approve plan and start" })).toHaveClass("ng-btn--steer");
    expect(document.querySelector(".ng-board__head .ng-pill")).toHaveTextContent("Plan review");
    unmount();
    render(
      <MemoryRouter initialEntries={["/investigations/inv-2"]}>
        <Routes><Route path="/investigations/:id" element={<InvestigationRoute />} /></Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByRole("status")).toHaveClass("ng-banner");
    expect(document.querySelector(".ng-pill")).toHaveTextContent("Running");
  });
});
