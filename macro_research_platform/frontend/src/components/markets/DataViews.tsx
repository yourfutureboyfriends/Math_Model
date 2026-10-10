// Functions built on free alternatives to paid data: SI (short selling: FINRA + short
// interest), SPLC (suppliers / competitors from SEC 10-K text), ECO (global calendar with
// consensus and actuals) and ECST (economic surprise index).
import { Fragment, useMemo, useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { REGION_CCYS, useRegion } from '@/lib/region';
import { ErrorBox, fmtBig, Loading, Panel, useJSON } from './shared';
import { LineChart } from '@/components/ui/LineChart';

const enc = encodeURIComponent;
const pc = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${(v * 100).toFixed(d)}%`);

function Stat({ label, value, sub }: { label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return <div className="border border-border bg-surface-1 px-3 py-2"><div className="text-[10px] uppercase tracking-wide text-text-tertiary">{label}</div>
    <div className="text-lg font-mono text-text-primary">{value}</div>{sub && <div className="text-[10px] text-text-tertiary">{sub}</div>}</div>;
}

export function Bars({ values, height = 120, ref100 }: { values: number[]; height?: number; ref100?: number }) {
  const max = Math.max(...values, ref100 ?? 0, 1e-9);
  return (
    <div className="relative flex items-end gap-px" style={{ height }}>
      {ref100 != null && <div className="absolute left-0 right-0 border-t border-dashed border-bloomberg/70" style={{ bottom: (ref100 / max) * height }} />}
      {values.map((v, i) => <div key={i} className="flex-1 bg-blue/70 hover:bg-bloomberg" style={{ height: `${(v / max) * 100}%` }} />)}
    </div>
  );
}

// ── SI ──────────────────────────────────────────────────────────────────────
export function SiView({ symbol }: { symbol: string }) {
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/si/${enc(symbol)}?days=120`);
  if (loading && !data) return <Loading label="Loading FINRA short-sale data (first time: ~10 s)…" />;
  if (error && !data) return <ErrorBox msg={error} />;
  if (!data) return null;
  const o = data.official ?? {};
  const d = data.daily as any[];
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Stat label="Short interest" value={fmtBig(o.shares_short)} sub={o.as_of ? `shares · as of ${o.as_of}` : 'shares'} />
        <Stat label="% of float" value={pc(o.percent_of_float)} sub={o.change != null ? `${o.change >= 0 ? '+' : ''}${(o.change * 100).toFixed(1)}% vs prior report` : ''} />
        <Stat label="Days to cover" value={o.days_to_cover?.toFixed(1) ?? '—'} sub="short interest ÷ avg volume" />
        <Stat label="Short volume today" value={pc(data.ratio_latest)} sub={data.ratio_zscore != null ? `z ${data.ratio_zscore.toFixed(1)} vs 20 days` : ''} />
        <Stat label="Short volume 20d avg" value={pc(data.ratio_20d)} sub={data.ratio_prev_20d != null ? `prior 20d ${pc(data.ratio_prev_20d)}` : ''} />
      </div>
      <Panel title="Daily short-sale volume share (FINRA)">
        <LineChart rows={d.map((x, i) => ({ date: x.date, ratio: x.ratio * 100,
            avg20: i >= 19 ? d.slice(i - 19, i + 1).reduce((a, y) => a + y.ratio, 0) / 20 * 100 : null }))} x="date" height={240} fmt={(v) => `${v.toFixed(1)}%`}
          lines={[{ key: 'ratio', label: 'Short share', color: 'rgb(var(--c-blue))' }, { key: 'avg20', label: '20-day average', color: 'rgb(var(--c-bloomberg))' }]} />
      </Panel>
      <div className="overflow-x-auto border border-border max-h-72 overflow-y-auto">
        <table className="w-full text-[11px] font-mono tabular-nums">
          <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left px-2 font-normal">Date</th><th className="text-right font-normal">Short volume</th><th className="text-right font-normal">Total volume</th><th className="text-right px-2 font-normal">Short %</th></tr></thead>
          <tbody>{[...d].reverse().map((x) => (
            <tr key={x.date} className="border-t border-border-subtle"><td className="px-2 text-text-secondary">{x.date}</td><td className="text-right">{fmtBig(x.short_volume)}</td>
              <td className="text-right">{fmtBig(x.total_volume)}</td><td className={cn('text-right px-2', x.ratio > data.ratio_20d * 1.15 ? 'text-red' : x.ratio < data.ratio_20d * 0.85 ? 'text-green' : '')}>{pc(x.ratio)}</td></tr>))}</tbody>
        </table>
      </div>
      <div className="text-[10px] text-text-tertiary">{data.note} Source: {data.source}.</div>
    </div>
  );
}

// ── SPLC ────────────────────────────────────────────────────────────────────
export function SplcView({ symbol, onOpen }: { symbol: string; onOpen: (s: string) => void }) {
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/splc/${enc(symbol)}`);
  const [tab, setTab] = useState<'suppliers' | 'competitors'>('suppliers');
  if (loading && !data) return <Loading label="Searching SEC annual reports…" />;
  if (error && !data) return <ErrorBox msg={error} />;
  if (!data) return null;
  const rows = data[tab] as any[];
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-1 text-xs">
        {([['suppliers', `Suppliers — name ${data.searched_as[0]} as a customer (${data.suppliers.length})`], ['competitors', `Competitors — name it as a rival (${data.competitors.length})`]] as const).map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)} className={cn('px-3 py-1 border', tab === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{l}</button>))}
      </div>
      {rows.length === 0 ? <p className="text-xs text-text-tertiary">None found with explicit wording in 10-Ks from the last two years.</p> : (
        <div className="border border-border overflow-x-auto">
          <table className="w-full text-xs">
            <thead><tr className="text-text-tertiary text-[10px] uppercase"><th className="text-left px-2 py-1 font-normal">Company</th><th className="text-left font-normal">Ticker</th><th className="text-left font-normal">Evidence in its 10-K</th><th className="text-right font-normal">Latest 10-K</th><th /></tr></thead>
            <tbody>{rows.map((r) => (
              <tr key={r.cik} className="border-t border-border-subtle hover:bg-surface-3">
                <td className="px-2 py-1 text-text-primary">{r.name}</td>
                <td>{r.ticker ? <button onClick={() => onOpen(r.ticker)} className="font-mono text-bloomberg hover:underline">{r.ticker}</button> : <span className="text-text-tertiary">—</span>}</td>
                <td className="text-text-secondary">{r.evidence.slice(0, 3).map((e: string) => `“${e}”`).join(', ')}{r.evidence.length > 3 ? ` +${r.evidence.length - 3}` : ''}</td>
                <td className="text-right font-mono text-text-tertiary">{r.latest_10k}</td>
                <td className="px-2">{r.filing_url && <a href={r.filing_url} target="_blank" rel="noreferrer noopener" title="Open the filing on SEC.gov" className="text-text-tertiary hover:text-bloomberg"><ExternalLink className="w-3.5 h-3.5" /></a>}</td>
              </tr>))}</tbody>
          </table>
        </div>)}
      <div className="text-[10px] text-text-tertiary">{data.method} Searched as: {data.searched_as.join(', ')}. Foreign suppliers that don't file 10-Ks (e.g. TSMC, Foxconn) won't appear.</div>
    </div>
  );
}

// ── ECO: global economic calendar ───────────────────────────────────────────
const FLAG: Record<string, string> = { USD: 'US', EUR: 'Euro area', GBP: 'UK', JPY: 'Japan', CNY: 'China', AUD: 'Australia', CAD: 'Canada', CHF: 'Switzerland', NZD: 'New Zealand', All: 'Global' };

export function EcoGlobalView() {
  const [impact, setImpact] = useState('Medium');
  const [ccy, setCcy] = useState('');
  const area = useRegion();
  const ccyParam = ccy || REGION_CCYS[area].join(',');          // default: the Markets region's currencies
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/eco/global?days_back=14&min_impact=${impact}${ccyParam ? `&countries=${ccyParam}` : ''}`, 900_000);
  const days = useMemo(() => {
    const m = new Map<string, any[]>();
    for (const e of data?.events ?? []) { const k = String(e.date).slice(0, 10); m.set(k, [...(m.get(k) ?? []), e]); }
    return [...m.entries()];
  }, [data]);
  const today = new Date().toISOString().slice(0, 10);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1 text-xs">
        {['Low', 'Medium', 'High'].map((i) => <button key={i} onClick={() => setImpact(i)} className={cn('px-2 py-0.5 border', impact === i ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{i === 'Low' ? 'All' : `${i}+ impact`}</button>)}
        <span className="mx-2 text-text-tertiary">|</span>
        {['', 'USD', 'EUR', 'GBP', 'JPY', 'CNY', 'AUD', 'CAD', 'CHF'].map((c) => <button key={c || 'all'} onClick={() => setCcy(c)} className={cn('px-2 py-0.5 border', ccy === c ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{c ? FLAG[c] : 'All'}</button>)}
      </div>
      {loading && !data && <Loading label="Loading the calendar…" />}
      {error && <ErrorBox msg={error} />}
      {data && (
        <div className="border border-border overflow-x-auto">
          <table className="w-full text-xs">
            <thead><tr className="text-[10px] uppercase text-text-tertiary"><th className="text-left px-2 py-1 font-normal">Time</th><th className="text-left font-normal">Economy</th><th className="text-left font-normal">Release</th>
              <th className="text-right font-normal">Actual</th><th className="text-right font-normal">Consensus</th><th className="text-right font-normal">Previous</th><th className="text-right px-2 font-normal">Surprise</th></tr></thead>
            <tbody>{days.map(([day, evs]) => (
              <Fragment key={day}>
                <tr className="bg-surface-2"><td colSpan={7} className={cn('px-2 py-1 text-[11px] font-semibold', day === today ? 'text-bloomberg' : 'text-text-secondary')}>
                  {new Date(day + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'short' })}{day === today ? ' — today' : ''}</td></tr>
                {evs.map((e: any, i: number) => (
                  <tr key={day + i} className="border-t border-border-subtle">
                    <td className="px-2 py-1 font-mono text-text-tertiary">{new Date(e.date).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })}</td>
                    <td className="text-text-secondary whitespace-nowrap">{FLAG[e.country] ?? e.country}</td>
                    <td className="text-text-primary"><span className={cn('inline-block w-1.5 h-1.5 rounded-full mr-1.5', e.impact === 'High' ? 'bg-red' : e.impact === 'Medium' ? 'bg-amber' : 'bg-text-tertiary')} />{e.title}</td>
                    <td className="text-right font-mono text-text-primary">{e.actual != null ? `${e.actual}${e.unit && e.unit !== '%' ? e.unit : e.unit === '%' ? '%' : ''}` : ''}</td>
                    <td className="text-right font-mono text-text-secondary">{e.forecast ?? ''}</td>
                    <td className="text-right font-mono text-text-tertiary">{e.previous ?? ''}</td>
                    <td className={cn('text-right px-2 font-mono', e.surprise > 0 ? 'text-green' : e.surprise < 0 ? 'text-red' : '')}>{e.surprise != null ? `${e.surprise > 0 ? '+' : ''}${e.surprise}` : ''}</td>
                  </tr>))}
              </Fragment>))}</tbody>
          </table>
        </div>)}
      {data && <div className="text-[10px] text-text-tertiary">{data.note} Recording since {String(data.recorded_since ?? '').slice(0, 10) || 'today'}. Source: {data.source}.</div>}
    </div>
  );
}

// ── ECST: economic surprise index ───────────────────────────────────────────
export function EcstView() {
  const { data, error, loading } = useJSON<any>('/api/v1/mkt/ecst?start=2010-01-01', 3_600_000);
  if (loading && !data) return <Loading label="Rebuilding releases as first published (first time ~10 s)…" />;
  if (error && !data) return <ErrorBox msg={error} />;
  if (!data) return null;
  return (
    <div className="space-y-3">
      <div className="flex items-center text-xs"><span className="text-text-tertiary">US economic surprise index · weekly since 2010</span>
        <span className="ml-auto text-text-tertiary">Latest <span className={cn('font-mono text-sm', (data.latest ?? 0) >= 0 ? 'text-green' : 'text-red')}>{data.latest?.toFixed(2)}</span></span></div>
      <Panel title="Data beating (above 0) or missing (below 0) its recent trend">
        <LineChart rows={data.series} x="date" height={300} baseline={0} fmt={(v) => v.toFixed(2)}
          lines={[{ key: 'index', label: 'Surprise index', color: 'rgb(var(--c-bloomberg))' }]} />
      </Panel>
      <Panel title="Biggest surprises in the last 45 days">
        <table className="w-full text-xs"><tbody>
          {data.recent.map((r: any, i: number) => (
            <tr key={i} className="border-t border-border-subtle"><td className="py-1 font-mono text-text-tertiary">{r.date}</td><td className="text-text-primary">{SERIES_NAME[r.series] ?? r.series}</td>
              <td className={cn('text-right font-mono', r.z >= 0 ? 'text-green' : 'text-red')}>{r.z >= 0 ? '+' : ''}{r.z.toFixed(2)} σ</td></tr>))}
        </tbody></table>
      </Panel>
      <div className="text-[10px] text-text-tertiary">{data.method} Source: {data.source}.</div>
    </div>
  );
}

const SERIES_NAME: Record<string, string> = { PAYEMS: 'Non-farm payrolls', UNRATE: 'Unemployment rate (inverted)', ICSA: 'Jobless claims (inverted)',
  RSAFS: 'Retail sales', INDPRO: 'Industrial production', HOUST: 'Housing starts', PERMIT: 'Building permits', DGORDER: 'Durable goods orders', JTSJOL: 'Job openings' };
