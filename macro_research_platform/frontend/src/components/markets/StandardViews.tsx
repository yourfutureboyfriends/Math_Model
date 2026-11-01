// Screens modelled on standard Bloomberg functions the platform lacked (backend: api/marketdata/bbgplus.py):
//   IMOV index movers · TRA total returns · WPE world valuations · VAP volume at price · OVME option calculator
//   MRR member returns · GE P/E history · WB world bonds · DS filing search
import { Fragment, useMemo, useState } from 'react';
import { LineChart } from '@/components/ui/LineChart';
import { cn } from '@/lib/utils';
import { BarList } from '@/components/ui/BarList';
import { blackScholes, impliedVol, type OptionKind } from '@/lib/blackScholes';
import { ErrorBox, fmtPct, fmtPrice, Loading, Panel, useJSON } from './shared';

function Tile({ label, value, sub, cls }: { label: string; value: React.ReactNode; sub?: React.ReactNode; cls?: string }) {
  return (
    <div className="border border-border bg-surface-1 rounded-md px-2.5 py-1.5">
      <div className="text-[10px] uppercase tracking-wide text-text-tertiary">{label}</div>
      <div className={cn('font-mono text-text-primary', cls)}>{value}</div>
      {sub != null && <div className="text-[10px] text-text-tertiary leading-tight">{sub}</div>}
    </div>
  );
}
function Chip({ on, onClick, children }: { on: boolean; onClick: () => void; children: React.ReactNode }) {
  return <button onClick={onClick} className={cn('px-2 py-0.5 border rounded-sm text-[11px]', on ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary hover:text-text-primary')}>{children}</button>;
}
const sign = (v: number | null | undefined) => (v == null ? '' : v > 0 ? 'text-green' : v < 0 ? 'text-red' : '');
const pct = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(d)}%`);
const Source = ({ children }: { children: React.ReactNode }) => <p className="text-[10px] text-text-tertiary leading-relaxed">{children}</p>;

// ── IMOV ─────────────────────────────────────────────────────────────────────
export function ImovView({ onOpen }: { onOpen: (s: string) => void }) {
  const [code, setCode] = useState<'SPX' | 'NDX' | 'INDU'>('SPX');
  const { data: d, error, loading } = useJSON<any>(`/api/v1/mkt/imov/${code}`, 300_000);
  const pick = <div className="flex gap-1">{(['SPX', 'NDX', 'INDU'] as const).map((c) => <Chip key={c} on={code === c} onClick={() => setCode(c)}>{c}</Chip>)}</div>;
  if (loading && !d) return <div className="space-y-2">{pick}<Loading label="Pricing every member of the index…" /></div>;
  if (error && !d) return <div className="space-y-2">{pick}<ErrorBox msg={error} /></div>;
  if (!d) return null;
  const pts = (v: number | null) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(2)}`);
  const Movers = ({ title, rows }: { title: string; rows: any[] }) => (
    <Panel title={title}>
      <table className="w-full text-2xs font-mono tabular-nums">
        <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Member</th><th className="text-right font-normal">Weight</th>
          <th className="text-right font-normal">Change</th><th className="text-right font-normal">Index pts</th><th className="text-right font-normal">bp</th></tr></thead>
        <tbody>{rows.map((r) => (
          <tr key={r.symbol} onClick={() => onOpen(r.symbol)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-2" title={r.name}>
            <td className="py-1 font-sans"><span className="text-text-primary">{r.symbol}</span> <span className="text-text-tertiary truncate">{r.sector ?? ''}</span></td>
            <td className="text-right text-text-secondary">{(r.weight * 100).toFixed(2)}%</td>
            <td className={cn('text-right', sign(r.change_pct))}>{pct(r.change_pct, 2)}</td>
            <td className={cn('text-right', sign(r.contrib_pts))}>{pts(r.contrib_pts)}</td>
            <td className={cn('text-right', sign(r.contrib_bps))}>{r.contrib_bps.toFixed(1)}</td></tr>))}</tbody>
      </table>
    </Panel>
  );
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">{pick}<span className="text-[11px] text-text-tertiary">{d.prev_date} → {d.as_of}</span></div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Tile label={d.name} value={d.level != null ? d.level.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—'}
          cls={sign(d.change_pts)} sub={<span className={sign(d.change_pts)}>{pts(d.change_pts)} pts · {d.change_bps != null ? `${(d.change_bps / 100).toFixed(2)}%` : '—'}</span>} />
        <Tile label="Explained by members" value={`${(d.implied_bps / 100).toFixed(2)}%`} sub={`${(d.coverage * 100).toFixed(1)}% of weight priced`} />
        <Tile label="Breadth" value={<><span className="text-green">{d.advancers}↑</span> <span className="text-red">{d.decliners}↓</span></>} sub={`of ${d.count} members`} />
        <Tile label="Concentration" value={`${(d.top10_share * 100).toFixed(0)}%`} sub="of the move from the 10 biggest contributors" />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <Movers title="Biggest positive contributors" rows={d.leaders} />
        <Movers title="Biggest negative contributors" rows={d.laggards} />
      </div>
      <Panel title="Contribution by sector (bp of the index)">
        <BarList data={d.sectors.map((s: any) => ({ label: s.sector, value: s.contrib_bps }))} diverging fmt={(v) => `${v > 0 ? '+' : ''}${v.toFixed(1)} bp`} labelWidth="11rem" />
      </Panel>
      {d.note && <Source>{d.note}</Source>}
      <Source>{d.source}</Source>
    </div>
  );
}

// ── TRA ──────────────────────────────────────────────────────────────────────
const SET_LABEL: Record<string, string> = { assets: 'Asset classes', sectors: 'US sectors', factors: 'Factors', countries: 'Countries' };
export function TraView({ onOpen }: { onOpen: (s: string) => void }) {
  const [set, setSet] = useState('assets');
  const [custom, setCustom] = useState('');
  const [applied, setApplied] = useState('');
  const url = applied ? `/api/v1/mkt/tra?symbols=${encodeURIComponent(applied)}` : `/api/v1/mkt/tra?set=${set}`;
  const { data: d, error, loading } = useJSON<any>(url, 1_800_000);
  const controls = (
    <div className="flex flex-wrap items-center gap-1">
      {Object.entries(SET_LABEL).map(([k, l]) => <Chip key={k} on={!applied && set === k} onClick={() => { setApplied(''); setSet(k); }}>{l}</Chip>)}
      <form className="flex items-center gap-1 ml-2" onSubmit={(e) => { e.preventDefault(); setApplied(custom.trim().toUpperCase()); }}>
        <input value={custom} onChange={(e) => setCustom(e.target.value)} placeholder="Your symbols: AAPL, MSFT, ^N225" aria-label="Custom symbols"
          className="bg-surface-1 border border-border px-2 py-1 text-xs text-text-primary w-56" />
        <button className="px-2 py-1 border border-border text-[11px] text-text-secondary hover:text-text-primary">Compare</button>
      </form>
    </div>
  );
  if (loading && !d) return <div className="space-y-2">{controls}<Loading label="Loading total returns…" /></div>;
  if (error && !d) return <div className="space-y-2">{controls}<ErrorBox msg={error} /></div>;
  if (!d) return null;
  // shade each cell by its rank within the column, so leaders and laggards read across periods
  const ranks: Record<string, Map<string, number>> = {};
  for (const p of d.periods) {
    const vals = d.rows.filter((r: any) => r[p] != null).sort((a: any, b: any) => b[p] - a[p]);
    ranks[p] = new Map(vals.map((r: any, i: number) => [r.symbol, vals.length > 1 ? i / (vals.length - 1) : 0.5]));
  }
  return (
    <div className="space-y-3">
      {controls}
      <Panel title={`Total returns — ${applied ? 'your symbols' : SET_LABEL[d.set] ?? d.set}`} right={<span className="text-[11px] text-text-tertiary">as of {d.as_of}</span>}>
        <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Asset</th>
            {d.periods.map((p: string) => <th key={p} className="text-right font-normal px-1">{p}{p === '3Y' || p === '5Y' ? ' ann.' : ''}</th>)}
            <th className="text-right font-normal px-1">1Y vol</th></tr></thead>
          <tbody>{d.rows.map((r: any) => (
            <tr key={r.symbol} onClick={() => onOpen(r.symbol)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-2">
              <td className="py-1 font-sans whitespace-nowrap"><span className="text-text-primary">{r.symbol}</span> <span className="text-text-tertiary">{r.name !== r.symbol ? r.name : ''}</span></td>
              {d.periods.map((p: string) => {
                const rk = ranks[p].get(r.symbol);
                const bg = rk == null ? undefined : rk <= 0.2 ? 'rgb(var(--c-green) / 0.12)' : rk >= 0.8 ? 'rgb(var(--c-red) / 0.12)' : undefined;
                return <td key={p} className={cn('text-right px-1', sign(r[p]))} style={{ background: bg }}>{pct(r[p])}</td>;
              })}
              <td className="text-right px-1 text-text-secondary">{r.vol_1y != null ? `${(r.vol_1y * 100).toFixed(1)}%` : '—'}</td></tr>))}</tbody>
        </table></div>
      </Panel>
      <Source>{d.source} Shading marks the top and bottom fifth of each column.</Source>
    </div>
  );
}

// ── WPE ──────────────────────────────────────────────────────────────────────
export function WpeView({ onOpen }: { onOpen: (s: string) => void }) {
  const { data: d, error, loading } = useJSON<any>('/api/v1/mkt/wpe', 6 * 3_600_000);
  if (loading && !d) return <Loading label="Loading country valuations…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  const name = (iso: string) => { try { return new Intl.DisplayNames(['en'], { type: 'region' }).of(iso) ?? iso; } catch { return iso; } };
  const priced = d.rows.filter((r: any) => r.pe);
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Tile label="Median P/E" value={d.median_pe.toFixed(1)} sub={`across ${priced.length} markets`} />
        <Tile label="Cheapest" value={priced[0] ? name(priced[0].iso) : '—'} sub={priced[0] ? `${priced[0].pe.toFixed(1)}× trailing` : ''} />
        <Tile label="Most expensive" value={priced.at(-1) ? name(priced.at(-1).iso) : '—'} sub={priced.at(-1) ? `${priced.at(-1).pe.toFixed(1)}× trailing` : ''} />
        <Tile label="United States vs median" value={pct(d.rows.find((r: any) => r.iso === 'US')?.vs_median, 0)} sub="premium of US P/E over the median market" />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)] gap-3">
        <Panel title="Valuation by country (cheapest first)">
          <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
            <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Market</th><th className="text-left font-normal">ETF</th>
              <th className="text-right font-normal">P/E</th><th className="text-right font-normal">Earnings yield</th><th className="text-right font-normal">Dividend yield</th>
              <th className="text-right font-normal">vs median</th><th className="text-right font-normal">1Y</th></tr></thead>
            <tbody>{d.rows.map((r: any) => (
              <tr key={r.iso} onClick={() => onOpen(r.etf)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-2" title={r.name}>
                <td className="py-1 font-sans text-text-primary">{name(r.iso)}</td><td className="text-text-secondary">{r.etf}</td>
                <td className="text-right text-text-primary">{r.pe ? r.pe.toFixed(1) : '—'}</td>
                <td className="text-right">{r.earnings_yield != null ? `${(r.earnings_yield * 100).toFixed(1)}%` : '—'}</td>
                <td className="text-right">{r.div_yield != null ? `${(r.div_yield * 100).toFixed(1)}%` : '—'}</td>
                <td className={cn('text-right', r.vs_median != null && (r.vs_median < 0 ? 'text-green' : 'text-red'))}>{pct(r.vs_median, 0)}</td>
                <td className={cn('text-right', sign(r.ret_1y))}>{pct(r.ret_1y, 0)}</td></tr>))}</tbody>
          </table></div>
        </Panel>
        <Panel title="P/E relative to the median market">
          <BarList data={priced.map((r: any) => ({ label: name(r.iso), value: r.vs_median * 100 }))} diverging
            fmt={(v) => `${v > 0 ? '+' : ''}${v.toFixed(0)}%`} labelWidth="8.5rem" posColor="#e66767" negColor="#199e70" />
        </Panel>
      </div>
      <Source>{d.source} Price-to-book is left out: Yahoo's ETF book values don't match index figures.</Source>
    </div>
  );
}

// ── VAP ──────────────────────────────────────────────────────────────────────
export function VapView({ symbol }: { symbol: string }) {
  const [days, setDays] = useState(120);
  const { data: d, error, loading } = useJSON<any>(`/api/v1/mkt/vap/${encodeURIComponent(symbol)}?days=${days}`, 1_800_000);
  const pick = <div className="flex gap-1">{[[20, '1M'], [60, '3M'], [120, '6M'], [250, '1Y'], [500, '2Y']].map(([n, l]) => <Chip key={n} on={days === n} onClick={() => setDays(n as number)}>{l}</Chip>)}</div>;
  if (loading && !d) return <div className="space-y-2">{pick}<Loading label="Building the volume profile…" /></div>;
  if (error && !d) return <div className="space-y-2">{pick}<ErrorBox msg={error} /></div>;
  if (!d) return null;
  const max = Math.max(...d.bins.map((b: any) => b.volume));
  const bins = [...d.bins].reverse();                               // highest price at the top
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">{pick}<span className="text-[11px] text-text-tertiary">{d.from} → {d.to} · {d.days} sessions</span></div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Tile label="Last" value={fmtPrice(d.last)} sub={d.position} cls={d.position === 'above value' ? 'text-green' : d.position === 'below value' ? 'text-red' : ''} />
        <Tile label="Point of control" value={fmtPrice(d.poc)} sub={`last is ${fmtPct(d.last / d.poc - 1, 1)} from it`} />
        <Tile label="Value area high" value={fmtPrice(d.value_high)} sub="70% of volume traded below" />
        <Tile label="Value area low" value={fmtPrice(d.value_low)} sub="and above this" />
      </div>
      <Panel title="Volume at price">
        <div className="space-y-px py-1" role="img" aria-label={`Volume profile of ${symbol}: most volume traded near ${fmtPrice(d.poc)}`}>
          {bins.map((b: any) => {
            const inVA = b.low >= d.value_low - 1e-9 && b.high <= d.value_high + 1e-9;
            const isPoc = d.poc >= b.low && d.poc <= b.high, hasLast = d.last >= b.low && d.last <= b.high;
            return (
              <div key={b.low} className="flex items-center gap-2 h-[11px] text-[10px] font-mono tabular-nums" title={`${fmtPrice(b.low)}–${fmtPrice(b.high)}: ${(b.share * 100).toFixed(1)}% of volume`}>
                <span className={cn('w-16 text-right shrink-0', hasLast ? 'text-text-primary font-semibold' : 'text-text-tertiary')}>{fmtPrice((b.low + b.high) / 2)}</span>
                <div className="flex-1 h-full relative">
                  <div className="h-full rounded-r-sm" style={{ width: `${(b.volume / max) * 100}%`, background: isPoc ? 'rgb(var(--c-bloomberg))' : inVA ? 'rgb(var(--c-bloomberg) / 0.45)' : 'rgb(var(--c-text-tertiary) / 0.35)' }} />
                  {hasLast && <div className="absolute inset-y-0 left-0 right-0 border-t border-dashed border-text-primary/70 top-1/2" />}
                </div>
                <span className="w-10 text-right text-text-tertiary shrink-0">{(b.share * 100).toFixed(1)}%</span>
              </div>);
          })}
        </div>
        <div className="flex gap-4 text-[10px] text-text-tertiary pt-2">
          <span><span className="inline-block w-2.5 h-2.5 align-middle mr-1" style={{ background: 'rgb(var(--c-bloomberg))' }} />Point of control</span>
          <span><span className="inline-block w-2.5 h-2.5 align-middle mr-1" style={{ background: 'rgb(var(--c-bloomberg) / 0.45)' }} />Value area (70%)</span>
          <span>– – Last price</span>
        </div>
      </Panel>
      <Source>{d.source}</Source>
    </div>
  );
}

// ── OVME ─────────────────────────────────────────────────────────────────────
function Field({ label, value, onChange, step = 'any', suffix }: { label: string; value: number; onChange: (v: number) => void; step?: string; suffix?: string }) {
  return (
    <label className="block text-[10px] uppercase tracking-wide text-text-tertiary">{label}
      <span className="mt-1 flex items-center gap-1"><input type="number" step={step} value={Number.isFinite(value) ? value : ''} onChange={(e) => onChange(parseFloat(e.target.value))}
        className="w-full bg-surface-1 border border-border px-2 py-1 text-xs font-mono text-text-primary normal-case" />{suffix && <span className="normal-case">{suffix}</span>}</span>
    </label>
  );
}

export function OvmeView({ symbol, q }: { symbol: string; q: any }) {
  const money = (v: number) => (Math.abs(v) < 0.005 ? '0.00' : v.toFixed(2));   // option values: cents, not price-style decimals
  const spot0 = q?.price ?? 100;
  const [kind, setKind] = useState<OptionKind>('call');
  const [spot, setSpot] = useState<number>(+spot0.toFixed(2));
  const [strike, setStrike] = useState<number>(Math.round(spot0));
  const [days, setDays] = useState(30);
  const [vol, setVol] = useState(25);
  const [rate, setRate] = useState(4);
  const [div, setDiv] = useState<number>(q?.dividend_yield != null ? +(q.dividend_yield * 100).toFixed(2) : 0);
  const [mkt, setMkt] = useState<number>(NaN);
  const inp = { kind, spot, strike, years: days / 365, vol: vol / 100, rate: rate / 100, div: div / 100 };
  const valid = spot > 0 && strike > 0 && days >= 0 && vol > 0;
  const r = useMemo(() => (valid ? blackScholes(inp) : null), [kind, spot, strike, days, vol, rate, div]);   // eslint-disable-line react-hooks/exhaustive-deps
  const iv = valid && mkt > 0 ? impliedVol(mkt, { kind, spot, strike, years: days / 365, rate: rate / 100, div: div / 100 }) : null;
  const scen = valid ? [-0.2, -0.1, -0.05, 0, 0.05, 0.1, 0.2].map((m) => {
    const s = spot * (1 + m), now = blackScholes({ ...inp, spot: s }).price, exp = blackScholes({ ...inp, spot: s, years: 0 }).price;
    return { m, s, now, exp, pnl: r ? now - r.price : 0 };
  }) : [];
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 xl:grid-cols-[320px_minmax(0,1fr)] gap-3">
        <Panel title={`Option on ${symbol}`}>
          <div className="space-y-3">
            <div className="flex gap-1">{(['call', 'put'] as const).map((k) => <Chip key={k} on={kind === k} onClick={() => setKind(k)}>{k === 'call' ? 'Call' : 'Put'}</Chip>)}</div>
            <div className="grid grid-cols-2 gap-2">
              <Field label="Spot" value={spot} onChange={setSpot} />
              <Field label="Strike" value={strike} onChange={setStrike} />
              <Field label="Days to expiry" value={days} onChange={setDays} step="1" />
              <Field label="Volatility" value={vol} onChange={setVol} suffix="%" />
              <Field label="Risk-free rate" value={rate} onChange={setRate} suffix="%" />
              <Field label="Dividend yield" value={div} onChange={setDiv} suffix="%" />
            </div>
            <Field label="Market price (optional, for implied vol)" value={mkt} onChange={setMkt} />
            <p className="text-[10px] text-text-tertiary leading-relaxed">Spot and dividend yield start from the live quote. Use OMON for traded prices and OVDV for the volatility surface.</p>
          </div>
        </Panel>
        <div className="space-y-3">
          {!r ? <ErrorBox msg="Enter a positive spot, strike and volatility." /> : <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              <Tile label="Theoretical value" value={money(r.price)} sub={`${((r.price / spot) * 100).toFixed(2)}% of spot`} />
              <Tile label="Delta" value={r.delta.toFixed(3)} sub={`≈ ${(r.delta * 100).toFixed(0)} shares per contract of 100`} />
              <Tile label="Gamma" value={r.gamma.toFixed(4)} sub="delta change per 1.00 move" />
              <Tile label="Vega" value={r.vega.toFixed(3)} sub="per 1 vol point" />
              <Tile label="Theta" value={r.theta.toFixed(3)} sub="per calendar day" cls={sign(r.theta)} />
              <Tile label="Rho" value={r.rho.toFixed(3)} sub="per 1% rate move" />
              <Tile label="Chance in the money" value={`${(r.probItm * 100).toFixed(0)}%`} sub="risk-neutral, at expiry" />
              <Tile label="Implied vol" value={iv != null ? `${(iv * 100).toFixed(1)}%` : mkt > 0 ? 'Out of bounds' : '—'} sub={mkt > 0 ? `from a price of ${money(mkt)}` : 'enter a market price'} />
            </div>
            <Panel title="Scenarios — the underlying moves today">
              <table className="w-full text-2xs font-mono tabular-nums">
                <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Move</th><th className="text-right font-normal">Spot</th>
                  <th className="text-right font-normal">Value now</th><th className="text-right font-normal">P&amp;L now</th><th className="text-right font-normal">Value at expiry</th></tr></thead>
                <tbody>{scen.map((x) => (
                  <tr key={x.m} className={cn('border-t border-border-subtle', x.m === 0 && 'bg-bloomberg/5')}>
                    <td className="py-1">{pct(x.m, 0)}</td><td className="text-right">{fmtPrice(x.s)}</td><td className="text-right text-text-primary">{money(x.now)}</td>
                    <td className={cn('text-right', sign(x.pnl))}>{x.pnl >= 0 ? '+' : ''}{money(x.pnl)}</td><td className="text-right text-text-secondary">{money(x.exp)}</td></tr>))}</tbody>
              </table>
            </Panel>
          </>}
          <Source>Black–Scholes–Merton for a European option with a continuous dividend yield. US single-stock options are American; for calls without dividends the values agree, for puts this is a lower bound.</Source>
        </div>
      </div>
    </div>
  );
}


// ── MRR ──────────────────────────────────────────────────────────────────────
const MRR_INDICES = ['SPX', 'NDX', 'INDU', 'UKX', 'DAX', 'CAC', 'SX5E', 'HSI'] as const;
const MRR_PERIODS = ['1D', '1W', '1M', '3M', 'YTD', '1Y'] as const;
export function MrrView({ onOpen }: { onOpen: (s: string) => void }) {
  const [code, setCode] = useState<string>('SPX');
  const [period, setPeriod] = useState<string>('YTD');
  const [sector, setSector] = useState<string | null>(null);
  const { data: d, error, loading } = useJSON<any>(`/api/v1/mkt/mrr/${code}?period=${period}`, 900_000);
  const controls = (
    <div className="flex flex-wrap items-center gap-1">
      {MRR_INDICES.map((c) => <Chip key={c} on={code === c} onClick={() => { setCode(c); setSector(null); }}>{c}</Chip>)}
      <span className="w-3" />
      {MRR_PERIODS.map((p) => <Chip key={p} on={period === p} onClick={() => setPeriod(p)}>{p}</Chip>)}
    </div>
  );
  if (loading && !d) return <div className="space-y-2">{controls}<Loading label="Ranking every member of the index…" /></div>;
  if (error && !d) return <div className="space-y-2">{controls}<ErrorBox msg={error} /></div>;
  if (!d) return null;
  const rows = sector ? d.rows.filter((r: any) => (r.sector || 'Other') === sector) : d.rows;
  const b = d.index_return;
  return (
    <div className="space-y-3">
      {controls}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Tile label={`${d.name} ${d.period}`} value={pct(b)} cls={sign(b)} sub={`price return to ${d.as_of}`} />
        <Tile label="Beat the index" value={d.beat_index != null ? `${d.beat_index} of ${d.count}` : '—'}
          sub={d.beat_index != null ? `${Math.round((d.beat_index / d.count) * 100)}% of members` : ''} />
        <Tile label="Median member" value={pct(d.median)} cls={sign(d.median)} sub={`equal-weight average ${pct(d.equal_weight)}`} />
        <Tile label="Top vs bottom fifth" value={pct(d.top_quintile - d.bottom_quintile)} sub={`${pct(d.top_quintile)} vs ${pct(d.bottom_quintile)}`} />
        <Tile label="Up over the period" value={`${d.positive} of ${d.count}`} sub={d.members_total > d.count ? `${d.members_total - d.count} without prices` : 'all members priced'} />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_20rem] gap-3">
        <Panel title={`Members ranked by ${d.period} return${sector ? ` — ${sector}` : ''}`}
          right={sector ? <button onClick={() => setSector(null)} className="text-[11px] text-bloomberg hover:underline">All sectors</button> : <span className="text-[11px] text-text-tertiary">{d.count} members</span>}>
          <div className="overflow-auto max-h-[34rem]"><table className="w-full text-2xs font-mono tabular-nums">
            <thead className="sticky top-0 bg-surface-1"><tr className="text-text-tertiary"><th className="text-right font-normal py-1 pr-2">#</th><th className="text-left font-normal">Member</th>
              <th className="text-left font-normal">Sector</th>
              {MRR_PERIODS.map((p) => <th key={p} className={cn('text-right font-normal px-1', p === d.period && 'text-text-primary')}>{p}</th>)}
              <th className="text-right font-normal px-1">vs index</th></tr></thead>
            <tbody>{rows.map((r: any) => {
              const rel = b != null ? r[d.period] - b : null;
              return (
                <tr key={r.symbol} onClick={() => onOpen(r.symbol)} className="border-t border-border-subtle cursor-pointer hover:bg-surface-2" title={r.name}>
                  <td className="text-right pr-2 text-text-tertiary">{r.rank}</td>
                  <td className="py-1 font-sans whitespace-nowrap"><span className="text-text-primary">{r.symbol}</span> <span className="text-text-tertiary">{(r.name ?? '').slice(0, 22)}</span></td>
                  <td className="font-sans text-text-tertiary whitespace-nowrap max-w-[10rem] truncate">{r.sector ?? ''}</td>
                  {MRR_PERIODS.map((p) => <td key={p} className={cn('text-right px-1', sign(r[p]), p === d.period && 'font-semibold')}>{pct(r[p])}</td>)}
                  <td className={cn('text-right px-1', sign(rel))}>{pct(rel)}</td></tr>
              );
            })}</tbody>
          </table></div>
        </Panel>
        <Panel title={`Median member by sector (${d.period})`}>
          <div className="space-y-0.5">{d.sectors.map((x: any) => (
            <button key={x.sector} onClick={() => setSector(sector === x.sector ? null : x.sector)}
              className={cn('w-full flex items-center justify-between gap-2 px-1.5 py-1 rounded-sm text-[11px] text-left hover:bg-surface-2', sector === x.sector && 'bg-surface-2')}>
              <span className="text-text-secondary truncate">{x.sector} <span className="text-text-tertiary">({x.count})</span></span>
              <span className={cn('font-mono', sign(x.median))}>{pct(x.median)}</span></button>))}</div>
          <p className="text-[10px] text-text-tertiary mt-2">Click a sector to rank only its members.</p>
        </Panel>
      </div>
      <Source>{d.source}</Source>
    </div>
  );
}

// ── GE ───────────────────────────────────────────────────────────────────────
const BAND_LABEL: Record<string, string> = { '-2sd': '−2σ', '-1sd': '−1σ', mean: 'Average', '+1sd': '+1σ', '+2sd': '+2σ' };
export function GeView({ symbol }: { symbol: string }) {
  const [years, setYears] = useState(10);
  const [view, setView] = useState<'pe' | 'ey'>('pe');
  const { data: d, error, loading } = useJSON<any>(`/api/v1/mkt/ge/${encodeURIComponent(symbol)}?years=${years}`, 6 * 3_600_000);
  const controls = (
    <div className="flex flex-wrap gap-1">
      {[5, 10, 15].map((y) => <Chip key={y} on={years === y} onClick={() => setYears(y)}>{y} years</Chip>)}
      <span className="w-3" />
      <Chip on={view === 'pe'} onClick={() => setView('pe')}>P/E</Chip>
      <Chip on={view === 'ey'} onClick={() => setView('ey')}>Earnings yield</Chip>
    </div>
  );
  const priceRows = useMemo(() => (d?.points ?? []).map((p: any) => ({
    date: p.date, price: p.price,
    mean: p.eps > 0 ? p.eps * d.bands.mean : null, hi: p.eps > 0 ? p.eps * d.bands['+1sd'] : null,
    lo: p.eps > 0 && d.bands['-1sd'] > 0 ? p.eps * d.bands['-1sd'] : null })), [d]);
  if (loading && !d) return <div className="space-y-2">{controls}<Loading label="Reading earnings from SEC filings…" /></div>;
  if (error && !d) return <div className="space-y-2">{controls}<ErrorBox msg={error} /></div>;
  if (!d) return null;
  const x = (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(1)}×`);
  const refs = Object.entries(d.bands).filter(([, v]) => (v as number) > 0)
    .map(([k, v]) => ({ value: v as number, label: BAND_LABEL[k], color: k === 'mean' ? 'rgb(var(--c-text-secondary))' : 'rgb(var(--c-text-tertiary))' }));
  const verdict = d.z == null ? null : d.z > 1 ? 'expensive against its own history' : d.z < -1 ? 'cheap against its own history' : 'within its normal range';
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 flex-wrap">{controls}<span className="text-[11px] text-text-tertiary">weekly, to {d.as_of}</span></div>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Tile label="Trailing P/E" value={x(d.pe)} sub={verdict ?? 'no positive earnings'} />
        <Tile label={`${d.years}-year average`} value={x(d.mean)} sub={`median ${x(d.median)} · σ ${d.sd.toFixed(1)}`} />
        <Tile label="Percentile" value={d.percentile != null ? `${Math.round(d.percentile * 100)}th` : '—'} sub={`range ${x(d.min)} – ${x(d.max)}`} />
        <Tile label="Standard deviations" value={d.z != null ? `${d.z > 0 ? '+' : ''}${d.z.toFixed(2)}σ` : '—'} sub="from the average" />
        <Tile label={d.basis === 'sec' ? 'EPS, last 4 quarters' : 'Trailing EPS'} value={d.eps_ttm != null ? d.eps_ttm.toFixed(2) : '—'}
          sub={`price ${d.price.toFixed(2)} · earnings yield ${d.earnings_yield != null ? `${(d.earnings_yield * 100).toFixed(2)}%` : '—'}`} />
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {view === 'pe' ? (
          <Panel title="Trailing P/E with average and ±1σ, ±2σ bands">
            <div className="mkt-chart-surface"><LineChart rows={d.points} x="date" height={260} controls={false} fmt={(v) => `${v.toFixed(1)}×`} refs={refs}
              lines={[{ key: 'pe', label: 'P/E', color: 'rgb(var(--c-bloomberg))' }]} /></div>
          </Panel>
        ) : (
          <Panel title="Earnings yield (EPS ÷ price) — shows loss-making periods too">
            <div className="mkt-chart-surface"><LineChart rows={d.points.map((p: any) => ({ date: p.date, ey: p.earnings_yield != null ? p.earnings_yield * 100 : null }))}
              x="date" height={260} controls={false} fmt={(v) => `${v.toFixed(2)}%`} baseline={0}
              lines={[{ key: 'ey', label: 'Earnings yield', color: 'rgb(var(--c-bloomberg))' }]} /></div>
          </Panel>
        )}
        <Panel title="Price against the prices the P/E bands imply">
          <div className="mkt-chart-surface"><LineChart rows={priceRows} x="date" height={260} controls={false} fmt={(v) => v.toFixed(2)}
            lines={[{ key: 'price', label: 'Price', color: 'rgb(var(--c-bloomberg))' }, { key: 'hi', label: '+1σ', color: 'rgb(var(--c-red))' },
              { key: 'mean', label: 'Average P/E', color: 'rgb(var(--c-text-secondary))' }, { key: 'lo', label: '−1σ', color: 'rgb(var(--c-green))' }]} /></div>
        </Panel>
      </div>
      <Panel title="What each band implies on today's earnings">
        <table className="w-full text-2xs font-mono tabular-nums">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Band</th><th className="text-right font-normal">P/E</th>
            <th className="text-right font-normal">Implied price</th><th className="text-right font-normal">vs today</th></tr></thead>
          <tbody>{Object.keys(BAND_LABEL).slice().reverse().map((k) => {
            const px = d.band_prices[k];
            return <tr key={k} className="border-t border-border-subtle"><td className="py-1 font-sans text-text-secondary">{BAND_LABEL[k]}</td>
              <td className="text-right">{x(d.bands[k])}</td><td className="text-right">{px != null ? px.toFixed(2) : '—'}</td>
              <td className={cn('text-right', sign(px != null ? px / d.price - 1 : null))}>{px != null ? pct(px / d.price - 1) : '—'}</td></tr>;
          })}</tbody>
        </table>
      </Panel>
      <Source>{d.note} {d.source}</Source>
    </div>
  );
}

// ── WB ───────────────────────────────────────────────────────────────────────
const REGION_LABEL: Record<string, string> = { americas: 'Americas', europe: 'Europe', mea: 'Middle East & Africa', apac: 'Asia-Pacific' };
export function WbView() {
  const [region, setRegion] = useState<string | null>(null);
  const { data: d, error, loading } = useJSON<any>('/api/v1/mkt/wb', 1_800_000);
  if (loading && !d) return <Loading label="Loading government bond yields…" />;
  if (error && !d) return <ErrorBox msg={error} />;
  if (!d) return null;
  const rows = d.rows.filter((r: any) => !region || r.region === region);
  const bp = (v: number | null | undefined) => (v == null ? '—' : `${v > 0 ? '+' : ''}${Math.round(v)}`);
  const y = (v: number | null | undefined) => (v == null ? '—' : `${v.toFixed(2)}%`);
  const live = d.rows.filter((r: any) => !r.stale);
  const top = live.filter((r: any) => r.real_yield != null).sort((a: any, b: any) => b.real_yield - a.real_yield)[0];
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        <Tile label="US 10-year" value={y(d.us_10y)} sub="the benchmark the spreads are measured against" />
        <Tile label="Bund 10-year" value={y(d.de_10y)} sub="euro-area spreads are measured against it" />
        <Tile label="Median 10-year" value={y(d.median_10y)} sub={`across ${live.length} markets`} />
        <Tile label="Highest real yield" value={top ? top.name : '—'} sub={top ? `${y(top.real_yield)} after inflation` : ''} />
        {d.us_tips_10y && <Tile label="US 10-year TIPS" value={y(d.us_tips_10y.yield)} sub={`the market's real yield, ${d.us_tips_10y.date}`} />}
      </div>
      <div className="flex flex-wrap gap-1">
        <Chip on={!region} onClick={() => setRegion(null)}>All</Chip>
        {Object.entries(REGION_LABEL).map(([k, l]) => <Chip key={k} on={region === k} onClick={() => setRegion(k)}>{l}</Chip>)}
      </div>
      <Panel title="10-year government yields (highest first)" right={<span className="text-[11px] text-text-tertiary">{rows.length} markets</span>}>
        <div className="overflow-x-auto"><table className="w-full text-2xs font-mono tabular-nums">
          <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Country</th><th className="text-right font-normal px-1">10Y</th>
            <th className="text-right font-normal px-1">1M bp</th><th className="text-right font-normal px-1">1Y bp</th><th className="text-right font-normal px-1">vs US bp</th>
            <th className="text-right font-normal px-1">vs Bund bp</th><th className="text-right font-normal px-1">Policy</th><th className="text-right font-normal px-1">10Y − policy</th>
            <th className="text-right font-normal px-1">Inflation</th><th className="text-right font-normal px-1">Real 10Y</th><th className="text-right font-normal px-1">2Y</th>
            <th className="text-right font-normal px-1">2s10s</th><th className="text-left font-normal px-1">Rating</th><th className="text-left font-normal px-1">As of</th></tr></thead>
          <tbody>{rows.map((r: any) => (
            <tr key={r.iso} className={cn('border-t border-border-subtle', r.stale && 'opacity-60')} title={r.source ?? ''}>
              <td className="py-1 font-sans whitespace-nowrap text-text-primary">{r.name}</td>
              <td className="text-right px-1 font-semibold">{y(r.yield_10y)}</td>
              <td className={cn('text-right px-1', sign(r.change_1m_bp))}>{bp(r.change_1m_bp)}</td>
              <td className={cn('text-right px-1', sign(r.change_1y_bp))}>{bp(r.change_1y_bp)}</td>
              <td className="text-right px-1 text-text-secondary">{bp(r.spread_us_bp)}</td>
              <td className="text-right px-1 text-text-secondary">{bp(r.spread_de_bp)}</td>
              <td className="text-right px-1">{y(r.policy_rate)}</td>
              <td className={cn('text-right px-1', sign(r.term_spread_bp))}>{bp(r.term_spread_bp)}</td>
              <td className="text-right px-1 text-text-secondary" title={r.inflation_source ?? ''}>{r.inflation != null ? `${r.inflation.toFixed(1)}%` : '—'}{r.inflation_source === 'IMF estimate' ? '*' : ''}</td>
              <td className={cn('text-right px-1', sign(r.real_yield))}>{y(r.real_yield)}</td>
              <td className="text-right px-1 text-text-secondary">{y(r.yield_2y)}</td>
              <td className={cn('text-right px-1', sign(r.slope_2s10s_bp))}>{bp(r.slope_2s10s_bp)}</td>
              <td className="px-1 font-sans text-text-secondary">{r.rating ?? '—'}</td>
              <td className="px-1 font-sans text-text-tertiary whitespace-nowrap">{r.date ?? '—'}{r.daily ? '' : ' (monthly)'}</td></tr>))}</tbody>
        </table></div>
      </Panel>
      <Source>{d.note} * = IMF estimate (no recent CPI print). Faded rows are more than 45 days old. {d.source}</Source>
    </div>
  );
}

// ── DS: filing search ────────────────────────────────────────────────────────
const DS_SUGGEST = ['share repurchase', 'guidance outlook', 'largest risks', 'China', 'tariffs', 'artificial intelligence', 'customer concentration', 'litigation', 'supply constraints'];
function Highlight({ text, terms }: { text: string; terms: string[] }) {
  const stems = terms.filter((t) => t.length > 1).map((t) => t.replace(/(ies|ing|es|ed|s)$/, '').replace(/[.*+?^${}()|[\]\\]/g, '\\$&'));
  if (!stems.length) return <>{text}</>;
  const re = new RegExp(`\\b(${stems.join('|')})[a-z]*`, 'gi');
  const out: React.ReactNode[] = [];
  let last = 0, m: RegExpExecArray | null;
  while ((m = re.exec(text))) {
    out.push(<Fragment key={`t${last}`}>{text.slice(last, m.index)}</Fragment>, <mark key={`m${m.index}`} className="bg-bloomberg/25 text-text-primary rounded-sm px-px">{m[0]}</mark>);
    last = m.index + m[0].length;
  }
  out.push(<Fragment key="end">{text.slice(last)}</Fragment>);
  return <>{out}</>;
}
export function DsView({ symbol, onGo }: { symbol: string; onGo: (fn: string, s?: string) => void }) {
  const [input, setInput] = useState('');
  const [query, setQuery] = useState('');
  const [form, setForm] = useState<string | null>(null);
  const url = query ? `/api/v1/mkt/ds/${encodeURIComponent(symbol)}?q=${encodeURIComponent(query)}${form ? `&forms=${form === '10-K' ? '10-K,20-F,40-F' : form}` : ''}&limit=15` : null;
  const { data: d, error, loading } = useJSON<any>(url);
  const run = (q: string) => { setInput(q); setQuery(q.trim()); };
  return (
    <div className="space-y-3">
      <form className="flex flex-wrap items-center gap-2" onSubmit={(e) => { e.preventDefault(); run(input); }}>
        <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={`Search ${symbol}'s filings — e.g. buyback, China, guidance`} aria-label="Search filings"
          className="bg-surface-1 border border-border rounded-sm px-2 py-1.5 text-xs text-text-primary flex-1 min-w-[16rem]" />
        <button className="px-3 py-1.5 border border-bloomberg text-bloomberg text-[11px] rounded-sm hover:bg-bloomberg/10">Search</button>
        <div className="flex gap-1">{[null, '10-K', '10-Q', '8-K'].map((f) => <Chip key={f ?? 'all'} on={form === f} onClick={() => setForm(f)}>{f ?? 'All filings'}</Chip>)}</div>
      </form>
      {!query && (
        <div className="space-y-2">
          <p className="text-xs text-text-secondary">Searches the full text of {symbol}'s latest annual report, its last two quarterly reports and its last three 8-Ks with their press releases, and shows the passages that answer best.</p>
          <div className="flex flex-wrap gap-1">{DS_SUGGEST.map((q) => <Chip key={q} on={false} onClick={() => run(q)}>{q}</Chip>)}</div>
        </div>
      )}
      {query && loading && !d && <Loading label="Reading the filings (the first search on a company takes a few seconds)…" />}
      {query && error && <ErrorBox msg={error} />}
      {query && d && (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2 text-[11px] text-text-tertiary">
            <span>{d.matches} passages match · showing the best {d.hits.length}{d.also?.length ? ` · also matching ${d.also.join(', ')}` : ''}</span>
            <button onClick={() => onGo('AI', symbol)} className="text-bloomberg hover:underline">Ask the AI assistant to summarise these filings →</button>
          </div>
          {!d.hits.length && <p className="text-xs text-text-secondary">Nothing in these filings matches — try other words.</p>}
          <div className="space-y-2">{d.hits.map((h: any, i: number) => (
            <div key={i} className="border border-border rounded-md bg-surface-1 px-3 py-2">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-1">
                <div className="text-[11px]"><span className="font-semibold text-text-primary">{h.form}</span> <span className="text-text-tertiary">filed {h.filed}{h.period ? ` · period ${h.period}` : ''}</span>
                  {h.section && <span className="text-text-secondary"> · {h.section}</span>}</div>
                <a href={h.url} target="_blank" rel="noreferrer" className="text-[11px] text-bloomberg hover:underline">Open filing ↗</a>
              </div>
              <p className="text-xs text-text-secondary leading-relaxed"><Highlight text={h.text} terms={[...d.terms, ...(d.also ?? [])]} /></p>
            </div>))}</div>
          <Panel title="Filings searched">
            <table className="w-full text-2xs font-mono tabular-nums">
              <thead><tr className="text-text-tertiary"><th className="text-left font-normal py-1">Form</th><th className="text-left font-normal">Filed</th><th className="text-left font-normal">Period</th><th className="text-right font-normal">Passages</th><th /></tr></thead>
              <tbody>{d.documents.map((x: any) => (
                <tr key={x.url} className="border-t border-border-subtle"><td className="py-1">{x.form}</td><td>{x.filed}</td><td>{x.period ?? '—'}</td><td className="text-right">{x.passages}</td>
                  <td className="text-right"><a href={x.url} target="_blank" rel="noreferrer" className="text-bloomberg hover:underline font-sans">SEC ↗</a></td></tr>))}</tbody>
            </table>
          </Panel>
          <Source>{d.source}</Source>
        </>
      )}
    </div>
  );
}
