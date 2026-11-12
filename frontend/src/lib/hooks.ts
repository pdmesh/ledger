import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "./api";

type Query = Parameters<typeof api.get>[1];

/** Fetch `path` and re-fetch when the query changes. Returns data + reload(). */
export function useApi<T>(path: string | null, query?: Query, deps: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const key = JSON.stringify([path, query]);
  const seq = useRef(0);

  const load = useCallback(async () => {
    if (!path) return;
    const my = ++seq.current;
    setLoading(true);
    try {
      const d = await api.get<T>(path, query);
      if (my === seq.current) {
        setData(d);
        setError(null);
      }
    } catch (e) {
      if (my === seq.current) setError((e as Error).message);
    } finally {
      if (my === seq.current) setLoading(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, ...deps]);

  useEffect(() => {
    void load();
  }, [load]);

  return { data, error, loading, reload: load, setData };
}

/** Poll while `active` is true. */
export function usePoll(fn: () => void, active: boolean, ms = 2000) {
  useEffect(() => {
    if (!active) return;
    const t = setInterval(fn, ms);
    return () => clearInterval(t);
  }, [fn, active, ms]);
}
