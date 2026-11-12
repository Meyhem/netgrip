import { useCallback, useEffect, useState } from "react";
import { ApiError, sendCommand } from "../api/client";
import type { DurableEvent } from "../api/types";
import { subscribeDurable } from "./investigationStore";

export interface SendOptions {
  /** What `isSent` asks about; defaults to the command type. */
  key?: string;
  nodeId?: string | null;
  payload?: Record<string, unknown>;
  /** Which of the command's events confirms it. Defaults to the first one. */
  until?: (ev: DurableEvent) => boolean;
}

export interface CommandError { key: string; code: string; message: string }

interface Pending { id: string; until?: (ev: DurableEvent) => boolean }

/** Commands with client-generated ids (steering.md, "the life of any command"): `isSent(key)` is
 * true from the click until a durable event carrying that command's id arrives on the stream.
 * A refused or unsent command ends is-sent and sets `error`. Needs `useInvestigation(id)` mounted
 * so the stream is open. */
export function useCommand(investigationId: string) {
  const [pending, setPending] = useState<Record<string, Pending>>({});
  const [error, setError] = useState<CommandError | null>(null);

  useEffect(
    () =>
      subscribeDurable(investigationId, (ev) => {
        if (!ev.command_id) return;
        setPending((p) => {
          const done = Object.keys(p).filter((k) => p[k].id === ev.command_id && (!p[k].until || p[k].until!(ev)));
          if (!done.length) return p;
          const next = { ...p };
          for (const k of done) delete next[k];
          return next;
        });
      }),
    [investigationId],
  );

  const send = useCallback(
    async (type: string, opts: SendOptions = {}): Promise<boolean> => {
      const key = opts.key ?? type;
      const id = crypto.randomUUID();
      setError(null);
      setPending((p) => ({ ...p, [key]: { id, until: opts.until } }));
      try {
        await sendCommand(investigationId, type, { id, nodeId: opts.nodeId, payload: opts.payload });
        return true;
      } catch (e) {
        setPending((p) => {
          if (p[key]?.id !== id) return p;
          const next = { ...p };
          delete next[key];
          return next;
        });
        setError({
          key,
          code: e instanceof ApiError ? e.code : "network",
          message: e instanceof Error && e.message ? e.message : "The command was not sent.",
        });
        return false;
      }
    },
    [investigationId],
  );

  const isSent = useCallback((key: string) => key in pending, [pending]);

  return { send, isSent, error, clearError: () => setError(null) };
}
