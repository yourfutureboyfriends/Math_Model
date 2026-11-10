/** Provider timestamps are evidence; browser receipt times never establish observation freshness. */
export type SourceMeta = { source: string; supplied: boolean; delay?: number | null; stale?: boolean; asOf?: string | null; dateBasis?: string; fetchedAt?: number; coverage?: string; note?: string };
function dateLabel(value: unknown): string | null {
  if (typeof value === 'number' && Number.isFinite(value) && value > 946684800) {
    const d = new Date(value < 1e12 ? value * 1000 : value);
    return Number.isFinite(d.getTime()) ? d.toISOString() : null;
  }
  if (typeof value === 'string' && /^\d{4}-(0[1-9]|1[0-2])$/.test(value)) return value;
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}(?:$|[T ])/.test(value) && Number.isFinite(Date.parse(value))) return value;
  return null;
}
export function sourceMeta(j: unknown): SourceMeta | null {
  if (!j || typeof j !== 'object') return null;
  const p = j as Record<string, unknown>;
  const sources = Array.isArray(p.sources) ? p.sources.filter((s): s is string => typeof s === 'string' && !!s.trim()) : [];
  const supplied = typeof p.source === 'string' && !!p.source.trim() || sources.length > 0;
  const source = typeof p.source === 'string' && p.source.trim() ? p.source : sources.join(' · ') || 'Provider not identified';
  const dateField=['as_of','price_date','observed_at','time','computed_at','last_updated','date'].find(k=>dateLabel(p[k])!=null);
  const asOf=dateField ? dateLabel(p[dateField]) : null;
  return {source, supplied, asOf, dateBasis:dateField, stale: !!p.stale,
    delay: typeof p.delay_minutes === 'number' && Number.isFinite(p.delay_minutes) && p.delay_minutes >= 0 ? p.delay_minutes : null,
    coverage: typeof p.coverage === 'string' ? p.coverage : undefined,
    note: typeof p.note === 'string' ? p.note : typeof p.method === 'string' ? p.method : undefined};
}
