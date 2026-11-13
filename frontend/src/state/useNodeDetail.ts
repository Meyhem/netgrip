import { useEffect, useMemo, useRef, useState } from "react";
import { getJSON } from "../api/client";
import type { DurableEvent, NodeDetail } from "../api/types";
import { useInvestigationSlice } from "./investigationStore";

export type NodeDetailStatus = "loading" | "ready" | "error";

export interface NodeDetailState {
  /** The detail of the asked node only; null while it loads (never another node's). */
  detail: NodeDetail | null;
  status: NodeDetailStatus;
  error: unknown;
}

/** The node ids a durable event is about: its `node_id`, and `data.node_ids` (inclusion changes). */
function nodesOf(ev: DurableEvent): string[] {
  const ids = Array.isArray(ev.data.node_ids) ? (ev.data.node_ids as string[]) : [];
  return ev.node_id ? [ev.node_id, ...ids] : ids;
}

/** Whether `ev` can change the detail of `nodeId`: an event for the node, a change to one of
 * its claims, a node it proposed, or an instruction on it or an ancestor. */
export function touchesNode(ev: DurableEvent, nodeId: string, claimIds: Set<string>, lineage: Set<string>): boolean {
  if (nodesOf(ev).includes(nodeId)) return true;
  if (ev.data.proposed_by === nodeId) return true;
  if (ev.type.startsWith("claim.")) {
    const ids = [ev.data.claim_id, ev.data.merged_into, ...(Array.isArray(ev.data.claim_ids) ? ev.data.claim_ids : [])];
    if (ids.some((c) => typeof c === "string" && claimIds.has(c))) return true;
  }
  return ev.type.startsWith("instruction.") && ev.node_id !== null && lineage.has(ev.node_id);
}

/** Everything about one node (`GET /api/investigations/{id}/nodes/{node_id}`). `null` asks for
 * the root. Fetched again whenever a durable event that touches the node arrives on the
 * board's stream; a response for an earlier node, or older than one already shown, is dropped. */
export function useNodeDetail(investigationId: string, nodeId: string | null): NodeDetailState {
  const nodes = useInvestigationSlice(investigationId, (s) => s.snapshot?.nodes);
  const events = useInvestigationSlice(investigationId, (s) => s.events);
  const id = nodeId ?? nodes?.find((n) => n.parent_id === null)?.id ?? null;

  const [got, setGot] = useState<{ id: string; detail: NodeDetail | null; error: unknown } | null>(null);
  const current = got && got.id === id ? got : null;

  const claimKey = current?.detail?.claims.map((c) => c.id).join(" ") ?? "";
  const lineageKey = useMemo(() => {
    const byId = new Map((nodes ?? []).map((n) => [n.id, n]));
    const out: string[] = [];
    for (let n = id ? byId.get(id) : undefined; n && out.length <= byId.size; n = n.parent_id ? byId.get(n.parent_id) : undefined) out.push(n.id);
    return out.join(" ");
  }, [nodes, id]);

  // The seq of the newest event that touches the node: a new one means fetch again.
  const version = useMemo(() => {
    if (!id) return 0;
    const claims = new Set(claimKey ? claimKey.split(" ") : []);
    const lineage = new Set(lineageKey ? lineageKey.split(" ") : []);
    for (let i = events.length - 1; i >= 0; i--) if (touchesNode(events[i], id, claims, lineage)) return events[i].seq;
    return 0;
  }, [events, id, claimKey, lineageKey]);

  const asked = useRef(0);
  const shown = useRef<{ id: string | null; req: number }>({ id: null, req: 0 });
  const live = useRef<string | null>(id);
  live.current = id;

  useEffect(() => {
    if (!id) return;
    live.current = id;
    const req = ++asked.current;
    let unmounted = false;
    const keep = () => !unmounted && live.current === id && !(shown.current.id === id && shown.current.req > req);
    getJSON<NodeDetail>(`/api/investigations/${encodeURIComponent(investigationId)}/nodes/${encodeURIComponent(id)}`).then(
      (detail) => {
        if (!keep()) return;
        shown.current = { id, req };
        setGot({ id, detail, error: null });
      },
      (error) => {
        if (!keep()) return;
        shown.current = { id, req };
        // A failed refresh keeps the detail already shown for this node.
        setGot((g) => (g && g.id === id && g.detail ? g : { id, detail: null, error }));
      },
    );
    return () => {
      // Only a change of node or unmount drops the answer; a newer refetch supersedes it by `req`.
      if (live.current !== id) unmounted = true;
    };
  }, [investigationId, id, version]);

  useEffect(() => () => { live.current = null; }, []);

  if (!current) return { detail: null, status: "loading", error: null };
  if (current.detail) return { detail: current.detail, status: "ready", error: null };
  return { detail: null, status: "error", error: current.error };
}
