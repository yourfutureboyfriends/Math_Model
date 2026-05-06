/**
 * Format Library — Single Source of Truth for Number Formatting
 *
 * Rules:
 * - Every number displayed to the user MUST go through this library
 * - No component ever calls .toFixed() directly
 * - All formatters handle null/undefined/NaN gracefully
 * - Use appropriate formatter for each data type
 */

// ============================================================================
// LEGACY EXPORTS (backward compatibility)
// ============================================================================

export function safeNum(v: number | null | undefined, decimals = 2, suffix = ''): string {
  if (v === null || v === undefined || typeof v !== 'number' || isNaN(v) || !isFinite(v)) return '—';
  return v.toFixed(decimals) + suffix;
}

export function safePct(v: number | null | undefined, decimals = 1): string {
  return safeNum(v, decimals, '%');
}

export function clampPct(v: number | null | undefined): string {
  if (v === null || v === undefined || typeof v !== 'number' || isNaN(v)) return '—';
  return `${Math.min(100, Math.max(0, Math.round(v)))}%`;
}

export function safeSign(v: number | null | undefined, decimals = 2): string {
  if (v === null || v === undefined || typeof v !== 'number' || isNaN(v) || !isFinite(v)) return '—';
  return (v >= 0 ? '+' : '') + v.toFixed(decimals);
}

export function safeBps(v: number | null | undefined): string {
  if (v === null || v === undefined || typeof v !== 'number' || isNaN(v)) return '—';
  return `${Math.round(v)} bps`;
}

export function safeInt(v: number | null | undefined): string {
  if (v === null || v === undefined || typeof v !== 'number' || isNaN(v) || !isFinite(v)) return '—';
  return Math.round(v).toString();
}

export function safeCurrency(v: number | null | undefined, decimals = 2): string {
  if (v === null || v === undefined || typeof v !== 'number' || isNaN(v) || !isFinite(v)) return '—';
  return '$' + v.toFixed(decimals);
}

export function safeRatio(v: number | null | undefined, decimals = 2): string {
  if (v === null || v === undefined || typeof v !== 'number' || isNaN(v) || !isFinite(v)) return '—';
  return v.toFixed(decimals) + 'x';
}

// ============================================================================
// NEW STANDARDIZED FORMATTERS (Phase 1)
// ============================================================================

// Null/NaN guard wrapper
const guard = (
  v: number | null | undefined,
  fn: (n: number) => string,
  defaultValue = '—'
): string => {
  if (v == null || isNaN(v) || !isFinite(v)) return defaultValue;
  return fn(v);
};

// ============================================================================
// RATES (FED, 10Y, 2Y)
// ============================================================================

/**
 * Format interest rate as percentage
 * Input: 3.64 (decimal) -> Output: "3.64%"
 * Input: null -> Output: "—"
 */
export const fmtRate = (v: number | null, decimals = 2): string =>
  guard(v, (n) => n.toFixed(decimals) + '%');

/**
 * Format rate change
 * Input: 0.25 -> Output: "+0.25%"
 * Input: -0.10 -> Output: "-0.10%"
 */
export const fmtRateChange = (v: number | null, decimals = 2): string =>
  guard(v, (n) => {
    const sign = n >= 0 ? '+' : '';
    return sign + n.toFixed(decimals) + '%';
  });

// ============================================================================
// PRICES (SPX, NDX, GLD, WTI)
// ============================================================================

/**
 * Format price with thousands separator
 * Input: 4200.5 -> Output: "4,200.50"
 */
export const fmtPrice = (v: number | null, decimals = 2): string =>
  guard(v, (n) =>
    n.toFixed(decimals).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  );

/**
 * Format price with no decimals (for indices)
 * Input: 4200.5 -> Output: "4,201"
 */
export const fmtPriceInt = (v: number | null): string =>
  guard(v, (n) =>
    Math.round(n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  );

/**
 * Format FX rate
 * Input: 1.1750 -> Output: "1.1750"
 */
export const fmtFx = (v: number | null, decimals = 4): string =>
  guard(v, (n) => n.toFixed(decimals));

// ============================================================================
// CHANGES (percent change)
// ============================================================================

/**
 * Format percent change
 * Input: 0.0114 -> Output: "+1.14%"
 * Input: -0.0056 -> Output: "-0.56%"
 */
export const fmtChange = (v: number | null, decimals = 2): string =>
  guard(v, (n) => {
    const pct = (n * 100).toFixed(decimals);
    const sign = n >= 0 ? '+' : '';
    return sign + pct + '%';
  });

/**
 * Format change with color indicator
 * Returns object with formatted string and CSS color class
 */
export const fmtChangeWithColor = (
  v: number | null,
  decimals = 2
): { text: string; colorClass: string } => {
  if (v == null || isNaN(v)) {
    return { text: '—', colorClass: 'text-text-secondary' };
  }
  const pct = (v * 100).toFixed(decimals);
  const sign = v >= 0 ? '+' : '';
  const colorClass =
    v > 0 ? 'text-green' : v < 0 ? 'text-red' : 'text-text-secondary';
  return { text: sign + pct + '%', colorClass };
};

// ============================================================================
// SIGMA (z-scores, signal scores)
// ============================================================================

/**
 * Format sigma value
 * Input: -0.74 -> Output: "-0.74σ"
 */
export const fmtSigma = (v: number | null, decimals = 2): string =>
  guard(v, (n) => n.toFixed(decimals) + 'σ');

/**
 * Format signal score with direction indicator
 * Input: 0.45 -> Output: "+0.45"
 */
export const fmtSignal = (v: number | null, decimals = 2): string =>
  guard(v, (n) => {
    const sign = n >= 0 ? '+' : '';
    return sign + n.toFixed(decimals);
  });

// ============================================================================
// AGREEMENT & CONFIDENCE (percentages 0-1)
// ============================================================================

/**
 * Format agreement as percentage
 * Input: 0.50 -> Output: "50%"
 * Input: 0.725 -> Output: "73%"
 */
export const fmtAgreement = (v: number | null): string =>
  guard(v, (n) => {
    // Clamp to 0-1 range
    const clamped = Math.max(0, Math.min(1, n));
    return (clamped * 100).toFixed(0) + '%';
  });

/**
 * Format confidence as percentage
 * Input: 0.90 -> Output: "90%"
 */
export const fmtConfidence = (v: number | null): string =>
  guard(v, (n) => {
    const clamped = Math.max(0, Math.min(1, n));
    return (clamped * 100).toFixed(0) + '%';
  });

/**
 * Format probability as percentage
 * Input: 0.25 -> Output: "25%"
 */
export const fmtProbability = (v: number | null): string =>
  guard(v, (n) => {
    const clamped = Math.max(0, Math.min(1, n));
    return (clamped * 100).toFixed(0) + '%';
  });

/**
 * Format probability with decimals for precision
 * Input: 0.2534 -> Output: "25.34%"
 */
export const fmtProbabilityPrecise = (v: number | null, decimals = 1): string =>
  guard(v, (n) => {
    const clamped = Math.max(0, Math.min(1, n));
    return (clamped * 100).toFixed(decimals) + '%';
  });

// ============================================================================
// BASIS POINTS (for small changes)
// ============================================================================

/**
 * Format as basis points
 * Input: 0.0080 (80bps as decimal) -> Output: "+80bps"
 * Note: If input > 1, assumes it's already in bps
 */
export const fmtBps = (v: number | null): string =>
  guard(v, (n) => {
    const bps = n > 1 ? Math.round(n) : Math.round(n * 10000);
    const sign = bps >= 0 ? '+' : '';
    return sign + bps + 'bps';
  });

// ============================================================================
// DURATION & TIME
// ============================================================================

/**
 * Format duration in months
 * Input: 6 -> Output: "6 months"
 * Input: 1 -> Output: "1 month"
 */
export const fmtDuration = (v: number | null): string =>
  guard(v, (n) => {
    const months = Math.round(n);
    return `${months} month${months !== 1 ? 's' : ''}`;
  });

/**
 * Format date as ISO string
 * Input: Date -> Output: "2026-05-06"
 */
export const fmtDate = (v: Date | string | null): string => {
  if (!v) return '—';
  const d = typeof v === 'string' ? new Date(v) : v;
  if (isNaN(d.getTime())) return '—';
  return d.toISOString().split('T')[0];
};

/**
 * Format time (HH:MM:SS)
 */
export const fmtTime = (v: Date | string | null): string => {
  if (!v) return '—';
  const d = typeof v === 'string' ? new Date(v) : v;
  if (isNaN(d.getTime())) return '—';
  return d.toISOString().split('T')[1].split('.')[0];
};

/**
 * Format datetime
 */
export const fmtDateTime = (v: Date | string | null): string => {
  if (!v) return '—';
  const d = typeof v === 'string' ? new Date(v) : v;
  if (isNaN(d.getTime())) return '—';
  return d.toISOString().replace('T', ' ').slice(0, 19) + ' UTC';
};

// ============================================================================
// SPECIAL FORMATTERS
// ============================================================================

/**
 * Format regime name for display
 * Input: "goldilocks" -> Output: "Goldilocks"
 */
export const fmtRegime = (v: string | null): string => {
  if (!v) return '—';
  return v.charAt(0).toUpperCase() + v.slice(1).toLowerCase();
};

/**
 * Format number with magnitude suffix (K, M, B)
 * Input: 1500000 -> Output: "1.5M"
 */
export const fmtMagnitude = (v: number | null, decimals = 1): string =>
  guard(v, (n) => {
    const abs = Math.abs(n);
    if (abs >= 1e9) {
      return (n / 1e9).toFixed(decimals) + 'B';
    }
    if (abs >= 1e6) {
      return (n / 1e6).toFixed(decimals) + 'M';
    }
    if (abs >= 1e3) {
      return (n / 1e3).toFixed(decimals) + 'K';
    }
    return n.toFixed(decimals);
  });

/**
 * Format volatility (VIX-style)
 * Input: 25.2 -> Output: "25.2"
 */
export const fmtVol = (v: number | null): string =>
  guard(v, (n) => n.toFixed(1));

// ============================================================================
// DECISION FORMATTERS (for business logic)
// ============================================================================

/**
 * Format signal state with appropriate styling
 */
export const fmtSignalState = (
  state: string | null
): { text: string; colorClass: string } => {
  const stateMap: Record<string, { text: string; colorClass: string }> = {
    expansion: { text: 'Expansion', colorClass: 'text-green' },
    contraction: { text: 'Contraction', colorClass: 'text-red' },
    neutral: { text: 'Neutral', colorClass: 'text-text-secondary' },
    up: { text: 'Up', colorClass: 'text-green' },
    down: { text: 'Down', colorClass: 'text-red' },
    stable: { text: 'Stable', colorClass: 'text-text-secondary' },
  };

  const key = (state || 'neutral').toLowerCase();
  return stateMap[key] || { text: state || '—', colorClass: 'text-text-secondary' };
};

/**
 * Format conviction level
 */
export const fmtConviction = (
  conviction: string | null
): { text: string; colorClass: string } => {
  const conv = (conviction || 'low').toLowerCase();
  const colorClass =
    conv === 'high'
      ? 'text-green'
      : conv === 'medium'
      ? 'text-amber'
      : 'text-text-secondary';
  return { text: conviction || '—', colorClass };
};

// ============================================================================
// COMPOSITE FORMATTERS (for complex display)
// ============================================================================

/**
 * Format price with change inline
 * Example: "4,200 (+1.14%)"
 */
export const fmtPriceWithChange = (
  price: number | null,
  change: number | null
): string => {
  if (price == null) return '—';
  const priceStr = fmtPriceInt(price);
  if (change == null) return priceStr;
  return `${priceStr} (${fmtChange(change)})`;
};

/**
 * Format regime with confidence
 * Example: "Goldilocks (90% confidence)"
 */
export const fmtRegimeWithConfidence = (
  regime: string | null,
  confidence: number | null
): string => {
  if (!regime) return '—';
  const conf = confidence != null ? ` (${fmtConfidence(confidence)})` : '';
  return fmtRegime(regime) + conf;
};
