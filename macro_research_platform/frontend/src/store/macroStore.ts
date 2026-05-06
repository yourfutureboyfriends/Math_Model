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
}

interface Meta {
  latestDate: string | null;
  dataStatus: 'loading' | 'live' | 'stale' | 'error';
  lastUpdated: string | null;
}

interface MacroState {
  // Data
  prices: Prices;
  changes: Changes;
  regime: Regime;
  signals: Signals;
  ensemble: Ensemble;
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
const MAX_RECONNECT_ATTEMPTS = 5;
const RECONNECT_DELAY = 5000; // 5 seconds

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
    },
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

      try {
        // Try new unified endpoint first
        const res = await fetch('/api/v2/dashboard');

        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`);
        }

        const data = await res.json();

        set({
          prices: data.prices || { ...defaultPrices },
          changes: data.changes || {},
          regime: data.regime || get().regime,
          signals: data.signals || get().signals,
          ensemble: data.ensemble || get().ensemble,
          meta: {
            latestDate: data.meta?.latestDate || null,
            dataStatus: 'live',
            lastUpdated: data.meta?.lastUpdated || new Date().toISOString(),
          },
        });

        console.log('[MacroStore] Dashboard fetched successfully');
      } catch (e) {
        console.error('[MacroStore] Dashboard fetch failed:', e);
        set({
          meta: { ...get().meta, dataStatus: 'error' },
          wsError: e instanceof Error ? e.message : 'Unknown error',
        });
      }
    },

    // Start WebSocket for live price updates
    startWebSocket: () => {
      // Prevent multiple connections
      if (ws?.readyState === WebSocket.OPEN) {
        console.log('[MacroStore] WebSocket already connected');
        return;
      }

      // Stop any existing connection first
      get().stopWebSocket();

      const connect = () => {
        try {
          const wsUrl = `ws://${window.location.host}/ws/prices`;
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

              // Handle price updates
              if (update.prices) {
                set({
                  prices: { ...get().prices, ...update.prices },
                });
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

          ws.onclose = () => {
            console.log('[MacroStore] WebSocket disconnected');
            set({
              wsConnected: false,
              meta: { ...get().meta, dataStatus: 'stale' },
            });

            // Auto-reconnect with backoff
            if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
              reconnectAttempts++;
              console.log(`[MacroStore] Reconnecting in ${RECONNECT_DELAY}ms (attempt ${reconnectAttempts})`);
              reconnectTimeout = setTimeout(connect, RECONNECT_DELAY);
            } else {
              console.error('[MacroStore] Max reconnect attempts reached');
              set({ wsError: 'WebSocket connection failed after retries' });
            }
          };

          ws.onerror = (error) => {
            console.error('[MacroStore] WebSocket error:', error);
            set({ wsError: 'WebSocket connection error' });
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
export const selectPrices = (state: MacroState) => state.prices;
export const selectRegime = (state: MacroState) => state.regime;
export const selectSignals = (state: MacroState) => state.signals;
export const selectEnsemble = (state: MacroState) => state.ensemble;
export const selectMeta = (state: MacroState) => state.meta;
export const selectDataStatus = (state: MacroState) => state.meta.dataStatus;
export const selectIsLoading = (state: MacroState) => state.meta.dataStatus === 'loading';
export const selectIsLive = (state: MacroState) => state.meta.dataStatus === 'live';
export const selectWsConnected = (state: MacroState) => state.wsConnected;
