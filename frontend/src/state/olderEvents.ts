import { useCallback, useRef, useState } from "react";
import { getJSON } from "../api/client";
import type { DurableEvent } from "../api/types";
import { addEvents } from "./investigationStore";

/** Events asked for per older page of the log. */
export const OLDER_PAGE = 200;

export type OlderState = "more" | "loading" | "done";

/** Older pages of the event log, on demand: `loadOlder` fetches the `OLDER_PAGE` events before
 * the oldest one kept (`before=`) and adds them to the store. It stops when a page comes back
 * empty or seq 1 is reached. Nothing is fetched until it is called. */
export function useOlderEvents(id: string, events: DurableEvent[], seq: number): { older: OlderState; loadOlder: () => void } {
  const oldest = events.length ? events[0].seq : seq + 1;
  const [exhausted, setExhausted] = useState(false);
  const [loading, setLoading] = useState(false);
  const busy = useRef(false);
  const done = exhausted || oldest <= 1;

  const loadOlder = useCallback(() => {
    if (busy.current || done) return;
    busy.current = true;
    setLoading(true);
    getJSON<DurableEvent[]>(`/api/investigations/${encodeURIComponent(id)}/events?before=${oldest}&limit=${OLDER_PAGE}`)
      .then((page) => {
        if (page.length === 0) setExhausted(true);
        else addEvents(id, page);
      })
      .catch(() => { /* the next scroll to the end tries again */ })
      .finally(() => {
        busy.current = false;
        setLoading(false);
      });
  }, [id, oldest, done]);

  return { older: done ? "done" : loading ? "loading" : "more", loadOlder };
}
