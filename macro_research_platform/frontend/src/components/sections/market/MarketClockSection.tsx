// Section G Panel 1 — Market Clock + Global Equity Monitor
// Real-time market status with live ticking seconds. Holiday calendars are fetched from the
// backend (/api/market-hours → python-holidays, per-region + any-year, incl. lunar calendars),
// NOT hardcoded — the live open/closed computation runs client-side against those dates.

import React from 'react';
import { cn } from '@/lib/utils';

// Populated at runtime from /api/market-hours (exchange display name -> holiday YYYY-MM-DD list).
type HolidayMap = Record<string, { dates: Set<string>; names: Record<string, string> }>;

// Market sessions configuration - module level constant
const SESSIONS = [
  { name: 'New York',  tz: 'America/New_York',  open: 9.5,  close: 16   },
  { name: 'London',    tz: 'Europe/London',      open: 8,    close: 16.5 },
  { name: 'Tokyo',     tz: 'Asia/Tokyo',         open: 9,    close: 15.5 },
  { name: 'Sydney',    tz: 'Australia/Sydney',   open: 10,   close: 16   },
  { name: 'Hong Kong', tz: 'Asia/Hong_Kong',     open: 9.5,  close: 16   },
  { name: 'Frankfurt', tz: 'Europe/Berlin',      open: 9,    close: 17.5 },
];

type SessionStatus = 'open' | 'closed' | 'holiday';

// Local calendar date (YYYY-MM-DD) and weekday (0=Sun..6=Sat) in a timezone.
function getLocalDateInfo(tz: string): { ymd: string; dow: number } {
  try {
    const ymd = new Intl.DateTimeFormat('en-CA', {
      timeZone: tz, year: 'numeric', month: '2-digit', day: '2-digit',
    }).format(new Date());
    const wd = new Intl.DateTimeFormat('en-US', { timeZone: tz, weekday: 'short' }).format(new Date());
    const dow = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].indexOf(wd);
    return { ymd, dow };
  } catch {
    return { ymd: '', dow: 0 };
  }
}

// Get current hour in a specific timezone
function getLocalHour(tz: string): number {
  try {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      hour: 'numeric',
      minute: 'numeric',
      hour12: false,
    }).formatToParts(new Date());
    const h = parseInt(parts.find(p => p.type === 'hour')?.value ?? '0');
    const m = parseInt(parts.find(p => p.type === 'minute')?.value ?? '0');
    return h + m / 60;
  } catch {
    return 0;
  }
}

// Get time string in a specific timezone
function getLocalTimeStr(tz: string): string {
  try {
    return new Intl.DateTimeFormat('en-GB', {
      timeZone: tz,
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    }).format(new Date());
  } catch {
    return '--:--:--';
  }
}

// Full session status: closed on weekends and exchange holidays, else open within hours.
// `holidayMap` is fetched from /api/market-hours (real per-region calendars, not hardcoded).
function getSessionStatus(name: string, open: number, close: number, tz: string, holidayMap: HolidayMap): SessionStatus {
  const { ymd, dow } = getLocalDateInfo(tz);
  if (holidayMap[name]?.dates.has(ymd)) return 'holiday';
  if (dow === 0 || dow === 6) return 'closed';           // weekend
  const h = getLocalHour(tz);
  return h >= open && h < close ? 'open' : 'closed';
}

// Calculate progress through the trading day
function getSessionProgress(open: number, close: number, tz: string): number {
  const h = getLocalHour(tz);
  if (h < open || h >= close) return 0;
  return Math.min((h - open) / (close - open), 1);
}

export const MarketClockSection: React.FC = () => {
  const [tick, setTick] = React.useState(0);
  const [holidayMap, setHolidayMap] = React.useState<HolidayMap>({});

  // Update every second to show live time
  // tick is used to trigger re-renders for live clock
  React.useEffect(() => {
    const timer = setInterval(() => setTick(n => n + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  // Fetch REAL per-region holiday calendars once (not hardcoded). Live open/closed still runs
  // client-side against these dates so the clock keeps ticking.
  React.useEffect(() => {
    let cancelled = false;
    fetch('/api/market-hours')
      .then(r => r.json())
      .then(d => {
        if (cancelled || !d?.exchanges) return;
        const map: HolidayMap = {};
        for (const ex of d.exchanges) {
          map[ex.name] = { dates: new Set<string>(ex.holidays ?? []), names: ex.holidayNames ?? {} };
        }
        setHolidayMap(map);
      })
      .catch(() => { /* fall back to weekend-only detection if unavailable */ });
    return () => { cancelled = true; };
  }, []);

  // Force re-render when tick changes (live clock update)
  void tick;

  // Calculate UTC time
  const utcTime = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'UTC',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  }).format(new Date());

  // Count open sessions (with guard for SESSIONS being undefined)
  const openCount = (SESSIONS ?? []).filter(
    s => getSessionStatus(s.name, s.open, s.close, s.tz, holidayMap) === 'open'
  ).length;

  return (
    <section id="market-clock" className="terminal-section">
      {/* Section Header */}
      <div className="section-header">
        <span className="section-tag">CLOCK</span>
        <h2 className="section-title">Market Clock</h2>
        <span className="section-meta text-text-secondary text-xs">
          {openCount} session{openCount !== 1 ? 's' : ''} open
        </span>
      </div>

      {/* UTC time display */}
      <div className="flex items-center gap-3 mb-4">
        <span className="text-text-secondary text-xs uppercase tracking-widest">
          UTC
        </span>
        <span className="text-bloomberg font-mono text-xl tabular-nums">
          {utcTime}
        </span>
      </div>

      {/* Session grid */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        {SESSIONS.map(session => {
          const status = getSessionStatus(session.name, session.open, session.close, session.tz, holidayMap);
          const open = status === 'open';
          const progress = getSessionProgress(session.open, session.close, session.tz);
          const localTime = getLocalTimeStr(session.tz);

          return (
            <div
              key={session.name}
              className={cn(
                'p-3 border bg-surface-2 flex flex-col gap-1.5',
                open ? 'border-bloomberg/30' : 'border-border-subtle opacity-50'
              )}
            >
              {/* City + status */}
              <div className="flex items-center justify-between">
                <span className="text-text-secondary text-xs">
                  {session.name}
                </span>
                <span className={cn(
                  'text-xs font-semibold px-1.5 py-0.5 rounded',
                  status === 'open' ? 'bg-green-dim text-green'
                    : status === 'holiday' ? 'bg-amber-dim text-amber'
                    : 'bg-surface-3 text-text-tertiary'
                )}
                title={status === 'holiday' ? `${session.name}: exchange holiday` : undefined}>
                  {status === 'open' ? 'OPEN' : status === 'holiday' ? 'HOLIDAY' : 'CLOSED'}
                </span>
              </div>

              {/* Local time */}
              <span className="font-mono tabular-nums text-text-primary text-sm">
                {localTime}
              </span>

              {/* Progress bar (only when open) */}
              <div className="h-0.5 w-full rounded bg-surface-3">
                {open && (
                  <div
                    className="h-full bg-bloomberg transition-all duration-1000"
                    style={{ width: `${progress * 100}%` }}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
};

export default MarketClockSection;
