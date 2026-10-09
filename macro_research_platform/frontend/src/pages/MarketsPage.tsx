// Markets mode — a universal, Bloomberg-style market workstation.
// Routes live in the URL hash so every screen can be linked or bookmarked:
//   #mkt/wei · #mkt/des/7203.T · #mkt/omon/SPY · #mkt/eqs · #mkt/imap …
import { useCallback, useEffect, useState } from 'react';
import { Bell, BookOpen, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { CommandLine } from '@/components/markets/CommandLine';
import { FUNCTIONS, MARKET_FUNCTIONS, SECURITY_FUNCTIONS, findFunction, type MktFunction } from '@/components/markets/functions';
import { FunctionMenu, HelpPanel, KeyBar, NewsCrawl, TitleBar, useHelp } from '@/components/markets/Chrome';
import { MonitorHome } from '@/components/markets/Monitor';
import { toTerminal } from '@/components/markets/bbg';
import { setMarketsSkin, useMarketsSkin } from '@/lib/theme';
import { OverviewView } from '@/components/markets/OverviewView';
import { Chart, Financials, News, useQuote } from '@/components/markets/TickerView';
import { MoversView, ScreenerView } from '@/components/markets/ScreenerView';
import { AnrView, BetaView, DcfView, DvdView, ErnView, HdsView, HpView, OmonView, RvView } from '@/components/markets/SecurityFunctions';
import { BtmmView, CmdtyView, CompView, CryptoView, EcoView, EvtsView, GcView, ImapView, NewsView, WcrsView } from '@/components/markets/GlobalFunctions';
import { AlertsView, AlertToasts, JournalView, WatchlistsView, useAddToWatchlist } from '@/components/markets/MyTools';
import { ErrorBox, fmtPrice, Loading, TYPE_COLOR } from '@/components/markets/shared';
import { InstrumentOverview } from '@/components/markets/InstrumentOverview';
import { WorldMap } from '@/components/markets/WorldMap';
import { AiChat, RightRail } from '@/components/markets/RightRail';

export type MarketsRoute = { fn: string; symbol?: string };

export function parseMarketsHash(h = window.location.hash): MarketsRoute {
  const parts = h.replace(/^#mkt\/?/, '').split('/').filter(Boolean);
  // legacy routes from the first version
  const legacy: Record<string, string> = { overview: 'WEI', ticker: 'DES', movers: 'MOST', screener: 'EQS' };
  const raw = (parts[0] ?? 'wei').toUpperCase();
  const f = findFunction(legacy[raw.toLowerCase()] ?? raw);
  const code = f?.code ?? 'WEI';
  const symbol = parts[1] ? decodeURIComponent(parts[1]).toUpperCase() : undefined;
  if (f?.security && !symbol) return { fn: 'WEI' };
  return { fn: code, symbol };
}

export function goMarkets(fn: string, symbol?: string) {
  const f = findFunction(fn);
  const code = (f?.code ?? 'WEI').toLowerCase();
  window.location.hash = f?.security && symbol ? `#mkt/${code}/${encodeURIComponent(symbol)}` : `#mkt/${code}${symbol && !f?.security ? `/${encodeURIComponent(symbol)}` : ''}`;
  window.scrollTo({ top: 0 });
}

export function useMarketsRoute(): MarketsRoute {
  const [r, setR] = useState<MarketsRoute>(() => parseMarketsHash());
  useEffect(() => {
    const h = () => setR(parseMarketsHash());
    window.addEventListener('hashchange', h);
    return () => window.removeEventListener('hashchange', h);
  }, []);
  return r;
}

const GROUP_ORDER: MktFunction['group'][] = ['Markets', 'Rates & FX', 'Research', 'My tools'];

function FunctionHeader({ f, symbol }: { f: MktFunction; symbol?: string }) {
  return (
    <div className="flex items-baseline gap-3 flex-wrap">
      <span className="px-2 py-0.5 text-xs font-mono font-semibold text-bloomberg border border-bloomberg/50">{f.code}</span>
      <h1 className="text-lg font-semibold text-text-primary">{f.name}{symbol ? <span className="text-text-tertiary font-normal"> · {symbol}</span> : null}</h1>
      <p className="text-2xs text-text-tertiary">{f.desc}</p>
    </div>
  );
}

function Launchpad({ onGo }: { onGo: (fn: string, s?: string) => void }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3">
        {GROUP_ORDER.map((g) => (
          <div key={g} className="bg-surface-1 border border-border">
            <div className="px-3 py-1.5 border-b border-border-subtle text-[10px] uppercase tracking-wider text-text-tertiary">{g}</div>
            <ul>{FUNCTIONS.filter((f) => f.group === g).map((f) => (
              <li key={f.code}><button onClick={() => onGo(f.code)} className="w-full text-left px-3 py-2 hover:bg-surface-3 flex gap-2 items-start group">
                <span className="w-12 shrink-0 text-[11px] font-mono font-semibold text-bloomberg">{f.code}</span>
                <span className="min-w-0"><span className="block text-xs text-text-primary group-hover:text-bloomberg">{f.name}</span>
                  <span className="block text-[10px] text-text-tertiary leading-snug">{f.desc}</span></span></button></li>))}</ul>
          </div>))}
      </div>
      <div className="text-2xs text-text-tertiary">
        Tip: type in the command line above — a company (“toyota”), a ticker (“7203.T”), a function (“EQS”), or both (“NVDA OMON”), then Enter.
        Instrument functions: {SECURITY_FUNCTIONS.map((f) => f.code).join(' · ')}.
      </div>
    </div>
  );
}

function TerminalQuoteHeader({ d, f, symbol, onGo, actions }: { d: any; f: MktFunction; symbol: string; onGo: (fn: string, s?: string) => void; actions: React.ReactNode }) {
  const up = (d.change ?? 0) >= 0;
  const state = d.market_state === 'REGULAR' ? 'OPEN' : d.market_state === 'PRE' ? 'PRE-MKT' : d.market_state === 'POST' || d.market_state === 'POSTPOST' ? 'AFTER HRS' : 'CLOSED';
  return (
    <div className="space-y-1">
      <TitleBar security={toTerminal(d.symbol ?? symbol, d.type)} code={f.code} title={f.name}
        right={<span>{d.exchange} · {d.currency} · {d.delay_minutes ? `delayed ${d.delay_minutes}m` : 'end of day / real-time where free'} · {d.source}</span>} />
      <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1 px-2 py-1 text-[13px]">
        <span className="text-text-primary font-semibold uppercase truncate max-w-[28rem]">{d.name}</span>
        <span className="text-[22px] font-semibold tabular-nums text-text-primary">{fmtPrice(d.price, d.type)}</span>
        {d.change != null && <span className={cn('tabular-nums font-semibold', up ? 'text-green' : 'text-red')}>{up ? '▲' : '▼'} {up ? '+' : ''}{fmtPrice(d.change, d.type)}  {d.change_pct != null ? `${up ? '+' : ''}${(d.change_pct * 100).toFixed(2)}%` : ''}</span>}
        <span className="text-text-secondary">{TYPE_LABEL[d.type] ?? d.type}</span>
        <span className={cn('px-1', state === 'OPEN' ? 'bg-green text-black' : 'border border-border text-text-tertiary')}>{state}</span>
        <span className="ml-auto flex flex-wrap gap-1">{actions}</span>
      </div>
      <div className="px-2 py-1 border border-border">
        <FunctionMenu items={SECURITY_FUNCTIONS} active={f.code} onPick={(x) => onGo(x.code, symbol)} />
      </div>
    </div>
  );
}

const TYPE_LABEL: Record<string, string> = { Stock: 'EQUITY', ETF: 'ETF', Index: 'INDEX', FX: 'CURNCY', Future: 'COMDTY', Crypto: 'CRYPTO', Fund: 'FUND' };

function SecurityView({ fn, symbol, onGo }: { fn: string; symbol: string; onGo: (fn: string, s?: string) => void }) {
  const classic = useMarketsSkin() === 'classic';
  const q = useQuote(symbol);
  const addToWatch = useAddToWatchlist();
  const [note, setNote] = useState<string | null>(null);
  // while a new symbol loads, don't show the previous security under the new one
  const d = q.current ? q.data : null;
  const isEquity = d?.type === 'Stock';
  const tabs = SECURITY_FUNCTIONS.filter((f) => !f.equityOnly || isEquity);
  const f = findFunction(fn)!;
  if (!d && !q.error) return <Loading label={`Loading ${symbol}…`} />;
  if (q.error && !d) return <ErrorBox msg={`${q.error} Try the command line to search by name.`} />;
  if (!d) return null;
  const watch = async () => { try { const n = await addToWatch(symbol); if (n) setNote(`Added to “${n}”.`); } catch (e: any) { setNote(e.message); } };
  const tk = 'px-2 py-0.5 text-[11px] border border-border hover:border-bloomberg hover:text-bloomberg';
  return (
    <div className="space-y-3">
      {classic ? (
        <TerminalQuoteHeader d={d} f={f} symbol={symbol} onGo={onGo} actions={<>
          <button onClick={watch} className={tk}>+ WATCH</button>
          <button onClick={() => onGo('ALRT', symbol)} className={tk}>ALRT</button>
          <button onClick={() => onGo('JRNL', symbol)} className={tk}>JRNL</button>
          <button onClick={() => onGo('COMP', symbol)} className={tk}>COMP</button>
          {note && <span className="text-[11px] text-green self-center">{note}</span>}</>} />
      ) : <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-xs text-text-tertiary">
            <span className="font-mono font-semibold text-text-secondary">{d.symbol}</span><span>·</span><span>{d.exchange}</span>
            <span className={cn('px-1.5 py-0.5 rounded border border-border text-[10px]', TYPE_COLOR[d.type])}>{d.type}</span>
            {d.market_state && <span className={cn('inline-flex items-center gap-1', d.market_state === 'REGULAR' ? 'text-green' : '')}>
              <span className={cn('w-1.5 h-1.5 rounded-full', d.market_state === 'REGULAR' ? 'bg-green' : 'bg-text-tertiary')} />
              {d.market_state === 'REGULAR' ? 'Market open' : d.market_state === 'PRE' ? 'Pre-market' : d.market_state === 'POST' || d.market_state === 'POSTPOST' ? 'After hours' : 'Market closed'}</span>}
          </div>
          <h1 className="text-2xl font-semibold text-text-primary mt-1 truncate">{d.name}</h1>
          <div className="flex items-baseline gap-3 mt-1">
            <span className="text-4xl font-semibold font-mono tabular-nums text-text-primary">{fmtPrice(d.price, d.type)}</span>
            <span className="text-sm font-mono">{d.currency}</span>
            {d.change != null && <span className={cn('px-2 py-0.5 rounded-md text-sm font-mono font-semibold', d.change >= 0 ? 'bg-green/15 text-green' : 'bg-red/15 text-red')}>
              {d.change >= 0 ? '+' : ''}{fmtPrice(d.change, d.type)} ({d.change_pct != null ? `${d.change_pct >= 0 ? '+' : ''}${(d.change_pct * 100).toFixed(2)}%` : '—'})</span>}
          </div>
          <div className="text-[11px] text-text-tertiary mt-1">{d.delay_minutes ? `Delayed ${d.delay_minutes} min · ` : ''}Source: {d.source}</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={watch}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-xs border border-border hover:border-bloomberg bg-surface-1"><Plus className="w-3.5 h-3.5" />Watch</button>
          <button onClick={() => onGo('ALRT', symbol)} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-xs border border-border hover:border-bloomberg bg-surface-1"><Bell className="w-3.5 h-3.5" />Alert</button>
          <button onClick={() => onGo('JRNL', symbol)} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-xs border border-border hover:border-bloomberg bg-surface-1"><BookOpen className="w-3.5 h-3.5" />Journal</button>
          <button onClick={() => onGo('COMP', symbol)} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-xs border border-border hover:border-bloomberg bg-surface-1">Compare</button>
          {note && <span className="text-xs text-green self-center">{note}</span>}
        </div>
      </div>
      <nav aria-label="Functions" className="flex gap-1 border-b border-border overflow-x-auto [scrollbar-width:thin]">
        {tabs.map((t) => (
          <button key={t.code} onClick={() => onGo(t.code, symbol)} title={t.desc}
            className={cn('px-3 py-2 text-xs -mb-px border-b-2 whitespace-nowrap transition-colors', t.code === f.code ? 'border-bloomberg text-text-primary font-semibold' : 'border-transparent text-text-secondary hover:text-text-primary')}>
            {t.code === 'DES' ? 'Overview' : t.name}<span className="ml-1.5 font-mono text-[9px] text-text-tertiary">{t.code}</span></button>))}
      </nav>
      </>}
      <ErrorBoundary sectionName={`${f.code} ${symbol}`} key={`${f.code}:${symbol}`}>
        {f.code === 'DES' && <InstrumentOverview q={d} onOpen={(s) => onGo('DES', s)} onGo={onGo} />}
        {f.code === 'GP' && <Chart symbol={symbol} height={560} />}
        {f.code === 'FA' && <Financials symbol={symbol} />}
        {f.code === 'ERN' && <ErnView symbol={symbol} />}
        {f.code === 'ANR' && <AnrView symbol={symbol} />}
        {f.code === 'HDS' && <HdsView symbol={symbol} />}
        {f.code === 'DVD' && <DvdView symbol={symbol} />}
        {f.code === 'OMON' && <OmonView symbol={symbol} />}
        {f.code === 'RV' && <RvView symbol={symbol} onOpen={(s) => onGo('DES', s)} />}
        {f.code === 'HP' && <HpView symbol={symbol} />}
        {f.code === 'BETA' && <BetaView symbol={symbol} />}
        {f.code === 'DCF' && <DcfView symbol={symbol} />}
        {f.code === 'CN' && <News symbol={symbol} />}
      </ErrorBoundary>
    </div>
  );
}

export function MarketsPage() {
  const route = useMarketsRoute();
  const onGo = useCallback((fn: string, s?: string) => goMarkets(fn, s), []);
  const open = useCallback((s: string) => goMarkets('DES', s), []);
  useEffect(() => { if (!window.location.hash.startsWith('#mkt')) goMarkets('WEI'); }, []);
  const f = findFunction(route.fn) ?? findFunction('WEI')!;
  const classic = useMarketsSkin() === 'classic';
  const help = useHelp();
  return (
    <div className={cn('mkt-root flex items-start', classic ? 'p-2 pb-10 gap-2' : 'p-4 gap-4')}>
    <div className={cn('flex-1 min-w-0', classic ? 'space-y-2' : 'space-y-4 max-w-[1500px]')}>
      {classic ? <KeyBar onGo={(fn) => onGo(fn)} onHelp={help.toggle} /> : (
        <div className="flex justify-end -mb-2"><button onClick={() => setMarketsSkin('classic')} className="text-[11px] text-text-tertiary hover:text-bloomberg">Switch to the classic terminal look</button></div>)}
      <CommandLine current={f.security ? route.symbol : undefined} onGo={onGo} />
      {help.open && <HelpPanel onClose={help.close} />}
      {f.security && route.symbol ? <SecurityView fn={f.code} symbol={route.symbol} onGo={onGo} /> : (
        <div className={classic ? 'space-y-2' : 'space-y-3'}>
          {classic ? <TitleBar code={f.code} title={f.name} right={f.desc} /> : <FunctionHeader f={f} />}
          <ErrorBoundary sectionName={`Markets · ${f.code}`} key={f.code}>
            {f.code === 'WEI' && (classic
              ? <div className="space-y-2"><div className="px-2 py-1 border border-border"><FunctionMenu items={MARKET_FUNCTIONS} onPick={(x) => onGo(x.code)} /></div><MonitorHome onOpen={open} onGo={onGo} /></div>
              : <div className="space-y-5"><Launchpad onGo={onGo} /><OverviewView onOpen={open} /></div>)}
            {f.code === 'MOST' && <MoversView onOpen={open} />}
            {f.code === 'EQS' && <ScreenerView onOpen={open} />}
            {f.code === 'IMAP' && <ImapView onOpen={open} />}
            {f.code === 'MAP' && <WorldMap onOpen={open} />}
            {f.code === 'CRYPTO' && <CryptoView onOpen={open} />}
            {f.code === 'CMDTY' && <CmdtyView onOpen={open} />}
            {f.code === 'COMP' && <CompView seed={route.symbol} />}
            {f.code === 'GC' && <GcView />}
            {f.code === 'BTMM' && <BtmmView />}
            {f.code === 'WCRS' && <WcrsView onOpen={open} />}
            {f.code === 'EVTS' && <EvtsView onOpen={open} />}
            {f.code === 'ECO' && <EcoView />}
            {f.code === 'N' && <NewsView />}
            {f.code === 'W' && <WatchlistsView onOpen={open} />}
            {f.code === 'ALRT' && <AlertsView seed={route.symbol} />}
            {f.code === 'JRNL' && <JournalView seed={route.symbol} onOpen={open} />}
            {f.code === 'AI' && <div className="bg-surface-1 border border-border rounded-md h-[calc(100vh-220px)] min-h-[480px]"><AiChat context={route.symbol} /></div>}
          </ErrorBoundary>
        </div>
      )}
      <AlertToasts onOpen={open} />
      {classic && <NewsCrawl />}
    </div>
    {f.code !== 'AI' && <RightRail symbol={f.security ? route.symbol : undefined} onOpen={open} />}
    </div>
  );
}
