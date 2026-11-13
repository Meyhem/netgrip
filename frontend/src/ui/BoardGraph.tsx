import { useMemo, useState } from "react";
import type { DurableEvent, Snapshot } from "../api/types";
import { counts, lastByNode } from "../state/derive";
import { GraphCanvas } from "./GraphCanvas";
import type { ActivityDetail } from "./GraphNode";
import { DEFAULT_VIEW, GraphToggles, GraphToolbar, type GraphView } from "./GraphToolbar";

export interface BoardGraphProps {
  s: Snapshot;
  /** The store's accumulated durable events, oldest first. */
  events: DurableEvent[];
  selectedId: string | null;
  onSelect: (id: string) => void;
  /** False while the stream is not open: nothing pulses. */
  live: boolean;
}

/** The board's centre: the 40px graph toolbar and the running graph (GraphCanvas, board mode). */
export function BoardGraph({ s, events, selectedId, onSelect, live }: BoardGraphProps) {
  const [view, setView] = useState<GraphView>(DEFAULT_VIEW);
  // A Paused or Stopped investigation runs nothing, whatever its nodes' last status says.
  const running = s.investigation.state !== "Paused" && s.investigation.state !== "Stopped";
  const c = useMemo(() => counts(s), [s]);

  const activities = useMemo(() => {
    const out: Record<string, ActivityDetail> = {};
    for (const [id, ev] of lastByNode(events, ["node.activity"])) {
      out[id] = {
        detail: typeof ev.data.detail === "string" ? ev.data.detail : "",
        retry: (ev.data.retry as ActivityDetail["retry"]) ?? null,
      };
    }
    return out;
  }, [events]);

  // Follow active: the running node that started last (by its node.started event).
  const active = useMemo(() => {
    const running = s.nodes.filter((n) => n.status === "Running" && n.inclusion === "Included");
    if (!running.length) return null;
    const started = lastByNode(events, ["node.started"]);
    let best = running[running.length - 1];
    let bestSeq = started.get(best.id)?.seq ?? -1;
    for (const n of running) {
      const seq = started.get(n.id)?.seq ?? -1;
      if (seq > bestSeq) [best, bestSeq] = [n, seq];
    }
    return best.id;
  }, [s.nodes, events]);

  return (
    <GraphCanvas
      nodes={s.nodes}
      selectedId={selectedId}
      onSelect={onSelect}
      mode="board"
      live={live && running}
      running={running}
      activities={activities}
      showExcluded={view.showExcluded}
      collapseCompleted={view.collapseCompleted}
      follow={view.followActive ? active : null}
      onPan={() => setView((v) => (v.followActive ? { ...v, followActive: false } : v))}
      toolbar={<GraphToolbar counts={c} seq={s.seq} />}
      toolbarEnd={<GraphToggles view={view} onChange={setView} />}
    />
  );
}
