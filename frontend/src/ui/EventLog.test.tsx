import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { DurableEvent } from "../api/types";
import type { ModelText } from "../state/investigationStore";
import { graphNode } from "../test/fixtures";
import { EventLog, type EventLogProps } from "./EventLog";
import { seqLabel } from "./GraphToolbar";

const nodes = [
  graphNode({ id: "n2", display_id: "D2" }),
  graphNode({ id: "n2b", display_id: "D2b", parent_id: "n2" }),
];

function ev(seq: number, type: string, actor: DurableEvent["actor"], node_id: string | null, data: Record<string, unknown> = {}): DurableEvent {
  return { seq, investigation_id: "inv", type, v: 1, at: `2026-11-13T14:02:${String(seq).padStart(2, "0")}Z`, actor, node_id, command_id: null, data };
}

const EVENTS: DurableEvent[] = [
  ev(1, "instruction.queued", "user", "n2", { instruction_id: "i", text: "Only first-hand.", waiting_for: "replan" }),
  ev(2, "node.approved", "orchestrator", "n2b", { budget: { sources: 8, child_nodes: 0 } }),
  ev(3, "schedule.updated", "orchestrator", null, { order: [], reasons: {}, slots: 2 }),
  ev(4, "claim.added", "node", "n2b", { claim_id: "c", text: "Chiao photographed it", status: "Supported", supporting: [], contradicting: [] }),
  ev(5, "page.unobtainable", "node", "n2b", { url: "xinhuanet.com/a", attempts: [{}, {}, {}] }),
  ev(6, "node.inclusion_changed", "user", "n2", { node_ids: ["n2"], inclusion: "Ignored", by: "user", instruction_id: null }),
];

function show(over: Partial<EventLogProps> = {}) {
  const props: EventLogProps = {
    events: EVENTS, nodes, seq: 6, ephemeral: [], selectedId: null, onSelect: vi.fn(), collapsed: false, onToggle: vi.fn(), ...over,
  };
  const r = render(<EventLog {...props} />);
  return { ...r, props };
}

const rows = () => [...document.querySelectorAll(".ng-log__row")];
const seqs = () => rows().map((r) => Number(r.querySelector(".ng-log__seq")!.textContent!.slice(1)));
const bySeqRow = (n: number) => rows().find((r) => r.getAttribute("data-seq") === String(n))!;
const tag = (name: RegExp) => screen.getByRole("button", { name });

describe("EventLog", () => {
  it("renders newest first with time, sequence, who and what; schedule rows are left out", () => {
    show();
    expect(seqs()).toEqual([6, 5, 4, 2, 1]);
    const first = rows()[0];
    expect(first.querySelector(".ng-log__who")).toHaveTextContent("You");
    expect(first).toHaveTextContent("ignored branch D2");
    expect(first.querySelector(".ng-log__t")!.textContent).toMatch(/^\d\d:\d\d:\d\d$/);
    expect(screen.getByText(`current to ${seqLabel(6)}`)).toBeInTheDocument();
  });

  it("user rows get ng-log__row--you", () => {
    show();
    const bySeq = (n: number) => rows().find((r) => r.getAttribute("data-seq") === String(n))!;
    expect(bySeq(1)).toHaveClass("ng-log__row", "ng-log__row--you");
    expect(bySeq(6)).toHaveClass("ng-log__row--you");
    expect(bySeq(2)).toHaveClass("ng-log__row--orc");
    expect(bySeq(5)).toHaveClass("ng-log__row--sys");
    expect(bySeq(4).className).toBe("ng-log__row");
  });

  it("filters narrow rows and show counts", () => {
    show({ selectedId: "n2b" });
    expect(tag(/^All$/)).toHaveClass("ng-tag--solid");
    expect(tag(/^You 2$/)).toHaveClass("ng-tag--steer");
    expect(tag(/^Orchestrator 1$/)).toBeInTheDocument();
    expect(tag(/^Selected node 3$/)).toBeInTheDocument();
    expect(tag(/^Claims 1$/)).toBeInTheDocument();
    expect(tag(/^Problems 1$/)).toBeInTheDocument();
    fireEvent.click(tag(/^You/));
    expect(tag(/^You/)).toHaveClass("ng-tag--solid");
    expect(tag(/^All$/)).not.toHaveClass("ng-tag--solid");
    expect(seqs()).toEqual([6, 1]);
    fireEvent.click(tag(/^Selected node/));
    expect(seqs()).toEqual([5, 4, 2]);
    fireEvent.click(tag(/^Claims/));
    expect(seqs()).toEqual([4]);
    fireEvent.click(tag(/^Problems/));
    expect(seqs()).toEqual([5]);
    fireEvent.click(tag(/^All/));
    expect(seqs()).toHaveLength(5);
  });

  it("counts are left out when zero", () => {
    show({ events: EVENTS.slice(0, 1) });
    expect(tag(/^Orchestrator$/)).toBeInTheDocument();
    expect(tag(/^Problems$/)).toBeInTheDocument();
    expect(tag(/^Selected node$/)).toBeInTheDocument();
  });

  it("scrolling turns Follow off; the button turns it on", () => {
    const { rerender, props } = show();
    const follow = screen.getByRole("button", { name: /^Follow/ });
    expect(follow).toHaveAttribute("aria-pressed", "true");
    const log = document.querySelector(".ng-log") as HTMLElement;
    log.scrollTop = 80;
    fireEvent.scroll(log);
    expect(follow).toHaveAttribute("aria-pressed", "false");
    // A new row does not pull the view back while Follow is off.
    rerender(<EventLog {...props} events={[...EVENTS, ev(7, "node.started", "node", "n2b", { attempt: 1, brief: {} })]} seq={7} />);
    expect(log.scrollTop).toBe(80);
    fireEvent.click(follow);
    expect(follow).toHaveAttribute("aria-pressed", "true");
    expect(log.scrollTop).toBe(0);
    // Following: the newest row stays in view.
    log.scrollTop = 0;
    rerender(<EventLog {...props} events={[...EVENTS, ev(8, "node.started", "node", "n2b", { attempt: 1, brief: {} })]} seq={8} />);
    expect(log.scrollTop).toBe(0);
    expect(follow).toHaveAttribute("aria-pressed", "true");
  });

  it("gap row appears after a large catch-up", () => {
    show({ gaps: [{ afterSeq: 2, count: 42 }] });
    const log = document.querySelector(".ng-log")!;
    const children = [...log.children].map((c) => c.classList.contains("ng-log__gap") ? "gap" : Number(c.getAttribute("data-seq")));
    expect(children).toEqual([6, 5, 4, "gap", 2, 1]);
    expect(log.querySelector(".ng-log__gap")).toHaveTextContent("42 events while this tab was closed");
  });

  it("older rows load on reaching the end", () => {
    const onReachEnd = vi.fn();
    const { rerender, props } = show({ onReachEnd, older: "more" });
    const log = document.querySelector(".ng-log") as HTMLElement;
    Object.defineProperty(log, "scrollHeight", { configurable: true, value: 1000 });
    Object.defineProperty(log, "clientHeight", { configurable: true, value: 166 });
    log.scrollTop = 300;
    fireEvent.scroll(log);
    expect(onReachEnd).not.toHaveBeenCalled();
    log.scrollTop = 834;
    fireEvent.scroll(log);
    expect(onReachEnd).toHaveBeenCalledTimes(1);
    // Nothing more to load, or a page already on its way: no call.
    rerender(<EventLog {...props} older="loading" />);
    fireEvent.scroll(log);
    rerender(<EventLog {...props} older="done" />);
    fireEvent.scroll(log);
    expect(onReachEnd).toHaveBeenCalledTimes(1);
  });

  it("ephemeral rows vanish when the step completes", () => {
    const live: ModelText = { node_id: "n2b", step: 3, text: "the caption says the photo was taken with a 180 mm lens", at: "2026-11-13T14:02:30Z" };
    const { rerender, props } = show({ ephemeral: [live] });
    const eph = document.querySelector(".ng-log__row--eph")!;
    expect(eph.querySelector(".ng-log__seq")).toHaveTextContent("live");
    expect(eph.querySelector(".ng-log__who")).toHaveTextContent("D2b");
    expect(eph).toHaveTextContent("…the caption says the photo was taken with a 180 mm lens");
    // The step completed: the store dropped the text.
    rerender(<EventLog {...props} ephemeral={[]} />);
    expect(document.querySelector(".ng-log__row--eph")).toBeNull();
  });

  it("clicking a row selects its node", () => {
    const { props } = show();
    fireEvent.click(bySeqRow(4));
    expect(props.onSelect).toHaveBeenCalledWith("n2b");
  });

  it("collapsed shows only the head row", () => {
    const { props, rerender } = show({ collapsed: true });
    expect(document.querySelector(".ng-log")).toBeNull();
    expect(screen.getByText("Event log")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Expand log" }));
    expect(props.onToggle).toHaveBeenCalled();
    rerender(<EventLog {...props} collapsed={false} />);
    expect(screen.getByRole("button", { name: "Collapse log" })).toBeInTheDocument();
  });
});
