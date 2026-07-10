/**
 * EventVolSection — Phase 6A event-driven volatility forecast.
 *
 * The next high-impact macro release + how SPX realized volatility has historically behaved
 * in the ±3 trading-day window around that event type vs baseline. Real SPX vol; historical
 * event dates are cadence-derived (caveat surfaced). Reads /api/v1/event-vol. 3-state load.
 */
import { useCallback, useEffect, useState } from 'react';
import { CalendarClock, RefreshCw, TrendingUp, TrendingDown } from 'lucide-react';
import { DataLineagePopover } from '@/components/ui/DataLineagePopover';

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

export function EventVolSection() {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [reason, setReason] = useState<string | null>(null);

  const load = useCallback(async (attempt = 0) => {
    setLoading(true); setReason(null);
    const timeout = new Promise<null>((r) => setTimeout(() => r(null), 8000));
    try {
      const res = await Promise.race([fetch('/api/v1/event-vol').then((r) => r.json()), timeout]);
      if (!res) { if (attempt < 1) { setTimeout(() => load(attempt + 1), 1500); return; } setReason('Timed out.'); setData(null); }
      else if (!res.available) { setReason(res.reason || 'Unavailable.'); setData(res.next_event ? res : null); }
      else setData(res);
    } catch (e: any) { setReason(e?.message || 'Failed.'); setData(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const ne = data?.next_event;
  const exp = data?.expansion_pct;
  const expands = typeof exp === 'number' && exp > 0;

  return (
    <div id="event-vol" className="terminal-section">
      <div className="section-header mb-3">
        <div className="section-header-left">
          <span className="section-tag"><CalendarClock className="w-3 h-3" /></span>
          <h2 className="section-title">Event Volatility Forecast</h2>
          {data?.source && <DataLineagePopover lineage={{ source: data.source, fetched_at: data.as_of, formula: 'Annualized SPX realized vol in ±3 trading-day windows around the last 8 releases vs full-sample baseline', notes: data.note }} />}
        </div>
        <button onClick={() => load()} title="Refresh" aria-label="Refresh" className="p-1 text-text-tertiary hover:text-bloomberg">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {loading && !data && <div className="p-3 text-2xs text-text-tertiary">Analysing event volatility…</div>}
      {!loading && reason && !ne && <div className="p-3 text-xs text-amber border border-amber/30 bg-amber-dim">Unavailable — {reason}</div>}

      {ne && (
        <div className="space-y-3">
          {/* Forward headline */}
          <div className="p-3 border border-border bg-surface-1">
            <div className="text-sm text-text-primary">
              Next: <span className="font-bold text-bloomberg">{ne.event}</span> in{' '}
              <span className="font-mono font-bold">{ne.days_away}</span> day{ne.days_away === 1 ? '' : 's'}{' '}
              <span className="text-2xs text-text-tertiary">({ne.date})</span>
            </div>
            {typeof exp === 'number' ? (
              <div className="text-2xs text-text-secondary mt-1 flex items-center gap-1">
                {expands ? <TrendingUp className="w-3 h-3 text-amber" /> : <TrendingDown className="w-3 h-3 text-green" />}
                Historically SPX realized vol runs <span className="font-mono text-text-primary">{pct(data.event_vol)}</span> in the ±{data.window}d window vs{' '}
                <span className="font-mono text-text-primary">{pct(data.baseline_vol)}</span> baseline —{' '}
                <span className={`font-mono font-bold ${expands ? 'text-amber' : 'text-green'}`}>{exp >= 0 ? '+' : ''}{exp}%</span>{' '}
                across {data.n_events} releases
              </div>
            ) : (
              <div className="text-2xs text-amber mt-1">{reason || 'Insufficient window history for this event.'}</div>
            )}
          </div>

          {/* Upcoming high-impact events */}
          {data.upcoming?.length > 0 && (
            <div>
              <div className="text-2xs text-text-tertiary uppercase tracking-wider mb-1">Upcoming high-impact</div>
              <div className="flex flex-wrap gap-2">
                {data.upcoming.map((e: any, i: number) => (
                  <div key={i} className="flex items-center gap-2 px-2 py-1 border border-border-subtle bg-surface-1 text-xs">
                    <span className="text-text-secondary">{e.event}</span>
                    <span className="font-mono text-text-primary">{e.days_away}d</span>
                  </div>
                ))}
              </div>
            </div>
          )}
          {data.note && <div className="text-2xs text-text-tertiary">{data.note}</div>}
        </div>
      )}
    </div>
  );
}
