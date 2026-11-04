// Market-wide function screens: EVTS, WCRS, BTMM, IMAP, CRYPTO, CMDTY, GC, ECO, N, COMP.
import { useEffect, useMemo, useRef, useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { REGION_HEATMAP, useRegion } from '@/lib/region';
import { LineChart } from '@/components/ui/LineChart';
import { PriceChart } from '@/components/ui/PriceChart';
import { CorrelationHeatmap } from '@/components/ui/CorrelationHeatmap';
import { CATEGORICAL } from '@/lib/chartPalette';
import { EChart, axisStyle, color, inkOn, over, useChartTheme } from '@/components/charts/EChart';
import { Chg, ErrorBox, fmtBig, fmtPct, fmtPrice, Loading, Panel, Spark, useJSON, useSort } from './shared';

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
      <div className="mkt-controls flex flex-wrap gap-2 items-center text-2xs text-text-tertiary">
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} className={sel}><option value={7}>Next 7 days</option><option value={14}>Next 14 days</option><option value={30}>Next 30 days</option></select>
        <select value={cap} onChange={(e) => setCap(Number(e.target.value))} className={sel}>
          {[[0, 'All sizes'], [2, '≥ $2bn'], [10, '≥ $10bn'], [50, '≥ $50bn'], [200, '≥ $200bn']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
        {data && <span>{data.rows.length} companies · {data.source}</span>}
      </div>
      {loading && !data ? <Loading label="Loading earnings calendar…" /> : error ? <ErrorBox msg={error} /> : byDay.length === 0 ? <Panel><div className="text-2xs text-text-tertiary">No reports in this window.</div></Panel> : (
        byDay.map(([day, rows]) => (
          <Panel key={day} title={new Date(day + 'T12:00:00').toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}>
            <div className="mkt-table-scroll" tabIndex={0} role="group" aria-label="Scrollable market data table"><table className="w-full text-2xs table-fixed"><tbody>{rows.map((r) => (
              <tr key={r.symbol + r.datetime} onClick={() => onOpen(r.home_symbol ?? r.symbol)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-3"
                title={r.home_symbol ? `${r.symbol} trades over the counter in the US; opens the home listing ${r.home_symbol}` : undefined} tabIndex={0} onKeyDown={e=>{if(e.key==='Enter'&&e.target===e.currentTarget){e.preventDefault();e.currentTarget.click();}}}>
                <td className="py-1 w-24 font-mono text-text-primary">{r.home_symbol ?? r.symbol}</td><td className="text-text-secondary truncate max-w-[18rem]">{r.company}</td>
                <td className="w-28 text-text-tertiary">{r.timing}</td><td className="w-24 text-right font-mono">{fmtBig(r.market_cap)}</td>
                <td className="w-24 text-right font-mono">{r.eps_estimate != null ? `est ${r.eps_estimate.toFixed(2)}` : ''}</td>
                <td className="w-28 text-right font-mono text-text-tertiary" title="Revenue estimate → reported (FMP)">{r.revenue_estimate != null ? <>rev {fmtBig(r.revenue_estimate)}{r.revenue_reported != null ? <> → <span className={r.revenue_reported >= r.revenue_estimate ? 'text-green' : 'text-red'}>{fmtBig(r.revenue_reported)}</span></> : null}</> : ''}</td>
                <td className="w-40 text-right font-mono">{r.eps_reported != null ? <>act {r.eps_reported.toFixed(2)} <Chg v={r.surprise_pct != null ? r.surprise_pct / 100 : null} d={1} /></> : ''}</td>
              </tr>))}</tbody></table></div>
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
            <div className="mkt-table-scroll" tabIndex={0} role="group" aria-label="Scrollable market data table"><table className="w-full text-2xs"><thead><tr className="text-text-tertiary"><th className="text-left font-normal">Rate</th><th className="text-right font-normal">Level</th>
              <th className="text-right font-normal">1W</th><th className="text-right font-normal">1M</th><th className="text-right font-normal">3M</th><th className="text-right font-normal">1Y</th><th className="text-right font-normal hidden md:table-cell">90d</th></tr></thead>
              <tbody>{g.rows.map((r: any) => (
                <tr key={r.series} className="border-t border-border-subtle" title={`FRED ${r.series}${r.date ? ` · ${r.date}` : ''}`}>
                  <td className="py-1 text-text-primary">{r.name}</td><td className="text-right font-mono text-text-primary">{r.value == null ? '—' : `${r.value.toFixed(2)}%`}</td>
                  <td className="text-right"><Bp v={r.change_1w_bp} /></td><td className="text-right"><Bp v={r.change_1m_bp} /></td><td className="text-right"><Bp v={r.change_3m_bp} /></td><td className="text-right"><Bp v={r.change_1y_bp} /></td>
                  <td className="text-right hidden md:table-cell"><Spark values={r.spark} /></td></tr>))}</tbody></table></div>
          </Panel>))}
      </div>
      <div className="text-[10px] text-text-tertiary">{data.source} · {data.units}. Rising rates shown red (bond prices fall).</div>
    </div>
  );
}

// ── IMAP (treemap: sector → stock, sized by market value, coloured by the move) ──
const heatColor = (v: number | null) => {
  if (v == null) return 'rgb(var(--c-surface-3))';
  const a = Math.min(1, Math.abs(v) / 0.03) * 0.85 + 0.15;
  return v >= 0 ? `rgb(var(--c-green) / ${a})` : `rgb(var(--c-red) / ${a})`;
};

function MarketTreemap({ data, period, country, onOpen }: { data: any; period: 'change_1d' | 'change_5d'; country: string; onOpen: (s: string) => void }) {
  const t = useChartTheme();
  const openRef = useRef(onOpen);
  openRef.current = onOpen;
  const option = useMemo(() => {
    const pctTxt = (v: number | null | undefined) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(1)}%`);
    const total = data.rows.reduce((a: number, r: any) => a + (r.market_cap_usd || 0), 0) || 1;
    const tree = data.sectors.filter((s: any) => s.market_cap_usd).map((s: any) => ({
      name: s.sector, value: s.market_cap_usd, sector: s,
      children: data.rows.filter((r: any) => r.sector === s.sector && r.market_cap_usd).map((r: any) => ({
        name: String(r.symbol).split('.')[0], value: r.market_cap_usd, row: r, itemStyle: { color: over(color(heatColor(r[period])), t.surface1) } })) }));
    return {
      legend: { show: false }, toolbox: { show: false },
      tooltip: { formatter: (q: any) => { const r = q.data?.row, s = q.data?.sector;
        if (r) return `<b>${r.name}</b> <span style="opacity:.6">${r.symbol}</span><br/>${pctTxt(r[period])} · $${fmtBig(r.market_cap_usd)}<br/><span style="opacity:.6">click to open</span>`;
        return s ? `<b>${s.sector}</b><br/>${pctTxt(s[period])} · $${fmtBig(s.market_cap_usd)}` : ''; } },
      series: [{
        type: 'treemap', left: 0, right: 0, top: 0, bottom: 0, roam: false, nodeClick: false, breadcrumb: { show: false }, squareRatio: 0.5 * (1 + Math.sqrt(5)),
        data: tree,
        levels: [
          { itemStyle: { borderColor: t.surface1, borderWidth: 0, gapWidth: 3 } },                // the root
          { itemStyle: { color: t.surface, borderColor: t.surface, borderWidth: 2, gapWidth: 1 },
            upperLabel: { show: true, height: 16, color: t.text, fontSize: 9, backgroundColor: t.surface,
              formatter: (q: any) => `${String(q.name).toUpperCase()}  ${pctTxt(q.data?.sector?.[period])}` } },
          { itemStyle: { borderColor: t.surface1, borderWidth: 1, gapWidth: 1, borderRadius: 2 },
            emphasis: { itemStyle: { borderColor: t.textStrong, borderWidth: 1 } },
            label: { show: true, color: '#fff', overflow: 'truncate', ellipsis: '', lineHeight: 14,
              // label only tiles big enough to hold it (share of the whole map's value)
              formatter: (q: any) => { const f = (q.value ?? 0) / total;
                return f < 0.0025 ? '' : f < 0.006 ? `{s|${q.name}}` : `{s|${q.name}}\n{p|${pctTxt(q.data?.row?.[period])}}`; },
              rich: { s: { fontWeight: 600, fontSize: 12, color: '#fff' }, p: { fontSize: 10, color: 'rgba(255,255,255,.85)', fontFamily: t.mono } } } },
        ],
      }],
    };
  }, [data, period, t]);
  return <EChart option={option} height={620} ariaLabel={`${country} market heatmap`}
    onReady={(c) => c.on('click', (q: any) => { const r = q.data?.row; if (r) openRef.current(r.symbol); })} />;
}

export function ImapView({ onOpen }: { onOpen: (s: string) => void }) {
  const area = useRegion();
  const [country, setCountry] = useState(REGION_HEATMAP[area]);
  useEffect(() => { setCountry(REGION_HEATMAP[area]); }, [area]);            // follow the Markets region
  const [period, setPeriod] = useState<'change_1d' | 'change_5d'>('change_1d');
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/imap?country=${country}&max_names=${country === 'US' ? 300 : 150}`, 300_000);
  const countries = data?.countries ?? ['US', 'JP', 'GB', 'DE', 'FR', 'CN', 'IN', 'CA', 'AU', 'KR', 'TW', 'HK', 'CH'];
  return (
    <div className="space-y-3">
      <div className="mkt-controls flex flex-wrap gap-2 items-center">
        <select value={country} onChange={(e) => setCountry(e.target.value)} className={sel}>{countries.map((c: string) => <option key={c}>{c}</option>)}</select>
        <div className="flex border border-border">{([['change_1d', '1 day'], ['change_5d', '5 days']] as const).map(([k, l]) => (
          <button key={k} onClick={() => setPeriod(k)} className={cn('px-2 py-1 text-2xs', period === k ? 'bg-bloomberg text-text-inverse' : 'text-text-secondary')}>{l}</button>))}</div>
        <span className="text-2xs text-text-tertiary">Tile size = market value · colour = move (full colour at ±3%) · click to open</span>
      </div>
      {loading && !data ? <Loading label="Loading heatmap (first build after a restart ~25 s)…" /> : error ? <ErrorBox msg={error} /> : data && (
        <div className="bg-surface-1 border border-border p-1">
          <MarketTreemap data={data} period={period} country={country} onOpen={onOpen} />
        </div>
      )}
      {data && <div className="text-[10px] text-text-tertiary">{data.note} {data.source}.</div>}
    </div>
  );
}

// ── CRYPTO ───────────────────────────────────────────────────────────────────
export function CryptoView({ onOpen }: { onOpen: (s: string) => void }) {
  const { data, error, loading } = useJSON<any>('/api/v1/mkt/crypto?limit=100', 180_000);
  const { rows, th } = useSort(data?.rows);
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
          <thead><tr className="text-text-tertiary">
            {th('rank', '#', 'text-left py-1', false)}{th('name', 'Coin', 'text-left', false)}{th('price', 'Price', 'text-right')}
            {th('change_1h', '1h', 'text-right')}{th('change_24h', '24h', 'text-right')}{th('change_7d', '7d', 'text-right')}{th('change_30d', '30d', 'text-right')}
            {th('market_cap', 'Market cap', 'text-right')}{th('volume_24h', 'Volume 24h', 'text-right')}{th('ath_change', 'From ATH', 'text-right')}
            <th className="font-normal text-right">7 days</th></tr></thead>
          <tbody>{rows.map((r: any) => (
            <tr key={r.symbol} onClick={() => onOpen(r.symbol)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-3" tabIndex={0} onKeyDown={e=>{if(e.key==='Enter'&&e.target===e.currentTarget){e.preventDefault();e.currentTarget.click();}}}>
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
/** A futures curve on a true time axis (contracts years out sit where they belong), with the same
 *  contracts a month and a year ago as dashed overlays. */
function FuturesCurve({ pts, name, show }: { pts: any[]; name: string; show: { m1: boolean; y1: boolean } }) {
  const t = useChartTheme();
  const option = useMemo(() => {
    const ax = axisStyle(t);
    const at = (m: string) => `${m}-15`;
    const line = (key: string, label: string, c: string, style: any, width: number, z: number) => ({ name: label, type: 'line', z,
      data: pts.filter((p) => p[key] != null).map((p) => ({ value: [at(p.month), p[key]], contract: p.contract })), showSymbol: key === 'price', symbol: 'circle', symbolSize: 5,
      lineStyle: { color: c, width, type: style }, itemStyle: { color: c, borderColor: t.surface1, borderWidth: 1 } });
    const nowC = CATEGORICAL[3];
    return {
      legend: { top: 0, left: 0 }, toolbox: { show: false },
      grid: { left: 8, right: 70, top: 30, bottom: 4, containLabel: true },
      tooltip: { trigger: 'axis', axisPointer: { type: 'line', lineStyle: { color: t.mutedText, type: 'dashed' } },
        formatter: (ps: any[]) => `<b>${String(ps[0].value[0]).slice(0, 7)}</b> <span style="opacity:.6">${ps[0].data.contract ?? ''}</span>${ps.map((p) => `<br/>${p.marker}${p.seriesName} ${fmtPrice(p.value[1])}`).join('')}` },
      xAxis: { type: 'time', ...ax, splitLine: { show: false }, axisLabel: { ...ax.axisLabel, fontFamily: t.mono, hideOverlap: true } },
      yAxis: { type: 'value', scale: true, ...ax, axisLabel: { ...ax.axisLabel, fontFamily: t.mono, formatter: (v: number) => fmtPrice(v) } },
      series: [
        ...(show.y1 ? [line('price_1y_ago', '1 year ago', t.mutedText, [2, 4], 1.5, 1)] : []),
        ...(show.m1 ? [line('price_1m_ago', '1 month ago', CATEGORICAL[0], [6, 4], 1.5, 2)] : []),
        { ...line('price', 'Now', nowC, 'solid', 2.25, 3),
          endLabel: { show: true, formatter: (p: any) => fmtPrice(p.value[1]), color: inkOn(nowC), backgroundColor: nowC, padding: [2, 4], borderRadius: 3, fontSize: 10, fontFamily: t.mono } },
      ],
    };
  }, [pts, show, t]);
  return <EChart option={option} height={320} ariaLabel={`${name} futures curve`} />;
}

export function CmdtyView({ onOpen }: { onOpen: (s: string) => void }) {
  const roots = useJSON<any>('/api/v1/mkt/futures');
  const [root, setRoot] = useState('CL');
  const [show, setShow] = useState({ m1: true, y1: true });
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/futures/${root}?n=60`, 600_000);
  const cur = data && data.root === root ? data : null;
  return (
    <div className="space-y-3">
      <div className="mkt-controls flex flex-wrap gap-1">{(roots.data?.roots ?? []).map((r: any) => (
        <button key={r.root} onClick={() => setRoot(r.root)} className={cn('px-2 py-1 text-2xs border', root === r.root ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary hover:text-text-primary')}>{r.name}</button>))}</div>
      {loading && !cur ? <Loading label="Loading the futures curve…" /> : error ? <ErrorBox msg={error} /> : cur && (
        <>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            <Panel><div className="text-[10px] uppercase text-text-tertiary">Front month</div><div className="font-mono text-base">{fmtPrice(cur.front.price)}</div><div className="text-[10px] text-text-tertiary">{cur.front.contract}</div></Panel>
            <Panel><div className="text-[10px] uppercase text-text-tertiary">Curve shape (first year)</div><div className={cn('text-sm', cur.slope < 0 ? 'text-green' : 'text-amber')}>{cur.shape}</div></Panel>
            <Panel><div className="text-[10px] uppercase text-text-tertiary">Front → {cur.slope_months}M</div><div className="font-mono text-base"><Chg v={cur.slope} d={1} /></div></Panel>
            <Panel><div className="text-[10px] uppercase text-text-tertiary">Front → {cur.last_month}</div><div className="font-mono text-base"><Chg v={cur.full_slope} d={1} /></div></Panel>
            <Panel><div className="text-[10px] uppercase text-text-tertiary">Roll yield / yr</div><div className="font-mono text-base"><Chg v={cur.annualised_roll_yield} d={1} /></div></Panel>
          </div>
          <Panel title={`${cur.name} — futures curve to ${cur.last_month} (${cur.exchange}, ${cur.points.length} contracts)`} right={<span className="flex gap-2 text-[10px] text-text-tertiary">
            <label className="inline-flex items-center gap-1"><input type="checkbox" checked={show.m1} onChange={(e) => setShow({ ...show, m1: e.target.checked })} /><span style={{ color: CATEGORICAL[0] }}>— —</span> 1 month ago</label>
            <label className="inline-flex items-center gap-1"><input type="checkbox" checked={show.y1} onChange={(e) => setShow({ ...show, y1: e.target.checked })} /><span>· · ·</span> 1 year ago</label></span>}>
            <FuturesCurve pts={cur.points} name={cur.name} show={show} />
            <div className="overflow-x-auto mt-3 max-h-72 overflow-y-auto"><table className="w-full text-2xs font-mono">
              <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-left font-normal">Month</th><th className="text-left font-normal">Contract</th>
                <th className="text-right font-normal">Price</th><th className="text-right font-normal">1D</th><th className="text-right font-normal">vs 1M ago</th><th className="text-right font-normal">vs 1Y ago</th></tr></thead>
              <tbody>{cur.points.map((p: any) => (
                <tr key={p.contract} onClick={() => onOpen(p.contract)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-3" tabIndex={0} onKeyDown={e=>{if(e.key==='Enter'&&e.target===e.currentTarget){e.preventDefault();e.currentTarget.click();}}}>
                  <td className="py-0.5 text-text-secondary">{p.month}</td><td className="text-text-tertiary">{p.contract}</td><td className="text-right">{fmtPrice(p.price)}</td>
                  <td className="text-right"><Chg v={p.change_1d} /></td>
                  <td className="text-right"><Chg v={p.price_1m_ago ? p.price / p.price_1m_ago - 1 : null} d={1} /></td>
                  <td className="text-right"><Chg v={p.price_1y_ago ? p.price / p.price_1y_ago - 1 : null} d={1} /></td></tr>))}</tbody></table></div>
          </Panel>
          <Panel title={`${cur.name} — continuous front month (${cur.root}=F)`}>
            <div className="mkt-chart-surface"><PriceChart key={cur.root} symbol={`${cur.root}=F`} height={340} /></div>
          </Panel>
          <div className="text-[10px] text-text-tertiary">{cur.note} {cur.source}. Every listed month for two years, then June and December contracts as far as they trade.</div>
        </>
      )}
    </div>
  );
}

// ── GC ───────────────────────────────────────────────────────────────────────
const tenorLabel = (t: number) => (t < 1 ? `${Math.round(t * 12)}M` : `${+t.toFixed(1)}Y`);

/** Government curves on a true maturity axis (square-root scale: the short end gets room, 30Y
 *  still fits). Each country plots only the tenors it has, so sparse curves stay correct. */
function CurveChart({ curves, codes, colors, overlay }: { curves: Record<string, any>; codes: string[]; colors: Record<string, string>;
  overlay: { code: string; which: 'week_ago' | 'month_ago' } | null }) {
  const t = useChartTheme();
  const option = useMemo(() => {
    const ax = axisStyle(t);
    const all = codes.flatMap((c) => curves[c].points);
    const tmax = Math.max(...all.map((p: any) => p.tenor), 10);
    const ticks = [0.25, 1, 2, 3, 5, 7, 10, 20, 30, 40].filter((v) => v <= tmax);
    const extra = overlay ? curves[overlay.code]?.[overlay.which]?.points ?? [] : [];
    // square-root maturity scale: the short end gets room and 30Y still fits
    const pt = (p: any) => ({ value: [Math.sqrt(p.tenor), p.yield], tenor: p.tenor });
    return {
      legend: { top: 0, left: 0 }, toolbox: { show: false },
      grid: { left: 8, right: 16, top: 30, bottom: 4, containLabel: true },
      tooltip: { trigger: 'item', formatter: (q: any) => `${q.marker}<b>${q.seriesName}</b> ${tenorLabel(q.data.tenor)}: ${q.data.value[1].toFixed(3)}%` },
      xAxis: { type: 'value', min: 0, max: Math.sqrt(tmax), ...ax, splitLine: { show: false },
        axisLabel: { ...ax.axisLabel, fontFamily: t.mono, customValues: ticks.map(Math.sqrt), formatter: (v: number) => tenorLabel(+(v * v).toFixed(2)) },
        axisTick: { show: true, customValues: ticks.map(Math.sqrt), lineStyle: { color: t.border } } },
      yAxis: { type: 'value', scale: true, ...ax, axisLabel: { ...ax.axisLabel, fontFamily: t.mono, formatter: (v: number) => `${v.toFixed(1)}%` } },
      series: [
        ...(overlay && extra.length > 1 ? [{ name: `${overlay.code} ${overlay.which === 'week_ago' ? '1 week' : '1 month'} ago`, type: 'line', data: extra.map(pt), showSymbol: false,
          lineStyle: { color: color(colors[overlay.code]), width: 1.5, type: [5, 4], opacity: 0.75 }, itemStyle: { color: color(colors[overlay.code]) } }] : []),
        ...codes.map((c) => ({ name: curves[c].name ?? c, type: 'line', data: curves[c].points.map(pt), symbol: 'circle', symbolSize: 5,
          lineStyle: { color: color(colors[c]), width: 2 }, itemStyle: { color: color(colors[c]), borderColor: t.surface1, borderWidth: 1 }, emphasis: { focus: 'series' } })),
      ],
    };
  }, [curves, codes, colors, overlay, t]);
  return <EChart option={option} height={360} ariaLabel="Government yield curves" />;
}

export function GcView() {
  const { data, error, loading } = useJSON<any>('/api/v1/mkt/gc', 3_600_000);
  const [off, setOff] = useState<Record<string, boolean>>({});
  const [overlay, setOverlay] = useState<{ code: string; which: 'week_ago' | 'month_ago' } | null>(null);
  if (loading && !data) return <Loading label="Loading government curves from the issuers…" />;
  if (error && !data) return <ErrorBox msg={error} />;
  if (!data) return null;
  const order: string[] = data.order;
  const colors = Object.fromEntries(order.map((c, i) => [c, CATEGORICAL[i % CATEGORICAL.length]]));
  const shown = order.filter((c) => !off[c]);
  const tenors = Array.from(new Set(order.flatMap((c) => data.curves[c].points.map((p: any) => p.tenor)))).sort((a: any, b: any) => a - b) as number[];
  const at = (c: string, t: number) => data.curves[c].points.find((p: any) => Math.abs(p.tenor - t) < 1e-6);
  return (
    <div className="space-y-3">
      <Panel title="Government yield curves" right={<span className="flex flex-wrap gap-1 text-[10px]">
        {order.map((c) => <button key={c} onClick={() => setOff({ ...off, [c]: !off[c] })} title={`${data.curves[c].name} · ${data.curves[c].date}`}
          className={cn('px-1.5 border font-mono', off[c] ? 'border-border text-text-tertiary' : 'border-transparent')} style={off[c] ? undefined : { background: `${colors[c]}22`, color: colors[c] }}>{c}</button>)}
        <select value={overlay ? `${overlay.code}:${overlay.which}` : ''} onChange={(e) => { const [code, which] = e.target.value.split(':'); setOverlay(code ? { code, which: which as any } : null); }}
          className="ml-2 bg-surface-1 border border-border px-1 text-text-primary">
          <option value="">Compare: none</option>
          {order.flatMap((c) => [<option key={c + 'w'} value={`${c}:week_ago`}>{c} vs 1 week ago</option>, <option key={c + 'm'} value={`${c}:month_ago`}>{c} vs 1 month ago</option>])}
        </select></span>}>
        {shown.length ? <CurveChart curves={data.curves} codes={shown} colors={colors} overlay={overlay} /> : <div className="text-2xs text-text-tertiary">Pick a country.</div>}
        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[10px] text-text-tertiary">{order.map((c) => (
          <span key={c}><span style={{ color: colors[c] }}>■</span> {data.curves[c].name} · {data.curves[c].date}{data.curves[c].slope_2s10s_bp != null ? ` · 2s10s ${data.curves[c].slope_2s10s_bp > 0 ? '+' : ''}${data.curves[c].slope_2s10s_bp.toFixed(0)}bp` : ''}</span>))}</div>
      </Panel>
      <Panel title="Yields by tenor (%) — change over 1 week / 1 month in bp">
        <div className="overflow-x-auto"><table className="w-full text-2xs font-mono">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Tenor</th>{order.map((c) => <th key={c} className="text-right font-normal px-2" style={{ color: colors[c] }}>{c}</th>)}</tr></thead>
          <tbody>{tenors.map((t) => (
            <tr key={t} className="border-t border-border-subtle"><td className="py-0.5 text-text-secondary">{tenorLabel(t)}</td>
              {order.map((c) => { const p = at(c, t); return (
                <td key={c} className="text-right px-2 whitespace-nowrap">{p ? <>{p.yield.toFixed(2)} <span className="text-[10px]"><Bp v={p.change_1w_bp} /> <Bp v={p.change_1m_bp} /></span></> : <span className="text-text-tertiary">—</span>}</td>); })}
            </tr>))}</tbody>
        </table></div>
        <div className="text-[10px] text-text-tertiary mt-2">— = tenor not published by that issuer. Rising yields red (prices fall).</div>
      </Panel>
      {Object.keys(data.unavailable ?? {}).length > 0 && <div className="text-[10px] text-amber">Unavailable now: {Object.keys(data.unavailable).join(', ')}</div>}
      <div className="text-[10px] text-text-tertiary">{data.note} Sources — {data.source}.</div>
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
      <div className="mkt-table-scroll" tabIndex={0} role="group" aria-label="Scrollable market data table"><table className="w-full text-2xs"><thead><tr className="text-text-tertiary"><th className="text-left font-normal">When</th><th className="text-left font-normal">Release</th>
        <th className="text-left font-normal">Importance</th><th className="text-right font-normal">Previous</th><th className="text-right font-normal">Forecast</th><th className="text-right font-normal">Actual</th></tr></thead>
        <tbody>{rows.map((r: any) => (
          <tr key={r.id + r.event_name + r.release_datetime} className="border-t border-border-subtle">
            <td className="py-1 font-mono text-text-secondary whitespace-nowrap">{new Date(r.release_datetime).toLocaleString(undefined, { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}</td>
            <td className="text-text-primary">{r.event_name}</td>
            <td><span className={cn('px-1.5 border text-[10px]', r.importance === 'HIGH' ? 'border-red/50 text-red' : r.importance === 'MEDIUM' ? 'border-amber/50 text-amber' : 'border-border text-text-tertiary')}>{r.importance}</span></td>
            <td className="text-right font-mono">{r.previous ?? '—'}</td><td className="text-right font-mono">{r.forecast ?? '—'}</td><td className="text-right font-mono text-text-primary">{r.actual ?? '—'}</td></tr>))}</tbody></table></div>
      <div className="text-[10px] text-text-tertiary mt-2">Times in your local time zone. Sources: {(data.events?.[0]?.source) ?? 'FRED release calendar'}. Consensus forecasts are not available from free sources.</div>
    </Panel>
  );
}

// ── N ────────────────────────────────────────────────────────────────────────
export function NewsView() {
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');
  const [src, setSrc] = useState('');
  const [tone, setTone] = useState('');
  const [ctry, setCtry] = useState('');
  const area = useRegion();
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/news?limit=150${area !== 'global' ? `&region=${area}` : ''}${query ? `&q=${encodeURIComponent(query)}` : ''}`, 600_000);
  const toneOf = (v: number) => (v > 0.15 ? 'positive' : v < -0.15 ? 'negative' : 'neutral');
  const items = (data?.items ?? []).filter((i: any) => (!src || i.source === src) && (!tone || toneOf(i.sentiment) === tone)
    && (!ctry || (i.countries ?? []).includes(ctry)));
  // countries actually mentioned in the current headlines, most frequent first
  const mentioned = useMemo(() => {
    const n: Record<string, number> = {};
    for (const i of data?.items ?? []) for (const c of i.countries ?? []) n[c] = (n[c] ?? 0) + 1;
    return Object.entries(n).sort((a, b) => b[1] - a[1]).slice(0, 25);
  }, [data]);
  return (
    <div className="space-y-3">
      <form onSubmit={(e) => { e.preventDefault(); setQuery(q.trim()); }} className="flex flex-wrap gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search headlines — e.g. Fed, oil, Nvidia, China" className="flex-1 min-w-[14rem] bg-surface-1 border border-border px-3 py-1.5 text-xs text-text-primary" />
        <select value={src} onChange={(e) => setSrc(e.target.value)} className={sel}><option value="">All sources</option>{(data?.sources ?? []).map((s: string) => <option key={s}>{s}</option>)}</select>
        <select value={tone} onChange={(e) => setTone(e.target.value)} className={sel} aria-label="Tone"><option value="">Any tone</option>
          <option value="positive">Positive</option><option value="neutral">Neutral</option><option value="negative">Negative</option></select>
        <select value={ctry} onChange={(e) => setCtry(e.target.value)} className={sel} aria-label="Country mentioned"><option value="">Any country</option>
          {mentioned.map(([c, k]) => <option key={c} value={c}>{c} ({k})</option>)}</select>
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
            <div className="mkt-chart-surface"><LineChart rows={data.curve} x="date" height={300} log baseline={1} fmt={(v) => `${v.toFixed(2)}×`}
              lines={data.symbols.map((s: string, i: number) => ({ key: s, label: s, color: CATEGORICAL[i % CATEGORICAL.length] }))} /></div>
          </Panel>
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            <Panel title="Return and risk">
              <div className="mkt-table-scroll" tabIndex={0} role="group" aria-label="Scrollable market data table"><table className="w-full text-2xs font-mono"><thead><tr className="text-text-tertiary"><th className="text-left font-normal">Symbol</th><th className="text-right font-normal">Total</th>
                <th className="text-right font-normal">Per year</th><th className="text-right font-normal">Volatility</th><th className="text-right font-normal">Return/vol</th><th className="text-right font-normal">Max drawdown</th></tr></thead>
                <tbody>{data.stats.map((s: any) => (<tr key={s.symbol} className="border-t border-border-subtle"><td className="text-text-primary py-0.5">{s.symbol}</td>
                  <td className="text-right"><Chg v={s.total_return} d={0} /></td><td className="text-right"><Chg v={s.cagr} d={1} /></td><td className="text-right">{(s.vol * 100).toFixed(1)}%</td>
                  <td className="text-right">{s.sharpe != null ? s.sharpe.toFixed(2) : '—'}</td><td className="text-right text-red">{(s.max_drawdown * 100).toFixed(0)}%</td></tr>))}</tbody></table></div>
              {data.missing.length > 0 && <div className="text-[10px] text-amber mt-1">No data for: {data.missing.join(', ')}</div>}
            </Panel>
            <Panel title="Correlation of daily returns">
              <div className="mkt-chart-surface"><CorrelationHeatmap labels={data.symbols} matrix={data.symbols.map((a: string) => data.symbols.map((b: string) => data.correlation[a][b]))} /></div>
            </Panel>
          </div>
          <div className="text-[10px] text-text-tertiary">{data.note}</div>
        </>
      )}
    </div>
  );
}
