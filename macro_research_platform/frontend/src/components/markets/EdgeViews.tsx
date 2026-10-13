// Edge data: EDGE (signal board), COT (positioning), PRED (prediction markets), NOW (nowcasts and
// trade from ship data). Sources that lead the official numbers or show who is crowded where.
import { useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { LineChart } from '@/components/ui/LineChart';
import { ErrorBox, Loading, Panel, Spark, useJSON } from './shared';

const pct = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`);
const num = (v: number | null | undefined) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${Math.round(v).toLocaleString()}`);
const tone = (v: number | null | undefined) => (v == null ? 'text-text-tertiary' : v >= 0 ? 'text-green' : 'text-red');

function Frame<T>({ url, label, refresh, children }: { url: string; label: string; refresh?: number; children: (d: T) => React.ReactNode }) {
  const { data, error, loading } = useJSON<T>(url, refresh);
  if (loading && !data) return <Loading label={label} />;
  if (error && !data) return <ErrorBox msg={error} />;
  return data ? <>{children(data)}</> : null;
}

// ── EDGE: signal board ──────────────────────────────────────────────────────
const KIND_COL: Record<string, string> = { Positioning: 'text-blue', 'Prediction markets': 'text-[rgb(168_85_247)]', Trade: 'text-amber', 'Fund flows': 'text-green' };
const KIND_EDGE: Record<string, string> = { Positioning: 'rgb(var(--c-blue))', 'Prediction markets': 'rgb(168 85 247)', Trade: 'rgb(var(--c-amber))', 'Fund flows': 'rgb(var(--c-green))' };

export function EdgeBoard({ onGo, onOpen }: { onGo: (fn: string, s?: string) => void; onOpen: (s: string) => void }) {
  const [kind, setKind] = useState('All');
  return (
    <Frame<any> url="/api/v1/mkt/edge/board" label="Scanning positioning, prediction markets, trade and fund flows…" refresh={1_800_000}>{(d) => {
      const kinds = ['All', ...new Set<string>(d.signals.map((s: any) => s.kind))];
      const list = d.signals.filter((s: any) => kind === 'All' || s.kind === kind);
      const max = Math.max(1, ...d.signals.map((s: any) => s.score));
      return (
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-1 text-[11px]">
            {kinds.map((k) => <button key={k} onClick={() => setKind(k)} className={cn('px-2 py-0.5 border', kind === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{k}</button>)}
            <span className="ml-auto text-text-tertiary">{d.generated?.replace('T', ' ')} UTC</span>
          </div>
          <ol className="space-y-1">{list.map((s: any, i: number) => (
            <li key={i} className="border border-border bg-surface-1 rounded-md px-3 py-2 flex gap-3 items-start hover:bg-surface-2 transition-colors"
              style={{ borderLeft: `3px solid ${KIND_EDGE[s.kind] ?? 'rgb(var(--c-border))'}` }}>
              <span className="w-6 text-right font-mono text-bloomberg shrink-0">{i + 1}</span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-baseline gap-2"><span className={cn('text-[10px] uppercase tracking-wide', KIND_COL[s.kind] ?? 'text-text-tertiary')}>{s.kind}</span>
                  <span className="text-sm text-text-primary">{s.title}</span></div>
                <div className="text-[11px] text-text-secondary">{s.detail}</div>
              </div>
              <div className="w-20 shrink-0 text-right">
                <div className="h-1.5 bg-surface-3"><div className="h-full bg-bloomberg" style={{ width: `${(s.score / max) * 100}%` }} /></div>
                <div className="mt-1 flex justify-end gap-1">
                  {s.symbol && <button onClick={() => onOpen(s.symbol)} className="text-[10px] font-mono text-bloomberg hover:underline">{s.symbol}</button>}
                  {s.fn && <button onClick={() => onGo(s.fn)} className="text-[10px] font-mono text-text-tertiary hover:text-bloomberg">{s.fn} ›</button>}
                </div>
              </div>
            </li>))}</ol>
          {list.length === 0 && <p className="text-xs text-text-tertiary">Nothing unusual in this category right now.</p>}
          <div className="text-[10px] text-text-tertiary">{d.note}</div>
        </div>);
    }}</Frame>
  );
}

// ── COT: positioning ────────────────────────────────────────────────────────
export function CotView() {
  const [sel, setSel] = useState<string | null>(null);
  return (
    <Frame<any> url="/api/v1/mkt/edge/cot" label="Loading CFTC positioning…">{(d) => {
      const groups = [...new Set<string>(d.markets.map((m: any) => m.group))];
      const cur = d.markets.find((m: any) => m.code === sel) ?? d.markets[0];
      return (
        <div className="grid grid-cols-1 2xl:grid-cols-[minmax(0,1fr)_520px] gap-3">
          <div className="space-y-2">
            {groups.map((g) => (
              <Panel key={g} title={g}>
                <table className="w-full text-[11px] font-mono">
                  <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Market</th><th className="text-left font-normal">Who</th><th className="text-right font-normal">Net</th>
                    <th className="text-right font-normal">% of OI</th><th className="font-normal w-40">3-year range</th><th className="text-right font-normal">1W</th><th className="text-right font-normal">4W</th><th className="font-normal">Trend</th></tr></thead>
                  <tbody>{d.markets.filter((m: any) => m.group === g).map((m: any) => (
                    <tr key={m.code} onClick={() => setSel(m.code)} className={cn('border-t border-border-subtle cursor-pointer hover:bg-surface-3', cur?.code === m.code && 'bg-surface-3')}>
                      <td className="py-0.5 font-sans text-text-primary">{m.market}{m.crowded && <span title={m.crowded === 'long' ? 'Most long (or least short) in 3 years' : 'Most short (or least long) in 3 years'}
                        className={cn('ml-1 text-[9px] px-1 border', m.crowded === 'long' ? 'border-green text-green' : 'border-red text-red')}>3y {m.crowded === 'long' ? 'high' : 'low'}</span>}</td>
                      <td className="font-sans text-text-tertiary">{m.spec_name}</td>
                      <td className={cn('text-right', tone(m.net))}>{num(m.net)}</td><td className="text-right text-text-secondary">{m.pct_oi != null ? `${(m.pct_oi * 100).toFixed(1)}%` : '—'}</td>
                      <td className="px-2"><RangeDot p={m.pct_3y} /></td>
                      <td className={cn('text-right', tone(m.chg_1w))}>{num(m.chg_1w)}</td><td className={cn('text-right', tone(m.chg_4w))}>{num(m.chg_4w)}</td>
                      <td className="pl-2"><Spark values={m.history.slice(-52).map((h: any) => h.spec)} w={60} h={14} /></td></tr>))}</tbody>
                </table>
              </Panel>))}
            <div className="text-[10px] text-text-tertiary">{d.note} {d.source}. Data as of {d.markets[0]?.date} (released the following Friday).</div>
          </div>
          {cur && <Panel title={`${cur.market} — net positions, 3 years`}>
            <LineChart rows={cur.history} x="date" height={280} fmt={(v) => Math.round(v).toLocaleString()} lines={[{ key: 'spec', label: cur.spec_name, color: 'rgb(var(--c-bloomberg))' }, { key: 'other', label: cur.other_name, color: 'rgb(var(--c-blue))' }]} />
            <div className="grid grid-cols-2 gap-2 text-[11px] mt-2">
              {[[cur.spec_name, cur], [cur.other_name, cur.other]].map(([n, s]: any) => (
                <div key={n} className="border border-border-subtle p-2"><div className="text-text-tertiary">{n}</div>
                  <div className="font-mono text-text-primary">{num(s.net)} <span className="text-text-tertiary">· {Math.round(s.pct_3y * 100)}th pct · z {s.z_3y >= 0 ? '+' : ''}{s.z_3y}</span></div>
                  <div className="text-text-tertiary">range {num(s.min_3y)} to {num(s.max_3y)}</div></div>))}
            </div>
          </Panel>}
        </div>);
    }}</Frame>
  );
}

function RangeDot({ p }: { p: number }) {
  return (
    <div className="relative h-2 bg-surface-3" title={`${Math.round(p * 100)}th percentile of 3 years`}>
      <div className="absolute inset-y-0 left-0 w-[10%] bg-red/25" /><div className="absolute inset-y-0 right-0 w-[10%] bg-green/25" />
      <div className={cn('absolute top-[-2px] w-1.5 h-3', p >= 0.9 ? 'bg-green' : p <= 0.1 ? 'bg-red' : 'bg-text-primary')} style={{ left: `calc(${p * 100}% - 3px)` }} />
    </div>
  );
}

// ── NOW: nowcasts and trade from ship data ──────────────────────────────────
export function NowView() {
  const now = useJSON<any>('/api/v1/mkt/edge/nowcasts', 3_600_000);
  const trade = useJSON<any>('/api/v1/mkt/edge/trade', 3_600_000);
  const ports = useJSON<any>('/api/v1/mkt/edge/ports', 3_600_000);
  const [sortC, setSortC] = useState<'exports_yoy' | 'imports_yoy' | 'trade_value'>('exports_yoy');
  const n = now.data;
  const lastOf = (s: any[] | null | undefined) => (s && s.length ? s[s.length - 1] : null);
  const infl = n?.infl_q ? Object.entries<any>(n.infl_q).slice(-2) : [];
  const countries = useMemo(() => [...(trade.data?.countries ?? [])].filter((c: any) => (c.exports ?? 0) > 20 || (c.imports ?? 0) > 20)
    .sort((a: any, b: any) => (b[sortC] ?? -9) - (a[sortC] ?? -9)), [trade.data, sortC]);
  return (
    <div className="space-y-3">
      {now.error && !n && <ErrorBox msg={now.error} />}
      {n && <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-1.5">
        {[['GDPNow (q/q ann.)', lastOf(n.gdpnow)?.value != null ? `${lastOf(n.gdpnow).value.toFixed(2)}%` : '—', `quarter from ${lastOf(n.gdpnow)?.date ?? '—'}`],
          ['Weekly Economic Index', lastOf(n.wei)?.value?.toFixed(2) ?? '—', `week of ${lastOf(n.wei)?.date ?? '—'}`],
          ['Financial conditions', lastOf(n.nfci)?.value?.toFixed(2) ?? '—', (lastOf(n.nfci)?.value ?? 0) > 0 ? 'tighter than average' : 'looser than average'],
          ...infl.flatMap(([q, s]: any) => [[`CPI nowcast ${q}`, s['CPI Inflation'] ? `${s['CPI Inflation'].latest.toFixed(2)}%` : '—', `core ${s['Core CPI Inflation']?.latest?.toFixed(2) ?? '—'}%`],
            [`PCE nowcast ${q}`, s['PCE Inflation'] ? `${s['PCE Inflation'].latest.toFixed(2)}%` : '—', `core ${s['Core PCE Inflation']?.latest?.toFixed(2) ?? '—'}%`]]),
          ['World seaborne trade', pct(trade.data?.world_yoy?.trade_7d), `y/y, 7 days to ${trade.data?.as_of ?? '—'}`]].map(([k, v, sub]) => (
          <div key={k as string} className="border border-border bg-surface-1 px-2.5 py-1.5"><div className="text-[10px] uppercase tracking-wide text-text-tertiary">{k}</div>
            <div className="font-mono text-text-primary">{v}</div><div className="text-[10px] text-text-tertiary">{sub}</div></div>))}
      </div>}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <Panel title="Real activity — Weekly Economic Index (≈ 4-quarter GDP growth) and financial conditions">
          {n ? <LineChart rows={mergeDates([['wei', n.wei], ['nfci', n.nfci]])} x="date" height={240} fmt={(v) => v.toFixed(2)}
            lines={[{ key: 'wei', label: 'Weekly Economic Index (%)', color: 'rgb(var(--c-blue))' }, { key: 'nfci', label: 'Financial conditions (NFCI, + = tight)', color: 'rgb(var(--c-amber))' }]} /> : <Loading />}
        </Panel>
        <Panel title="World seaborne trade — million tonnes a day (7-day average)">
          {trade.data ? <LineChart rows={trade.data.world} x="date" height={240} fmt={(v) => v.toFixed(1)}
            lines={[{ key: 'trade_7d', label: 'All cargo', color: 'rgb(var(--c-text-primary))' }, { key: 'container_7d', label: 'Container imports', color: 'rgb(var(--c-blue))' },
              { key: 'tanker_7d', label: 'Tanker imports', color: 'rgb(var(--c-red))' }, { key: 'dry_bulk_7d', label: 'Dry bulk imports', color: 'rgb(var(--c-amber))' }]} />
            : trade.error ? <ErrorBox msg={trade.error} /> : <Loading label="Loading PortWatch…" />}
        </Panel>
      </div>
      {trade.data?.regions && <Panel title={`Seaborne trade by region — last 4 weeks vs a year ago (to ${trade.data.regions[0]?.as_of})`}>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-1.5">{trade.data.regions.map((r: any) => (
          <div key={r.region} className="border border-border-subtle px-2 py-1.5 text-[11px]"><div className="text-text-secondary truncate" title={r.region}>{r.region}</div>
            <div className="font-mono">exports <span className={tone(r.exports_yoy)}>{pct(r.exports_yoy)}</span> · imports <span className={tone(r.imports_yoy)}>{pct(r.imports_yoy)}</span></div></div>))}</div>
      </Panel>}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <Panel title="Biggest ports — cargo handled, last 4 weeks">
          {ports.error && !ports.data ? <ErrorBox msg={ports.error} /> : !ports.data ? <Loading label="Loading port activity (first load ~30 s)…" /> : (
            <table className="w-full text-[11px] font-mono">
              <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Port</th><th className="text-right font-normal">k tonnes/day</th><th className="text-right font-normal">y/y</th><th className="text-right font-normal">m/m</th><th className="text-right font-normal">Calls y/y</th><th className="font-normal">90 days</th></tr></thead>
              <tbody>{ports.data.ports.map((p: any) => (
                <tr key={p.port} className="border-t border-border-subtle"><td className="py-0.5 font-sans text-text-primary">{p.port} <span className="text-text-tertiary">{p.country}</span></td>
                  <td className="text-right">{Math.round(p.tonnes_day / 1000).toLocaleString()}</td><td className={cn('text-right', tone(p.yoy))}>{pct(p.yoy, 0)}</td>
                  <td className={cn('text-right', tone(p.mom))}>{pct(p.mom, 0)}</td><td className={cn('text-right', tone(p.calls_yoy))}>{pct(p.calls_yoy, 0)}</td>
                  <td className="pl-2"><Spark values={p.spark} w={70} h={14} /></td></tr>))}</tbody>
            </table>)}
          {ports.data && <div className="text-[10px] text-text-tertiary mt-1">{ports.data.note} {ports.data.source}.</div>}
        </Panel>
        <Panel title={`Trade nowcast by country (IMF TradeNow, ${countries[0]?.month ?? '—'})`}>
          {!trade.data ? <Loading /> : (
            <div className="max-h-[520px] overflow-y-auto">
              <table className="w-full text-[11px] font-mono">
                <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left font-normal">Country</th>
                  {([['exports_yoy', 'Exports y/y'], ['imports_yoy', 'Imports y/y'], ['trade_value', 'Trade index']] as const).map(([k, l]) => (
                    <th key={k} onClick={() => setSortC(k)} className={cn('text-right font-normal cursor-pointer', sortC === k && 'text-bloomberg')}>{l}</th>))}</tr></thead>
                <tbody>{countries.map((c: any) => (
                  <tr key={c.iso3} className="border-t border-border-subtle"><td className="py-0.5 font-sans text-text-primary">{c.name}</td>
                    <td className={cn('text-right', tone(c.exports_yoy))}>{pct(c.exports_yoy, 0)}</td><td className={cn('text-right', tone(c.imports_yoy))}>{pct(c.imports_yoy, 0)}</td>
                    <td className="text-right text-text-secondary">{c.trade_value?.toFixed(0)}</td></tr>))}</tbody>
              </table>
            </div>)}
          {trade.data && <div className="text-[10px] text-text-tertiary mt-1">{trade.data.note}</div>}
        </Panel>
      </div>
      {n && <div className="text-[10px] text-text-tertiary">{n.note} Sources: {n.source}.</div>}
    </div>
  );
}

function mergeDates(series: [string, { date: string; value: number }[] | null][]) {
  const m = new Map<string, any>();
  for (const [k, s] of series) for (const p of s ?? []) { const r = m.get(p.date) ?? { date: p.date }; r[k] = p.value; m.set(p.date, r); }
  // series dated on different weekdays: carry each forward so every row has every line
  const rows = [...m.values()].sort((a, b) => a.date.localeCompare(b.date));
  const last: Record<string, number> = {};
  for (const r of rows) for (const [k] of series) { if (r[k] != null) last[k] = r[k]; else if (last[k] != null) r[k] = last[k]; }
  return rows;
}
