import { useEffect, useState, type ReactNode } from "react";
import { liveModelText, useInvestigation } from "../state/investigationStore";
import { useOlderEvents } from "../state/olderEvents";
import { useSelection } from "../state/selection";
import { Banner } from "../ui/Banner";
import { BoardGraph } from "../ui/BoardGraph";
import { BoardHeader } from "../ui/BoardHeader";
import { EventLog } from "../ui/EventLog";
import { ExecutionOrder } from "../ui/ExecutionOrder";
import { Inspector } from "../ui/Inspector";
import { cx } from "../ui/cx";
import { Page } from "./InvestigationRoute";

/** The board's regions (ScreenControlBoard README). Each slot is one region; later tasks fill
 * them: ExecutionOrder (left), GraphCanvas with its toolbar (centre), EventLog (dock),
 * the inspector (right), and a SystemPause banner between the header and the panes. */
export interface BoardSlots {
  header: ReactNode;
  /** SystemPause, when present: pushes the panes down. */
  banner?: ReactNode;
  executionOrder: ReactNode;
  /** The centre's 40px toolbar row and the canvas, as GraphCanvas renders them. */
  graph: ReactNode;
  eventLog: ReactNode;
  inspector: ReactNode;
}

export function BoardLayout({ header, banner, executionOrder, graph, eventLog, inspector }: BoardSlots) {
  return (
    <div className={cx("ng-board", "control-board", banner != null && "control-board--banner")}>
      {header}
      {banner}
      <div className="ng-board__body">
        <aside className="ng-pane ng-pane--left" data-slot="execution-order" aria-label="Execution order">{executionOrder}</aside>
        <div className="ng-center" data-slot="center">
          {graph}
          <div className="ng-dock" data-slot="event-log">{eventLog}</div>
        </div>
        <aside className="ng-pane ng-pane--right" data-slot="inspector" aria-label="Inspector">{inspector}</aside>
      </div>
    </div>
  );
}

/** ScreenControlBoard: one investigation, three panes over one store and one selection. Opens
 * from the snapshot and follows the stream (useInvestigation). Read-only in Phase 5. */
export function ControlBoard({ id }: { id: string }) {
  const state = useInvestigation(id);
  const { snapshot, status, error, events, gaps } = state;
  const { selectedId, select } = useSelection(id);
  const { older, loadOlder } = useOlderEvents(id, events, snapshot?.seq ?? 0);
  const [logCollapsed, setLogCollapsed] = useState(false);
  // `L` toggles the log (ScreenControlBoard keyboard).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== "l" || e.metaKey || e.ctrlKey || e.altKey) return;
      if ((e.target as HTMLElement | null)?.closest?.("input, textarea, select, [contenteditable]")) return;
      e.preventDefault();
      setLogCollapsed((c) => !c);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  if (!snapshot) {
    return error ? <Page><Banner tone="warn" title="Netgrip cannot reach its service.">Reload to try again. Nothing is lost.</Banner></Page> : null;
  }
  const root = snapshot.nodes.find((n) => n.parent_id === null) ?? null;
  // Nothing selected: the inspector shows the root.
  const inspected = selectedId ?? root?.id ?? null;
  return (
    <BoardLayout
      header={<BoardHeader s={snapshot} status={status} runControls={null /* Phase 6: RunControls */} />}
      executionOrder={<ExecutionOrder s={snapshot} events={events} selectedId={selectedId} onSelect={select} live={status === "open"} />}
      graph={<BoardGraph s={snapshot} events={events} selectedId={selectedId} onSelect={select} live={status === "open"} />}
      eventLog={
        <EventLog events={events} nodes={snapshot.nodes} seq={snapshot.seq} ephemeral={liveModelText(state)} gaps={gaps}
          selectedId={selectedId} onSelect={select} collapsed={logCollapsed} onToggle={() => setLogCollapsed((c) => !c)}
          onReachEnd={loadOlder} older={older} />
      }
      inspector={
        <Inspector investigationId={id} s={snapshot} events={events} nodeId={inspected} live={status === "open"}
          nodeActions={null /* Phase 6: NodeActions */} composer={null /* Phase 6: InstructionComposer */} />
      }
    />
  );
}
