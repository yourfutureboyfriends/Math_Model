// Business Layer Hook — Phase 3D
// Fetches business outputs: recommendations, decision log, IC pack, expected returns

import { useState, useEffect, useCallback } from 'react';
import type { BackendRecommendationsResponse } from '@/lib/businessAdapter';

// Re-export backend types for components that need them
export type { BackendRecommendationsResponse };

interface DecisionLogEntry {
  date: string;
  action: string;
  asset: string;
  rationale: string;
  outcome?: string;
}

// Use backend types directly to ensure compatibility
interface BusinessRecommendations extends BackendRecommendationsResponse {}

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

interface ExpectedReturnItem {
  asset_class: string;
  expected_return_score: number;
  conviction?: string;
  rationale?: string;
}

// Hook for expected returns only
export function useExpectedReturns() {
  const [returns, setReturns] = useState<ExpectedReturnItem[]>([]);
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

interface PositionSizingItem {
  asset_class: string;
  recommended_weight: number;
  min_weight?: number;
  max_weight?: number;
  conviction?: string;
}

// Hook for position sizing only
export function usePositionSizing() {
  const [positions, setPositions] = useState<PositionSizingItem[]>([]);
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
