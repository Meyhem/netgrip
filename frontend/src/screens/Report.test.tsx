import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { Report as ReportData, ReportClaim, ReportSection } from "../api/types";
import { forgetInvestigation } from "../state/investigationStore";
import { forgetSelection } from "../state/selection";
import { runContract } from "../test/contract";
import { FakeEventSource } from "../test/eventSource";
import { mockApi } from "../test/fetch";
import { settings } from "../test/fixtures";
import { InvestigationRoute } from "./InvestigationRoute";

const { snapshots } = runContract();
const done = snapshots[snapshots.length - 1];
const ID = done.investigation.id;
const p1 = done.nodes.find((n) => n.display_id === "P1")!;
const d1 = done.nodes.find((n) => n.display_id === "D1")!;
const root = done.nodes.find((n) => n.parent_id === null)!;

beforeEach(() => {
  FakeEventSource.reset();
  forgetInvestigation(ID);
  forgetSelection(ID);
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => vi.unstubAllGlobals());

const claim = (id: string, label: string, over: Partial<ReportClaim> = {}): ReportClaim => ({
  id, label, node_id: d1.id, text: `Text of ${label}`, status: "Confirmed", supporting: [{
    id: `s-${id}`, url: `https://example.org/${id}`, title: null, page_version_id: "pv", credibility: "Primary",
    published_at: "2005-02-01", origin_key: "nasa",
  }], contradicting: [], node_display_id: "D1",
  path: [{ id: root.id, display_id: "R", question: "Root question" }, { id: d1.id, display_id: "D1", question: "Astronaut accounts" }],
  ...over,
});

function report(over: Partial<ReportData> = {}, wrong = true): ReportData {
  const sections: ReportSection[] = [
    { key: "answer", title: "The answer", statements: [
      { text: "No, it cannot be seen unaided.", claim_ids: ["c1"], hedged: false, premise_node_id: null },
      { text: "It was reported to be narrow.", claim_ids: ["c2"], hedged: true, premise_node_id: null },
    ] },
    ...(wrong ? [{ key: "wrong" as const, title: "Where you were wrong", statements: [
      { text: "Astronauts report it is not visible.", claim_ids: ["c1"], hedged: false, premise_node_id: p1.id },
    ] }] : []),
    { key: "findings", title: "Key findings", statements: [
      { text: "The Wall is nine metres wide.", claim_ids: ["c1", "c3"], hedged: false, premise_node_id: null },
      { text: "It may go back to a 1754 letter.", claim_ids: ["c2"], hedged: true, premise_node_id: null },
    ] },
    { key: "unverified", title: "What could not be verified", statements: [] },
    { key: "limits", title: "Limits of this investigation", statements: [
      { text: "Effort: Medium. A claim counts as Confirmed with 2 independent sources.", claim_ids: [], hedged: false, premise_node_id: null },
    ] },
  ];
  return {
    id: "r1", investigation_id: ID, created_at: "2026-11-13T14:00:00Z", answer_confidence: "medium", sections,
    limits: {
      effort: "Medium", confirm_threshold: 2, ended_early: false, cut_short_by: null, unobtainable_pages: [],
      excluded_branches: [], instructions: [], excluded_domains: [],
    },
    totals: { claims: 4, sources: 3, nodes: 7, spent_usd: 0.4, run_seconds: 2492 },
    claims: {
      c1: claim("c1", "C-001"), c3: claim("c3", "C-003"),
      c2: claim("c2", "C-002", { status: "Supported" }),
    },
    premises: [{ text: "The Wall is visible from low Earth orbit.", outcome: "refuted", node_id: p1.id, display_id: "P1" }],
    ...over,
  };
}

function show(r: ReportData | null, snapshot = done, routes: Record<string, unknown> = {}) {
  mockApi({
    [`GET /api/investigations/${ID}`]: snapshot,
    [`GET /api/investigations/${ID}/report`]: r ?? new Response(JSON.stringify({ code: "no_report", message: "x" }), { status: 404 }),
    "GET /api/settings": settings(),
    ...routes,
  });
  render(
    <MemoryRouter initialEntries={[`/investigations/${ID}`]}>
      <Routes>
        <Route path="/investigations/:id" element={<InvestigationRoute />} />
        <Route path="/investigations/:id/board" element={<div>the board</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

const sectionTitles = () => [...document.querySelectorAll(".ng-report .ng-label, .ng-report .ng-title, .ng-report .ng-banner__t")].map((e) => e.textContent);

describe("Report screen", () => {
  it("sections render in the fixed order", async () => {
    show(report());
    await screen.findByText("Where you were wrong", { selector: ".ng-banner__t" });
    expect(sectionTitles()).toEqual(["The answer", "Where you were wrong", "Key findings", "What could not be verified", "Limits of this investigation"]);
  });

  it('"Where you were wrong" is absent without a refuted premise', async () => {
    show(report({ premises: [] }, false));
    await screen.findByText("Key findings");
    expect(screen.queryByText("Where you were wrong", { selector: ".ng-banner__t" })).toBeNull();
    expect(screen.queryByText(/Where you were wrong/)).toBeNull();
  });

  it("the wrong section is a danger banner quoting the assumption and citing the premise node", async () => {
    show(report());
    const banner = (await screen.findByText("Where you were wrong", { selector: ".ng-banner__t" })).closest(".ng-banner")!;
    expect(banner).toHaveClass("ng-banner--danger");
    expect(banner).toHaveTextContent("Your question assumed The Wall is visible from low Earth orbit.");
    expect(within(banner as HTMLElement).getByRole("button", { name: "P1" })).toHaveClass("ng-cite");
  });

  it("the answer's first sentence is display, with a confidence readout above it", async () => {
    show(report());
    const h2 = await screen.findByRole("heading", { name: /No, it cannot be seen unaided/ });
    expect(h2).toHaveClass("ng-display");
    const label = document.querySelector("#report-answer .ng-row")!;
    expect(label).toHaveTextContent("The answer");
    expect(label.querySelector(".ng-conf")).toHaveTextContent("Medium confidence");
    expect(label.compareDocumentPosition(h2) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("every statement outside Limits ends in at least one citation", async () => {
    show(report());
    await screen.findByText("Key findings");
    const statements = document.querySelectorAll("#report-answer h2, #report-answer p, #report-findings p, #report-wrong .ng-banner .ng-col > span:not(.ng-banner__t)");
    expect(statements.length).toBe(5);
    for (const s of statements) expect(s.querySelector(".ng-cite")).not.toBeNull();
  });

  it("a hedged statement has ng-hedge underline and its status pill", async () => {
    show(report());
    const hedged = (await screen.findByText("It may go back to a 1754 letter.")).closest("p")!;
    expect(hedged.querySelector(".ng-hedge")).toHaveTextContent("It may go back");
    expect(hedged.querySelector(".ng-pill")).toHaveTextContent("Supported");
    const plain = screen.getByText("The Wall is nine metres wide.").closest("p")!;
    expect(plain.querySelector(".ng-hedge")).toBeNull();
  });

  it("clicking a citation opens the evidence pane and fills the chip; clicking again closes it", async () => {
    show(report());
    await screen.findByText("Key findings");
    expect(screen.queryByLabelText("Evidence")).toBeNull();
    const chip = within(screen.getByText("The Wall is nine metres wide.").closest("p")!).getByRole("button", { name: "C-003" });
    fireEvent.click(chip);
    const pane = await screen.findByLabelText("Evidence");
    expect(chip).toHaveClass("is-open");
    expect(pane).toHaveTextContent("Evidence for C-003");
    expect(document.querySelector(".report-body")).not.toHaveClass("report-body--closed");
    fireEvent.click(chip);
    expect(screen.queryByLabelText("Evidence")).toBeNull();
    expect(chip).not.toHaveClass("is-open");
    expect(document.querySelector(".report-body")).toHaveClass("report-body--closed");
  });

  it("the evidence pane lists the node path and other uses, and links to the board", async () => {
    show(report());
    await screen.findByText("Key findings");
    fireEvent.click(within(screen.getByText("The Wall is nine metres wide.").closest("p")!).getByRole("button", { name: "C-001" }));
    const pane = await screen.findByLabelText("Evidence");
    expect(pane).toHaveTextContent("R Root question");
    expect(pane).toHaveTextContent("D1 Astronaut accounts");
    expect(pane).toHaveTextContent("The answer, sentence 1 · Where you were wrong, item 1 · Key findings, item 1");
    expect(within(pane).getByRole("link", { name: "show on the board" })).toHaveAttribute("href", `/investigations/${ID}/board`);
  });

  it("Export Markdown links to /report.md and Open the board to the board", async () => {
    show(report());
    expect(await screen.findByRole("link", { name: "Export Markdown" })).toHaveAttribute("href", `/api/investigations/${ID}/report.md`);
    expect(screen.getByRole("link", { name: "Open the board" })).toHaveAttribute("href", `/investigations/${ID}/board`);
    expect(screen.queryByText("Ask a follow-up")).toBeNull();
    expect(document.querySelector(".ng-btn--steer")).toBeNull();
  });

  it("the header says effort, run time, spend and ended early", async () => {
    const r = report();
    r.limits = { ...r.limits, ended_early: true, cut_short_by: "finish_now" };
    show(r);
    await screen.findByText("Key findings");
    const head = document.querySelector(".ng-board__head")!;
    expect(head.querySelector(".ng-pill")).toHaveTextContent("Completed");
    expect(head).toHaveTextContent("Medium");
    expect(head).toHaveTextContent("0:41:32");
    expect(head).toHaveTextContent("ended early by you");
  });

  it("limits render exclusions and narrowing as Instruction blocks", async () => {
    const r = report();
    r.limits = {
      ...r.limits, unobtainable_pages: ["https://example.org/blocked"],
      excluded_branches: [{ display_id: "D4", question: "Other structures visible from orbit", by: "user" }],
      instructions: [{ text: "Only first-hand statements.", node_display_id: "D2", seq: 12 }],
    };
    show(r);
    await screen.findByRole("heading", { name: "Limits of this investigation" });
    const blocks = [...document.querySelectorAll("#report-limits .ng-instr")];
    expect(blocks).toHaveLength(2);
    expect(blocks[0]).toHaveTextContent("You excluded · D4");
    expect(blocks[0]).toHaveTextContent("Other structures visible from orbit");
    expect(blocks[1]).toHaveTextContent("You narrowed · D2");
    expect(blocks[1]).toHaveTextContent("Only first-hand statements.");
    expect(document.querySelector("#report-limits")).toHaveTextContent("1 page could not be obtained");
  });

  it("the contents show counts, with the wrong section in danger", async () => {
    show(report());
    const nav = await screen.findByRole("navigation", { name: "Report" });
    expect(within(nav).getByText("Where you were wrong · 1")).toHaveClass("ng-danger");
    expect(within(nav).getByText("Key findings · 2")).toBeInTheDocument();
    expect(nav).toHaveTextContent("Medium effort: a claim is Confirmed with 2 independent sources.");
  });

  it("synthesising shows the headings and the activity line only", async () => {
    const synth = { ...done, investigation: { ...done.investigation, state: "Synthesising" as const }, synthesis_claims: 61 };
    show(null, synth);
    expect(await screen.findByText("from 61 claims…")).toHaveClass("ng-activity__what");
    expect([...document.querySelectorAll(".ng-report .ng-title")].map((e) => e.textContent)).toEqual([
      "The answer", "Where you were wrong", "Key findings", "What could not be verified", "Limits of this investigation",
    ]);
    expect(document.querySelectorAll(".ng-report p, .ng-cite, .ng-display")).toHaveLength(0);
    expect(screen.queryByRole("link", { name: "Export Markdown" })).toBeNull();
  });

  it("a Completed investigation without a stored report says so", async () => {
    show(null);
    await waitFor(() => expect(screen.getByText("This investigation has no stored report.")).toBeInTheDocument());
  });
});
