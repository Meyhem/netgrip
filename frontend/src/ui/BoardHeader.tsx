import { useEffect, useRef, useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";
import { deleteInvestigation, getJSON } from "../api/client";
import type { DurableEvent, Snapshot } from "../api/types";
import { downloadJSON } from "../lib/download";
import { clock } from "../lib/format";
import { PRESET_WORD } from "../screens/NewInvestigation";
import { counts, refutedPremises } from "../state/derive";
import { forgetInvestigation, type ConnectionStatus } from "../state/investigationStore";
import { forgetSelection } from "../state/selection";
import { BudgetMeter } from "./BudgetMeter";
import { Button } from "./Button";
import { DeleteDialog } from "./DeleteDialog";
import { StatusPill } from "./StatusPill";

/** ScreenControlBoard region 1: state, the prompt, budget, run controls and the overflow. */
export function BoardHeader({ s, status, runControls, focusAction }: {
  s: Snapshot; status: ConnectionStatus; runControls?: ReactNode;
  /** "Run everything", shown beside the focus line while the user runs only a branch. */
  focusAction?: ReactNode;
}) {
  const inv = s.investigation;
  const id = inv.id;
  const navigate = useNavigate();
  const [menu, setMenu] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [exportFailed, setExportFailed] = useState<string | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!menu) return;
    const close = (e: MouseEvent) => { if (!menuRef.current?.contains(e.target as Node)) setMenu(false); };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [menu]);

  const c = counts(s);
  const refuted = refutedPremises(s).length;
  const preset = inv.settings?.preset;
  const focus = s.focus_node_id ? s.nodes.find((n) => n.id === s.focus_node_id) : undefined;
  const line = focus
    ? `Running only ${focus.display_id}`
    : [inv.effort, preset ? PRESET_WORD[preset] : null, clock(inv.run_seconds), `${inv.running_count} running`].filter(Boolean).join(" · ");
  const reportReady = inv.state === "Completed";

  const exportEvents = async () => {
    setMenu(false);
    setExportFailed(null);
    try {
      const events = await getJSON<DurableEvent[]>(`/api/investigations/${encodeURIComponent(id)}/events`);
      downloadJSON(`netgrip-events-${id}.json`, events);
    } catch (e) {
      setExportFailed(e instanceof Error ? e.message : "The events were not exported.");
    }
  };
  const item = (fn: () => void) => ({
    role: "menuitem", tabIndex: 0, onClick: fn,
    onKeyDown: (e: React.KeyboardEvent) => { if (e.key === "Enter") fn(); },
  });

  return (
    <div className="ng-board__head">
      <Link to="/" className="ng-btn ng-btn--sm ng-btn--quiet" aria-label="Back to investigations">←</Link>
      <div className="ng-col ng-grow board-head__title">
        <div className="ng-row ng-row--nowrap">
          <StatusPill kind="investigation" state={inv.state} origin={inv.pause_cause} reconnecting={status === "reconnecting"} />
          <span className="ng-mono ng-muted">{line}</span>
          {focus && focusAction}
          {refuted > 0 && (
            <span className="ng-pill ng-pill--danger"><i>✕</i>{refuted === 1 ? "Premise refuted" : `${refuted} premises refuted`}</span>
          )}
          {exportFailed && <span className="ng-small ng-danger">{exportFailed}</span>}
        </div>
        <h1 className="ng-title ng-clip" title={inv.prompt}>{inv.prompt}</h1>
      </div>
      <div className="board-head__spend">
        <BudgetMeter label="Spend" value={inv.spent_usd} max={inv.spending_limit_usd} format="money" approximate={inv.spend_approximate} />
      </div>
      <div className="board-head__nodes">
        <BudgetMeter label="Nodes" value={c.nodes} max={c.maxNodes} format="count" />
      </div>
      <div className="board-head__depth">
        <BudgetMeter label="Depth" value={c.depth} max={c.maxDepth} format="count" />
      </div>
      <div className="ng-row ng-row--nowrap board-head__controls" ref={menuRef}>
        {runControls}
        <Button variant="quiet" aria-label="More" aria-haspopup="menu" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>⋯</Button>
        {menu && (
          <div className="ng-menu row-menu" role="menu">
            <div className="ng-menu__item" {...item(() => void exportEvents())}>
              <b>Export events</b>
              <small>Every recorded event of this investigation, as JSON.</small>
            </div>
            {reportReady ? (
              <Link className="ng-menu__item" role="menuitem" to={`/investigations/${encodeURIComponent(id)}`} onClick={() => setMenu(false)}>
                <b>Open report</b>
                <small>The answer, with every statement traced to sources.</small>
              </Link>
            ) : (
              <div className="ng-menu__item is-disabled" role="menuitem" aria-disabled="true" tabIndex={-1}>
                <b>Open report</b>
                <small>Netgrip writes the report when the run completes.</small>
              </div>
            )}
            <div className="ng-menu__sep" />
            <div className="ng-menu__item" {...item(() => { setMenu(false); setDeleting(true); })}>
              <b>Delete investigation</b>
              <small>Removes it and frees its disk space. Asks first.</small>
            </div>
          </div>
        )}
      </div>
      {deleting && (
        <DeleteDialog
          prompt={inv.prompt}
          diskBytes={inv.disk_bytes}
          onCancel={() => setDeleting(false)}
          onDelete={async () => {
            await deleteInvestigation(id);
            forgetInvestigation(id);
            forgetSelection(id);
            navigate("/");
          }}
        />
      )}
    </div>
  );
}
