// WIRP (Fed rate probabilities), AUCT (Treasury auctions), EIA (oil & gas inventories),
// WETR (degree days), INSD (Form 4 insiders), 13F (investor holdings).
import { useState } from 'react';
import { ExternalLink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ErrorBox, fmtBig, fmtPrice, Loading, Panel, useJSON } from './shared';

const enc = encodeURIComponent;
const pc = (v: number | null | undefined, d = 1) => (v == null ? '—' : `${(v * 100).toFixed(d)}%`);
const sgn = (v: number | null | undefined, d = 1, suf = '') => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(d)}${suf}`);

function Stat({ label, value, sub, tone }: { label: string; value: React.ReactNode; sub?: React.ReactNode; tone?: 'up' | 'down' }) {
  return <div className="border border-border bg-surface-1 px-3 py-2"><div className="text-[10px] uppercase tracking-wide text-text-tertiary">{label}</div>
    <div className={cn('text-lg font-mono', tone === 'up' ? 'text-green' : tone === 'down' ? 'text-red' : 'text-text-primary')}>{value}</div>
    {sub && <div className="text-[10px] text-text-tertiary">{sub}</div>}</div>;
}

function Frame<T>({ url, label, refresh = 0, children }: { url: string | null; label: string; refresh?: number; children: (d: T) => React.ReactNode }) {
  const { data, error, loading } = useJSON<T>(url, refresh);
  if (loading && !data) return <Loading label={label} />;
  if (error && !data) return <ErrorBox msg={error} />;
  return data ? <>{children(data)}</> : null;
}

// ── WIRP ────────────────────────────────────────────────────────────────────
export function WirpView() {
  return <Frame<any> url="/api/v1/mkt/wirp" label="Pricing the FOMC path from fed funds futures…" refresh={900_000}>{(d) => {
    const path = d.path as { month: string; implied_rate: number }[];
    const lo = Math.min(d.effective_rate, ...path.map((p) => p.implied_rate)) - 0.15, hi = Math.max(d.effective_rate, ...path.map((p) => p.implied_rate)) + 0.15;
    const W = 760, H = 200, pad = 34;
    const sx = (i: number) => pad + (i / Math.max(1, path.length - 1)) * (W - 2 * pad), sy = (v: number) => H - pad - ((v - lo) / (hi - lo)) * (H - 2 * pad);
    const next = d.meetings[0];
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <Stat label="Fed funds target" value={d.target_lower != null ? `${d.target_lower.toFixed(2)}–${d.target_upper.toFixed(2)}%` : '—'} sub={`effective ${d.effective_rate?.toFixed(2)}%`} />
          {next && <Stat label={`Next meeting ${next.meeting}`} value={next.p_hike > 0.5 ? `Hike ${pc(next.p_hike, 0)}` : next.p_cut > 0.5 ? `Cut ${pc(next.p_cut, 0)}` : `Hold ${pc(1 - next.p_hike - next.p_cut, 0)}`}
            sub={`${sgn(next.change_bp, 0, 'bp')} priced`} tone={next.p_hike > 0.5 ? 'down' : next.p_cut > 0.5 ? 'up' : undefined} />}
          <Stat label="Priced by year-end" value={sgn(d.meetings.filter((m: any) => m.meeting.slice(0, 4) === String(new Date().getFullYear())).slice(-1)[0]?.cumulative_bp, 0, 'bp')} />
          <Stat label="Priced over the curve" value={sgn(d.meetings.slice(-1)[0]?.cumulative_bp, 0, 'bp')} sub={`to ${d.meetings.slice(-1)[0]?.meeting ?? '—'}`} />
        </div>
        <Panel title="Meeting-by-meeting probabilities">
          <table className="w-full text-xs">
            <thead><tr className="text-[10px] uppercase text-text-tertiary"><th className="text-left font-normal">Meeting</th><th className="text-right font-normal">Implied rate</th><th className="text-right font-normal">Move</th><th className="text-right font-normal">Cumulative</th><th className="text-left font-normal pl-4">Probabilities</th></tr></thead>
            <tbody>{d.meetings.map((m: any) => (
              <tr key={m.meeting} className="border-t border-border-subtle">
                <td className="py-1 font-mono text-text-primary">{m.meeting}</td><td className="text-right font-mono">{m.implied_rate.toFixed(3)}%</td>
                <td className={cn('text-right font-mono', m.change_bp > 2 ? 'text-red' : m.change_bp < -2 ? 'text-green' : '')}>{sgn(m.change_bp, 1, 'bp')}</td>
                <td className="text-right font-mono">{sgn(m.cumulative_bp, 0, 'bp')}</td>
                <td className="pl-4"><div className="flex h-4 w-64 overflow-hidden border border-border">{Object.entries<number>(m.probabilities).map(([k, v]) => (
                  <div key={k} title={`${k}: ${(v * 100).toFixed(0)}%`} style={{ width: `${v * 100}%` }}
                    className={cn('text-[9px] leading-4 text-center text-black overflow-hidden', k.startsWith('+0') ? 'bg-text-tertiary' : k.startsWith('-') ? 'bg-green' : 'bg-red')}>{v > 0.12 ? `${k} ${(v * 100).toFixed(0)}%` : ''}</div>))}</div></td>
              </tr>))}</tbody>
          </table>
        </Panel>
        <Panel title="Implied policy-rate path (monthly average)">
          <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Implied fed funds path">
            <line x1={pad} x2={W - pad} y1={sy(d.effective_rate)} y2={sy(d.effective_rate)} stroke="rgb(var(--c-border-strong))" strokeDasharray="4 3" />
            <text x={W - pad} y={sy(d.effective_rate) - 4} textAnchor="end" fontSize="10" fill="rgb(var(--c-text-tertiary))">today {d.effective_rate.toFixed(2)}%</text>
            <path d={path.map((p, i) => `${i ? 'L' : 'M'}${sx(i)},${sy(p.implied_rate)}`).join('')} fill="none" stroke="rgb(var(--c-bloomberg))" strokeWidth={2} />
            {path.map((p, i) => <g key={p.month}><circle cx={sx(i)} cy={sy(p.implied_rate)} r={2.5} fill="rgb(var(--c-bloomberg))" />
              {i % 2 === 0 && <text x={sx(i)} y={H - 10} fontSize="9" textAnchor="middle" fill="rgb(var(--c-text-tertiary))">{p.month.slice(2)}</text>}</g>)}
          </svg>
        </Panel>
        <div className="text-[10px] text-text-tertiary">{d.method} Source: {d.source}.</div>
      </div>);
  }}</Frame>;
}

// ── AUCT ────────────────────────────────────────────────────────────────────
export function AuctView() {
  const [kind, setKind] = useState('Note');
  return (
    <div className="space-y-3">
      <div className="flex gap-1 text-xs">{['Bill', 'Note', 'Bond', 'TIPS', 'FRN'].map((k) => (
        <button key={k} onClick={() => setKind(k)} className={cn('px-2 py-0.5 border', kind === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{k}s</button>))}</div>
      <Frame<any> url={`/api/v1/mkt/auct?kind=${kind}&limit=40`} label="Loading auction results…">{(d) => (
        <>
          <div className="border border-border overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-[10px] uppercase text-text-tertiary"><th className="text-left px-2 py-1 font-normal">Auction</th><th className="text-left font-normal">Security</th><th className="text-right font-normal">Size $bn</th>
                <th className="text-right font-normal">{kind === 'Bill' ? 'Rate' : 'High yield'}</th><th className="text-right font-normal">Bid/cover</th><th className="text-right font-normal">vs avg</th>
                <th className="text-right font-normal">Indirect</th><th className="text-right font-normal">Direct</th><th className="text-right px-2 font-normal">Dealers</th></tr></thead>
              <tbody>{d.auctions.map((a: any) => (
                <tr key={a.cusip + a.auction_date} className="border-t border-border-subtle">
                  <td className="px-2 py-1 font-mono text-text-secondary">{a.auction_date}</td><td className="text-text-primary">{a.term}{a.reopening ? <span className="text-text-tertiary"> (reopening)</span> : ''}</td>
                  <td className="text-right font-mono">{a.size_bn.toFixed(0)}</td><td className="text-right font-mono">{a.high_yield?.toFixed(3)}%</td>
                  <td className="text-right font-mono">{a.bid_to_cover?.toFixed(2)}</td>
                  <td className={cn('text-right font-mono', (a.btc_vs_avg ?? 0) > 0.05 ? 'text-green' : (a.btc_vs_avg ?? 0) < -0.05 ? 'text-red' : '')}>{a.btc_vs_avg != null ? sgn(a.btc_vs_avg, 2) : ''}</td>
                  <td className="text-right font-mono">{pc(a.indirect, 0)}</td><td className="text-right font-mono">{pc(a.direct, 0)}</td>
                  <td className={cn('text-right px-2 font-mono', (a.dealers ?? 0) > 0.2 ? 'text-red' : '')}>{pc(a.dealers, 0)}</td></tr>))}</tbody>
            </table>
          </div>
          <div className="text-[10px] text-text-tertiary">{d.note} Source: {d.source}.</div>
        </>)}</Frame>
    </div>
  );
}

// ── EIA ─────────────────────────────────────────────────────────────────────
export function EiaView() {
  return <Frame<any> url="/api/v1/mkt/eia" label="Loading EIA weekly reports…">{(d) => (
    <div className="space-y-3">
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        <Panel title={`US petroleum stocks — week to ${d.week} (${d.units})`}>
          <table className="w-full text-xs"><thead><tr className="text-[10px] uppercase text-text-tertiary"><th className="text-left font-normal">Product</th><th className="text-right font-normal">Stocks</th><th className="text-right font-normal">Weekly change</th><th className="text-right font-normal">vs year ago</th></tr></thead>
            <tbody>{d.petroleum.map((p: any) => (
              <tr key={p.item} className="border-t border-border-subtle"><td className="py-1 text-text-primary">{p.item}</td><td className="text-right font-mono">{p.latest?.toFixed(1)}</td>
                <td className={cn('text-right font-mono', (p.change ?? 0) < 0 ? 'text-green' : (p.change ?? 0) > 0 ? 'text-red' : '')} title="A draw (negative) is usually bullish for prices">{sgn(p.change, 2)}</td>
                <td className="text-right font-mono">{sgn(p.vs_year_ago_pct, 1, '%')}</td></tr>))}
              {d.cushing && <tr className="border-t border-border-subtle"><td className="py-1 text-text-primary">Cushing, OK (WTI delivery point)</td><td className="text-right font-mono">{d.cushing.latest?.toFixed(1)}</td>
                <td className={cn('text-right font-mono', d.cushing.change < 0 ? 'text-green' : 'text-red')}>{sgn(d.cushing.change, 2)}</td><td className="text-right font-mono">{d.cushing.year_ago ? sgn((d.cushing.latest / d.cushing.year_ago - 1) * 100, 1, '%') : '—'}</td></tr>}
            </tbody></table>
          <p className="text-[10px] text-text-tertiary mt-2">Green = draw (inventories fell — usually supportive for prices); red = build.</p>
        </Panel>
        <Panel title={`Natural gas in storage — week to ${d.gas_week} (${d.gas_units})`}>
          <table className="w-full text-xs"><thead><tr className="text-[10px] uppercase text-text-tertiary"><th className="text-left font-normal">Region</th><th className="text-right font-normal">Storage</th><th className="text-right font-normal">Injection</th><th className="text-right font-normal">vs 5-yr avg</th><th className="text-right font-normal">vs year ago</th></tr></thead>
            <tbody>{d.gas.map((g: any) => (
              <tr key={g.region} className="border-t border-border-subtle"><td className="py-1 text-text-primary capitalize">{g.region}</td><td className="text-right font-mono">{g.latest?.toLocaleString()}</td>
                <td className="text-right font-mono">{sgn(g.change, 0)}</td><td className="text-right font-mono">{sgn(g.vs_5yr_pct, 1, '%')}</td><td className="text-right font-mono">{sgn(g.vs_year_ago_pct, 1, '%')}</td></tr>))}</tbody></table>
        </Panel>
      </div>
      <div className="text-[10px] text-text-tertiary">Source: {d.source}. Petroleum released Wednesdays 10:30 ET, gas Thursdays 10:30 ET.</div>
    </div>)}</Frame>;
}

// ── WETR ────────────────────────────────────────────────────────────────────
export function WetrView() {
  return <Frame<any> url="/api/v1/mkt/wetr" label="Building degree days vs 10-year normals…">{(d) => {
    const max = Math.max(...d.days.flatMap((x: any) => [x.hdd, x.cdd, x.hdd_normal, x.cdd_normal]), 1);
    const t = d.totals;
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <Stat label="Heating degree days, 16d" value={t.hdd.toFixed(0)} sub={`normal ${t.hdd_normal.toFixed(0)} (${sgn(t.hdd - t.hdd_normal, 0)})`} tone={t.hdd - t.hdd_normal > 8 ? 'up' : undefined} />
          <Stat label="Cooling degree days, 16d" value={t.cdd.toFixed(0)} sub={`normal ${t.cdd_normal.toFixed(0)} (${sgn(t.cdd - t.cdd_normal, 0)})`} tone={t.cdd - t.cdd_normal > 8 ? 'up' : undefined} />
          <div className="md:col-span-2 border border-border bg-surface-1 px-3 py-2 text-xs text-text-primary flex items-center">{d.signal}</div>
        </div>
        <Panel title="Daily degree days vs normal (population-weighted, 12 US metros)">
          <div className="flex items-end gap-1 h-40">{d.days.map((x: any) => (
            <div key={x.date} className="flex-1 flex flex-col justify-end items-center gap-px" title={`${x.date}: HDD ${x.hdd.toFixed(1)} (normal ${x.hdd_normal.toFixed(1)}), CDD ${x.cdd.toFixed(1)} (normal ${x.cdd_normal.toFixed(1)})`}>
              <div className="w-full flex items-end gap-px justify-center h-full">
                <div className="w-1/3 bg-blue/80" style={{ height: `${(x.hdd / max) * 100}%` }} /><div className="w-1/3 bg-red/80" style={{ height: `${(x.cdd / max) * 100}%` }} />
                <div className="w-1/6 bg-text-tertiary/50" style={{ height: `${(Math.max(x.hdd_normal, x.cdd_normal) / max) * 100}%` }} /></div>
              <div className="text-[9px] text-text-tertiary">{x.date.slice(8)}</div></div>))}</div>
          <div className="text-[10px] text-text-tertiary mt-1"><span className="text-blue">■</span> heating · <span className="text-red">■</span> cooling · <span className="text-text-tertiary">■</span> normal</div>
        </Panel>
        <div className="border border-border overflow-x-auto">
          <table className="w-full text-[11px] font-mono"><thead><tr className="text-text-tertiary"><th className="text-left px-2 font-normal">City (°F, daily mean)</th>{d.days.map((x: any) => <th key={x.date} className="font-normal px-1">{x.date.slice(5)}</th>)}</tr></thead>
            <tbody>{d.cities.map((c: any) => (
              <tr key={c.city} className="border-t border-border-subtle"><td className="px-2 text-text-primary font-sans">{c.city}</td>
                {c.temps.map((v: number | null, i: number) => <td key={i} className="text-center px-1" style={v == null ? undefined : { color: v >= 80 ? 'rgb(var(--c-red))' : v <= 45 ? 'rgb(var(--c-blue))' : undefined }}>{v == null ? '' : Math.round(v)}</td>)}</tr>))}</tbody></table>
        </div>
        <div className="text-[10px] text-text-tertiary">{d.method} Source: {d.source}.</div>
      </div>);
  }}</Frame>;
}

// ── INSD ────────────────────────────────────────────────────────────────────
export function InsdView({ symbol }: { symbol: string }) {
  const [onlyMarket, setOnlyMarket] = useState(false);
  return <Frame<any> url={`/api/v1/mkt/insd/${enc(symbol)}?limit=60`} label="Reading Form 4 filings from SEC EDGAR…">{(d) => {
    const rows = (d.transactions as any[]).filter((x) => !onlyMarket || x.code === 'P' || x.code === 'S');
    return (
      <div className="space-y-3">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <Stat label="Open-market buys, 6m" value={`$${fmtBig(d.open_market_buys_6m)}`} sub={`${d.buyers_6m} insiders`} tone={d.open_market_buys_6m > 0 ? 'up' : undefined} />
          <Stat label="Open-market sales, 6m" value={`$${fmtBig(d.open_market_sales_6m)}`} sub={`${d.sellers_6m} insiders`} tone={d.open_market_sales_6m > 0 ? 'down' : undefined} />
          <Stat label="Filings read" value={d.transactions.length} sub="transactions, newest first" />
          <label className="border border-border bg-surface-1 px-3 py-2 text-xs flex items-center gap-2 cursor-pointer"><input type="checkbox" checked={onlyMarket} onChange={(e) => setOnlyMarket(e.target.checked)} />Open-market trades only</label>
        </div>
        <div className="border border-border overflow-x-auto max-h-[520px] overflow-y-auto">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-surface-1"><tr className="text-[10px] uppercase text-text-tertiary"><th className="text-left px-2 py-1 font-normal">Date</th><th className="text-left font-normal">Insider</th><th className="text-left font-normal">Role</th>
              <th className="text-left font-normal">Transaction</th><th className="text-right font-normal">Shares</th><th className="text-right font-normal">Price</th><th className="text-right font-normal">Value</th><th className="text-right font-normal">Owned after</th><th /></tr></thead>
            <tbody>{rows.map((x, i) => (
              <tr key={i} className={cn('border-t border-border-subtle', x.code === 'P' && 'bg-green/10', x.code === 'S' && 'bg-red/5')}>
                <td className="px-2 py-0.5 font-mono text-text-secondary">{x.date}</td><td className="text-text-primary">{x.insider}</td><td className="text-text-tertiary">{x.role}</td>
                <td className={x.code === 'P' ? 'text-green' : x.code === 'S' ? 'text-red' : 'text-text-secondary'}>{x.type}</td>
                <td className="text-right font-mono">{x.shares != null ? x.shares.toLocaleString() : '—'}</td><td className="text-right font-mono">{x.price ? fmtPrice(x.price) : '—'}</td>
                <td className="text-right font-mono">{x.value ? `$${fmtBig(x.value)}` : '—'}</td><td className="text-right font-mono text-text-tertiary">{x.owned_after != null ? fmtBig(x.owned_after) : '—'}</td>
                <td className="px-2"><a href={x.url} target="_blank" rel="noreferrer noopener" className="text-text-tertiary hover:text-bloomberg"><ExternalLink className="w-3 h-3" /></a></td></tr>))}</tbody>
          </table>
        </div>
        <div className="text-[10px] text-text-tertiary">{d.note} Source: {d.source}.</div>
      </div>);
  }}</Frame>;
}

// ── 13F ─────────────────────────────────────────────────────────────────────
export function ThirteenFView({ onOpen }: { onOpen: (s: string) => void }) {
  const [cik, setCik] = useState('0001067983');
  const CHG: Record<string, string> = { new: 'text-green', added: 'text-green', reduced: 'text-red', unchanged: 'text-text-tertiary' };
  return <Frame<any> url={`/api/v1/mkt/13f?cik=${cik}`} label="Reading 13F filings from SEC EDGAR…">{(d) => (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <select value={cik} onChange={(e) => setCik(e.target.value)} className="bg-surface-1 border border-border px-2 py-1 text-text-primary">
          {d.managers.map((m: any) => <option key={m.cik} value={m.cik}>{m.name}</option>)}</select>
        <span className="text-text-tertiary">{d.filer} · quarter to {d.period} · filed {d.filed}{d.previous_period ? ` · vs ${d.previous_period}` : ''}</span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        <Stat label="Reported value" value={`$${fmtBig(d.total_value)}`} sub="US-listed long positions" />
        <Stat label="Positions" value={d.positions} />
        <Stat label="New / added" value={`${d.holdings.filter((h: any) => h.change === 'new').length} / ${d.holdings.filter((h: any) => h.change === 'added').length}`} tone="up" />
        <Stat label="Reduced / sold out" value={`${d.holdings.filter((h: any) => h.change === 'reduced').length} / ${d.sold_out.length}`} tone="down" />
      </div>
      <div className="border border-border overflow-x-auto max-h-[520px] overflow-y-auto">
        <table className="w-full text-xs">
          <thead className="sticky top-0 bg-surface-1"><tr className="text-[10px] uppercase text-text-tertiary"><th className="text-left px-2 py-1 font-normal">#</th><th className="text-left font-normal">Holding</th><th className="text-left font-normal">Ticker</th>
            <th className="text-right font-normal">Value</th><th className="font-normal">Weight</th><th className="text-right font-normal">Shares</th><th className="text-right px-2 font-normal">Change q/q</th></tr></thead>
          <tbody>{d.holdings.map((h: any, i: number) => (
            <tr key={h.cusip + (h.put_call ?? '')} className="border-t border-border-subtle hover:bg-surface-3">
              <td className="px-2 text-text-tertiary">{i + 1}</td><td className="text-text-primary">{h.issuer}{h.put_call ? <span className="text-amber"> ({h.put_call})</span> : ''}</td>
              <td>{h.ticker ? <button onClick={() => onOpen(h.ticker)} className="font-mono text-bloomberg hover:underline">{h.ticker}</button> : <span className="font-mono text-text-tertiary">{h.cusip}</span>}</td>
              <td className="text-right font-mono">${fmtBig(h.value)}</td>
              <td className="px-2 w-36"><div className="h-1.5 bg-surface-3"><div className="h-full bg-bloomberg" style={{ width: `${Math.min(100, h.weight * 100 / Math.max(d.holdings[0].weight, 0.01))}%` }} /></div>
                <div className="text-[10px] text-right font-mono text-text-secondary">{pc(h.weight)}</div></td>
              <td className="text-right font-mono">{fmtBig(h.shares)}</td>
              <td className={cn('text-right px-2', CHG[h.change])}>{h.change === 'new' ? 'NEW' : h.change === 'unchanged' ? '—' : `${h.change} ${sgn((h.shares_change_pct ?? 0) * 100, 0, '%')}`}</td></tr>))}</tbody>
        </table>
      </div>
      {d.sold_out.length > 0 && <div className="text-xs text-red">Sold out: {d.sold_out.map((s: any) => s.issuer).join(', ')}</div>}
      <div className="text-[10px] text-text-tertiary">{d.note} Source: {d.source}.</div>
    </div>)}</Frame>;
}
