// Environment Configuration — Phase 5B Production Prep
// Centralized env var access with type safety and defaults

export interface EnvConfig {
  API_URL: string;
  WS_URL: string;
  APP_NAME: string;
  APP_VERSION: string;
  ENABLE_WEBSOCKET: boolean;
  ENABLE_ANALYTICS: boolean;
  DEBUG_MODE: boolean;
  API_TIMEOUT: number;
  WS_RECONNECT_DELAY: number;
}

function getEnvVar(key: string, defaultValue: string): string {
  // vite env vars are exposed as import.meta.env.VITE_*
  const value = import.meta.env[`VITE_${key}`];
  return value !== undefined ? value : defaultValue;
}

function getBoolEnvVar(key: string, defaultValue: boolean): boolean {
  const value = getEnvVar(key, String(defaultValue));
  return value === 'true' || value === '1';
}

function getIntEnvVar(key: string, defaultValue: number): number {
  const value = getEnvVar(key, String(defaultValue));
  const parsed = parseInt(value, 10);
  return isNaN(parsed) ? defaultValue : parsed;
}

export const env: EnvConfig = {
  API_URL: getEnvVar('API_URL', '/api'),
  WS_URL: getEnvVar('WS_URL', 'ws://localhost:8000/ws'),
  APP_NAME: getEnvVar('APP_NAME', 'MACRO OS'),
  APP_VERSION: getEnvVar('APP_VERSION', '8.0.0'),
  ENABLE_WEBSOCKET: getBoolEnvVar('ENABLE_WEBSOCKET', true),
  ENABLE_ANALYTICS: getBoolEnvVar('ENABLE_ANALYTICS', false),
  DEBUG_MODE: getBoolEnvVar('DEBUG_MODE', false),
  API_TIMEOUT: getIntEnvVar('API_TIMEOUT', 30000),
  WS_RECONNECT_DELAY: getIntEnvVar('WS_RECONNECT_DELAY', 5000),
};

// Health check endpoints
export const HEALTH_ENDPOINTS = {
  API: `${env.API_URL}/health`,
  WS: env.WS_URL.replace('ws://', 'http://').replace('wss://', 'https://') + '/health',
} as const;

// Validate required config
export function validateConfig(): { valid: boolean; errors: string[] } {
  const errors: string[] = [];

  if (!env.API_URL) {
    errors.push('API_URL is required');
  }

  if (!env.WS_URL) {
    errors.push('WS_URL is required');
  }

  if (env.API_TIMEOUT < 1000) {
    errors.push('API_TIMEOUT must be at least 1000ms');
  }

  return { valid: errors.length === 0, errors };
}
