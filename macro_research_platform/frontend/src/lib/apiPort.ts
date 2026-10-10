/**
 * Dynamic API port resolution — never hardcode a port.
 *
 * Resolution order:
 *  1. VITE_API_URL env var (set at build time)
 *  2. .api_port file served from /.api_port (dev only)
 *  3. Probe known ports until one responds
 *  4. Fall back to same-origin (for prod/reverse-proxy)
 */

// Only the default backend port. Vite proxies /api to the backend in dev and prod
// uses same-origin, so probing extra dead ports (8001/8002/8080/9000) just fired
// four failed requests on every load.
const PROBE_PORTS = [8000];
const PROBE_TIMEOUT = 1500; // ms per probe
const CACHE_KEY = "__macro_api_port__";

/** Probe a port and return true if the API responds. */
async function probePort(port: number): Promise<boolean> {
  try {
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), PROBE_TIMEOUT);
    const res = await fetch(`http://localhost:${port}/api/health`, {
      signal: ctrl.signal,
      cache: "no-store",
    });
    clearTimeout(timer);
    return res.ok;
  } catch {
    return false;
  }
}

/** Read the .api_port file written by the backend. */
async function readPortFile(): Promise<number | null> {
  try {
    // Vite dev server exposes root files at /
    const res = await fetch("/.api_port", { cache: "no-store" });
    if (!res.ok) return null;
    const text = (await res.text()).trim();
    const port = parseInt(text, 10);
    return isNaN(port) ? null : port;
  } catch {
    return null;
  }
}

/** Discover the API base URL — called once at app startup. */
export async function resolveApiBase(): Promise<string> {
  // 1. Env var (build-time / .env)
  const envUrl = import.meta.env.VITE_API_URL as string | undefined;
  if (envUrl) return envUrl.replace(/\/$/, "");

  // 1b. Dev: Vite proxies /api to the backend, so same-origin is correct and avoids
  // probing localhost ports entirely (the old probe timed out on the slow /api/health).
  if (import.meta.env.DEV) {
    (window as any)[CACHE_KEY] = "";
    return "";
  }

  // 2. In-memory cache (resolved in this session)
  const cached = (window as any)[CACHE_KEY];
  if (cached) return cached;

  // 3. .api_port file (written by Python backend on startup)
  const filePort = await readPortFile();
  if (filePort) {
    const base = `http://localhost:${filePort}`;
    (window as any)[CACHE_KEY] = base;
    return base;
  }

  // 4. Probe ports sequentially
  for (const port of PROBE_PORTS) {
    if (await probePort(port)) {
      const base = `http://localhost:${port}`;
      (window as any)[CACHE_KEY] = base;
      console.info(`[Macro OS] API discovered on port ${port}`);
      return base;
    }
  }

  // 5. Same-origin fallback (production / reverse proxy)
  console.warn("[Macro OS] API port not found — using same-origin");
  return "";
}

/** Cached synchronous accessor — only valid after resolveApiBase() */
export function getApiBase(): string {
  return (window as any)[CACHE_KEY] ?? "";
}

/** Build a full API URL from a path */
export function apiUrl(path: string): string {
  const base = getApiBase();
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${base}${p}`;
}

/** Get WebSocket URL */
export function getWsUrl(): string {
  const base = getApiBase();
  if (!base) return ""; // Same-origin
  return base.replace("http://", "ws://").replace("https://", "wss://");
}
