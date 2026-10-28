/**
 * Runtime API response validation
 * Validates responses from backend before using in frontend
 */

import type { components } from '@/types/api-generated';

export type DashboardData = components['schemas']['DashboardData'];
export type RegimeData = components['schemas']['RegimeData'];
export type SignalsData = components['schemas']['SignalsData'];
export type RecessionData = components['schemas']['RecessionData'];
export type Scores = components['schemas']['Scores'];

export class ValidationError extends Error {
  constructor(
    message: string,
    public field: string,
    public value: unknown
  ) {
    super(message);
    this.name = 'ValidationError';
  }
}

/**
 * Validate required fields exist
 */
export function validateRequiredFields<T extends Record<string, unknown>>(
  data: unknown,
  requiredFields: (keyof T)[]
): data is T {
  if (!data || typeof data !== 'object') {
    throw new ValidationError('Response is not an object', 'root', data);
  }

  const obj = data as Record<string, unknown>;

  for (const field of requiredFields) {
    if (!(field in obj)) {
      throw new ValidationError(
        `Missing required field: ${String(field)}`,
        String(field),
        undefined
      );
    }
  }

  return true;
}

/**
 * Normalize numeric field (handle string numbers, NaN, null)
 */
export function normalizeNumericField(value: unknown, fallback = 0): number {
  if (typeof value === 'number' && !isNaN(value) && isFinite(value)) {
    return value;
  }

  if (typeof value === 'string') {
    const parsed = parseFloat(value);
    if (!isNaN(parsed) && isFinite(parsed)) {
      return parsed;
    }
  }

  if (value === null || value === undefined) {
    return fallback;
  }

  console.warn(`[Validation] Invalid numeric value: ${value}, using fallback: ${fallback}`);
  return fallback;
}

/**
 * Validate DashboardData response
 */
export function validateDashboardData(data: unknown): asserts data is DashboardData {
  validateRequiredFields<DashboardData>(data, [
    'regime',
    'keyMetrics',
    'scores',
    'signals',
    'recession',
    'metadata',
    'timestamp',
    'mode'
  ]);

  const dashboard = data as DashboardData;

  // Type-specific validations
  if (typeof dashboard.regime.confidenceScore !== 'number') {
    throw new ValidationError(
      'regime.confidenceScore must be number',
      'regime.confidenceScore',
      dashboard.regime.confidenceScore
    );
  }

  if (dashboard.regime.confidenceScore < 0 || dashboard.regime.confidenceScore > 1) {
    throw new ValidationError(
      'regime.confidenceScore must be 0-1',
      'regime.confidenceScore',
      dashboard.regime.confidenceScore
    );
  }

  if (typeof dashboard.scores.growth !== 'number') {
    throw new ValidationError(
      'scores.growth must be number',
      'scores.growth',
      dashboard.scores.growth
    );
  }

  // Validate arrays not empty where expected
  if (!Array.isArray(dashboard.recession.components) || dashboard.recession.components.length === 0) {
    console.warn('[Validation] recession.components is empty or not an array');
  }

  if (!Array.isArray(dashboard.recession.history) || dashboard.recession.history.length === 0) {
    console.warn('[Validation] recession.history is empty or not an array');
  }
}

/**
 * Validate and normalize dashboard data
 * Handles string numbers from backend and converts to actual numbers
 */
export function validateAndNormalizeDashboard(raw: unknown): DashboardData {
  validateDashboardData(raw);

  const data = raw as DashboardData;

  // Normalize any string numbers to actual numbers
  data.regime.confidenceScore = normalizeNumericField(data.regime.confidenceScore, 0);
  data.scores.growth = normalizeNumericField(data.scores.growth, 50);
  data.scores.inflation = normalizeNumericField(data.scores.inflation, 50);
  data.scores.liquidity = normalizeNumericField(data.scores.liquidity, 50);
  data.scores.risk = normalizeNumericField(data.scores.risk, 50);

  return data;
}

/**
 * Validate SignalsData response
 */
export function validateSignalsData(data: unknown): asserts data is SignalsData {
  validateRequiredFields<SignalsData>(data, [
    'finalSignal',
    'growth',
    'inflation',
    'liquidity',
    'risk'
  ]);

  const signals = data as SignalsData;

  // Validate signal details have required fields
  const requiredSignalFields = ['score', 'threeMonth', 'state', 'direction', 'interpretation'];

  for (const field of requiredSignalFields) {
    if (!(field in signals.growth)) {
      throw new ValidationError(
        `growth.${field} is required`,
        `growth.${field}`,
        undefined
      );
    }
  }
}

/**
 * Validate RecessionData response
 */
export function validateRecessionData(data: unknown): asserts data is RecessionData {
  validateRequiredFields<RecessionData>(data, [
    'probability',
    'level',
    'components',
    'history'
  ]);

  const recession = data as RecessionData;

  if (typeof recession.probability !== 'number') {
    throw new ValidationError(
      'probability must be number',
      'probability',
      recession.probability
    );
  }

  if (recession.probability < 0 || recession.probability > 1) {
    throw new ValidationError(
      'probability must be 0-1',
      'probability',
      recession.probability
    );
  }
}
