import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { getJSON } from "../api/client";
import type { InvestigationState, Snapshot } from "../api/types";
import { liveModelText, useInvestigation } from "../state/investigationStore";
import { useOlderEvents } from "../state/olderEvents";
import { useSelection } from "../state/selection";
import { Banner } from "../ui/Banner";
import { BoardGraph } from "../ui/BoardGraph";
import { BoardHeader } from "../ui/BoardHeader";
import { Button } from "../ui/Button";
import { EventLog } from "../ui/EventLog";
import { ExecutionOrder } from "../ui/ExecutionOrder";
import { Inspector } from "../ui/Inspector";
import { cx } from "../ui/cx";
import { Page } from "./InvestigationRoute";

/** Below 900px the left pane, the graph and the log are tabs (ScreenControlBoard, narrow widths). */
export type BoardTab = "order" | "graph" | "log";
const BOARD_TABS: [BoardTab, string][] = [["order", "Execution order"], ["graph", "Graph"], ["log", "Log"]];

/** The board's regions (ScreenControlBoard README). Each slot is one region: ExecutionOrder
 * (left), GraphCanvas with its toolbar (centre), EventLog (dock), the inspector (right), and a
 * SystemPause banner between the header and the panes.
 *
 * Narrow widths are CSS (app.css) over two pieces of state kept here: below 1180px the
 * inspector is an overlay sheet over the graph, shown while `sheetOpen`; below 900px the tab
 * bar shows and only the `tab` region is visible. Wider, both are ignored. */
export interface BoardSlots {
  header: ReactNode;
  /** SystemPause, when present: pushes the panes down. */
  banner?: ReactNode;
  executionOrder: ReactNode;
  /** The centre's 40px toolbar row and the canvas, as GraphCanvas renders them. */
  graph: ReactNode;
  eventLog: ReactNode;
  inspector: ReactNode;
  sheetOpen?: boolean;
  onCloseSheet?: () => void;
  tab?: BoardTab;
  onTab?: (tab: BoardTab) => void;
}

export function BoardLayout({ header, banner, executionOrder, graph, eventLog, inspector, sheetOpen = false, onCloseSheet, tab = "graph", onTab }: BoardSlots) {
  return (
    <div className={cx("ng-board", "control-board", banner != null && "control-board--banner", sheetOpen && "control-board--sheet-open", `control-board--tab-${tab}`)}>
      {header}
      {banner}
      <div className="ng-board__body">
        <div className="ng-tabs board-tabs" role="tablist" aria-label="Board">
          {BOARD_TABS.map(([key, label]) => (
            <button key={key} type="button" role="tab" aria-selected={tab === key} className={cx("ng-tab", tab === key && "is-on")} onClick={() => onTab?.(key)}>
              {label}
            </button>
          ))}
        </div>
        <aside className="ng-pane ng-pane--left" data-slot="execution-order" aria-label="Execution order">{executionOrder}</aside>
        <div className="ng-center" data-slot="center">
          {graph}
          <div className="ng-dock" data-slot="event-log">{eventLog}</div>
        </div>
        <aside className="ng-pane ng-pane--right" data-slot="inspector" aria-label="Inspector">
          <div className="ng-panel__head board-sheet__bar">
            <span className="ng-label">Inspector</span>
            <Button variant="quiet" size="sm" className="ng-right" aria-label="Close inspector" onClick={onCloseSheet}>✕</Button>
          </div>
          {inspector}
        </aside>
      </div>
    </div>
  );
}

/** Opening a board (screens.md): header and empty panes, "Loading the investigation" as an
 * ActivityLine, no shimmer. */
function LoadingBoard() {
  return (
    <BoardLayout
      header={
        <div className="ng-board__head">
          <Link to="/" className="ng-btn ng-btn--sm ng-btn--quiet" aria-label="Back to investigations">←</Link>
          <div className="ng-activity">
            <span className="ng-activity__verb">Loading</span>{" "}
            <span className="ng-activity__what">the investigation</span>
          </div>
        </div>
      }
      executionOrder={null}
      graph={<><div className="ng-toolbar" /><div className="ng-canvas" /></>}
      eventLog={null}
      inspector={null}
    />
  );
}

/** Synthesising: the left pane says what the report is written from. The count is read from
 * the snapshot endpoint when synthesis starts (the reducer does not keep it). */
function useSynthesisClaims(id: string, state: InvestigationState | undefined): number | null {
  const [n, setN] = useState<number | null>(null);
  useEffect(() => {
    if (state !== "Synthesising") return;
    let live = true;
    getJSON<Snapshot>(`/api/investigations/${encodeURIComponent(id)}`)
      .then((s) => { if (live && typeof s.synthesis_claims === "number") setN(s.synthesis_claims); })
      .catch(() => {});
    return () => { live = false; };
  }, [id, state]);
  return n;
}

function Synthesising({ claims }: { claims: number | null }) {
  const what = claims == null ? "the report" : `the report from ${claims} ${claims === 1 ? "claim" : "claims"}`;
  return (
    <div className="ng-pane__scroll">
      <div className="ng-pad">
        <div className="ng-activity">
          <span className="ng-activity__verb">Writing</span>{" "}
          <span className="ng-activity__what">{what}</span>
        </div>
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
  const [sheetOpen, setSheetOpen] = useState(false);
  const [tab, setTab] = useState<BoardTab>("graph");
  const synthesisClaims = useSynthesisClaims(id, snapshot?.investigation.state);
  // Selecting a node from any pane opens the inspector sheet (narrow widths), even when the
  // node was already selected.
  const pick = useCallback((nodeId: string | null) => {
    select(nodeId);
    if (nodeId) setSheetOpen(true);
  }, [select]);
  // `L` toggles the log; Escape closes the inspector sheet (ScreenControlBoard keyboard).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if ((e.target as HTMLElement | null)?.closest?.("input, textarea, select, [contenteditable]")) return;
      if (e.key === "Escape") {
        // A dialog (stored page, delete) takes Escape first.
        if (document.querySelector('[role="dialog"]')) return;
        setSheetOpen(false);
        return;
      }
      if (e.key.toLowerCase() !== "l") return;
      e.preventDefault();
      setLogCollapsed((c) => !c);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  if (!snapshot) {
    return error ? <Page><Banner tone="warn" title="Netgrip cannot reach its service.">Reload to try again. Nothing is lost.</Banner></Page> : <LoadingBoard />;
  }
  const root = snapshot.nodes.find((n) => n.parent_id === null) ?? null;
  // Nothing selected: the inspector shows the root.
  const inspected = selectedId ?? root?.id ?? null;
  const synthesising = snapshot.investigation.state === "Synthesising";
  return (
    <BoardLayout
      sheetOpen={sheetOpen}
      onCloseSheet={() => setSheetOpen(false)}
      tab={tab}
      onTab={setTab}
      header={<BoardHeader s={snapshot} status={status} runControls={null /* Phase 6: RunControls */} />}
      executionOrder={
        synthesising
          ? <Synthesising claims={synthesisClaims} />
          : <ExecutionOrder s={snapshot} events={events} selectedId={selectedId} onSelect={pick} live={status === "open"} />
      }
      graph={<BoardGraph s={snapshot} events={events} selectedId={selectedId} onSelect={pick} live={status === "open"} />}
      eventLog={
        <EventLog events={events} nodes={snapshot.nodes} seq={snapshot.seq} ephemeral={liveModelText(state)} gaps={gaps}
          selectedId={selectedId} onSelect={pick} collapsed={logCollapsed} onToggle={() => setLogCollapsed((c) => !c)}
          onReachEnd={loadOlder} older={older} />
      }
      inspector={
        <Inspector investigationId={id} s={snapshot} events={events} nodeId={inspected} live={status === "open"}
          nodeActions={null /* Phase 6: NodeActions */} composer={null /* Phase 6: InstructionComposer */} />
      }
    />
  );
}
