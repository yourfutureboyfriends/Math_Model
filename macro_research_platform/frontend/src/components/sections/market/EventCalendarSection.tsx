// Economic Calendar — official US release dates (FRED release calendar) and FOMC decisions,
// with each release's latest print. No consensus forecasts: there is no licensed source here.

import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { useCallback, useEffect, useState } from 'react';

interface CalendarEvent {
  id: number;
  event_name: string;
  importance: 'HIGH' | 'MEDIUM' | 'LOW';
  release_datetime: string;
  time_et?: string;
  previous: string | null;
  previous_period?: string | null;
  series_id?: string;
  affected_assets?: string[];
  source?: string;
}

interface CalendarData {
  upcoming?: CalendarEvent[];
  this_week?: CalendarEvent[];
  blackout_active?: boolean;
  minutes_to_next?: number | null;
  sources_failed?: string[];
  error?: string;
}

interface Props {
  data?: CalendarData | null;
}

const IMP_CLASS: Record<string, string> = {
  HIGH: 'bg-red-dim text-red',
  MEDIUM: 'bg-amber-dim text-amber',
  LOW: 'bg-surface-3 text-text-tertiary',
};

function countdown(iso: string, now: Date): { label: string; urgent: boolean } {
  const diffMin = Math.floor((new Date(iso).getTime() - now.getTime()) / 60_000);
  if (diffMin <= 5) return { label: 'now', urgent: true };
  if (diffMin < 60) return { label: `${diffMin}m`, urgent: false };
  const h = Math.floor(diffMin / 60);
  if (h < 24) return { label: `${h}h ${diffMin % 60}m`, urgent: false };
  return { label: `${Math.floor(h / 24)}d ${h % 24}h`, urgent: false };
}

function period(p?: string | null): string {
  if (!p) return '';
  const d = new Date(`${p}T00:00:00Z`);
  return d.toLocaleDateString('en-US', { month: 'short', year: '2-digit', timeZone: 'UTC' });
}

export function EventCalendarSection({ data: initial }: Props) {
  const [data, setData] = useState<CalendarData | null>(initial ?? null);
  const [error, setError] = useState<string | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [minImp, setMinImp] = useState<'LOW' | 'MEDIUM' | 'HIGH'>('LOW');
  const [now, setNow] = useState(() => new Date());

  const load = useCallback(async () => {
    try {
      const r = await fetch('/api/calendar');
      const j = await r.json();
      if (!r.ok) throw new Error(typeof j?.detail === 'string' ? j.detail : `HTTP ${r.status}`);
      setData(j); setError(j.error ?? null);
    } catch (e: any) {
      setError(e?.message || 'Calendar unavailable');
    }
  }, []);

  useEffect(() => {
    if (!initial) load();
    const poll = setInterval(load, 30 * 60_000);
    const tick = setInterval(() => setNow(new Date()), 60_000);
    return () => { clearInterval(poll); clearInterval(tick); };
  }, [initial, load]);

  const rank = { LOW: 0, MEDIUM: 1, HIGH: 2 } as const;
  const events = (data?.upcoming ?? []).filter((e) => rank[e.importance] >= rank[minImp]
    && new Date(e.release_datetime).getTime() > now.getTime() - 60 * 60_000);
  const shown = showAll ? events : events.slice(0, 10);
  const next = events.find((e) => new Date(e.release_datetime) > now) ?? null;
  const cd = next ? countdown(next.release_datetime, now) : null;

  return (
    <section id="economic-calendar" className="terminal-section">
      <div className="section-header">
        <span className="section-tag">ECO</span>
        <h2 className="section-title">Economic Calendar</h2>
        {data && (
          <Badge variant={data.blackout_active ? 'danger' : 'info'} className="ml-2">
            {data.blackout_active ? 'BLACKOUT' : `${events.length} releases · 45 days`}
          </Badge>
        )}
        <div className="ml-auto flex gap-1">
          {(['LOW', 'MEDIUM', 'HIGH'] as const).map((l) => (
            <button key={l} onClick={() => setMinImp(l)}
              className={`px-1.5 py-0.5 text-2xs border ${minImp === l ? 'border-bloomberg text-bloomberg' : 'border-border text-text-tertiary hover:text-text-secondary'}`}>
              {l === 'LOW' ? 'All' : l === 'MEDIUM' ? 'Med+' : 'High'}
            </button>
          ))}
        </div>
      </div>

      <Card className="p-4">
        {!data && !error && <div className="h-32 animate-pulse bg-surface-2 rounded" />}
        {error && !events.length && (
          <div className="p-4 text-xs text-amber text-center">
            Calendar unavailable: {error} <button onClick={load} className="ml-2 underline">Retry</button>
          </div>
        )}
        {data && !error && !events.length && (
          <div className="p-6 text-text-secondary text-sm text-center">No releases in the next 45 days at this importance.</div>
        )}
        {events.length > 0 && (
          <>
            {cd && next && (
              <div className={`mb-2 text-xs ${cd.urgent ? 'text-red font-bold' : 'text-text-secondary'}`}>
                Next: <span className="text-text-primary">{next.event_name}</span> {cd.urgent ? 'releasing now' : `in ${cd.label}`}
              </div>
            )}
            <table className="w-full text-xs">
              <thead>
                <tr className="text-2xs text-text-tertiary uppercase border-b border-border-subtle text-left">
                  <th className="font-normal pb-1.5">Date</th>
                  <th className="font-normal pb-1.5">ET</th>
                  <th className="font-normal pb-1.5">Release</th>
                  <th className="font-normal pb-1.5 text-center">Imp</th>
                  <th className="font-normal pb-1.5 text-right">Previous</th>
                  <th className="font-normal pb-1.5 text-right hidden sm:table-cell">Period</th>
                </tr>
              </thead>
              <tbody>
                {shown.map((e) => {
                  const dt = new Date(e.release_datetime);
                  const day = dt.toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric', timeZone: 'America/New_York' });
                  return (
                    <tr key={`${e.event_name}-${e.release_datetime}`} className="border-b border-border-subtle last:border-0"
                      title={[e.source, e.series_id && `headline series ${e.series_id}`, e.affected_assets?.length && `watch ${e.affected_assets.join(', ')}`].filter(Boolean).join(' · ')}>
                      <td className="py-1.5 text-text-secondary whitespace-nowrap">{day}</td>
                      <td className="py-1.5 font-mono text-text-tertiary">{e.time_et ?? '—'}</td>
                      <td className={`py-1.5 ${e.importance === 'HIGH' ? 'text-text-primary font-medium' : 'text-text-secondary'}`}>{e.event_name}</td>
                      <td className="py-1.5 text-center">
                        <span className={`inline-flex items-center justify-center w-5 h-5 text-2xs font-bold font-mono ${IMP_CLASS[e.importance]}`}>{e.importance[0]}</span>
                      </td>
                      <td className="py-1.5 text-right font-mono text-text-primary">{e.previous ?? <span className="text-text-tertiary">—</span>}</td>
                      <td className="py-1.5 text-right text-text-tertiary hidden sm:table-cell">{period(e.previous_period)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {events.length > 10 && (
              <button onClick={() => setShowAll((s) => !s)} className="mt-2 text-2xs text-text-tertiary hover:text-bloomberg">
                {showAll ? 'Show fewer' : `Show all ${events.length}`}
              </button>
            )}
            <div className="mt-2 text-[10px] text-text-tertiary">
              Official release dates (FRED release calendar; Federal Reserve FOMC calendar). Previous = latest published print.
              {data?.sources_failed?.length ? ` Unavailable: ${data.sources_failed.join(', ')}.` : ''}
            </div>
          </>
        )}
      </Card>
    </section>
  );
}
