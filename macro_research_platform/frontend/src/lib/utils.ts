import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatPercent(value: number, decimals = 1): string {
  return `${value.toFixed(decimals)}%`;
}

export function formatScore(value: number, decimals = 2): string {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(decimals)}`;
}

export function formatDate(date: string | Date): string {
  const d = typeof date === 'string' ? new Date(date) : date;
  return d.toLocaleDateString('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  });
}

export function getSignalColor(signal: string): string {
  const signalLower = signal.toLowerCase();
  if (signalLower.includes('overweight')) {
    return '#238636'; // green
  }
  if (signalLower.includes('underweight')) {
    return '#da3633'; // red
  }
  if (signalLower.includes('neutral')) {
    return '#7d8590'; // muted
  }
  return '#7d8590';
}

export function getDirectionColor(direction: 'up' | 'down' | 'neutral'): string {
  switch (direction) {
    case 'up':
      return '#3fb950';
    case 'down':
      return '#f85149';
    default:
      return '#7d8590';
  }
}

export function debounce<T extends (...args: unknown[]) => unknown>(
  fn: T,
  delay: number
): (...args: Parameters<T>) => void {
  let timeoutId: ReturnType<typeof setTimeout>;
  return (...args: Parameters<T>) => {
    clearTimeout(timeoutId);
    timeoutId = setTimeout(() => fn(...args), delay);
  };
}

// FIXED: Safe value display helper - never show blank or placeholder
interface SafeValOptions {
  unit?: string;
  decimals?: number;
  prefix?: string;
  fallback?: string;
}

export function safeVal(
  value: unknown,
  options: SafeValOptions = {}
): string {
  const { unit = '', decimals = 2, prefix = '', fallback = '--' } = options;

  // Check for null, undefined, empty string, NaN
  if (value === null || value === undefined || value === '') {
    return fallback;
  }
  if (typeof value === 'number' && isNaN(value)) {
    return fallback;
  }

  // Convert to number if string
  const num = typeof value === 'string' ? parseFloat(value) : value;
  if (typeof num !== 'number' || isNaN(num)) {
    return fallback;
  }

  return `${prefix}${num.toFixed(decimals)}${unit}`;
}

// FIXED: Safe display with tooltip for unavailable data
export function safeValWithTooltip(
  value: unknown,
  label: string,
  options: SafeValOptions & { tooltip?: string } = {}
): { display: string; tooltip: string; isEmpty: boolean } {
  const { tooltip, ...safeOptions } = options;
  const display = safeVal(value, safeOptions);
  const isEmpty = display === (options.fallback ?? '--');

  return {
    display,
    tooltip: isEmpty
      ? tooltip || `${label}: Data unavailable`
      : `${label}: ${display}`,
    isEmpty,
  };
}
