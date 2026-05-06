// Business Layer Hook — Phase 3D
// Fetches business outputs: recommendations, decision log, IC pack, expected returns

import { useState, useEffect, useCallback } from 'react';

interface Recommendation {
  asset_class: string;
  expected_return_score: number;
  rationale: string;
  conviction: string;
}

interface PositionSizing {
  asset_class: string;
  recommended_weight: number;
  min_weight: number;
  max_weight: number;
  rationale: string;
}

interface DecisionLogEntry {
  date: string;
  action: string;
  asset: string;
  rationale: string;
  outcome?: string;
}

interface BusinessRecommendations {
  summary: string | null;
  expected_returns: Recommendation[];
  position_sizing: PositionSizing[];
  signal_scorecard: unknown[];
  timestamp: string;
}

interface DecisionLog {
  entries: DecisionLogEntry[];
  total: number;
  timestamp: string;
}

interface ICPack {
  content: string | null;
  filename: string | null;
  generated: number | null;
  timestamp: string;
}

interface BusinessState {
  recommendations: BusinessRecommendations | null;
  decisionLog: DecisionLog | null;
  icPack: ICPack | null;
  loading: boolean;
  error: string | null;
}

export function useBusinessLayer() {
  const [state, setState] = useState<BusinessState>({
    recommendations: null,
    decisionLog: null,
    icPack: null,
    loading: true,
    error: null,
  });

  const fetchBusinessData = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));

    try {
      // Fetch all business endpoints in parallel
      const [recRes, logRes, icRes] = await Promise.all([
        fetch('/api/business/recommendations'),
        fetch('/api/business/decision-log'),
        fetch('/api/business/ic-pack'),
      ]);

      const [recommendations, decisionLog, icPack] = await Promise.all([
        recRes.ok ? recRes.json() : null,
        logRes.ok ? logRes.json() : null,
        icRes.ok ? icRes.json() : null,
      ]);

      setState({
        recommendations,
        decisionLog,
        icPack,
        loading: false,
        error: null,
      });
    } catch (e) {
      setState(prev => ({
        ...prev,
        loading: false,
        error: e instanceof Error ? e.message : 'Failed to load business data',
      }));
    }
  }, []);

  useEffect(() => {
    fetchBusinessData();

    // Refresh every 5 minutes
    const interval = setInterval(fetchBusinessData, 300000);
    return () => clearInterval(interval);
  }, [fetchBusinessData]);

  return {
    ...state,
    refresh: fetchBusinessData,
  };
}

// Hook for expected returns only
export function useExpectedReturns() {
  const [returns, setReturns] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchReturns = async () => {
      try {
        const res = await fetch('/api/business/expected-returns');
        if (res.ok) {
          const data = await res.json();
          setReturns(data.returns || []);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load');
      } finally {
        setLoading(false);
      }
    };

    fetchReturns();
  }, []);

  return { returns, loading, error };
}

// Hook for position sizing only
export function usePositionSizing() {
  const [positions, setPositions] = useState<PositionSizing[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const fetchSizing = async () => {
      try {
        const res = await fetch('/api/business/position-sizing');
        if (res.ok) {
          const data = await res.json();
          setPositions(data.positions || []);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to load');
      } finally {
        setLoading(false);
      }
    };

    fetchSizing();
  }, []);

  return { positions, loading, error };
}
