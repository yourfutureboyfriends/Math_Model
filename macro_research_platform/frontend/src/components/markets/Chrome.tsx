// Classic terminal chrome for the Markets mode: yellow market-sector keys, amber function
// keys, the function title bar, numbered function menus and the scrolling news crawl.
import { useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { setMarketsSkin, setUpDown, useMarketsSkin, useUpDown } from '@/lib/theme';
import { FUNCTIONS, findFunction, type MktFunction } from './functions';
import { toTerminal } from './bbg';
import { useJSON } from './shared';

const SECTOR_KEYS: [string, string, string][] = [
  ['GOVT', 'GC', 'Government bonds: yield curves'], ['CORP', 'BTMM', 'Credit spreads & money markets'], ['M-MKT', 'BTMM', 'Money markets'],
  ['EQUITY', 'MOST', 'Equities: most active, gainers, losers'], ['INDEX', 'WEI', 'World equity indices'], ['CURNCY', 'WCRS', 'Currencies: cross rates'],
  ['CMDTY', 'CMDTY', 'Commodities & futures curves'],
];
const FN_KEYS: [string, string, string][] = [['MENU', 'BACK', 'Back to the previous screen'], ['HOME', 'WEI', 'Launchpad: world markets monitor'], ['NEWS', 'N', 'Top news'], ['MON', 'W', 'Your monitors / watchlists'],
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
        <UpDownToggle />
        <span className="w-2" />
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

/** Up colour: green (US/Europe) or red (Hong Kong, China, Japan, Korea — Futubull's default there). */
export function UpDownToggle() {
  const u = useUpDown();
  return (
    <span className="inline-flex items-center gap-1" title="Colour for rising prices">
      Up
      {(['green', 'red'] as const).map((c) => (
        <button key={c} onClick={() => setUpDown(c)} aria-pressed={u === c}
          className={cn('px-1.5 py-0.5 border', u === c ? 'border-bloomberg' : 'border-border hover:text-text-primary')}>
          <span style={{ color: c === 'green' ? '#22c55e' : '#ef4444' }}>▲</span></button>))}
    </span>
  );
}

// ── Workspace tabs: several screens open at once, each keeping its own security & function ──
type WsTab = { id: string; hash: string };
const TABS_KEY = 'mkt_tabs';
const MAX_TABS = 9;

function tabLabel(hash: string): { code: string; sec?: string } {
  const parts = hash.replace(/^#mkt\/?/, '').split('/').filter(Boolean);
  const f = findFunction(parts[0] ?? 'WEI');
  const sym = parts[1] ? decodeURIComponent(parts[1]).toUpperCase() : undefined;
  return { code: f?.code ?? 'WEI', sec: sym && f?.security ? toTerminal(sym).replace(/ (Equity|Index|Curncy|Comdty)$/, '') : sym };
}

export function WorkspaceTabs() {
  const load = (): { tabs: WsTab[]; active: string } => {
    const cur = window.location.hash.startsWith('#mkt') ? window.location.hash : '#mkt/wei';
    try {
      const j = JSON.parse(localStorage.getItem(TABS_KEY) || '');
      if (Array.isArray(j.tabs) && j.tabs.length) {
        const active = j.tabs.some((t: WsTab) => t.id === j.active) ? j.active : j.tabs[0].id;
        return { tabs: j.tabs.map((t: WsTab) => (t.id === active ? { ...t, hash: cur } : t)), active };
      }
    } catch { /* first run or storage unavailable */ }
    return { tabs: [{ id: 't1', hash: cur }], active: 't1' };
  };
  const [st, setSt] = useState(load);
  const ref = useRef(st);
  ref.current = st;
  useEffect(() => { try { localStorage.setItem(TABS_KEY, JSON.stringify(st)); } catch { /* storage unavailable */ } }, [st]);
  useEffect(() => {
    const h = () => {
      if (!window.location.hash.startsWith('#mkt')) return;
      setSt((s) => ({ ...s, tabs: s.tabs.map((t) => (t.id === s.active ? { ...t, hash: window.location.hash } : t)) }));
    };
    window.addEventListener('hashchange', h);
    return () => window.removeEventListener('hashchange', h);
  }, []);
  const activate = (id: string) => {
    const t = ref.current.tabs.find((x) => x.id === id);
    if (!t) return;
    setSt((s) => ({ ...s, active: id }));
    if (window.location.hash !== t.hash) window.location.hash = t.hash;
  };
  const add = () => {
    if (ref.current.tabs.length >= MAX_TABS) return;
    const id = `t${Date.now()}`;
    setSt((s) => ({ tabs: [...s.tabs, { id, hash: '#mkt/wei' }], active: id }));
    window.location.hash = '#mkt/wei';
  };
  const close = (id: string) => {
    const s = ref.current;
    if (s.tabs.length <= 1) return;
    const i = s.tabs.findIndex((t) => t.id === id);
    const tabs = s.tabs.filter((t) => t.id !== id);
    if (id === s.active) {
      const next = tabs[Math.max(0, i - 1)];
      setSt({ tabs, active: next.id });
      window.location.hash = next.hash;
    } else setSt({ ...s, tabs });
  };
  // Alt+1…9 switch tabs, Alt+T new tab, Alt+W close tab (Option on a Mac)
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      if (!e.altKey || e.metaKey || e.ctrlKey) return;
      const m = /^Digit([1-9])$/.exec(e.code);
      if (m) { const t = ref.current.tabs[Number(m[1]) - 1]; if (t) { e.preventDefault(); activate(t.id); } }
      else if (e.code === 'KeyT') { e.preventDefault(); add(); }
      else if (e.code === 'KeyW') { e.preventDefault(); close(ref.current.active); }
    };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, []);
  return (
    <div role="tablist" aria-label="Workspace tabs" className="flex items-end gap-px overflow-x-auto text-[11px] border-b border-border">
      {st.tabs.map((t, i) => {
        const { code, sec } = tabLabel(t.hash);
        const on = t.id === st.active;
        return (
          <div key={t.id} role="tab" aria-selected={on} title={`Alt+${i + 1}`}
            className={cn('group flex items-center gap-1.5 pl-2 pr-1 py-1 border border-b-0 cursor-pointer whitespace-nowrap',
              on ? 'bg-surface-1 border-border text-text-primary' : 'bg-surface-2/60 border-transparent text-text-tertiary hover:text-text-primary')}
            onClick={() => activate(t.id)} onAuxClick={(e) => { if (e.button === 1) close(t.id); }}>
            <span className="text-text-tertiary">{i + 1}</span>
            {sec && <span className={on ? 'text-[rgb(var(--key-yellow,255_214_0))]' : ''}>{sec}</span>}
            <span className={cn('font-mono font-semibold', on && 'text-bloomberg')}>{code}</span>
            {st.tabs.length > 1 && <button onClick={(e) => { e.stopPropagation(); close(t.id); }} aria-label="Close tab"
              className="px-0.5 text-text-tertiary opacity-0 group-hover:opacity-100 hover:text-red">×</button>}
          </div>);
      })}
      {st.tabs.length < MAX_TABS && <button onClick={add} title="New tab (Alt+T)" className="px-2 py-1 text-text-tertiary hover:text-bloomberg">+</button>}
      <span className="ml-auto pr-1 pb-1 text-[10px] text-text-tertiary hidden md:inline">Alt+1…9 switch · Alt+T new · Alt+W close · MENU = back</span>
    </div>
  );
}
