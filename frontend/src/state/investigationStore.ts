import { useEffect } from "react";
import { createStore, useStore, type StoreApi } from "zustand";
import { useShallow } from "zustand/react/shallow";
import { getJSON } from "../api/client";
import { openStream } from "../api/stream";
import type { DurableEvent, EphemeralEvent, Snapshot } from "../api/types";
import { reduce } from "./reduce";

export type ConnectionStatus = "loading" | "open" | "reconnecting" | "error";

export interface InvestigationState {
  snapshot: Snapshot | null;
  status: ConnectionStatus;
  /** Every durable event seen so far, one per `seq`, oldest first: the snapshot's
   * `recent_events`, then each streamed event, plus older pages added with `addEvents`. */
  events: DurableEvent[];
  /** Streamed model text now being written, one per node: only the current step's, never
   * stored (D-11). Read it with `liveModelText`. */
  modelText: Record<string, ModelText>;
  /** Long catch-ups (more than GAP_MIN events at once), shown as "N events while this tab
   * was closed" after the event with seq `afterSeq`. */
  gaps: Gap[];
  /** Catch-ups after each reconnect, while they are counted (see trackCatchUp). */
  catchUps: CatchUp[];
  error: unknown;
}

/** The model text a node's open trail step is streaming (`ephemeral` `model_text`). */
export interface ModelText { node_id: string; step: number; text: string; /** when the first delta arrived */ at: string }

/** Fold one ephemeral message into the current model text. A delta for a later step replaces
 * the node's text; a late one for an earlier step is dropped. */
export function applyModelText(m: Record<string, ModelText>, ev: EphemeralEvent, now = Date.now()): Record<string, ModelText> {
  const step = ev.data?.step, delta = ev.data?.delta;
  if (ev.kind !== "model_text" || !ev.node_id || typeof step !== "number" || typeof delta !== "string") return m;
  const cur = m[ev.node_id];
  if (cur && cur.step > step) return m;
  const next = cur && cur.step === step ? { ...cur, text: cur.text + delta } : { node_id: ev.node_id, step, text: delta, at: new Date(now).toISOString() };
  return { ...m, [ev.node_id]: next };
}

/** Durable events that end a node's open step: its model text is dropped. */
const ENDS_STEP = new Set(["node.activity", "node.step_completed", "node.completed", "node.failed", "node.reset", "node.waiting_on_children", "node.started"]);

export function dropModelText(m: Record<string, ModelText>, ev: DurableEvent): Record<string, ModelText> {
  if (!ev.node_id || !(ev.node_id in m) || !ENDS_STEP.has(ev.type)) return m;
  const { [ev.node_id]: _gone, ...rest } = m;
  return rest;
}

/** The model text being written now, oldest first. Shared by the event log and the trail. */
export function liveModelText(s: Pick<InvestigationState, "modelText">): ModelText[] {
  return Object.values(s.modelText).sort((a, b) => a.at.localeCompare(b.at));
}

/** More than this many events at once after a reconnect insert a gap row (EventLog README). */
export const GAP_MIN = 20;

export interface Gap { afterSeq: number; count: number }

/** One catch-up: the events recorded after `afterSeq` and before the stream reopened at
 * `since` (ms). The server replays them first; the first event recorded after `since` ends it. */
export interface CatchUp { afterSeq: number; since: number; count: number; done: boolean }

export const startCatchUp = (afterSeq: number, since: number): CatchUp => ({ afterSeq, since, count: 0, done: false });

export function trackCatchUp(c: CatchUp, ev: DurableEvent): CatchUp {
  if (c.done || ev.seq <= c.afterSeq) return c;
  if (Date.parse(ev.at) > c.since) return { ...c, done: true };
  return { ...c, count: c.count + 1 };
}

export const gapRows = (cs: CatchUp[]): Gap[] => cs.filter((c) => c.count > GAP_MIN).map(({ afterSeq, count }) => ({ afterSeq, count }));

/** The last seq this browser showed for an investigation, so that reopening a closed tab can
 * say how much happened meanwhile. Only the number is kept. */
const LAST_SEEN = (id: string) => `netgrip.lastSeq.${id}`;
function readLastSeen(id: string): number | null {
  try {
    const v = localStorage.getItem(LAST_SEEN(id));
    return v === null ? null : Number(v);
  } catch {
    return null;
  }
}
function writeLastSeen(id: string, seq: number): void {
  try { localStorage.setItem(LAST_SEEN(id), String(seq)); } catch { /* storage unavailable: no gap row */ }
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

/** The held events with a snapshot's `recent_events`. When they do not join up (the board was
 * left while more events happened than `recent_events` carries), the held ones are dropped:
 * older pages then load backwards from the new oldest, so no hole is left in the list. */
export function joinRecent(held: DurableEvent[], recent: DurableEvent[]): DurableEvent[] {
  if (held.length && recent.length && recent[0].seq > held[held.length - 1].seq + 1) return recent;
  return mergeEvents(held, recent);
}

/** Add durable events to what is kept for `id` (older pages of the log fetched with `before=`).
 * De-duplicated by `seq`; the list stays in seq order. */
export function addEvents(id: string, events: DurableEvent[]): void {
  const store = storeFor(id);
  store.setState((s) => ({ events: mergeEvents(s.events, events) }));
}

/** Streamed model text arrives in many small deltas: they are folded into the store at most
 * once per animation frame (a timer where there are no frames). */
const nextFrame: (fn: () => void) => () => void = (fn) => {
  if (typeof requestAnimationFrame === "function") {
    const h = requestAnimationFrame(fn);
    return () => cancelAnimationFrame(h);
  }
  const t = setTimeout(fn, 16);
  return () => clearTimeout(t);
};

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

/** Deliver `ev` to the subscribers as if the stream had (for tests of what reacts to events). */
export function emitDurable(id: string, ev: DurableEvent): void {
  for (const fn of [...(durableListeners.get(id) ?? [])]) fn(ev);
}

function storeFor(id: string): StoreApi<InvestigationState> {
  let store = stores.get(id);
  if (!store) {
    store = createStore<InvestigationState>(() => ({
      snapshot: null, status: "loading", events: [], modelText: {}, gaps: [], catchUps: [], error: null,
    }));
    stores.set(id, store);
  }
  return store;
}

/** Drop what is kept for `id` (after deleting it, and between tests). `keepLastSeen` keeps
 * the last seq shown, as when a tab is closed. */
export function forgetInvestigation(id: string, opts: { keepLastSeen?: boolean } = {}): void {
  stores.delete(id);
  if (!opts.keepLastSeen) {
    try { localStorage.removeItem(LAST_SEEN(id)); } catch { /* nothing kept */ }
  }
}

/** Load the snapshot, then follow the stream from its `seq`, folding durable events in with
 * `reduce`. The stream closes when the component unmounts. */
export function useInvestigation(id: string): BoardState {
  const store = storeFor(id);
  useEffect(() => {
    let cancelled = false;
    let close: (() => void) | null = null;
    let stopFrames: (() => void) | null = null;
    store.setState({ status: "loading", error: null });
    getJSON<Snapshot>(`/api/investigations/${encodeURIComponent(id)}`).then(
      (loaded) => {
        if (cancelled) return;
        // A snapshot kept from an earlier mount may be newer; reduce never goes backwards.
        const current = store.getState().snapshot;
        const snapshot = current && current.seq > loaded.seq ? current : loaded;
        // Seen before, in this tab or one since closed: a long gap gets its row.
        const seen = current?.seq ?? readLastSeen(id);
        const opened: CatchUp[] = seen !== null && snapshot.seq > seen ? [{ afterSeq: seen, since: 0, count: snapshot.seq - seen, done: true }] : [];
        store.setState((s) => ({
          snapshot,
          events: joinRecent(s.events, loaded.recent_events ?? []),
          catchUps: [...s.catchUps, ...opened],
          gaps: gapRows([...s.catchUps, ...opened]),
          modelText: {},
        }));
        writeLastSeen(id, snapshot.seq);
        let reconnecting = false;
        // Model-text deltas waiting for the next frame, and the frame's cancel.
        let pending: EphemeralEvent[] = [];
        let cancelFrame: (() => void) | null = null;
        const flush = () => {
          cancelFrame?.();
          cancelFrame = null;
          if (!pending.length) return;
          const batch = pending;
          pending = [];
          store.setState((s) => ({ modelText: batch.reduce((m, ev) => applyModelText(m, ev), s.modelText) }));
        };
        const dropPending = () => {
          cancelFrame?.();
          cancelFrame = null;
          pending = [];
        };
        stopFrames = dropPending;
        close = openStream(id, snapshot.seq, {
          onDurable: (ev) => {
            // Text streamed before this event is applied first, so the event can end it.
            flush();
            store.setState((s) => {
              if (!s.snapshot) return s;
              const catchUps = s.catchUps.map((c) => trackCatchUp(c, ev));
              const counted = catchUps.some((c, i) => c !== s.catchUps[i]);
              return {
                snapshot: reduce(s.snapshot, ev),
                events: mergeEvents(s.events, [ev]),
                modelText: dropModelText(s.modelText, ev),
                ...(counted ? { catchUps, gaps: gapRows(catchUps) } : {}),
              };
            });
            const seq = store.getState().snapshot?.seq;
            if (seq !== undefined) writeLastSeen(id, seq);
            for (const fn of [...(durableListeners.get(id) ?? [])]) fn(ev);
          },
          onEphemeral: (ev) => {
            if (ev.kind !== "model_text") return;
            pending.push(ev);
            if (!cancelFrame) cancelFrame = nextFrame(flush);
          },
          onStatus: (status) => {
            if (status === "reconnecting") {
              reconnecting = true;
              // The connection dropped mid-step: the rest of that text is not replayed.
              dropPending();
              store.setState({ status, modelText: {} });
            } else if (reconnecting) {
              reconnecting = false;
              store.setState((s) => ({ status, catchUps: [...s.catchUps, startCatchUp(s.snapshot?.seq ?? 0, Date.now())] }));
            } else {
              store.setState({ status });
            }
          },
        });
      },
      (error) => {
        if (!cancelled) store.setState({ status: "error", error });
      },
    );
    return () => {
      cancelled = true;
      close?.();
      stopFrames?.();
    };
  }, [id, store]);
  return useStore(store, useShallow(withoutModelText));
}

/** What the board needs on every durable event. Model text changes on every frame of
 * streaming: only the parts that show it subscribe to it (`useModelText`). */
export type BoardState = Omit<InvestigationState, "modelText">;
function withoutModelText({ modelText: _skip, ...rest }: InvestigationState): BoardState {
  return rest;
}

/** For tests: the model text held for `id`, and a listener on every store update. */
export function readModelText(id: string): Record<string, ModelText> {
  return storeFor(id).getState().modelText;
}
export function subscribeStore(id: string, fn: () => void): () => void {
  return storeFor(id).subscribe(fn);
}

/** The model text being written now, oldest first (the event log's live rows). */
export function useLiveModelText(id: string): ModelText[] {
  return useStore(storeFor(id), useShallow((s) => liveModelText(s)));
}

/** Read part of what is kept for `id` without opening a stream (the board's `useInvestigation`
 * owns the stream). */
export function useInvestigationSlice<T>(id: string, select: (s: InvestigationState) => T): T {
  return useStore(storeFor(id), select);
}
