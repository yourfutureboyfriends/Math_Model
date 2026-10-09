// Markets mode — a universal, Bloomberg-style market workstation.
// Routes live in the URL hash so every screen can be linked or bookmarked:
//   #mkt/wei · #mkt/des/7203.T · #mkt/omon/SPY · #mkt/eqs · #mkt/imap …
import { useCallback, useEffect, useState } from 'react';
import { Bell, BookOpen, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { CommandLine } from '@/components/markets/CommandLine';
import { FUNCTIONS, SECURITY_FUNCTIONS, findFunction, type MktFunction } from '@/components/markets/functions';
import { OverviewView } from '@/components/markets/OverviewView';
import { Chart, Financials, News, Profile, QuoteHeader, useQuote } from '@/components/markets/TickerView';
import { MoversView, ScreenerView } from '@/components/markets/ScreenerView';
import { AnrView, BetaView, DcfView, DvdView, ErnView, HdsView, HpView, OmonView, RvView } from '@/components/markets/SecurityFunctions';
import { BtmmView, CmdtyView, CompView, CryptoView, EcoView, EvtsView, GcView, ImapView, NewsView, WcrsView } from '@/components/markets/GlobalFunctions';
import { AlertsView, AlertToasts, JournalView, WatchlistsView, useAddToWatchlist } from '@/components/markets/MyTools';
import { ErrorBox, Loading } from '@/components/markets/shared';

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

function SecurityView({ fn, symbol, onGo }: { fn: string; symbol: string; onGo: (fn: string, s?: string) => void }) {
  const q = useQuote(symbol);
  const addToWatch = useAddToWatchlist();
  const [note, setNote] = useState<string | null>(null);
  const d = q.data;
  const isEquity = d?.type === 'Stock';
  const tabs = SECURITY_FUNCTIONS.filter((f) => !f.equityOnly || isEquity);
  const f = findFunction(fn)!;
  if (q.loading && !d) return <Loading label={`Loading ${symbol}…`} />;
  if (q.error && !d) return <ErrorBox msg={`${q.error} Try the command line to search by name.`} />;
  if (!d) return null;
  return (
    <div className="space-y-3">
      <div className="bg-surface-1 border border-border p-4 space-y-3">
        <QuoteHeader d={d} />
        <div className="flex flex-wrap gap-2">
          <button onClick={async () => { try { const n = await addToWatch(symbol); if (n) setNote(`Added to “${n}”.`); } catch (e: any) { setNote(e.message); } }}
            className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs border border-border hover:border-bloomberg"><Plus className="w-3 h-3" />Watch</button>
          <button onClick={() => onGo('ALRT', symbol)} className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs border border-border hover:border-bloomberg"><Bell className="w-3 h-3" />Alert</button>
          <button onClick={() => onGo('JRNL', symbol)} className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs border border-border hover:border-bloomberg"><BookOpen className="w-3 h-3" />Journal</button>
          <button onClick={() => onGo('COMP', symbol)} className="inline-flex items-center gap-1 px-2.5 py-1 text-2xs border border-border hover:border-bloomberg">Compare</button>
          {note && <span className="text-2xs text-green self-center">{note}</span>}
        </div>
      </div>
      <nav aria-label="Functions" className="flex flex-wrap gap-0.5 border-b border-border">
        {tabs.map((t) => (
          <button key={t.code} onClick={() => onGo(t.code, symbol)} title={t.desc}
            className={cn('px-3 py-1.5 text-2xs -mb-px border-b-2 whitespace-nowrap', t.code === f.code ? 'border-bloomberg text-text-primary' : 'border-transparent text-text-secondary hover:text-text-primary')}>
            <span className="font-mono font-semibold mr-1 text-bloomberg/90">{t.code}</span>{t.name}</button>))}
      </nav>
      <ErrorBoundary sectionName={`${f.code} ${symbol}`} key={`${f.code}:${symbol}`}>
        {f.code === 'DES' && <div className="space-y-3"><Chart symbol={symbol} height={320} /><Profile symbol={symbol} /></div>}
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
  return (
    <div className="p-4 space-y-4 max-w-[1680px]">
      <CommandLine current={f.security ? route.symbol : undefined} onGo={onGo} />
      {f.security && route.symbol ? <SecurityView fn={f.code} symbol={route.symbol} onGo={onGo} /> : (
        <div className="space-y-3">
          <FunctionHeader f={f} />
          <ErrorBoundary sectionName={`Markets · ${f.code}`} key={f.code}>
            {f.code === 'WEI' && <div className="space-y-5"><Launchpad onGo={onGo} /><OverviewView onOpen={open} /></div>}
            {f.code === 'MOST' && <MoversView onOpen={open} />}
            {f.code === 'EQS' && <ScreenerView onOpen={open} />}
            {f.code === 'IMAP' && <ImapView onOpen={open} />}
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
          </ErrorBoundary>
        </div>
      )}
      <AlertToasts onOpen={open} />
    </div>
  );
}
