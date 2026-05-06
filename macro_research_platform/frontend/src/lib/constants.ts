/**
 * Standard formatting constants (mirrors backend api/utils/formatting.py)
 */

// Number formatting precision
export const FORMAT_PROBABILITY = 4;      // 0.0000 to 1.0000
export const FORMAT_PERCENTAGE = 2;       // 75.25%
export const FORMAT_INDEX = 2;            // 100.00
export const FORMAT_PRICE = 2;            // $123.45
export const FORMAT_BASIS_POINTS = 0;     // 250

// Rate/yield formatting
export const FORMAT_YIELD = 2;            // 4.25%
export const FORMAT_SPREAD = 1;           // 1.5%

// FX formatting
export const FORMAT_FX_MAJOR = 4;         // 1.0850
export const FORMAT_FX_JPY = 2;           // 150.25
export const FORMAT_FX_MINOR = 5;         // 0.89125

/**
 * Format helpers
 */
export function formatProbability(value: number): string {
  return value.toFixed(FORMAT_PROBABILITY);
}

export function formatPercentage(value: number, multiply = false): string {
  const v = multiply ? value * 100 : value;
  return `${v.toFixed(FORMAT_PERCENTAGE)}%`;
}

export function formatPrice(value: number): string {
  return value.toFixed(FORMAT_PRICE);
}

export function formatIndex(value: number): string {
  return value.toFixed(FORMAT_INDEX);
}
