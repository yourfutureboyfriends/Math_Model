// Book analytics on the actual holdings: Brinson attribution and tracking error vs the fund's benchmark, liquidity
// (days to liquidate, LVaR cost), FIFO lots, transaction-cost analysis of fills, and trade-idea P&L.
// Data: /api/v1/portfolio/analytics/*, /api/v1/portfolio/lots, /tca, /ideas/performance.

import { useState } from 'react';
import { useApiData } from '@/hooks/useApiData';
import { cn } from '@/lib/utils';

type Tab = 'brinson' | 'te' | 'liquidity' | 'lots' | 'tca' | 'ideas' | 'news';
const TABS: [Tab, string][] = [['brinson', 'Attribution vs benchmark'], ['te', 'Tracking error'], ['liquidity', 'Liquidity'],
  ['lots', 'Lots'], ['tca', 'TCA'], ['ideas', 'Idea P&L'], ['news', 'News by holding']];

const bps = (v: number | null | undefined) => (v == null ? '—' : `${v > 0 ? '+' : ''}${v.toFixed(1)}`);
const pct = (v: number | null | undefined, d = 2) => (v == null ? '—' : `${v > 0 ? '+' : ''}${(v * 100).toFixed(d)}%`);
const tone = (v: number | null | undefined, costPositive = false) =>
  v == null ? 'text-text-tertiary' : (costPositive ? -v : v) > 0 ? 'text-green' : (costPositive ? -v : v) < 0 ? 'text-red' : 'text-text-secondary';
const usd = (v: number | null | undefined) => (v == null ? '—' : `$${Math.round(v).toLocaleString()}`);

function Unavailable({ d }: { d: any }) {
  return <div className="p-3 text-xs text-amber">{d?.reason ?? 'Loading…'}</div>;
}

function Brinson() {
  const { data: d } = useApiData<any>('/api/v1/portfolio/analytics/brinson');
  if (!d?.available) return <Unavailable d={d} />;
  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2 text-xs">
        {[['Portfolio' + (d.currency ? ` (${d.currency})` : ''), pct(d.portfolio_return)], [d.benchmark_label ? `Benchmark: ${d.benchmark}` : d.benchmark ?? 'Benchmark', pct(d.benchmark_return)], ['Active (bps)', bps(d.active_return_bps)],
          ['Tracking error (ex-post)', d.ex_post_tracking_error != null ? `${(d.ex_post_tracking_error * 100).toFixed(1)}%` : '—'],
          ['Information ratio', d.information_ratio ?? '—']].map(([k, v]) => (
          <div key={k as string} className="p-2 bg-surface-2 border border-border-subtle">
            <div className="text-2xs text-text-tertiary uppercase">{k}</div><div className="font-mono">{v}</div>
          </div>))}
      </div>
      <table className="w-full text-xs">
        <thead><tr className="text-2xs text-text-tertiary uppercase border-b border-border-subtle">
          <th className="text-left font-normal py-1">Segment</th><th className="text-right font-normal">Allocation</th>
          <th className="text-right font-normal">Selection</th><th className="text-right font-normal">Interaction</th><th className="text-right font-normal">Total (bps)</th></tr></thead>
        <tbody>
          {d.by_sector.map((r: any) => (
            <tr key={r.sector} className="border-b border-border-subtle last:border-0">
              <td className="py-1 text-text-secondary">{r.sector}</td>
              <td className={cn('text-right font-mono', tone(r.allocation))}>{bps(r.allocation)}</td>
              <td className={cn('text-right font-mono', tone(r.selection))}>{bps(r.selection)}</td>
              <td className={cn('text-right font-mono', tone(r.interaction))}>{bps(r.interaction)}</td>
              <td className={cn('text-right font-mono font-medium', tone(r.total_bps))}>{bps(r.total_bps)}</td>
            </tr>))}
          {d.benchmark_construction_bps != null && (
            <tr className="border-b border-border-subtle">
              <td className="py-1 text-text-secondary" title="The real benchmark's return minus the return of its sector segments (proxies): e.g. the equal-weighted half's within-sector return">Benchmark construction</td>
              <td colSpan={3} className="text-right text-2xs text-text-tertiary">real blend vs its sector proxies</td>
              <td className={cn('text-right font-mono font-medium', tone(d.benchmark_construction_bps))}>{bps(d.benchmark_construction_bps)}</td>
            </tr>)}
          <tr className="border-t border-border font-medium">
            <td className="py-1">Total</td>
            {(['allocation', 'selection', 'interaction'] as const).map((k) => (
              <td key={k} className={cn('text-right font-mono', tone(d.effects_bps[k]))}>{bps(d.effects_bps[k])}</td>))}
            <td className={cn('text-right font-mono', tone(d.active_return_bps))}>{bps(d.active_return_bps)}</td>
          </tr>
        </tbody>
      </table>
      <div className="text-[10px] text-text-tertiary">{d.benchmark_label ? `${d.benchmark_label}, in ${d.currency}. ` : ''}{d.period.start} → {d.period.end} ({d.period.sessions} sessions). {d.method} {d.limitations}</div>
    </div>
  );
}

function TrackingError() {
  const { data: d } = useApiData<any>('/api/v1/portfolio/analytics/tracking-error');
  if (!d?.available) return <Unavailable d={d} />;
  return (
    <div className="space-y-2 text-xs">
      <div className="grid grid-cols-3 gap-2">
        <div className="p-2 bg-surface-2 border border-border-subtle"><div className="text-2xs text-text-tertiary uppercase">Ex-ante TE vs {d.benchmark}</div><div className="font-mono text-lg">{(d.ex_ante_tracking_error * 100).toFixed(1)}%</div></div>
        <div className="p-2 bg-surface-2 border border-border-subtle"><div className="text-2xs text-text-tertiary uppercase">Beta</div><div className="font-mono text-lg">{d.portfolio_beta}</div></div>
        <div className="p-2 bg-surface-2 border border-border-subtle"><div className="text-2xs text-text-tertiary uppercase">Net invested</div><div className="font-mono text-lg">{(d.invested_net * 100).toFixed(1)}%</div></div>
      </div>
      <table className="w-full"><thead><tr className="text-2xs text-text-tertiary uppercase border-b border-border-subtle"><th className="text-left font-normal py-1">Holding</th><th className="text-right font-normal">Active weight</th><th className="text-right font-normal">Share of TE</th></tr></thead>
        <tbody>{Object.entries(d.active_weights).map(([s, w]: any) => (
          <tr key={s} className="border-b border-border-subtle last:border-0"><td className="py-1 font-mono">{s}</td>
            <td className="text-right font-mono">{pct(w)}</td><td className="text-right font-mono">{d.te_contribution[s] != null ? `${(d.te_contribution[s] * 100).toFixed(1)}%` : '—'}</td></tr>))}</tbody></table>
      <div className="text-[10px] text-text-tertiary">As of {d.as_of}; 1-year daily covariance. {d.note}</div>
    </div>
  );
}

function Liquidity() {
  const { data: d } = useApiData<any>('/api/v1/portfolio/analytics/liquidity');
  const { data: v } = useApiData<any>('/api/v1/risk/var');
  if (!d?.available) return <Unavailable d={d} />;
  const var95 = v?.var?.['95']?.historical?.['1d'] ?? null;   // historical 95% 1-day VaR, $
  return (
    <div className="space-y-2 text-xs">
      <div className="grid grid-cols-3 gap-2">
        <div className="p-2 bg-surface-2 border border-border-subtle"><div className="text-2xs text-text-tertiary uppercase">Liquidity cost (½ spread)</div><div className="font-mono text-lg">{usd(d.liquidity_cost_total)}</div></div>
        <div className="p-2 bg-surface-2 border border-border-subtle"><div className="text-2xs text-text-tertiary uppercase">LVaR 95% 1d (historical + cost)</div><div className="font-mono text-lg">{typeof var95 === 'number' ? usd(Math.abs(var95) + d.liquidity_cost_total) : '—'}</div></div>
        <div className="p-2 bg-surface-2 border border-border-subtle"><div className="text-2xs text-text-tertiary uppercase">Longest exit</div><div className="font-mono text-lg">{d.max_days_to_liquidate < 0.01 ? '< 0.01 days' : `${d.max_days_to_liquidate.toFixed(2)} days`}</div></div>
      </div>
      <table className="w-full"><thead><tr className="text-2xs text-text-tertiary uppercase border-b border-border-subtle">
        <th className="text-left font-normal py-1">Position</th><th className="text-right font-normal">Value</th><th className="text-right font-normal">% of ADV</th>
        <th className="text-right font-normal">Days to exit</th><th className="text-right font-normal">Spread (bps)</th><th className="text-right font-normal">Cost</th></tr></thead>
        <tbody>{d.positions.map((p: any) => (
          <tr key={`${p.symbol}-${p.book}`} className="border-b border-border-subtle last:border-0"><td className="py-1 font-mono">{p.symbol}</td>
            <td className="text-right font-mono">{usd(p.market_value)}</td><td className="text-right font-mono">{p.pct_of_adv != null ? `${p.pct_of_adv}%` : '—'}</td>
            <td className="text-right font-mono">{p.days_to_liquidate == null ? '—' : p.days_to_liquidate < 0.01 ? '< 0.01' : p.days_to_liquidate.toFixed(2)}</td>
            <td className="text-right font-mono">{p.spread_bps ?? '—'}</td><td className="text-right font-mono">{usd(p.liquidity_cost)}</td></tr>))}</tbody></table>
      <div className="text-[10px] text-text-tertiary">{d.method}</div>
    </div>
  );
}

function Lots() {
  const { data: d } = useApiData<any>('/api/v1/portfolio/lots');
  if (!d?.available) return <Unavailable d={d} />;
  return (
    <div className="space-y-2 text-xs">
      <table className="w-full"><thead><tr className="text-2xs text-text-tertiary uppercase border-b border-border-subtle">
        <th className="text-left font-normal py-1">Symbol</th><th className="text-left font-normal">Opened</th><th className="text-right font-normal">Quantity</th>
        <th className="text-right font-normal">Cost</th><th className="text-right font-normal">Days held</th><th className="text-left font-normal pl-3">Term</th><th className="text-left font-normal">Source</th></tr></thead>
        <tbody>{Object.entries(d.lots).flatMap(([s, ls]: any) => ls.map((l: any, i: number) => (
          <tr key={`${s}-${i}`} className="border-b border-border-subtle last:border-0"><td className="py-1 font-mono">{s}</td><td>{l.date}</td>
            <td className="text-right font-mono">{l.quantity}</td><td className="text-right font-mono">{l.price}</td>
            <td className="text-right font-mono">{l.holding_days ?? '—'}</td><td className="pl-3">{l.term ?? '—'}</td><td className="text-text-tertiary">{l.source}</td></tr>)))}</tbody></table>
      <div className="text-[10px] text-text-tertiary">{d.method}</div>
    </div>
  );
}

function Tca() {
  const { data: d } = useApiData<any>('/api/v1/portfolio/tca');
  if (!d?.available) return <Unavailable d={d} />;
  return (
    <div className="space-y-2 text-xs">
      <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
        {Object.entries(d.by_book).map(([b, s]: any) => (
          <div key={b} className="p-2 bg-surface-2 border border-border-subtle">
            <div className="text-2xs text-text-tertiary uppercase">{b} · {s.fills} fills</div>
            <div className={cn('font-mono', tone(s.median_vs_arrival_bps, true))}>median {bps(s.median_vs_arrival_bps)} bps vs arrival</div>
            <div className="text-2xs text-text-tertiary">shortfall {usd(s.shortfall_usd)}</div>
          </div>))}
      </div>
      <div className="max-h-72 overflow-y-auto">
        <table className="w-full"><thead className="sticky top-0 bg-surface-1"><tr className="text-2xs text-text-tertiary uppercase border-b border-border-subtle">
          <th className="text-left font-normal py-1">Fill</th><th className="text-left font-normal">Book</th><th className="text-left font-normal">Symbol</th>
          <th className="text-right font-normal">Price</th><th className="text-right font-normal">vs arrival</th><th className="text-right font-normal">vs VWAP proxy</th>
          <th className="text-right font-normal">vs close</th><th className="text-right font-normal">Shortfall $</th></tr></thead>
          <tbody>{d.fills.map((f: any, i: number) => (
            <tr key={i} className="border-b border-border-subtle last:border-0"><td className="py-1">{f.fill_date}</td><td className="text-text-tertiary">{f.book}</td>
              <td className="font-mono">{f.side === 'SELL' ? '−' : ''}{f.symbol}</td><td className="text-right font-mono">{Number(f.fill_price).toFixed(2)} {f.currency}</td>
              <td className={cn('text-right font-mono', tone(f.vs_arrival_bps, true))}>{bps(f.vs_arrival_bps)}</td>
              <td className={cn('text-right font-mono', tone(f.vs_vwap_proxy_bps, true))}>{bps(f.vs_vwap_proxy_bps)}</td>
              <td className={cn('text-right font-mono', tone(f.vs_close_bps, true))}>{bps(f.vs_close_bps)}</td>
              <td className="text-right font-mono">{usd(f.shortfall_usd)}</td></tr>))}</tbody></table>
      </div>
      <div className="text-[10px] text-text-tertiary">{d.method}</div>
    </div>
  );
}

function Ideas() {
  const { data: d } = useApiData<any>('/api/v1/portfolio/ideas/performance');
  if (!d?.available) return <Unavailable d={d} />;
  return (
    <div className="space-y-2 text-xs">
      <div className="text-text-secondary">{d.summary.ideas} ideas · {d.summary.with_prices} priced · hit rate {d.summary.hit_rate != null ? `${Math.round(d.summary.hit_rate * 100)}%` : '—'} · average {pct(d.summary.average_return, 1)}</div>
      <table className="w-full"><thead><tr className="text-2xs text-text-tertiary uppercase border-b border-border-subtle">
        <th className="text-left font-normal py-1">Idea</th><th className="text-left font-normal">Proposed</th><th className="text-right font-normal">Entry</th>
        <th className="text-right font-normal">Return</th><th className="text-left font-normal pl-3">Outcome</th><th className="text-right font-normal">Best / worst</th></tr></thead>
        <tbody>{d.ideas.map((i: any) => (
          <tr key={`${i.source}-${i.id}`} className="border-b border-border-subtle last:border-0" title={i.entry_adjusted ? `Stated entry ${i.entry} was ${i.entry_vs_market_pct}% from the market that day — measured from the close instead` : undefined}>
            <td className="py-1"><span className="font-mono">{i.direction === 'SHORT' ? '−' : ''}{i.symbol}</span> <span className="text-text-tertiary">{i.source}</span></td>
            <td>{i.created}</td>
            <td className="text-right font-mono">{i.entry_used ?? '—'}{i.entry_adjusted && <span className="text-amber">*</span>}</td>
            <td className={cn('text-right font-mono', tone(i.return))}>{pct(i.return, 1)}</td>
            <td className="pl-3">{i.status}{i.closed_on ? ` ${i.closed_on}` : ''}</td>
            <td className="text-right font-mono text-text-tertiary">{pct(i.max_favourable, 1)} / {pct(i.max_adverse, 1)}</td></tr>))}</tbody></table>
      <div className="text-[10px] text-text-tertiary">{d.method}</div>
    </div>
  );
}

function HoldingNews() {
  const { data: d } = useApiData<any>('/api/v1/portfolio/news');
  if (!d?.available) return <Unavailable d={d} />;
  return (
    <div className="space-y-3 text-xs">
      {Object.entries(d.holdings).map(([s, v]: any) => (
        <div key={s}>
          <div className="flex items-center gap-2 mb-0.5">
            <span className="font-mono text-text-primary">{v.side === 'short' ? '−' : ''}{s}</span>
            {v.topic && <span className="text-2xs text-text-tertiary">news on “{v.topic}”</span>}
            {v.average_tone != null && <span className={cn('text-2xs font-mono', tone(v.average_tone))}>tone {v.average_tone > 0 ? '+' : ''}{v.average_tone}</span>}
            {v.against_position && <span className="text-2xs text-amber">against the position</span>}
          </div>
          {v.headlines.length === 0 ? <div className="text-text-tertiary">No recent headlines.</div> : v.headlines.map((h: any, i: number) => (
            <div key={i} className="flex gap-2">
              <span className={cn('font-mono w-10 shrink-0 text-right', tone(h.tone))}>{h.tone > 0 ? '+' : ''}{h.tone}</span>
              {h.url ? <a href={h.url} target="_blank" rel="noopener noreferrer" className="text-text-secondary hover:text-bloomberg truncate">{h.title}</a>
                : <span className="text-text-secondary truncate">{h.title}</span>}
              <span className="text-text-tertiary shrink-0">{h.publisher} {String(h.time ?? '').slice(0, 10)}</span>
            </div>))}
          {v.filings?.length > 0 && <div className="text-2xs text-text-tertiary mt-0.5">SEC: {v.filings.map((f: any) => `${f.form ?? f.type ?? ''} ${f.date ?? f.filed ?? ''}`).join(' · ')}</div>}
        </div>))}
      <div className="text-[10px] text-text-tertiary">{d.method}</div>
    </div>
  );
}

export function PortfolioAnalyticsSection() {
  const [tab, setTab] = useState<Tab>('brinson');
  return (
    <div id="book-analytics" className="terminal-section">
      <div className="section-header mb-2">
        <div className="section-header-left">
          <span className="section-tag">◆</span>
          <h2 className="section-title">Book analytics</h2>
          <span className="section-meta">actual holdings · vs S&amp;P 500</span>
        </div>
      </div>
      <div className="flex flex-wrap gap-1 mb-2">
        {TABS.map(([k, l]) => (
          <button key={k} onClick={() => setTab(k)}
            className={cn('px-2 py-0.5 text-2xs border', tab === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-tertiary hover:text-text-secondary')}>{l}</button>))}
      </div>
      <div className="border border-border bg-surface-1 p-2">
        {tab === 'brinson' && <Brinson />}
        {tab === 'te' && <TrackingError />}
        {tab === 'liquidity' && <Liquidity />}
        {tab === 'lots' && <Lots />}
        {tab === 'tca' && <Tca />}
        {tab === 'ideas' && <Ideas />}
        {tab === 'news' && <HoldingNews />}
      </div>
    </div>
  );
}
