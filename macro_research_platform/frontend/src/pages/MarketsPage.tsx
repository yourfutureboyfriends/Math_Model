import { ResearchDesk } from '@/components/markets/ResearchDesk';
import { SavedLayouts } from '@/components/markets/SavedLayouts';
// Markets mode — a universal, Bloomberg-style market workstation.
// Routes live in the URL hash so every screen can be linked or bookmarked:
//   #mkt/wei · #mkt/des/7203.T · #mkt/omon/SPY · #mkt/eqs · #mkt/imap …
import { useCallback, useEffect, useState } from 'react';
import { Bell, BookOpen, Briefcase, Plus } from 'lucide-react';
import { cn } from '@/lib/utils';
import { setHubMode } from '@/lib/hubMode';
import { openLbo } from '@/components/pe/peShared';
import { ContextStrip } from '@/components/markets/ContextStrip';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { CommandLine } from '@/components/markets/CommandLine';
import { FUNCTIONS, MARKET_FUNCTIONS, SECURITY_FUNCTIONS, findFunction, parseCommand, type MktFunction } from '@/components/markets/functions';
import { FunctionMenu, HelpPanel, KeyBar, NewsCrawl, TitleBar, UpDownToggle, WorkspaceTabs, useHelp } from '@/components/markets/Chrome';
import { QuoteWorkstation, WatchColumn } from '@/components/markets/QuoteWorkstation';
import { CorrView, FrdView, OsaView, RrgView, SeasView } from '@/components/markets/AnalyticsViews';
import { EcoGlobalView, EcstView, SiView, SplcView } from '@/components/markets/DataViews';
import { FutuView } from '@/components/markets/FutuView';
import { ActionsView } from '@/components/markets/ActionsView';
import { FlyView, QuakeView, ShipView } from '@/components/markets/TrackingViews';
import { FlowView } from '@/components/markets/FlowView';
import { CotView, EdgeBoard, NowView } from '@/components/markets/EdgeViews';
import { PredView, RelatedOdds } from '@/components/markets/PredMarkets';
import { ValuationHub } from '@/components/markets/ValuationHub';
import { CfView, CredView, FacView, PortView } from '@/components/markets/ResearchViews';
import { CbrtView, EcosView, EtfaView, SprdView, TechView } from '@/components/markets/ToolkitViews';
import { AllWeatherPanel, DebtCyclesPanel, EnvironmentsPanel, HolyGrailPanel, WorldOrderPanel } from '@/components/markets/BridgewaterViews';
import { CacsView, CdrView, ChartView, DataView, DdisView, DvdcView, FsrcView, FxcaView, IlbeView, MembView, MgmtView, MrgrView, OvdvView, PgeoView, YasView } from '@/components/markets/TerminalPlus';
import { BreadthView, ImpmView, RiskView, UoaView, VolView } from '@/components/markets/InsightViews';
import { AuctView, EiaView, InsdView, IpoView, ThirteenFView, WetrView, WirpView } from '@/components/markets/ExtrasViews';
import { CountryView, RegionBar, RegionMonitor } from '@/components/markets/RegionViews';
import { useRegion } from '@/lib/region';
import { MonitorHome } from '@/components/markets/Monitor';
import { toTerminal } from '@/components/markets/bbg';
import { setMarketsSkin, useMarketsSkin } from '@/lib/theme';
import { OverviewView } from '@/components/markets/OverviewView';
import { Chart, Financials, News, useQuote } from '@/components/markets/TickerView';
import { MoversView, ScreenerView } from '@/components/markets/ScreenerView';
import { AnrView, BetaView, DcfView, DvdView, ErnView, FundHoldingsView, HdsView, HpView, NotApplicable, OmonView, RvView } from '@/components/markets/SecurityFunctions';
import { BtmmView, CmdtyView, CompView, CryptoView, EvtsView, GcView, ImapView, NewsView, WcrsView } from '@/components/markets/GlobalFunctions';
import { AlertsView, JournalView, TeamNotes, WatchlistsView, useAddToWatchlist } from '@/components/markets/MyTools';
import { LiveNumber } from '@/components/ui/LiveNumber';
import { useLiveQuote } from '@/lib/cryptoStream';
import { ErrorBox, fmtPrice, Loading, SourceScope, SourcesBar, TYPE_COLOR } from '@/components/markets/shared';
import { WorldMap } from '@/components/markets/WorldMap';
import { PageSections } from '@/components/markets/PageSections';
import { DsView, GeView, ImovView, MrrView, OvmeView, TraView, VapView, WbView, WpeView } from '@/components/markets/StandardViews';
import { EaView, EcfcView, EmView, FomcView, FwcvView } from '@/components/markets/StandardViews2';
import { BorrowView, CrprView, DarkView, LeagView, ProbView } from '@/components/markets/GapViews';
import { CdsaView, CdsxView, ExthView, SwapView, TranView } from '@/components/markets/FreeDataViews';
import { ViewTools,useMarketDisplay } from '@/components/markets/ViewTools';
import { tableCSV } from '@/lib/tableData';
import { AiChat, RightRail } from '@/components/markets/RightRail';

export { parseMarketsHash, goMarkets, useMarketsRoute } from '@/lib/marketsRoute';
export type { MarketsRoute } from '@/lib/marketsRoute';
import { goMarkets, useMarketsRoute } from '@/lib/marketsRoute';

function countryTerms(iso?: string): string[] {
  const code = (iso || 'US').toUpperCase();
  let name = '';
  try { name = new Intl.DisplayNames(['en'], { type: 'region' }).of(code) ?? ''; } catch { /* old browser */ }
  const extra: Record<string, string[]> = { US: ['fed', 'recession', 'us'], GB: ['uk', 'britain', 'bank of england'], JP: ['boj', 'yen'], CN: ['china', 'xi'],
    DE: ['germany', 'ecb'], FR: ['france', 'macron', 'ecb'], RU: ['russia', 'putin'], UA: ['ukraine', 'zelenskyy'], IL: ['israel'], IR: ['iran'], TW: ['taiwan'], KR: ['korea'] };
  return [...new Set([name.replace(/^United States$/, 'United States'), ...(extra[code] ?? [])].filter(Boolean))];
}

const GROUP_ORDER: MktFunction['group'][] = ['Markets', 'Rates & FX', 'Economy & policy', 'Alternative data', 'Research', 'My tools'];

/** The Markets page header: the same card, eyebrow, title and intro as the other areas' WorkspaceHeader. On an
 * instrument page the quote header below names the security, so this shows the function only. */
function MarketsHeader({ f, symbol, security, children }: { f: MktFunction; symbol?: string; security: boolean; children: React.ReactNode }) {
  return (
    <header className="workspace-hero mkt-hero" data-area="markets">
      <div className="workspace-hero-intro">
        <span className="workspace-emblem mkt-hero-code" title="Function code">{f.code}</span>
        <div className="min-w-0">
          <div className="workspace-eyebrow">Markets / {security && symbol ? symbol : f.group === 'Markets' ? 'Market-wide' : f.group}</div>
          <h1>{f.name}{security && symbol ? <span className="text-text-tertiary font-normal"> · {symbol}</span> : null}</h1>
          <p>{f.desc}</p>
        </div>
        <div className="mkt-hero-actions">
          <SoftKeys fn={f.code} symbol={symbol} />
          <span className="flex items-center gap-3"><UpDownToggle />
            <button onClick={() => setMarketsSkin('classic')} className="hover:text-bloomberg">Classic terminal look</button></span>
        </div>
      </div>
      <div className="workspace-hero-tools mkt-hero-tools">{children}</div>
    </header>
  );
}

function Launchpad({ onGo }: { onGo: (fn: string, s?: string) => void }) {
  return (
    <div className="space-y-3">
      <div className="mkt-quick-functions">{['MOST','EQS','MAP','ECO','N','W'].map(code=>{const f=findFunction(code)!;return <button key={code} onClick={()=>onGo(code)} title={f.desc}><span>{code}</span><strong>{f.name}</strong><b aria-hidden>↗</b></button>;})}</div>
      <details className="mkt-function-directory"><summary>Browse all market functions <span>{MARKET_FUNCTIONS.length} tools · or search the navigation</span></summary>
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
      </details>
      <div className="text-2xs text-text-tertiary">
        Tip: type in the command line above — a company (“toyota”), a ticker (“7203.T”), a function (“EQS”), or both (“NVDA OMON”), then Enter.
        Instrument functions: {SECURITY_FUNCTIONS.map((f) => f.code).join(' · ')}.
      </div>
    </div>
  );
}

function TerminalQuoteHeader({ d, f, symbol, onGo, actions }: { d: any; f: MktFunction; symbol: string; onGo: (fn: string, s?: string) => void; actions: React.ReactNode }) {
  const up = (d.change ?? 0) > 0, flat = !d.change;
  const state = d.market_state === 'REGULAR' ? 'OPEN' : d.market_state === 'PRE' ? 'PRE-MKT' : d.market_state === 'POST' || d.market_state === 'POSTPOST' ? 'AFTER HRS' : 'CLOSED';
  return (
    <div className="space-y-1">
      <TitleBar security={toTerminal(d.symbol ?? symbol, d.type)} code={f.code} title={f.name}
        right={<span className="flex items-center gap-4"><span className="hidden xl:inline">{d.exchange} · {d.currency} · {d.delay_minutes ? `delayed ${d.delay_minutes}m` : 'real-time where free'}</span><SoftKeys fn={f.code} symbol={symbol} /></span>} />
      <div className="flex flex-wrap items-baseline gap-x-5 gap-y-1 px-2 py-1 text-[13px]">
        <span className="text-text-primary font-semibold uppercase truncate max-w-[28rem]">{d.name}</span>
        <LiveNumber value={d.price} format={(v) => fmtPrice(v, d.type)} className="text-[22px] font-semibold tabular-nums text-text-primary" />
        {d.change != null && <span className={cn('tabular-nums font-semibold', flat ? 'text-text-secondary' : up ? 'text-green' : 'text-red')}>{flat ? '■' : up ? '▲' : '▼'} {up ? '+' : ''}{fmtPrice(d.change, d.type)}  {d.change_pct != null ? `${up ? '+' : ''}${(d.change_pct * 100).toFixed(2)}%` : ''}</span>}
        <span className="text-text-secondary">{TYPE_LABEL[d.type] ?? d.type}</span>
        <span className={cn('px-1.5 rounded-sm text-[11px] border', state === 'OPEN' ? 'border-green/40 bg-green/10 text-green' : 'border-border text-text-tertiary')}>{state}</span>
        <span className="ml-auto flex flex-wrap gap-1">{actions}</span>
      </div>
      <div className="px-2 py-1 border border-border">
        <FunctionMenu items={SECURITY_FUNCTIONS} active={f.code} onPick={(x) => onGo(x.code, symbol)}
          dim={(x) => !!x.equityOnly && d.type !== 'Stock' && !(x.code === 'HDS' && (d.type === 'ETF' || d.type === 'Fund'))} />
      </div>
    </div>
  );
}

const TYPE_LABEL: Record<string, string> = { Stock: 'EQUITY', ETF: 'ETF', Index: 'INDEX', FX: 'CURNCY', Future: 'COMDTY', Crypto: 'CRYPTO', Fund: 'FUND' };

export function SecurityBody({ code, symbol, d, isFund, onGo,compact=false }: { code: string; symbol: string; d: any; isFund: boolean; onGo: (fn: string, s?: string) => void;compact?:boolean }) {
  return (
    <div className="mkt-page-canvas" data-market-page={code}><PageSections page={code} compact={compact}/>
        {code === 'DES' && <QuoteWorkstation q={d} onOpen={(s) => onGo('DES', s)} onGo={onGo} />}
        {code === 'DES' && <div className="mt-3"><TeamNotes target={symbol} /></div>}
        {code === 'GP' && <Chart symbol={symbol} height={560} />}
        {code === 'FA' && <Financials symbol={symbol} />}
        {code === 'ERN' && <ErnView symbol={symbol} />}
        {code === 'ANR' && <AnrView symbol={symbol} />}
        {code === 'HDS' && (isFund ? <FundHoldingsView symbol={symbol} onOpen={(s) => onGo('DES', s)} /> : <HdsView symbol={symbol} />)}
        {code === 'DVD' && <DvdView symbol={symbol} />}
        {code === 'OMON' && <OmonView symbol={symbol} />}
        {code === 'RV' && <RvView symbol={symbol} onOpen={(s) => onGo('DES', s)} />}
        {code === 'HP' && <HpView symbol={symbol} />}
        {code === 'BETA' && <BetaView symbol={symbol} />}
        {code === 'VAP' && <VapView symbol={symbol} />}
        {code === 'OVME' && <OvmeView symbol={symbol} q={d} />}
        {code === 'GE' && <GeView symbol={symbol} />}
        {code === 'EM' && <EmView symbol={symbol} />}
        {code === 'CRPR' && <CrprView symbol={symbol} />}
        {code === 'PROB' && <ProbView symbol={symbol} />}
        {code === 'DARK' && <DarkView symbol={symbol} />}
        {code === 'TRAN' && <TranView symbol={symbol} />}
        {code === 'DS' && <DsView symbol={symbol} onGo={onGo} />}
        {code === 'DCF' && <DcfView symbol={symbol} />}
        {code === 'VAL' && <ValuationHub symbol={symbol} onGo={onGo} />}
        {code === 'CF' && <CfView symbol={symbol} />}
        {code === 'TECH' && <TechView symbol={symbol} />}
        {code === 'FUTU' && <FutuView symbol={symbol} />}
        {code === 'OVDV' && <OvdvView symbol={symbol} />}
        {code === 'CACS' && <CacsView symbol={symbol} />}
        {code === 'MGMT' && <MgmtView symbol={symbol} />}
        {code === 'PGEO' && <PgeoView symbol={symbol} />}
        {code === 'DDIS' && <DdisView symbol={symbol} />}
        {code === 'FAC' && <FacView symbol={symbol} />}
        {code === 'CN' && <News symbol={symbol} />}
        {code === 'SEAS' && <SeasView symbol={symbol} />}
        {code === 'OSA' && <OsaView symbol={symbol} />}
        {code === 'SI' && <SiView symbol={symbol} />}
        {code === 'INSD' && <InsdView symbol={symbol} />}
        {code === 'SPLC' && <SplcView symbol={symbol} onOpen={(s) => onGo('DES', s)} />}
    </div>
  );
}

export function SecurityView({ fn, symbol, onGo, compact = false }: { fn: string; symbol: string; onGo: (fn: string, s?: string) => void; compact?: boolean }) {
  const classic = useMarketsSkin() === 'classic';
  const q = useQuote(symbol);
  const addToWatch = useAddToWatchlist();
  const [note, setNote] = useState<string | null>(null);
  // while a new symbol loads, don't show the previous security under the new one
  const d = useLiveQuote(q.current ? q.data : null);    // crypto: streamed trades over the polled quote
  const isEquity = d?.type === 'Stock';
  const isFund = d?.type === 'ETF' || d?.type === 'Fund';
  const tabs = SECURITY_FUNCTIONS.filter((f) => !f.equityOnly || isEquity || (f.code === 'HDS' && isFund));
  const f = findFunction(fn)!;
  // two-level function bar: the group being browsed (defaults to the open function's group)
  const [browse, setBrowse] = useState<string | null>(null);
  useEffect(() => setBrowse(null), [fn, symbol]);
  const groupOf = (code: string) => SECURITY_GROUPS.find((g) => g.codes.includes(code))?.name ?? SECURITY_GROUPS[0].name;
  const activeGroup = browse ?? groupOf(f.code);
  if (!d && !q.error) return <Loading label={`Loading ${symbol}…`} />;
  if (q.error && !d) return <ErrorBox onRetry={q.retry} msg={/HTTP 5\d\d|unavailable|fetch/i.test(q.error) ? `${q.error} The data service may be restarting — reopen the security in a moment.` : `${q.error} Try the command line to search by name.`} />;
  if (!d) return null;
  const lbo = () => { openLbo(symbol); setHubMode('pe'); };     // the PE workbench, loaded with this company
  const watch = async () => { try { const n = await addToWatch(symbol); if (n) setNote(`Added to “${n}”.`); } catch (e: any) { setNote(e.message); } };
  const tk = 'px-2 py-0.5 text-[11px] border border-border hover:border-bloomberg hover:text-bloomberg';
  if (compact) {
    const up = (d.change ?? 0) >= 0;
    return (
      <div className="space-y-1">
        <div className="flex items-baseline gap-2 px-1 text-[12px] font-mono">
          <span className="text-[rgb(255,214,0)]">{toTerminal(d.symbol ?? symbol, d.type)}</span>
          <span className="text-text-secondary truncate max-w-[14rem] font-sans">{d.name}</span>
          <span className="text-text-primary font-semibold">{fmtPrice(d.price, d.type)}</span>
          {d.change_pct != null && <span className={up ? 'text-green' : 'text-red'}>{up ? '▲+' : '▼'}{(d.change_pct * 100).toFixed(2)}%</span>}
        </div>
        <ErrorBoundary sectionName={`${f.code} ${symbol}`} key={`${f.code}:${symbol}`}>
          {f.equityOnly && !isEquity && !(f.code === 'HDS' && isFund) ? <NotApplicable fn={f.code} name={f.name} q={d} onGo={onGo} />
            : <SourceScope><SourcesBar className="mb-2"/><SecurityBody compact={compact} code={f.code} symbol={symbol} d={d} isFund={isFund} onGo={onGo}/></SourceScope>}
        </ErrorBoundary>
      </div>);
  }
  return (
    <div className="space-y-3">
      {classic ? (<>
        <TerminalQuoteHeader d={d} f={f} symbol={symbol} onGo={onGo} actions={<>
          <button onClick={watch} className={tk}>+ WATCH</button>
          <button onClick={() => onGo('ALRT', symbol)} className={tk}>ALRT</button>
          <button onClick={() => onGo('JRNL', symbol)} className={tk}>JRNL</button>
          <button onClick={() => onGo('COMP', symbol)} className={tk}>COMP</button>
          {isEquity && <button onClick={lbo} className={tk} title="Model a buyout of this company in the PE area">LBO</button>}
          {note && <span className="text-[11px] text-green self-center">{note}</span>}</>} />
        <ContextStrip symbol={symbol} onGo={onGo} isEquity={isEquity} />
      </>) : <>
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-xs text-text-tertiary">
            <span className="font-mono font-semibold text-text-secondary">{d.symbol}</span><span>·</span><span>{d.exchange}</span>
            <span className={cn('px-1.5 py-0.5 rounded border border-border text-[10px]', TYPE_COLOR[d.type])}>{d.type}</span>
            {d.market_state && <span className={cn('inline-flex items-center gap-1', d.market_state === 'REGULAR' ? 'text-green' : '')}>
              <span className={cn('w-1.5 h-1.5 rounded-full', d.market_state === 'REGULAR' ? 'bg-green' : 'bg-text-tertiary')} />
              {d.market_state === 'REGULAR' ? 'Market open' : d.market_state === 'PRE' ? 'Pre-market' : d.market_state === 'POST' || d.market_state === 'POSTPOST' ? 'After hours' : 'Market closed'}</span>}
          </div>
          <h1 className={cn('font-semibold text-text-primary mt-1 truncate', f.code === 'DES' ? 'text-lg' : 'text-2xl')}>{d.name}</h1>
          {f.code !== 'DES' && <>
          <div className="flex items-baseline gap-3 mt-1">
            <LiveNumber value={d.price} format={(v) => fmtPrice(v, d.type)} className="text-4xl font-semibold font-mono tabular-nums text-text-primary" />
            {d.streaming && <span className="live-pill" title="Every trade on Coinbase, streamed to this page">Live</span>}
            <span className="text-sm font-mono">{d.currency}</span>
            {d.change != null && <span className={cn('px-2 py-0.5 rounded-md text-sm font-mono font-semibold', d.change >= 0 ? 'bg-green/15 text-green' : 'bg-red/15 text-red')}>
              {d.change >= 0 ? '+' : ''}{fmtPrice(d.change, d.type)} ({d.change_pct != null ? `${d.change_pct >= 0 ? '+' : ''}${(d.change_pct * 100).toFixed(2)}%` : '—'})</span>}
          </div>
          <div className="text-[11px] text-text-tertiary mt-1">{d.delay_minutes ? `Delayed ${d.delay_minutes} min · ` : ''}Source: {d.source}</div>
          </>}
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={watch}
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-xs border border-border hover:border-bloomberg bg-surface-1"><Plus className="w-3.5 h-3.5" />Watch</button>
          <button onClick={() => onGo('ALRT', symbol)} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-xs border border-border hover:border-bloomberg bg-surface-1"><Bell className="w-3.5 h-3.5" />Alert</button>
          <button onClick={() => onGo('JRNL', symbol)} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-xs border border-border hover:border-bloomberg bg-surface-1"><BookOpen className="w-3.5 h-3.5" />Journal</button>
          <button onClick={() => onGo('COMP', symbol)} className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-xs border border-border hover:border-bloomberg bg-surface-1">Compare</button>
          {isEquity && <button onClick={lbo} title="Model a buyout of this company in the PE area"
            className="inline-flex items-center gap-1.5 px-3 py-2 rounded-md text-xs border border-border hover:border-bloomberg bg-surface-1"><Briefcase className="w-3.5 h-3.5" />LBO</button>}
          {note && <span className="text-xs text-green self-center">{note}</span>}
        </div>
      </div>
      <ContextStrip symbol={symbol} onGo={onGo} isEquity={isEquity} />
      <nav aria-label="Functions" className="border-b border-border">
        <div className="flex flex-wrap gap-x-1" role="tablist" aria-label="Function groups">
          {SECURITY_GROUPS.map((g) => {
            const n = tabs.filter((t) => g.codes.includes(t.code)).length;
            if (!n) return null;
            const on = g.name === activeGroup;
            return (
              <button key={g.name} role="tab" aria-selected={on} onClick={() => setBrowse(g.name)}
                className={cn('px-3 py-1.5 text-[11px] uppercase tracking-wider border-b-2 -mb-px transition-colors',
                  on ? 'border-bloomberg text-text-primary font-semibold' : 'border-transparent text-text-tertiary hover:text-text-primary',
                  g.codes.includes(f.code) && !on && 'text-bloomberg')}>
                {g.name}<span className="ml-1 text-[10px] text-text-tertiary normal-case">{n}</span></button>);
          })}
        </div>
        <div className="flex flex-wrap gap-1 py-1.5">
          {tabs.filter((t) => (SECURITY_GROUPS.find((g) => g.name === activeGroup)?.codes ?? []).includes(t.code)
                              || (!SECURITY_GROUPS.some((g) => g.codes.includes(t.code)) && activeGroup === SECURITY_GROUPS[0].name)).map((t) => (
            <button key={t.code} onClick={() => onGo(t.code, symbol)} title={t.desc}
              className={cn('px-2.5 py-1 text-xs rounded-sm border whitespace-nowrap transition-colors',
                t.code === f.code ? 'border-bloomberg bg-bloomberg/10 text-text-primary font-semibold' : 'border-border-subtle text-text-secondary hover:text-text-primary hover:border-border')}>
              {t.code === 'DES' ? 'Overview' : t.name}<span className="ml-1.5 font-mono text-[10px] text-text-tertiary">{t.code}</span></button>))}
        </div>
      </nav>
      </>}
      <ErrorBoundary sectionName={`${f.code} ${symbol}`} key={`${f.code}:${symbol}`}>
        {f.equityOnly && !isEquity && !(f.code === 'HDS' && isFund) ? <NotApplicable fn={f.code} name={f.name} q={d} onGo={onGo} /> : <>
        <SourceScope>
          <SourcesBar className="mb-2" />
          <SecurityBody compact={compact} code={f.code} symbol={symbol} d={d} isFund={isFund} onGo={onGo} />
        </SourceScope>
        </>}
      </ErrorBoundary>
    </div>
  );
}

/** Security functions grouped for the two-level function bar (codes not listed fall into the first group). */
const SECURITY_GROUPS: { name: string; codes: string[] }[] = [
  { name: 'Price & trading', codes: ['DES', 'GP', 'HP', 'TECH', 'SEAS', 'BETA', 'VAP', 'FUTU', 'SI', 'DARK'] },
  { name: 'Fundamentals', codes: ['FA', 'ERN', 'EM', 'TRAN', 'DVD', 'PGEO', 'DDIS', 'CF', 'DS', 'CACS'] },
  { name: 'Valuation', codes: ['VAL', 'DCF', 'GE', 'RV', 'FAC', 'CRPR'] },
  { name: 'Analysts & ownership', codes: ['ANR', 'HDS', 'INSD', 'MGMT', 'SPLC', 'CN'] },
  { name: 'Options', codes: ['OMON', 'OVDV', 'OSA', 'OVME', 'PROB'] },
];

/** The body of any market-wide function (used by the main view and by launchpad windows). */
export function MarketBody({ code, seed, onGo, open, classic, compact = false }: { code: string; seed?: string; onGo: (fn: string, s?: string) => void;
  open: (s: string) => void; classic: boolean; compact?: boolean }) {
  const region = useRegion();
  return (
    <SourceScope><div className="mkt-page-canvas" data-market-page={code}>
    <SourcesBar className="mb-2" /><PageSections page={code} compact={compact}/>
    {code === 'RMON' && <RegionMonitor onOpen={open} onGo={onGo} />}
    {code === 'CTRY' && <><CountryView iso={seed} onOpen={open} onGo={onGo} /><RelatedOdds terms={countryTerms(seed)} title="Odds on this country" limit={6} className="mt-3" /></>}
    {code === 'WEI' && (classic || compact
      ? <div className="space-y-2">{!compact && <div className="px-2 py-1 border border-border"><FunctionMenu items={MARKET_FUNCTIONS} onPick={(x) => onGo(x.code)} /></div>}
          {region === 'global' ? <MonitorHome onOpen={open} onGo={onGo} /> : <RegionMonitor onOpen={open} onGo={onGo} />}</div>
      : <div className="space-y-5"><OverviewView onOpen={open} /><Launchpad onGo={onGo} /></div>)}
    {code === 'MOST' && <MoversView onOpen={open} />}
    {code === 'EQS' && <ScreenerView onOpen={open} />}
    {code === 'IMAP' && <ImapView onOpen={open} />}
    {code === 'MAP' && <WorldMap onOpen={open} onGo={onGo} />}
    {code === 'CRYPTO' && <><CryptoView onOpen={open} /><RelatedOdds terms={['bitcoin', 'ethereum', 'solana', 'crypto', 'xrp']} title="Crypto price odds" limit={8} className="mt-3" /></>}
    {code === 'CMDTY' && <><CmdtyView onOpen={open} /><RelatedOdds terms={['oil', 'crude', 'wti', 'brent', 'gold', 'natural gas', 'opec', 'gas price']} title="Commodity odds" limit={8} className="mt-3" /></>}
    {code === 'COMP' && <CompView seed={seed} />}
    {code === 'CORR' && <CorrView seed={seed} />}
    {code === 'RRG' && <RrgView onOpen={open} />}
    {code === 'FRD' && <FrdView />}
    {code === 'FLOW' && <FlowView onOpen={open} />}
    {code === 'EDGE' && <EdgeBoard onGo={onGo} onOpen={open} />}
    {code === 'COT' && <CotView />}
    {code === 'PRED' && <PredView />}
    {code === 'ETFA' && <EtfaView onOpen={(s) => open(s)} />}
    {code === 'CRED' && <><CredView /><RelatedOdds terms={['recession', 'default', 'bankruptcy', 'fed', 'rate cut']} title="Macro odds that move credit" limit={4} className="mt-3" /></>}
    {code === 'PORT' && <PortView onOpen={open} />}
    {code === 'SPRD' && <SprdView seed={seed} />}
    {code === 'CHART' && <ChartView seed={seed} />}
    {code === 'ENVR' && <EnvironmentsPanel />}
    {code === 'AWP' && <AllWeatherPanel />}
    {code === 'DCYC' && <DebtCyclesPanel />}
    {code === 'HGRL' && <HolyGrailPanel defaultSymbols={seed || undefined} />}
    {code === 'WPWR' && <WorldOrderPanel />}
    {code === 'DATA' && <DataView seed={seed} />}
    {code === 'YAS' && <YasView />}
    {code === 'ILBE' && <IlbeView />}
    {code === 'FXCA' && <FxcaView />}
    {code === 'IMOV' && <ImovView onOpen={open} />}
    {code === 'TRA' && <TraView onOpen={open} />}
    {code === 'WPE' && <WpeView onOpen={open} />}
    {code === 'MRR' && <MrrView onOpen={open} />}
    {code === 'WB' && <WbView />}
    {code === 'FWCV' && <FwcvView />}
    {code === 'FOMC' && <FomcView />}
    {code === 'ECFC' && <EcfcView onGo={onGo} />}
    {code === 'EARN' && <EaView onOpen={open} />}
    {code === 'BORROW' && <BorrowView onOpen={open} />}
    {code === 'LEAG' && <LeagView onGo={onGo} />}
    {code === 'SWAP' && <SwapView />}
    {code === 'CDSX' && <CdsxView />}
    {code === 'CDSA' && <CdsaView onOpen={open} />}
    {code === 'EXTH' && <ExthView onOpen={open} />}
    {code === 'MRGR' && <MrgrView onOpen={open} />}
    {code === 'MEMB' && <MembView seed={seed} onOpen={open} />}
    {code === 'FSRC' && <FsrcView onOpen={open} />}
    {code === 'DVDC' && <DvdcView onOpen={open} />}
    {code === 'CDR' && <CdrView />}
    {code === 'CBRT' && <><CbrtView /><RelatedOdds terms={['fed', 'ecb', 'bank of england', 'boj', 'rate cut', 'rate hike']} title="Next decisions — betting-market odds" limit={6} className="mt-3" /></>}
    {code === 'ECOS' && <EcosView seed={seed} />}
    {code === 'NOW' && <NowView />}
    {code === 'RISK' && <><RiskView /><RelatedOdds terms={['recession', 'shutdown', 'debt ceiling', 'fed', 'tariff']} title="Macro risk odds" limit={6} className="mt-3" /></>}
    {code === 'VOL' && <VolView onOpen={open} />}
    {code === 'BRDT' && <BreadthView />}
    {code === 'IMPM' && <ImpmView onOpen={open} />}
    {code === 'UOA' && <UoaView onOpen={open} />}
    {code === 'SHIP' && <><ShipView /><RelatedOdds terms={['hormuz', 'red sea', 'houthi', 'suez', 'panama canal', 'blockade', 'taiwan', 'iran']} title="Shipping-lane risk — geopolitical odds" limit={8} className="mt-3" /></>}
    {code === 'FLY' && <FlyView />}
    {code === 'QUAK' && <QuakeView />}
    {code === 'WIRP' && <><WirpView /><RelatedOdds terms={['fed', 'fomc', 'rate cut', 'rate hike', 'powell', 'fed chair']} title="The same meetings on Kalshi and Polymarket" limit={6} className="mt-3" /></>}
    {code === 'AUCT' && <AuctView />}
    {code === 'EIA' && <EiaView />}
    {code === 'WETR' && <WetrView />}
    {code === '13F' && <ThirteenFView onOpen={open} />}
    {code === 'IPO' && <IpoView onOpen={open} />}
    {code === 'GC' && <GcView />}
    {code === 'BTMM' && <BtmmView />}
    {code === 'WCRS' && <WcrsView onOpen={open} />}
    {code === 'EVTS' && <EvtsView onOpen={open} />}
    {code === 'ACTN' && <ActionsView onOpen={open} />}
    {code === 'ECO' && <><EcoGlobalView /><RelatedOdds terms={['cpi', 'inflation', 'payrolls', 'jobs', 'unemployment', 'gdp', 'recession', 'pce']} title="Release odds — what the crowd expects" limit={8} className="mt-3" /></>}
    {code === 'ECST' && <EcstView />}
    {code === 'N' && <NewsView />}
    {code === 'W' && <WatchlistsView onOpen={open} />}
    {code === 'ALRT' && <AlertsView seed={seed} />}
    {code === 'RDESK' && <ResearchDesk />}
    {code === 'JRNL' && <JournalView seed={seed} onOpen={open} />}
    {code === 'AI' && <div className="bg-surface-1 border border-border rounded-md h-[calc(100vh-220px)] min-h-[480px]"><AiChat context={seed} /></div>}
    </div></SourceScope>
  );
}

// ── LP: multi-window launchpad ───────────────────────────────────────────────
type Link = 'red' | 'green' | 'blue' | 'yellow';
type Pane = { fn: string; symbol?: string; link?: Link | null };
const LINKS: (Link | null)[] = [null, 'red', 'green', 'blue', 'yellow'];
const LINK_RGB: Record<Link, string> = { red: '239 68 68', green: '34 197 94', blue: '59 130 246', yellow: '250 204 21' };
const LP_KEY = 'mkt_lp_v2';
const LAYOUTS: Record<string, { n: number; cls: string; h: string }> = {
  '1x1': { n: 1, cls: 'grid-cols-1', h: 'h-[calc(100vh-230px)]' }, '2x1': { n: 2, cls: 'grid-cols-1 xl:grid-cols-2', h: 'h-[calc(100vh-230px)]' },
  '2x2': { n: 4, cls: 'grid-cols-1 xl:grid-cols-2', h: 'h-[calc((100vh-240px)/2)]' }, '3x2': { n: 6, cls: 'grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3', h: 'h-[calc((100vh-240px)/2)]' },
};
const DEFAULT_LP = { layout: '2x2', panes: [{ fn: 'W', link: 'red' }, { fn: 'GP', symbol: 'AAPL', link: 'red' }, { fn: 'DES', symbol: 'AAPL', link: 'red' },
  { fn: 'WIRP' }, { fn: 'N' }, { fn: 'WEI' }] as Pane[] };
function loadLP(): { layout: string; panes: Pane[] } {
  try { const j = JSON.parse(localStorage.getItem(LP_KEY) || ''); if(Array.isArray(j?.panes)&&j.panes.length&&LAYOUTS[j.layout]){const panes=j.panes.filter((p:any)=>p&&typeof p.fn==='string'&&findFunction(p.fn)&&(!p.symbol||typeof p.symbol==='string')).slice(0,6).map((p:Pane)=>({...p,link:LINKS.includes(p.link??null)?p.link:null}));if(panes.length)return {layout:j.layout,panes};} } catch { /* first run */ }
  return DEFAULT_LP;
}
function saveLP(v: { layout: string; panes: Pane[] }) { try { localStorage.setItem(LP_KEY, JSON.stringify(v)); } catch { /* storage unavailable */ } }

/** Put a function into the first launchpad window and open the launchpad ("pop out"). */
export function popOutToLaunchpad(fn: string, symbol?: string) {
  const st = loadLP();
  const panes = [{ fn, symbol }, ...st.panes].slice(0, 6);
  saveLP({ ...st, panes });
  goMarkets('LP');
}

async function resolveCommand(text: string): Promise<Pane | null> {
  const p = parseCommand(text);
  if (p.fn && !p.fn.security) return { fn: p.fn.code };
  let sym = p.symbol;
  if (sym && !p.terminal) {
    try {
      const j = await (await fetch(`/api/v1/mkt/search?q=${encodeURIComponent(text.replace(new RegExp(`\\b${p.fn?.code ?? '§'}\\b`, 'i'), '').trim())}&limit=1`)).json();
      const hit = j.results?.[0]?.symbol;
      if (hit && (hit.toUpperCase() === sym || !/^[A-Z0-9.^=-]+$/.test(text.trim().toUpperCase().split(' ')[0]) || !p.fn)) sym = hit;
    } catch { /* keep the typed symbol */ }
  }
  return sym ? { fn: p.fn?.code ?? 'DES', symbol: sym } : null;
}

function LpPane({ pane, index, classic, onChange, onClose, onMax, onPick }: { pane: Pane; index: number; classic: boolean; onChange: (p: Pane) => void;
  onClose: () => void; onMax: () => void; onPick: (symbol: string) => boolean }) {
  const [text, setText] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const f = findFunction(pane.fn) ?? findFunction('WEI')!;
  const go = (fn: string, s?: string) => onChange({ ...pane, ...(findFunction(fn)?.security ? { fn, symbol: s ?? pane.symbol } : { fn, symbol: s }) });
  // Picking a security inside a linked window (e.g. a watchlist) drives the linked windows instead
  const openSym = (s: string) => { if (!onPick(s)) go('DES', s); };
  const cycle = () => onChange({ ...pane, link: LINKS[(LINKS.indexOf(pane.link ?? null) + 1) % LINKS.length] });
  const submit = async () => {
    const r = await resolveCommand(text);
    if (!r) { setErr('Not recognised'); return; }
    if (findFunction(r.fn)?.security && !r.symbol) { setErr(`${r.fn} needs a security`); return; }
    setErr(null); setText(''); onChange({ ...r, link: pane.link });
  };
  return (
    <section className="bg-surface-1 border border-border flex flex-col min-w-0 min-h-0" style={pane.link ? { borderTopColor: `rgb(${LINK_RGB[pane.link]})`, borderTopWidth: 2 } : undefined}>
      <header className="panel-hdr flex items-center gap-2 px-1.5 h-7 text-[11px]">
        <button onClick={cycle} title={pane.link ? `Linked: ${pane.link} group — windows of the same colour follow the same security (click to change)` : 'Not linked — click to link this window to a colour group'}
          aria-label={`Window ${index + 1} link group: ${pane.link ?? 'unlinked'}`} className="w-3.5 h-3.5 border border-border-strong shrink-0" style={pane.link ? { background: `rgb(${LINK_RGB[pane.link]})` } : undefined} />
        <span className="key-amber px-1">{index + 1}</span>
        <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === 'Enter') submit(); }}
          placeholder={f.security && pane.symbol ? `${toTerminal(pane.symbol)} ${f.code} — type a security or function` : `${f.code} — type e.g. AAPL US Equity GP, WIRP, toyota`}
          aria-label={`Window ${index + 1} command`} className="flex-1 min-w-0 bg-transparent font-mono text-text-primary placeholder:text-text-tertiary outline-none" />
        {err && <span className="text-red">{err}</span>}
        <span className="text-bloomberg font-mono font-semibold">{f.code}</span>
        <span className="hidden md:inline text-text-tertiary truncate max-w-[10rem]">{f.name}</span>
        <button onClick={onMax} title="Open full screen" className="text-text-tertiary hover:text-bloomberg px-0.5">⤢</button>
        <button onClick={onClose} title="Reset this window" className="text-text-tertiary hover:text-red px-0.5">×</button>
      </header>
      <div className="flex-1 min-h-0 overflow-auto p-1.5 text-[12px]">
        <ErrorBoundary sectionName={`Window ${index + 1}`} key={`${pane.fn}:${pane.symbol ?? ''}`}>
          {f.security && pane.symbol ? <SecurityView fn={f.code} symbol={pane.symbol} onGo={(fn, sym) => (sym && sym !== pane.symbol && fn === 'DES' && onPick(sym) ? undefined : go(fn, sym))} compact />
            : f.security ? <p className="text-xs text-text-tertiary p-2">{f.code} needs a security — type one above, e.g. “AAPL US Equity {f.code}”.</p>
            : <MarketBody code={f.code} seed={pane.symbol} onGo={go} open={openSym} classic={classic} compact />}
        </ErrorBoundary>
      </div>
    </section>
  );
}

function LaunchpadGrid({ classic }: { classic: boolean }) {
  const [st, setSt] = useState(loadLP);
  const [undoLayout,setUndoLayout]=useState<ReturnType<typeof loadLP>|null>(null);
  const restoreLayout=(next:ReturnType<typeof loadLP>)=>{setUndoLayout(structuredClone(st));setSt(next);};
  useEffect(() => saveLP(st), [st]);
  const L = LAYOUTS[st.layout] ?? LAYOUTS['2x2'];
  const panes = [...st.panes, ...DEFAULT_LP.panes].slice(0, L.n);
  const set = (i: number, p: Pane) => setSt((s) => {
    const ps = [...s.panes, ...DEFAULT_LP.panes].slice(0, 6);
    const before = ps[i];
    ps[i] = p;
    // a linked window that switched security takes its colour group with it (IBKR-style linking)
    if (p.link && p.symbol && p.symbol !== before?.symbol && findFunction(p.fn)?.security) {
      ps.forEach((q, j) => { if (j !== i && q.link === p.link && findFunction(q.fn)?.security) ps[j] = { ...q, symbol: p.symbol }; });
    }
    return { ...s, panes: ps };
  });
  /** A security picked inside window i: if other windows share its colour, they follow and window i stays put. */
  const pick = (i: number, symbol: string): boolean => {
    const me = panes[i];
    if (!me?.link) return false;
    const followers = panes.map((q, j) => (j !== i && q.link === me.link && findFunction(q.fn)?.security ? j : -1)).filter((j) => j >= 0);
    if (!followers.length) return false;
    setSt((s) => { const ps = [...s.panes, ...DEFAULT_LP.panes].slice(0, 6); followers.forEach((j) => { ps[j] = { ...ps[j], symbol }; }); return { ...s, panes: ps }; });
    return true;
  };
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-1 text-[11px]">
        <span className="text-text-tertiary mr-1">Layout</span>
        {Object.keys(LAYOUTS).map((k) => <button key={k} onClick={() => setSt((s) => ({ ...s, layout: k }))}
          className={cn('px-2 py-0.5 border font-mono', st.layout === k ? 'border-bloomberg text-bloomberg' : 'border-border text-text-secondary')}>{k}</button>)}
        <button className="px-2 py-0.5 border border-border text-bloomberg" onClick={() => { const symbol = panes.find(p => p.symbol)?.symbol ?? 'AAPL'; restoreLayout({layout:'2x2',panes:['GP','ERN','CF','VAL'].map(fn => ({fn,symbol,link:'blue' as Link}))}); }}>Linked company research</button>
        <button className="px-2 py-0.5 border border-border text-bloomberg" onClick={() => { const symbol = panes.find(p => p.symbol)?.symbol ?? 'AAPL'; restoreLayout({layout:'2x2',panes:['ERN','ANR','CN','FA'].map(fn => ({fn,symbol,link:'green' as Link}))}); }}>Earnings workspace</button>
        <button onClick={() => restoreLayout(DEFAULT_LP)} className="ml-2 px-2 py-0.5 border border-border text-text-tertiary hover:text-text-primary">Reset</button>
        <span className="ml-auto text-text-tertiary">Each window takes its own command (“VOD LN Equity GP”, “WIRP”, “toyota”). The coloured square links windows: same colour = same security, as in IBKR’s Mosaic.</span>
      </div>
      <SavedLayouts value={st} onRestore={restoreLayout}/>
      {undoLayout&&<button className="text-xs text-bloomberg" onClick={()=>{setSt(undoLayout);setUndoLayout(null);}}>Undo layout replacement</button>}
      <div className={cn('grid gap-1.5', L.cls)}>
        {panes.map((p, i) => (
          <div key={i} className={cn('min-w-0', L.h, 'min-h-[320px] flex')}>
            <div className="flex-1 min-w-0 flex">
              <LpPane pane={p} index={i} classic={classic} onChange={(np) => set(i, np)} onClose={() => set(i, DEFAULT_LP.panes[i])} onPick={(sym) => pick(i, sym)}
                onMax={() => goMarkets(p.fn, p.symbol)} />
            </div>
          </div>))}
      </div>
    </div>
  );
}

// ── Soft keys on every function's title bar (Bloomberg: 96) … 99) …) ──────────
function exportFirstTable(name: string):boolean {
  const table=[...document.querySelectorAll('#mkt-fn-body table')].filter(t=>!t.closest('[hidden]')).sort((a,b)=>b.querySelectorAll('tr').length-a.querySelectorAll('tr').length)[0] as HTMLTableElement|undefined;
  if(!table)return false;
  const rows=[...table.rows].filter(r=>!r.hidden).map(r=>[...r.cells].map(c=>(c.innerText||c.textContent||'').replace(/\s+/g,' ').trim()));
  const url=URL.createObjectURL(new Blob(['\uFEFF'+tableCSV(rows[0]??[],rows.slice(1))],{type:'text/csv;charset=utf-8'}));
  const a=document.createElement('a');a.href=url;a.download=`${name}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);return true;
}

function SoftKeys({ fn, symbol, onHelp }: { fn: string; symbol?: string; onHelp?: () => void }) {
  const [notice,setNotice]=useState('');
  const k = 'softkey px-1 hover:underline whitespace-nowrap';
  return (
    <span className="flex gap-2 normal-case tracking-normal text-[11px]">
      {fn !== 'LP' && <button className={k} onClick={() => popOutToLaunchpad(fn, symbol)} title="Open this function in a launchpad window">96) Pop out</button>}
      <button className={k} onClick={()=>setNotice(exportFirstTable(`${fn}${symbol?`_${symbol}`:''}_${new Date().toISOString().slice(0,10)}`)?'CSV downloaded.':'No loaded table here. Use Tables to inspect available data.')} title="Download the main table as CSV">97) Export</button>
      {onHelp && <button className={k} onClick={onHelp}>98) Help</button>}<span role="status" className="text-text-tertiary">{notice}</span>
    </span>
  );
}

const REGION_AWARE = new Set(['WEI', 'RMON', 'MOST', 'EQS', 'IMAP', 'N', 'ECO', 'EVTS', 'MAP', 'LP']);

export function MarketsPage() {
  const route = useMarketsRoute();
  const onGo = useCallback((fn: string, s?: string) => goMarkets(fn, s), []);
  const open = useCallback((s: string) => goMarkets('DES', s), []);
  useEffect(() => { if (!window.location.hash.startsWith('#mkt')) goMarkets('WEI'); }, []);
  const f = findFunction(route.fn) ?? findFunction('WEI')!;
  const classic = useMarketsSkin() === 'classic';
  const help = useHelp();
  const display=useMarketDisplay();
  return (
    <div data-market-density={display.density} className={cn('mkt-root mkt-workspace flex items-start',display.focused&&'mkt-focused', classic ? 'p-2 pb-10 gap-2' : 'p-4 gap-4')}>
    <div className={cn('flex-1 min-w-0', classic ? 'space-y-2' : 'space-y-4', !classic && f.code !== 'LP' && 'max-w-[1500px]')}>
      {classic ? <>
        <KeyBar onGo={(fn) => (fn === 'BACK' ? window.history.back() : onGo(fn))} onHelp={help.toggle} />
        <RegionBar onPick={() => { if (!REGION_AWARE.has(f.code)) onGo('RMON'); }} />
        <WorkspaceTabs />
        <CommandLine current={f.security ? route.symbol : undefined} onGo={onGo} />
        <ViewTools code={f.code} density={display.density} onDensity={display.setDensity} focused={display.focused} onFocus={()=>display.setFocused(v=>!v)} onHelp={help.toggle}/>
      </> : <>
        <WorkspaceTabs />
        {/* the same page header as every other area: where you are, what this page is, its actions, then the command line */}
        <MarketsHeader f={f} symbol={route.symbol} security={!!(f.security && route.symbol)}>
          <CommandLine current={f.security ? route.symbol : undefined} onGo={onGo} />
        </MarketsHeader>
        {/* one toolbar row: the region filter on the left, the view controls on the right. Screens that follow
            the region stay put; anything else opens the regional monitor */}
        <div className="mkt-toolbar-row">
          <RegionBar onPick={() => { if (!REGION_AWARE.has(f.code)) onGo('RMON'); }} />
          <ViewTools code={f.code} density={display.density} onDensity={display.setDensity} focused={display.focused} onFocus={()=>display.setFocused(v=>!v)} onHelp={help.toggle}/>
        </div>
      </>}
      {help.open && <HelpPanel onClose={help.close} />}
      {f.security && route.symbol ? (
        <div className="mkt-security-layout grid grid-cols-1 xl:grid-cols-[230px_minmax(0,1fr)] gap-2 items-start">
          <div className="mkt-watch-column"><WatchColumn current={route.symbol} onOpen={(s) => onGo(f.code, s)} /></div>
          <div className="min-w-0 mkt-function-content" id="mkt-fn-body"><SecurityView fn={f.code} symbol={route.symbol} onGo={onGo} /></div>
        </div>
      ) : (
        <div className={classic ? 'space-y-2' : 'space-y-3'}>
          {classic ? <TitleBar code={f.code} title={f.name} right={<span className="flex items-center gap-4"><span className="hidden xl:inline truncate max-w-[36rem]">{f.desc}</span><SoftKeys fn={f.code} symbol={route.symbol} onHelp={help.toggle} /></span>} />
            : null}
          <div className="mkt-function-content" id="mkt-fn-body">
          <ErrorBoundary sectionName={`Markets · ${f.code}`} key={f.code}>
            {f.code === 'LP' ? <LaunchpadGrid classic={classic} /> : <MarketBody code={f.code} seed={route.symbol} onGo={onGo} open={open} classic={classic} />}
          </ErrorBoundary>
          </div>
        </div>
      )}
      {/* triggered alerts now pop up in both modes (components/layout/LivePopups) */}
      {classic && <NewsCrawl />}
    </div>
    {!display.focused && f.code !== 'AI' && f.code !== 'LP' && !(f.security && route.symbol) && <RightRail onOpen={open} />}
    </div>
  );
}
