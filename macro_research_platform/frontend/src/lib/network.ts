/**
 * Network utilities — centralized API and WebSocket URL resolution
 *
 * Rules:
 * - Never derive backend URLs from window.location in dev mode
 * - Respect VITE_API_URL and VITE_WS_URL environment variables
 * - Fallback to discovered backend port or default localhost:8000
 * - Normalize paths to avoid double slashes
 */

const DEFAULT_API_PORT = 8000;

/**
 * Get the discovered backend API port
 * Tries .api_port file first, then falls back to default
 */
function getDiscoveredPort(): number | null {
  // In a real app, this could read from a file or localStorage
  // For now, check if we have a global variable or fallback to null
  const discovered = (window as any).__API_PORT__;
  if (discovered && typeof discovered === 'number') {
    return discovered;
  }
  return null;
}

/**
 * Get the base URL for HTTP API calls
 *
 * Priority:
 * 1. VITE_API_URL environment variable
 * 2. Discovered backend port
 * 3. Default localhost:8000
 *
 * In production, this should be configured via env var
 */
export function getApiBaseUrl(): string {
  // Check for explicit env var first
  const envUrl = import.meta.env.VITE_API_URL as string | undefined;
  if (envUrl) {
    return envUrl.replace(/\/$/, ''); // Remove trailing slash
  }

  // Fallback to discovered port or default
  const port = getDiscoveredPort() || DEFAULT_API_PORT;
  return `http://localhost:${port}`;
}

/**
 * Get the base URL for WebSocket connections
 *
 * Priority:
 * 1. VITE_WS_URL environment variable
 * 2. Derived from API base URL (http -> ws, https -> wss)
 * 3. Default ws://localhost:8000
 */
export function getWsBaseUrl(): string {
  // Check for explicit WebSocket env var first
  const envWsUrl = import.meta.env.VITE_WS_URL as string | undefined;
  if (envWsUrl) {
    return envWsUrl.replace(/\/$/, ''); // Remove trailing slash
  }

  // Derive from API base URL
  const apiBase = getApiBaseUrl();
  return apiBase
    .replace(/^http:/, 'ws:')
    .replace(/^https:/, 'wss:');
}

/**
 * Build a full API endpoint URL
 *
 * @param path - API path (e.g., '/api/dashboard')
 * @returns Full URL (e.g., 'http://localhost:8000/api/dashboard')
 */
export function getEndpointUrl(path: string): string {
  const base = getApiBaseUrl();
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${base}${normalizedPath}`;
}

/**
 * Build a full WebSocket URL
 *
 * @param path - WebSocket path (e.g., '/ws/prices')
 * @returns Full URL (e.g., 'ws://localhost:8000/ws/prices')
 */
export function getWebSocketUrl(path: string): string {
  const base = getWsBaseUrl();
  const normalizedPath = path.startsWith('/') ? path : `/${path}`;
  return `${base}${normalizedPath}`;
}

/**
 * Get just the API path for use with Vite proxy
 * Returns the path without the base URL
 *
 * @param path - API path
 * @returns Normalized path starting with /
 */
export function getApiPath(path: string): string {
  return path.startsWith('/') ? path : `/${path}`;
}
