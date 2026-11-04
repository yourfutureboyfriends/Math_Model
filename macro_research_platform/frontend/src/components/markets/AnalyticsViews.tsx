// Analytics functions: SEAS (seasonality), CORR (correlation matrix), RRG (relative rotation),
// FRD (FX forwards) and OSA (option strategy builder).
import { useMemo, useRef, useState } from 'react';
import { EChart, alpha, axisStyle, color, useChartTheme, type ECharts } from '@/components/charts/EChart';
import { cn } from '@/lib/utils';
import { toTerminal } from './bbg';
import { ErrorBox, fmtPrice, Loading, Panel, useJSON } from './shared';
import { signedPct as pct } from '@/lib/format';

const enc = encodeURIComponent;
const heat = (v: number | null | undefined, scale: number) => {
  if (v == null) return undefined;
  const a = Math.min(1, Math.abs(v) / scale) * 0.75 + 0.08;
  // strong cells take the text colour computed for a green / red fill (lib/accentContrast) — light text on a bright
  // green cell was 2.7:1
  return { background: v >= 0 ? `rgb(var(--c-green) / ${a})` : `rgb(var(--c-red) / ${a})`,
           ...(a > 0.5 ? { color: v >= 0 ? 'rgb(var(--c-on-green, 10 14 20))' : 'rgb(var(--c-on-red, 10 14 20))' } : {}) };
};

// ── SEAS ────────────────────────────────────────────────────────────────────
export function SeasView({ symbol }: { symbol: string }) {
  const [years, setYears] = useState(15);
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/seas/${enc(symbol)}?years=${years}`);
  if (loading && !data) return <Loading label="Computing seasonality…" />;
  if (error && !data) return <ErrorBox msg={error} />;
  if (!data) return null;
  const maxAbs = Math.max(...data.stats.map((s: any) => Math.abs(s.mean ?? 0)), 0.005);
  const now = new Date().getMonth();
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-xs">
        <span className="text-text-tertiary">Look-back</span>
        {[5, 10, 15, 20, 30].map((y) => (
          <button key={y} onClick={() => setYears(y)} className={cn('px-2 py-0.5 border', years === y ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{y}y</button>))}
        <span className="ml-auto text-text-tertiary">since {data.from}</span>
      </div>
      <Panel title="Average return by calendar month">
        <div className="grid grid-cols-12 gap-1 items-end h-44">
          {data.stats.map((s: any, i: number) => {
            const h = s.mean != null ? (Math.abs(s.mean) / maxAbs) * 45 : 0;
            return (
              <div key={s.month} className="flex flex-col items-center h-full" title={`${s.month}: mean ${pct(s.mean, 2)}, median ${pct(s.median, 2)}, up ${Math.round((s.hit_rate ?? 0) * 100)}% of ${s.n} years, t = ${s.t_stat?.toFixed(1) ?? '—'}`}>
                <div className="flex-1 w-full flex flex-col justify-end"><div className="w-full flex-1 flex items-end justify-center">
                  {s.mean >= 0 && <div className={cn('w-3/4 bg-green', Math.abs(s.t_stat ?? 0) < 2 && 'opacity-60')} style={{ height: `${h}%` }} />}</div></div>
                <div className="w-full h-px bg-border" />
                <div className="flex-1 w-full flex items-start justify-center">{s.mean < 0 && <div className={cn('w-3/4 bg-red', Math.abs(s.t_stat ?? 0) < 2 && 'opacity-60')} style={{ height: `${h}%` }} />}</div>
                <div className={cn('text-[10px] mt-0.5', i === now ? 'text-bloomberg font-semibold' : 'text-text-tertiary')}>{s.month}</div>
              </div>);
          })}
        </div>
      </Panel>
      <div className="overflow-x-auto border border-border">
        <table className="w-full text-[11px] font-mono tabular-nums">
          <thead><tr className="text-text-tertiary"><th className="text-left px-2 font-normal">Stat</th>{data.stats.map((s: any) => <th key={s.month} className="text-right px-1.5 font-normal">{s.month}</th>)}</tr></thead>
          <tbody>
            {([['Mean', 'mean'], ['Median', 'median'], ['% up', 'hit_rate'], ['Best', 'best'], ['Worst', 'worst'], ['t-stat', 't_stat'], ['This year', 'this_year']] as const).map(([lab, k]) => (
              <tr key={lab} className="border-t border-border-subtle"><td className="px-2 text-text-secondary font-sans">{lab}</td>
                {data.stats.map((s: any) => <td key={s.month} className="text-right px-1.5" style={k === 'mean' || k === 'median' || k === 'this_year' ? heat(s[k], maxAbs * 1.5) : undefined}>
                  {k === 'hit_rate' ? (s[k] != null ? `${Math.round(s[k] * 100)}%` : '—') : k === 't_stat' ? (s[k] != null ? s[k].toFixed(1) : '—') : pct(s[k])}</td>)}</tr>))}
            {data.yearly.map((y: any) => (
              <tr key={y.year} className="border-t border-border-subtle"><td className="px-2 text-text-tertiary">{y.year}</td>
                {y.months.map((v: number | null, i: number) => <td key={i} className="text-right px-1.5" style={heat(v, 0.08)}>{v == null ? '' : pct(v)}</td>)}</tr>))}
          </tbody>
        </table>
      </div>
      <div className="text-[10px] text-text-tertiary">{data.note} Faded bars: |t| &lt; 2.</div>
    </div>
  );
}

// ── CORR ────────────────────────────────────────────────────────────────────
const CORR_PRESETS: [string, string][] = [
  ['Cross-asset', 'SPY,QQQ,EFA,EEM,TLT,IEF,LQD,HYG,GLD,DBC,USO,UUP,BTC-USD,VNQ'],
  ['World indices', '^GSPC,^NDX,^STOXX50E,^FTSE,^GDAXI,^N225,^HSI,000001.SS,^KS11,^TWII,^BSESN,^AXJO,^BVSP'],
  ['US sectors', 'XLK,XLF,XLV,XLE,XLI,XLY,XLP,XLU,XLB,XLRE,XLC'],
  ['Currencies', 'EURUSD=X,GBPUSD=X,JPY=X,CHF=X,AUDUSD=X,CAD=X,CNY=X,MXN=X,BRL=X,INR=X'],
  ['Mega caps', 'AAPL,MSFT,NVDA,GOOGL,AMZN,META,AVGO,TSLA,BRK-B,JPM,LLY,TSM'],
];

export function CorrView({ seed }: { seed?: string }) {
  const [syms, setSyms] = useState(seed ? `${seed},SPY,TLT,GLD,UUP` : CORR_PRESETS[0][1]);
  const [input, setInput] = useState(syms);
  const [period, setPeriod] = useState('1y');
  const [freq, setFreq] = useState('daily');
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/corr?symbols=${enc(syms)}&period=${period}&freq=${freq}`);
  return (
    <div className="space-y-3">
      <div className="mkt-controls flex flex-wrap gap-1 text-xs">
        {CORR_PRESETS.map(([l, v]) => <button key={l} onClick={() => { setSyms(v); setInput(v); }} className={cn('px-2 py-0.5 border', syms === v ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary hover:text-text-primary')}>{l}</button>)}
      </div>
      <div className="mkt-controls flex flex-wrap items-center gap-2 text-xs">
        <input value={input} onChange={(e) => setInput(e.target.value.toUpperCase())} onKeyDown={(e) => e.key === 'Enter' && setSyms(input.replace(/\s/g, ''))}
          className="flex-1 min-w-[260px] bg-surface-1 border border-border px-2 py-1 font-mono text-text-primary" aria-label="Symbols, comma separated" />
        <button onClick={() => setSyms(input.replace(/\s/g, ''))} className="px-3 py-1 bg-bloomberg text-black font-semibold">GO</button>
        {['3mo', '6mo', '1y', '2y', '5y'].map((p) => <button key={p} onClick={() => setPeriod(p)} className={cn('px-2 py-0.5 border', period === p ? 'border-bloomberg text-bloomberg' : 'border-border')}>{p}</button>)}
        {['daily', 'weekly'].map((f) => <button key={f} onClick={() => setFreq(f)} className={cn('px-2 py-0.5 border', freq === f ? 'border-bloomberg text-bloomberg' : 'border-border')}>{f}</button>)}
      </div>
      {loading && !data && <Loading label="Computing correlations…" />}
      {error && <ErrorBox msg={error} />}
      {data && (
        <div className="overflow-x-auto border border-border bg-surface-1 p-2">
          <table className="text-[11px] font-mono tabular-nums">
            <thead><tr><th />{data.symbols.map((s: string) => <th key={s} className="px-1 font-normal text-text-tertiary [writing-mode:vertical-rl] rotate-180 h-24 text-left">{toTerminal(s)}</th>)}<th className="px-2 font-normal text-text-tertiary text-right">Vol</th></tr></thead>
            <tbody>{data.symbols.map((s: string, i: number) => (
              <tr key={s}><td className="pr-2 text-text-primary whitespace-nowrap">{toTerminal(s)}</td>
                {data.matrix[i].map((v: number | null, j: number) => (
                  <td key={j} className="w-11 h-7 text-center" style={i === j ? { background: 'rgb(var(--c-surface-3))' } : heat(v, 1)} title={`${s} × ${data.symbols[j]}: ${v ?? '—'}`}>
                    {i === j ? '' : v == null ? '—' : v.toFixed(2)}</td>))}
                <td className="px-2 text-right text-text-secondary">{data.volatility[i] != null ? `${(data.volatility[i] * 100).toFixed(0)}%` : '—'}</td></tr>))}</tbody>
          </table>
          <div className="text-[10px] text-text-tertiary mt-2">{data.note} {data.observations} observations. Vol = annualised volatility.</div>
        </div>)}
    </div>
  );
}

// ── RRG ─────────────────────────────────────────────────────────────────────
const RRG_LABEL: Record<string, string> = { us_sectors: 'US sectors', countries: 'Countries', factors: 'Factors', assets: 'Asset classes' };
/** Option payoff (Apache ECharts): P&L at expiry (profit shaded green, loss red) and today's value dashed, with
 *  spot and breakevens marked; the axis tooltip reads both at any price. */
function PayoffChart({ grid, pay, now, spot, breakevens, money }: { grid: number[]; pay: number[]; now: number[]; spot: number; breakevens: number[]; money: (v: number) => string }) {
  const t = useChartTheme();
  const option = useMemo(() => {
    const ax = axisStyle(t);
    const accent = color('rgb(var(--c-bloomberg))', t.accent), blue = color('rgb(var(--c-blue))', t.series[0]);
    return {
      legend: { top: 0, left: 0, data: ['At expiry', 'Today'] }, toolbox: { show: false },
      grid: { left: 8, right: 16, top: 30, bottom: 4, containLabel: true },
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross', label: { formatter: (p: any) => (p.axisDimension === 'x' ? fmtPrice(p.value) : money(p.value)) } },
        formatter: (ps: any[]) => `<b>${fmtPrice(ps[0].value[0])}</b>${ps.map((p) => `<br/>${p.marker}${p.seriesName} ${money(p.value[1])}`).join('')}` },
      xAxis: { type: 'value', min: grid[0], max: grid[grid.length - 1], ...ax, splitLine: { show: false }, axisLabel: { ...ax.axisLabel, fontFamily: t.mono, formatter: (v: number) => fmtPrice(v) } },
      yAxis: { type: 'value', ...ax, axisLabel: { ...ax.axisLabel, fontFamily: t.mono, formatter: (v: number) => money(v) } },
      visualMap: { show: false, seriesIndex: 0, dimension: 1, pieces: [{ lt: 0, color: t.red }, { gte: 0, color: t.green }] },
      series: [
        { name: 'At expiry', type: 'line', data: grid.map((x, i) => [x, pay[i]]), showSymbol: false, lineStyle: { width: 2 },
          areaStyle: { opacity: 0.12, origin: 0 },
          markLine: { symbol: 'none', silent: true, data: [
            { xAxis: spot, lineStyle: { color: accent, type: [3, 3] }, label: { formatter: `spot ${fmtPrice(spot)}`, color: accent, position: 'end' } },
            { yAxis: 0, lineStyle: { color: t.borderStrong, type: 'solid' }, label: { show: false } }] },
          markPoint: { symbol: 'circle', symbolSize: 7, silent: true, itemStyle: { color: t.textStrong, borderColor: t.surface1, borderWidth: 2 },
            label: { show: true, position: 'top', formatter: (q: any) => `BE ${fmtPrice(q.data.coord[0])}`, color: t.textStrong, fontSize: 9 },
            data: breakevens.map((b) => ({ coord: [b, 0] })) } },
        { name: 'Today', type: 'line', data: grid.map((x, i) => [x, now[i]]), showSymbol: false, lineStyle: { width: 1.5, type: [4, 3], color: blue }, itemStyle: { color: blue } },
      ],
    };
  }, [grid, pay, now, spot, breakevens, money, t]);
  return <EChart option={option} height={320} ariaLabel="Payoff diagram" />;
}

const QCOL: Record<string, string> = { Leading: 'rgb(var(--c-green))', Weakening: 'rgb(var(--c-amber))', Lagging: 'rgb(var(--c-red))', Improving: 'rgb(var(--c-blue))' };

export function RrgView({ onOpen }: { onOpen: (s: string) => void }) {
  const [u, setU] = useState('us_sectors');
/** Relative rotation graph (Apache ECharts): RS-Ratio × RS-Momentum around 100, quadrant tints, each symbol's tail
 *  ending in its current point; hover (here or in the table) isolates a symbol, click opens it. */
function RrgChart({ points, lo, hi, hover, setHover, onOpen }: { points: any[]; lo: number; hi: number; hover: string | null;
  setHover: (s: string | null) => void; onOpen: (s: string) => void }) {
  const t = useChartTheme();
  const cbs = useRef({ setHover, onOpen });
  cbs.current = { setHover, onOpen };
  const option = useMemo(() => {
    const ax = axisStyle(t);
    const qc = (q: string) => color(QCOL[q]);
    const quad = (q: string, x0: number, x1: number, y0: number, y1: number, pos: string) => [
      { coord: [x0, y1], itemStyle: { color: alpha(qc(q), 0.06) }, label: { show: true, position: pos, formatter: q.toUpperCase(), color: qc(q), fontWeight: 600, fontSize: 11 } },
      { coord: [x1, y0] }];
    const axis = (name: string, extra: any) => ({ type: 'value', min: lo, max: hi, name, ...ax, splitLine: { show: false },
      axisLine: { onZero: false, lineStyle: { color: t.border } }, axisLabel: { ...ax.axisLabel, fontFamily: t.mono, formatter: (v: number) => v.toFixed(1) }, ...extra });
    return {
      animation: false, legend: { show: false }, toolbox: { show: false },
      grid: { left: 44, right: 16, top: 28, bottom: 34 },
      tooltip: { trigger: 'item', formatter: (q: any) => { const p = q.data?.p; if (!p) return '';
        const last = p.trail[p.trail.length - 1];
        return `<b>${p.label}</b> <span style="opacity:.6">${p.symbol}</span><br/>${p.quadrant}<br/>RS-Ratio ${last.x.toFixed(2)} · RS-Momentum ${last.y.toFixed(2)}<br/><span style="opacity:.6">click to open</span>`; } },
      xAxis: axis('RS-Ratio (relative trend) →', { nameLocation: 'end', nameGap: 4, nameTextStyle: { ...ax.nameTextStyle, verticalAlign: 'top', align: 'right', padding: [20, 0, 0, 0] } }),
      yAxis: axis('↑ RS-Momentum', { nameLocation: 'end', nameTextStyle: { ...ax.nameTextStyle, align: 'left' } }),
      series: [
        { type: 'line', data: [], silent: true,
          markArea: { silent: true, data: [quad('Improving', lo, 100, 100, hi, 'insideTopLeft'), quad('Leading', 100, hi, 100, hi, 'insideTopRight'),
            quad('Lagging', lo, 100, lo, 100, 'insideBottomLeft'), quad('Weakening', 100, hi, lo, 100, 'insideBottomRight')] },
          markLine: { symbol: 'none', silent: true, lineStyle: { color: t.borderStrong, type: 'solid' }, label: { show: false }, data: [{ xAxis: 100 }, { yAxis: 100 }] } },
        ...points.flatMap((p) => { const on = !hover || hover === p.symbol, c = qc(p.quadrant), op = on ? 1 : 0.15;
          return [
            { type: 'line', data: p.trail.map((q: any) => ({ value: [q.x, q.y], p })), smooth: 0.3, symbol: 'circle', symbolSize: 3.5, z: 2,
              lineStyle: { color: c, width: 1.5, opacity: 0.7 * op }, itemStyle: { color: c, opacity: 0.5 * op } },
            { type: 'scatter', z: 3, cursor: 'pointer', data: [{ value: [p.trail.at(-1).x, p.trail.at(-1).y], p }], symbolSize: 11,
              itemStyle: { color: c, borderColor: t.surface1, borderWidth: 1.5, opacity: op },
              label: { show: true, position: 'right', formatter: p.label, color: t.textStrong, fontSize: 10, opacity: op } }];
        }),
      ],
    };
  }, [points, lo, hi, hover, t]);
  const onReady = (c: ECharts) => {
    c.on('mouseover', (q: any) => q.data?.p && cbs.current.setHover(q.data.p.symbol));
    c.on('mouseout', () => cbs.current.setHover(null));
    c.on('click', (q: any) => q.data?.p && cbs.current.onOpen(q.data.p.symbol));
  };
  return <EChart option={option} height={480} onReady={onReady} ariaLabel="Relative rotation graph" />;
}

  const [tail, setTail] = useState(8);
  const [hover, setHover] = useState<string | null>(null);
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/rrg?universe=${u}&tail=${tail}`, 3_600_000);
  const bounds = useMemo(() => {
    const xs: number[] = [], ys: number[] = [];
    for (const p of data?.points ?? []) for (const t of p.trail) { xs.push(t.x); ys.push(t.y); }
    const span = Math.max(1.5, ...xs.map((x) => Math.abs(x - 100)), ...ys.map((y) => Math.abs(y - 100))) * 1.15;
    return { lo: 100 - span, hi: 100 + span };
  }, [data]);
  return (
    <div className="space-y-3">
      <div className="mkt-controls flex flex-wrap items-center gap-1 text-xs">
        {Object.entries(RRG_LABEL).map(([k, l]) => <button key={k} onClick={() => setU(k)} className={cn('px-2 py-0.5 border', u === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{l}</button>)}
        <span className="ml-3 text-text-tertiary">Tail</span>
        {[4, 8, 13, 26].map((t) => <button key={t} onClick={() => setTail(t)} className={cn('px-2 py-0.5 border', tail === t ? 'border-bloomberg text-bloomberg' : 'border-border')}>{t}w</button>)}
        {data && <span className="ml-auto text-text-tertiary">vs {toTerminal(data.benchmark)} · week of {data.as_of}</span>}
      </div>
      {loading && !data && <Loading label="Building the rotation graph…" />}
      {error && <ErrorBox msg={error} />}
      {data && (
        <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_300px] gap-3">
          <div className="border border-border bg-surface-1 p-2">
            <RrgChart points={data.points} lo={bounds.lo} hi={bounds.hi} hover={hover} setHover={setHover} onOpen={onOpen} />
          </div>
          <Panel title="Quadrants">
            <div className="mkt-table-scroll" tabIndex={0} role="group" aria-label="Scrollable market data table"><table className="w-full text-xs"><tbody>
              {['Leading', 'Improving', 'Weakening', 'Lagging'].flatMap((q) => data.points.filter((p: any) => p.quadrant === q).map((p: any) => (
                <tr key={p.symbol} className="border-t border-border-subtle cursor-pointer hover:bg-surface-3" onMouseEnter={() => setHover(p.symbol)} onMouseLeave={() => setHover(null)} onClick={() => onOpen(p.symbol)} tabIndex={0} onKeyDown={e=>{if(e.key==='Enter'&&e.target===e.currentTarget){e.preventDefault();e.currentTarget.click();}}}>
                  <td className="py-1"><span className="inline-block w-2 h-2 mr-1.5" style={{ background: QCOL[q] }} />{p.label} <span className="font-mono text-text-tertiary">{p.symbol}</span></td>
                  <td className="text-right font-mono" title="Relative to the benchmark, last 4 weeks">{pct(p.relative_4w)}</td></tr>)))}
            </tbody></table></div>
            <p className="mt-2 text-[10px] text-text-tertiary">Rotation usually runs clockwise: improving → leading → weakening → lagging. Right column: performance vs the benchmark over 4 weeks.</p>
          </Panel>
        </div>)}
      {data && <div className="text-[10px] text-text-tertiary">{data.method}</div>}
    </div>
  );
}

// ── FRD ─────────────────────────────────────────────────────────────────────
const FRD_CCYS = ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'CAD', 'AUD', 'NZD', 'SEK', 'NOK', 'DKK', 'KRW', 'MXN', 'ZAR', 'INR', 'PLN', 'CZK', 'HUF', 'ILS', 'CNY', 'BRL'];

export function FrdView() {
  const [b, setB] = useState('EUR');
  const [q, setQ] = useState('USD');
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/frd?base=${b}&quote=${q}`);
  const sel = (v: string, set: (s: string) => void, label: string) => (
    <label className="text-xs text-text-tertiary">{label} <select value={v} onChange={(e) => set(e.target.value)} className="ml-1 bg-surface-1 border border-border px-2 py-1 text-text-primary font-mono">
      {FRD_CCYS.map((c) => <option key={c}>{c}</option>)}</select></label>);
  return (
    <div className="space-y-3">
      <div className="mkt-controls flex flex-wrap items-center gap-3">{sel(b, setB, 'Base')}{sel(q, setQ, 'Quote')}
        <button onClick={() => { setB(q); setQ(b); }} className="px-2 py-1 text-xs border border-border hover:border-bloomberg">⇄ swap</button></div>
      {loading && !data && <Loading />}
      {error && <ErrorBox msg={error} />}
      {data && (
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_300px] gap-3">
          <Panel title={`${data.pair} forwards — spot ${fmtPrice(data.spot, 'FX')}`}>
            <div className="mkt-table-scroll" tabIndex={0} role="group" aria-label="Scrollable market data table"><table className="w-full text-xs font-mono tabular-nums">
              <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Tenor</th><th className="text-right font-normal">Outright</th><th className="text-right font-normal">Points</th><th className="text-right font-normal">Annualised</th></tr></thead>
              <tbody>{data.tenors.map((t: any) => (
                <tr key={t.tenor} className="border-t border-border-subtle"><td className="py-1 text-text-primary font-sans">{t.tenor}</td>
                  <td className="text-right">{t.forward.toFixed(data.pip === 0.01 ? 3 : 5)}</td>
                  <td className={cn('text-right', t.points >= 0 ? 'text-green' : 'text-red')}>{t.points >= 0 ? '+' : ''}{t.points.toFixed(1)}</td>
                  <td className="text-right">{pct(t.annualised_premium, 2)}</td></tr>))}</tbody>
            </table></div>
          </Panel>
          <Panel title="Interest rates used">
            <div className="space-y-2 text-xs">{Object.entries<any>(data.rates).map(([c, r]) => (
              <div key={c} className="flex justify-between"><span className="text-text-secondary">{c} 3-month</span>
                <span className="font-mono text-text-primary">{(r.rate * 100).toFixed(2)}% <span className={cn('text-[10px]', data.stale_rates?.includes(c) ? 'text-amber' : 'text-text-tertiary')}>{r.date}</span></span></div>))}
              {data.stale_rates?.length > 0 && <p className="text-[11px] text-amber">The {data.stale_rates.join(' and ')} rate is more than 3 months old (latest published by the OECD) — treat those forwards as indicative.</p>}
              <p className="text-[10px] text-text-tertiary">{data.method}</p>
            </div>
          </Panel>
        </div>)}
    </div>
  );
}

// ── OSA: option strategy builder ────────────────────────────────────────────
type Leg = { kind: 'call' | 'put' | 'stock'; side: 1 | -1; strike: number; qty: number; premium: number; iv: number | null; greeks?: any };

function normCdf(x: number) {
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const d = 0.3989423 * Math.exp(-x * x / 2);
  const p = d * t * (0.3193815 + t * (-0.3565638 + t * (1.781478 + t * (-1.821256 + t * 1.330274))));
  return x > 0 ? 1 - p : p;
}
function bsPrice(S: number, K: number, T: number, r: number, q: number, v: number, call: boolean) {
  if (T <= 0 || v <= 0) return Math.max(0, call ? S - K : K - S);
  const d1 = (Math.log(S / K) + (r - q + v * v / 2) * T) / (v * Math.sqrt(T)), d2 = d1 - v * Math.sqrt(T);
  return call ? S * Math.exp(-q * T) * normCdf(d1) - K * Math.exp(-r * T) * normCdf(d2) : K * Math.exp(-r * T) * normCdf(-d2) - S * Math.exp(-q * T) * normCdf(-d1);
}

const TEMPLATES: [string, (k: (m: number) => number) => Omit<Leg, 'premium' | 'iv' | 'greeks'>[]][] = [
  ['Long call', (k) => [{ kind: 'call', side: 1, strike: k(1), qty: 1 }]],
  ['Long put', (k) => [{ kind: 'put', side: 1, strike: k(1), qty: 1 }]],
  ['Covered call', (k) => [{ kind: 'stock', side: 1, strike: 0, qty: 1 }, { kind: 'call', side: -1, strike: k(1.05), qty: 1 }]],
  ['Protective put', (k) => [{ kind: 'stock', side: 1, strike: 0, qty: 1 }, { kind: 'put', side: 1, strike: k(0.95), qty: 1 }]],
  ['Bull call spread', (k) => [{ kind: 'call', side: 1, strike: k(1), qty: 1 }, { kind: 'call', side: -1, strike: k(1.05), qty: 1 }]],
  ['Bear put spread', (k) => [{ kind: 'put', side: 1, strike: k(1), qty: 1 }, { kind: 'put', side: -1, strike: k(0.95), qty: 1 }]],
  ['Long straddle', (k) => [{ kind: 'call', side: 1, strike: k(1), qty: 1 }, { kind: 'put', side: 1, strike: k(1), qty: 1 }]],
  ['Long strangle', (k) => [{ kind: 'call', side: 1, strike: k(1.05), qty: 1 }, { kind: 'put', side: 1, strike: k(0.95), qty: 1 }]],
  ['Iron condor', (k) => [{ kind: 'put', side: 1, strike: k(0.9), qty: 1 }, { kind: 'put', side: -1, strike: k(0.95), qty: 1 },
    { kind: 'call', side: -1, strike: k(1.05), qty: 1 }, { kind: 'call', side: 1, strike: k(1.1), qty: 1 }]],
  ['Call butterfly', (k) => [{ kind: 'call', side: 1, strike: k(0.95), qty: 1 }, { kind: 'call', side: -1, strike: k(1), qty: 2 }, { kind: 'call', side: 1, strike: k(1.05), qty: 1 }]],
];

export function OsaView({ symbol }: { symbol: string }) {
  const [expiry, setExpiry] = useState<string | null>(null);
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/omon/${enc(symbol)}${expiry ? `?expiry=${expiry}` : ''}`);
  const [tpl, setTpl] = useState('Bull call spread');
  const [legs, setLegs] = useState<Leg[] | null>(null);
  const S: number = data?.underlying;
  const T: number = data ? (data.sessions ?? data.days) / 252 : 0;
  const chainRow = (kind: 'call' | 'put', K: number) => (kind === 'call' ? data?.calls : data?.puts)?.find((r: any) => r.strike === K);
  const quoteLeg = (l: Omit<Leg, 'premium' | 'iv' | 'greeks'>): Leg => {
    if (l.kind === 'stock') return { ...l, premium: S, iv: null };
    const r = chainRow(l.kind, l.strike);
    const mid = r && r.bid > 0 && r.ask > 0 ? (r.bid + r.ask) / 2 : r?.last ?? 0;
    return { ...l, premium: mid, iv: r?.iv ?? data?.atm_iv ?? null, greeks: r };
  };
  const strikes: number[] = useMemo(() => [...new Set<number>([...(data?.calls ?? []), ...(data?.puts ?? [])].map((r: any) => r.strike))].sort((a, b) => a - b), [data]);
  // strike nearest to S·m, kept at least one listed strike away per 5% from the at-the-money one so
  // spreads, strangles and condors never collapse onto a single strike where strikes are sparse
  const nearest = (m: number) => {
    const idx = (t: number) => strikes.reduce((bi, k, i) => (Math.abs(k - t) < Math.abs(strikes[bi] - t) ? i : bi), 0);
    const atm = idx(S), steps = Math.round(Math.abs(m - 1) / 0.05);
    let i = idx(S * m);
    if (m > 1) i = Math.max(i, atm + steps); else if (m < 1) i = Math.min(i, atm - steps);
    return strikes[Math.max(0, Math.min(strikes.length - 1, i))];
  };
  const applyTpl = (name: string) => { setTpl(name); const t = TEMPLATES.find((x) => x[0] === name)!; setLegs(t[1](nearest).map(quoteLeg)); };
  // build legs once the chain arrives (and whenever the expiry changes)
  const legsNow: Leg[] = useMemo(() => {
    if (!data || !strikes.length) return [];
    if (legs && legs.every((l) => l.kind === 'stock' || chainRow(l.kind, l.strike))) return legs.map((l) => ({ ...quoteLeg(l), premium: l.premium }));
    return TEMPLATES.find((x) => x[0] === tpl)![1](nearest).map(quoteLeg);
  }, [data, legs, tpl, strikes]);

  if (loading && !data) return <Loading label="Loading the option chain…" />;
  if (error && !data) return <ErrorBox msg={error} />;
  if (!data || !legsNow.length) return null;

  const mult = 100;
  const payoff = (P: number) => legsNow.reduce((s, l) => s + l.side * l.qty * mult * (l.kind === 'stock' ? P - l.premium
    : Math.max(0, l.kind === 'call' ? P - l.strike : l.strike - P) - l.premium), 0);
  const valueNow = (P: number) => legsNow.reduce((s, l) => s + l.side * l.qty * mult * (l.kind === 'stock' ? P - l.premium
    : bsPrice(P, l.strike, T, data.rate ?? 0.04, data.dividend_yield ?? 0, l.iv ?? data.atm_iv ?? 0.3, l.kind === 'call') - l.premium), 0);
  // chart range from the implied move: ±3.5 standard deviations (at least ±5%), widened to show every strike
  const sdMove = (data.atm_iv ?? 0.3) * Math.sqrt(Math.max(T, 1 / 252));
  const ks = legsNow.filter((l) => l.kind !== 'stock').map((l) => l.strike);
  const lo = Math.min(S * Math.exp(-Math.max(3.5 * sdMove, 0.05)), ...ks.map((k) => k * 0.97));
  const hi = Math.max(S * Math.exp(Math.max(3.5 * sdMove, 0.05)), ...ks.map((k) => k * 1.03));
  const N = 240;
  const grid = Array.from({ length: N + 1 }, (_, i) => lo + ((hi - lo) * i) / N);
  const pay = grid.map(payoff), now = grid.map(valueNow);
  const netCost = legsNow.reduce((s, l) => s + l.side * l.qty * mult * l.premium, 0);
  // unbounded if the payoff still slopes at the edges (calls/stock to the upside, puts to zero)
  const slopeHi = payoff(S * 10) - payoff(S * 9), slopeLo = payoff(0) - payoff(S * 0.01);
  const maxP = slopeHi > 1e-6 ? Infinity : Math.max(...pay, payoff(0));
  const maxL = slopeHi < -1e-6 ? -Infinity : Math.min(...pay, payoff(0));
  void slopeLo;
  const breakevens: number[] = [];
  for (let i = 1; i < grid.length; i++) if ((pay[i - 1] < 0) !== (pay[i] < 0)) breakevens.push(grid[i - 1] + (grid[i] - grid[i - 1]) * (-pay[i - 1] / (pay[i] - pay[i - 1])));
  // probability of profit at expiry: lognormal with the ATM implied vol
  const sig = data.atm_iv ?? 0.3, mu = Math.log(S) + ((data.rate ?? 0.04) - sig * sig / 2) * T, sd = sig * Math.sqrt(Math.max(T, 1e-6));
  let pop = 0;
  for (let i = 1; i < grid.length; i++) if (pay[i] > 0) pop += normCdf((Math.log(grid[i]) - mu) / sd) - normCdf((Math.log(grid[i - 1]) - mu) / sd);
  if (payoff(hi * 2) > 0) pop += 1 - normCdf((Math.log(hi) - mu) / sd);
  if (payoff(lo * 0.5) > 0) pop += normCdf((Math.log(lo) - mu) / sd);
  const greeks = ['delta', 'gamma', 'theta', 'vega'].map((g) => [g, legsNow.reduce((s, l) => s + l.side * l.qty * mult * (l.kind === 'stock' ? (g === 'delta' ? 1 : 0) : (l.greeks?.[g] ?? 0)), 0)] as const);
  const money = (v: number) => (v === Infinity ? 'Unlimited' : v === -Infinity ? 'Unlimited' : `${v < 0 ? '−' : ''}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`);
  const setLeg = (i: number, patch: Partial<Leg>) => setLegs(legsNow.map((l, j) => (j === i ? quoteLeg({ ...l, ...patch }) : l)));

  return (
    <div className="space-y-3">
      <div className="mkt-controls flex flex-wrap items-center gap-1 text-xs">
        {TEMPLATES.map(([n]) => <button key={n} onClick={() => applyTpl(n)} className={cn('px-2 py-0.5 border', tpl === n ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary hover:text-text-primary')}>{n}</button>)}
        <select value={data.expiry} onChange={(e) => { setExpiry(e.target.value); setLegs(null); }} className="ml-auto bg-surface-1 border border-border px-2 py-0.5 font-mono" aria-label="Expiry">
          {data.expirations.map((e: string) => <option key={e}>{e}</option>)}</select>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-6 gap-2 text-xs">
        {[['Net ' + (netCost >= 0 ? 'debit' : 'credit'), money(Math.abs(netCost))], ['Max profit', money(maxP)], ['Max loss', money(maxL)],
          ['Breakeven', breakevens.length ? breakevens.map((b) => fmtPrice(b)).join(' / ') : '—'], ['Chance of profit', `${Math.round(pop * 100)}%`],
          ['Days / sessions', `${data.days} / ${data.sessions ?? '—'}`]].map(([k, v]) => (
          <div key={k} className="border border-border bg-surface-1 px-2 py-1.5"><div className="text-[10px] uppercase tracking-wide text-text-tertiary">{k}</div><div className="font-mono text-text-primary">{v}</div></div>))}
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_380px] gap-3">
        <div className="border border-border bg-surface-1 p-2">
          <PayoffChart grid={grid} pay={pay} now={now} spot={S} breakevens={breakevens} money={money} />
          <div className="text-[10px] text-text-tertiary"><span className="text-text-primary">━</span> at expiry · <span className="text-blue">┅</span> today (each leg at its implied vol) · per 1 contract = 100 shares</div>
        </div>
        <div className="space-y-2">
          <div className="border border-border bg-surface-1">
            <div className="mkt-table-scroll" tabIndex={0} role="group" aria-label="Scrollable market data table"><table className="w-full text-[11px] font-mono">
              <thead><tr className="text-text-tertiary"><th className="text-left font-normal px-1.5">Leg</th><th className="font-normal">Strike</th><th className="font-normal">Qty</th><th className="text-right font-normal">Price</th><th className="text-right font-normal px-1.5">IV</th></tr></thead>
              <tbody>{legsNow.map((l, i) => (
                <tr key={i} className="border-t border-border-subtle">
                  <td className="px-1.5"><button onClick={() => setLeg(i, { side: (l.side * -1) as 1 | -1 })} className={l.side > 0 ? 'text-green' : 'text-red'}>{l.side > 0 ? 'BUY' : 'SELL'}</button> {l.kind}</td>
                  <td className="text-center">{l.kind === 'stock' ? '—' : (
                    <select value={l.strike} onChange={(e) => setLeg(i, { strike: Number(e.target.value) })} className="bg-transparent">{strikes.map((k) => <option key={k} value={k}>{k}</option>)}</select>)}</td>
                  <td className="text-center"><input type="number" min={1} value={l.qty} onChange={(e) => setLeg(i, { qty: Math.max(1, Number(e.target.value) || 1) })} className="w-10 bg-transparent text-center" /></td>
                  <td className="text-right">{fmtPrice(l.premium)}</td><td className="text-right px-1.5">{l.iv != null ? `${(l.iv * 100).toFixed(1)}%` : '—'}</td></tr>))}</tbody>
            </table></div>
          </div>
          <div className="border border-border bg-surface-1 p-2 grid grid-cols-4 gap-2 text-[11px]">
            {greeks.map(([g, v]) => <div key={g}><div className="text-text-tertiary capitalize">{g}</div><div className="font-mono text-text-primary">{v.toFixed(g === 'gamma' ? 3 : 1)}</div></div>)}
          </div>
          <p className="text-[10px] text-text-tertiary leading-relaxed">Prices are bid/ask mids (15-min delayed). Chance of profit assumes a lognormal price at expiry with the at-the-money implied vol ({data.atm_iv != null ? `${(data.atm_iv * 100).toFixed(1)}%` : '—'}). Greeks are position totals (theta per trading day). Click BUY/SELL to flip a leg.</p>
          {data.warning && <p className="text-[11px] text-amber">{data.warning}</p>}
        </div>
      </div>
    </div>
  );
}
