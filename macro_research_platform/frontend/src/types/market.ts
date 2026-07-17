/**
 * Market data types (rates, FX, commodities, prices)
 */

// ── Market Rates ──────────────────────────────────────────────────────────────

export interface RateData {
  symbol: string;
  value: number;
  change: number;
  timestamp: string;
}

export interface YieldCurveData {
  tenYear: number;
  twoYear: number;
  spread: number;
  shape: 'steep' | 'flat' | 'inverted';
  fedFunds: number;
}

// ── FX Data ───────────────────────────────────────────────────────────────────

export interface FXData {
  pair: string;
  rate: number;
  change: number;
  trend: string;
}

export interface DXYData {
  value: number;
  change: number;
  components: Record<string, number>;
}

// ── Commodities ───────────────────────────────────────────────────────────────

export interface CommodityData {
  name: string;
  price: number;
  change: number;
  unit: string;
}

// ── Prices ─────────────────────────────────────────────────────────────────────

export interface PriceData {
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  volume?: number;
  timestamp: string;
}

export interface PriceChangeData {
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
}

// ── Unified Dashboard Response (Phase 1 Standardized) ─────────────────────────

export interface UnifiedDashboardResponse {
  prices: {
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
  };
  changes: Record<string, number | null>;
  regime: {
    current: string | null;
    confidence: number | null;
    duration: number | null;
    probabilities: {
      goldilocks: number | null;
      reflation: number | null;
      stagflation: number | null;
      slowdown: number | null;
    };
  };
  signals: {
    growth: {
      score: number | null;
      threeMonth: number | null;
      state: string | null;
    };
    inflation: {
      score: number | null;
      threeMonth: number | null;
      state: string | null;
    };
    liquidity: {
      score: number | null;
      threeMonth: number | null;
      state: string | null;
    };
    risk: {
      score: number | null;
      threeMonth: number | null;
      state: string | null;
    };
  };
  ensemble: {
    score: number | null;
    conviction: string | null;
    agreement: number | null;
    riskBudget: number | null;
  };
  meta: {
    latestDate: string | null;
    dataStatus: 'loading' | 'live' | 'stale' | 'error';
    lastUpdated: string | null;
  };
}
