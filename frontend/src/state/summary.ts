// The derived part of an investigation row. Mirrors `summarise` in
// backend/src/netgrip/api/investigations.py; contract/run.json checks the two agree.

import type { GraphNode, InvestigationState, PauseCause, Premise } from "../api/types";

export const PAUSE_REASON: Record<PauseCause, string> = {
  user: "Paused by you.",
  spending_limit: "Reached the spending limit.",
  model_unavailable: "The model service stopped responding.",
  search_unavailable: "Web search stopped responding.",
  key_rejected: "A key was rejected.",
  credit_exhausted: "The model account ran out of credit.",
};

/** running_count: nodes Running while the investigation is Running. nodes_total: nodes below
 * the root that were approved. summary: Running, the first running node's activity
 * ("D1 Searching"); Paused, the cause; then each refuted premise; joined by " · ". */
export function summarise(
  state: InvestigationState, pauseCause: PauseCause | null, nodes: GraphNode[], premises: Premise[],
): { running_count: number; nodes_total: number; summary: string | null } {
  const running = state === "Running" ? nodes.filter((n) => n.status === "Running") : [];
  const parts: string[] = [];
  if (state === "Running") {
    const live = running.find((n) => n.activity);
    if (live) parts.push(`${live.display_id} ${live.activity}`);
  } else if (state === "Paused") {
    parts.push((pauseCause && PAUSE_REASON[pauseCause]) || "Paused.");
  }
  for (const p of premises) if (p.outcome === "refuted") parts.push(`Premise refuted: ${p.text}`);
  return {
    running_count: running.length,
    nodes_total: nodes.filter((n) => n.depth >= 1 && n.status !== "Proposed" && n.status !== "Rejected").length,
    summary: parts.length ? parts.join(" · ") : null,
  };
}
