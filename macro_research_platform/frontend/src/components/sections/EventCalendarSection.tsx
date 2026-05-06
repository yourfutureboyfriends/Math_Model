// Event Calendar / Economic Calendar Section
// Shows upcoming economic data releases
// Calendar polish - importance header, styled nulls, ET times, live countdown

import { Card } from '@/components/ui/Card';
import { Badge } from '@/components/ui/Badge';
import { useState, useEffect } from 'react';

interface CalendarEvent {
  id: number;
  event_name: string;
  importance: 'HIGH' | 'MEDIUM' | 'LOW';
  release_datetime: string;
  time_et?: string;
  actual: string | null;
  forecast: string | null;
  previous: string | null;
  affected_assets?: string[];
}

interface Props {
  data?: {
    upcoming?: CalendarEvent[];
    this_week?: CalendarEvent[];
    blackout_active?: boolean;
    minutes_to_next?: number;
  } | null;
}

export function EventCalendarSection({ data }: Props) {
  const [loading, setLoading] = useState(!data);
  const [timedOut, setTimedOut] = useState(false);
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    if (data) setLoading(false);
  }, [data]);

  // FIXED (BUG 8): Timeout after 10 seconds to prevent infinite loading (Fix 8)
  useEffect(() => {
    const t = setTimeout(() => setTimedOut(true), 10000);
    return () => clearTimeout(t);
  }, []);

  // Live countdown timer - updates every minute
  useEffect(() => {
    const interval = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(interval);
  }, []);

  // Loading state with timeout
  if (loading && !timedOut) {
    return (
      <section id="economic-calendar" className="terminal-section">
        <div className="section-header">
          <span className="section-tag">ECO</span>
          <h2 className="section-title">Economic Calendar</h2>
          <Badge variant="info" className="ml-2">Loading...</Badge>
        </div>
        <Card className="p-4">
          <div className="h-32 animate-pulse bg-surface-2 rounded" />
        </Card>
      </section>
    );
  }

  // No data state
  if (!data || (!data.upcoming?.length && !data.this_week?.length)) {
    return (
      <section id="economic-calendar" className="terminal-section">
        <div className="section-header">
          <span className="section-tag">ECO</span>
          <h2 className="section-title">Economic Calendar</h2>
        </div>
        <Card className="p-4">
          <div className="p-6 text-text-secondary text-sm text-center">
            No upcoming economic events scheduled.
          </div>
        </Card>
      </section>
    );
  }

  const events = data.upcoming || data.this_week || [];

  // Importance badge with color coding
  const ImpBadge = ({ level }: { level: string }) => {
    const imp = level?.toLowerCase();
    let colorClass = 'bg-surface-3 text-text-tertiary';
    if (imp === 'high') colorClass = 'bg-red-dim text-red';
    if (imp === 'medium') colorClass = 'bg-amber-dim text-amber';

    return (
      <span className={`inline-flex items-center justify-center w-5 h-5 text-xs font-bold font-mono ${colorClass}`}>
        {level?.charAt(0) || '—'}
      </span>
    );
  };

  // Styled formatter for null/undefined values
  const fmtCalVal = (val: string | number | null | undefined) => {
    if (val === null || val === undefined || val === '') {
      return <span className="text-text-tertiary">—</span>;
    }
    return <span>{val}</span>;
  };

  // Format date/time with ET label
  const formatDateTime = (isoDate: string, timeEt?: string) => {
    if (!isoDate) return { date: '—', time: '—' };
    try {
      const date = new Date(isoDate);
      return {
        // FIXED (BUG 8): Use ISO date format
        date: date.toISOString().split('T')[0],
        time: timeEt || date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })
      };
    } catch {
      return { date: '—', time: '—' };
    }
  };

  // Get countdown to next event
  const getCountdown = (nextEvent: CalendarEvent | null) => {
    if (!nextEvent?.release_datetime) return null;
    const nextDt = new Date(nextEvent.release_datetime);
    const diffMs = nextDt.getTime() - now.getTime();
    if (diffMs <= 0) return { label: 'LIVE NOW', urgent: true };

    const diffMin = Math.floor(diffMs / 60_000);
    const diffH = Math.floor(diffMin / 60);
    const diffD = Math.floor(diffH / 24);
    const remH = diffH % 24;
    const remM = diffMin % 60;

    if (diffMin <= 5) return { label: 'LIVE NOW', urgent: true };
    if (diffMin < 60) return { label: `${diffMin}m`, urgent: false };
    if (diffH < 24) return { label: `${diffH}h ${remM}m`, urgent: false };
    return { label: `${diffD}d ${remH}h`, urgent: false };
  };

  const nextEvent = events[0] || null;
  const countdown = getCountdown(nextEvent);

  return (
    <section id="economic-calendar" className="terminal-section">
      <div className="section-header">
        <span className="section-tag">ECO</span>
        <h2 className="section-title">Economic Calendar</h2>
        <Badge variant={data.blackout_active ? 'danger' : 'info'} className="ml-2">
          {data.blackout_active ? 'BLACKOUT' : `${events.length} Events`}
        </Badge>
      </div>

      <Card className="p-4">
        <div className="space-y-3">
          {/* Added Imp column header */}
          <div className="grid grid-cols-7 text-2xs text-text-tertiary uppercase border-b border-border-subtle pb-2">
            <span>Date</span>
            <span>Time</span>
            <span className="col-span-2">Event</span>
            <span className="text-center">Imp</span>
            <span className="text-right">Prev</span>
            <span className="text-right">Fcst</span>
          </div>
          {events.slice(0, 8).map((event) => {
            const { date, time } = formatDateTime(event.release_datetime, event.time_et);
            // Color event name by importance
            const eventNameClass = event.importance === 'HIGH'
              ? 'text-text-primary font-medium'
              : event.importance === 'MEDIUM'
                ? 'text-text-secondary'
                : 'text-text-tertiary';

            return (
              <div key={event.id} className="grid grid-cols-7 text-sm py-2 border-b border-border-subtle last:border-0">
                <span className="text-text-secondary">{date}</span>
                <span className="text-text-secondary font-mono text-xs">{time}</span>
                <span className={`col-span-2 ${eventNameClass}`}>
                  {event.event_name}
                </span>
                {/* Importance badge in its own column */}
                <span className="flex justify-center">
                  <ImpBadge level={event.importance} />
                </span>
                {/* Styled null values */}
                <span className="text-text-secondary text-right">{fmtCalVal(event.previous)}</span>
                <span className="text-text-primary text-right">{fmtCalVal(event.forecast)}</span>
              </div>
            );
          })}
        </div>

        {/* Live countdown with urgency indicator */}
        {countdown && (
          <div className={`mt-3 text-xs ${
            countdown.urgent
              ? 'text-red font-bold animate-pulse'
              : 'text-text-secondary'
          }`}>
            {countdown.urgent
              ? `⚡ LIVE NOW — ${nextEvent?.event_name}`
              : nextEvent
                ? `Next: ${nextEvent.event_name} in ${countdown.label}`
                : 'No upcoming events'}
          </div>
        )}
      </Card>
    </section>
  );
}
