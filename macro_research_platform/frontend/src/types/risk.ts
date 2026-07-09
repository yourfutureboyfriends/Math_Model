/**
 * Risk, recession, and analytics types
 */

// ── Risk Indicators ────────────────────────────────────────────────────────────

export interface RiskIndicatorsData {
  indicators: RiskIndicator[];
  compositeScore: number;
  regime: string;
}

export interface RiskIndicator {
  name: string;
  value: string;
  level: 'low' | 'medium' | 'high' | 'extreme';
  interpretation: string;
}

// ── Recession ─────────────────────────────────────────────────────────────────

export interface RecessionData {
  probability: number;
  level: string;
  logisticProb: number;
  emProbitProb: number;
  sahmValue: number;
  sahmSignal: string;
  description: string;
}

export interface AdvancedIndicator {
  name: string;
  value: string;
  status: string;
  trend: string;
  description: string;
}

export interface AdvancedIndicatorsData {
  sahmRule: AdvancedIndicator;
  creditImpulse: AdvancedIndicator;
  leiComposite: AdvancedIndicator;
  riskParity: AdvancedIndicator;
}

// ── Portfolio Analytics ────────────────────────────────────────────────────────

export interface PortfolioHolding {
  asset: string;
  ticker: string;
  currentWeight: number;
  targetWeight: number;
  drift: number;
  pnl: number;
  regimeAlignment: 'aligned' | 'neutral' | 'contrarian';
}

export interface PortfolioAnalytics {
  holdings: PortfolioHolding[];
  totalValue: number;
  dayPnl: number;
  totalReturn: number;
  volatility: number;
  sharpe: number;
  maxDrawdown: number;
  beta: number;
  correlationToBenchmark: number;
  sectorExposure: Record<string, number>;
  factorExposure: Record<string, number>;
}

export interface PortfolioSimulationMetrics {
  totalReturn: number;
  annReturn: number;
  sharpe: number;
  maxDrawdown: number;
  winRate: number | null;
}

export interface PortfolioSimulationHolding {
  etf: string;
  signal: string;
  weight: number;
  pnlPct: number;
  entryDate: string;
}

export interface PortfolioSimulationData {
  inceptionDate: string;
  benchmark: string;
  metrics: {
    terminal: PortfolioSimulationMetrics;
    benchmark6040: PortfolioSimulationMetrics;
    spy: PortfolioSimulationMetrics;
  };
  holdings: PortfolioSimulationHolding[];
  monthsTracked: number;
  monthlyReturns: number[];
  benchmarkReturns: number[];
  lastUpdated: string;
}

// ── Alerts ────────────────────────────────────────────────────────────────────

export interface AlertItem {
  id: string;
  severity: 'critical' | 'warning' | 'info';
  triggered: boolean;
  triggeredAt?: string;
  message: string;
  action: string;
  currentValue: number | string;
  threshold: number | string;
  acknowledged: boolean;
}

export interface AlertsData {
  active: AlertItem[];
  count: {
    critical: number;
    warning: number;
    info: number;
  };
  lastEvaluated: string;
}

// ── Trade Ideas ─────────────────────────────────────────────────────────────────

export interface TradeIdea {
  id: number | string;
  ticker: string;
  direction: 'LONG' | 'SHORT';
  thesis: string;
  entry?: number | null;
  target?: number | null;
  stop?: number | null;
  rr?: number;
  kelly_size?: number;
  suggested_size?: number;
  position_size_pct?: number;
  horizon_days: number;
  conviction: 'HIGH' | 'MEDIUM' | 'LOW';
  category: string;
  regime_valid: boolean;
  regime_current: string;
  status: 'ACTIVE' | 'REVIEW';
  days_open: number;
  pnl_pct: number;
  exit_conditions: string[];
}

export interface TradeIdeasData {
  ideas?: TradeIdea[];
  regime?: string;
  total_ideas?: number;
  generated_at?: string;
  risk_budget?: number;
}

// ── Trade Recommendations (Dynamic Engine) ───────────────────────────────────────

export interface TradeComponentScores {
  regime_alignment: number;
  factor_alignment: number;
  momentum: number;
  fundamental: number;
  macro: number;
  analyst: number;
}

export interface TradeRecommendation {
  ticker: string;
  name: string;
  asset_class: string;
  sector: string;
  factor: string;
  composite_score: number;
  confidence: number;
  component_scores: TradeComponentScores;
  kelly_pct: number;
  position_pct?: number;
  market_cap: number;
  avg_volume: number;
  last_price: number;
  pe?: number;
  div_yield?: number;
  beta?: number;
}

export interface PairTrade {
  long_ticker: string;
  long_name: string;
  short_ticker: string;
  short_name: string;
  sector: string;
  regime: string;
  long_score: number;
  short_score: number;
  net_score: number;
  long_position: number;
  short_position: number;
}

export interface TradeRecommendationsSummary {
  total_scored: number;
  qualified_count: number;
  long_count: number;
  short_count: number;
  avg_confidence: number;
  avg_long_score: number;
  avg_short_score: number;
  pair_trade_count: number;
}

export interface TradeRecommendationsData {
  regime: string;
  macro_score: number;
  generated_at: string;
  longs: TradeRecommendation[];
  shorts: TradeRecommendation[];
  pair_trades: PairTrade[];
  summary: TradeRecommendationsSummary;
  duration_seconds?: number;
}
