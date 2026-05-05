// Schema Adapters — Phase 2 Frontend Schema-Driven Rendering
// Converts API responses to safe, typed structures with null guards

import type { PriceData } from '@/hooks/useMarketStream';

// =============================================================================
// Safe Type Guards
// =============================================================================

export function isNonNull<T>(value: T | null | undefined): value is T {
  return value !== null && value !== undefined;
}

export function isNonEmptyArray<T>(value: T[] | null | undefined): value is T[] {
  return Array.isArray(value) && value.length > 0;
}

export function safeNumber(value: unknown, defaultValue = 0): number {
  if (typeof value !== 'number') return defaultValue;
  if (isNaN(value) || !isFinite(value)) return defaultValue;
  return value;
}

export function safeString(value: unknown, defaultValue = ''): string {
  if (typeof value !== 'string') return defaultValue;
  return value;
}

export function safeArray<T>(value: unknown, defaultValue: T[] = []): T[] {
  if (!Array.isArray(value)) return defaultValue;
  return value.filter(isNonNull);
}

export function safeObject<T extends Record<string, unknown>>(
  value: unknown,
  defaultValue: T = {} as T
): T {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return defaultValue;
  }
  return value as T;
}

// =============================================================================
// Price Data Adapter
// =============================================================================

export interface SafePriceData {
  symbol: string;
  price: number;
  prevPrice: number;
  change: number;
  pctChange: number;
  timestamp: string;
  assetClass: string;
  name: string;
  localTimestamp: Date | null;
  direction: 'up' | 'down' | 'unchanged';
}

export function adaptPriceData(data: unknown): SafePriceData | null {
  if (!data || typeof data !== 'object') return null;

  const d = data as Partial<PriceData>;

  const price = safeNumber(d.price);
  const prevPrice = safeNumber(d.prev_price ?? d.price);
  const change = safeNumber(d.change);
  const pctChange = safeNumber(d.pct_change);

  // Determine direction
  let direction: 'up' | 'down' | 'unchanged' = 'unchanged';
  if (price > prevPrice) direction = 'up';
  else if (price < prevPrice) direction = 'down';

  return {
    symbol: safeString(d.symbol, 'UNKNOWN'),
    price,
    prevPrice,
    change,
    pctChange,
    timestamp: safeString(d.timestamp),
    assetClass: safeString(d.asset_class, 'unknown'),
    name: safeString(d.name, 'Unknown'),
    localTimestamp: d.localTimestamp instanceof Date ? d.localTimestamp : null,
    direction,
  };
}

export function adaptPriceDataList(data: unknown[]): SafePriceData[] {
  if (!Array.isArray(data)) return [];
  return data.map(adaptPriceData).filter(isNonNull);
}

// =============================================================================
// Metric Data Adapter
// =============================================================================

export interface SafeMetric {
  value: number;
  formatted: string;
  direction: 'up' | 'down' | 'neutral';
  sparklineData: number[];
}

export function adaptMetric(data: unknown): SafeMetric {
  if (!data || typeof data !== 'object') {
    return {
      value: 0,
      formatted: '—',
      direction: 'neutral',
      sparklineData: [],
    };
  }

  const d = data as Record<string, unknown>;
  const value = safeNumber(d.value);
  const sparklineData = safeArray<number>(d.sparklineData);

  // Clean sparkline data
  const cleanSparkline = sparklineData.map((v) => {
    if (typeof v === 'number' && !isNaN(v) && isFinite(v)) return v;
    return 0;
  });

  // Determine direction from string or compute from sparkline
  let direction: 'up' | 'down' | 'neutral' = 'neutral';
  const dirStr = safeString(d.direction).toLowerCase();
  if (dirStr.includes('up') || dirStr.includes('bull')) direction = 'up';
  else if (dirStr.includes('down') || dirStr.includes('bear')) direction = 'down';

  return {
    value,
    formatted: safeString(d.formatted, value.toFixed(2)),
    direction,
    sparklineData: cleanSparkline,
  };
}

// =============================================================================
// Signal Data Adapter
// =============================================================================

export interface SafeSignalDetails {
  latestScore: number;
  threeMonthChange: string;
  state: string;
  direction: string;
  interpretation: string;
  history: number[];
  historyLabels: string[];
}

export function adaptSignalDetails(data: unknown): SafeSignalDetails {
  if (!data || typeof data !== 'object') {
    return {
      latestScore: 0,
      threeMonthChange: '—',
      state: 'neutral',
      direction: 'stable',
      interpretation: 'No data available',
      history: [],
      historyLabels: [],
    };
  }

  const d = data as Record<string, unknown>;

  // Clean history data
  const history = safeArray<number>(d.history).map((v) => safeNumber(v));
  const historyLabels = safeArray<string>(d.historyLabels);

  return {
    latestScore: safeNumber(d.latestScore),
    threeMonthChange: safeString(d.threeMonthChange, '—'),
    state: safeString(d.state, 'neutral'),
    direction: safeString(d.direction, 'stable'),
    interpretation: safeString(d.interpretation, 'No data available'),
    history,
    historyLabels,
  };
}

// =============================================================================
// Sector Data Adapter
// =============================================================================

export interface SafeSector {
  name: string;
  score: number;
  signal: string;
  conviction: string;
  rationale: string;
}

export function adaptSector(data: unknown): SafeSector | null {
  if (!data || typeof data !== 'object') return null;

  const d = data as Record<string, unknown>;

  return {
    name: safeString(d.name, 'Unknown'),
    score: safeNumber(d.score),
    signal: safeString(d.signal, 'NEUTRAL'),
    conviction: safeString(d.conviction, 'low'),
    rationale: safeString(d.rationale, 'No data available'),
  };
}

export function adaptSectorList(data: unknown[]): SafeSector[] {
  if (!Array.isArray(data)) return [];
  return data.map(adaptSector).filter(isNonNull);
}

// =============================================================================
// Regime Data Adapter
// =============================================================================

export interface SafeRegimeData {
  current: string;
  confidence: string;
  confidenceScore: number;
  duration: number;
  history: Array<{ date: string; regime: string }>;
  interpretations: Array<{ label: string; value: string }>;
  alert: string | null;
}

export function adaptRegimeData(data: unknown): SafeRegimeData {
  if (!data || typeof data !== 'object') {
    return {
      current: 'Unknown',
      confidence: 'low',
      confidenceScore: 0,
      duration: 0,
      history: [],
      interpretations: [],
      alert: null,
    };
  }

  const d = data as Record<string, unknown>;

  // Clean history
  const rawHistory = safeArray<Record<string, unknown>>(d.history);
  const history = rawHistory
    .map((h) => ({
      date: safeString(h.date || h.timestamp),
      regime: safeString(h.regime || h.regimeLabel, 'Unknown'),
    }))
    .filter((h) => h.date && h.regime);

  // Clean interpretations
  const rawInterp = safeArray<Record<string, unknown>>(d.interpretations);
  const interpretations = rawInterp.map((i) => ({
    label: safeString(i.label || i.key),
    value: safeString(i.value || i.text),
  }));

  return {
    current: safeString(d.current, 'Unknown'),
    confidence: safeString(d.confidence, 'low'),
    confidenceScore: safeNumber(d.confidenceScore),
    duration: Math.max(0, safeNumber(d.duration)),
    history,
    interpretations,
    alert: d.alert ? safeString(d.alert) : null,
  };
}

// =============================================================================
// Recession Data Adapter
// =============================================================================

export interface SafeRecessionData {
  probability: number;
  level: string;
  logisticProb: number;
  emProbitProb: number;
  sahmValue: number;
  sahmSignal: string;
  description: string;
  trendDirection: string;
  oneMonthDelta: number;
}

export function adaptRecessionData(data: unknown): SafeRecessionData {
  if (!data || typeof data !== 'object') {
    return {
      probability: 0,
      level: 'low',
      logisticProb: 0,
      emProbitProb: 0,
      sahmValue: 0,
      sahmSignal: 'normal',
      description: 'No recession data available',
      trendDirection: 'stable',
      oneMonthDelta: 0,
    };
  }

  const d = data as Record<string, unknown>;

  return {
    probability: Math.max(0, Math.min(1, safeNumber(d.probability))),
    level: safeString(d.level, 'low'),
    logisticProb: Math.max(0, Math.min(1, safeNumber(d.logisticProb))),
    emProbitProb: Math.max(0, Math.min(1, safeNumber(d.emProbitProb))),
    sahmValue: safeNumber(d.sahmValue),
    sahmSignal: safeString(d.sahmSignal, 'normal'),
    description: safeString(d.description, 'No data available'),
    trendDirection: safeString(d.trendDirection, 'stable'),
    oneMonthDelta: safeNumber(d.oneMonthDelta),
  };
}

// =============================================================================
// Dashboard Data Adapter
// =============================================================================

export interface SafeDashboardData {
  regime: SafeRegimeData;
  keyMetrics: {
    growth: SafeMetric;
    inflation: SafeMetric;
    liquidity: SafeMetric;
    risk: SafeMetric;
    recession: SafeMetric;
    regimeDuration: Record<string, string>;
  };
  signals: {
    growth: SafeSignalDetails;
    inflation: SafeSignalDetails;
    liquidity: SafeSignalDetails;
    risk: SafeSignalDetails;
  };
  sectorAllocation: {
    sectors: SafeSector[];
    chartData: unknown[];
  };
  recession: SafeRecessionData;
  metadata: {
    latestDate: string;
    dataStatus: string;
    daysSinceUpdate: number;
    mode: string;
  };
}

export function adaptDashboardData(data: unknown): SafeDashboardData | null {
  if (!data || typeof data !== 'object') return null;

  const d = data as Record<string, unknown>;

  const keyMetrics = safeObject<Record<string, unknown>>(d.keyMetrics);
  const signals = safeObject<Record<string, unknown>>(d.signals);
  const sectorAllocation = safeObject<Record<string, unknown>>(d.sectorAllocation);

  return {
    regime: adaptRegimeData(d.regime),
    keyMetrics: {
      growth: adaptMetric(keyMetrics.growth),
      inflation: adaptMetric(keyMetrics.inflation),
      liquidity: adaptMetric(keyMetrics.liquidity),
      risk: adaptMetric(keyMetrics.risk),
      recession: adaptMetric(keyMetrics.recession),
      regimeDuration: safeObject(keyMetrics.regimeDuration, {}),
    },
    signals: {
      growth: adaptSignalDetails(signals.growth),
      inflation: adaptSignalDetails(signals.inflation),
      liquidity: adaptSignalDetails(signals.liquidity),
      risk: adaptSignalDetails(signals.risk),
    },
    sectorAllocation: {
      sectors: adaptSectorList(safeArray(sectorAllocation.sectors)),
      chartData: safeArray(sectorAllocation.chartData),
    },
    recession: adaptRecessionData(d.recession),
    metadata: {
      latestDate: safeString(
        (d.metadata as Record<string, unknown>)?.latestDate,
        'N/A'
      ),
      dataStatus: safeString(
        (d.metadata as Record<string, unknown>)?.dataStatus,
        'unavailable'
      ),
      daysSinceUpdate: safeNumber(
        (d.metadata as Record<string, unknown>)?.daysSinceUpdate
      ),
      mode: safeString((d.metadata as Record<string, unknown>)?.mode, 'unknown'),
    },
  };
}

// =============================================================================
// Array/Map Safety Helpers
// =============================================================================

/**
 * Safely maps over an array with null handling
 */
export function safeMap<T, R>(
  arr: T[] | null | undefined,
  fn: (item: T, index: number) => R | null
): R[] {
  if (!Array.isArray(arr)) return [];
  return arr
    .map((item, index) => {
      try {
        return fn(item, index);
      } catch {
        return null;
      }
    })
    .filter(isNonNull);
}

/**
 * Safely reduces an array with null handling
 */
export function safeReduce<T, R>(
  arr: T[] | null | undefined,
  fn: (acc: R, item: T, index: number) => R,
  initial: R
): R {
  if (!Array.isArray(arr)) return initial;
  try {
    return arr.reduce(fn, initial);
  } catch {
    return initial;
  }
}

/**
 * Safely filters an array with null handling
 */
export function safeFilter<T>(
  arr: T[] | null | undefined,
  predicate: (item: T) => boolean
): T[] {
  if (!Array.isArray(arr)) return [];
  try {
    return arr.filter(predicate);
  } catch {
    return [];
  }
}

// =============================================================================
// Export all adapters
// =============================================================================

export const adapters = {
  price: adaptPriceData,
  priceList: adaptPriceDataList,
  metric: adaptMetric,
  signal: adaptSignalDetails,
  sector: adaptSector,
  sectorList: adaptSectorList,
  regime: adaptRegimeData,
  recession: adaptRecessionData,
  dashboard: adaptDashboardData,
};

export default adapters;
