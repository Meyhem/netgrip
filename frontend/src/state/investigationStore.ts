import { useEffect } from "react";
import { createStore, useStore, type StoreApi } from "zustand";
import { getJSON } from "../api/client";
import { openStream } from "../api/stream";
import type { DurableEvent, EphemeralEvent, Snapshot } from "../api/types";
import { reduce } from "./reduce";

export type ConnectionStatus = "loading" | "open" | "reconnecting" | "error";

export interface InvestigationState {
  snapshot: Snapshot | null;
  status: ConnectionStatus;
  /** The latest ephemeral messages (streamed model text and similar), oldest first. */
  ephemeral: EphemeralEvent[];
  /** Every durable event seen so far, one per `seq`, oldest first: the snapshot's
   * `recent_events`, then each streamed event, plus older pages added with `addEvents`. */
  events: DurableEvent[];
  error: unknown;
}

/** `a` and `b` as one list sorted by `seq`, one envelope per `seq` (the first one seen). */
export function mergeEvents(a: DurableEvent[], b: DurableEvent[]): DurableEvent[] {
  if (b.length === 0) return a;
  // The common case: streamed events arrive in order after everything known.
  const last = a.length ? a[a.length - 1].seq : -Infinity;
  if (b.every((e, i) => e.seq > (i === 0 ? last : b[i - 1].seq))) return [...a, ...b];
  const bySeq = new Map<number, DurableEvent>();
  for (const e of [...a, ...b]) if (!bySeq.has(e.seq)) bySeq.set(e.seq, e);
  return [...bySeq.values()].sort((x, y) => x.seq - y.seq);
}

/** Add durable events to what is kept for `id` (older pages of the log fetched with `before=`).
 * De-duplicated by `seq`; the list stays in seq order. */
export function addEvents(id: string, events: DurableEvent[]): void {
  const store = storeFor(id);
  store.setState((s) => ({ events: mergeEvents(s.events, events) }));
}

/** How many ephemeral messages are kept; they are never stored or replayed (D-11). */
export const EPHEMERAL_KEEP = 50;

const stores = new Map<string, StoreApi<InvestigationState>>();
const durableListeners = new Map<string, Set<(ev: DurableEvent) => void>>();

/** Call `fn` with every durable event the stream delivers for `id`, after it is applied.
 * Returns the unsubscribe function. */
export function subscribeDurable(id: string, fn: (ev: DurableEvent) => void): () => void {
  let set = durableListeners.get(id);
  if (!set) durableListeners.set(id, (set = new Set()));
  set.add(fn);
  return () => { set.delete(fn); };
}

function storeFor(id: string): StoreApi<InvestigationState> {
  let store = stores.get(id);
  if (!store) {
    store = createStore<InvestigationState>(() => ({ snapshot: null, status: "loading", ephemeral: [], events: [], error: null }));
    stores.set(id, store);
  }
  return store;
}

/** Drop what is kept for `id` (after deleting it, and between tests). */
export function forgetInvestigation(id: string): void {
  stores.delete(id);
}

/** Load the snapshot, then follow the stream from its `seq`, folding durable events in with
 * `reduce`. The stream closes when the component unmounts. */
export function useInvestigation(id: string): InvestigationState {
  const store = storeFor(id);
  useEffect(() => {
    let cancelled = false;
    let close: (() => void) | null = null;
    store.setState({ status: "loading", error: null });
    getJSON<Snapshot>(`/api/investigations/${encodeURIComponent(id)}`).then(
      (loaded) => {
        if (cancelled) return;
        // A snapshot kept from an earlier mount may be newer; reduce never goes backwards.
        const current = store.getState().snapshot;
        const snapshot = current && current.seq > loaded.seq ? current : loaded;
        store.setState((s) => ({ snapshot, events: mergeEvents(s.events, loaded.recent_events ?? []) }));
        close = openStream(id, snapshot.seq, {
          onDurable: (ev) => {
            store.setState((s) => (s.snapshot ? { snapshot: reduce(s.snapshot, ev), events: mergeEvents(s.events, [ev]) } : s));
            for (const fn of [...(durableListeners.get(id) ?? [])]) fn(ev);
          },
          onEphemeral: (ev) => store.setState((s) => ({ ephemeral: [...s.ephemeral, ev].slice(-EPHEMERAL_KEEP) })),
          onStatus: (status) => store.setState({ status }),
        });
      },
      (error) => {
        if (!cancelled) store.setState({ status: "error", error });
      },
    );
    return () => {
      cancelled = true;
      close?.();
    };
  }, [id, store]);
  return useStore(store);
}
