// Screens modelled on standard Bloomberg functions the platform lacked (backend: api/marketdata/bbgplus.py):
//   IMOV index movers · TRA total returns · WPE world valuations · VAP volume at price · OVME option calculator
import { useMemo, useState } from 'react';
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
