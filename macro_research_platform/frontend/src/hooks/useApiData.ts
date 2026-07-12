import { useState, useEffect } from 'react';

interface UseApiDataResult<T> {
  data: T | null;
  loading: boolean;
  error: Error | null;
  refetch: () => void;
}

/**
 * Reusable hook for fetching API data with loading/error states.
 *
 * Replaces direct fetch() calls in components.
 *
 * @param endpoint - API endpoint (e.g., '/api/risk/full')
 * @param dependencies - Re-fetch when these change
 * @returns Object with data, loading, error, refetch
 *
 * @example
 * const { data, loading, error } = useApiData<RiskData>('/api/risk/full');
 */
export function useApiData<T>(
  endpoint: string,
  dependencies: any[] = []
): UseApiDataResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);
  const [refetchTrigger, setRefetchTrigger] = useState<number>(0);

  useEffect(() => {
    let cancelled = false;
    let lastError: Error = new Error('Request failed');
    const timeoutMs = 12000;

    // One fetch attempt with a bounded timeout (Sweep 5 — no unbounded loading states): a hung
    // request always resolves rather than spinning forever. Returns true on success.
    const attempt = async (): Promise<boolean> => {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), timeoutMs);
      try {
        const response = await fetch(endpoint, { signal: controller.signal });
        clearTimeout(timer);
        if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        const json = await response.json();
        if (!cancelled) { setData(json); setLoading(false); }
        return true;
      } catch (err) {
        clearTimeout(timer);
        if (cancelled) return true;  // unmounted — stop, don't touch state
        const isAbort = err instanceof DOMException && err.name === 'AbortError';
        lastError = isAbort ? new Error(`Request timed out after ${timeoutMs / 1000}s`)
                            : (err instanceof Error ? err : new Error(String(err)));
        return false;
      }
    };

    const run = async () => {
      setLoading(true);
      setError(null);
      if (await attempt()) return;                    // succeeded first try
      if (cancelled) return;
      await new Promise((r) => setTimeout(r, 1500));  // one self-heal retry (matches panel pattern)
      if (cancelled) return;
      if (await attempt()) return;
      if (!cancelled) { setError(lastError); setLoading(false); }
    };

    run();

    return () => { cancelled = true; };
  }, [endpoint, refetchTrigger, ...dependencies]);

  const refetch = () => {
    setRefetchTrigger(prev => prev + 1);
  };

  return { data, loading, error, refetch };
}
