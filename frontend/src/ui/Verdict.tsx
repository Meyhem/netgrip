import type { ReactNode } from "react";
import type { Confidence as Level, Verdict as VerdictData } from "../api/types";
import { Confidence } from "./Confidence";
import { StatusPill } from "./StatusPill";

const LEVELS: Level[] = ["low", "medium", "high"];

/** The verdict stored on a node row (`node.completed.data.verdict`), or null. */
export function asVerdict(v: unknown): VerdictData | null {
  if (!v || typeof v !== "object") return null;
  const { text, confidence } = v as { text?: unknown; confidence?: unknown };
  if (typeof text !== "string") return null;
  return { text, confidence: LEVELS.includes(confidence as Level) ? (confidence as Level) : "low" };
}

/** A node's verdict, its confidence and one mono line of counts. Without a verdict it says
 * so; a failed node gets the failed state with what happened and its ways out (`actions`,
 * Phase 6). The text is the agent's, shown as written. */
export function Verdict({ verdict, failed, counts, actions }: {
  verdict: VerdictData | null;
  /** The failure reason, when the node Failed. */
  failed?: string | null;
  counts?: string | null;
  actions?: ReactNode;
}) {
  if (failed != null) {
    return (
      <div className="ng-panel"><div className="ng-panel__body ng-col">
        <div className="ng-row"><span className="ng-label">No verdict</span><span className="ng-right"><StatusPill kind="node" state="Failed" /></span></div>
        <p>{failed || "This node failed."}</p>
        {actions != null && <div className="ng-row">{actions}</div>}
      </div></div>
    );
  }
  if (!verdict) {
    return (
      <div className="ng-row"><span className="ng-label">Verdict</span><span className="ng-small ng-faint ng-right">not yet · appears here the moment it exists</span></div>
    );
  }
  return (
    <div className="ng-panel"><div className="ng-panel__body ng-col">
      <div className="ng-row"><span className="ng-label">Verdict</span><Confidence level={verdict.confidence} className="ng-right" /></div>
      <p>{verdict.text}</p>
      {counts && <div className="ng-row ng-mono ng-muted"><span>{counts}</span></div>}
    </div></div>
  );
}
