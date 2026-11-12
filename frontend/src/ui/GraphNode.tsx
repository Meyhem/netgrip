import type { CSSProperties } from "react";
import type { GraphNode as Node, NodeState } from "../api/types";
import { cx } from "./cx";
import { KIND_CODE } from "./vocab";

export type GraphMode = "plan" | "board";

/** Class per execution status, spelled out for the design contract test. */
const STATUS_CLASS: Record<NodeState, string> = {
  Proposed: "ng-node--proposed",
  Rejected: "ng-node--rejected",
  // bundle.css defines no pending modifier: a pending node is the plain ng-node.
  Pending: "",
  Running: "ng-node--running",
  "Waiting on children": "ng-node--waiting",
  Paused: "ng-node--paused",
  Completed: "ng-node--done",
  Failed: "ng-node--failed",
};

/** Glyph and word on line 1 (the GraphNode preview shortens "Waiting on children" to "Waiting"). */
const STATUS_WORD: Record<NodeState, [string, string]> = {
  Proposed: ["◌", "Proposed"],
  Rejected: ["⊘", "Rejected"],
  Pending: ["○", "Pending"],
  Running: ["●", "Running"],
  "Waiting on children": ["◔", "Waiting"],
  Paused: ["‖", "Paused"],
  Completed: ["✓", "Completed"],
  Failed: ["✕", "Failed"],
};

export interface GraphNodeProps {
  node: Node;
  selected: boolean;
  onSelect: (id: string) => void;
  mode: GraphMode;
  /** Line 3. Defaults to the activity while running, or the verdict summary once complete. */
  sub?: string | null;
  /** Overrides the instruction mark "✎︎ n" (plan review shows "new" on nodes the last instruction added). */
  mark?: string | null;
  /** Removed by the last instruction: shown once more as excluded with "− Removed". */
  removed?: boolean;
  /** "−" for an open branch, "+4" for a folded one. */
  fold?: string | null;
  onFold?: (id: string) => void;
  style?: CSSProperties;
}

export function GraphNode({ node, selected, onSelect, mode, sub, mark, removed, fold, onFold, style }: GraphNodeProps) {
  const excluded = removed || node.inclusion !== "Included";
  const planned = mode === "plan" && node.status === "Proposed";
  const [glyph, word] = removed
    ? ["−", "Removed"]
    : node.inclusion === "Ignored"
      ? ["⦸", "Ignored"]
      : node.inclusion === "Superseded"
        ? ["↺", "Superseded"]
        : planned
          ? ["◌", "Planned"]
          : STATUS_WORD[node.status];
  const pulses = !excluded && mode === "board" && node.status === "Running";
  const markText = mark !== undefined ? mark : node.instruction_count > 0 ? `✎︎ ${node.instruction_count}` : null;
  const line3 = sub !== undefined ? sub : nodeSub(node);

  return (
    <div
      className={cx("ng-node", excluded ? "ng-node--excluded" : STATUS_CLASS[node.status], selected && "is-selected")}
      style={style}
      role="button"
      tabIndex={0}
      aria-pressed={selected}
      data-node={node.id}
      onClick={() => onSelect(node.id)}
      onDoubleClick={onFold ? () => onFold(node.id) : undefined}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect(node.id);
        }
      }}
    >
      {markText && <span className="ng-node__mark">{markText}</span>}
      <div className="ng-node__top">
        <span className="ng-node__kind">{KIND_CODE[node.kind]}</span>
        <span>{node.display_id}</span>
        <span className="ng-node__state">
          {pulses ? <span className="ng-pulse">{glyph}</span> : glyph} {word}
        </span>
      </div>
      <div className="ng-node__q">{node.question}</div>
      {line3 && <div className="ng-node__sub">{line3}</div>}
      {fold && <span className="ng-node__fold">{fold}</span>}
    </div>
  );
}

/** Line 3 from the node itself: the activity while running, the verdict summary once complete. */
export function nodeSub(node: Node): string | null {
  if (node.status === "Running" && node.activity) return node.activity;
  if (node.status === "Completed") {
    const v = node.verdict as { summary?: unknown } | null;
    if (v && typeof v === "object" && typeof v.summary === "string") return v.summary;
  }
  return null;
}
