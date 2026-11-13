import { useLayoutEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import type { DurableEvent, GraphNode } from "../api/types";
import { eventText, type EventText } from "../lib/eventText";
import { timeOfDaySeconds } from "../lib/format";
import type { Gap, ModelText } from "../state/investigationStore";
import type { OlderState } from "../state/olderEvents";
import { Button } from "./Button";
import { cx } from "./cx";
import { seqLabel } from "./GraphToolbar";

export interface EventLogProps {
  /** Durable events, oldest first (the store's accumulated list). */
  events: DurableEvent[];
  nodes: GraphNode[];
  /** The last applied sequence number: "current to" and the seq. */
  seq: number;
  /** Streamed model text now being written: rows with sequence "live". */
  ephemeral: ModelText[];
  gaps?: Gap[];
  selectedId: string | null;
  onSelect: (nodeId: string) => void;
  collapsed: boolean;
  onToggle: () => void;
  /** Called when scrolling reaches the oldest row, while `older` is "more". */
  onReachEnd?: () => void;
  older?: OlderState;
}

type Filter = "all" | "you" | "orc" | "selected" | "claims" | "problems";

interface Row { ev: DurableEvent; t: EventText }

const nodeOf = (ev: DurableEvent): string | null => {
  if (ev.node_id) return ev.node_id;
  const ids = ev.data?.node_ids ?? ev.data?.reset_node_ids;
  if (Array.isArray(ids) && typeof ids[0] === "string") return ids[0];
  return typeof ev.data?.node_id === "string" ? ev.data.node_id : null;
};

const touches = (ev: DurableEvent, id: string) =>
  ev.node_id === id || (Array.isArray(ev.data?.node_ids) && ev.data.node_ids.includes(id)) || ev.data?.node_id === id;

const PROBLEM_TYPES = new Set(["node.failed", "plan.failed", "node.left_failed", "page.unobtainable"]);
const isProblem = ({ ev, t }: Row) =>
  t.actorClass === "sys" || PROBLEM_TYPES.has(ev.type) || (ev.type === "node.activity" && ev.data?.activity === "Retrying");

const FILTERS: { key: Filter; label: string; steer?: boolean }[] = [
  { key: "all", label: "All" },
  { key: "you", label: "You", steer: true },
  { key: "orc", label: "Orchestrator" },
  { key: "selected", label: "Selected node" },
  { key: "claims", label: "Claims" },
  { key: "problems", label: "Problems" },
];

const ACTOR_CLASS = { you: "ng-log__row--you", orc: "ng-log__row--orc", sys: "ng-log__row--sys", "": "" } as const;

/** How much streamed text a live row keeps: the newest part, the rest is ellipsised. */
const LIVE_TAIL = 240;

/** EventLog: the investigation's recorded history, newest first, docked under the graph. */
export function EventLog({
  events, nodes, seq, ephemeral, gaps = [], selectedId, onSelect, collapsed, onToggle, onReachEnd, older = "done",
}: EventLogProps) {
  const [filter, setFilter] = useState<Filter>("all");
  const [follow, setFollow] = useState(true);
  const logRef = useRef<HTMLDivElement>(null);

  const all = useMemo(() => {
    const rows: Row[] = [];
    for (let i = events.length - 1; i >= 0; i--) {
      const t = eventText(events[i], nodes);
      if (t) rows.push({ ev: events[i], t });
    }
    return rows;
  }, [events, nodes]);

  const match: Record<Filter, (r: Row) => boolean> = {
    all: () => true,
    you: (r) => r.t.actorClass === "you",
    orc: (r) => r.t.actorClass === "orc",
    selected: (r) => selectedId !== null && touches(r.ev, selectedId),
    claims: (r) => r.ev.type.startsWith("claim."),
    problems: isProblem,
  };
  const shown = filter === "all" ? all : all.filter(match[filter]);
  const liveShown = ephemeral.filter((m) => filter === "all" || (filter === "selected" && m.node_id === selectedId));

  // Follow keeps the newest row (the top) in view.
  useLayoutEffect(() => {
    if (follow && logRef.current) logRef.current.scrollTop = 0;
  }, [follow, shown, liveShown.length, collapsed]);

  // Rows that do not fill the log (a filter, a short page) cannot be scrolled to the end:
  // ask for older rows until they do, or until there are none.
  useLayoutEffect(() => {
    const el = logRef.current;
    if (!el || collapsed || older !== "more" || !onReachEnd) return;
    if (el.clientHeight > 0 && el.scrollHeight <= el.clientHeight + 24) onReachEnd();
  }, [older, shown, collapsed, onReachEnd]);

  const onScroll = () => {
    const el = logRef.current;
    if (!el) return;
    if (el.scrollTop > 0 && follow) setFollow(false);
    if (older === "more" && onReachEnd && el.scrollHeight > 0 && el.scrollTop + el.clientHeight >= el.scrollHeight - 24) onReachEnd();
  };

  const byId = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);
  const items: ReactNode[] = liveShown.map((m) => (
    <div key={`live-${m.node_id}`} className="ng-log__row ng-log__row--eph" data-node-id={m.node_id} onClick={() => onSelect(m.node_id)}>
      <span className="ng-log__t">{timeOfDaySeconds(m.at)}</span>
      <span className="ng-log__seq">live</span>
      <span className="ng-log__who">{byId.get(m.node_id)?.display_id ?? "a node"}</span>
      <span>…{m.text.slice(-LIVE_TAIL)}</span>
    </div>
  ));
  const pending = [...gaps].sort((a, b) => b.afterSeq - a.afterSeq);
  const gapRow = (g: Gap) => (
    <div key={`gap-${g.afterSeq}`} className="ng-log__gap">{g.count} events while this tab was closed</div>
  );
  let above = false;
  for (const r of shown) {
    while (pending.length && pending[0].afterSeq >= r.ev.seq) {
      const g = pending.shift()!;
      if (above) items.push(gapRow(g));
    }
    const node = nodeOf(r.ev);
    items.push(
      <div key={r.ev.seq} className={cx("ng-log__row", ACTOR_CLASS[r.t.actorClass])} data-seq={r.ev.seq}
        onClick={node ? () => onSelect(node) : undefined}>
        <span className="ng-log__t">{timeOfDaySeconds(r.ev.at)}</span>
        <span className="ng-log__seq">{seqLabel(r.ev.seq)}</span>
        <span className="ng-log__who">{r.t.who}</span>
        <span title={r.t.text}>{r.t.text}</span>
      </div>,
    );
    above = true;
  }
  // Gaps older than every row loaded so far sit at the end until older rows arrive.
  if (above) for (const g of pending) if (shown.length && g.afterSeq < shown[0].ev.seq) items.push(gapRow(g));

  const count = (f: Filter) => (f === "all" ? 0 : all.filter(match[f]).length);
  const pick = (f: Filter) => setFilter(f);
  const onTagKey = (f: Filter) => (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(f); }
  };

  return (
    <div className="board-log" data-older={older}>
      <div className="ng-panel__head">
        <span className="ng-label">Event log</span>
        <div className="ng-row ng-row--tight" role="group" aria-label="Filter the log">
          {FILTERS.map(({ key, label, steer }) => {
            const n = count(key);
            const on = filter === key;
            return (
              <span key={key} role="button" tabIndex={0} aria-pressed={on}
                className={cx("ng-tag", on ? "ng-tag--solid" : steer && "ng-tag--steer")}
                onClick={() => pick(key)} onKeyDown={onTagKey(key)}>
                {n > 0 ? `${label} ${n}` : label}
              </span>
            );
          })}
        </div>
        <span className="ng-right ng-mono ng-faint">current to {seqLabel(seq)}</span>
        <Button variant="quiet" size="sm" aria-pressed={follow} onClick={() => setFollow(true)}>
          {follow ? "Follow ●" : "Follow"}
        </Button>
        <Button variant="quiet" size="sm" aria-label={collapsed ? "Expand log" : "Collapse log"} aria-expanded={!collapsed} onClick={onToggle}>
          {collapsed ? "▸" : "▾"}
        </Button>
      </div>
      {!collapsed && (
        <div className="ng-log" ref={logRef} onScroll={onScroll} role="log" aria-label="Event log">
          {items}
        </div>
      )}
    </div>
  );
}
