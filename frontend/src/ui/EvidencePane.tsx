import type { ReactNode } from "react";
import type { ReportClaim } from "../api/types";
import { Button } from "./Button";
import { ClaimCard } from "./ClaimCard";

/** ScreenReport region 4: the evidence for the citation that is open. The ClaimCard, the path of
 * nodes that produced it, and where else the report uses it. */
export function EvidencePane({ claim, usedIn, nodeDisplayIds, onClose, onBoard }: {
  claim: ReportClaim; usedIn: string[]; nodeDisplayIds: Record<string, string>;
  onClose: () => void;
  /** "show on the board": opens the board with the producing node selected. */
  onBoard: ReactNode;
}) {
  return (
    <aside className="ng-pane ng-pane--right report-evidence" aria-label="Evidence">
      <div className="ng-panel__head">
        <span className="ng-label">Evidence for {claim.label}</span>
        <Button variant="quiet" size="sm" className="ng-right" aria-label="Close evidence" onClick={onClose}>✕</Button>
      </div>
      <div className="ng-pane__scroll ng-col report-evidence__body">
        <ClaimCard claim={{ ...claim, id: claim.label }} nodeDisplayIds={nodeDisplayIds} />
        <div className="ng-col">
          <span className="ng-label">How it got here</span>
          <div className="ng-well report-path">
            {claim.path.map((n, i) => (
              <div key={n.id} className="report-path__row" style={{ paddingLeft: `${i * 16}px` }}>
                {i > 0 && "└ "}{n.display_id} {n.question}
              </div>
            ))}
          </div>
          <span className="ng-small">{onBoard}</span>
        </div>
        <div className="ng-col">
          <span className="ng-label">Used in</span>
          <span className="ng-small ng-muted">{usedIn.join(" · ")}</span>
        </div>
      </div>
    </aside>
  );
}
