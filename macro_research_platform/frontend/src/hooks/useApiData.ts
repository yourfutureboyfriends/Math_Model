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

    const fetchData = async () => {
      setLoading(true);
      setError(null);

      try {
        const response = await fetch(endpoint);

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const json = await response.json();

        if (!cancelled) {
          setData(json);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err : new Error(String(err)));
          setLoading(false);
        }
      }
    };

    fetchData();

    return () => {
      cancelled = true;
    };
  }, [endpoint, refetchTrigger, ...dependencies]);

  const refetch = () => {
    setRefetchTrigger(prev => prev + 1);
  };

  return { data, loading, error, refetch };
}
