// Market-wide function screens: EVTS, WCRS, BTMM, IMAP, CRYPTO, CMDTY, GC, ECO, N, COMP.
import { useEffect, useMemo, useRef, useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { REGION_HEATMAP, useRegion } from '@/lib/region';
import { LineChart } from '@/components/ui/LineChart';
import { CorrelationHeatmap } from '@/components/ui/CorrelationHeatmap';
import { CATEGORICAL } from '@/lib/chartPalette';
import { Chg, ErrorBox, fmtBig, fmtPct, fmtPrice, Loading, Panel, Spark, useJSON } from './shared';

const Bp = ({ v }: { v: number | null | undefined }) => (
  <span className={cn('font-mono', v == null ? 'text-text-tertiary' : v > 0 ? 'text-red' : v < 0 ? 'text-green' : 'text-text-secondary')}>
    {v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(0)}bp`}</span>);
const sel = 'bg-surface-1 border border-border px-2 py-1 text-xs text-text-primary';

// ── EVTS ─────────────────────────────────────────────────────────────────────
export function EvtsView({ onOpen }: { onOpen: (s: string) => void }) {
  const [days, setDays] = useState(7);
  const [cap, setCap] = useState(10);
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/evts?days=${days}&min_cap_bn=${cap}&limit=250`, 1_800_000);
  const area = useRegion();
  const byDay = useMemo(() => {
    const m: Record<string, any[]> = {};
    for (const r of data?.rows ?? []) if (area === 'global' || r.region === area) (m[String(r.datetime).slice(0, 10)] ||= []).push(r);
    return Object.entries(m).sort(([a], [b]) => a.localeCompare(b));
  }, [data, area]);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center text-2xs text-text-tertiary">
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} className={sel}><option value={7}>Next 7 days</option><option value={14}>Next 14 days</option><option value={30}>Next 30 days</option></select>
        <select value={cap} onChange={(e) => setCap(Number(e.target.value))} className={sel}>
          {[[0, 'All sizes'], [2, '≥ $2bn'], [10, '≥ $10bn'], [50, '≥ $50bn'], [200, '≥ $200bn']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        {data && <span>{data.rows.length} companies</span>}
      </div>
      {loading && !data ? <Loading label="Loading earnings calendar…" /> : error ? <ErrorBox msg={error} /> : byDay.length === 0 ? <Panel><div className="text-2xs text-text-tertiary">No reports in this window.</div></Panel> : (
        byDay.map(([day, rows]) => (
          <Panel key={day} title={new Date(day + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}>
            <table className="w-full text-2xs"><tbody>{rows.map((r) => (
              <tr key={r.symbol + r.datetime} onClick={() => onOpen(r.symbol)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-3">
                <td className="py-1 w-20 font-mono text-text-primary">{r.symbol}</td><td className="text-text-secondary truncate max-w-[18rem]">{r.company}</td>
                <td className="text-text-tertiary">{r.timing}</td><td className="text-right font-mono">{fmtBig(r.market_cap)}</td>
                <td className="text-right font-mono">{r.eps_estimate != null ? `est ${r.eps_estimate.toFixed(2)}` : ''}</td>
                <td className="text-right font-mono">{r.eps_reported != null ? <>act {r.eps_reported.toFixed(2)} <Chg v={r.surprise_pct != null ? r.surprise_pct / 100 : null} d={1} /></> : ''}</td>
              </tr>))}</tbody></table>
          </Panel>)))}
    </div>
  );
}

// ── WCRS ─────────────────────────────────────────────────────────────────────
export function WcrsView({ onOpen }: { onOpen: (s: string) => void }) {
  const { data, error, loading } = useJSON<any>('/api/v1/mkt/wcrs', 300_000);
  const [view, setView] = useState<'rate' | 'chg'>('rate');
  if (loading && !data) return <Loading label="Loading FX rates…" />;
  if (error) return <ErrorBox msg={error} />;
  if (!data) return null;
  const cs: string[] = data.currencies;
  const fmt = (v: number) => (v >= 100 ? v.toFixed(2) : v >= 1 ? v.toFixed(4) : v.toFixed(5));
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 xl:grid-cols-[1fr_260px] gap-3">
        <Panel title={`Cross rates — ${view === 'rate' ? 'units of column per 1 row' : 'today’s change of row vs column'}`} right={
          <div className="flex border border-border">{([['rate', 'Rates'], ['chg', '1-day %']] as const).map(([k, l]) => (
            <button key={k} onClick={() => setView(k)} className={cn('px-2 py-0.5 text-2xs', view === k ? 'bg-bloomberg text-text-inverse' : 'text-text-secondary')}>{l}</button>))}</div>}>
          <div className="overflow-x-auto"><table className="text-[11px] font-mono tabular-nums">
            <thead><tr><th />{cs.map((c) => <th key={c} className="px-2 py-1 text-text-tertiary font-normal">{c}</th>)}</tr></thead>
            <tbody>{cs.map((b) => (
              <tr key={b} className="border-t border-border-subtle"><td className="pr-2 text-text-primary font-semibold">{b}</td>
                {cs.map((q) => {
                  const v = view === 'rate' ? data.matrix[b][q] : data.change_1d[b][q];
                  return b === q ? <td key={q} className="px-2 text-center text-text-tertiary bg-surface-2">—</td> :
                    <td key={q} onClick={() => onOpen(b === 'USD' ? `${q}=X` : `${b}${q}=X`)} title={`${b}/${q} — open chart`}
                      className={cn('px-2 text-right cursor-pointer hover:bg-surface-3', view === 'chg' && (v > 0 ? 'text-green' : v < 0 ? 'text-red' : ''))}>
                      {view === 'rate' ? fmt(v) : `${(v * 100).toFixed(2)}`}</td>;
                })}</tr>))}</tbody>
          </table></div>
        </Panel>
        <Panel title="Strength vs USD today">
          <ul className="space-y-1">{data.strength_vs_usd.map((r: any) => (
            <li key={r.ccy} className="grid grid-cols-[2.5rem_1fr_4rem] items-center gap-2 text-2xs">
              <span className="font-mono text-text-primary">{r.ccy}</span>
              <span className="relative h-2 bg-surface-3"><span className={cn('absolute top-0 h-2', r.usd_change_1d >= 0 ? 'left-1/2 bg-green' : 'right-1/2 bg-red')}
                style={{ width: `${Math.min(50, Math.abs(r.usd_change_1d) * 5000)}%` }} /></span>
              <Chg v={r.usd_change_1d} /></li>))}</ul>
        </Panel>
      </div>
      <div className="text-[10px] text-text-tertiary">{data.note} {data.source} · {data.as_of}</div>
    </div>
  );
}

// ── BTMM ─────────────────────────────────────────────────────────────────────
export function BtmmView() {
  const { data, error, loading } = useJSON<any>('/api/v1/mkt/btmm', 3_600_000);
  if (loading && !data) return <Loading label="Loading money markets from FRED…" />;
  if (error) return <ErrorBox msg={error} />;
  if (!data) return null;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {data.groups.map((g: any) => (
          <Panel key={g.group} title={g.group}>
            <table className="w-full text-2xs"><thead><tr className="text-text-tertiary"><th className="text-left font-normal">Rate</th><th className="text-right font-normal">Level</th>
              <th className="text-right font-normal">1W</th><th className="text-right font-normal">1M</th><th className="text-right font-normal">1Y</th><th className="text-right font-normal hidden md:table-cell">3M</th></tr></thead>
              <tbody>{g.rows.map((r: any) => (
                <tr key={r.series} className="border-t border-border-subtle" title={`FRED ${r.series}${r.date ? ` · ${r.date}` : ''}`}>
                  <td className="py-1 text-text-primary">{r.name}</td><td className="text-right font-mono text-text-primary">{r.value == null ? '—' : `${r.value.toFixed(2)}%`}</td>
                  <td className="text-right"><Bp v={r.change_1w_bp} /></td><td className="text-right"><Bp v={r.change_1m_bp} /></td><td className="text-right"><Bp v={r.change_1y_bp} /></td>
                  <td className="text-right hidden md:table-cell"><Spark values={r.spark} /></td></tr>))}</tbody></table>
          </Panel>))}
      </div>
      <div className="text-[10px] text-text-tertiary">{data.source} · {data.units}. Rising rates shown red (bond prices fall).</div>
    </div>
  );
}

// ── IMAP (squarified treemap) ────────────────────────────────────────────────
type Rect = { x: number; y: number; w: number; h: number };
function squarify<T extends { value: number }>(items: T[], r: Rect): (T & Rect)[] {
  const out: (T & Rect)[] = [];
  const total = items.reduce((a, b) => a + b.value, 0);
  if (!total) return out;
  let rect = { ...r };
  let rest = items.map((it) => ({ ...it, area: (it.value / total) * r.w * r.h }));
  while (rest.length) {
    const short = Math.min(rect.w, rect.h);
    let row: typeof rest = [];
    let best = Infinity;
    for (const it of rest) {
      const cand = [...row, it];
      const s = cand.reduce((a, b) => a + b.area, 0);
      const worst = Math.max(...cand.map((c) => Math.max((short * short * c.area) / (s * s), (s * s) / (short * short * c.area))));
      if (worst > best && row.length) break;
      best = worst;
      row = cand;
    }
    const s = row.reduce((a, b) => a + b.area, 0);
    const horiz = rect.w >= rect.h;
    const thick = s / short;
    let off = 0;
    for (const it of row) {
      const len = it.area / thick;
      out.push({ ...(it as any), ...(horiz ? { x: rect.x, y: rect.y + off, w: thick, h: len } : { x: rect.x + off, y: rect.y, w: len, h: thick }) });
      off += len;
    }
    rect = horiz ? { x: rect.x + thick, y: rect.y, w: rect.w - thick, h: rect.h } : { x: rect.x, y: rect.y + thick, w: rect.w, h: rect.h - thick };
    rest = rest.slice(row.length);
  }
  return out;
}

const heatColor = (v: number | null) => {
  if (v == null) return 'rgb(var(--c-surface-3))';
  const a = Math.min(1, Math.abs(v) / 0.03) * 0.85 + 0.15;
  return v >= 0 ? `rgb(var(--c-green) / ${a})` : `rgb(var(--c-red) / ${a})`;
};

export function ImapView({ onOpen }: { onOpen: (s: string) => void }) {
  const area = useRegion();
  const [country, setCountry] = useState(REGION_HEATMAP[area]);
  useEffect(() => { setCountry(REGION_HEATMAP[area]); }, [area]);            // follow the Markets region
  const [period, setPeriod] = useState<'change_1d' | 'change_5d'>('change_1d');
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/imap?country=${country}&max_names=${country === 'US' ? 300 : 150}`, 300_000);
  // Lay out at the container's real pixel size so labels stay legible on any screen.
  const box = useRef<HTMLDivElement>(null);
  const [W, setW] = useState(1000);
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(320, Math.round(e.contentRect.width))));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const H = Math.max(420, Math.min(760, Math.round(W * 0.62)));
  const tiles = useMemo(() => {
    if (!data) return [];
    const secs = squarify(data.sectors.map((s: any) => ({ ...s, value: s.market_cap_usd || 0 })), { x: 0, y: 0, w: W, h: H });
    return secs.flatMap((s: any) => {
      const pad = 14;
      const inner = { x: s.x + 1, y: s.y + pad, w: Math.max(0, s.w - 2), h: Math.max(0, s.h - pad - 1) };
      const stocks = data.rows.filter((r: any) => r.sector === s.sector && r.market_cap_usd).sort((a: any, b: any) => b.market_cap_usd - a.market_cap_usd)
        .map((r: any) => ({ ...r, value: r.market_cap_usd }));
      return [{ kind: 'sector', ...s }, ...squarify(stocks, inner).map((t: any) => ({ kind: 'stock', ...t }))];
    });
  }, [data, W, H]);
  const countries = data?.countries ?? ['US', 'JP', 'GB', 'DE', 'FR', 'CN', 'IN', 'CA', 'AU', 'KR', 'TW', 'HK', 'CH'];
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 items-center">
        <select value={country} onChange={(e) => setCountry(e.target.value)} className={sel}>{countries.map((c: string) => <option key={c}>{c}</option>)}</select>
        <div className="flex border border-border">{([['change_1d', '1 day'], ['change_5d', '5 days']] as const).map(([k, l]) => (
          <button key={k} onClick={() => setPeriod(k)} className={cn('px-2 py-1 text-2xs', period === k ? 'bg-bloomberg text-text-inverse' : 'text-text-secondary')}>{l}</button>))}</div>
        <span className="text-2xs text-text-tertiary">Tile size = market value · colour = move (full colour at ±3%) · click to open</span>
      </div>
      <div ref={box} className="w-full" />
      {loading && !data ? <Loading label="Loading heatmap…" /> : error ? <ErrorBox msg={error} /> : data && (
        <div className="bg-surface-1 border border-border p-1">
          <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label={`${country} market heatmap`}>
            {tiles.map((t: any, i: number) => t.kind === 'sector' ? (
              <g key={`s${i}`}><rect x={t.x} y={t.y} width={t.w} height={t.h} fill="var(--surface-2)" stroke="var(--bg)" strokeWidth="2" />
                {t.w > 60 && <text x={t.x + 4} y={t.y + 10} fontSize="9" fill="var(--text-secondary)" className="uppercase">{t.sector} {t.change_1d != null ? `${(t.change_1d * 100).toFixed(1)}%` : ''}</text>}</g>
            ) : (
              <g key={t.symbol} onClick={() => onOpen(t.symbol)} className="cursor-pointer">
                <rect x={t.x} y={t.y} width={t.w} height={t.h} fill={heatColor(t[period])} stroke="var(--bg)" strokeWidth="1"><title>{`${t.name} (${t.symbol}) ${t[period] != null ? (t[period] * 100).toFixed(2) + '%' : '—'} · $${fmtBig(t.market_cap_usd)}`}</title></rect>
                {t.w > 34 && t.h > 18 && <text x={t.x + t.w / 2} y={t.y + t.h / 2} fontSize={Math.min(14, Math.max(7, t.w / 6))} textAnchor="middle" fill="var(--text-primary)" pointerEvents="none">
                  <tspan x={t.x + t.w / 2} dy="-0.1em" fontWeight="600">{t.symbol.split('.')[0]}</tspan>
                  {t.h > 32 && <tspan x={t.x + t.w / 2} dy="1.2em" fontSize={Math.min(11, Math.max(7, t.w / 8))}>{t[period] != null ? `${(t[period] * 100).toFixed(1)}%` : ''}</tspan>}</text>}
              </g>))}
          </svg>
        </div>
      )}
      {data && <div className="text-[10px] text-text-tertiary">{data.note} {data.source}.</div>}
    </div>
  );
}

// ── CRYPTO ───────────────────────────────────────────────────────────────────
export function CryptoView({ onOpen }: { onOpen: (s: string) => void }) {
  const { data, error, loading } = useJSON<any>('/api/v1/mkt/crypto?limit=100', 180_000);
  if (loading && !data) return <Loading label="Loading crypto…" />;
  if (error) return <ErrorBox msg={error} />;
  if (!data) return null;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Panel><div className="text-[10px] uppercase text-text-tertiary">Total market cap (top 100)</div><div className="font-mono text-base">${fmtBig(data.total_market_cap)}</div></Panel>
        <Panel><div className="text-[10px] uppercase text-text-tertiary">Bitcoin dominance</div><div className="font-mono text-base">{fmtPct(data.btc_dominance, 1).replace('+', '')}</div></Panel>
      </div>
      <Panel title="Top coins by market cap — click to chart">
        <div className="overflow-x-auto"><table className="w-full text-2xs">
          <thead><tr className="text-text-tertiary">{['#', 'Coin', 'Price', '1h', '24h', '7d', '30d', 'Market cap', 'Volume 24h', 'From ATH', '7 days'].map((h) =>
            <th key={h} className={cn('font-normal py-1', h === 'Coin' || h === '#' ? 'text-left' : 'text-right')}>{h}</th>)}</tr></thead>
          <tbody>{data.rows.map((r: any) => (
            <tr key={r.symbol} onClick={() => onOpen(r.symbol)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-3">
              <td className="text-text-tertiary py-1">{r.rank}</td><td><span className="font-mono text-text-primary">{r.coin}</span> <span className="text-text-secondary">{r.name}</span></td>
              <td className="text-right font-mono">{fmtPrice(r.price)}</td><td className="text-right"><Chg v={r.change_1h} d={1} /></td><td className="text-right"><Chg v={r.change_24h} d={1} /></td>
              <td className="text-right"><Chg v={r.change_7d} d={1} /></td><td className="text-right"><Chg v={r.change_30d} d={1} /></td>
              <td className="text-right font-mono">{fmtBig(r.market_cap)}</td><td className="text-right font-mono">{fmtBig(r.volume_24h)}</td>
              <td className="text-right"><Chg v={r.ath_change} d={0} /></td><td className="text-right"><Spark values={r.spark} /></td></tr>))}</tbody>
        </table></div>
      </Panel>
      <div className="text-[10px] text-text-tertiary">{data.source}. Charts open the Yahoo USD pair, which may not exist for small coins.</div>
    </div>
  );
}

// ── CMDTY ────────────────────────────────────────────────────────────────────
export function CmdtyView({ onOpen }: { onOpen: (s: string) => void }) {
  const roots = useJSON<any>('/api/v1/mkt/futures');
  const [root, setRoot] = useState('CL');
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/futures/${root}?n=12`, 600_000);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-1">{(roots.data?.roots ?? []).map((r: any) => (
        <button key={r.root} onClick={() => setRoot(r.root)} className={cn('px-2 py-1 text-2xs border', root === r.root ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary hover:text-text-primary')}>{r.name}</button>))}</div>
      {loading && !data ? <Loading label="Loading futures curve…" /> : error ? <ErrorBox msg={error} /> : data && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            <Panel><div className="text-[10px] uppercase text-text-tertiary">Front month</div><div className="font-mono text-base">{fmtPrice(data.front.price)}</div><div className="text-[10px] text-text-tertiary">{data.front.contract}</div></Panel>
            <Panel><div className="text-[10px] uppercase text-text-tertiary">Curve shape</div><div className={cn('text-sm', data.slope < 0 ? 'text-green' : 'text-amber')}>{data.shape}</div></Panel>
            <Panel><div className="text-[10px] uppercase text-text-tertiary">Front → back</div><div className="font-mono text-base"><Chg v={data.slope} d={1} /></div></Panel>
            <Panel><div className="text-[10px] uppercase text-text-tertiary">Roll yield / yr</div><div className="font-mono text-base"><Chg v={data.annualised_roll_yield} d={1} /></div></Panel>
          </div>
          <Panel title={`${data.name} — futures curve (${data.exchange})`}>
            <LineChart rows={data.points} x="month" height={260} lines={[{ key: 'price', label: data.name, color: CATEGORICAL[3] }]} fmt={(v) => fmtPrice(v)} />
            <table className="w-full text-2xs font-mono mt-3"><tbody>{data.points.map((p: any) => (
              <tr key={p.contract} onClick={() => onOpen(p.contract)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-3">
                <td className="py-0.5 text-text-secondary">{p.month}</td><td className="text-text-tertiary">{p.contract}</td><td className="text-right">{fmtPrice(p.price)}</td><td className="text-right"><Chg v={p.change_1d} /></td></tr>))}</tbody></table>
          </Panel>
          <div className="text-[10px] text-text-tertiary">{data.note} {data.source}.</div>
        </>
      )}
    </div>
  );
}

// ── GC ───────────────────────────────────────────────────────────────────────
const COUNTRY: Record<string, string> = { US: 'United States', UK: 'United Kingdom', DE: 'Germany', JP: 'Japan', CA: 'Canada', AU: 'Australia' };
export function GcView() {
  const { data, error, loading } = useJSON<any>('/api/rates', 900_000);
  if (loading && !data) return <Loading label="Loading yield curves…" />;
  if (error) return <ErrorBox msg={error} />;
  if (!data?.yieldCurves) return <ErrorBox msg="Yield curve data unavailable." />;
  const curves = data.yieldCurves as Record<string, any>;
  const label = (t: number) => (t < 1 ? `${Math.round(t * 12)}M` : `${+t.toFixed(1)}Y`);
  const tenors = Array.from(new Set(Object.values(curves).flatMap((c: any) => (c?.points ?? []).map((p: any) => Number(p.tenor))))).sort((a, b) => a - b);
  const rows = tenors.map((t) => ({ tenor: label(t), ...Object.fromEntries(Object.entries(curves).map(([k, c]: [string, any]) =>
    [k, (c?.points ?? []).find((p: any) => Math.abs(Number(p.tenor) - t) < 1e-6)?.yield ?? null])) }));
  const keys = Object.keys(curves);
  return (
    <div className="space-y-3">
      <Panel title="Government yield curves">
        <LineChart rows={rows} x="tenor" height={300} lines={keys.map((k, i) => ({ key: k, label: COUNTRY[k] ?? k, color: CATEGORICAL[i % CATEGORICAL.length] }))} fmt={(v) => `${v.toFixed(2)}%`} />
      </Panel>
      <Panel title="Yields by tenor (%)">
        <div className="overflow-x-auto"><table className="w-full text-2xs font-mono">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Tenor</th>{keys.map((k) => <th key={k} className="text-right font-normal">{COUNTRY[k] ?? k}</th>)}</tr></thead>
          <tbody>{rows.map((r: any) => (<tr key={r.tenor} className="border-t border-border-subtle"><td className="text-text-secondary py-0.5">{r.tenor}</td>
            {keys.map((k) => <td key={k} className="text-right">{r[k] == null ? '—' : Number(r[k]).toFixed(2)}</td>)}</tr>))}</tbody>
        </table></div>
      </Panel>
      {data.creditSpreads?.length > 0 && <Panel title="US credit spreads">
        <div className="grid grid-cols-3 gap-2">{data.creditSpreads.map((c: any) => (
          <div key={c.name}><div className="text-[10px] uppercase text-text-tertiary">{c.name}</div><div className="font-mono">{c.spreadBps}bp <Bp v={c.change1wBps} /> <span className="text-text-tertiary">1w</span></div></div>))}</div>
      </Panel>}
      <div className="text-[10px] text-text-tertiary">Sources: US Treasury / FRED and national data as used in the Research mode's Yield Curve panel. Last updated {data.lastUpdated ?? '—'}.</div>
    </div>
  );
}

// ── ECO ──────────────────────────────────────────────────────────────────────
export function EcoView() {
  const { data, error, loading } = useJSON<any>('/api/calendar', 900_000);
  if (loading && !data) return <Loading label="Loading economic calendar…" />;
  if (error) return <ErrorBox msg={error} />;
  if (!data) return null;
  const rows = data.upcoming ?? [];
  return (
    <Panel title="Upcoming US economic releases">
      <table className="w-full text-2xs"><thead><tr className="text-text-tertiary"><th className="text-left font-normal">When</th><th className="text-left font-normal">Release</th>
        <th className="text-left font-normal">Importance</th><th className="text-right font-normal">Previous</th><th className="text-right font-normal">Forecast</th><th className="text-right font-normal">Actual</th></tr></thead>
        <tbody>{rows.map((r: any) => (
          <tr key={r.id + r.event_name + r.release_datetime} className="border-t border-border-subtle">
            <td className="py-1 font-mono text-text-secondary whitespace-nowrap">{new Date(r.release_datetime).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
            <td className="text-text-primary">{r.event_name}</td>
            <td><span className={cn('px-1.5 border text-[10px]', r.importance === 'HIGH' ? 'border-red/50 text-red' : r.importance === 'MEDIUM' ? 'border-amber/50 text-amber' : 'border-border text-text-tertiary')}>{r.importance}</span></td>
            <td className="text-right font-mono">{r.previous ?? '—'}</td><td className="text-right font-mono">{r.forecast ?? '—'}</td><td className="text-right font-mono text-text-primary">{r.actual ?? '—'}</td></tr>))}</tbody></table>
      <div className="text-[10px] text-text-tertiary mt-2">Times in your local time zone. Sources: {(data.events?.[0]?.source) ?? 'FRED release calendar'}. Consensus forecasts are not available from free sources.</div>
    </Panel>
  );
}

// ── N ────────────────────────────────────────────────────────────────────────
export function NewsView() {
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [src, setSrc] = useState('');
  const area = useRegion();
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/news?limit=150${area !== 'global' ? `&region=${area}` : ''}${query ? `&q=${encodeURIComponent(query)}` : ''}`, 600_000);
  const items = (data?.items ?? []).filter((i: any) => !src || i.source === src);
  return (
    <div className="space-y-3">
      <form onSubmit={(e) => { e.preventDefault(); setQuery(q.trim()); }} className="flex flex-wrap gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search headlines — e.g. Fed, oil, Nvidia, China" className="flex-1 min-w-[14rem] bg-surface-1 border border-border px-3 py-1.5 text-xs text-text-primary" />
        <select value={src} onChange={(e) => setSrc(e.target.value)} className={sel}><option value="">All sources</option>{(data?.sources ?? []).map((s: string) => <option key={s}>{s}</option>)}</select>
        <button className="px-3 py-1.5 text-xs bg-bloomberg text-text-inverse">Search</button>
      </form>
      {loading && !data ? <Loading label="Loading headlines…" /> : error ? <ErrorBox msg={error} /> : (
        <Panel title={`${items.length} headlines${query ? ` matching “${query}”` : ''}`}>
          <ul className="divide-y divide-border-subtle">{items.map((n: any, i: number) => (
            <li key={i} className="py-2 grid grid-cols-[4.5rem_1fr] gap-3">
              <div className="text-[10px] text-text-tertiary font-mono">{n.time ? new Date(n.time).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : ''}<br />
                {n.time ? new Date(n.time).toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) : ''}</div>
              <div className="min-w-0">
                <a href={n.url} target="_blank" rel="noreferrer noopener" className="text-xs text-text-primary hover:text-bloomberg inline-flex items-start gap-1">{n.title}<ExternalLink className="w-3 h-3 shrink-0 mt-0.5 text-text-tertiary" /></a>
                {n.summary && <p className="text-2xs text-text-secondary line-clamp-2 mt-0.5">{n.summary}</p>}
                <div className="text-[10px] text-text-tertiary mt-0.5">{n.source} · tone <span className={n.sentiment > 0.15 ? 'text-green' : n.sentiment < -0.15 ? 'text-red' : ''}>{n.sentiment > 0.15 ? 'positive' : n.sentiment < -0.15 ? 'negative' : 'neutral'}</span></div>
              </div>
            </li>))}</ul>
        </Panel>
      )}
    </div>
  );
}

// ── COMP ─────────────────────────────────────────────────────────────────────
export function CompView({ seed }: { seed?: string }) {
  const [text, setText] = useState(seed ? `${seed}, SPY` : 'SPY, QQQ, GLD, TLT, BTC-USD');
  const [period, setPeriod] = useState('5y');
  const [syms, setSyms] = useState(text);
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/comp?symbols=${encodeURIComponent(syms.replace(/\s/g, ''))}&period=${period}`);
  return (
    <div className="space-y-3">
      <form onSubmit={(e) => { e.preventDefault(); setSyms(text); }} className="flex flex-wrap gap-2">
        <input value={text} onChange={(e) => setText(e.target.value.toUpperCase())} className="flex-1 min-w-[16rem] bg-surface-1 border border-border px-3 py-1.5 text-xs font-mono text-text-primary" placeholder="Up to 8 symbols, comma separated" />
        <select value={period} onChange={(e) => setPeriod(e.target.value)} className={sel}>{['1mo', '3mo', '6mo', 'ytd', '1y', '2y', '5y', '10y', 'max'].map((p) => <option key={p}>{p}</option>)}</select>
        <button className="px-3 py-1.5 text-xs bg-bloomberg text-text-inverse">Compare</button>
      </form>
      {loading && !data ? <Loading /> : error ? <ErrorBox msg={error} /> : data && (
        <>
          <Panel title={`Growth of 1 since ${data.start} (total return)`}>
            <LineChart rows={data.curve} x="date" height={300} log baseline={1} fmt={(v) => `${v.toFixed(2)}×`}
              lines={data.symbols.map((s: string, i: number) => ({ key: s, label: s, color: CATEGORICAL[i % CATEGORICAL.length] }))} />
          </Panel>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <Panel title="Return and risk">
              <table className="w-full text-2xs font-mono"><thead><tr className="text-text-tertiary"><th className="text-left font-normal">Symbol</th><th className="text-right font-normal">Total</th>
                <th className="text-right font-normal">Per year</th><th className="text-right font-normal">Volatility</th><th className="text-right font-normal">Return/vol</th><th className="text-right font-normal">Max drawdown</th></tr></thead>
                <tbody>{data.stats.map((s: any) => (<tr key={s.symbol} className="border-t border-border-subtle"><td className="text-text-primary py-0.5">{s.symbol}</td>
                  <td className="text-right"><Chg v={s.total_return} d={0} /></td><td className="text-right"><Chg v={s.cagr} d={1} /></td><td className="text-right">{(s.vol * 100).toFixed(1)}%</td>
                  <td className="text-right">{s.sharpe != null ? s.sharpe.toFixed(2) : '—'}</td><td className="text-right text-red">{(s.max_drawdown * 100).toFixed(0)}%</td></tr>))}</tbody></table>
              {data.missing.length > 0 && <div className="text-[10px] text-amber mt-1">No data for: {data.missing.join(', ')}</div>}
            </Panel>
            <Panel title="Correlation of daily returns">
              <CorrelationHeatmap labels={data.symbols} matrix={data.symbols.map((a: string) => data.symbols.map((b: string) => data.correlation[a][b]))} />
            </Panel>
          </div>
          <div className="text-[10px] text-text-tertiary">{data.note}</div>
        </>
      )}
    </div>
  );
}
