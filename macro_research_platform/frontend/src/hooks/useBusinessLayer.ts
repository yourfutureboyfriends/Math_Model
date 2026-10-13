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

// NOTE: useExpectedReturns / usePositionSizing were removed — they had zero consumers
// (BusinessLayerSection reads expected returns from /api/business/recommendations).
