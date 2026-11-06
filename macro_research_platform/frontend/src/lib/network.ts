/**
 * Network utilities — centralized API and WebSocket URL resolution
 *
 * Rules:
 * - HTTP calls are same-origin (relative) unless VITE_API_URL says otherwise: the dev proxy forwards /api
 * - WebSockets still connect to the backend directly (browsers don't apply CORS to WebSocket handshakes)
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

  // An explicitly discovered backend port (a global set by the host page) still wins
  const port = getDiscoveredPort();
  if (port) return `http://localhost:${port}`;
  // Otherwise same origin: the Vite dev proxy (or the production host) forwards /api to the backend. An absolute
  // http://localhost:8000 was cross-origin from any frontend port but 5173 and failed CORS.
  if (typeof window !== 'undefined' && import.meta.env.MODE !== 'test') return '';   // Node tests: absolute
  return `http://localhost:${DEFAULT_API_PORT}`;
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

  const apiBase = getApiBaseUrl();

  // A same-origin (relative) API base carries no host to upgrade, so take the origin from the
  // page itself: in production the host serves the API and the socket together. An empty base
  // means dev, where the Vite proxy does not forward /ws — sockets go to the backend directly
  // (browsers apply no CORS to WebSocket handshakes).
  if (apiBase.startsWith('/')) {
    if (typeof window !== 'undefined') {
      return `${window.location.protocol}//${window.location.host}`;
    }
  }

  const absolute = apiBase || `http://localhost:${getDiscoveredPort() || DEFAULT_API_PORT}`;
  return absolute
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
