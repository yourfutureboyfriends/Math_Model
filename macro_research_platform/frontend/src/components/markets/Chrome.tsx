// Classic terminal chrome for the Markets mode: yellow market-sector keys, amber function
// keys, the function title bar, numbered function menus and the scrolling news crawl.
import { useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { setMarketsSkin, useMarketsSkin } from '@/lib/theme';
import { FUNCTIONS, type MktFunction } from './functions';
import { useJSON } from './shared';

const SECTOR_KEYS: [string, string, string][] = [
  ['GOVT', 'GC', 'Government bonds: yield curves'], ['CORP', 'BTMM', 'Credit spreads & money markets'], ['M-MKT', 'BTMM', 'Money markets'],
  ['EQUITY', 'MOST', 'Equities: most active, gainers, losers'], ['INDEX', 'WEI', 'World equity indices'], ['CURNCY', 'WCRS', 'Currencies: cross rates'],
  ['CMDTY', 'CMDTY', 'Commodities & futures curves'],
];
const FN_KEYS: [string, string, string][] = [['MENU', 'WEI', 'Back to the launchpad'], ['NEWS', 'N', 'Top news'], ['MON', 'W', 'Your monitors / watchlists'],
  ['ALRT', 'ALRT', 'Alerts'], ['AI', 'AI', 'AI research assistant']];

export function KeyBar({ onGo, onHelp }: { onGo: (fn: string) => void; onHelp: () => void }) {
  const skin = useMarketsSkin();
  return (
    <div className="flex flex-wrap items-center gap-1 text-[11px]">
      {SECTOR_KEYS.map(([k, fn, title]) => (
        <button key={k} onClick={() => onGo(fn)} title={title} className="key-yellow px-2 py-0.5 leading-5">{k}</button>))}
      <span className="w-2" />
      {FN_KEYS.map(([k, fn, title]) => (
        <button key={k} onClick={() => onGo(fn)} title={title} className="key-amber px-2 py-0.5 leading-5">{k}</button>))}
      <button onClick={onHelp} title="How to use the terminal" className="px-2 py-0.5 leading-5 bg-green text-black font-bold">HELP</button>
      <span className="ml-auto inline-flex items-center gap-1 text-text-tertiary">
        Style
        {(['classic', 'modern'] as const).map((s) => (
          <button key={s} onClick={() => setMarketsSkin(s)} className={cn('px-1.5 py-0.5 border', skin === s ? 'border-bloomberg text-bloomberg' : 'border-border hover:text-text-primary')}>{s}</button>))}
      </span>
    </div>
  );
}

export function TitleBar({ code, title, security, right }: { code: string; title: string; security?: string; right?: React.ReactNode }) {
  return (
    <div className="panel-bar flex flex-wrap items-center gap-x-3 gap-y-1 px-2 py-1 border-y border-border text-[12px] uppercase tracking-wide">
      {security && <span className="key-yellow px-1.5 normal-case">{security}</span>}
      <span className="key-amber px-1.5">{code}</span>
      <span className="text-text-primary">{title}</span>
      <span className="ml-auto text-text-tertiary normal-case tracking-normal">{right}</span>
    </div>
  );
}

/** Numbered menu of functions, like a terminal menu page. Selecting a number opens it. */
export function FunctionMenu({ items, active, onPick, columns = 'auto' }: { items: MktFunction[]; active?: string; onPick: (f: MktFunction) => void; columns?: 'auto' | 'one' }) {
  return (
    <nav aria-label="Functions" className={cn('grid gap-x-6 gap-y-0.5 text-[12px]', columns === 'one' ? 'grid-cols-1' : 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7')}>
      {items.map((f, i) => (
        <button key={f.code} onClick={() => onPick(f)} title={f.desc}
          className={cn('text-left whitespace-nowrap px-1 hover:bg-surface-3', f.code === active && 'bg-[rgb(251,139,30)] text-black')}>
          <span className={cn('inline-block w-6 text-right mr-1', f.code === active ? 'text-black' : 'text-bloomberg')}>{i + 1})</span>
          <span className={cn('inline-block w-12 font-semibold', f.code === active ? 'text-black' : 'text-text-primary')}>{f.code}</span>
          <span className={f.code === active ? 'text-black' : 'text-text-secondary'}>{f.name}</span>
        </button>))}
    </nav>
  );
}

export function NewsCrawl() {
  const { data } = useJSON<any>('/api/v1/mkt/news?limit=40', 600_000);
  const text: any[] = useMemo(() => (data?.items ?? []).slice(0, 30), [data]);
  if (!text.length) return null;
  const row = (k: string) => (
    <span key={k} className="inline-flex gap-10 pr-10">
      {text.map((n: any, i: number) => (
        <a key={i} href={n.url} target="_blank" rel="noreferrer noopener" className="whitespace-nowrap hover:underline">
          <span className="text-bloomberg">{n.time ? new Date(n.time).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' }) : ''}</span>{' '}
          <span className="text-text-primary">{n.title}</span> <span className="text-text-tertiary">[{n.source}]</span>
        </a>))}
    </span>);
  return (
    <div className="fixed bottom-0 left-0 right-0 z-30 h-6 bg-surface-1 border-t border-border overflow-hidden text-[11px] leading-6 font-mono" aria-label="Top news crawl">
      <div className="news-crawl inline-flex">{row('a')}{row('b')}</div>
    </div>
  );
}

export function HelpPanel({ onClose }: { onClose: () => void }) {
  return (
    <div className="border border-border bg-surface-1 p-3 text-[12px] space-y-2">
      <div className="flex justify-between"><span className="text-bloomberg font-semibold">HELP — USING THE TERMINAL</span><button onClick={onClose} className="text-text-tertiary hover:text-text-primary">[X] close</button></div>
      <p className="text-text-primary">Type a security, then a function, then press <span className="key-yellow px-1">&lt;GO&gt;</span> (Enter):</p>
      <ul className="text-text-secondary space-y-0.5">
        <li><span className="text-text-primary">AAPL US Equity DES</span> — description · <span className="text-text-primary">VOD LN Equity GP</span> — price graph · <span className="text-text-primary">7203 JP Equity FA</span> — financials</li>
        <li><span className="text-text-primary">SPX Index GP</span> · <span className="text-text-primary">EURUSD Curncy GP</span> · <span className="text-text-primary">CL1 Comdty</span> · <span className="text-text-primary">USGG10YR Index</span> · <span className="text-text-primary">XBTUSD Curncy</span></li>
        <li>Plain tickers and names work too: <span className="text-text-primary">NVDA OMON</span>, <span className="text-text-primary">toyota</span>, <span className="text-text-primary">gold</span>.</li>
        <li>On a security page, type a <span className="text-text-primary">menu number</span> (e.g. <span className="text-text-primary">8</span>) and &lt;GO&gt; to open that function. <span className="text-text-primary">/</span> focuses the command line.</li>
        <li>Yellow keys open market sectors; amber keys: MENU (launchpad), NEWS, MON (monitors), ALRT, AI.</li>
      </ul>
      <p className="text-text-tertiary">All functions: {FUNCTIONS.map((f) => f.code).join(' · ')}</p>
    </div>
  );
}

export function useHelp() {
  const [open, setOpen] = useState(false);
  return { open, toggle: () => setOpen((o) => !o), close: () => setOpen(false) };
}
