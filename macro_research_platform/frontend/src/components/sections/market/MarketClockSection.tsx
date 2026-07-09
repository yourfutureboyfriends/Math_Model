// Section G Panel 1 — Market Clock + Global Equity Monitor
// Real-time market status with live ticking seconds

import React from 'react';
import { cn } from '@/lib/utils';

// Market sessions configuration - module level constant
const SESSIONS = [
  { name: 'New York',  tz: 'America/New_York',  open: 9.5,  close: 16   },
  { name: 'London',    tz: 'Europe/London',      open: 8,    close: 16.5 },
  { name: 'Tokyo',     tz: 'Asia/Tokyo',         open: 9,    close: 15.5 },
  { name: 'Sydney',    tz: 'Australia/Sydney',   open: 10,   close: 16   },
  { name: 'Hong Kong', tz: 'Asia/Hong_Kong',     open: 9.5,  close: 16   },
  { name: 'Frankfurt', tz: 'Europe/Berlin',      open: 9,    close: 17.5 },
];

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

// Check if a session is currently open
function isSessionOpen(open: number, close: number, tz: string): boolean {
  const h = getLocalHour(tz);
  return h >= open && h < close;
}

// Calculate progress through the trading day
function getSessionProgress(open: number, close: number, tz: string): number {
  const h = getLocalHour(tz);
  if (h < open || h >= close) return 0;
  return Math.min((h - open) / (close - open), 1);
}

export const MarketClockSection: React.FC = () => {
  const [tick, setTick] = React.useState(0);

  // Update every second to show live time
  // tick is used to trigger re-renders for live clock
  React.useEffect(() => {
    const timer = setInterval(() => setTick(n => n + 1), 1000);
    return () => clearInterval(timer);
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
    s => isSessionOpen(s.open, s.close, s.tz)
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
          const open = isSessionOpen(session.open, session.close, session.tz);
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
                  open
                    ? 'bg-green-dim text-green'
                    : 'bg-surface-3 text-text-tertiary'
                )}>
                  {open ? 'OPEN' : 'CLOSED'}
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
