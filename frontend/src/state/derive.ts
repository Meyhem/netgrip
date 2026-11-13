// Pure views of a snapshot for the control board. Nothing here guesses state: every row comes
// from the snapshot's nodes, schedule and premises, or from durable events.

import type { DurableEvent, GraphNode, Premise, Snapshot } from "../api/types";

export interface NowRow { node: GraphNode }
/** `position` is 1-based; `reason` is the raw `schedule.updated` reason, `waitText` its words. */
export interface NextRow { node: GraphNode; position: number; reason: string | null; waitText: string }
/** `finishedAt` is the time of the node's last `node.completed` or `node.failed`, when known. */
export interface DoneRow { node: GraphNode; finishedAt: string | null; refutedPremise: boolean }
export type NotRunningWhy = "Ignored" | "Superseded" | "Rejected" | "Paused";
export interface NotRunningRow { node: GraphNode; why: NotRunningWhy }

export interface Sections { now: NowRow[]; next: NextRow[]; done: DoneRow[]; notRunning: NotRunningRow[] }

export interface Counts {
  /** Approved nodes below the root (not Proposed or Rejected), as `nodes_total`. */
  nodes: number;
  maxNodes: number;
  running: number;
  /** Ignored, Superseded and Rejected nodes. */
  excluded: number;
  /** The deepest approved depth. */
  depth: number;
  maxDepth: number;
  slots: number;
}

const FINISHED = new Set(["Completed", "Failed", "Rejected"]);
const STILL_TO_RUN = new Set(["Pending", "Running", "Waiting on children", "Paused"]);
const approved = (n: GraphNode) => n.status !== "Proposed" && n.status !== "Rejected";
const displayOf = (nodes: GraphNode[], id: string) => nodes.find((n) => n.id === id)?.display_id ?? id;

/** The ExecutionOrder README's words for a `schedule.updated` wait reason. */
export function waitReasonText(reason: string, nodes: GraphNode[]): string {
  const [kind, arg] = reason.split(/:(.*)/s);
  switch (kind) {
    case "dependency": return `waits for ${displayOf(nodes, arg)} (dependency)`;
    case "slot": return "waits for a free slot";
    case "orchestrator": return "awaiting the orchestrator";
    case "focus": return `waits: you are running only ${displayOf(nodes, arg)}`;
    case "paused": return "paused";
    default: return reason;
  }
}

export function refutedPremises(s: Snapshot): Premise[] {
  return s.premises.filter((p) => p.outcome === "refuted");
}

/** The ExecutionOrder sections. While the investigation is Paused nothing is in Now: nodes
 * still marked Running (stopped mid-work by the pause) head Next with "paused". Done is newest
 * first by the node's `finished_seq`, else by its finishing event among `events` (oldest first:
 * the store's accumulated durable events)
 * order Done newest first; a finished node with no finishing event among them sorts after the
 * known ones, newest created first. */
export function sections(s: Snapshot, events: DurableEvent[]): Sections {
  const nodes = s.nodes;
  const reasons = s.schedule.reasons;
  const kids = new Map<string, GraphNode[]>();
  for (const n of nodes) {
    if (n.parent_id !== null && n.inclusion === "Included") kids.set(n.parent_id, [...(kids.get(n.parent_id) ?? []), n]);
  }

  const paused = s.investigation.state === "Paused";
  const now: NowRow[] = [];
  const held: GraphNode[] = [];
  const doneNodes: GraphNode[] = [];
  const notRunning: NotRunningRow[] = [];
  const waiting: GraphNode[] = [];
  for (const n of nodes) {
    if (n.inclusion !== "Included") notRunning.push({ node: n, why: n.inclusion });
    else if (n.status === "Rejected") notRunning.push({ node: n, why: "Rejected" });
    else if (n.status === "Paused" || (n.status === "Pending" && reasons[n.id] === "paused")) notRunning.push({ node: n, why: "Paused" });
    else if (n.status === "Running") {
      if (paused) held.push(n);
      else now.push({ node: n });
    } else if (n.status === "Completed" || n.status === "Failed") doneNodes.push(n);
    else waiting.push(n); // Pending, Proposed, Waiting on children
  }

  // Next: the scheduler's order first, then the rest in the order they would be considered
  // (premise checks, depth, creation), then coordinators waiting on children, deepest first.
  const waitingIds = new Set(waiting.map((n) => n.id));
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const scheduled = s.schedule.order.filter((id) => waitingIds.has(id)).map((id) => byId.get(id)!);
  const inOrder = new Set(scheduled.map((n) => n.id));
  const index = new Map(nodes.map((n, i) => [n.id, i]));
  const rest = waiting.filter((n) => !inOrder.has(n.id));
  const toStart = rest
    .filter((n) => n.status !== "Waiting on children" && !kids.has(n.id))
    .sort((a, b) => Number(a.kind !== "Premise check") - Number(b.kind !== "Premise check") || a.depth - b.depth || index.get(a.id)! - index.get(b.id)!);
  const coordinators = rest
    .filter((n) => n.status === "Waiting on children" || kids.has(n.id))
    .sort((a, b) => b.depth - a.depth || index.get(a.id)! - index.get(b.id)!);
  // Running nodes held by the investigation's pause come first: they continue on Resume.
  const queued: { n: GraphNode; reason: string | null }[] = [
    ...held.map((n) => ({ n, reason: "paused" })),
    ...[...scheduled, ...toStart, ...coordinators].map((n) => ({ n, reason: reasons[n.id] ?? null })),
  ];
  const next: NextRow[] = queued.map(({ n, reason }, i) => {
    let waitText = reason ? waitReasonText(reason, nodes) : "";
    if (!reason && !inOrder.has(n.id)) {
      const open = (kids.get(n.id) ?? []).filter((k) => !FINISHED.has(k.status));
      if (open.length) waitText = `waits for ${open.map((k) => k.display_id).join(", ")}`;
    }
    return { node: n, position: i + 1, reason, waitText };
  });

  // Done: newest first by the node's finish, projected on its row; events cover older snapshots.
  const finished = new Map<string, { seq: number; at: string }>();
  for (const ev of events) {
    if ((ev.type === "node.completed" || ev.type === "node.failed") && ev.node_id) finished.set(ev.node_id, { seq: ev.seq, at: ev.at });
  }
  for (const n of doneNodes) {
    if (n.finished_seq != null && n.finished_at != null) finished.set(n.id, { seq: n.finished_seq, at: n.finished_at });
  }
  const refutedNodes = new Set(refutedPremises(s).map((p) => p.node_id).filter(Boolean));
  const done: DoneRow[] = doneNodes
    .sort((a, b) => {
      const fa = finished.get(a.id)?.seq ?? -1;
      const fb = finished.get(b.id)?.seq ?? -1;
      return fb - fa || index.get(b.id)! - index.get(a.id)!;
    })
    .map((n) => ({ node: n, finishedAt: finished.get(n.id)?.at ?? null, refutedPremise: refutedNodes.has(n.id) }));

  return { now, next, done, notRunning };
}

export function counts(s: Snapshot): Counts {
  const budget = s.investigation.settings?.effort_budget;
  const below = s.nodes.filter((n) => n.depth >= 1 && approved(n));
  return {
    nodes: below.length,
    maxNodes: budget?.max_nodes ?? s.investigation.nodes_max,
    running: s.nodes.filter((n) => n.status === "Running").length,
    excluded: s.nodes.filter((n) => n.inclusion !== "Included" || n.status === "Rejected").length,
    depth: below.reduce((d, n) => Math.max(d, n.depth), 0),
    maxDepth: budget?.max_depth ?? 0,
    slots: s.schedule.slots,
  };
}

/** How many nodes an instruction to `nodeId` reaches: the Included nodes of its branch (itself
 * and every descendant) that may still run. Mirrors node detail's `branch.reach`. */
export function reach(s: Snapshot, nodeId: string): number {
  const children = new Map<string, GraphNode[]>();
  for (const n of s.nodes) if (n.parent_id !== null) children.set(n.parent_id, [...(children.get(n.parent_id) ?? []), n]);
  const start = s.nodes.find((n) => n.id === nodeId);
  if (!start) return 0;
  let count = 0;
  const stack = [start];
  while (stack.length) {
    const n = stack.pop()!;
    if (n.inclusion === "Included" && STILL_TO_RUN.has(n.status)) count += 1;
    stack.push(...(children.get(n.id) ?? []));
  }
  return count;
}
