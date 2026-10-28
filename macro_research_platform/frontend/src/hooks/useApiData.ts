// Hook: GET an endpoint with loading / error state (the app's standard data fetch).
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
 * @param options.refreshMs - Optional silent re-poll interval (only while the tab is visible).
 *   Without it the data is fetched once per mount, so a live-market panel would sit on its
 *   page-load snapshot and (correctly) turn STALE.
 * @returns Object with data, loading, error, refetch
 *
 * @example
 * const { data, loading, error } = useApiData<RiskData>('/api/risk/full');
 */
export function useApiData<T>(
  endpoint: string,
  dependencies: any[] = [],
  options: { refreshMs?: number } = {}
): UseApiDataResult<T> {
  const refreshMs = options.refreshMs ?? 0;
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<Error | null>(null);
  const [refetchTrigger, setRefetchTrigger] = useState<number>(0);
  // One stable dependency instead of spreading a caller array (whose length may change
  // between renders, which React does not allow).
  const depKey = JSON.stringify(dependencies);

  useEffect(() => {
    let cancelled = false;
    let inflight: AbortController | null = null;
    let lastError: Error = new Error('Request failed');
    const timeoutMs = 12000;

    // One fetch attempt with a bounded timeout (Sweep 5 — no unbounded loading states): a hung
    // request always resolves rather than spinning forever. Returns true on success.
    const attempt = async (): Promise<boolean> => {
      const controller = new AbortController();
      inflight = controller;
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

    // Retries: a request that fails while the server is busy or restarting (timeout, network error, 5xx) backs off
    // 2 → 4 → 8 → 16 → 30 s, then keeps trying every 30 s in the background until it lands — so a panel heals itself
    // once the backend is back instead of staying "unavailable". A 4xx is final (it won't fix itself).
    let healer: ReturnType<typeof setInterval> | null = null;
    const final = () => /^HTTP 4\d\d/.test(lastError.message);
    const run = async () => {
      setLoading(true);
      setError(null);
      for (let k = 0; k < 6; k++) {
        if (await attempt()) return;
        if (cancelled || final()) break;
        await new Promise((r) => setTimeout(r, Math.min(30_000, 2000 * 2 ** k)));
        if (cancelled) return;
      }
      if (cancelled) return;
      setError(lastError); setLoading(false);
      if (!final()) healer = setInterval(async () => {
        if (document.visibilityState !== 'visible') return;
        if (await attempt()) { setError(null); if (healer) clearInterval(healer); healer = null; }
      }, 30_000);
    };

    run();

    // Background refresh: no loading flicker, and a failed poll keeps the last good data.
    const poll = refreshMs > 0
      ? setInterval(() => { if (document.visibilityState === 'visible') void attempt(); }, refreshMs)
      : null;

    return () => { cancelled = true; inflight?.abort(); if (poll) clearInterval(poll); if (healer) clearInterval(healer); };   // stop the request, not just ignore it
  }, [endpoint, refetchTrigger, depKey, refreshMs]);

  const refetch = () => {
    setRefetchTrigger(prev => prev + 1);
  };

  return { data, loading, error, refetch };
}
