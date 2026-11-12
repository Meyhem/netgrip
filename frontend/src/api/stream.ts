import type { DurableEvent, EphemeralEvent } from "./types";

export type StreamStatus = "open" | "reconnecting";

export interface StreamHandlers {
  onDurable: (ev: DurableEvent) => void;
  onEphemeral: (ev: EphemeralEvent) => void;
  onStatus: (status: StreamStatus) => void;
}

/** Follow an investigation's live stream from `afterSeq`. Durable events come as
 * `event: durable` (id = seq), ephemeral ones as `event: ephemeral`. On an error the stream is
 * closed and, after `backoffMs`, reopened from the last durable seq received, so nothing is
 * missed; the reducer drops anything replayed. Returns a function that stops it for good. */
export function openStream(
  id: string,
  afterSeq: number,
  handlers: StreamHandlers,
  opts: { backoffMs?: number } = {},
): () => void {
  const backoffMs = opts.backoffMs ?? 1000;
  let lastSeq = afterSeq;
  let source: EventSource | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let stopped = false;

  const connect = () => {
    timer = null;
    if (stopped) return;
    const es = new EventSource(`/api/investigations/${encodeURIComponent(id)}/stream?after=${lastSeq}`);
    source = es;
    es.onopen = () => handlers.onStatus("open");
    es.addEventListener("durable", (msg) => {
      const ev = JSON.parse((msg as MessageEvent<string>).data) as DurableEvent;
      if (ev.seq > lastSeq) lastSeq = ev.seq;
      handlers.onDurable(ev);
    });
    es.addEventListener("ephemeral", (msg) => {
      handlers.onEphemeral(JSON.parse((msg as MessageEvent<string>).data) as EphemeralEvent);
    });
    es.onerror = () => {
      es.close();
      if (source === es) source = null;
      if (stopped || timer) return;
      handlers.onStatus("reconnecting");
      timer = setTimeout(connect, backoffMs);
    };
  };

  connect();
  return () => {
    stopped = true;
    if (timer) clearTimeout(timer);
    source?.close();
    source = null;
  };
}
