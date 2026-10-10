// Analytics functions: SEAS (seasonality), CORR (correlation matrix), RRG (relative rotation),
// FRD (FX forwards) and OSA (option strategy builder).
import { useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { toTerminal } from './bbg';
import { ErrorBox, fmtPrice, Loading, Panel, useJSON } from './shared';

const enc = encodeURIComponent;
const pct = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${v >= 0 ? '+' : ''}${(v * 100).toFixed(d)}%`);
const heat = (v: number | null | undefined, scale: number) => {
  if (v == null) return undefined;
  const a = Math.min(1, Math.abs(v) / scale) * 0.75 + 0.08;
  return { background: v >= 0 ? `rgb(var(--c-green) / ${a})` : `rgb(var(--c-red) / ${a})` };
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
      <div className="flex flex-wrap gap-1 text-xs">
        {CORR_PRESETS.map(([l, v]) => <button key={l} onClick={() => { setSyms(v); setInput(v); }} className={cn('px-2 py-0.5 border', syms === v ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary hover:text-text-primary')}>{l}</button>)}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
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
const QCOL: Record<string, string> = { Leading: 'rgb(var(--c-green))', Weakening: 'rgb(var(--c-amber))', Lagging: 'rgb(var(--c-red))', Improving: 'rgb(var(--c-blue))' };

export function RrgView({ onOpen }: { onOpen: (s: string) => void }) {
  const [u, setU] = useState('us_sectors');
  const [tail, setTail] = useState(8);
  const [hover, setHover] = useState<string | null>(null);
  const { data, error, loading } = useJSON<any>(`/api/v1/mkt/rrg?universe=${u}&tail=${tail}`, 3_600_000);
  const W = 620, H = 480, pad = 36;
  const bounds = useMemo(() => {
    const xs: number[] = [], ys: number[] = [];
    for (const p of data?.points ?? []) for (const t of p.trail) { xs.push(t.x); ys.push(t.y); }
    const span = Math.max(1.5, ...xs.map((x) => Math.abs(x - 100)), ...ys.map((y) => Math.abs(y - 100))) * 1.15;
    return { lo: 100 - span, hi: 100 + span };
  }, [data]);
  const sx = (x: number) => pad + ((x - bounds.lo) / (bounds.hi - bounds.lo)) * (W - 2 * pad);
  const sy = (y: number) => H - pad - ((y - bounds.lo) / (bounds.hi - bounds.lo)) * (H - 2 * pad);
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1 text-xs">
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
            <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Relative rotation graph">
              {([['Improving', pad, pad], ['Leading', W / 2, pad], ['Lagging', pad, H / 2], ['Weakening', W / 2, H / 2]] as const).map(([q, x, y]) => (
                <g key={q}><rect x={x} y={y} width={W / 2 - pad} height={H / 2 - pad} fill={QCOL[q]} opacity={0.06} />
                  <text x={q === 'Leading' || q === 'Weakening' ? W - pad - 6 : pad + 6} y={q === 'Improving' || q === 'Leading' ? pad + 14 : H - pad - 6}
                    textAnchor={q === 'Leading' || q === 'Weakening' ? 'end' : 'start'} fontSize="11" fill={QCOL[q]} fontWeight="600">{q.toUpperCase()}</text></g>))}
              <line x1={sx(100)} x2={sx(100)} y1={pad} y2={H - pad} stroke="rgb(var(--c-border-strong))" />
              <line x1={pad} x2={W - pad} y1={sy(100)} y2={sy(100)} stroke="rgb(var(--c-border-strong))" />
              <text x={W - pad} y={H - 8} textAnchor="end" fontSize="10" fill="rgb(var(--c-text-tertiary))">RS-Ratio (relative trend) →</text>
              <text x={10} y={pad - 10} fontSize="10" fill="rgb(var(--c-text-tertiary))">↑ RS-Momentum</text>
              {data.points.map((p: any) => {
                const on = !hover || hover === p.symbol;
                const pts = p.trail.map((t: any) => `${sx(t.x)},${sy(t.y)}`).join(' ');
                const last = p.trail[p.trail.length - 1];
                return (
                  <g key={p.symbol} opacity={on ? 1 : 0.15} onMouseEnter={() => setHover(p.symbol)} onMouseLeave={() => setHover(null)} onClick={() => onOpen(p.symbol)} className="cursor-pointer">
                    <polyline points={pts} fill="none" stroke={QCOL[p.quadrant]} strokeWidth={1.5} strokeOpacity={0.7} />
                    {p.trail.slice(0, -1).map((t: any, i: number) => <circle key={i} cx={sx(t.x)} cy={sy(t.y)} r={1.8} fill={QCOL[p.quadrant]} opacity={0.5} />)}
                    <circle cx={sx(last.x)} cy={sy(last.y)} r={5} fill={QCOL[p.quadrant]} stroke="rgb(var(--c-bg))" strokeWidth={1.5} />
                    <text x={sx(last.x) + 7} y={sy(last.y) + 4} fontSize="10" fill="rgb(var(--c-text-primary))">{p.label}</text>
                  </g>);
              })}
            </svg>
          </div>
          <Panel title="Quadrants">
            <table className="w-full text-xs"><tbody>
              {['Leading', 'Improving', 'Weakening', 'Lagging'].flatMap((q) => data.points.filter((p: any) => p.quadrant === q).map((p: any) => (
                <tr key={p.symbol} className="border-t border-border-subtle cursor-pointer hover:bg-surface-3" onMouseEnter={() => setHover(p.symbol)} onMouseLeave={() => setHover(null)} onClick={() => onOpen(p.symbol)}>
                  <td className="py-1"><span className="inline-block w-2 h-2 mr-1.5" style={{ background: QCOL[q] }} />{p.label} <span className="font-mono text-text-tertiary">{p.symbol}</span></td>
                  <td className="text-right font-mono" title="Relative to the benchmark, last 4 weeks">{pct(p.relative_4w)}</td></tr>)))}
            </tbody></table>
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
      <div className="flex flex-wrap items-center gap-3">{sel(b, setB, 'Base')}{sel(q, setQ, 'Quote')}
        <button onClick={() => { setB(q); setQ(b); }} className="px-2 py-1 text-xs border border-border hover:border-bloomberg">⇄ swap</button></div>
      {loading && !data && <Loading />}
      {error && <ErrorBox msg={error} />}
      {data && (
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_300px] gap-3">
          <Panel title={`${data.pair} forwards — spot ${fmtPrice(data.spot, 'FX')}`}>
            <table className="w-full text-xs font-mono tabular-nums">
              <thead><tr className="text-text-tertiary"><th className="text-left font-normal">Tenor</th><th className="text-right font-normal">Outright</th><th className="text-right font-normal">Points</th><th className="text-right font-normal">Annualised</th></tr></thead>
              <tbody>{data.tenors.map((t: any) => (
                <tr key={t.tenor} className="border-t border-border-subtle"><td className="py-1 text-text-primary font-sans">{t.tenor}</td>
                  <td className="text-right">{t.forward.toFixed(data.pip === 0.01 ? 3 : 5)}</td>
                  <td className={cn('text-right', t.points >= 0 ? 'text-green' : 'text-red')}>{t.points >= 0 ? '+' : ''}{t.points.toFixed(1)}</td>
                  <td className="text-right">{pct(t.annualised_premium, 2)}</td></tr>))}</tbody>
            </table>
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
  const nearest = (m: number) => strikes.reduce((best, k) => (Math.abs(k - S * m) < Math.abs(best - S * m) ? k : best), strikes[0]);
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
  const W = 640, H = 300, pad = 40;
  const ymin = Math.min(...pay, ...now), ymax = Math.max(...pay, ...now);
  const sx = (x: number) => pad + ((x - lo) / (hi - lo)) * (W - 2 * pad);
  const sy = (y: number) => H - pad - ((y - ymin) / ((ymax - ymin) || 1)) * (H - 2 * pad);
  const path = (ys: number[]) => grid.map((x, i) => `${i ? 'L' : 'M'}${sx(x).toFixed(1)},${sy(ys[i]).toFixed(1)}`).join('');
  const money = (v: number) => (v === Infinity ? 'Unlimited' : v === -Infinity ? 'Unlimited' : `${v < 0 ? '−' : ''}$${Math.abs(v).toLocaleString(undefined, { maximumFractionDigits: 0 })}`);
  const setLeg = (i: number, patch: Partial<Leg>) => setLegs(legsNow.map((l, j) => (j === i ? quoteLeg({ ...l, ...patch }) : l)));

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1 text-xs">
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
          <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Payoff diagram">
            <line x1={pad} x2={W - pad} y1={sy(0)} y2={sy(0)} stroke="rgb(var(--c-border-strong))" />
            <line x1={sx(S)} x2={sx(S)} y1={pad / 2} y2={H - pad} stroke="rgb(var(--c-bloomberg))" strokeDasharray="3 3" />
            <text x={sx(S) + 4} y={pad / 2 + 8} fontSize="10" fill="rgb(var(--c-bloomberg))">spot {fmtPrice(S)}</text>
            {breakevens.map((b) => <g key={b}><line x1={sx(b)} x2={sx(b)} y1={sy(0) - 5} y2={sy(0) + 5} stroke="rgb(var(--c-text-secondary))" /><text x={sx(b)} y={sy(0) + 16} fontSize="9" textAnchor="middle" fill="rgb(var(--c-text-secondary))">{fmtPrice(b)}</text></g>)}
            <path d={path(now)} fill="none" stroke="rgb(var(--c-blue))" strokeWidth={1.5} strokeDasharray="4 3" />
            <path d={path(pay)} fill="none" stroke="rgb(var(--c-text-primary))" strokeWidth={2} />
            {[0, 0.25, 0.5, 0.75, 1].map((f) => { const x = lo + (hi - lo) * f; return <text key={f} x={sx(x)} y={H - pad + 14} fontSize="9" textAnchor="middle" fill="rgb(var(--c-text-tertiary))">{fmtPrice(x)}</text>; })}
            {[ymin, 0, ymax].map((y) => <text key={y} x={pad - 4} y={sy(y) + 3} fontSize="9" textAnchor="end" fill="rgb(var(--c-text-tertiary))">{money(y)}</text>)}
          </svg>
          <div className="text-[10px] text-text-tertiary"><span className="text-text-primary">━</span> at expiry · <span className="text-blue">┅</span> today (each leg at its implied vol) · per 1 contract = 100 shares</div>
        </div>
        <div className="space-y-2">
          <div className="border border-border bg-surface-1">
            <table className="w-full text-[11px] font-mono">
              <thead><tr className="text-text-tertiary"><th className="text-left font-normal px-1.5">Leg</th><th className="font-normal">Strike</th><th className="font-normal">Qty</th><th className="text-right font-normal">Price</th><th className="text-right font-normal px-1.5">IV</th></tr></thead>
              <tbody>{legsNow.map((l, i) => (
                <tr key={i} className="border-t border-border-subtle">
                  <td className="px-1.5"><button onClick={() => setLeg(i, { side: (l.side * -1) as 1 | -1 })} className={l.side > 0 ? 'text-green' : 'text-red'}>{l.side > 0 ? 'BUY' : 'SELL'}</button> {l.kind}</td>
                  <td className="text-center">{l.kind === 'stock' ? '—' : (
                    <select value={l.strike} onChange={(e) => setLeg(i, { strike: Number(e.target.value) })} className="bg-transparent">{strikes.map((k) => <option key={k} value={k}>{k}</option>)}</select>)}</td>
                  <td className="text-center"><input type="number" min={1} value={l.qty} onChange={(e) => setLeg(i, { qty: Math.max(1, Number(e.target.value) || 1) })} className="w-10 bg-transparent text-center" /></td>
                  <td className="text-right">{fmtPrice(l.premium)}</td><td className="text-right px-1.5">{l.iv != null ? `${(l.iv * 100).toFixed(1)}%` : '—'}</td></tr>))}</tbody>
            </table>
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
