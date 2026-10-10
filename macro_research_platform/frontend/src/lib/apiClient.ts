/**
 * Typed API client with runtime validation
 * Simplified version using only schemas that exist in OpenAPI spec
 */

import type { components } from '@/types/api-generated';
import {
  validateAndNormalizeDashboard,
  validateSignalsData,
  validateRecessionData,
  ValidationError
} from './apiValidation';

// Type aliases for easier use
export type DashboardData = components['schemas']['DashboardData'];
export type SignalsData = components['schemas']['SignalsData'];
export type RecessionData = components['schemas']['RecessionData'];
export type RegimeData = components['schemas']['RegimeData'];
export type AlertsData = components['schemas']['AlertsData'];
export type BusinessLayerData = components['schemas']['BusinessLayerData'];
export type MorningBriefData = Record<string, unknown>; // schema not yet generated from backend
export type SignalStackData = components['schemas']['SignalStackData'];
export type TradeIdeasResponse = components['schemas']['TradeIdeasResponse'];

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

/**
 * Get full URL for an endpoint
 */
export function getEndpointUrl(path: string): string {
  return `${API_BASE_URL}${path}`;
}

/**
 * Handle API response
 */
async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  return response.json() as Promise<T>;
}

/**
 * Typed API client for all backend endpoints
 */
export const api = {
  /**
   * Dashboard endpoints
   */
  dashboard: {
    get: async (mode: 'live' | 'sample' = 'live'): Promise<DashboardData> => {
      const response = await fetch(getEndpointUrl(`/api/dashboard?mode=${mode}`));
      const raw = await handleResponse<DashboardData>(response);

      // Validate and normalize
      try {
        return validateAndNormalizeDashboard(raw);
      } catch (error) {
        if (error instanceof ValidationError) {
          console.error('[API] Validation error:', error.message, {
            field: error.field,
            value: error.value
          });
        }
        throw error;
      }
    }
  },

  /**
   * Signal endpoints
   */
  signals: {
    get: async (): Promise<SignalsData> => {
      const response = await fetch(getEndpointUrl('/api/signals'));
      const raw = await handleResponse<SignalsData>(response);

      try {
        validateSignalsData(raw);
        return raw;
      } catch (error) {
        console.error('[API] Signals validation error:', error);
        throw error;
      }
    },
    getStack: async (): Promise<SignalStackData> => {
      const response = await fetch(getEndpointUrl('/api/signal-stack'));
      return handleResponse<SignalStackData>(response);
    }
  },

  /**
   * Risk endpoints
   */
  risk: {
    getRecession: async (): Promise<RecessionData> => {
      const response = await fetch(getEndpointUrl('/api/recession'));
      const raw = await handleResponse<RecessionData>(response);

      try {
        validateRecessionData(raw);
        return raw;
      } catch (error) {
        console.error('[API] Recession validation error:', error);
        throw error;
      }
    },

    getAlerts: async (): Promise<AlertsData> => {
      const response = await fetch(getEndpointUrl('/api/alerts'));
      return handleResponse<AlertsData>(response);
    }
  },

  /**
   * Business endpoints
   */
  business: {
    getRecommendations: async (): Promise<BusinessLayerData> => {
      const response = await fetch(getEndpointUrl('/api/business/recommendations'));
      return handleResponse<BusinessLayerData>(response);
    },
    getMorningBrief: async (): Promise<MorningBriefData> => {
      const response = await fetch(getEndpointUrl('/api/morning-brief'));
      return handleResponse<MorningBriefData>(response);
    },
    getTradeIdeas: async (): Promise<TradeIdeasResponse> => {
      const response = await fetch(getEndpointUrl('/api/trade-ideas'));
      return handleResponse<TradeIdeasResponse>(response);
    }
  },

  /**
   * Health check
   */
  health: async (): Promise<{ status: string }> => {
    const response = await fetch(getEndpointUrl('/api/health'));
    return handleResponse<{ status: string }>(response);
  }
};

export type API = typeof api;
