// Terminal launchpad: a dense multi-panel monitor — world indices, rates, FX, commodities,
// crypto, most active / gainers / losers and top news — every row opens its security.
import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { toTerminal } from './bbg';
import { Chg, Flash, fmtPrice, Spark, useJSON } from './shared';
import { MarketClock } from './MarketClock';

function Pane({ title, code, onCode, children, className, style }: { title: string; code?: string; onCode?: () => void; children: React.ReactNode; className?: string; style?: React.CSSProperties }) {
  return (
    <section className={cn('bg-surface-1 border border-border min-w-0 flex flex-col', className)} style={style}>
      <header className="panel-bar flex items-center px-2 h-6 text-[11px] uppercase tracking-wide">
        <span className="text-bloomberg font-semibold">{title}</span>
        {code && <button onClick={onCode} title={`Open ${code}`} className="ml-auto text-text-tertiary hover:text-bloomberg">{code} &lt;GO&gt;</button>}
      </header>
      <div className="flex-1 min-h-0 overflow-auto">{children}</div>
    </section>
  );
}

const th = 'px-1.5 font-normal text-text-tertiary';
const td = 'px-1.5 py-[1px] whitespace-nowrap';

function Bp({ v }: { v?: number | null }) {
  return <span className={cn('font-mono', v == null ? 'text-text-tertiary' : v > 0 ? 'text-red' : v < 0 ? 'text-green' : 'text-text-secondary')}>{v == null ? '—' : `${v >= 0 ? '+' : ''}${v.toFixed(1)}`}</span>;
}

function GroupTable({ g, onOpen }: { g: any; onOpen: (s: string) => void }) {
  const fx = g.group === 'Currencies';
  const allYield = g.rows.length > 0 && g.rows.every((r: any) => r.is_yield);     // rates pane also holds VIX / MOVE
  return (
    <table className="w-full text-[11px] leading-[18px]">
      <thead><tr><th className={cn(th, 'text-left')}>Security</th><th className={cn(th, 'text-right')}>{allYield ? 'Yield' : 'Last'}</th>
        <th className={cn(th, 'text-right')} title={g.is_yield ? 'Yields: change in bp · others: % change' : undefined}>{allYield ? 'Chg bp' : g.is_yield ? 'Chg' : '%Chg'}</th><th className={cn(th, 'text-right hidden sm:table-cell')}>YTD</th><th className={cn(th, 'hidden md:table-cell')} /></tr></thead>
      <tbody>{g.rows.map((r: any) => (
        <tr key={r.symbol} onClick={() => onOpen(r.symbol)} className="cursor-pointer hover:bg-surface-3 odd:bg-surface-2/40" title={`${r.name} — ${r.symbol}`}>
          <td className={cn(td, 'text-text-primary max-w-[11rem] truncate')}>{r.name}<span className="ml-1 text-text-tertiary">{toTerminal(r.symbol)}</span></td>
          <td className={cn(td, 'text-right font-mono text-text-primary')}><Flash value={r.price}>{r.price == null ? '—' : r.is_yield ? `${r.price.toFixed(3)}%` : fmtPrice(r.price, fx ? 'FX' : undefined)}</Flash></td>
          <td className={cn(td, 'text-right')}>{r.is_yield ? <Bp v={r.change_1d_bp} /> : <Chg v={r.change_1d} />}</td>
          <td className={cn(td, 'text-right hidden sm:table-cell')}>{r.is_yield ? <Bp v={r.change_ytd_bp} /> : <Chg v={r.change_ytd} d={1} />}</td>
          <td className={cn(td, 'hidden md:table-cell w-16')}><Spark values={r.spark} /></td>
        </tr>))}</tbody>
    </table>
  );
}

function Movers({ kind, onOpen }: { kind: 'active' | 'gainers' | 'losers'; onOpen: (s: string) => void }) {
  const { data } = useJSON<any>(`/api/v1/mkt/movers?region=us&kind=${kind}&count=12`, 300_000);
  if (!data) return <div className="p-2 text-[11px] text-text-tertiary">Loading…</div>;
  return (
    <table className="w-full text-[11px] leading-[18px]">
      <thead><tr><th className={cn(th, 'text-left')}>Ticker</th><th className={cn(th, 'text-right')}>Last</th><th className={cn(th, 'text-right')}>%Chg</th>
        <th className={cn(th, 'text-right')}>{kind === 'active' ? 'Volume' : 'Mkt cap'}</th></tr></thead>
      <tbody>{(data.rows ?? []).map((r: any) => (
        <tr key={r.symbol} onClick={() => onOpen(r.symbol)} className="cursor-pointer hover:bg-surface-3 odd:bg-surface-2/40" title={r.name}>
          <td className={cn(td, 'text-text-primary')}>{toTerminal(r.symbol)}</td>
          <td className={cn(td, 'text-right font-mono text-text-primary')}><Flash value={r.price}>{fmtPrice(r.price)}</Flash></td>
          <td className={cn(td, 'text-right')}><Chg v={r.change_pct} /></td>
          <td className={cn(td, 'text-right font-mono text-text-secondary')}>{kind === 'active' ? compact(r.volume) : compact(r.market_cap)}</td>
        </tr>))}</tbody>
    </table>
  );
}

function compact(v?: number | null) {
  if (v == null) return '—';
  const a = Math.abs(v);
  return a >= 1e12 ? `${(v / 1e12).toFixed(2)}T` : a >= 1e9 ? `${(v / 1e9).toFixed(1)}B` : a >= 1e6 ? `${(v / 1e6).toFixed(1)}M` : a >= 1e3 ? `${(v / 1e3).toFixed(0)}K` : String(v);
}

function TopNews() {
  const { data } = useJSON<any>('/api/v1/mkt/news?limit=25', 600_000);
  if (!data) return <div className="p-2 text-[11px] text-text-tertiary">Loading…</div>;
  return (
    <ol className="text-[11px] leading-[18px]">
      {(data.items ?? []).slice(0, 25).map((n: any, i: number) => (
        <li key={i} className="flex gap-1.5 px-1.5 odd:bg-surface-2/40 hover:bg-surface-3">
          <span className="text-bloomberg w-5 text-right shrink-0">{i + 1})</span>
          <a href={n.url} target="_blank" rel="noreferrer noopener" className="flex-1 min-w-0 truncate text-text-primary hover:underline" title={n.summary || n.title}>{n.title}</a>
          <span className="text-text-tertiary shrink-0">{n.source}</span>
          <span className="text-text-tertiary shrink-0 w-10 text-right">{n.time ? new Date(n.time).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : ''}</span>
        </li>))}
    </ol>
  );
}

/** Columns that follow the container's own width (so the monitor also fits a launchpad window). */
function useColumns(): [React.RefObject<HTMLDivElement>, number] {
  const ref = useRef<HTMLDivElement>(null);
  const [cols, setCols] = useState(3);
  useEffect(() => {
    const el = ref.current; if (!el) return;
    const ro = new ResizeObserver(([e]) => { const w = e.contentRect.width; setCols(w >= 1250 ? 3 : w >= 640 ? 2 : 1); });
    ro.observe(el); return () => ro.disconnect();
  }, []);
  return [ref, cols];
}

export function MonitorHome({ onOpen, onGo }: { onOpen: (s: string) => void; onGo: (fn: string) => void }) {
  const [box, cols] = useColumns();
  const { data, error } = useJSON<any>('/api/v1/mkt/overview', 120_000);
  const groups: any[] = data?.groups ?? [];
  const pick = (re: RegExp) => groups.find((g) => re.test(g.group));
  const panes: [RegExp, string, string][] = [[/equit|indic/i, 'World equity indices', 'WEI'], [/rate|yield|vol/i, 'Rates & volatility', 'GC'],
    [/curr/i, 'Currencies', 'WCRS'], [/commod/i, 'Commodities', 'CMDTY'], [/crypto/i, 'Crypto', 'CRYPTO']];
  return (
    <div className="space-y-2">
      {error && !data && <div className="text-[11px] text-red">World markets unavailable: {error}</div>}
      <div ref={box} className="grid gap-2" style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}>
        {panes.map(([re, title, code]) => { const g = pick(re); return (
          <Pane key={title} title={title} code={code} onCode={() => onGo(code)} className={code === 'WEI' && cols > 1 ? 'row-span-2' : ''}>
            {g ? <GroupTable g={g} onOpen={onOpen} /> : <div className="p-2 text-[11px] text-text-tertiary">{data ? 'No data' : 'Loading…'}</div>}
          </Pane>); })}
        <Pane title="Market hours" className="max-h-[420px]"><MarketClock /></Pane>
        <Pane title="Most active · US" code="MOST" onCode={() => onGo('MOST')}><Movers kind="active" onOpen={onOpen} /></Pane>
        <Pane title="Top gainers · US" code="MOST" onCode={() => onGo('MOST')}><Movers kind="gainers" onOpen={onOpen} /></Pane>
        <Pane title="Top losers · US" code="MOST" onCode={() => onGo('MOST')}><Movers kind="losers" onOpen={onOpen} /></Pane>
        <Pane title="Top news" code="N" onCode={() => onGo('N')} className="max-h-[480px]" style={{ gridColumn: `span ${cols}` }}><TopNews /></Pane>
      </div>
      <div className="text-[10px] text-text-tertiary">{data?.source ?? ''} · exchange delays apply · yields in %, changes in bp · refreshes every 2 min</div>
    </div>
  );
}
