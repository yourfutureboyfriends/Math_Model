/**
 * FormattedNumber component - Phase 4 Standardization
 *
 * Replaces ad-hoc .toFixed() calls with consistent formatting.
 * Uses FORMAT_* constants from utils/format.ts
 */

import {
  fmtProbability,
  fmtPrice,
  fmtChange,
  fmtRate,
  fmtSigma,
  fmtMagnitude,
} from '@/utils/format';

type FormatType =
  | 'probability'    // 4 decimal places (0.7532)
  | 'price'          // 2 decimal places with $ ($123.45)
  | 'change'         // +12.34% format
  | 'rate'           // Rate formatting
  | 'sigma'          // Sigma/plus-minus format
  | 'magnitude'      // Large number (1.2M)
  | 'custom';        // specify decimals

interface FormattedNumberProps {
  value: number | null | undefined;
  type: FormatType;
  decimals?: number;
  prefix?: string;
  suffix?: string;
  className?: string;
  fallback?: string;
}

export function FormattedNumber({
  value,
  type,
  decimals,
  prefix = '',
  suffix = '',
  className,
  fallback = '--',
}: FormattedNumberProps) {
  if (value === null || value === undefined || isNaN(value)) {
    return <span className={className}>{fallback}</span>;
  }

  let formatted: string;

  switch (type) {
    case 'probability':
      formatted = fmtProbability(value);
      break;
    case 'price':
      formatted = fmtPrice(value, decimals);
      break;
    case 'change':
      formatted = fmtChange(value, decimals);
      break;
    case 'rate':
      formatted = fmtRate(value, decimals);
      break;
    case 'sigma':
      formatted = fmtSigma(value, decimals);
      break;
    case 'magnitude':
      formatted = fmtMagnitude(value, decimals);
      break;
    case 'custom':
      formatted = value.toFixed(decimals ?? 2);
      break;
    default:
      formatted = value.toString();
  }

  return (
    <span className={className}>
      {prefix}{formatted}{suffix}
    </span>
  );
}

/**
 * Convenience component for Sharpe/Sortino ratios
 * Shows 2 decimals
 */
export function Ratio({ value, className }: { value: number | null | undefined; className?: string }) {
  return (
    <FormattedNumber
      value={value}
      type="custom"
      decimals={2}
      className={className}
    />
  );
}

/**
 * Convenience component for Beta values
 */
export function Beta({ value, className }: { value: number | null | undefined; className?: string }) {
  return (
    <FormattedNumber
      value={value}
      type="custom"
      decimals={2}
      className={className}
    />
  );
}

/**
 * Convenience component for correlation values
 */
export function Correlation({ value, className }: { value: number | null | undefined; className?: string }) {
  return (
    <FormattedNumber
      value={value}
      type="custom"
      decimals={2}
      className={className}
    />
  );
}
