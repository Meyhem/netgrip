import type { Counts } from "../state/derive";
import { Button } from "./Button";
import { Toggle } from "./Field";

/** Local view settings of the board's graph. They change only this view; they are not commands. */
export interface GraphView {
  collapseCompleted: boolean;
  showExcluded: boolean;
  followActive: boolean;
}

/** Show excluded is on by default (GraphCanvas README); Follow active as in the board preview. */
export const DEFAULT_VIEW: GraphView = { collapseCompleted: false, showExcluded: true, followActive: true };

/** "#" and the last applied sequence number, zero-padded to four digits (419 reads 0419). */
export const seqLabel = (seq: number) => `#${String(seq).padStart(4, "0")}`;

/** The toolbar's lead, before Fit: "Graph", the node counts and the proof of freshness. */
export function GraphToolbar({ counts, seq }: { counts: Counts; seq: number }) {
  const line = [`${counts.nodes} / ${counts.maxNodes} nodes`, `${counts.running} running`, counts.excluded > 0 && `${counts.excluded} excluded`]
    .filter(Boolean)
    .join(" · ");
  return (
    <>
      <span className="ng-label">Graph</span>
      <span className="ng-mono ng-muted">{line}</span>
      <span className="ng-mono ng-faint">current to {seqLabel(seq)}</span>
    </>
  );
}

/** The toolbar's view toggles, after Fit: Collapse completed, Show excluded, Follow active. */
export function GraphToggles({ view, onChange }: { view: GraphView; onChange: (v: GraphView) => void }) {
  return (
    <>
      <Button variant="quiet" size="sm" aria-pressed={view.collapseCompleted}
        onClick={() => onChange({ ...view, collapseCompleted: !view.collapseCompleted })}>
        Collapse completed
      </Button>
      <Toggle on={view.showExcluded} onChange={(showExcluded) => onChange({ ...view, showExcluded })}>Show excluded</Toggle>
      <Toggle on={view.followActive} onChange={(followActive) => onChange({ ...view, followActive })}>Follow active</Toggle>
    </>
  );
}
