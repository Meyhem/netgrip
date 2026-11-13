import type { ReactNode } from "react";
import { useInvestigation } from "../state/investigationStore";
import { useSelection } from "../state/selection";
import { Banner } from "../ui/Banner";
import { BoardHeader } from "../ui/BoardHeader";
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
  const { snapshot, status, error } = useInvestigation(id);
  const { selectedId } = useSelection(id);
  if (!snapshot) {
    return error ? <Page><Banner tone="warn" title="Netgrip cannot reach its service.">Reload to try again. Nothing is lost.</Banner></Page> : null;
  }
  const root = snapshot.nodes.find((n) => n.parent_id === null) ?? null;
  // Nothing selected: the inspector shows the root.
  const inspected = selectedId ?? root?.id ?? null;
  return (
    <BoardLayout
      header={<BoardHeader s={snapshot} status={status} runControls={null /* Phase 6: RunControls */} />}
      executionOrder={<div className="ng-pane__scroll" />}
      graph={
        <>
          <div className="ng-toolbar"><span className="ng-label">Graph</span></div>
          <div className="ng-canvas" />
        </>
      }
      eventLog={null}
      inspector={<div className="ng-pane__scroll" data-node-id={inspected ?? undefined} />}
    />
  );
}
