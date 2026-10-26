// Bottom dock: the world ticker tape over a terminal status bar.
//
// Status bar, left to right: world exchange clocks in the order the trading day travels (Sydney → … → São Paulo),
// each with its local time and an open / lunch / closed light; then the data link (live socket), the model's data
// date, the fund and base currency, the signed-in user, the keyboard hints and the live-alerts button (pop-up
// history and settings). The tape can be hidden (remembered in this browser).
import { useEffect, useState } from 'react';
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
