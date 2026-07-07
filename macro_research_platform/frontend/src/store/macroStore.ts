/**
 * Macro Store — Single Source of Truth for All Frontend Data
 *
 * Rules:
 * - This is the ONLY place that fetches market data
 * - All components read from this store (no direct fetch())
 * - WebSocket connection managed here (single connection)
 * - All values stored in natural units (rates as decimals, not bps)
 */

import { create } from 'zustand';
import { subscribeWithSelector } from 'zustand/middleware';
import { getWebSocketUrl } from '@/lib/network';
import { api, type DashboardData } from '@/lib/apiClient';
import type { DashboardData as FullDashboardData } from '@/types';

// Types
interface Prices {
  SPX: number | null;
  NDX: number | null;
  VIX: number | null;
  TENYR: number | null;
  TWYR: number | null;
  FED: number | null;
  DXY: number | null;
  EURUSD: number | null;
  GBPUSD: number | null;
  USDJPY: number | null;
  USDCAD: number | null;
  USDCHF: number | null;
  AUDUSD: number | null;
  NZDUSD: number | null;
  GLD: number | null;
  WTI: number | null;
}

interface Changes {
  [key: string]: number | null;
}

interface Regime {
  current: string | null;
  confidence: number | null;
  duration: number | null;
  probabilities: {
    goldilocks: number | null;
    reflation: number | null;
    stagflation: number | null;
    slowdown: number | null;
  };
}

interface Signal {
  score: number | null;
  threeMonth: number | null;
  state: string | null;
}

interface Signals {
  growth: Signal;
  inflation: Signal;
  liquidity: Signal;
  risk: Signal;
}

interface Ensemble {
  score: number | null;
  conviction: string | null;
  agreement: number | null;
  riskBudget: number | null;
  mode: string | null;
}

interface Meta {
  latestDate: string | null;
  dataStatus: 'loading' | 'live' | 'stale' | 'error';
  lastUpdated: string | null;
}

interface CorrelationRegime {
  currentRegime: string | null;
  switchTriggered: boolean;
  equityBondCorrelation: number | null;
  fallbackStrategy: string | null;
  correlations: Array<{
    assetPair: string;
    correlation60d: number;
    regime: string;
    interpretation: string;
  }>;
  riskParityAdjustment: {
    normalWeights: Record<string, number>;
    adjustedWeights: Record<string, number>;
    rationale: string;
  };
}

interface MomentumVeto {
  vetoActive: boolean;
  dampenerApplied: number;
  assets: Array<{
    asset: string;
    return12m: number;
    return1m: number;
    momentum12_1: number;
    dampenedSignal: number;
    rawSignal: string;
    interpretation: string;
  }>;
  portfolioAdjustment: {
    action: string;
    magnitude: number;
    rationale: string;
  };
}

interface SignalStackLayer {
  layer: string;
  priority: number;
  signal: string;
  conviction: number;
  override: string | null;
}

interface SignalStack {
  layers: SignalStackLayer[];
  finalSignal: string;
  confidence: number;
  timestamp: string;
}

interface MacroState {
  // Data
  prices: Prices;
  changes: Changes;
  regime: Regime;
  signals: Signals;
  ensemble: Ensemble;
  correlationRegime: CorrelationRegime | null;
  momentumVeto: MomentumVeto | null;
  signalStack: SignalStack | null;
  fullDashboard: FullDashboardData | null;  // Complete raw dashboard response
  meta: Meta;

  // WebSocket
  wsConnected: boolean;
  wsError: string | null;

  // Actions
  fetchDashboard: () => Promise<void>;
  startWebSocket: () => void;
  stopWebSocket: () => void;
  reconnectWebSocket: () => void;

  // Getters
  getPrice: (symbol: keyof Prices) => number | null;
  getChange: (symbol: string) => number | null;
}

// Default state
const defaultPrices: Prices = {
  SPX: null,
  NDX: null,
  VIX: null,
  TENYR: null,
  TWYR: null,
  FED: null,
  DXY: null,
  EURUSD: null,
  GBPUSD: null,
  USDJPY: null,
  USDCAD: null,
  USDCHF: null,
  AUDUSD: null,
  NZDUSD: null,
  GLD: null,
  WTI: null,
};

const defaultSignal: Signal = {
  score: null,
  threeMonth: null,
  state: null,
};

// WebSocket instance (singleton)
let ws: WebSocket | null = null;
let reconnectTimeout: NodeJS.Timeout | null = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 10;
const INITIAL_RECONNECT_DELAY = 1000; // 1 second
const MAX_RECONNECT_DELAY = 30000; // 30 seconds

// Calculate exponential backoff delay
function getReconnectDelay(): number {
  const delay = INITIAL_RECONNECT_DELAY * Math.pow(2, reconnectAttempts);
  return Math.min(delay, MAX_RECONNECT_DELAY);
}

export const useMacroStore = create<MacroState>()(
  subscribeWithSelector((set, get) => ({
    // Initial state
    prices: { ...defaultPrices },
    changes: {},
    regime: {
      current: null,
      confidence: null,
      duration: null,
      probabilities: {
        goldilocks: null,
        reflation: null,
        stagflation: null,
        slowdown: null,
      },
    },
    signals: {
      growth: { ...defaultSignal },
      inflation: { ...defaultSignal },
      liquidity: { ...defaultSignal },
      risk: { ...defaultSignal },
    },
    ensemble: {
      score: null,
      conviction: null,
      agreement: null,
      riskBudget: null,
      mode: null,
    },
    correlationRegime: null,
    momentumVeto: null,
    signalStack: null,
    fullDashboard: null,
    meta: {
      latestDate: null,
      dataStatus: 'loading',
      lastUpdated: null,
    },
    wsConnected: false,
    wsError: null,

    // Fetch dashboard data from REST API
    fetchDashboard: async () => {
      set({
        meta: { ...get().meta, dataStatus: 'loading' },
        wsError: null,
      });

      // 8-second hard timeout — prevent infinite loading
      const timeoutId = setTimeout(() => {
        if (get().meta.dataStatus === 'loading') {
          console.warn('[MacroStore] Dashboard fetch timed out after 8s');
          set({
            meta: { ...get().meta, dataStatus: 'error' },
            wsError: 'Data unavailable — service did not respond in time',
          });
        }
      }, 8000);

      try {
        // Use typed API client with validation
        console.log('[MacroStore] Fetching dashboard...');
        const data: DashboardData = await api.dashboard.get('live');
        clearTimeout(timeoutId);

        // Transform validated DashboardData to store format
        set({
          // Extract prices from keyMetrics (if available)
          prices: {
            SPX: data.keyMetrics?.spxLevel ?? get().prices.SPX,
            NDX: data.keyMetrics?.ndxLevel ?? get().prices.NDX,
            VIX: data.keyMetrics?.vix ?? get().prices.VIX,
            TENYR: data.keyMetrics?.tenYearYield ?? get().prices.TENYR,
            TWYR: data.keyMetrics?.twoYearYield ?? get().prices.TWYR,
            FED: data.keyMetrics?.fedRate ?? get().prices.FED,
            DXY: data.keyMetrics?.dxy ?? get().prices.DXY,
            EURUSD: data.keyMetrics?.eurusd ?? get().prices.EURUSD,
            GBPUSD: get().prices.GBPUSD,
            USDJPY: get().prices.USDJPY,
            USDCAD: get().prices.USDCAD,
            USDCHF: get().prices.USDCHF,
            AUDUSD: get().prices.AUDUSD,
            NZDUSD: get().prices.NZDUSD,
            GLD: data.keyMetrics?.gold ?? get().prices.GLD,
            WTI: data.keyMetrics?.oil ?? get().prices.WTI,
          },
          // Extract changes from keyMetrics
          changes: {
            ...get().changes,
            SPX: data.keyMetrics?.spxChangePct ?? get().changes.SPX,
            NDX: data.keyMetrics?.ndxChangePct ?? get().changes.NDX,
            VIX: data.keyMetrics?.vixChange ?? get().changes.VIX,
            DXY: data.keyMetrics?.dxyChangePct ?? get().changes.DXY,
            EURUSD: data.keyMetrics?.eurusdChangePct ?? get().changes.EURUSD,
          },
          regime: {
            current: data.regime.current || null,
            confidence: data.regime.confidenceScore || null,
            duration: data.regime.duration || null,
            probabilities: get().regime.probabilities, // Keep existing
          },
          // Ensemble data IS part of the dashboard response — map it so the Morning
          // Brief signal bar reflects live score/agreement/conviction/mode instead of
          // showing Neutral / 0% / Static defaults.
          ensemble: data.ensemble ? {
            score: (data.ensemble as any).score ?? null,
            conviction: (data.ensemble as any).conviction ?? null,
            agreement: (data.ensemble as any).agreement ?? null,
            riskBudget: (data.ensemble as any).riskBudget ?? null,
            mode: (data.ensemble as any).mode ?? null,
          } : get().ensemble,
          // Correlation regime data from dashboard
          correlationRegime: (data.correlationRegime as CorrelationRegime) || null,
          // Momentum veto data from dashboard
          momentumVeto: (data.momentumVeto as MomentumVeto) || null,
          // Signal stack data from dashboard
          signalStack: data.signalStack ? {
            ...data.signalStack,
            layers: ((data.signalStack.layers || []) as any[]).map((l: any) => ({
              ...l,
              override: l.override ?? null,
            })) as SignalStackLayer[],
          } as SignalStack : null,
          // Read from new field names (latestScore, threeMonthChange) with fallback to legacy
          // Parse threeMonthChange string (e.g., "+0.2") to number
          signals: data.signals ? {
            growth: {
              score: data.signals.growth?.latestScore ?? data.signals.growth?.score ?? null,
              threeMonth: parseFloat(String(data.signals.growth?.threeMonthChange ?? data.signals.growth?.threeMonth ?? '0').replace('+', '')) || null,
              state: data.signals.growth?.state || null,
            },
            inflation: {
              score: data.signals.inflation?.latestScore ?? data.signals.inflation?.score ?? null,
              threeMonth: parseFloat(String(data.signals.inflation?.threeMonthChange ?? data.signals.inflation?.threeMonth ?? '0').replace('+', '')) || null,
              state: data.signals.inflation?.state || null,
            },
            liquidity: {
              score: data.signals.liquidity?.latestScore ?? data.signals.liquidity?.score ?? null,
              threeMonth: parseFloat(String(data.signals.liquidity?.threeMonthChange ?? data.signals.liquidity?.threeMonth ?? '0').replace('+', '')) || null,
              state: data.signals.liquidity?.state || null,
            },
            risk: {
              score: data.signals.risk?.latestScore ?? data.signals.risk?.score ?? null,
              threeMonth: parseFloat(String(data.signals.risk?.threeMonthChange ?? data.signals.risk?.threeMonth ?? '0').replace('+', '')) || null,
              state: data.signals.risk?.state || null,
            },
          } : get().signals,
          fullDashboard: data as unknown as FullDashboardData,
          meta: {
            latestDate: data.metadata?.latestDate || null,
            dataStatus: 'live',
            lastUpdated: data.metadata?.lastRefreshed || new Date().toISOString(),
          },
        });

        console.log('[MacroStore] Dashboard fetched and validated successfully');
      } catch (e) {
        clearTimeout(timeoutId);
        console.error('[MacroStore] Dashboard fetch failed:', e);
        set({
          meta: { ...get().meta, dataStatus: 'error' },
          wsError: e instanceof Error ? e.message : 'Unknown error',
        });
      }
    },

    // Start WebSocket for live price updates
    startWebSocket: () => {
      // Prevent multiple connections or if already connecting
      if (ws?.readyState === WebSocket.OPEN) {
        console.log('[MacroStore] WebSocket already connected');
        return;
      }
      if (ws?.readyState === WebSocket.CONNECTING) {
        console.log('[MacroStore] WebSocket already connecting');
        return;
      }

      // Stop any existing connection first
      get().stopWebSocket();

      const connect = () => {
        try {
          const wsUrl = getWebSocketUrl('/ws/prices');
          console.log('[MacroStore] Connecting WebSocket:', wsUrl);

          ws = new WebSocket(wsUrl);

          ws.onopen = () => {
            console.log('[MacroStore] WebSocket connected');
            reconnectAttempts = 0;
            set({
              wsConnected: true,
              wsError: null,
              meta: { ...get().meta, dataStatus: 'live' },
            });
          };

          ws.onmessage = (event) => {
            try {
              const update = JSON.parse(event.data);
              console.log('[MacroStore] WebSocket message:', update.type || 'unknown');

              // Handle price updates
              if (update.prices || update.data) {
                set({
                  prices: { ...get().prices, ...(update.prices || update.data) },
                });
              }

              // Handle heartbeat
              if (update.type === 'heartbeat') {
                // Connection is alive, no action needed
                console.log('[MacroStore] WebSocket heartbeat received');
              }

              // Handle regime changes
              if (update.regime) {
                set({
                  regime: { ...get().regime, ...update.regime },
                });
              }

              // Handle signal updates
              if (update.signals) {
                set({
                  signals: { ...get().signals, ...update.signals },
                });
              }
            } catch (e) {
              console.error('[MacroStore] WebSocket message parse error:', e);
            }
          };

          ws.onclose = (event) => {
            console.log('[MacroStore] WebSocket disconnected:', {
              code: event.code,
              reason: event.reason,
              wasClean: event.wasClean,
            });

            // Don't update state if we're intentionally closing
            if (ws === null) return;

            set({
              wsConnected: false,
              meta: { ...get().meta, dataStatus: 'stale' },
            });

            // Auto-reconnect with exponential backoff
            if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
              reconnectAttempts++;
              const delay = getReconnectDelay();
              console.log(`[MacroStore] Reconnecting in ${delay}ms (attempt ${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})`);
              reconnectTimeout = setTimeout(connect, delay);
            } else {
              console.error('[MacroStore] Max reconnect attempts reached, giving up');
              set({ wsError: 'WebSocket unavailable - using REST fallback' });
            }
          };

          ws.onerror = (error) => {
            // A transient socket error (e.g. the backend restarting) is expected and is
            // handled by onclose's reconnect/backoff, so log at debug level to avoid
            // alarming red console errors during normal reconnect cycles. A genuine
            // give-up is surfaced as an error by the onclose handler.
            console.debug('[MacroStore] WebSocket transient error (will reconnect):', error);
          };
        } catch (e) {
          console.error('[MacroStore] WebSocket setup error:', e);
          set({ wsError: e instanceof Error ? e.message : 'Setup error' });
        }
      };

      connect();
    },

    // Stop WebSocket connection
    stopWebSocket: () => {
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
      }

      if (ws) {
        ws.close();
        ws = null;
      }

      reconnectAttempts = 0;
      set({ wsConnected: false });
    },

    // Manually reconnect WebSocket
    reconnectWebSocket: () => {
      reconnectAttempts = 0;
      get().stopWebSocket();
      get().startWebSocket();
    },

    // Get price for a symbol
    getPrice: (symbol: keyof Prices) => {
      return get().prices[symbol];
    },

    // Get change for a symbol
    getChange: (symbol: string) => {
      return get().changes[symbol] ?? null;
    },
  }))
);

// Export selector helpers for common data access
export const selectFullDashboard = (state: MacroState) => state.fullDashboard;
export const selectPrices = (state: MacroState) => state.prices;
export const selectRegime = (state: MacroState) => state.regime;
export const selectSignals = (state: MacroState) => state.signals;
export const selectEnsemble = (state: MacroState) => state.ensemble;
export const selectMeta = (state: MacroState) => state.meta;
export const selectDataStatus = (state: MacroState) => state.meta.dataStatus;
export const selectIsLoading = (state: MacroState) => state.meta.dataStatus === 'loading';
export const selectIsLive = (state: MacroState) => state.meta.dataStatus === 'live';
export const selectWsConnected = (state: MacroState) => state.wsConnected;
