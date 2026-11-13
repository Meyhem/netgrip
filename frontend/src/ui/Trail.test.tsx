import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { GraphNode, NodeDetail, Snapshot, TrailStep } from "../api/types";
import { timeOfDaySeconds } from "../lib/format";
import { forgetInvestigation } from "../state/investigationStore";
import { emptySnapshot } from "../state/reduce";
import { mockApi } from "../test/fetch";
import { graphNode, nodeDetail } from "../test/fixtures";
import { Inspector } from "./Inspector";
import { PageSheet } from "./PageSheet";
import { Trail } from "./Trail";

const ID = "inv-1";
const D = graphNode({ id: "D2b", display_id: "D2b", parent_id: "R", depth: 2, status: "Running", question: "Who took the photo?" });

const step = (n: number, over: Partial<TrailStep> = {}): TrailStep => ({
  step: n, name: "read", kind: "fetch", activity: "Reading", detail: `detail ${n}`, summary: null,
  started_at: `2026-11-13T10:01:${String(10 + n).padStart(2, "0")}Z`, ended_at: `2026-11-13T10:01:${String(20 + n).padStart(2, "0")}Z`,
  route: null, page_version_id: null, retry: null, instruction_applied: [], ...over,
});

const wells = () => [...document.querySelectorAll(".trail .ng-well")] as HTMLElement[];
const stepWells = () => wells().filter((w) => w.dataset.step);

afterEach(() => {
  vi.unstubAllGlobals();
  forgetInvestigation(ID);
});

describe("Trail", () => {
  it("one well per step: number, time, verb, detail, stored page", () => {
    const d = nodeDetail(D, {
      trail: [
        step(1, { name: "plan", kind: "decision", activity: "Planning", detail: "find the caption", route: "search" }),
        step(2, { activity: "Reading", detail: "nasa.gov/vision", summary: "4.1 KB of text", route: "simple", page_version_id: "pv1" }),
      ],
    });
    render(<Trail detail={d} modelText={null} onOpenPage={() => {}} live running />);
    const [a, b] = stepWells();
    expect(a).toHaveTextContent(`step 1 · ${timeOfDaySeconds(d.trail[0].started_at)} · PLANNING find the caption`);
    expect(a).not.toHaveTextContent("stored page");
    expect(b).toHaveTextContent("READING nasa.gov/vision · simple fetch · 4.1 KB of text");
    expect(within(b).getByRole("button", { name: "stored page" })).toBeInTheDocument();
  });

  it("open step shows live text and the not-stored line", () => {
    const d = nodeDetail(D, {
      trail: [step(1), step(2, { name: "reason", kind: null, activity: "Reasoning", detail: "3 claims", ended_at: null })],
    });
    const text = '{"action": "conclude", "<b>bold</b>": 1}';
    const { rerender } = render(<Trail detail={d} modelText={{ node_id: "D2b", step: 2, text, at: "x" }} onOpenPage={() => {}} live running />);
    const [closed, open] = stepWells();
    expect(open).toHaveClass("trail__step--open");
    expect(closed).not.toHaveClass("trail__step--open");
    const liveText = open.querySelector(".trail__live")!;
    expect(liveText).toHaveTextContent(`${text}▍`);
    expect(liveText.querySelector("b")).toBeNull();
    expect(within(open).getByText("Live. This text is not stored.")).toBeInTheDocument();
    expect(closed.querySelector(".trail__live")).toBeNull();

    // Text for another step (a stale delta, or the next step before the detail refetch) is not shown.
    rerender(<Trail detail={d} modelText={{ node_id: "D2b", step: 3, text: "next step", at: "x" }} onOpenPage={() => {}} live running />);
    expect(document.querySelector(".trail__live")).toBeNull();
    expect(screen.queryByText("Live. This text is not stored.")).toBeNull();
  });

  it("closed steps show only persisted detail", () => {
    const d = nodeDetail(D, {
      trail: [step(1, { name: "reason", activity: "Reasoning", detail: "3 claims", summary: "conclude" }), step(2)],
    });
    // The store holds text for step 1, but step 1 is closed: only what was persisted shows.
    render(<Trail detail={d} modelText={{ node_id: "D2b", step: 1, text: "streamed words", at: "x" }} onOpenPage={() => {}} live running />);
    expect(screen.queryByText(/streamed words/)).toBeNull();
    expect(screen.queryByText("Live. This text is not stored.")).toBeNull();
    expect(document.querySelector(".trail__step--open")).toBeNull();
    expect(stepWells()[0]).toHaveTextContent("REASONING 3 claims · conclude");
  });

  it("retry steps are warn and name the route", () => {
    const d = nodeDetail(D, {
      trail: [
        step(1, { activity: "Retrying", retry: { n: 2, m: 3 }, detail: "space.com timed out", route: "browser" }),
        step(2, { activity: "Retrying", retry: { n: 3, m: 3 }, detail: "space.com blocked", route: "hardened" }),
        step(3, { activity: "Reading", detail: "nasa.gov", route: "simple" }),
        // An outage retry (model or search) has no fetch route: none is named.
        step(4, { name: "plan", activity: "Retrying", retry: { n: 2, m: 5 }, detail: "model unavailable", route: null }),
      ],
    });
    render(<Trail detail={d} modelText={null} onOpenPage={() => {}} live running />);
    const [r1, r2, read, outage] = stepWells();
    for (const w of [r1, r2, outage]) {
      expect(w).toHaveClass("trail__step--retry");
      expect(w.querySelector(".trail__verb")).toHaveClass("ng-warn");
    }
    expect(read).not.toHaveClass("trail__step--retry");
    expect(read.querySelector(".trail__verb")).not.toHaveClass("ng-warn");
    expect(r1).toHaveTextContent("RETRYING 2 OF 3 space.com timed out · full browser");
    expect(r2).toHaveTextContent("RETRYING 3 OF 3 space.com blocked · hardened browser");
    expect(read).toHaveTextContent("READING nasa.gov · simple fetch");
    expect(outage).toHaveTextContent(/RETRYING 2 OF 5 model unavailable$/);
    expect(outage).not.toHaveTextContent(/fetch|browser/);
  });

  it("steer rule at the instruction boundary", () => {
    const d = nodeDetail(D, {
      trail: [step(1), step(2, { instruction_applied: ["i1"] }), step(3), step(4, { instruction_applied: ["i2", "i3"] })],
      instructions: {
        inherited: [],
        own: ["i1", "i2", "i3"].map((id) => ({ id, node_id: "D2b", text: "x", state: "applied" as const, queued_seq: 1, applied_seq: 2, diff: null, undone: false })),
      },
    });
    render(<Trail detail={d} modelText={null} onOpenPage={() => {}} live running />);
    const all = wells();
    const rules = all.filter((w) => w.classList.contains("trail__rule"));
    expect(rules).toHaveLength(2);
    // Between step 2 and step 3, so the user sees it did not interrupt a step.
    expect(all.indexOf(rules[0])).toBe(all.indexOf(stepWells()[1]) + 1);
    expect(rules[0].querySelector(".ng-steer")).toHaveTextContent("— instruction from D2b applied here, between step 2 and step 3 —");
    expect(rules[1]).toHaveTextContent("— 2 instructions from D2b applied here, after step 4 —");
    expect(rules[1]).toBe(all[all.length - 1]);
  });

  describe("nothing runs: the open step is a plain well", () => {
    const open = () => nodeDetail(D, { trail: [step(1), step(2, { name: "reason", activity: "Reasoning", detail: "3 claims", ended_at: null })] });
    const mt = { node_id: "D2b", step: 2, text: "streamed words", at: "x" };
    const base = emptySnapshot(ID);
    const R = graphNode({ id: "R", display_id: "R", kind: "Synthesis", status: "Waiting on children" });
    const snapWith = (node: GraphNode, state: Snapshot["investigation"]["state"]): Snapshot =>
      ({ ...base, seq: 10, nodes: [R, node], investigation: { ...base.investigation, state } });

    async function showTrail(s: Snapshot, node: GraphNode, live: boolean) {
      mockApi({ [`GET /api/investigations/${ID}/nodes/D2b`]: { ...open(), node } });
      render(<Inspector investigationId={ID} s={s} events={[]} nodeId="D2b" live={live} />);
      fireEvent.click(screen.getByRole("tab", { name: "Trail" }));
      await screen.findByText(/3 claims/);
    }
    const expectNotLive = () => {
      expect(document.querySelector(".trail__step--open")).toBeNull();
      expect(document.querySelector(".trail__live")).toBeNull();
      expect(screen.queryByText("Live. This text is not stored.")).toBeNull();
    };

    it("paused node with an open step", async () => {
      const node = { ...D, status: "Paused" as const };
      await showTrail(snapWith(node, "Running"), node, true);
      expectNotLive();
    });

    it("paused investigation", async () => {
      await showTrail(snapWith(D, "Paused"), D, true);
      expectNotLive();
    });

    it("stream not open", async () => {
      await showTrail(snapWith(D, "Running"), D, false);
      expectNotLive();
    });

    it("running node with an open stream is live", async () => {
      await showTrail(snapWith(D, "Running"), D, true);
      expect(document.querySelector(".trail__step--open")).not.toBeNull();
    });

    // Trail verbs and the header pill: `live` only on running or waiting work.
    const noLive = () => {
      expect(document.querySelector(".trail [class*='live'], .inspector__head [class*='live']")).toBeNull();
      expect(document.querySelector(".inspector__head .ng-pulse")).toBeNull();
    };

    it("a Superseded node still marked Running: no live verb, no live pill", async () => {
      const node = { ...D, inclusion: "Superseded" as const };
      await showTrail(snapWith(node, "Running"), node, true);
      noLive();
    });

    it("a node-level Paused node: no live verb, no live pill", async () => {
      const node = { ...D, status: "Paused" as const };
      await showTrail(snapWith(node, "Running"), node, true);
      noLive();
    });

    it("a Completed investigation: no live verb, no live pill", async () => {
      const node = { ...D, status: "Completed" as const };
      await showTrail(snapWith(node, "Completed"), node, true);
      noLive();
    });

    it("a running node: live verbs and a pulsing live pill", async () => {
      await showTrail(snapWith(D, "Running"), D, true);
      expect(document.querySelector(".trail .trail__verb.ng-live")).not.toBeNull();
      expect(document.querySelector(".inspector__head .ng-pill--live .ng-pulse")).not.toBeNull();
    });

    it("Trail with live false shows no live text even with model text", () => {
      render(<Trail detail={open()} modelText={mt} onOpenPage={() => {}} live={false} running />);
      expectNotLive();
      expect(screen.queryByText(/streamed words/)).toBeNull();
    });
  });

  it("a Completed node's trail verbs carry no ng-live", () => {
    const done = nodeDetail({ ...D, status: "Completed" }, {
      trail: [step(1, { name: "plan", activity: "Planning" }), step(2), step(3, { activity: "Retrying", retry: { n: 2, m: 3 }, route: "browser" })],
    });
    render(<Trail detail={done} modelText={null} onOpenPage={() => {}} live={false} running={false} />);
    expect(document.querySelectorAll(".trail .ng-live")).toHaveLength(0);
    expect(stepWells()).toHaveLength(3);
  });

  it("a halted node's trail (investigation Paused or Stopped) carries no ng-live", () => {
    const halted = nodeDetail({ ...D, status: "Running" }, {
      trail: [step(1, { name: "plan", activity: "Planning" }), step(2, { ended_at: null })],
    });
    render(<Trail detail={halted} modelText={null} onOpenPage={() => {}} live={false} running={false} />);
    expect(document.querySelector(".trail [class*='live']")).toBeNull();
    expect(stepWells()).toHaveLength(2);
  });

  it("an empty trail says so", () => {
    render(<Trail detail={nodeDetail(D)} modelText={null} onOpenPage={() => {}} live running />);
    expect(screen.getByText("No steps recorded yet.")).toBeInTheDocument();
  });
});

describe("PageSheet", () => {
  const PAGE = `/api/investigations/${ID}/pages/pv1`;

  it('page sheet renders "<script>alert(1)</script>" as text and creates no script or img element', async () => {
    const text = 'Before\n<script>alert(1)</script>\n<img src=x onerror="alert(2)">\n<a href="https://evil.example">link</a>\nAfter';
    mockApi({ [`GET ${PAGE}`]: { url: "https://nasa.gov/vision/great_wall.html", title: "Great <i>Wall</i>", fetched_at: "2026-11-13T10:01:30Z", text } });
    const alert = vi.fn();
    vi.stubGlobal("alert", alert);
    render(<PageSheet investigationId={ID} pageVersionId="pv1" onClose={() => {}} />);
    const sheet = await screen.findByRole("dialog", { name: "Stored page" });
    const body = await within(sheet).findByText(/<script>alert\(1\)<\/script>/);
    expect(body.tagName).toBe("PRE");
    expect(body.textContent).toBe(text);
    expect(body).toHaveTextContent('<img src=x onerror="alert(2)">');
    expect(sheet.querySelector("script")).toBeNull();
    expect(sheet.querySelector("img")).toBeNull();
    expect(sheet.querySelector("a")).toBeNull();
    expect(sheet.querySelector("i")).toBeNull();
    expect(within(sheet).getByText("Great <i>Wall</i>")).toBeInTheDocument();
    expect(sheet).toHaveTextContent("https://nasa.gov/vision/great_wall.html");
    expect(alert).not.toHaveBeenCalled();
  });

  it("loading, then 404 and error states", async () => {
    let resolve!: (v: unknown) => void;
    mockApi({ [`GET ${PAGE}`]: () => new Promise((r) => { resolve = r; }) });
    const { unmount } = render(<PageSheet investigationId={ID} pageVersionId="pv1" onClose={() => {}} />);
    expect(screen.getByRole("dialog")).toHaveTextContent("LoadingStored page");
    await act(async () => resolve(new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 })));
    expect(await screen.findByText("This stored page is not available.")).toBeInTheDocument();
    unmount();

    mockApi({ [`GET ${PAGE}`]: () => new Response("{}", { status: 500 }) });
    render(<PageSheet investigationId={ID} pageVersionId="pv1" onClose={() => {}} />);
    expect(await screen.findByText("Netgrip cannot reach its service.")).toBeInTheDocument();
  });

  it("opens from the trail over the inspector; Escape and Close dismiss it and focus returns", async () => {
    const R = graphNode({ id: "R", display_id: "R", kind: "Synthesis", status: "Waiting on children" });
    const detail: NodeDetail = nodeDetail(D, { trail: [step(1, { route: "simple", page_version_id: "pv1" })] });
    mockApi({
      [`GET /api/investigations/${ID}/nodes/D2b`]: detail,
      [`GET ${PAGE}`]: { url: "https://nasa.gov/x", title: null, fetched_at: "2026-11-13T10:01:30Z", text: "Page body" },
    });
    const base = emptySnapshot(ID);
    const s: Snapshot = { ...base, seq: 10, nodes: [R, D] as GraphNode[], investigation: { ...base.investigation, state: "Running" } };
    render(<Inspector investigationId={ID} s={s} events={[]} nodeId="D2b" />);
    fireEvent.click(screen.getByRole("tab", { name: "Trail" }));
    const opener = await screen.findByRole("button", { name: "stored page" });
    opener.focus();
    fireEvent.click(opener);
    await screen.findByText("Page body");
    const close = screen.getByRole("button", { name: "Close stored page" });
    expect(close).toHaveFocus();
    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "stored page" })).toHaveFocus();

    fireEvent.click(screen.getByRole("button", { name: "stored page" }));
    fireEvent.click(await screen.findByRole("button", { name: "Close stored page" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: "stored page" })).toHaveFocus();
  });
});
