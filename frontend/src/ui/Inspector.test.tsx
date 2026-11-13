import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { DurableEvent, GraphNode, NodeDetail, Snapshot } from "../api/types";
import { timeOfDaySeconds } from "../lib/format";
import { forgetInvestigation } from "../state/investigationStore";
import { emptySnapshot } from "../state/reduce";
import { mockApi } from "../test/fetch";
import { claim, claimSource, graphNode, nodeDetail } from "../test/fixtures";
import { Brief } from "./Brief";
import { ClaimCard } from "./ClaimCard";
import { Confidence } from "./Confidence";
import { Inspector } from "./Inspector";
import { seqLabel } from "./Instruction";

const ID = "inv-1";

function snap(nodes: GraphNode[], over: Partial<Snapshot> = {}): Snapshot {
  const base = emptySnapshot(ID);
  return { ...base, seq: 100, nodes, investigation: { ...base.investigation, state: "Running", spending_limit_usd: 5 }, ...over };
}

const ev = (seq: number, type: string, node_id: string | null, data: Record<string, unknown> = {}): DurableEvent => ({
  seq, investigation_id: ID, type, v: 1, at: `2026-11-13T10:00:${String(seq % 60).padStart(2, "0")}Z`,
  actor: "node", node_id, command_id: null, data,
});

const R = graphNode({ id: "R", display_id: "R", kind: "Synthesis", status: "Waiting on children", question: "Why is the Great Wall visible from space?" });
const kid = (id: string, over: Partial<GraphNode> = {}) =>
  graphNode({ id, display_id: id, parent_id: "R", depth: 1, status: "Pending", question: `Question of ${id}`, ...over });

function serve(details: Record<string, NodeDetail>) {
  return mockApi({ [`GET /api/investigations/${ID}/nodes/*`]: (url: string) => details[decodeURIComponent(url.split("/").pop()!)] });
}

function show(s: Snapshot, nodeId: string | null, events: DurableEvent[] = []) {
  return render(<Inspector investigationId={ID} s={s} events={events} nodeId={nodeId} />);
}

const overview = () => document.querySelector('[data-tab="overview"]') as HTMLElement;

beforeEach(() => forgetInvestigation(ID));
afterEach(() => vi.unstubAllGlobals());

describe("Inspector", () => {
  it("nothing selected shows the root", async () => {
    serve({ R: nodeDetail(R) });
    show(snap([R, kid("D1")]), null);
    expect(await screen.findByRole("heading", { name: R.question })).toHaveClass("ng-heading");
    expect(document.querySelector("[data-node-id]")).toHaveAttribute("data-node-id", "R");
    expect(screen.getByText("SYN")).toHaveClass("ng-tag");
    expect(screen.getByText("R · depth 0")).toBeInTheDocument();
  });

  it("header: kind, id, depth, status, inclusion when not Included, the question and Why", async () => {
    const D = kid("D2b", { kind: "Deep-dive", depth: 2, status: "Completed", inclusion: "Ignored", justification: "If the photo needed a long lens, it does not support naked-eye visibility." });
    serve({ D2b: nodeDetail(D) });
    show(snap([R, D]), "D2b");
    await screen.findByRole("heading", { name: D.question });
    expect(screen.getByText("DEEP")).toHaveClass("ng-tag");
    expect(screen.getByText("D2b · depth 2")).toBeInTheDocument();
    const pills = [...document.querySelectorAll(".inspector__head .ng-pill")].map((p) => p.textContent);
    expect(pills).toEqual(["✓Completed", "⦸Ignored by you"]);
    expect(screen.getByText(D.justification!).closest("p")).toHaveTextContent(/^Why/);
    // Tabs, in order.
    expect([...document.querySelectorAll(".ng-tab")].map((t) => t.textContent?.replace(/\d+$/, ""))).toEqual(["Overview", "Claims", "Brief", "Trail", "Instructions"]);
  });

  describe("overview per state", () => {
    it("Running: Now block, verdict not yet, claims so far, branch meters, inherited instructions", async () => {
      vi.useFakeTimers({ now: new Date("2026-11-13T10:01:22Z"), shouldAdvanceTime: true });
      try {
        const D = kid("D2b", { status: "Running", activity: "Extracting", budget: { child_nodes: 0, sources: 8 }, spent_usd: 0.14 });
        serve({
          D2b: nodeDetail(D, {
            claims: [claim({ id: "C-040", status: "Supported", text: "Chiao photographed a section of the Wall." })],
            trail: [
              { step: 1, name: "read", kind: "fetch", activity: "Reading", detail: "a", summary: null, started_at: "x", ended_at: "y", route: "simple", page_version_id: "pv1", retry: null, instruction_applied: [] },
              { step: 2, name: "extract", kind: null, activity: "Extracting", detail: "4 claims", summary: null, started_at: "x", ended_at: null, route: null, page_version_id: null, retry: null, instruction_applied: [] },
            ],
            instructions: { inherited: [{ id: "i1", node_id: "R", text: "Only first-hand statements.", state: "applied", queued_seq: 412, applied_seq: 413, diff: null, undone: false, from_display_id: "R" }], own: [] },
          }),
        });
        show(snap([R, D]), "D2b", [ev(10, "node.started", "D2b"), ev(12, "node.activity", "D2b", { activity: "Extracting", detail: "4 claims · nasa.gov/great_wall", step: "extract" })]);
        await screen.findByText("Chiao photographed a section of the Wall.");
        const o = overview();
        expect(o.querySelector(".ng-activity__verb")).toHaveTextContent("Extracting");
        expect(o.querySelector(".ng-activity__what")).toHaveTextContent("4 claims · nasa.gov/great_wall");
        expect(within(o).getByText(/step 2 · 1:12 in this run · 1 of 8 sources read/)).toBeInTheDocument();
        expect(within(o).getByText("not yet · appears here the moment it exists")).toBeInTheDocument();
        expect(within(o).getByText("Claims so far")).toBeInTheDocument();
        expect([...o.querySelectorAll(".ng-meter .ng-label")].map((l) => l.textContent)).toEqual(["Spend", "Sources"]);
        expect(o.querySelector(".ng-instr--inherited")).toHaveTextContent("Only first-hand statements.");
      } finally {
        vi.useRealTimers();
      }
    });

    it("Completed: verdict first, then open questions and proposed follow-ups with the decision", async () => {
      const D = kid("D2a", { status: "Completed", verdict: { text: "Yang Liwei could not see the Wall.", confidence: "high" }, spent_usd: 0.21 });
      const F = kid("D2a1", { parent_id: "D2a", status: "Proposed", question: "Statements by Shenzhou 6 crews" });
      const G = kid("D2a2", { parent_id: "D2a", status: "Rejected", question: "Tourism brochures" });
      serve({
        D2a: nodeDetail(D, {
          claims: [claim({ id: "C1", supporting: [claimSource({ id: "s1", origin_key: "nasa" }), claimSource({ id: "s2", origin_key: "nasa" }), claimSource({ id: "s3", origin_key: "space" })] })],
          open_questions: ["Whether later astronauts reported differently."],
          proposals: [
            { node_id: "D2a1", display_id: "D2a1", question: F.question, decision: "pending", reason: null },
            { node_id: "D2a2", display_id: "D2a2", question: G.question, decision: "rejected", reason: "outside the question" },
          ],
        }),
      });
      show(snap([R, D, F, G]), "D2a", [ev(20, "page.unobtainable", "D2a", { url: "x" })]);
      await screen.findByText("Whether later astronauts reported differently.");
      const o = overview();
      expect(o.firstElementChild).toHaveTextContent(/^Verdict/);
      expect(o.firstElementChild).toHaveTextContent("Yang Liwei could not see the Wall.");
      expect(o.firstElementChild).toHaveTextContent("1 claim · 2 independent sources · $0.21 · 1 page unobtainable");
      expect(within(o).getByText("Open questions")).toBeInTheDocument();
      const follow = within(o).getByText("Follow-ups it proposed").parentElement!;
      expect(follow).toHaveTextContent("Statements by Shenzhou 6 crews◌Proposed");
      expect(follow).toHaveTextContent("Tourism brochures⊘Rejected");
      expect(follow).toHaveTextContent("outside the question");
    });

    it("Rejected: only the proposal, who proposed it and the reason", async () => {
      const P = kid("D1b", { status: "Completed" });
      const D = kid("D1b1", { parent_id: "D1b", status: "Rejected", proposed_by: "D1b", question: "Tourism marketing claims", justification: "Brochures repeat the myth.", rejection_reason: "duplicates D1" });
      serve({ D1b1: nodeDetail(D, { claims: [claim({ id: "C9" })] }) });
      show(snap([R, P, D]), "D1b1");
      await screen.findByText("Proposed by D1b");
      const o = overview();
      expect(o).toHaveTextContent("Tourism marketing claims");
      expect(o).toHaveTextContent("Brochures repeat the myth.");
      expect(o).toHaveTextContent("Rejected by the orchestrator: duplicates D1");
      expect(o.querySelector(".ng-panel, .ng-meter, .ng-claim, .ng-instr")).toBeNull();
    });

    it("Ignored: who excluded it and when, what is kept", async () => {
      const D = kid("D4", { status: "Completed", inclusion: "Ignored", excluded_by: "user", excluded_at: "2026-11-13T14:00:02Z", spent_usd: 0.04 });
      serve({ D4: nodeDetail(D, { claims: [claim({ id: "C1" })] }) });
      show(snap([R, D]), "D4", [ev(98, "node.inclusion_changed", null, { node_ids: ["D4"], inclusion: "Ignored", by: "user" })]);
      await screen.findByText(/1 claim kept in storage/);
      const o = overview();
      expect(o.querySelector(".ng-pill")).toHaveTextContent("Ignored by you");
      expect(o).toHaveTextContent(`${timeOfDaySeconds("2026-11-13T14:00:02Z")} · ${seqLabel(98)}`);
      expect(o).toHaveTextContent("This branch is stopped. Its 1 claim is kept out of the report, and the report will list the branch as excluded.");
      expect(o.querySelector(".ng-well")).toHaveTextContent("1 node · $0.04 spent · 1 claim kept in storage");
    });

    it("Failed: the verdict in its failed state", async () => {
      const D = kid("D3", { status: "Failed", failure_reason: "Both searches returned nothing usable." });
      serve({ D3: nodeDetail(D) });
      show(snap([R, D]), "D3");
      await screen.findByText("Both searches returned nothing usable.");
      const o = overview();
      const v = o.querySelector(".ng-panel")!;
      expect(v).toHaveTextContent(/^No verdict/);
      expect(v.querySelector(".ng-pill--danger")).toHaveTextContent("Failed");
    });

    it("a coordinator waiting on its children without a brief says so (no crash)", async () => {
      serve({ R: nodeDetail(R, { brief: null }) });
      show(snap([R, kid("D1")]), null);
      expect(await within(overview()).findByText("This node has not started its own work; it waits on its children.")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("tab", { name: "Brief" }));
      expect(screen.getByText("This node has not started its own work; it waits on its children.")).toBeInTheDocument();
      expect(document.querySelector(".ng-brief")).toBeNull();
    });
  });

  it("claims empty copy", async () => {
    const D = kid("D1", { status: "Running" });
    serve({ D1: nodeDetail(D) });
    show(snap([R, D]), "D1");
    fireEvent.click(screen.getByRole("tab", { name: /Claims/ }));
    expect(await screen.findByText("No claims yet. They appear here as pages are read.")).toBeInTheDocument();
  });

  it("claim filter by status", async () => {
    const D = kid("D1", { status: "Completed" });
    serve({
      D1: nodeDetail(D, {
        claims: [
          claim({ id: "C1", status: "Confirmed", text: "first" }),
          claim({ id: "C2", status: "Contested", text: "second" }),
          claim({ id: "C3", status: "Confirmed", text: "third" }),
        ],
      }),
    });
    show(snap([R, D]), "D1");
    fireEvent.click(screen.getByRole("tab", { name: /Claims/ }));
    await screen.findByText("first");
    const tags = () => [...document.querySelectorAll(".inspector__filter")].map((t) => t.textContent);
    expect(tags()).toEqual(["All 3", "Confirmed 2", "Contested 1"]);
    expect(screen.getByRole("button", { name: "All 3" })).toHaveClass("ng-tag--solid");
    fireEvent.click(screen.getByRole("button", { name: "Contested 1" }));
    expect(screen.getByRole("button", { name: "Contested 1" })).toHaveClass("ng-tag--solid");
    expect(screen.queryByText("first")).toBeNull();
    expect(screen.getByText("second")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "All 3" }));
    expect(document.querySelectorAll(".ng-claim")).toHaveLength(3);
  });

  it("instructions tab: inherited from the root down, then the node's own", async () => {
    const D = kid("D2", { status: "Running" });
    const i = (id: string, node_id: string, seq: number) => ({ id, node_id, text: `text ${id}`, state: "applied" as const, queued_seq: seq, applied_seq: seq + 1, diff: null, undone: false });
    serve({ D2: nodeDetail(D, { instructions: { inherited: [{ ...i("a", "R", 10), from_display_id: "R" }], own: [i("b", "D2", 20), { ...i("c", "D2", 30), state: "queued", applied_seq: null }] } }) });
    show(snap([R, D]), "D2");
    fireEvent.click(await screen.findByRole("tab", { name: /Instructions\s*3/ }));
    const blocks = [...document.querySelectorAll('[data-tab="instructions"] .ng-instr')];
    expect(blocks.map((b) => b.querySelector(".ng-instr__text")!.textContent)).toEqual(["text a", "text b", "text c"]);
    expect(blocks[0]).toHaveClass("ng-instr--inherited");
    expect(blocks[0]).toHaveTextContent("Inherited from R");
    expect(blocks[2]).toHaveClass("ng-instr--queued");
  });

  it("brief shows root goal verbatim and the path", async () => {
    const goal = "Why is the Great Wall of China visible from space with the naked eye?  <b>verbatim</b>";
    const D = kid("D2b", { depth: 2, status: "Running", justification: "If the photo needed a long lens…" });
    serve({
      D2b: nodeDetail(D, {
        brief: {
          root_goal: goal,
          path: [
            { display_id: "R", question: "answer the question as asked", justification: null },
            { display_id: "D2", question: "first-hand reports", justification: null },
          ],
          task: { question: "Establish who took the photo.", out_of_scope: "Satellite imagery.", done_when: "Lens confirmed.", budget: { sources: 8, child_nodes: 0 } },
          known: { claims: [{ id: "C-031", text: "t", status: "Confirmed" }], dependency_results: [{ display_id: "D2a", verdict: { text: "v", confidence: "high" } }], instructions: [] },
        },
      }),
    });
    show(snap([R, D]), "D2b");
    fireEvent.click(screen.getByRole("tab", { name: "Brief" }));
    const dl = await waitForBrief();
    const rows = Object.fromEntries([...dl.querySelectorAll("dt")].map((dt) => [dt.textContent, dt.nextElementSibling as HTMLElement]));
    expect(Object.keys(rows)).toEqual(["Root goal", "Path", "Why", "Task", "Out of scope", "Done when", "Known", "Budget"]);
    expect(rows["Root goal"].textContent).toBe(goal);
    expect(rows["Root goal"].querySelector("b")).toBeNull();
    const path = [...rows["Path"].children];
    expect(path.map((p) => p.textContent)).toEqual(["R → answer the question as asked", "D2 → first-hand reports", "D2b → Establish who took the photo."]);
    expect(path[0]).toHaveClass("ng-muted");
    expect(path[2]).not.toHaveClass("ng-muted");
    expect(rows["Known"]).toHaveTextContent("C-031 · result of D2a");
  });

  it("detail that fails to load shows the error state", async () => {
    mockApi({ [`GET /api/investigations/${ID}/nodes/*`]: () => new Response("{}", { status: 500 }) });
    show(snap([R]), null);
    expect(await screen.findByText("Netgrip cannot reach its service.")).toBeInTheDocument();
  });

  it("loading shows an activity line, not a shimmer", () => {
    mockApi({ [`GET /api/investigations/${ID}/nodes/*`]: () => new Promise(() => {}) });
    show(snap([R]), null);
    expect(overview().querySelector(".ng-activity")).toHaveTextContent("Loading");
  });

  it("slots: node actions in the header and a composer pinned at the bottom", async () => {
    serve({ R: nodeDetail(R) });
    render(<Inspector investigationId={ID} s={snap([R])} events={[]} nodeId={null} nodeActions={<button>acts</button>} composer={<div>compose</div>} />);
    expect(screen.getByText("acts").closest(".inspector__head")).not.toBeNull();
    expect(screen.getByText("compose").closest(".inspector__composer")).not.toBeNull();
  });
});

async function waitForBrief(): Promise<HTMLElement> {
  return (await screen.findByText("Root goal")).closest("dl") as HTMLElement;
}

describe("evidence components", () => {
  it("confidence renders bars and the word", () => {
    const { container } = render(<Confidence level="medium" />);
    const c = container.querySelector(".ng-conf")!;
    expect(c.querySelectorAll(".ng-conf__bars b")).toHaveLength(3);
    expect(c.querySelectorAll(".ng-conf__bars b.is-on")).toHaveLength(2);
    expect(c).toHaveTextContent("Medium confidence");
  });

  it("weak source is dashed, unobtainable is ng-src--lost", () => {
    render(
      <ClaimCard
        claim={claim({
          id: "C-042", status: "Contested", node_id: "D2c",
          supporting: [claimSource({ id: "w", credibility: "Weak", url: "https://travelblog.example/wall" }), claimSource({ id: "l", page_version_id: null, url: "https://xinhuanet.com/x" })],
          contradicting: [claimSource({ id: "p", credibility: "Primary", url: "https://nasa.gov/great_wall" })],
        })}
        nodeDisplayIds={{ D2c: "D2c" }}
      />,
    );
    expect(screen.getByText("C-042 · from D2c")).toBeInTheDocument();
    expect(screen.getByText("WEAK")).toHaveClass("ng-tag", "ng-tag--dashed");
    expect(screen.getByText("travelblog.example/wall").closest(".ng-src")).not.toHaveClass("ng-src--lost");
    const lost = screen.getByText("xinhuanet.com/x").closest(".ng-src")!;
    expect(lost).toHaveClass("ng-src--lost");
    expect(lost).toHaveTextContent("LOST");
    expect(lost).toHaveTextContent("unobtainable");
    expect(screen.getByText("PRIMARY")).toHaveClass("ng-tag--solid");
    expect(screen.getByText("nasa.gov/great_wall").closest(".ng-src")).toHaveClass("ng-src--against");
    expect(screen.getByText("Supports · 2 independent")).toBeInTheDocument();
    expect(screen.getByText("Contradicts · 1")).toBeInTheDocument();
    expect(document.querySelector(".ng-pill--warn")).toHaveTextContent("Contested");
  });

  it("claim and page text are inert text", () => {
    render(<ClaimCard claim={claim({ id: "C1", text: '<img src=x onerror="alert(1)">' })} nodeDisplayIds={{}} />);
    expect(document.querySelector("img")).toBeNull();
    expect(screen.getByText('<img src=x onerror="alert(1)">')).toHaveClass("ng-claim__text");
  });

  it("brief without a stored brief says so", () => {
    render(<Brief brief={null} node={graphNode({ id: "D1", status: "Pending" })} />);
    expect(screen.getByText("This node has not started. Its brief is written when it starts.")).toBeInTheDocument();
  });
});
