import { useEffect, useState, useCallback, useRef } from "react";

export function usePolling<T>(
  fetcher: () => Promise<T>,
  intervalMs = 10_000,
  deps: unknown[] = []
): { data: T | null; error: string | null; loading: boolean; refresh: () => void } {
  const [data,    setData]    = useState<T | null>(null);
  const [error,   setError]   = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetch_ = useCallback(async () => {
    try {
      const result = await fetcher();
      setData(result);
      setError(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    fetch_();
    timerRef.current = setInterval(fetch_, intervalMs);
    return () => { if (timerRef.current) clearInterval(timerRef.current); };
  }, [fetch_, intervalMs]);

  return { data, error, loading, refresh: fetch_ };
}
