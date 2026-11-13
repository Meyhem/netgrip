import { useCallback, useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { getJSON } from "../api/client";
import type { GraphNode, InvestigationState, Snapshot } from "../api/types";
import { useInvestigation, useLiveModelText } from "../state/investigationStore";
import { useBoardKeys } from "../lib/keys";
import { useOlderEvents } from "../state/olderEvents";
import { useCommand } from "../state/useCommand";
import { useSelection } from "../state/selection";
import { Banner } from "../ui/Banner";
import { BoardGraph } from "../ui/BoardGraph";
import { BoardHeader } from "../ui/BoardHeader";
import { Button } from "../ui/Button";
import { EventLog, type EventLogProps } from "../ui/EventLog";
import { ExecutionOrder } from "../ui/ExecutionOrder";
import { Inspector } from "../ui/Inspector";
import { Instruction } from "../ui/Instruction";
import { InstructionComposer } from "../ui/InstructionComposer";
import { descendants, instructTarget, NodeActions, RerunQuestion, useNodeActions } from "../ui/NodeActions";
import { RunControls } from "../ui/RunControls";
import { RecoveryNotice, SystemPause, useRecoveryNotice } from "../ui/SystemPause";
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

/** The event log with the live model-text rows. Only this part of the board re-renders on
 * each frame of streamed text. */
function LiveEventLog({ id, ...props }: Omit<EventLogProps, "ephemeral"> & { id: string }) {
  return <EventLog {...props} ephemeral={useLiveModelText(id)} />;
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
  const command = useCommand(id);
  // A refused command: the server's message, for 6 s (steering.md, "the life of any command").
  const { error: commandError, clearError } = command;
  useEffect(() => {
    if (!commandError) return;
    const t = setTimeout(clearError, 6000);
    return () => clearTimeout(t);
  }, [commandError, clearError]);
  // Selecting a node from any pane opens the inspector sheet (narrow widths), even when the
  // node was already selected.
  const pick = useCallback((nodeId: string | null) => {
    select(nodeId);
    if (nodeId) setSheetOpen(true);
  }, [select]);
  const [focusToken, setFocusToken] = useState(0);
  const [errorsRequest, setErrorsRequest] = useState<{ filter: "problems"; n: number } | null>(null);
  const recovery = useRecoveryNotice(id, events);
  const inspectedNode = snapshot
    ? snapshot.nodes.find((n) => n.id === (selectedId ?? snapshot.nodes.find((x) => x.parent_id === null)?.id)) ?? null
    : null;
  const actions = useNodeActions(snapshot, inspectedNode, command, () => setFocusToken((t) => t + 1));
  // The keyboard (ScreenControlBoard): one handler for the whole board. Escape clears the
  // selection and, below 1180px, closes the inspector sheet.
  useBoardKeys({
    instruct: () => actions.runKey("I"),
    deeper: () => actions.runKey("D"),
    focus: () => actions.runKey("F"),
    pause: () => actions.runKey("Space"),
    ignore: () => actions.runKey("X"),
    rerun: () => actions.runKey("R"),
    menu: () => actions.setMenu((o) => !o),
    log: () => setLogCollapsed((c) => !c),
    escape: () => { setSheetOpen(false); select(null); },
  });
  // An instruction's sequence number shows its row in the log.
  const showSeq = useCallback((seq: number) => {
    setLogCollapsed(false);
    setTimeout(() => document.querySelector(`.ng-log__row[data-seq="${seq}"]`)?.scrollIntoView?.({ block: "center" }), 0);
  }, []);
  const restore = (nid: string) => void command.send("restore_branch", { key: `restore_branch:${nid}`, nodeId: nid });
  const restoring = (nid: string) => command.isSent(`restore_branch:${nid}`);
  if (!snapshot) {
    return error ? <Page><Banner tone="warn" title="Netgrip cannot reach its service.">Reload to try again. Nothing is lost.</Banner></Page> : <LoadingBoard />;
  }
  const root = snapshot.nodes.find((n) => n.parent_id === null) ?? null;
  // Nothing selected: the inspector shows the root.
  const inspected = selectedId ?? root?.id ?? null;
  const synthesising = snapshot.investigation.state === "Synthesising";
  const systemPause = (
    <SystemPause s={snapshot} command={command} onShowErrors={() => { setLogCollapsed(false); setErrorsRequest((r) => ({ filter: "problems", n: (r?.n ?? 0) + 1 })); }} />
  );
  const paused = snapshot.investigation.state === "Paused" && snapshot.investigation.pause_cause !== null && snapshot.investigation.pause_cause !== "user";
  // One banner at a time: a system pause first, then a refused command, then the recovery notice.
  const banner = paused ? systemPause
    : commandError ? <Banner tone="warn" title={commandError.message} />
    : recovery.notice ? <RecoveryNotice event={recovery.notice} onDismiss={recovery.dismiss} />
    : undefined;
  return (
    <BoardLayout
      sheetOpen={sheetOpen}
      onCloseSheet={() => setSheetOpen(false)}
      tab={tab}
      onTab={setTab}
      banner={banner}
      header={
        <BoardHeader s={snapshot} status={status}
          runControls={<RunControls s={snapshot} command={command} bannerShown={paused} />}
          focusAction={
            <Button size="sm" sent={command.isSent("run_everything")} sentLabel="Running everything…"
              onClick={() => void command.send("run_everything", { settledBy: (ev) => ev.type === "focus.changed" })}>
              Run everything
            </Button>
          } />
      }
      executionOrder={
        synthesising
          ? <Synthesising claims={synthesisClaims} />
          : <ExecutionOrder s={snapshot} events={events} selectedId={selectedId} onSelect={pick} live={status === "open"} onRestore={restore} restoring={restoring} />
      }
      graph={<BoardGraph s={snapshot} events={events} selectedId={selectedId} onSelect={pick} live={status === "open"} />}
      eventLog={
        <LiveEventLog id={id} events={events} nodes={snapshot.nodes} seq={snapshot.seq} gaps={gaps}
          selectedId={selectedId} onSelect={pick} collapsed={logCollapsed} onToggle={() => setLogCollapsed((c) => !c)}
          onReachEnd={loadOlder} older={older} filterRequest={errorsRequest} />
      }
      inspector={
        <Inspector investigationId={id} s={snapshot} events={events} nodeId={inspected} live={status === "open"}
          nodeActions={<NodeActions state={actions} />}
          notice={inspectedNode ? <RerunQuestion node={inspectedNode} state={actions} /> : null}
          restoreAction={inspectedNode && inspectedNode.inclusion !== "Included" ? (
            <Button variant="steer" sent={actions.isSent("restore_branch")} sentLabel="Restoring…" onClick={() => actions.run("restore_branch")}>Restore branch</Button>
          ) : null}
          onRestore={restore} restoring={restoring} onSeq={showSeq}
          composer={inspectedNode ? <BoardComposer s={snapshot} node={inspectedNode} command={command} focusToken={focusToken} onSeq={showSeq} /> : null} />
      }
    />
  );
}

/** The composer pinned to the bottom of the inspector, aimed at the selected node (a Rejected
 * node's parent), with the target's own latest instructions above it. */
function BoardComposer({ s, node, command, focusToken, onSeq }: {
  s: Snapshot; node: GraphNode; command: ReturnType<typeof useCommand>; focusToken: number; onSeq: (seq: number) => void;
}) {
  const target = instructTarget(s, node);
  const state = s.investigation.state;
  const isRoot = target.parent_id === null;
  const key = `instruct:${target.id}`;
  const locked =
    isRoot ? true
    : state === "Stopped" ? "Resume the investigation to give instructions."
    : state === "Running" || state === "Paused" ? false
    : "The research has ended. Instructions no longer apply.";
  const reach = descendants(s, target.id) + 1;
  const hasChildren = s.nodes.some((n) => n.parent_id === target.id && n.inclusion === "Included" && n.status !== "Rejected");
  const names = Object.fromEntries(s.nodes.map((n) => [n.id, n.display_id]));
  const questions = Object.fromEntries(s.nodes.map((n) => [n.id, n.question]));
  const own = s.instructions.filter((i) => i.node_id === target.id && i.state !== "undone");
  const shown = [...own.filter((i) => i.state === "queued"), ...own.filter((i) => i.state === "applied").slice(-1)];
  return (
    <>
      {shown.map((i) => (
        <Instruction key={i.id} instruction={i} nodeDisplayIds={names} nodeQuestions={questions}
          variant={i.state === "queued" ? "queued" : "applied"} onSeq={onSeq}
          waitingFor={i.waiting_for ? `applies when ${i.waiting_for}` : "applies at once"}
          onRestore={(nid) => void command.send("restore_branch", { key: `restore_branch:${nid}`, nodeId: nid })}
          restoring={(nid) => command.isSent(`restore_branch:${nid}`)} />
      ))}
      <InstructionComposer
        target={{ id: target.id, display_id: target.display_id, label: isRoot ? "the whole investigation" : target.question }}
        reach={reach} hasChildren={hasChildren} locked={locked} focusToken={focusToken}
        buttonLabel="Send instruction"
        // One pink control per view: an excluded node's Restore branch takes it.
        buttonVariant={node.inclusion === "Included" ? "steer" : "default"}
        sent={command.isSent(key)} sentLabel="Sending…" draftKey={s.investigation.id}
        onSend={(text) => command.send("add_instruction", { key, nodeId: target.id, payload: { text } })} />
    </>
  );
}
