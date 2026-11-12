import { useCallback, useEffect, useRef, useState } from "react";

/** Load now and every `intervalMs`. `error` is set while the latest attempt failed; `data`
 * keeps the last good value so a screen never pretends a failure means "empty". */
export function usePoll<T>(load: () => Promise<T>, intervalMs: number) {
  const [data, setData] = useState<T | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);
  const loadRef = useRef(load);
  loadRef.current = load;
  const reload = useCallback(async () => {
    try {
      setData(await loadRef.current());
      setError(null);
    } catch (e) {
      setError(e);
    }
  }, []);
  useEffect(() => {
    void reload();
    if (!intervalMs) return;
    const t = setInterval(() => void reload(), intervalMs);
    return () => clearInterval(t);
  }, [reload, intervalMs]);
  return { data, error, reload };
}
