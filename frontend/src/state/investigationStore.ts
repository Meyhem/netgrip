import { useEffect } from "react";
import { createStore, useStore, type StoreApi } from "zustand";
import { getJSON } from "../api/client";
import { openStream } from "../api/stream";
import type { EphemeralEvent, Snapshot } from "../api/types";
import { reduce } from "./reduce";

export type ConnectionStatus = "loading" | "open" | "reconnecting" | "error";

export interface InvestigationState {
  snapshot: Snapshot | null;
  status: ConnectionStatus;
  /** The latest ephemeral messages (streamed model text and similar), oldest first. */
  ephemeral: EphemeralEvent[];
  error: unknown;
}

/** How many ephemeral messages are kept; they are never stored or replayed (D-11). */
export const EPHEMERAL_KEEP = 50;

const stores = new Map<string, StoreApi<InvestigationState>>();

function storeFor(id: string): StoreApi<InvestigationState> {
  let store = stores.get(id);
  if (!store) {
    store = createStore<InvestigationState>(() => ({ snapshot: null, status: "loading", ephemeral: [], error: null }));
    stores.set(id, store);
  }
  return store;
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
        store.setState({ snapshot });
        close = openStream(id, snapshot.seq, {
          onDurable: (ev) => store.setState((s) => (s.snapshot ? { snapshot: reduce(s.snapshot, ev) } : s)),
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
