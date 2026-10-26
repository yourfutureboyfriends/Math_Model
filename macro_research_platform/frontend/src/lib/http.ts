// One JSON fetch helper for panels: sends JSON, returns JSON, and throws an Error whose message is the server's
// explanation (FastAPI `detail` as text, {message, reasons|problems}, or a validation list) — else "HTTP <status>".
export function errorMessage(j: any, status: number): string {
  const d = j?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x: any) => x?.msg ?? String(x)).join('; ');
  if (d?.message) {
    const extra = d.reasons ?? d.problems;
    return Array.isArray(extra) && extra.length ? `${d.message}: ${extra.join('; ')}` : d.message;
  }
  return `HTTP ${status}`;
}

export async function apiCall(url: string, method = 'GET', body?: unknown): Promise<any> {
  const r = await fetch(url, { method, headers: body ? { 'Content-Type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(errorMessage(j, r.status));
  return j;
}
