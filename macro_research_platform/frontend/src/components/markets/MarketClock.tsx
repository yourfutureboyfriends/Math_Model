// World market hours: each major exchange's session in its own time zone — open / lunch break /
// closed, the local time there, and the time to the next open or close. Regular sessions only;
// exchange holidays are not modelled (the status says "closed" only on weekends).
import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';

type Ex = { code: string; name: string; tz: string; sessions: [string, string][]; days?: number[]; region: string };
// sessions in local exchange time; days = ISO weekdays traded (default Mon–Fri)
export const EXCHANGES: Ex[] = [
  { code: 'NYSE', name: 'New York', tz: 'America/New_York', sessions: [['09:30', '16:00']], region: 'americas' },
  { code: 'TSX', name: 'Toronto', tz: 'America/Toronto', sessions: [['09:30', '16:00']], region: 'americas' },
  { code: 'B3', name: 'São Paulo', tz: 'America/Sao_Paulo', sessions: [['10:00', '17:00']], region: 'americas' },
  { code: 'LSE', name: 'London', tz: 'Europe/London', sessions: [['08:00', '16:30']], region: 'europe' },
  { code: 'XETRA', name: 'Frankfurt', tz: 'Europe/Berlin', sessions: [['09:00', '17:30']], region: 'europe' },
  { code: 'EPA', name: 'Paris', tz: 'Europe/Paris', sessions: [['09:00', '17:30']], region: 'europe' },
  { code: 'SIX', name: 'Zurich', tz: 'Europe/Zurich', sessions: [['09:00', '17:30']], region: 'europe' },
  { code: 'TADAWUL', name: 'Riyadh', tz: 'Asia/Riyadh', sessions: [['10:00', '15:00']], days: [7, 1, 2, 3, 4], region: 'mea' },
  { code: 'JSE', name: 'Johannesburg', tz: 'Africa/Johannesburg', sessions: [['09:00', '17:00']], region: 'mea' },
  { code: 'NSE', name: 'Mumbai', tz: 'Asia/Kolkata', sessions: [['09:15', '15:30']], region: 'apac' },
  { code: 'SSE', name: 'Shanghai', tz: 'Asia/Shanghai', sessions: [['09:30', '11:30'], ['13:00', '15:00']], region: 'apac' },
  { code: 'HKEX', name: 'Hong Kong', tz: 'Asia/Hong_Kong', sessions: [['09:30', '12:00'], ['13:00', '16:00']], region: 'apac' },
  { code: 'SGX', name: 'Singapore', tz: 'Asia/Singapore', sessions: [['09:00', '12:00'], ['13:00', '17:00']], region: 'apac' },
  { code: 'TWSE', name: 'Taipei', tz: 'Asia/Taipei', sessions: [['09:00', '13:30']], region: 'apac' },
  { code: 'KRX', name: 'Seoul', tz: 'Asia/Seoul', sessions: [['09:00', '15:30']], region: 'apac' },
  { code: 'TSE', name: 'Tokyo', tz: 'Asia/Tokyo', sessions: [['09:00', '11:30'], ['12:30', '15:30']], region: 'apac' },
  { code: 'ASX', name: 'Sydney', tz: 'Australia/Sydney', sessions: [['10:00', '16:00']], region: 'apac' },
];

const mins = (hhmm: string) => { const [h, m] = hhmm.split(':').map(Number); return h * 60 + m; };

/** Local weekday (1=Mon … 7=Sun) and minutes after midnight in a time zone. */
function localNow(tz: string, now: Date): { dow: number; min: number; label: string } {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: tz, weekday: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
    .formatToParts(now).map((x) => [x.type, x.value]));
  const dow = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'].indexOf(p.weekday) + 1;
  return { dow, min: Number(p.hour) * 60 + Number(p.minute), label: `${p.hour}:${p.minute}` };
}

export function sessionState(ex: Ex, now = new Date()): { state: 'open' | 'lunch' | 'closed'; next: string; local: string } {
  const { dow, min, label } = localNow(ex.tz, now);
  const days = ex.days ?? [1, 2, 3, 4, 5];
  const fmt = (m: number) => (m >= 60 * 24 ? `${Math.floor(m / 1440)}d ${Math.floor((m % 1440) / 60)}h` : m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m}m`);
  if (days.includes(dow)) {
    for (const [a, b] of ex.sessions) {
      if (min >= mins(a) && min < mins(b)) return { state: 'open', next: `closes in ${fmt(mins(b) - min)}`, local: label };
    }
    const first = mins(ex.sessions[0][0]), last = mins(ex.sessions[ex.sessions.length - 1][1]);
    if (min > first && min < last) {                       // between sessions = lunch break
      const resume = ex.sessions.find(([a]) => mins(a) > min)!;
      return { state: 'lunch', next: `reopens in ${fmt(mins(resume[0]) - min)}`, local: label };
    }
    if (min < first) return { state: 'closed', next: `opens in ${fmt(first - min)}`, local: label };
  }
  // next trading day's open
  let ahead = 0, d = dow;
  do { d = (d % 7) + 1; ahead += 1; } while (!days.includes(d) && ahead < 8);
  const toOpen = ahead * 1440 - min + mins(ex.sessions[0][0]);
  return { state: 'closed', next: `opens in ${fmt(toOpen)}`, local: label };
}

export function MarketClock({ region = 'global', compact = false }: { region?: string; compact?: boolean }) {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 30_000); return () => clearInterval(t); }, []);
  const list = EXCHANGES.filter((e) => region === 'global' || e.region === region);
  return (
    <table className="w-full text-[11px] leading-[18px]">
      {!compact && <thead><tr className="text-text-tertiary"><th className="px-1.5 font-normal text-left">Exchange</th><th className="px-1.5 font-normal text-right">Local</th>
        <th className="px-1.5 font-normal text-left">Status</th><th className="px-1.5 font-normal text-right hidden sm:table-cell">Next</th></tr></thead>}
      <tbody>{list.map((e) => { const s = sessionState(e, now); return (
        <tr key={e.code} className="odd:bg-surface-2/40" title={`${e.name}: ${e.sessions.map(([a, b]) => `${a}–${b}`).join(', ')} local time${e.days ? ' (Sun–Thu)' : ''}. Holidays not shown.`}>
          <td className="px-1.5 whitespace-nowrap"><span className="font-mono text-text-primary">{e.code}</span> <span className="text-text-tertiary">{e.name}</span></td>
          <td className="px-1.5 text-right font-mono text-text-secondary">{s.local}</td>
          <td className="px-1.5"><span className={cn('px-1 text-[10px] border', s.state === 'open' ? 'border-green/50 text-green' : s.state === 'lunch' ? 'border-amber/50 text-amber' : 'border-border text-text-tertiary')}>
            {s.state === 'open' ? 'OPEN' : s.state === 'lunch' ? 'LUNCH' : 'CLOSED'}</span></td>
          <td className="px-1.5 text-right text-text-tertiary whitespace-nowrap hidden sm:table-cell">{s.next}</td>
        </tr>); })}</tbody>
    </table>
  );
}
