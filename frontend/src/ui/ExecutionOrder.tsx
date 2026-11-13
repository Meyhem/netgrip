import { useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { DurableEvent, GraphNode, Snapshot } from "../api/types";
import { lastByNode, sections, type NotRunningRow } from "../state/derive";
import { elapsed, timeOfDay } from "../lib/format";
import { ActivityLine } from "./ActivityLine";
import { cx } from "./cx";

export interface ExecutionOrderProps {
  s: Snapshot;
  /** The store's accumulated durable events, oldest first. */
  events: DurableEvent[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** False while the stream is disconnected: running glyphs stop pulsing. */
  live?: boolean;
}

type Section = "now" | "next" | "done" | "not-running";

interface Row {
  id: string;
  section: Section;
  n: ReactNode;
  q: string;
  side: string;
  meta: ReactNode;
  off?: boolean;
}

const NOT_RUNNING_GLYPH = { Ignored: "⦸", Superseded: "↺", Rejected: "⊘", Paused: "‖" } as const;

/** The current time, ticking each second while `active`. */
function useNow(active: boolean): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return;
    setNow(Date.now());
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

function verdictOf(node: GraphNode): { text: string | null; confidence: string | null } {
  const v = node.verdict as { text?: unknown; confidence?: unknown } | null;
  if (!v || typeof v !== "object") return { text: null, confidence: null };
  return {
    text: typeof v.text === "string" ? v.text : null,
    confidence: typeof v.confidence === "string" ? v.confidence : null,
  };
}

/** Who excluded a node, from its latest excluding event; the bare word when it is not known. */
function whyText(row: NotRunningRow, s: Snapshot, inclusion: Map<string, DurableEvent>, rejected: Map<string, DurableEvent>): string {
  const display = (id: string | null | undefined) => (id ? s.nodes.find((n) => n.id === id)?.display_id ?? null : null);
  if (row.why === "Ignored" || row.why === "Superseded") {
    // The node row carries who excluded it; the event covers snapshots from before that.
    const ev = inclusion.get(row.node.id);
    const fromEvent = ev && ev.data.inclusion === row.why ? ev : null;
    const by = row.node.excluded_by ?? (fromEvent?.data.by as string | undefined);
    const at = row.node.excluded_at ?? fromEvent?.at;
    const instructionId = row.node.excluded_instruction_id ?? (fromEvent?.data.instruction_id as string | null | undefined);
    if (!by) return row.why;
    if (by === "user") return at ? `${row.why} by you · ${timeOfDay(at)}` : `${row.why} by you`;
    const instruction = s.instructions.find((i) => i.id === instructionId);
    if (instruction) {
      const on = display(instruction.node_id);
      return on ? `${row.why} by your instruction on ${on}` : `${row.why} by your instruction`;
    }
    return `${row.why} by a re-plan`;
  }
  if (row.why === "Rejected") {
    const reason = row.node.rejection_reason ?? rejected.get(row.node.id)?.data.reason;
    return typeof reason === "string" && reason ? `Rejected: ${reason}` : "Rejected";
  }
  return "Paused";
}

/** ExecutionOrder: the board's left pane. The same nodes as the graph, by time: Now, Next,
 * Done, Not running, always in that order. */
export function ExecutionOrder({ s, events, selectedId, onSelect, live = true }: ExecutionOrderProps) {
  const paused = s.investigation.state === "Paused";
  const derived = useMemo(() => sections(s, events), [s, events]);
  const now = derived.now;
  const clockNow = useNow(now.length > 0);

  const rows = useMemo(() => {
    const started = lastByNode(events, ["node.started"]);
    const activity = lastByNode(events, ["node.activity"]);
    const failed = lastByNode(events, ["node.failed"]);
    const inclusion = lastByNode(events, ["node.inclusion_changed"]);
    const rejected = lastByNode(events, ["node.rejected"]);
    const display = (id: string | null) => (id ? s.nodes.find((n) => n.id === id)?.display_id ?? null : null);
    const title = (n: GraphNode) => `${n.display_id} ${n.question}`;

    const nowRows: Row[] = now.map(({ node }) => {
      const act = activity.get(node.id)?.data ?? {};
      const retry = act.retry as { n: number; m: number } | null | undefined;
      const retrying = node.activity === "Retrying";
      const at = started.get(node.id)?.at;
      return {
        id: node.id, section: "now", q: title(node),
        n: retrying
          ? <span className="ng-warn">●</span>
          : <span className={cx("ng-live", live && "ng-pulse")}>●</span>,
        side: at ? elapsed((clockNow - Date.parse(at)) / 1000) : "",
        meta: node.activity ? <ActivityLine activity={node.activity} detail={typeof act.detail === "string" ? act.detail : ""} retry={retry ?? null} /> : null,
      };
    });

    const nextRows: Row[] = derived.next.map(({ node, position, waitText }) => {
      // A node still Running while the investigation is paused shows the Paused glyph.
      const glyph = node.status === "Proposed" ? "◌" : node.status === "Waiting on children" ? "◔" : node.status === "Running" ? "‖" : "○";
      const by = node.status === "Proposed" ? display(node.proposed_by) : null;
      const words = [by && `proposed by ${by}`, waitText].filter(Boolean).join(" · ");
      return { id: node.id, section: "next", n: String(position), q: title(node), side: "", meta: words ? `${glyph} ${words}` : glyph };
    });

    const doneRows: Row[] = derived.done.map(({ node, finishedAt, refutedPremise }) => {
      const { text, confidence } = verdictOf(node);
      const cross = node.status === "Failed" || refutedPremise;
      let meta: string;
      if (node.status === "Failed") {
        const reason = node.failure_reason ?? failed.get(node.id)?.data.reason;
        meta = typeof reason === "string" && reason ? reason : "Failed";
      } else {
        const lead = refutedPremise ? "Premise refuted" : text;
        meta = [lead, confidence].filter(Boolean).join(" · ");
      }
      return {
        id: node.id, section: "done", q: title(node),
        n: cross ? <span className="ng-danger">✕</span> : <span className="ng-ok">✓</span>,
        side: finishedAt ? timeOfDay(finishedAt) : "", meta,
      };
    });

    const offRows: Row[] = derived.notRunning.map((row) => ({
      id: row.node.id, section: "not-running", q: title(row.node), off: true,
      n: NOT_RUNNING_GLYPH[row.why], side: "", meta: whyText(row, s, inclusion, rejected),
    }));

    return { now: nowRows, next: nextRows, done: doneRows, off: offRows };
  }, [s, events, derived, now, live, clockNow]);

  const order = useMemo(() => [...rows.now, ...rows.next, ...rows.done, ...rows.off].map((r) => r.id), [rows]);
  const pane = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!selectedId) return;
    const el = [...(pane.current?.querySelectorAll<HTMLElement>(".ng-qrow") ?? [])].find((r) => r.dataset.nodeId === selectedId);
    el?.scrollIntoView?.({ block: "nearest" });
  }, [selectedId]);

  const onKeyDown = (e: KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    if (order.length === 0) return;
    const at = selectedId ? order.indexOf(selectedId) : -1;
    const to = at === -1
      ? (e.key === "ArrowDown" ? 0 : order.length - 1)
      : at + (e.key === "ArrowDown" ? 1 : -1);
    if (to >= 0 && to < order.length && to !== at) onSelect(order[to]);
  };

  const renderRows = (list: Row[]) =>
    list.map((r) => (
      <div
        key={r.id}
        className={cx("ng-qrow", r.off && "is-off", r.id === selectedId && "is-selected")}
        role="option"
        aria-selected={r.id === selectedId}
        data-node-id={r.id}
        data-section={r.section}
        onClick={() => onSelect(r.id)}
      >
        <span className="ng-qrow__n">{r.n}</span>
        <span className="ng-qrow__q">{r.q}</span>
        <span className="ng-qrow__side">{r.side}</span>
        <span className="ng-qrow__meta">{r.meta}</span>
      </div>
    ));

  return (
    <div
      ref={pane}
      className="ng-pane__scroll"
      role="listbox"
      aria-label="Execution order"
      tabIndex={0}
      onKeyDown={onKeyDown}
    >
      <div className="ng-queue__head">
        <span className={cx("ng-label", rows.now.length > 0 && "ng-live")}>Now</span>
        <span className="ng-queue__count">{paused ? "Nothing runs while paused" : `${rows.now.length} running · ${s.schedule.slots} slots`}</span>
      </div>
      {renderRows(rows.now)}
      <div className="ng-queue__head">
        <span className="ng-label">Next</span>
        <span className="ng-queue__count">{`${rows.next.length} in order`}</span>
      </div>
      {rows.next.length ? renderRows(rows.next) : <div className="ng-pad ng-small ng-muted">Nothing queued. The orchestrator is deciding.</div>}
      <div className="ng-queue__head">
        <span className="ng-label ng-ok">Done</span>
        <span className="ng-queue__count">{`${rows.done.length} · newest first`}</span>
      </div>
      {renderRows(rows.done)}
      <div className="ng-queue__head">
        <span className="ng-label">Not running</span>
        <span className="ng-queue__count">{String(rows.off.length)}</span>
      </div>
      {renderRows(rows.off)}
    </div>
  );
}
