// Bottom dock: the world ticker tape over a terminal status bar.
//
// Status bar, left to right: world exchange clocks in the order the trading day travels (Sydney → … → São Paulo),
// each with its local time and an open / lunch / closed light; then the data link (live socket), the model's data
// date, the fund and base currency, the signed-in user, the keyboard hints and the live-alerts button (pop-up
// history and settings). The tape can be hidden (remembered in this browser).
//
// Account bar (between the clocks and the link light), the always-on summary IBKR's account window and Futu's asset
// bar keep in view: NAV, day P&L, unrealized P&L, gross / net exposure and the limits state of the current fund.
// Click it to open Positions. Polled every minute while the page is visible (/api/v1/desk/account).
import { useEffect, useState } from 'react';
import { openPanel } from '@/lib/commands';
import { EXCHANGES, sessionState } from '@/components/markets/MarketClock';
import { useAuth } from '@/context/AuthContext';
import { currentFund } from '@/lib/fund';
import { loadFunds } from '@/lib/fundBrand';
import { cn } from '@/lib/utils';
import { useMacroStore, selectMeta } from '@/store/macroStore';
import { TickerTape } from './TickerTape';
import { AlertsButton } from './LivePopups';

// Exchanges on the clock row, east to west — the order the trading day opens.
const CLOCKS: [string, string][] = [
  ['ASX', 'SYD'], ['TSE', 'TYO'], ['HKEX', 'HKG'], ['SSE', 'SHA'], ['NSE', 'BOM'], ['TADAWUL', 'RUH'],
  ['JSE', 'JNB'], ['XETRA', 'FRA'], ['LSE', 'LDN'], ['NYSE', 'NYC'], ['B3', 'SAO'],
];
const TAPE_KEY = 'ui_tape';

export const DOCK_HEIGHT = { withTape: 48, withoutTape: 24 };

export function useTapeVisible(): [boolean, (v: boolean) => void] {
  const read = () => { try { return localStorage.getItem(TAPE_KEY) !== 'off'; } catch { return true; } };
  const [on, setOn] = useState(read);
  useEffect(() => {
    const h = () => setOn(read());
    window.addEventListener('ui-tape', h);
    return () => window.removeEventListener('ui-tape', h);
  }, []);
  const set = (v: boolean) => {
    try { localStorage.setItem(TAPE_KEY, v ? 'on' : 'off'); } catch { /* storage unavailable */ }
    window.dispatchEvent(new Event('ui-tape'));
  };
  return [on, set];
}

function WorldClocks() {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 15_000); return () => clearInterval(t); }, []);
  return (
    <div className="status-clocks">
      {CLOCKS.map(([code, label]) => {
        const ex = EXCHANGES.find((e) => e.code === code);
        if (!ex) return null;
        const s = sessionState(ex, now);
        return (
          <span key={code} className={cn('status-clock', s.state)} title={`${ex.name} (${ex.code}) — ${s.state === 'open' ? 'open' : s.state === 'lunch' ? 'lunch break' : 'closed'}, ${s.next}. Regular session; holidays not modelled.`}>
            <span className="status-light" />
            <span className="status-city">{label}</span>
            <span className="status-time">{s.local}</span>
          </span>
        );
      })}
    </div>
  );
}

type Account = { available: boolean; base_currency?: string; nav?: number; day_pnl?: number | null; day_pnl_pct?: number | null;
  unrealized_pnl?: number | null; gross_pct?: number | null; net_pct?: number | null; positions?: number; limits?: string };

/** 1,234,567 → 1.23M; signed when asked. */
export function compactMoney(v: number | null | undefined, signed = false): string {
  if (v == null || !Number.isFinite(v)) return '—';
  const a = Math.abs(v);
  const s = a >= 1e9 ? `${(a / 1e9).toFixed(2)}B` : a >= 1e6 ? `${(a / 1e6).toFixed(2)}M` : a >= 1e4 ? `${(a / 1e3).toFixed(1)}K` : a.toFixed(0);
  return `${v < 0 ? '−' : signed && v > 0 ? '+' : ''}${s}`;
}
const pct0 = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(0)}%`);
const toneOf = (v: number | null | undefined) => (v == null || v === 0 ? 'text-text-secondary' : v > 0 ? 'text-green' : 'text-red');

function AccountStrip({ fund }: { fund: string }) {
  const [a, setA] = useState<Account | null>(null);
  useEffect(() => {
    let live = true;
    const get = () => {
      if (document.visibilityState !== 'visible') return;
      fetch('/api/v1/desk/account').then((r) => (r.ok ? r.json() : null)).then((j) => live && setA(j)).catch(() => { /* optional */ });
    };
    get();
    const t = setInterval(get, 60_000);
    document.addEventListener('visibilitychange', get);
    return () => { live = false; clearInterval(t); document.removeEventListener('visibilitychange', get); };
  }, [fund]);
  if (!a?.available) return null;
  const lim = a.limits === 'BREACH' ? 'breach' : a.limits === 'WARN' ? 'warn' : 'open';
  return (
    <button type="button" className="status-account" onClick={() => openPanel('portfolio-positions')}
      title={`Account summary for this fund — click for Positions.\nNAV ${a.nav?.toLocaleString()} ${a.base_currency ?? ''} · ${a.positions ?? 0} positions · limits ${a.limits ?? '—'}\nDay P&L is the last NAV snapshot's change; it needs two snapshots.`}>
      <span className="status-k">NAV</span><span className="status-v">{compactMoney(a.nav)}</span>
      <span className="status-k">DAY</span>
      <span className={cn('status-v', toneOf(a.day_pnl))}>{compactMoney(a.day_pnl, true)}{a.day_pnl_pct != null && <small> {a.day_pnl_pct >= 0 ? '+' : ''}{(a.day_pnl_pct * 100).toFixed(2)}%</small>}</span>
      <span className="status-k hidden 2xl:inline">UNRL</span><span className={cn('status-v hidden 2xl:inline', toneOf(a.unrealized_pnl))}>{compactMoney(a.unrealized_pnl, true)}</span>
      <span className="status-k hidden lg:inline">GROSS</span><span className="status-v hidden lg:inline">{pct0(a.gross_pct)}</span>
      <span className="status-k hidden lg:inline">NET</span><span className="status-v hidden lg:inline">{pct0(a.net_pct)}</span>
      <span className="status-k">LIM</span><span className={cn('status-light', lim)} aria-label={`Limits ${a.limits ?? 'unknown'}`} />
    </button>
  );
}

export function BottomDock() {
  const [tape, setTape] = useTapeVisible();
  const ws = useMacroStore((s) => s.wsConnected);
  const meta = useMacroStore(selectMeta);
  const { user } = useAuth();
  const fund = currentFund();
  const [base, setBase] = useState<string | null>(null);
  useEffect(() => {
    loadFunds().then((fs) => setBase(fs.find((f) => f.id === fund)?.base_currency ?? null)).catch(() => { /* optional */ });
  }, [fund]);

  return (
    <div className="bottom-dock" style={{ height: tape ? DOCK_HEIGHT.withTape : DOCK_HEIGHT.withoutTape }}>
      {tape && <TickerTape />}
      <div className="status-bar">
        <WorldClocks />
        <div className="status-right">
          {user && <AccountStrip fund={fund} />}
          <span className="status-item" title={ws ? 'Live link to the server is up' : 'Live link down — data refreshes by polling'}>
            <span className={cn('status-light', ws ? 'open' : 'closed-warn')} />{ws ? 'LINK' : 'POLL'}
          </span>
          {meta.latestDate && <span className="status-item hidden md:inline-flex" title="Latest observation in the macro model">DATA {meta.latestDate}</span>}
          <span className="status-item" title="Current fund and base currency">
            <span className="text-bloomberg">{fund.toUpperCase()}</span>{base && <span className="text-text-tertiary">{base}</span>}
          </span>
          {user && <span className="status-item hidden lg:inline-flex">{user.username.toUpperCase()}</span>}
          <span className="status-item hidden xl:inline-flex text-text-tertiary"><kbd>⌘K</kbd> COMMAND <kbd>?</kbd> KEYS</span>
          <AlertsButton />
          <button type="button" className="status-btn" onClick={() => setTape(!tape)} aria-pressed={tape}
            title={tape ? 'Hide the ticker tape' : 'Show the ticker tape'}>TAPE {tape ? '▾' : '▴'}</button>
        </div>
      </div>
    </div>
  );
}
